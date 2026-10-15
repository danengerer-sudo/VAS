"""Episode shot builder: turns timing.json + a shot table into one Blender scene per shot
(white diorama style, EEVEE, slow camera moves), plus a preview frame and shotlist.json.

python3 episode.py <episode_dir> [--only S01,S03] [--preview-only] [--res 50]
Each shot's duration comes from the narration timing of the paragraphs it covers.
"""
import os
import sys
import json
import math
import random
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = "/opt/blender_dl/blender-4.2.23-linux-x64/blender"
FPS = 24
LEAD, TAIL = 0.35, 0.45  # seconds of picture before the first word / after the last


# ----------------------------------------------------------------------------- shot table
# paras: indices into timing.json["paragraphs"]; move: camera (start, end, lens) in metres;
# scene: name of a builder function in episode_scenes.py
SHOTS = [
    dict(id="S01", scene="hook", paras=[0, 1],
         cam=((-150, -95, 28), (-105, -62, 18)), look=((0, 5, 12), (-5, 2, 10)), lens=40),
    dict(id="S02", scene="paper", paras=[2, 3],
         cam=((0.95, -0.55, 1.12), (0.95, -0.75, 1.0)), look=((0.15, 0.0, 0.76), (0.45, -0.2, 0.76)), lens=50),
    dict(id="S03", scene="tv_shop", paras=[4, 5, 6],
         cam=((11, -16, 2.3), (7.0, -12.5, 1.8)), look=((1.2, -6.0, 1.4), (1.5, -7.2, 1.1)), lens=35),
    dict(id="S04", scene="door", paras=[7, 8, 9],
         cam=((9, -16, 2.0), (6, -10.5, 1.6)), look=((4, 3.5, 1.6), (4, 2.5, 1.4)), lens=32),
    dict(id="S05", scene="table", paras=[10, 11, 12],
         cam=((2.0, -1.35, 1.75), (1.9, 1.15, 1.7)), look=((0.0, 0.05, 0.78), (0.0, 0.05, 0.78)), lens=45),
    dict(id="S06", scene="town", paras=[13, 14, 15, 16, 17, 18],
         cam=((-45, -4, 2.5), (-150, -120, 75)), look=((20, 0, 3), (0, 15, 0)), lens=30),
    dict(id="TAG", scene="donkey", paras=[19],
         cam=((4.6, -4.2, 1.35), (3.1, -2.9, 1.15)), look=((0.2, 0, 0.95), (0.3, 0.1, 1.0)), lens=50),
]


def frame_plan(timing, shots):
    paras = timing["paragraphs"]
    plan, f = [], 0
    for s in shots:
        t0 = paras[s["paras"][0]]["start"] - LEAD
        t1 = paras[s["paras"][-1]]["end"] + TAIL
        if plan:  # butt shots together; the gap between beats is split at the midpoint
            prev = plan[-1]
            mid = (prev["t1"] + t0) / 2
            prev["t1"], t0 = mid, mid
        plan.append(dict(s, t0=max(0.0, t0), t1=t1))
    for p in plan:
        p["frames"] = max(FPS, round((p["t1"] - p["t0"]) * FPS))
        p["frame_start"] = f + 1
        f += p["frames"]
        p["frame_end"] = f
    return plan


def main():
    ep = os.path.abspath(sys.argv[1])
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].split(",")
    res = int(sys.argv[sys.argv.index("--res") + 1]) if "--res" in sys.argv else 50
    timing = json.load(open(os.path.join(ep, "timing.json")))
    plan = frame_plan(timing, SHOTS)
    os.makedirs(os.path.join(ep, "shots"), exist_ok=True)
    json.dump({"fps": FPS, "audio_offset": plan[0]["t0"], "shots": plan},
              open(os.path.join(ep, "shotlist.json"), "w"), indent=1)
    for p in plan:
        if only and p["id"] not in only:
            continue
        spec = os.path.join(ep, "shots", f"{p['id']}.json")
        json.dump(p, open(spec, "w"))
        cmd = [BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "episode_scenes.py"), "--",
               spec, os.path.join(ep, "shots"), str(res)]
        print("BUILD", p["id"], p["scene"], p["frames"], "frames")
        out = subprocess.run(cmd, capture_output=True, text=True)
        for line in out.stdout.splitlines():
            if line.startswith(("SAVED", "PREVIEW", "WARN")) or "Error" in line or "Traceback" in line:
                print("  ", line)
        if out.returncode:
            print(out.stderr[-2000:])


if __name__ == "__main__":
    main()
