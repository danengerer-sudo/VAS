"""v2 episode driver: beat table (one beat per narration paragraph) -> one blend per set, a storyboard
still per beat, and shotlist.json for assembly / render submission.

python3 ep2.py <episode_dir> [--only crowd,street] [--pct 40] [--no-stills]
"""
import os
import sys
import json
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from episode import frame_plan, FPS, BLENDER

# set id -> (builder in ep2_scenes.py, sun (elevation, rotation))
SETS = {
    "crowd": ("crowd", (24, 140)), "dome": ("dome", (20, 140)), "dome_dusk": ("dome", (6, 205)),
    "nap": ("nap", (26, 150)), "street": ("street", (26, 150)), "defense": ("defense", (26, 150)),
    "basement": ("basement", (20, 140)), "hall": ("hall", (20, 140)), "jail": ("jail", (20, 140)),
    "lawn": ("lawn", (26, 150)), "table": ("table", (20, 140)), "kid": ("kid", (20, 140)), "own": ("own", (18, 160)),
}


def B(para, set_id, cam, look, lens=40, fstop=None, focus=None, show=(), hide=(), words=None):
    """cam/look: ((start),(end)); show: names visible only on their listed beats; hide: names hidden on
    this beat; words: {name: "word"} -> name appears at that word of this paragraph (and stays)."""
    return dict(para=para, set=set_id, cam=cam, look=look, lens=lens, fstop=fstop, focus=focus,
                show=list(show), hide=list(hide), words=words or {})


