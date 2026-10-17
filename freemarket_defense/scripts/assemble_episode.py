"""Assemble an episode: intro → shots (cross-dissolves) → end card, with narration (+ optional music).

python3 assemble_episode.py <episode_dir> --title "..." --frames <dir with f_####.png or shots/*/frames>
                            [--videos <dir with SHOT.mp4 from fetch_videos.py>]
                            [--audio narration.wav] [--music file.mp3] [--out video.mp4] [--res 1280x720]
Shot frame ranges come from shotlist.json (global frame numbers f_0001...). Missing frames are
filled by holding the last available one (so a partial render still previews).
"""
import os
import sys
import json
import glob
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from intro import make_intro

FPS = 24
F_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
F_SEMI = "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf"
F_REG = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
GOLD = (255, 214, 0)


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def end_card(base, W, H, a, title):
    img = base.filter(ImageFilter.GaussianBlur(8 * a)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (247, 246, 243, int(215 * a)))
    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)
    f1, f2, f3 = ImageFont.truetype(F_BOLD, 58), ImageFont.truetype(F_SEMI, 26), ImageFont.truetype(F_REG, 18)
    w = d.textlength(title, font=f1)
    d.text(((W - w) / 2, H * 0.36), title, font=f1, fill=(24, 26, 29, int(255 * a)))
    d.rounded_rectangle((W / 2 - 40, H * 0.36 + 84, W / 2 + 40, H * 0.36 + 90), radius=3, fill=(*GOLD, int(255 * a)))
    s = "Narrated by Dan Engerer"
    w = d.textlength(s, font=f2)
    d.text(((W - w) / 2, H * 0.36 + 112), s, font=f2, fill=(60, 62, 66, int(255 * a)))
    c = "Models: original + CC0 (Kenney, Poly Haven, MakeHuman). Motion capture: CMU."
    w = d.textlength(c, font=f3)
    d.text(((W - w) / 2, H - 56), c, font=f3, fill=(140, 144, 150, int(255 * a)))
    return img


def main():
    ep = os.path.abspath(sys.argv[1])
    title = arg("--title", "Episode")
    frames_dir = arg("--frames", os.path.join(ep, "frames"))
    audio = arg("--audio", os.path.join(ep, "narration_tts.wav"))
    music = arg("--music")
    out = arg("--out", os.path.join(ep, "episode.mp4"))
    W, H = map(int, arg("--res", "1920x1080").split("x"))
    sl = json.load(open(os.path.join(ep, "shotlist.json")))
    videos = arg("--videos")
    if videos:  # per-shot mp4s from the render farm -> globally numbered frames under frames_dir/<id>/
        frames_dir = arg("--frames", os.path.join(ep, "frames_final"))
        for s in sl["shots"]:
            mp4 = os.path.join(videos, s["id"] + ".mp4")
            d = os.path.join(frames_dir, s["id"])
            want = s["frame_end"] - s["frame_start"] + 1
            have = len(glob.glob(os.path.join(d, "f_*.png")))
            if not os.path.exists(mp4):
                print("WARN no video for", s["id"], "- holding last frame")
                continue
            if have == want:
                continue
            os.makedirs(d, exist_ok=True)
            subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-start_number", str(s["frame_start"]),
                                   os.path.join(d, "f_%04d.png")])
            print("expanded", s["id"], len(glob.glob(os.path.join(d, "f_*.png"))), "frames")
    comp = os.path.join(ep, "comp")
    os.makedirs(comp, exist_ok=True)
    for f in glob.glob(os.path.join(comp, "*.jpg")):
        os.remove(f)

    def load(fn):
        return Image.open(fn).convert("RGB").resize((W, H), Image.LANCZOS)

    # frame lookup: global f_####.png anywhere under frames_dir
    idx = {}
    for fn in glob.glob(os.path.join(frames_dir, "**", "f_*.png"), recursive=True):
        try:
            idx[int(os.path.basename(fn)[2:6])] = fn
        except ValueError:
            pass
    if not idx:
        sys.exit("no frames found under " + frames_dir)
    first_shot_frame = load(idx[min(idx)])

    n = 0
    # intro over a blurred first frame
    intro_dir = os.path.join(ep, "intro_frames")
    if not glob.glob(os.path.join(intro_dir, "*.png")):
        tmp = os.path.join(ep, "_intro_bg.png")
        first_shot_frame.save(tmp)
        make_intro(title, tmp, intro_dir, W=W, H=H)
    intro_frames = sorted(glob.glob(os.path.join(intro_dir, "*.png")))
    for fn in intro_frames:
        Image.open(fn).convert("RGB").resize((W, H), Image.LANCZOS).save(os.path.join(comp, f"c_{n:05d}.jpg"), quality=94)
        n += 1
    intro_len = len(intro_frames) / FPS

    # shots butt together on the narration timeline; every frame is kept (no drift), and each cut is
    # softened over SOFT frames by blending toward a held frame of the other side.
    SOFT = int(arg("--soft", 3))
    last_img = None
    hold = first_shot_frame
    prev_last = None
    for si, s in enumerate(sl["shots"]):
        imgs = []
        for g in range(s["frame_start"], s["frame_end"] + 1):
            if g in idx:
                hold = load(idx[g])
            imgs.append(hold)
        nxt = sl["shots"][si + 1] if si + 1 < len(sl["shots"]) else None
        next_first = load(idx[nxt["frame_start"]]) if nxt and nxt["frame_start"] in idx else None
        L = len(imgs)
        for k, im in enumerate(imgs):
            if prev_last is not None and k < SOFT:
                im = Image.blend(prev_last, im, (k + 1) / (SOFT + 1))
            elif next_first is not None and k >= L - SOFT:
                im = Image.blend(im, next_first, (k - (L - SOFT) + 1) / (SOFT + 1) * 0.5)
            im.save(os.path.join(comp, f"c_{n:05d}.jpg"), quality=94)
            n += 1
        prev_last = imgs[-1]
        last_img = imgs[-1]
    # end card
    END = 4.0
    for i in range(int(END * FPS)):
        a = min(1.0, i / 14)
        im = end_card(last_img, W, H, a, title).convert("RGB")
        if i > END * FPS - 16:
            im = Image.blend(im, Image.new("RGB", (W, H), (0, 0, 0)), (i - (END * FPS - 16)) / 16)
        im.save(os.path.join(comp, f"c_{n:05d}.jpg"), quality=94)
        n += 1

    # audio: narration delayed by intro length minus the lead we cut off the first shot
    delay_ms = int((intro_len - sl["audio_offset"]) * 1000)
    af = [f"[1:a]adelay={max(0, delay_ms)}|{max(0, delay_ms)},apad[v]"]
    inputs = ["-framerate", str(FPS), "-i", os.path.join(comp, "c_%05d.jpg"), "-i", audio]
    if music:
        inputs += ["-stream_loop", "-1", "-i", music]
        af.append("[2:a]volume=0.18,afade=t=in:st=0:d=2[m]")
        af.append("[v][m]amix=inputs=2:duration=first:dropout_transition=3[a]")
        amap = "[a]"
    else:
        amap = "[v]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(af), "-map", "0:v", "-map", amap,
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", out]
    subprocess.check_call(cmd)
    print("wrote", out, n, "frames", round(n / FPS, 1), "s")


if __name__ == "__main__":
    main()
