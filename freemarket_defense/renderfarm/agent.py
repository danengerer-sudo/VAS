#!/usr/bin/env python3
"""
renderfarm agent -- renders Blender jobs that arrive through this git repository.

Standard library only, Python 3.11+.  Runs on the Windows mini PC(s); also runs on
Linux (used for --dry-run testing).

    python agent.py                 # loop forever: pull, claim chunks, render, push progress
    python agent.py --once          # one poll cycle, then exit
    python agent.py --bench         # benchmark frames 1-48 of bench/bench.blend, push bench_result.json
    python agent.py --dry-run ...   # run `blender --version` instead of rendering, never commit/push
    python agent.py --job <id>      # only consider this job

Layout (relative to this file):
    config.json                 local config (copy of config.example.json, git-ignored)
    jobs/<job_id>/job.json      job description, pushed by submit.py from the cloud side
    jobs/<job_id>/<file>.blend  packed blend (or job.json["blend_url"] -> downloaded to jobs/<id>/_dl/)
    jobs/<job_id>/claims/<worker>.json     chunks this worker claimed (committed)
    jobs/<job_id>/progress/<worker>.json   per-chunk progress of this worker (committed every ~10 min)
    jobs/<job_id>/frames/       rendered PNGs (git-ignored; uploaded by rclone or zipped to outbox/)
    jobs/<job_id>/done.json     written when every chunk is done (committed)
    jobs/<job_id>/failed.json   written when the job could not be processed (committed)
    logs/agent.log              rotating log (git-ignored)
    outbox/<job_id>/*.zip       zipped frames for manual upload when rclone is not configured
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import logging.handlers
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
JOBS_DIR = HERE / "jobs"
LOG_DIR = HERE / "logs"
BENCH_DIR = HERE / "bench"
DEFAULT_OUTBOX = HERE / "outbox"
MIN_FRAME_BYTES = 1024          # files smaller than this are treated as broken/partial frames
DEFAULT_CHUNK = 240
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec"

log = logging.getLogger("agent")


# ----------------------------------------------------------------------------- helpers
def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(s: str) -> float:
    try:
        return _dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
    except Exception:
        return 0.0


def read_json(path: Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except Exception as exc:  # corrupt file: treat as missing but say so
        log.warning("bad json %s: %s", path, exc)
        return default


def write_json(path: Path, data) -> None:
    """Atomic-ish write (write temp, then replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def human_time(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def chunk_key(a: int, b: int) -> str:
    return f"{a}-{b}"


def make_chunks(start: int, end: int, size: int) -> List[Tuple[int, int]]:
    size = max(1, int(size or DEFAULT_CHUNK))
    out = []
    a = start
    while a <= end:
        b = min(end, a + size - 1)
        out.append((a, b))
        a = b + 1
    return out


def frame_path(frames_dir: Path, pattern: str, frame: int, ext: str) -> Path:
    """Expand Blender's '####' padding in `pattern` (e.g. 'frames/f_####') for one frame."""
    name = Path(pattern).name
    m = re.search(r"#+", name)
    if m:
        name = name[: m.start()] + str(frame).zfill(len(m.group(0))) + name[m.end():]
    else:
        name = name + str(frame).zfill(4)
    if not name.lower().endswith(ext.lower()):
        name += ext
    return frames_dir / name


FORMAT_EXT = {"PNG": ".png", "JPEG": ".jpg", "OPEN_EXR": ".exr", "OPEN_EXR_MULTILAYER": ".exr",
              "TIFF": ".tif", "BMP": ".bmp", "WEBP": ".webp", "TARGA": ".tga"}


# ----------------------------------------------------------------------------- config
class Config:
    def __init__(self, path: Path, overrides: Optional[dict] = None):
        data = read_json(path, None)
        if data is None:
            raise SystemExit(f"config not found: {path}\n"
                             f"copy {HERE / 'config.example.json'} to {path} and edit it.")
        data.update(overrides or {})
        self.blender: str = data.get("blender") or "blender"
        self.repo: Path = Path(data.get("repo") or self._find_repo()).resolve()
        self.branch: str = data.get("branch") or "main"
        self.worker: str = data.get("worker") or socket.gethostname()
        self.poll_minutes: float = float(data.get("poll_minutes") or 5)
        self.push_minutes: float = float(data.get("push_minutes") or 10)
        self.uploader: str = data.get("uploader") or "auto"
        self.rclone_remote: str = data.get("rclone_remote") or ""
        self.rclone: str = data.get("rclone") or "rclone"
        self.git: str = data.get("git") or "git"
        self.outbox_dir: Path = Path(data.get("outbox_dir") or DEFAULT_OUTBOX)
        self.zip_part_bytes: int = int(data.get("zip_part_bytes") or 1_900_000_000)
        self.claim_stale_hours: float = float(data.get("claim_stale_hours") or 12)
        self.bench_url: str = data.get("bench_url") or ""
        self.blender_extra_args: List[str] = list(data.get("blender_extra_args") or [])
        if self.uploader == "auto":
            self.uploader = "rclone" if self.rclone_remote else "zip"

    @staticmethod
    def _find_repo() -> Path:
        p = HERE
        for _ in range(6):
            if (p / ".git").exists():
                return p
            p = p.parent
        return HERE.parents[1]


# ----------------------------------------------------------------------------- git
class Git:
    """Thin wrapper around the git CLI. All methods swallow errors and return success flags."""

    def __init__(self, cfg: Config, dry_run: bool):
        self.cfg = cfg
        self.dry_run = dry_run
        self.lock = threading.Lock()

    def run(self, *args: str, check: bool = False, quiet: bool = False) -> subprocess.CompletedProcess:
        cmd = [self.cfg.git, *args]
        if not quiet:
            log.debug("git %s", " ".join(args))
        cp = subprocess.run(cmd, cwd=str(self.cfg.repo), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        if check and cp.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed ({cp.returncode}): {cp.stderr.strip()}")
        return cp

    def rel(self, path: Path) -> str:
        return str(Path(path).resolve().relative_to(self.cfg.repo)).replace(os.sep, "/")

    def has_lfs(self) -> bool:
        return self.run("lfs", "version", quiet=True).returncode == 0

    def pull(self) -> bool:
        """Fetch + rebase onto origin/<branch>. Never raises. On conflict: abort and hard reset
        to the remote (our own committed-but-unpushed state is regenerated from disk anyway)."""
        if self.dry_run:
            log.info("[dry-run] skip git pull")
            return True
        with self.lock:
            cp = self.run("pull", "--rebase", "--autostash", "origin", self.cfg.branch)
            if cp.returncode == 0:
                return True
            log.warning("git pull failed: %s", (cp.stderr or cp.stdout).strip()[-800:])
            git_dir = self.cfg.repo / ".git"
            in_rebase = (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()
            if in_rebase or "CONFLICT" in cp.stdout + cp.stderr:
                self.run("rebase", "--abort")
                self.run("stash", "drop")  # autostash may have been left behind; ignore result
                cp2 = self.run("reset", "--hard", f"origin/{self.cfg.branch}")
                log.warning("resolved by hard reset to origin/%s (%s)", self.cfg.branch,
                            "ok" if cp2.returncode == 0 else cp2.stderr.strip())
                return cp2.returncode == 0
            return False  # most likely offline; carry on with what we have

    def commit_push(self, paths: List[Path], message: str, retries: int = 4) -> bool:
        """Stage `paths`, commit if there is anything to commit, push; on rejection pull --rebase
        and retry. Never raises."""
        if self.dry_run:
            log.info("[dry-run] skip commit/push: %s (%d paths)", message, len(paths))
            return True
        with self.lock:
            rels = [self.rel(p) for p in paths if Path(p).exists()]
            if not rels:
                return True
            self.run("add", "--", *rels)
            cp = self.run("diff", "--cached", "--quiet")
            if cp.returncode == 0:
                return True  # nothing staged
            cp = self.run("commit", "-q", "-m", message, "--", *rels)
            if cp.returncode != 0:
                log.warning("git commit failed: %s", cp.stderr.strip()[-500:])
                return False
            for attempt in range(1, retries + 1):
                cp = self.run("push", "-q", "origin", f"HEAD:{self.cfg.branch}")
                if cp.returncode == 0:
                    log.info("pushed: %s", message)
                    return True
                log.warning("push attempt %d failed: %s", attempt, cp.stderr.strip()[-400:])
                cp = self.run("pull", "--rebase", "--autostash", "origin", self.cfg.branch)
                if cp.returncode != 0:
                    log.warning("rebase during push-retry failed: %s", cp.stderr.strip()[-400:])
                    self.run("rebase", "--abort")
                    self.run("reset", "--hard", f"origin/{self.cfg.branch}")
                    # re-stage our files from disk and commit again
                    self.run("add", "--", *rels)
                    if self.run("diff", "--cached", "--quiet").returncode == 0:
                        return True  # remote already has identical content
                    self.run("commit", "-q", "-m", message, "--", *rels)
                time.sleep(2 * attempt)
            return False


# ----------------------------------------------------------------------------- uploaders
# An uploader is: fn(cfg, job_id, frames_dir, files, log) -> bool.  `files` is the list of frame
# paths (Path) that just finished.  Register a new one by adding it to UPLOADERS.
Uploader = Callable[[Config, str, Path, List[Path]], bool]


def upload_none(cfg: Config, job_id: str, frames_dir: Path, files: List[Path]) -> bool:
    log.info("uploader=none: %d frames stay in %s", len(files), frames_dir)
    return True


def upload_rclone(cfg: Config, job_id: str, frames_dir: Path, files: List[Path]) -> bool:
    """rclone copy <frames_dir> <remote>/<job_id>/frames  (skips files already identical remote-side)."""
    if not cfg.rclone_remote:
        log.error("uploader=rclone but rclone_remote is empty in config; falling back to zip")
        return upload_zip(cfg, job_id, frames_dir, files)
    dest = f"{cfg.rclone_remote.rstrip('/')}/{job_id}/frames"
    cmd = [cfg.rclone, "copy", str(frames_dir), dest, "--transfers", "4", "--checkers", "8",
           "--retries", "5", "--low-level-retries", "20", "--stats-one-line", "--stats", "60s",
           "--exclude", "*.tmp", "--exclude", "*.part"]
    log.info("rclone upload -> %s (%d new frames)", dest, len(files))
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=6 * 3600)
    except FileNotFoundError:
        log.error("rclone executable not found (%s); falling back to zip", cfg.rclone)
        return upload_zip(cfg, job_id, frames_dir, files)
    except subprocess.TimeoutExpired:
        log.error("rclone timed out")
        return False
    if cp.returncode != 0:
        log.error("rclone failed (%d): %s", cp.returncode, (cp.stderr or cp.stdout).strip()[-800:])
        return False
    log.info("rclone ok: %s", (cp.stderr or cp.stdout).strip().splitlines()[-1:] or "")
    return True


def upload_zip(cfg: Config, job_id: str, frames_dir: Path, files: List[Path]) -> bool:
    """Zip `files` into <outbox>/<job_id>/<job>_<worker>_<first>-<last>_partN.zip, each part
    <= cfg.zip_part_bytes (1.9 GB default) so they can be uploaded by hand anywhere."""
    if not files:
        return True
    files = sorted(files)
    out_dir = cfg.outbox_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    first, last = files[0].stem, files[-1].stem
    base = f"{job_id}_{cfg.worker}_{first}-{last}"
    part, part_bytes, zf = 1, 0, None
    try:
        for f in files:
            size = f.stat().st_size
            if zf is None or (part_bytes + size > cfg.zip_part_bytes and part_bytes > 0):
                if zf is not None:
                    zf.close()
                    part += 1
                zpath = out_dir / f"{base}_part{part}.zip"
                zf = zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_STORED, allowZip64=True)
                part_bytes = 0
                log.info("zipping -> %s", zpath)
            zf.write(f, arcname=f"{job_id}/frames/{f.name}")
            part_bytes += size
    finally:
        if zf is not None:
            zf.close()
    log.info("zip uploader: %d frames in %d part(s) under %s (upload manually)", len(files), part, out_dir)
    return True


UPLOADERS: Dict[str, Uploader] = {"none": upload_none, "rclone": upload_rclone, "zip": upload_zip}


# ----------------------------------------------------------------------------- blender
def blender_python_expr(job: dict, engine: str) -> str:
    """Python executed inside Blender before rendering: resolution, samples, persistent data,
    output format, and (for CYCLES) HIP GPU with CPU fallback."""
    rx, ry = (job.get("resolution") or [1920, 1080])[:2]
    samples = int(job.get("samples") or 16)
    fmt = (job.get("format") or "PNG").upper()
    lines = [
        "import bpy",
        "sc=bpy.context.scene",
        "r=sc.render",
        f"r.engine={engine!r}",
        f"r.resolution_x={int(rx)}; r.resolution_y={int(ry)}; r.resolution_percentage=100",
        f"r.image_settings.file_format={fmt!r}",
        "r.use_persistent_data=True",
        "r.use_overwrite=True; r.use_placeholder=False; r.use_file_extension=True",
        f"sc.eevee.taa_render_samples={samples}",
        f"sc.cycles.samples={samples}",
        "sc.cycles.use_denoising=True",
        # Cycles device: HIP if available, else CPU. EEVEE always uses the GPU via OpenGL/Vulkan.
        "def _dev():",
        "    try:",
        "        p=bpy.context.preferences.addons['cycles'].preferences",
        "        p.compute_device_type='HIP'",
        "        p.get_devices()",
        "        hip=[d for d in p.devices if d.type=='HIP']",
        "        if not hip: raise RuntimeError('no HIP device')",
        "        for d in p.devices: d.use = d.type in ('HIP','CPU')",
        "        sc.cycles.device='GPU'",
        "        print('AGENT: cycles device HIP:', [d.name for d in hip])",
        "    except Exception as e:",
        "        try:",
        "            bpy.context.preferences.addons['cycles'].preferences.compute_device_type='NONE'",
        "        except Exception: pass",
        "        sc.cycles.device='CPU'",
        "        print('AGENT: cycles device CPU (HIP unavailable: %s)' % e)",
        f"if {engine!r}=='CYCLES': _dev()",
        f"print('AGENT: settings', r.engine, r.resolution_x, r.resolution_y, {samples})",
    ]
    return "\n".join(lines)


_RE_SAVED = re.compile(r"^Saved: '(.+?)'")
_RE_FRA = re.compile(r"^Fra:(\d+)")
_RE_TIME = re.compile(r"\bTime: (\d+):(\d+\.\d+)")


class BlenderRun:
    """Runs one Blender process rendering a list of frames and streams its stdout to a log file.
    `on_frame(frame, seconds)` is called after every saved frame."""

    def __init__(self, cfg: Config, dry_run: bool):
        self.cfg = cfg
        self.dry_run = dry_run
        self.proc: Optional[subprocess.Popen] = None
        self.current_frame: Optional[int] = None
        self.stop_requested = False

    def terminate(self):
        self.stop_requested = True
        p = self.proc
        if p and p.poll() is None:
            log.info("terminating blender pid %s", p.pid)
            try:
                p.terminate()
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
            except Exception:
                pass

    def render(self, blend: Path, job: dict, engine: str, out_pattern: Path, frames: List[int],
               log_file: Path, on_frame: Callable[[int, float], None]) -> Tuple[bool, str]:
        if not frames:
            return True, "nothing to render"
        fmt = (job.get("format") or "PNG").upper()
        if self.dry_run:
            cmd = [self.cfg.blender, "--version"]
        else:
            cmd = [self.cfg.blender, "-b", str(blend), "--python-expr", blender_python_expr(job, engine),
                   "-E", engine, "-o", str(out_pattern), "-F", fmt, "-x", "1",
                   *self.cfg.blender_extra_args, "-f", compress_frames(frames)]
        log.info("blender: %s", " ".join(f'"{c}"' if " " in c else c for c in cmd if not c.startswith("import bpy")))
        log_file.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        t_frame = time.monotonic()
        last_lines: List[str] = []
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, encoding="utf-8", errors="replace", env=env,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError:
            return False, f"blender executable not found: {self.cfg.blender}"
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(f"\n==== {utcnow()} {' '.join(cmd[:3])} ... frames={compress_frames(frames)}\n")
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                lf.write(line)
                line = line.rstrip()
                last_lines.append(line)
                if len(last_lines) > 30:
                    last_lines.pop(0)
                m = _RE_FRA.match(line)
                if m:
                    self.current_frame = int(m.group(1))
                    continue
                m = _RE_SAVED.match(line)
                if m:
                    now = time.monotonic()
                    saved = Path(m.group(1))
                    fr = frame_from_name(saved.name)
                    if fr is None:
                        fr = self.current_frame
                    if fr is not None:
                        on_frame(fr, now - t_frame)
                    t_frame = now
                    self.current_frame = None
            rc = self.proc.wait()
        if self.dry_run:
            # pretend every requested frame rendered (2 KB placeholder, so the loop logic can finish)
            for fr in frames:
                p = frame_path(out_pattern.parent, out_pattern.name, fr, FORMAT_EXT.get(fmt, ".png"))
                p.parent.mkdir(parents=True, exist_ok=True)
                if not p.exists():
                    with open(p, "wb") as fh:
                        fh.write(b"DRY-RUN PLACEHOLDER\n" + b"\0" * 2048)
                on_frame(fr, 0.01)
        if self.stop_requested:
            return False, "interrupted"
        if rc != 0:
            return False, f"blender exit code {rc}: " + " | ".join(last_lines[-5:])
        return True, "ok"


def frame_from_name(name: str) -> Optional[int]:
    m = re.search(r"(\d+)\.[A-Za-z0-9]+$", name)
    return int(m.group(1)) if m else None


def compress_frames(frames: List[int]) -> str:
    """[1,2,3,7,9,10] -> '1..3,7,9..10'  (Blender -f accepts comma lists and a..b ranges)."""
    frames = sorted(set(frames))
    parts = []
    i = 0
    while i < len(frames):
        j = i
        while j + 1 < len(frames) and frames[j + 1] == frames[j] + 1:
            j += 1
        parts.append(str(frames[i]) if i == j else f"{frames[i]}..{frames[j]}")
        i = j + 1
    return ",".join(parts)


# ----------------------------------------------------------------------------- job model
class Job:
    def __init__(self, folder: Path):
        self.folder = folder
        self.id = folder.name
        self.data = read_json(folder / "job.json", None)
        self.claims_dir = folder / "claims"
        self.progress_dir = folder / "progress"

    @property
    def ok(self) -> bool:
        return isinstance(self.data, dict) and "frame_start" in self.data and "frame_end" in self.data

    @property
    def done(self) -> bool:
        return (self.folder / "done.json").exists()

    @property
    def failed(self) -> bool:
        return (self.folder / "failed.json").exists()

    @property
    def priority(self) -> int:
        try:
            return int(self.data.get("priority", 5))
        except Exception:
            return 5

    @property
    def engine(self) -> str:
        e = str(self.data.get("engine") or "BLENDER_EEVEE_NEXT").upper()
        if e in ("EEVEE", "BLENDER_EEVEE"):
            e = "BLENDER_EEVEE_NEXT"
        return e

    @property
    def fmt(self) -> str:
        return str(self.data.get("format") or "PNG").upper()

    @property
    def ext(self) -> str:
        return FORMAT_EXT.get(self.fmt, "." + self.fmt.lower())

    @property
    def output_pattern(self) -> str:
        return str(self.data.get("output") or "frames/f_####")

    @property
    def frames_dir(self) -> Path:
        return (self.folder / self.output_pattern).parent

    def chunks(self) -> List[Tuple[int, int]]:
        return make_chunks(int(self.data["frame_start"]), int(self.data["frame_end"]),
                           int(self.data.get("chunk") or DEFAULT_CHUNK))

    def frame_file(self, frame: int) -> Path:
        return frame_path(self.frames_dir, self.output_pattern, frame, self.ext)

    def frame_exists(self, frame: int, min_bytes: int = MIN_FRAME_BYTES) -> bool:
        p = self.frame_file(frame)
        try:
            return p.stat().st_size >= min_bytes
        except FileNotFoundError:
            return False

    def missing_frames(self, a: int, b: int) -> List[int]:
        return [f for f in range(a, b + 1) if not self.frame_exists(f)]

    # -- claims / progress (one file per worker, so no textual git conflicts)
    def all_claims(self) -> Dict[str, dict]:
        out = {}
        if self.claims_dir.is_dir():
            for p in sorted(self.claims_dir.glob("*.json")):
                d = read_json(p, None)
                if isinstance(d, dict):
                    out[p.stem] = d
        return out

    def all_progress(self) -> Dict[str, dict]:
        out = {}
        if self.progress_dir.is_dir():
            for p in sorted(self.progress_dir.glob("*.json")):
                d = read_json(p, None)
                if isinstance(d, dict):
                    out[p.stem] = d
        return out

    def chunk_owner(self, key: str, stale_hours: float) -> Optional[str]:
        """Worker owning chunk `key`: earliest claim wins (tie -> worker name). Claims whose
        worker has shown no progress for `stale_hours` and are not done are ignored."""
        best = None
        progress = self.all_progress()
        now = time.time()
        for worker, claim in self.all_claims().items():
            c = (claim.get("chunks") or {}).get(key)
            if not c:
                continue
            prog = (progress.get(worker, {}).get("chunks") or {}).get(key, {})
            if prog.get("status") == "done":
                return worker
            last = max(parse_utc(c.get("claimed_at", "")), parse_utc(progress.get(worker, {}).get("updated", "")))
            if stale_hours > 0 and now - last > stale_hours * 3600:
                continue  # stale claim, treat as free
            cand = (parse_utc(c.get("claimed_at", "")), worker)
            if best is None or cand < best:
                best = cand
        return best[1] if best else None

    def done_chunks(self) -> Dict[str, dict]:
        out = {}
        for worker, prog in self.all_progress().items():
            for key, c in (prog.get("chunks") or {}).items():
                if c.get("status") == "done":
                    c = dict(c)
                    c["worker"] = worker
                    out[key] = c
        return out


# ----------------------------------------------------------------------------- agent
class Agent:
    def __init__(self, cfg: Config, dry_run: bool, only_job: Optional[str] = None):
        self.cfg = cfg
        self.dry_run = dry_run
        self.only_job = only_job
        self.git = Git(cfg, dry_run)
        self.runner = BlenderRun(cfg, dry_run)
        self.stop = False
        self.uploader = UPLOADERS.get(cfg.uploader) or upload_zip
        if cfg.uploader not in UPLOADERS:
            log.warning("unknown uploader %r, using zip", cfg.uploader)
        self._pending_push: List[Path] = []
        self._last_push = 0.0

    # -- signals
    def request_stop(self, *_):
        if not self.stop:
            log.info("stop requested (Ctrl-C) - finishing current frame, then exiting")
        self.stop = True
        self.runner.terminate()

    # -- main loop
    def loop(self, once: bool = False):
        log.info("agent %s starting; repo=%s branch=%s blender=%s uploader=%s dry_run=%s",
                 self.cfg.worker, self.cfg.repo, self.cfg.branch, self.cfg.blender, self.cfg.uploader, self.dry_run)
        while not self.stop:
            try:
                worked = self.poll_once()
            except KeyboardInterrupt:
                self.request_stop()
                break
            except Exception:
                log.error("poll cycle crashed (continuing):\n%s", traceback.format_exc())
                worked = False
            if once:
                break
            if self.stop:
                break
            if not worked:
                wait = self.cfg.poll_minutes * 60
                log.info("idle; next poll in %.0f min", self.cfg.poll_minutes)
                self._sleep(wait)
        self.flush_push(force=True)
        log.info("agent exiting")

    def _sleep(self, seconds: float):
        end = time.monotonic() + seconds
        while not self.stop and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    def poll_once(self) -> bool:
        """Pull, pick a job with a free chunk, render that chunk. Returns True if work was done."""
        self.git.pull()
        jobs = self.list_jobs()
        for job in jobs:
            if self.stop:
                return False
            if job.done or job.failed:
                continue
            if not job.ok:
                self.mark_failed(job, "job.json missing or lacks frame_start/frame_end")
                continue
            try:
                worked = self.work_on_job(job)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log.error("job %s failed:\n%s", job.id, traceback.format_exc())
                self.mark_failed(job, f"{type(exc).__name__}: {exc}")
                continue
            if worked:
                return True
        return False

    def list_jobs(self) -> List[Job]:
        if not JOBS_DIR.is_dir():
            return []
        jobs = [Job(p) for p in JOBS_DIR.iterdir() if p.is_dir() and (p / "job.json").exists()]
        if self.only_job:
            jobs = [j for j in jobs if j.id == self.only_job]
        jobs.sort(key=lambda j: (j.priority, j.id))
        return jobs

    # -- one job
    def work_on_job(self, job: Job) -> bool:
        chunks = job.chunks()
        done = job.done_chunks()
        if len(done) >= len(chunks) and all(chunk_key(a, b) in done for a, b in chunks):
            self.finish_job(job)
            return True  # wrote done.json; count as work
        # pick a chunk: prefer our existing claims that are not done, then free chunks
        my_claim = job.all_claims().get(self.cfg.worker, {"chunks": {}})
        mine = [(a, b) for a, b in chunks if chunk_key(a, b) in (my_claim.get("chunks") or {})
                and chunk_key(a, b) not in done]
        target = None
        for a, b in mine:
            if job.chunk_owner(chunk_key(a, b), self.cfg.claim_stale_hours) in (self.cfg.worker, None):
                target = (a, b)
                break
        if target is None:
            for a, b in chunks:
                key = chunk_key(a, b)
                if key in done:
                    continue
                if job.chunk_owner(key, self.cfg.claim_stale_hours) is None:
                    if self.claim_chunk(job, a, b):
                        target = (a, b)
                        break
        if target is None:
            return False
        a, b = target
        log.info("job %s: rendering chunk %s", job.id, chunk_key(a, b))
        blend = self.resolve_blend(job)
        ok = self.render_chunk(job, blend, a, b)
        self.flush_push(force=True)
        return ok or self.stop

    def claim_chunk(self, job: Job, a: int, b: int) -> bool:
        """Write/extend claims/<worker>.json, commit+push; then re-check we really own the chunk
        (the other worker may have pushed a claim first)."""
        key = chunk_key(a, b)
        path = job.claims_dir / f"{self.cfg.worker}.json"
        for attempt in range(3):
            claim = read_json(path, None) or {"worker": self.cfg.worker, "chunks": {}}
            claim.setdefault("chunks", {})
            claim["chunks"][key] = {"start": a, "end": b, "claimed_at": utcnow()}
            claim["host"] = socket.gethostname()
            claim["updated"] = utcnow()
            write_json(path, claim)
            pushed = self.git.commit_push([path], f"renderfarm: {self.cfg.worker} claims {job.id} {key}")
            if not pushed and not self.dry_run:
                log.warning("could not push claim for %s %s (offline?) - rendering anyway", job.id, key)
            owner = job.chunk_owner(key, self.cfg.claim_stale_hours)
            if owner in (self.cfg.worker, None):
                log.info("claimed %s %s", job.id, key)
                return True
            # lost the race: drop our claim on this chunk and try the next chunk
            log.info("chunk %s %s already claimed by %s; yielding", job.id, key, owner)
            claim = read_json(path, None) or {}
            (claim.get("chunks") or {}).pop(key, None)
            write_json(path, claim)
            self.git.commit_push([path], f"renderfarm: {self.cfg.worker} yields {job.id} {key}")
            return False
        return False

    def resolve_blend(self, job: Job) -> Path:
        """Return a local path to the .blend: relative path in the job folder (git or git-lfs),
        or download job.json['blend_url'] / a URL in 'blend' into jobs/<id>/_dl/."""
        spec = str(job.data.get("blend") or "")
        url = job.data.get("blend_url") or (spec if spec.startswith(("http://", "https://")) else "")
        local = None
        if spec and not spec.startswith(("http://", "https://")):
            local = (job.folder / spec).resolve()
            if local.exists():
                with open(local, "rb") as fh:
                    head = fh.read(len(LFS_POINTER_PREFIX))
                if head == LFS_POINTER_PREFIX:
                    log.info("%s is a git-lfs pointer; fetching", local.name)
                    if self.git.has_lfs():
                        cp = self.git.run("lfs", "pull", "--include", self.git.rel(local))
                        if cp.returncode != 0:
                            log.warning("git lfs pull failed: %s", cp.stderr.strip()[-300:])
                    else:
                        log.warning("git lfs is not installed on this machine")
                    with open(local, "rb") as fh:
                        if fh.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX:
                            local = None  # still a pointer
                if local is not None and local.exists() and local.stat().st_size > 0:
                    return local
            local = None
        if url:
            dl_dir = job.folder / "_dl"
            name = Path(spec).name if spec and not spec.startswith("http") else (url.split("?")[0].rstrip("/").split("/")[-1] or "job.blend")
            if not name.lower().endswith(".blend"):
                name += ".blend"
            dest = dl_dir / name
            if not dest.exists() or dest.stat().st_size == 0:
                download(url, dest, job.data.get("blend_sha256"))
            return dest
        raise FileNotFoundError(f"blend not found: {spec!r} and no blend_url (job {job.id})")

    def render_chunk(self, job: Job, blend: Path, a: int, b: int) -> bool:
        key = chunk_key(a, b)
        missing = job.missing_frames(a, b)
        total = b - a + 1
        prog_path = job.progress_dir / f"{self.cfg.worker}.json"
        prog = read_json(prog_path, None) or {"worker": self.cfg.worker, "chunks": {}}
        prog.setdefault("chunks", {})
        cprog = prog["chunks"].setdefault(key, {"start": a, "end": b, "frames_total": total,
                                                "frames_done": 0, "seconds": 0.0, "sec_per_frame": None,
                                                "status": "rendering", "started_at": utcnow()})
        cprog["frames_total"] = total
        cprog["frames_done"] = total - len(missing)
        cprog["status"] = "rendering"
        state = {"frames_this_run": 0, "seconds_this_run": 0.0, "new_files": []}

        def save_progress(status: Optional[str] = None):
            if status:
                cprog["status"] = status
            if state["frames_this_run"]:
                cprog["sec_per_frame"] = round(state["seconds_this_run"] / state["frames_this_run"], 2)
            cprog["updated"] = utcnow()
            prog["updated"] = utcnow()
            prog["host"] = socket.gethostname()
            prog["blender"] = self.cfg.blender
            prog["engine"] = job.engine
            prog["frames_done_total"] = sum(int(c.get("frames_done", 0)) for c in prog["chunks"].values())
            spf = [c["sec_per_frame"] for c in prog["chunks"].values() if c.get("sec_per_frame")]
            prog["sec_per_frame"] = round(sum(spf) / len(spf), 2) if spf else None
            write_json(prog_path, prog)

        def on_frame(frame: int, seconds: float):
            if a <= frame <= b:
                state["frames_this_run"] += 1
                state["seconds_this_run"] += seconds
                cprog["frames_done"] = total - len(job.missing_frames(a, b))
                cprog["seconds"] = round(float(cprog.get("seconds", 0.0)) + seconds, 2)
                state["new_files"].append(job.frame_file(frame))
                log.info("job %s frame %d done in %.1fs (%d/%d in chunk %s)", job.id, frame, seconds,
                         cprog["frames_done"], total, key)
            save_progress()
            self.queue_push(prog_path, f"renderfarm: {self.cfg.worker} progress {job.id} {key} "
                                       f"{cprog['frames_done']}/{total}")

        if not missing:
            log.info("job %s chunk %s: all %d frames already on disk", job.id, key, total)
        else:
            log.info("job %s chunk %s: %d/%d frames missing", job.id, key, len(missing), total)
            save_progress("rendering")
            self.queue_push(prog_path, f"renderfarm: {self.cfg.worker} starts {job.id} {key}", force=True)
            out_pattern = job.folder / job.output_pattern
            out_pattern.parent.mkdir(parents=True, exist_ok=True)
            ok, msg = self.runner.render(blend, job.data, job.engine, out_pattern, missing,
                                         job.folder / "logs" / f"blender_{self.cfg.worker}.log", on_frame)
            # drop a possibly partial frame if we were interrupted mid-frame
            if self.runner.current_frame is not None:
                pf = job.frame_file(self.runner.current_frame)
                if pf.exists() and not job.frame_exists(self.runner.current_frame):
                    pf.unlink(missing_ok=True)
            if not ok:
                if self.stop:
                    save_progress("interrupted")
                    self.queue_push(prog_path, f"renderfarm: {self.cfg.worker} interrupted {job.id} {key}", force=True)
                    return False
                save_progress("error")
                self.queue_push(prog_path, f"renderfarm: {self.cfg.worker} error {job.id} {key}", force=True)
                raise RuntimeError(f"chunk {key}: {msg}")
        still_missing = job.missing_frames(a, b)
        if still_missing:
            raise RuntimeError(f"chunk {key}: blender exited ok but {len(still_missing)} frames missing "
                               f"(e.g. {still_missing[:5]})")
        # upload this chunk's frames
        files = [job.frame_file(f) for f in range(a, b + 1)]
        try:
            up_ok = self.uploader(self.cfg, job.id, job.frames_dir, files)
        except Exception as exc:
            log.error("uploader %s crashed: %s", self.cfg.uploader, exc)
            up_ok = False
        cprog["uploaded"] = bool(up_ok)
        cprog["uploader"] = self.cfg.uploader
        cprog["finished_at"] = utcnow()
        save_progress("done")
        self.queue_push(prog_path, f"renderfarm: {self.cfg.worker} done {job.id} {key}", force=True)
        log.info("job %s chunk %s done (%.1f s/frame)", job.id, key, cprog.get("sec_per_frame") or 0)
        return True

    def finish_job(self, job: Job):
        self.git.pull()
        if job.done:
            return
        done = job.done_chunks()
        chunks = job.chunks()
        frames = sum(int(c.get("frames_total", 0)) for c in done.values())
        seconds = sum(float(c.get("seconds", 0.0)) for c in done.values())
        workers = sorted({c["worker"] for c in done.values()})
        per_worker = {}
        for c in done.values():
            w = per_worker.setdefault(c["worker"], {"frames": 0, "seconds": 0.0, "chunks": 0})
            w["frames"] += int(c.get("frames_total", 0))
            w["seconds"] += float(c.get("seconds", 0.0))
            w["chunks"] += 1
        for w in per_worker.values():
            w["seconds"] = round(w["seconds"], 1)
            w["sec_per_frame"] = round(w["seconds"] / w["frames"], 2) if w["frames"] else None
        info = {
            "job": job.id, "finished_at": utcnow(), "frames": frames,
            "frame_start": job.data["frame_start"], "frame_end": job.data["frame_end"],
            "chunks": len(chunks), "total_seconds": round(seconds, 1), "total_time": human_time(seconds),
            "sec_per_frame": round(seconds / frames, 2) if frames else None,
            "workers": workers, "per_worker": per_worker, "engine": job.engine,
            "uploaded": all(bool(c.get("uploaded")) for c in done.values()),
            "uploaders": sorted({str(c.get("uploader")) for c in done.values()}),
        }
        write_json(job.folder / "done.json", info)
        log.info("job %s DONE: %d frames, %s, %.2f s/frame, workers=%s", job.id, frames,
                 info["total_time"], info["sec_per_frame"] or 0, workers)
        self.git.commit_push([job.folder / "done.json"], f"renderfarm: {job.id} done ({frames} frames)")

    def mark_failed(self, job: Job, error: str):
        path = job.folder / "failed.json"
        prev = read_json(path, None) or {}
        attempts = int(prev.get("attempts", 0)) + 1
        write_json(path, {"job": job.id, "worker": self.cfg.worker, "failed_at": utcnow(),
                          "error": error[-2000:], "attempts": attempts})
        log.error("job %s marked failed: %s", job.id, error[-300:])
        self.git.commit_push([path], f"renderfarm: {job.id} failed on {self.cfg.worker}")

    # -- batched pushes of small progress files (every push_minutes)
    def queue_push(self, path: Path, message: str, force: bool = False):
        if path not in self._pending_push:
            self._pending_push.append(path)
        self._pending_msg = message
        self.flush_push(force=force)

    def flush_push(self, force: bool = False):
        if not self._pending_push:
            return
        if not force and time.monotonic() - self._last_push < self.cfg.push_minutes * 60:
            return
        paths, self._pending_push = self._pending_push, []
        self._last_push = time.monotonic()
        self.git.commit_push(paths, getattr(self, "_pending_msg", "renderfarm: progress"))

    # -- benchmark
    def bench(self) -> dict:
        blend = BENCH_DIR / "bench.blend"
        if not blend.exists():
            if not self.cfg.bench_url:
                raise SystemExit(f"{blend} missing and bench_url not set in config")
            download(self.cfg.bench_url, blend)
        out_dir = BENCH_DIR / "out"
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        job = {"engine": "BLENDER_EEVEE_NEXT", "resolution": [1920, 1080], "samples": 16, "format": "PNG",
               "output": "out/b_####", "frame_start": 1, "frame_end": 48}
        times: Dict[int, float] = {}

        def on_frame(frame, seconds):
            times[frame] = round(seconds, 2)
            log.info("bench frame %d: %.1fs", frame, seconds)

        t0 = time.monotonic()
        ok, msg = self.runner.render(blend, job, "BLENDER_EEVEE_NEXT", out_dir / "b_####",
                                     list(range(1, 49)), LOG_DIR / "bench_blender.log", on_frame)
        wall = time.monotonic() - t0
        vals = [times[k] for k in sorted(times)]
        steady = vals[1:] if len(vals) > 1 else vals
        result = {
            "worker": self.cfg.worker, "host": socket.gethostname(), "platform": sys.platform,
            "date": utcnow(), "blender": self.cfg.blender, "engine": "BLENDER_EEVEE_NEXT",
            "resolution": [1920, 1080], "samples": 16, "frames": len(vals), "ok": ok, "message": msg,
            "wall_seconds": round(wall, 1),
            "first_frame_seconds": vals[0] if vals else None,
            "sec_per_frame": round(sum(steady) / len(steady), 2) if steady else None,
            "sec_per_frame_incl_first": round(wall / len(vals), 2) if vals else None,
            "per_frame": times, "dry_run": self.dry_run,
        }
        path = BENCH_DIR / "bench_result.json"
        print(json.dumps(result, indent=2))
        print(f"\nBENCH {self.cfg.worker}: {result['sec_per_frame']} s/frame "
              f"(first frame {result['first_frame_seconds']} s, {len(vals)} frames, ok={ok})")
        self.git.pull()  # pick up other workers' results first, then merge ours in
        all_results = read_json(path, None) or {}
        if not isinstance(all_results, dict) or "worker" in all_results:
            all_results = {}
        all_results[self.cfg.worker] = result
        write_json(path, all_results)
        self.git.commit_push([path], f"renderfarm: bench {self.cfg.worker} {result['sec_per_frame']} s/frame")
        return result


def download(url: str, dest: Path, sha256: Optional[str] = None, retries: int = 3):
    """Download `url` to `dest` (via .part file). Google Drive 'uc?export=download' links work for
    files under the virus-scan threshold; for bigger files use a direct link (Dropbox ?dl=1, S3, ...)."""
    import hashlib
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            log.info("downloading %s -> %s (attempt %d)", url, dest, attempt)
            req = urllib.request.Request(url, headers={"User-Agent": "renderfarm-agent/1.0"})
            h = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=120) as resp, open(part, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                got, last_log = 0, time.monotonic()
                while True:
                    buf = resp.read(1 << 20)
                    if not buf:
                        break
                    fh.write(buf)
                    h.update(buf)
                    got += len(buf)
                    if time.monotonic() - last_log > 15:
                        log.info("  %.0f MB%s", got / 1e6, f" / {total / 1e6:.0f} MB" if total else "")
                        last_log = time.monotonic()
            if got < 1024:
                raise RuntimeError(f"download too small ({got} bytes) - not a direct link?")
            if sha256 and h.hexdigest().lower() != sha256.lower():
                raise RuntimeError("sha256 mismatch")
            os.replace(part, dest)
            log.info("downloaded %.1f MB", got / 1e6)
            return
        except Exception as exc:
            log.warning("download failed: %s", exc)
            if attempt == retries:
                raise
            time.sleep(5 * attempt)


# ----------------------------------------------------------------------------- entry
def setup_logging(verbose: bool):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(LOG_DIR / "agent.log", maxBytes=5_000_000, backupCount=5,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--once", action="store_true", help="one poll cycle then exit")
    ap.add_argument("--bench", action="store_true", help="run the benchmark and push bench_result.json")
    ap.add_argument("--dry-run", action="store_true", help="run `blender --version` instead of rendering; no git commit/push")
    ap.add_argument("--job", help="only consider this job id")
    ap.add_argument("--worker", help="override worker name from config")
    ap.add_argument("--blender", help="override blender path from config")
    ap.add_argument("--branch", help="override branch from config")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    setup_logging(args.verbose)
    overrides = {k: v for k, v in (("worker", args.worker), ("blender", args.blender), ("branch", args.branch)) if v}
    cfg = Config(Path(args.config), overrides)
    agent = Agent(cfg, dry_run=args.dry_run, only_job=args.job)
    signal.signal(signal.SIGINT, agent.request_stop)
    try:
        signal.signal(signal.SIGTERM, agent.request_stop)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, agent.request_stop)  # Windows Ctrl-Break
    except Exception:
        pass
    try:
        if args.bench:
            res = agent.bench()
            return 0 if res.get("ok") else 1
        agent.loop(once=args.once)
        return 0
    except KeyboardInterrupt:
        agent.request_stop()
        agent.flush_push(force=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