BEATS = [
    # --- the question, the usual answers
    B(0, "crowd", ((-12, -9, 1.0), (-9, -6, 1.2)), ((8, 0, 1.6), (10, 0, 1.8)), 28),
    B(1, "crowd", ((10.5, -6, 1.5), (10.5, 5, 1.5)), ((4, -6, 1.55), (4, 5, 1.55)), 50, 2.8, (4, 0, 1.55)),
    B(2, "dome", ((-15, -64, 1.0), (-13, -60, 1.2)), ((-10, -50, 3.5), (-10, -44, 6)), 30),
    # --- the competing view (nap lot: owner at (-1.2, 2.4), label at (-0.4, 5.6, 2.2), stranger at (0.4, -0.6))
    B(3, "nap", ((6, -6, 1.2), (3.5, -3, 1.3)), ((-1, 3, 1.2), (-1, 3, 1.2)), 35, 4.0, "Owner"),
    B(4, "nap", ((0.5, 0.0, 1.9), (0.0, 1.8, 2.1)), ((-0.4, 5.6, 2.2), (-0.4, 5.6, 2.2)), 50, 2.8, "naplabel"),
    B(5, "nap", ((-1.0, -0.4, 1.55), (-1.1, 0.4, 1.5)), ((-1.2, 2.4, 1.45), (-1.2, 2.4, 1.45)), 65, 2.0, (-1.2, 2.4, 1.45)),
    B(6, "nap", ((3.2, 3.0, 1.6), (2.2, 3.8, 1.8)), ((-0.4, 5.6, 2.2), (-0.4, 5.6, 2.2)), 45, 2.8, "naplabel"),
    B(7, "nap", ((-10, -10, 6), (8, -11, 7)), ((0, 4, 1), (0, 4, 1)), 32),
    # --- four wrongs
    B(8, "street", ((1.6, -0.5, 1.3), (1.3, 0.3, 1.3)), ((0.3, 4.5, 1.0), (0.3, 4.0, 1.0)), 40, 2.8, "Thief"),
    B(9, "street", ((0.5, -7.0, 1.3), (1.0, -6.4, 1.25)), ((4.3, -3.2, 1.1), (4.3, -3.2, 1.1)), 40, 2.8, "CarThief"),
    B(10, "street", ((-6.0, 0.6, 1.5), (-5.6, 1.2, 1.5)), ((-4.2, 5.0, 1.1), (-4.2, 5.0, 1.1)), 45, 2.8, "Squatter"),
    B(11, "street", ((-8.4, -4.6, 1.3), (-8.4, -4.0, 1.3)), ((-8.4, -1.2, 1.4), (-8.4, -1.2, 1.4)), 50, 2.5, (-8.3, -1.2, 1.4)),
    B(12, "street", ((-2, -19, 3.5), (0, -17, 3.2)), ((-2, 3, 1.2), (-2, 3, 1.2)), 28),
    # --- defence is fine
    B(13, "defense", ((-0.8, 6.7, 1.75), (-0.6, 6.5, 1.7)), ((0.3, 2.6, 1.3), (0.3, 2.6, 1.3)), 45, 2.8, "Intruder", hide=["Runner"]),
    B(14, "defense", ((1.6, 1.2, 0.7), (1.2, 2.0, 0.8)), ((0, 6.6, 1.3), (0, 6.6, 1.3)), 40, 2.8, "Home", hide=["Runner"]),
    B(15, "defense", ((7, -7, 3.0), (6, -6, 2.8)), ((-2, 2, 1.0), (-2, 2, 1.0)), 30, hide=["Intruder"]),
    # --- the inverse: the basement
    B(16, "basement", ((-1.0, 0.4, 1.25), (-1.5, 0.8, 1.15)), ((-3.4, 2.0, 0.8), (-3.4, 2.0, 0.8)), 50, 2.2, "rifle", hide=["Taker"]),
    B(17, "basement", ((0.5, -1.5, 1.2), (1.5, -2.2, 1.3)), ((-3.0, 1.8, 1.0), (-3.0, 1.8, 1.0)), 35, 4.0, "Taker", show=["Taker"]),
    B(18, "basement", ((3.5, 3.5, 1.6), (2.8, 2.8, 1.5)), ((-2.0, -1.5, 0.8), (-2.0, -1.5, 0.8)), 28, hide=["Taker"]),
    # --- the government says no
    B(19, "hall", ((0.3, 2.0, 1.5), (0.2, 2.5, 1.5)), ((0, 3.3, 1.5), (0, 3.3, 1.5)), 50, 2.8, (0, 3.3, 1.5), hide=["E1", "E2", "E3"]),
    B(20, "hall", ((-0.9, -2.4, 1.1), (-0.8, -1.8, 1.1)), ((0.1, 2.8, 1.3), (0.1, 2.8, 1.3)), 30, show=["E1", "E2", "E3"]),
    B(21, "jail", ((-2.4, -1.6, 0.8), (-2.0, -1.2, 0.9)), ((0.2, -0.3, 1.2), (0.2, -0.3, 1.2)), 45, 2.5, "Inmate"),
    B(22, "jail", ((4.6, -7.4, 1.05), (4.8, -7.2, 1.05)), ((6.4, -5.9, 0.85), (6.4, -5.9, 0.85)), 50, 2.0, ["gavel", "Cop1"]),
    # --- NAP check
    B(23, "nap", ((2.5, -1.5, 1.4), (1.8, -0.5, 1.5)), ((-0.4, 5.6, 2.1), (-0.4, 5.6, 2.1)), 40, 2.8, "naplabel"),
    B(24, "street", ((1.5, -5.0, 1.3), (2.0, -5.3, 1.3)), ((14, -7, 1.0), (22, -7, 1.0)), 40, show=["car_gone"], hide=["car", "CarThief"]),
    B(25, "street", ((-3, -2, 0.9), (-2.5, -1.2, 1.0)), ((0, 10, 5), (0, 10, 5)), 28, show=["fire1", "fire2", "smoke"]),
    B(26, "street", ((-8.4, 2.2, 1.3), (-8.4, 1.6, 1.3)), ((-8.4, -1.2, 1.4), (-8.4, -1.2, 1.4)), 55, 2.5, (-8.5, -1.2, 1.4)),
    B(27, "basement", ((-1.6, -0.4, 1.0), (-1.9, -0.1, 1.0)), ((-3.2, 1.9, 1.0), (-3.2, 1.9, 1.0)), 40, 2.5, "Taker", show=["Taker"]),
    B(28, "lawn", ((-3.5, -3.0, 0.6), (-2.5, -2.0, 0.7)), ((0.2, 1.0, 1.2), (0.2, 3.0, 1.2)), 35, 3.0, "Cop", hide=["Down", "Cop2", "blood"]),
    B(29, "jail", ((0.6, 0.4, 1.4), (0.4, 0.3, 1.4)), ((-3.6, 0.6, 1.3), (-3.6, 0.6, 1.3)), 35, 2.8, "Guard"),
    B(30, "lawn", ((-5.2, 2.0, 0.6), (-4.8, 2.4, 0.6)), ((-2.0, 4.4, 0.8), (-2.0, 4.4, 0.8)), 40, 2.8, "Cop2", hide=["Cop"]),
    # --- all rights come from here
    B(31, "table", ((0.0, -3.2, 1.0), (0.0, -2.6, 0.98)), ((0, 1.0, 0.85), (0, 1.0, 0.85)), 50, 2.8, (0, -0.35, 0.85),
      hide=["i_tv", "i_car", "i_this", "i_that", "i_other", "i_rifle", "Reacher"]),
    B(32, "table", ((0.0, -2.6, 0.98), (0.3, -2.2, 1.1)), ((0, 0.3, 0.85), (0, 0.3, 0.85)), 45, 2.8, "i_car", hide=["Reacher"],
      words={"i_tv": "TV,", "i_car": "car,", "i_this": "this,", "i_that": "that,", "i_other": "other", "i_rifle": "thing."}),
    B(33, "table", ((-1.2, -2.6, 1.2), (-0.9, -2.3, 1.15)), ((0.1, -1.2, 1.0), (0.1, -1.2, 1.0)), 55, 2.5, "i_tv", show=["Reacher"]),
    B(34, "street", ((-0.8, -19.5, 1.0), (-0.3, -18.8, 1.0)), ((2.3, -14.5, 0.9), (2.3, -14.5, 0.9)), 35, 3.0, "Victim", show=["flash", "blood"]),
    B(35, "kid", ((-3.0, -1.2, 1.1), (-2.6, -0.8, 1.15)), ((0.3, 0.1, 1.2), (0.8, 0.1, 1.4)), 40, 2.8, ["Pupil", "rule"]),
    B(36, "crowd", ((16.5, 1.2, 2.9), (15.5, 0.8, 2.7)), ((2, 0, 1.3), (2, 0, 1.3)), 35),
    B(37, "dome_dusk", ((-46, -78, 1.3), (-44, -76, 1.4)), ((-30, -50, 6), (0, 0, 12)), 35, 4.0, "Lone"),
    B(38, "own", ((0.5, -2, 1.0), (2, -11, 5)), ((0, 3.5, 1.2), (0, 4, 1.5)), 32),
    B(39, "own", ((0.3, -0.2, 1.5), (0.2, 0.0, 1.5)), ((0, 2.8, 1.45), (0, 2.8, 1.45)), 60, 2.2, (0, 2.8, 1.45)),
]


