#!/usr/bin/env python3
"""
submit.py -- create a render job folder (cloud / Linux side), commit and push it.

    python submit.py render/scene.blend --id ep03_s2 --start 97 --end 216 \
        --engine BLENDER_EEVEE_NEXT --res 1920 1080 --samples 16 --chunk 240 --priority 1

Options for getting the (100-300 MB) .blend to the Windows box:
    (default)        copy it into jobs/<id>/ and commit it (GitHub hard limit 100 MB / file!)
    --lfs            copy + `git lfs track` it (needs git-lfs on both sides; GitHub LFS quota applies)
    --blend-url URL  do NOT commit the blend; the agent downloads URL (direct link) to jobs/<id>/_dl/
    --upload TARGET  upload the blend with a transport and record the resulting URL (stub: "copy:<dir>"
                     copies to a directory you sync yourself; add your own in upload_blend())

Pack external textures/HDRIs into the .blend first (File > External Data > Pack Resources, or
`blender -b scene.blend --python-expr "import bpy; bpy.ops.file.pack_all(); bpy.ops.wm.save_mainfile()"`),
otherwise the Windows box renders pink.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOBS_DIR = HERE / "jobs"
GITHUB_FILE_LIMIT = 100 * 1024 * 1024


def repo_root() -> Path:
    p = HERE
    for _ in range(6):
        if (p / ".git").exists():
            return p
        p = p.parent
    return HERE.parents[1]


def git(*args, check=True):
    cp = subprocess.run(["git", *args], cwd=str(repo_root()), capture_output=True, text=True)
    if check and cp.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{cp.stderr}")
    return cp


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for buf in iter(lambda: fh.read(1 << 20), b""):
            h.update(buf)
    return h.hexdigest()


# ----------------------------------------------------------------------------- blend upload transports
def upload_blend(blend: Path, target: str, job_id: str) -> str:
    """Upload `blend` somewhere the Windows agent can download it from; return a direct URL.
    STUB: only 'copy:<dir>' (copy into a folder you sync/share yourself) is implemented; it returns
    a placeholder URL you must replace. Add 'rclone:<remote:path>' / S3 / etc. here as needed."""
    kind, _, arg = target.partition(":")
    if kind == "copy":
        dest = Path(arg).expanduser() / f"{job_id}_{blend.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(blend, dest)
        print(f"copied blend to {dest}; now share it and put the direct URL into job.json['blend_url']")
        return f"REPLACE_ME_WITH_DIRECT_LINK_TO/{dest.name}"
    if kind == "rclone":
        # rclone copyto <blend> <remote:path/job_id_name>; then `rclone link` for a public link
        dest = f"{arg.rstrip('/')}/{job_id}_{blend.name}"
        subprocess.run(["rclone", "copyto", str(blend), dest], check=True)
        cp = subprocess.run(["rclone", "link", dest], capture_output=True, text=True, check=True)
        url = cp.stdout.strip()
        m = re.search(r"/d/([^/]+)/", url)  # Google Drive share link -> direct download form
        if m:
            url = f"https://drive.google.com/uc?export=download&id={m.group(1)}"
        return url
    raise SystemExit(f"unknown upload target {target!r} (implement it in upload_blend())")


# ----------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blend", nargs="?", help="path to the packed .blend (omit with --blend-url)")
    ap.add_argument("--id", help="job id (default: <blendname>_<YYYYmmdd_HHMM>)")
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--engine", default="BLENDER_EEVEE_NEXT", choices=["BLENDER_EEVEE_NEXT", "CYCLES"])
    ap.add_argument("--res", type=int, nargs=2, default=[1920, 1080], metavar=("W", "H"))
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--output", default="frames/f_####")
    ap.add_argument("--format", default="PNG")
    ap.add_argument("--chunk", type=int, default=240)
    ap.add_argument("--priority", type=int, default=1, help="1 = highest")
    ap.add_argument("--blend-url", help="direct download URL instead of committing the blend")
    ap.add_argument("--blend-name", help="file name the agent should use for a downloaded blend")
    ap.add_argument("--upload", help="upload transport for the blend, e.g. copy:/path or rclone:gdrive:renderfarm/blends")
    ap.add_argument("--lfs", action="store_true", help="track the blend with git lfs")
    ap.add_argument("--note", default="", help="free text stored in job.json")
    ap.add_argument("--no-push", action="store_true", help="create + commit, do not push")
    ap.add_argument("--no-commit", action="store_true", help="only create the folder")
    ap.add_argument("--force", action="store_true", help="allow > 100 MB blend without lfs/url")
    args = ap.parse_args(argv)

    if not args.blend and not args.blend_url:
        ap.error("give a .blend path or --blend-url")
    if args.end < args.start:
        ap.error("--end must be >= --start")

    blend = Path(args.blend).resolve() if args.blend else None
    if blend and not blend.exists():
        ap.error(f"blend not found: {blend}")
    stem = blend.stem if blend else "job"
    job_id = args.id or f"{stem}_{_dt.datetime.now().strftime('%Y%m%d_%H%M')}"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", job_id):
        ap.error("job id may only contain letters, digits, _ . -")
    job_dir = JOBS_DIR / job_id
    if job_dir.exists() and (job_dir / "job.json").exists():
        ap.error(f"job {job_id} already exists")
    job_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "frame_start": args.start, "frame_end": args.end, "engine": args.engine,
        "resolution": args.res, "samples": args.samples, "output": args.output,
        "format": args.format.upper(), "chunk": args.chunk, "priority": args.priority,
        "submitted_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": args.note,
    }
    to_add = [job_dir / "job.json"]

    if blend:
        job["blend_sha256"] = sha256(blend)
        job["blend_size"] = blend.stat().st_size
    if args.upload and blend:
        args.blend_url = upload_blend(blend, args.upload, job_id)
    if args.blend_url:
        job["blend"] = args.blend_name or (blend.name if blend else "")
        job["blend_url"] = args.blend_url
        print(f"blend will be downloaded by the agent from {args.blend_url}")
    else:
        assert blend is not None
        dest = job_dir / blend.name
        shutil.copy2(blend, dest)
        job["blend"] = blend.name
        size = dest.stat().st_size
        if args.lfs:
            rel = str(dest.relative_to(repo_root())).replace("\\", "/")
            git("lfs", "track", rel)
            to_add.append(repo_root() / ".gitattributes")
            print(f"tracking {rel} with git lfs")
        elif size > GITHUB_FILE_LIMIT and not args.force:
            shutil.rmtree(job_dir)
            raise SystemExit(f"{blend.name} is {size / 1e6:.0f} MB > GitHub's 100 MB limit. "
                             f"Use --lfs, --blend-url, or --upload.")
        elif size > 50 * 1024 * 1024:
            print(f"warning: {size / 1e6:.0f} MB blend committed to git (GitHub warns above 50 MB)")
        to_add.append(dest)

    with open(job_dir / "job.json", "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"created {job_dir}")
    print(json.dumps(job, indent=2))

    if args.no_commit:
        return 0
    rels = [str(p.relative_to(repo_root())) for p in to_add]
    git("add", "--", *rels)
    frames = args.end - args.start + 1
    git("commit", "-q", "-m", f"renderfarm: submit job {job_id} ({frames} frames, {args.engine})", "--", *rels)
    if args.no_push:
        print("committed (not pushed)")
        return 0
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    cp = git("push", "origin", f"HEAD:{branch}", check=False)
    if cp.returncode != 0:
        print(cp.stderr)
        print("push failed; retrying after pull --rebase")
        git("pull", "--rebase", "origin", branch)
        git("push", "origin", f"HEAD:{branch}")
    print(f"pushed job {job_id} to origin/{branch}; agents will pick it up on their next poll")
    return 0


if __name__ == "__main__":
    sys.exit(main())
