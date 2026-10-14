"""Composite captions/title cards onto the rendered frames and encode the MP4.

python3 assemble.py [frames_dir] [out.mp4]
"""
import os
import sys
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
FR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "render", "frames")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "render", "how_free_market_defense_could_work.mp4")
TMP = os.path.join(HERE, "..", "render", "comp")
os.makedirs(TMP, exist_ok=True)
W, H = 1280, 720
FPS = 24
F_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
F_SEMI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
F_REG = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
ACCENT = (240, 140, 40)

SHOTS = [  # (start, end, kicker, title, body)
    (1, 96, None, None, None),
    (97, 216, "01", "Residents choose a protector",
     "Households and businesses subscribe to competing defense agencies, paying for the protection they actually want."),
    (217, 360, "02", "Agencies compete on performance",
     "Price, readiness and reputation win customers. A failing agency loses them to a rival."),
    (361, 504, "03", "Specialists sell air cover",
     "Aviation firms contract helicopters to many agencies at once, so no single firm has to own everything."),
    (505, 624, "04", "Maritime firms guard the coast",
     "Coastal patrols are paid per contract by ports, shippers and their insurers."),
    (625, 768, "05", "Insurers make aggression expensive",
     "Defense insurers price risk and fund deterrence. An invader faces many independent, well-funded defenders, not one capital to capture."),
]
END_FRAMES = 84


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def ramp(f, f0, f1, fade=10, delay=8):
    a = min((f - f0 - delay) / fade, (f1 - f) / fade)
    return max(0.0, min(1.0, a))


def lower_third(img, kicker, title, body, a):
    if a <= 0:
        return img
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    # soft gradient band at the bottom
    for y in range(H - 230, H):
        t = (y - (H - 230)) / 230
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(200 * t * t * a)))
    x0, y0 = 64, H - 170
    fk, ft, fb = font(F_BOLD, 18), font(F_BOLD, 38), font(F_REG, 21)
    slide = int((1 - a) * 18)
    d.rectangle([x0, y0 + 4 + slide, x0 + 4, y0 + 112 + slide], fill=(*ACCENT, int(255 * a)))
    d.text((x0 + 20, y0 + slide), f"{kicker}  ·  HOW IT COULD WORK", font=fk, fill=(*ACCENT, int(255 * a)))
    d.text((x0 + 20, y0 + 24 + slide), title, font=ft, fill=(255, 255, 255, int(255 * a)))
    for i, line in enumerate(wrap(d, body, fb, 880)):
        d.text((x0 + 20, y0 + 76 + i * 28 + slide), line, font=fb, fill=(225, 228, 230, int(235 * a)))
    return Image.alpha_composite(img, ov)


def title_card(img, a, sub=True):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(H):
        t = abs(y - H * 0.5) / (H * 0.5)
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int((70 + 60 * (1 - t)) * a)))
    f1, f2 = font(F_BOLD, 64), font(F_SEMI, 22)
    t1 = "How Free Market Defense"
    t2 = "Could Work"
    for i, t in enumerate((t1, t2)):
        w = d.textlength(t, font=f1)
        d.text(((W - w) / 2 + 2, 250 + i * 76 + 3), t, font=f1, fill=(0, 0, 0, int(120 * a)))
        d.text(((W - w) / 2, 250 + i * 76), t, font=f1, fill=(255, 255, 255, int(255 * a)))
    d.rectangle([W / 2 - 40, 418, W / 2 + 40, 422], fill=(*ACCENT, int(255 * a)))
    if sub:
        s = "A 3D THOUGHT EXPERIMENT"
        w = d.textlength(s, font=f2)
        d.text(((W - w) / 2, 440), s, font=f2, fill=(230, 230, 230, int(230 * a)))
    return Image.alpha_composite(img, ov)


def end_card(base, a):
    img = base.filter(ImageFilter.GaussianBlur(6 * a)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (8, 10, 12, int(185 * a)))
    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)
    f1, f2, f3 = font(F_BOLD, 52), font(F_SEMI, 24), font(F_REG, 16)
    t = "How Free Market Defense Could Work"
    w = d.textlength(t, font=f1)
    d.text(((W - w) / 2, 250), t, font=f1, fill=(255, 255, 255, int(255 * a)))
    d.rectangle([W / 2 - 40, 330, W / 2 + 40, 334], fill=(*ACCENT, int(255 * a)))
    pts = ["Competing agencies", "Specialist contractors", "Insurance-backed deterrence"]
    s = "   ·   ".join(pts)
    w = d.textlength(s, font=f2)
    d.text(((W - w) / 2, 356), s, font=f2, fill=(230, 232, 235, int(255 * a)))
    c = "Rendered in Blender (Cycles). Props, trees and rifle: Poly Haven (CC0). Soldier: three.js examples."
    w = d.textlength(c, font=f3)
    d.text(((W - w) / 2, H - 60), c, font=f3, fill=(170, 175, 180, int(255 * a)))
    return img


def vignette():
    v = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(v)
    for i in range(60):
        t = i / 60
        d.ellipse([-W * 0.25 + t * W * 0.25, -H * 0.3 + t * H * 0.3, W * 1.25 - t * W * 0.25, H * 1.3 - t * H * 0.3],
                  fill=int(255 * t))
    v = v.filter(ImageFilter.GaussianBlur(40))
    return v


VIG = vignette()
BLACK = Image.new("RGBA", (W, H), (0, 0, 0, 255))


def load(f):
    p = os.path.join(FR, f"f_{f:04d}.png")
    im = Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)
    dark = Image.eval(im, lambda c: int(c * 0.72))
    return Image.composite(im, dark, VIG).convert("RGBA")


def main():
    n = 0
    last = None
    for (f0, f1, k, t, b) in SHOTS:
        for f in range(f0, f1 + 1):
            img = load(f)
            if k is None:
                img = title_card(img, ramp(f, f0, f1 + 6, 14, 10))
            else:
                img = lower_third(img, k, t, b, ramp(f, f0, f1, 10, 10))
            # fade in from black at the very start
            if f < 13:
                img = Image.blend(BLACK, img, f / 13)
            img.convert("RGB").save(os.path.join(TMP, f"c_{n:05d}.jpg"), quality=95)
            n += 1
            last = f
    base = load(last).convert("RGB")
    for i in range(END_FRAMES):
        a = min(1.0, i / 16)
        img = end_card(base, a)
        if i > END_FRAMES - 14:
            img = Image.blend(img, BLACK, (i - (END_FRAMES - 14)) / 14)
        img.convert("RGB").save(os.path.join(TMP, f"c_{n:05d}.jpg"), quality=95)
        n += 1
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i",
                           os.path.join(TMP, "c_%05d.jpg"), "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT])
    print("wrote", OUT, n, "frames")


if __name__ == "__main__":
    main()
