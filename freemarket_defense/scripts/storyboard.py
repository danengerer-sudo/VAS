"""Storyboard sheet: one panel per beat (still + beat number + time + the line it covers).

python3 storyboard.py <episode_dir> [--cols 4] [--out storyboard.jpg]
Reads shots/storyboard/beat_NN.png and timing.json; writes one or more sheets of 20 panels.
"""
import os
import sys
import json
import glob
import textwrap
from PIL import Image, ImageDraw, ImageFont

F_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
F_REG = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    ep = os.path.abspath(sys.argv[1])
    cols = int(arg("--cols", 4))
    out = arg("--out", os.path.join(ep, "storyboard.jpg"))
    per_sheet = 20
    timing = json.load(open(os.path.join(ep, "timing.json")))
    sl = json.load(open(os.path.join(ep, "shotlist.json")))
    stills = sorted(glob.glob(os.path.join(ep, "shots", "storyboard", "beat_*.png")))
    PW, PH, CAP = 480, 270, 92
    fb, fr = ImageFont.truetype(F_BOLD, 15), ImageFont.truetype(F_REG, 13)
    panels = []
    for s in sl["shots"]:
        i = int(s["id"])
        p = timing["paragraphs"][i]
        fn = os.path.join(ep, "shots", "storyboard", f"beat_{i:02d}.png")
        im = Image.open(fn).convert("RGB").resize((PW, PH), Image.LANCZOS) if os.path.exists(fn) else Image.new("RGB", (PW, PH), (200, 200, 200))
        panel = Image.new("RGB", (PW, PH + CAP), (247, 246, 243))
        panel.paste(im, (0, 0))
        d = ImageDraw.Draw(panel)
        d.rectangle((0, 0, 34, 22), fill=(24, 26, 29))
        d.text((5, 3), f"{i:02d}", font=fb, fill=(255, 214, 0))
        head = f"{s['scene']}  |  {p['start']:.1f}-{p['end']:.1f}s  ({p['end'] - p['start']:.1f}s)"
        d.text((8, PH + 6), head, font=fb, fill=(24, 26, 29))
        txt = textwrap.fill(p["text"], 66)[:260]
        d.text((8, PH + 26), txt, font=fr, fill=(60, 62, 66))
        panels.append(panel)
    sheets = []
    for k in range(0, len(panels), per_sheet):
        chunk = panels[k:k + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (PW + 12) + 12, rows * (PH + CAP + 12) + 12), (225, 224, 220))
        for j, pn in enumerate(chunk):
            sheet.paste(pn, (12 + (j % cols) * (PW + 12), 12 + (j // cols) * (PH + CAP + 12)))
        fn = out if len(panels) <= per_sheet else out.replace(".jpg", f"_{k // per_sheet + 1}.jpg")
        sheet.save(fn, quality=88)
        sheets.append(fn)
        print("wrote", fn)
    return sheets


if __name__ == "__main__":
    main()
