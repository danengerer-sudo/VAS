"""Pull rendered frames straight from a publicly shared Drive folder (renderfarm/<job>/frames).

python3 pull_drive_frames.py <renderfarm_folder_id> <episode_dir> [--prefix gunrights_] [--jobs 16]
Uses Drive's anonymous embedded folder view for listings and the usercontent download URL for files;
only works after the folder is shared as 'anyone with the link'. Skips frames already on disk.
"""
import os
import re
import sys
import json
import html
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = sys.argv[1]
EP = os.path.abspath(sys.argv[2])
PREFIX = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else "gunrights_"
JOBS = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 16
OUT = os.path.join(EP, "frames_final")


def listing(folder_id):
    """[(name, id)] of a public folder via the embedded view (no auth)."""
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"
    page = subprocess.run(["curl", "-sL", "-m", "120", url], capture_output=True, text=True).stdout
    out = []
    # entries look like: <a href="https://drive.google.com/file/d/<id>/view?usp=drive_web" ...><div class="flip-entry-title">name</div>
    for m in re.finditer(r'(?:file/d/|folders/)([\w-]+)[^>]*>.*?class="flip-entry-title">([^<]+)<', page, re.S):
        out.append((html.unescape(m.group(2)).strip(), m.group(1)))
    return out


def fetch(name_id_dest):
    name, fid, dest = name_id_dest
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return name, "cached"
    url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
    tmp = dest + ".part"
    for attempt in range(4):
        cp = subprocess.run(["curl", "-sL", "-m", "300", "--retry", "3", "-o", tmp, url])
        if cp.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1024 and open(tmp, "rb").read(8)[:4] == b"\x89PNG":
            os.replace(tmp, dest)
            return name, "ok"
    return name, "FAILED"


def main():
    sl = json.load(open(os.path.join(EP, "shotlist.json")))
    top = dict(listing(ROOT))
    report = {}
    for s in sl["shots"]:
        job = PREFIX + s["id"]
        if job not in top:
            report[s["id"]] = "job folder not found on Drive"
            continue
        sub = dict(listing(top[job]))
        if "frames" not in sub:
            report[s["id"]] = "frames folder not found"
            continue
        files = [(n, i) for n, i in listing(sub["frames"]) if re.fullmatch(r"f_\d{4}\.png", n)]
        want = s["frame_end"] - s["frame_start"] + 1
        d = os.path.join(OUT, s["id"])
        os.makedirs(d, exist_ok=True)
        tasks = [(n, i, os.path.join(d, n)) for n, i in files]
        with ThreadPoolExecutor(JOBS) as ex:
            res = list(ex.map(fetch, tasks))
        failed = [n for n, r in res if r == "FAILED"]
        have = len([f for f in os.listdir(d) if f.endswith(".png")])
        report[s["id"]] = f"listed {len(files)}/{want}, on disk {have}, failed {len(failed)}"
        print(s["id"], report[s["id"]], flush=True)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