def main():
    ep = os.path.abspath(sys.argv[1])
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    pct = int(sys.argv[sys.argv.index("--pct") + 1]) if "--pct" in sys.argv else 40
    if "--no-stills" in sys.argv:
        pct = 0
    timing = json.load(open(os.path.join(ep, "timing.json")))
    shots = [dict(id=f"{b['para']:02d}", scene=b["set"], paras=[b["para"]]) for b in BEATS]
    plan = frame_plan(timing, shots)
    t_off = plan[0]["t0"]

    def frame_at(t):
        return 1 + round((t - t_off) * FPS)

    out = os.path.join(ep, "shots")
    os.makedirs(out, exist_ok=True)
    json.dump({"fps": FPS, "audio_offset": t_off, "shots": plan}, open(os.path.join(ep, "shotlist.json"), "w"), indent=1)

    # group beats per set, resolve visibility windows
    by_set = {}
    for b, p in zip(BEATS, plan):
        by_set.setdefault(b["set"], []).append((b, p))
    specs = []
    for set_id, items in by_set.items():
        builder, sun = SETS[set_id]
        first, last = items[0][1]["frame_start"], items[-1][1]["frame_end"]
        show_rules, hide_rules, word_rules = {}, {}, {}
        for b, p in items:
            for n in b["show"]:
                show_rules.setdefault(n, []).append([p["frame_start"], p["frame_end"]])
            for n in b["hide"]:
                hide_rules.setdefault(n, []).append([p["frame_start"], p["frame_end"]])
            para = timing["paragraphs"][b["para"]]
            for n, word in b["words"].items():
                hits = [w for w in para["words"] if w["w"] == word]
                if not hits:
                    print("WARN word not found", word, "in beat", b["para"])
                    continue
                word_rules.setdefault(n, []).append([frame_at(hits[0]["start"]), last])
        windows = {}
        for n in set(show_rules) | set(hide_rules) | set(word_rules):
            if n in show_rules or n in word_rules:
                windows[n] = show_rules.get(n, []) + word_rules.get(n, [])
            else:  # hide-only: visible everywhere except the hidden beats
                vis, cur = [], first
                for a, z in sorted(hide_rules[n]):
                    if a > cur:
                        vis.append([cur, a - 1])
                    cur = z + 1
                if cur <= last:
                    vis.append([cur, last])
                windows[n] = vis
        beats = []
        for b, p in items:
            beats.append(dict(id=b["para"], frame_start=p["frame_start"], frame_end=p["frame_end"], cam=b["cam"],
                              look=b["look"], lens=b["lens"], fstop=b["fstop"], focus=b["focus"]))
        beats[0]["show"] = windows
        specs.append(dict(id=set_id, set=builder, sun=sun, beats=beats))

    for spec in specs:
        if only and spec["id"] not in only:
            continue
        path = os.path.join(out, f"{spec['id']}.json")
        json.dump(spec, open(path, "w"), indent=1)
        cmd = [BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "ep2_scenes.py"), "--", path, out, str(pct)]
        print("BUILD", spec["id"], [b["id"] for b in spec["beats"]], flush=True)
        res = subprocess.run(cmd, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if line.startswith(("SAVED", "STILL", "WARN")) or "Error" in line or "Traceback" in line:
                print("  ", line, flush=True)
        if res.returncode:
            print(res.stderr[-3000:])


if __name__ == "__main__":
    main()
