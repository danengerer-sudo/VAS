#!/usr/bin/env python3
"""
status.py -- print the state of every render job from the (pulled) repository.

    python status.py            # read local checkout
    python status.py --pull     # git pull first
    python status.py --json     # machine-readable
    python status.py --bench    # also show bench_result.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from agent import Job, JOBS_DIR, BENCH_DIR, chunk_key, human_time, parse_utc, read_json  # noqa: E402


def job_summary(job: Job, stale_hours: float) -> dict:
    chunks = job.chunks()
    done = job.done_chunks()
    progress = job.all_progress()
    claims = job.all_claims()
    frames_total = int(job.data["frame_end"]) - int(job.data["frame_start"]) + 1
    frames_done = 0
    rendering = []
    spf = []
    last_update = 0.0
    for worker, prog in progress.items():
        last_update = max(last_update, parse_utc(prog.get("updated", "")))
        for key, c in (prog.get("chunks") or {}).items():
            frames_done += int(c.get("frames_done", 0))
            if c.get("sec_per_frame"):
                spf.append(float(c["sec_per_frame"]))
            if c.get("status") == "rendering":
                rendering.append(f"{worker}:{key}")
    claimed = {k for cl in claims.values() for k in (cl.get("chunks") or {})}
    owners = {chunk_key(a, b): job.chunk_owner(chunk_key(a, b), stale_hours) for a, b in chunks}
    free = [k for k, o in owners.items() if o is None and k not in done]
    if job.done:
        state = "DONE"
    elif job.failed:
        state = "FAILED"
    elif rendering:
        state = "RENDERING"
    elif claimed:
        state = "CLAIMED"
    else:
        state = "QUEUED"
    avg = sum(spf) / len(spf) if spf else None
    workers_active = len({r.split(":")[0] for r in rendering}) or 1
    eta = (frames_total - frames_done) * avg / workers_active if avg else None
    out = {
        "job": job.id, "state": state, "priority": job.priority, "engine": job.engine,
        "frames": f"{frames_done}/{frames_total}", "frames_done": frames_done, "frames_total": frames_total,
        "chunks": f"{len(done)}/{len(chunks)}", "chunks_free": len(free),
        "rendering": rendering, "workers": sorted(set(claims) | set(progress)),
        "sec_per_frame": round(avg, 1) if avg else None,
        "eta": human_time(eta) if eta is not None else None,
        "last_update": _dt.datetime.fromtimestamp(last_update, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if last_update else None,
        "age_min": round((time.time() - last_update) / 60) if last_update else None,
    }
    if job.done:
        d = read_json(job.folder / "done.json", {}) or {}
        out["done"] = {k: d.get(k) for k in ("finished_at", "total_time", "sec_per_frame", "workers", "uploaded")}
    if job.failed:
        f = read_json(job.folder / "failed.json", {}) or {}
        out["failed"] = {k: f.get(k) for k in ("worker", "failed_at", "error", "attempts")}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--stale-hours", type=float, default=12.0)
    args = ap.parse_args(argv)

    if args.pull:
        cp = subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=str(HERE), capture_output=True, text=True)
        if cp.returncode != 0:
            print("git pull failed:", cp.stderr.strip(), file=sys.stderr)

    jobs = [Job(p) for p in sorted(JOBS_DIR.iterdir()) if p.is_dir() and (p / "job.json").exists()] if JOBS_DIR.is_dir() else []
    rows = []
    for j in jobs:
        if not j.ok:
            rows.append({"job": j.id, "state": "BAD job.json"})
            continue
        rows.append(job_summary(j, args.stale_hours))
    rows.sort(key=lambda r: ({"RENDERING": 0, "CLAIMED": 1, "QUEUED": 2, "FAILED": 3, "DONE": 4}.get(r["state"], 5), r.get("priority", 9), r["job"]))

    bench = read_json(BENCH_DIR / "bench_result.json", None) if args.bench else None
    if args.json:
        print(json.dumps({"jobs": rows, "bench": bench}, indent=2))
        return 0

    if not rows:
        print("no jobs in", JOBS_DIR)
    else:
        hdr = f"{'JOB':<28} {'STATE':<10} {'PRI':>3} {'FRAMES':>11} {'CHUNKS':>7} {'S/FRAME':>7} {'ETA':>9}  {'WORKERS / ACTIVE':<30} LAST UPDATE"
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            if r["state"] == "BAD job.json":
                print(f"{r['job']:<28} {r['state']}")
                continue
            active = ", ".join(r["rendering"]) or ", ".join(r["workers"]) or "-"
            upd = f"{r['last_update']} ({r['age_min']} min ago)" if r["last_update"] else "-"
            print(f"{r['job']:<28} {r['state']:<10} {r['priority']:>3} {r['frames']:>11} {r['chunks']:>7} "
                  f"{(r['sec_per_frame'] if r['sec_per_frame'] is not None else '-')!s:>7} {(r['eta'] or '-'):>9}  {active:<30} {upd}")
            if r.get("failed"):
                print(f"    failed on {r['failed']['worker']} at {r['failed']['failed_at']} (attempt {r['failed']['attempts']}): {str(r['failed']['error'])[:160]}")
            if r.get("done"):
                d = r["done"]
                print(f"    done {d['finished_at']} total {d['total_time']} @ {d['sec_per_frame']} s/frame by {', '.join(d['workers'] or [])}, uploaded={d['uploaded']}")
    if args.bench:
        print("\nBENCH (EEVEE 1080p 16 spp, 48 frames):")
        if not bench:
            print("  no bench_result.json yet")
        else:
            for w, b in bench.items():
                print(f"  {w:<12} {b.get('sec_per_frame')} s/frame  (first frame {b.get('first_frame_seconds')} s, "
                      f"{b.get('date')}, ok={b.get('ok')}{', DRY-RUN' if b.get('dry_run') else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
