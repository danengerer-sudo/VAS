"""Channel intro / splash: episode title + "Narrated by" with the narrator's photo in a circle.

Clean light design that matches the white diorama look: a softly blurred, brightened frame of the
episode's own scene behind eased type, an accent rule that draws itself, the portrait ring that
sweeps in, then everything clears as the blur pulls focus into the first shot.

python3 intro.py "Where Do Gun Rights Come From?" bg.png out_dir [--mp4 preview.mp4]
"""
import os
import sys
import math
import subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = "/usr/share/fonts/opentype/inter"
F_TITLE = os.path.join(FONT_DIR, "InterDisplay-Bold.otf")
F_NAME = os.path.join(FONT_DIR, "InterDisplay-SemiBold.otf")
F_SMALL = os.path.join(FONT_DIR, "Inter-SemiBold.otf")
PHOTO = os.path.join(HERE, "..", "branding", "narrator_dan_engerer.jpg")
INK = (24, 26, 29)
MUTED = (118, 122, 128)
ACCENT = (240, 128, 32)


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def seg(t, a, b):
    return (t - a) / (b - a)


def circle_photo(path, d, ss=4):
    im = Image.open(path).convert("RGB")
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    im = im.resize((d * ss, d * ss), Image.LANCZOS)
    mask = Image.new("L", (d * ss, d * ss), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=255)
    im = im.resize((d, d), Image.LANCZOS)
    mask = mask.resize((d, d), Image.LANCZOS)
    out = Image.new("RGBA", (d, d))
    out.paste(im, (0, 0), mask)
    return out


def text_layer(size, text, font, fill, alpha, dy=0, xy=(0, 0), anchor="mm", tracking=0):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    if alpha <= 0:
        return layer
    d = ImageDraw.Draw(layer)
    x, y = xy
    if tracking:
        widths = [d.textlength(ch, font=font) + tracking for ch in text]
        total = sum(widths) - tracking
        cx = x - total / 2 if anchor[0] == "m" else x
        for ch, w in zip(text, widths):
            d.text((cx, y + dy), ch, font=font, fill=(*fill, int(255 * alpha)), anchor="l" + anchor[1])
            cx += w
    else:
        d.text((x, y + dy), text, font=font, fill=(*fill, int(255 * alpha)), anchor=anchor)
    return layer


