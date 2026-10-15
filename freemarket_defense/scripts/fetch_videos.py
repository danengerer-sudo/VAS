"""Fetch the per-shot videos the render agent published (done.json → video_url) for an episode.

python3 fetch_videos.py <episode_dir> [--prefix gunrights_] [--out <episode_dir>/video]
Writes <out>/<SHOT>.mp4 (job id with the prefix stripped), verifies sha256, skips files already fetched.
Prints which shots are still missing so it can be re-run until all are in.
"""
import os
import sys
import json
import glob
import hashlib
import re
import subprocess
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS = os.path.join(HERE, "..", "renderfarm", "jobs")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def drive_download_url(url):
    """rclone link gives https://drive.google.com/open?id=X (or /file/d/X/...): turn it into a direct
    download that also skips the 'large file, virus scan' interstitial."""
    m = re.search(r"[?&]id=([\w-]+)", url) or re.search(r"/file/d/([\w-]+)", url)
    if not m:
        return url
    return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main():
    ep = os.path.abspath(sys.argv[1])
    prefix = arg("--prefix", "gunrights_")
    out = arg("--out", os.path.join(ep, "video"))
    os.makedirs(out, exist_ok=True)
    sl = json.load(open(os.path.join(ep, "shotlist.json")))
    missing = []
    for s in sl["shots"]:
        job = prefix + s["id"]
        done = os.path.join(JOBS, job, "done.json")
        dest = os.path.join(out, s["id"] + ".mp4")
        info = json.load(open(done)) if os.path.exists(done) else {}
        url = info.get("video_url")
        if not url:
            missing.append((s["id"], "rendering" if not info else "done, video not published yet"))
            continue
        if os.path.exists(dest) and sha256(dest) == info.get("video_sha256"):
            print(s["id"], "ok (cached)")
            continue
        if url.startswith("outbox:"):
            missing.append((s["id"], "video sits in the mini PC outbox (no rclone remote)"))
            continue
        dl = drive_download_url(url)
        tmp = dest + ".part"
        print(s["id"], "downloading", round(info.get("video_size", 0) / 1e6, 1), "MB")
        cp = subprocess.run(["curl", "-sSL", "--retry", "5", "--retry-delay", "5", "-o", tmp, dl])
        if cp.returncode or not os.path.exists(tmp) or sha256(tmp) != info.get("video_sha256"):
            size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            head = open(tmp, "rb").read(200) if size else b""
            missing.append((s["id"], f"download failed/mismatch ({size} bytes, starts {head[:60]!r})"))
            continue
        os.replace(tmp, dest)
        print(s["id"], "ok", round(os.path.getsize(dest) / 1e6, 1), "MB")
    if missing:
        print("MISSING:")
        for sid, why in missing:
            print("  ", sid, "-", why)
        sys.exit(1)
    print("ALL_VIDEOS_FETCHED")


if __name__ == "__main__":
    main()