def make_intro(title, bg_path, out_dir, name="Dan Engerer", photo=PHOTO, fps=24, seconds=5.5, W=1920, H=1080):
    os.makedirs(out_dir, exist_ok=True)
    bg0 = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
    white = Image.new("RGB", (W, H), (247, 246, 243))
    f_title = ImageFont.truetype(F_TITLE, 86)
    f_small = ImageFont.truetype(F_SMALL, 21)
    f_name = ImageFont.truetype(F_NAME, 40)
    D = 156
    avatar = circle_photo(photo, D)
    shadow = Image.new("RGBA", (D + 80, D + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((40, 46, 40 + D, 46 + D), fill=(0, 0, 0, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))

    words = title.split()
    # measure title words for the staggered reveal
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    space = tmp.textlength(" ", font=f_title)
    wl = [tmp.textlength(w, font=f_title) for w in words]
    total = sum(wl) + space * (len(words) - 1)
    lines = [words]
    if total > W * 0.78:  # two balanced lines
        best = min(range(1, len(words)), key=lambda k: abs(sum(wl[:k]) - sum(wl[k:])))
        lines = [words[:best], words[best:]]
    title_y0 = 405 if len(lines) == 1 else 360
    line_h = 102

    # narrator block geometry (avatar left, two text lines right), centred as a group
    name_w = tmp.textlength(name, font=f_name)
    label = "NARRATED BY"
    block_w = D + 34 + max(name_w, 190)
    bx = (W - block_w) / 2
    by = title_y0 + line_h * (len(lines) - 1) + 205
    n = int(seconds * fps)
    for i in range(n):
        t = i / fps
        # background: slow push-in, blurred + brightened; pulls focus in the last second
        zoom = 1.0 + 0.05 * (i / n)
        bw, bh = int(W * zoom), int(H * zoom)
        bg = bg0.resize((bw, bh), Image.BILINEAR).crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W, (bh - H) // 2 + H))
        out_t = ease_in_out(seg(t, seconds - 1.25, seconds))
        blur = 22 * (1 - out_t)
        if blur > 0.3:
            bg = bg.filter(ImageFilter.GaussianBlur(blur))
        wash = 0.8 * (1 - out_t)
        frame = Image.blend(bg, white, wash)
        # opening fade from white
        frame = Image.blend(white, frame, ease_out(seg(t, 0.0, 0.6)))
        fr = frame.convert("RGBA")
        fade_all = 1 - ease_in_out(seg(t, seconds - 1.25, seconds - 0.45))

        # title words: staggered fade + rise
        k = 0
        for li, ln in enumerate(lines):
            lw = sum(tmp.textlength(w, font=f_title) for w in ln) + space * (len(ln) - 1)
            x = (W - lw) / 2
            y = title_y0 + li * line_h
            for w in ln:
                a = ease_out(seg(t, 0.45 + 0.09 * k, 1.15 + 0.09 * k))
                lay = text_layer((W, H), w, f_title, INK, a * fade_all, dy=(1 - a) * 26, xy=(x, y), anchor="lm")
                fr = Image.alpha_composite(fr, lay)
                x += tmp.textlength(w, font=f_title) + space
                k += 1
        # accent rule draws out from the centre
        ra = ease_out(seg(t, 1.05, 1.75))
        if ra > 0 and fade_all > 0.01:
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            half = 64 * ra
            ry = title_y0 + line_h * (len(lines) - 1) + 82
            d.rounded_rectangle((W / 2 - half, ry - 3, W / 2 + half, ry + 3), radius=3,
                                fill=(*ACCENT, int(255 * fade_all)))
            fr = Image.alpha_composite(fr, lay)
        # narrator: shadow + avatar scale-in, ring sweep, label + name
        pa = ease_out(seg(t, 1.55, 2.3))
        if pa > 0:
            s = 0.86 + 0.14 * pa
            dd = max(2, int(D * s))
            av = avatar.resize((dd, dd), Image.LANCZOS)
            ax = int(bx + (D - dd) / 2)
            ay = int(by + (D - dd) / 2)
            sh = shadow.copy()
            sh.putalpha(ImageChops.multiply(sh.getchannel("A"), Image.new("L", sh.size, int(255 * pa * fade_all))))
            fr.alpha_composite(sh, (int(bx - 40), int(by - 40)))
            av.putalpha(ImageChops.multiply(av.getchannel("A"), Image.new("L", av.size, int(255 * pa * fade_all))))
            fr.alpha_composite(av, (ax, ay))
            ring = ease_in_out(seg(t, 1.8, 2.7))
            if ring > 0 and fade_all > 0.01:
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                d = ImageDraw.Draw(lay)
                pad = 7
                d.arc((bx - pad, by - pad, bx + D + pad, by + D + pad), -90, -90 + 360 * ring,
                      fill=(*ACCENT, int(255 * fade_all)), width=4)
                fr = Image.alpha_composite(fr, lay)
        la = ease_out(seg(t, 2.05, 2.75))
        tx = bx + D + 34
        fr = Image.alpha_composite(fr, text_layer((W, H), label, f_small, MUTED, la * fade_all, dy=(1 - la) * 14,
                                                  xy=(tx, by + D / 2 - 26), anchor="ls", tracking=4))
        na = ease_out(seg(t, 2.2, 2.95))
        fr = Image.alpha_composite(fr, text_layer((W, H), name, f_name, INK, na * fade_all, dy=(1 - na) * 18,
                                                  xy=(tx, by + D / 2 + 30), anchor="ls"))
        fr.convert("RGB").save(os.path.join(out_dir, f"intro_{i:04d}.png"))
    return n


if __name__ == "__main__":
    title, bg, out = sys.argv[1], sys.argv[2], sys.argv[3]
    n = make_intro(title, bg, out)
    if "--mp4" in sys.argv:
        mp4 = sys.argv[sys.argv.index("--mp4") + 1]
        subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i",
                               os.path.join(out, "intro_%04d.png"), "-c:v", "libx264", "-crf", "16",
                               "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4])
    print("frames", n)
