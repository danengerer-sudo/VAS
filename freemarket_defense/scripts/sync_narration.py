#!/usr/bin/env python3
"""sync_narration.py — align a narrator's voice-over to the script and emit timing.json.

    python3 sync_narration.py <script.txt> <audio1> [audio2 ...] -o timing.json
                              [--trim-gaps 1.5] [--clean-wav out.wav]
                              [--model small.en] [--vad] [--whisper-cache words.json]

Pipeline
  1. Parse the script: title line, "(direction)" lines are ignored, blank-line
     separated paragraphs are the narration beats.
  2. Concatenate the audio files (ffmpeg, 48 kHz mono s16 WAV), remembering the
     offset of each input file on the joined timeline.
  3. Transcribe with faster-whisper (word timestamps).
  4. Align transcript tokens to script tokens with a global DP (fuzzy token
     match, insertions/deletions tolerated).  Insertions that duplicate nearby
     script text are treated as retakes/false starts: the LAST take is kept and
     the earlier span is marked for removal.
  5. With --trim-gaps X, silences between paragraphs longer than X are cut down
     to X.  Removed spans (retakes + gap excess) are cut out of the audio with
     20 ms crossfades (--clean-wav), and timing.json refers to the cleaned
     timeline.
  6. Write timing.json: {"source", "duration", "paragraphs": [{"text", "start",
     "end", "words": [{"w", "start", "end"}], ["confidence"]}]} and print a report.
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SR = 48000           # cleaned-audio sample rate
XFADE = 0.020        # crossfade length at every cut, seconds
MIN_SEG = 0.10       # shortest kept audio segment (merge cuts closer than this)
PAD_BEFORE_WORD = 0.12   # keep this much air in front of a kept word when cutting a retake


# ----------------------------------------------------------------------------- script
def parse_script(path):
    """Return (title, [paragraph_text, ...]).  Lines starting with '(' are directions."""
    lines = open(path, encoding="utf-8").read().splitlines()
    title = None
    paras, cur = [], []
    for raw in lines:
        line = raw.strip()
        if title is None:
            if line:
                title = line
            continue
        if not line:
            if cur:
                paras.append("\n".join(cur))
                cur = []
            continue
        if line.startswith("("):
            continue
        cur.append(line)
    if cur:
        paras.append("\n".join(cur))
    return title or "", paras


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
_NUM_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
              "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten"}


def normalise_tokens(text):
    """Lower-case alphanumeric tokens; hyphens and punctuation split, apostrophes kept."""
    t = text.lower().replace("’", "'").replace("‘", "'")
    toks = _TOKEN_RE.findall(t)
    return [_NUM_WORDS.get(x, x) for x in toks]


def script_words(paragraph):
    """Original words of a paragraph (for the "words" list) with their normalised tokens.
    Returns [(word, [tok, ...]), ...]; words with no alnum content (e.g. '—') are dropped."""
    out = []
    for w in paragraph.split():
        toks = normalise_tokens(w)
        if toks:
            out.append((w, toks))
    return out


def token_sim(a, b):
    if a == b:
        return 1.0
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
        return 0.85
    if abs(len(a) - len(b)) > max(len(a), len(b)) // 2:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ----------------------------------------------------------------------------- audio
def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path]).stdout
    return float(out.decode().strip())


def concat_inputs(files, out_wav):
    """Convert every input to 48 kHz mono s16 and concatenate.  Returns [(file, offset, dur)]."""
    tmpdir = os.path.dirname(out_wav)
    parts, inputs, t = [], [], 0.0
    for i, f in enumerate(files):
        p = os.path.join(tmpdir, f"in_{i:02d}.wav")
        run(["ffmpeg", "-y", "-v", "error", "-i", f, "-vn", "-ac", "1", "-ar", str(SR),
             "-c:a", "pcm_s16le", p])
        d = probe_duration(p)
        inputs.append({"file": f, "offset": round(t, 3), "duration": round(d, 3)})
        parts.append(p)
        t += d
    if len(parts) == 1:
        shutil.copy(parts[0], out_wav)
    else:
        lst = os.path.join(tmpdir, "concat.txt")
        with open(lst, "w") as fh:
            for p in parts:
                fh.write("file '%s'\n" % p.replace("'", r"'\''"))
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
             "-c", "copy", out_wav])
    return inputs, t


def load_audio_16k(wav):
    import numpy as np
    raw = run(["ffmpeg", "-v", "error", "-i", wav, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"]).stdout
    return np.frombuffer(raw, dtype=np.float32)


class Energy:
    """10 ms RMS envelope of the joined audio, used to snap paragraph edges to real speech on/offsets."""
    HOP = 0.010

    def __init__(self, wav):
        import numpy as np
        raw = run(["ffmpeg", "-v", "error", "-i", wav, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]).stdout
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        hop = int(16000 * self.HOP)
        n = len(x) // hop
        fr = x[:n * hop].reshape(n, hop)
        self.rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
        floor = float(np.percentile(self.rms, 10))
        self.thr = max(floor * 4.0, 10 ** (-45 / 20))   # 4x noise floor, at least -45 dBFS
        self.np = np

    def voiced(self, t):
        i = int(t / self.HOP)
        return 0 <= i < len(self.rms) and self.rms[i] > self.thr

    def snap_start(self, t, lo, hi):
        """First voiced frame in [lo, hi]; falls back to t."""
        i0, i1 = max(0, int(lo / self.HOP)), min(len(self.rms), int(hi / self.HOP) + 1)
        for i in range(i0, i1):
            if self.rms[i] > self.thr:
                return max(lo, i * self.HOP - 0.01)
        return t

    def snap_end(self, t, lo, hi):
        """Last voiced frame in [lo, hi]; falls back to t."""
        i0, i1 = max(0, int(lo / self.HOP)), min(len(self.rms), int(hi / self.HOP) + 1)
        for i in range(i1 - 1, i0 - 1, -1):
            if self.rms[i] > self.thr:
                return min(hi, (i + 1) * self.HOP + 0.01)
        return t


def transcribe(wav, model_name, vad):
    from faster_whisper import WhisperModel
    audio = load_audio_16k(wav)          # decode with ffmpeg: avoids PyAV version issues
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, _info = model.transcribe(audio, word_timestamps=True, beam_size=5,
                                   vad_filter=vad, condition_on_previous_text=False,
                                   vad_parameters=dict(min_silence_duration_ms=700) if vad else None)
    words = []
    for s in segs:
        for w in s.words or []:
            txt = w.word.strip()
            if txt:
                words.append({"w": txt, "start": float(w.start), "end": float(w.end),
                              "p": float(w.probability)})
    return words


def transcript_tokens(words):
    """Explode whisper words into normalised tokens (a word may yield several, e.g. 'mother-in-law')."""
    toks = []
    for wi, w in enumerate(words):
        parts = normalise_tokens(w["w"])
        if not parts:
            continue
        span = w["end"] - w["start"]
        for k, p in enumerate(parts):
            s = w["start"] + span * k / len(parts)
            e = w["start"] + span * (k + 1) / len(parts)
            toks.append({"tok": p, "start": s, "end": e, "word": wi})
    return toks


# ----------------------------------------------------------------------------- alignment
def align(script_toks, trans_toks):
    """Global alignment.  Returns list a[i] = j (transcript token index) or None for each script token,
    and the set of transcript indices used.  Ties are broken so that the LAST matching copy wins."""
    n, m = len(script_toks), len(trans_toks)
    GAP_S, GAP_T = -1.0, -0.6          # skipping a script token / a transcript token
    # score[i][j] = best score aligning script[:i] with transcript[:j]
    NEG = float("-inf")
    score = [[NEG] * (m + 1) for _ in range(n + 1)]
    move = [[0] * (m + 1) for _ in range(n + 1)]   # 1=diag 2=up(skip script) 3=left(skip transcript)
    score[0][0] = 0.0
    for j in range(1, m + 1):
        score[0][j] = score[0][j - 1] + GAP_T
        move[0][j] = 3
    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0] + GAP_S
        move[i][0] = 2
        st = script_toks[i - 1]
        row, prow, mrow = score[i], score[i - 1], move[i]
        for j in range(1, m + 1):
            sim = token_sim(st, trans_toks[j - 1])
            if sim >= 0.999:
                ms = 2.0
            elif sim >= 0.75:
                ms = 1.0 + (sim - 0.75) * 2
            else:
                ms = -1.5
            d = prow[j - 1] + ms
            u = prow[j] + GAP_S
            l = row[j - 1] + GAP_T
            # tie-break order: diagonal first (so trace-back from the end prefers the latest copy)
            best, mv = d, 1
            if l > best:
                best, mv = l, 3
            if u > best:
                best, mv = u, 2
            row[j], mrow[j] = best, mv
    a = [None] * n
    i, j = n, m
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == 1:
            if token_sim(script_toks[i - 1], trans_toks[j - 1]) >= 0.75:
                a[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif mv == 2:
            i -= 1
        else:
            j -= 1
    return a


def fix_retakes(a, script_toks, trans_toks, para_of_tok, min_len=2):
    """Find runs of unaligned transcript tokens that duplicate script text nearby.

    If the duplicate's script window is aligned to LATER transcript tokens -> the run is an
    earlier take: mark it for removal.  If it is aligned to EARLIER transcript tokens -> the
    DP kept the first take; re-point the script tokens at the run (the later take) and mark the
    earlier transcript span for removal.  Returns list of (j0, j1) transcript index spans to cut.
    """
    m = len(trans_toks)
    used = {j: i for i, j in enumerate(a) if j is not None}
    cuts = []
    runs, j = [], 0
    while j < m:
        if j in used:
            j += 1
            continue
        k = j
        while k < m and k not in used:
            k += 1
        runs.append((j, k))
        j = k
    for (j0, j1) in runs:
        if j1 - j0 < min_len:
            continue
        run_toks = [t["tok"] for t in trans_toks[j0:j1]]
        # script neighbourhood: the paragraph(s) aligned just before/after this run
        prev_i = max((used[x] for x in range(j0 - 1, -1, -1) if x in used), default=None) \
            if any(x in used for x in range(0, j0)) else None
        next_i = next((used[x] for x in range(j1, m) if x in used), None)
        paras = set()
        if prev_i is not None:
            paras.add(para_of_tok[prev_i])
        if next_i is not None:
            paras.add(para_of_tok[next_i])
        if not paras:
            continue
        lo = min(i for i, p in enumerate(para_of_tok) if p in paras)
        hi = max(i for i, p in enumerate(para_of_tok) if p in paras) + 1
        # best-matching script window of similar length inside [lo, hi)
        L = j1 - j0
        best = (0.0, None)
        for wl in {L, max(1, L - 1), L + 1, max(1, L - 2), L + 2}:
            for s0 in range(lo, max(lo, hi - wl) + 1):
                win = script_toks[s0:s0 + wl]
                if not win:
                    continue
                r = difflib.SequenceMatcher(None, run_toks, win).ratio()
                if r > best[0]:
                    best = (r, (s0, s0 + wl))
        ratio, win = best
        if win is None or ratio < 0.6:
            continue
        s0, s1 = win
        aligned_js = [a[i] for i in range(s0, s1) if a[i] is not None]
        if not aligned_js:
            continue
        if min(aligned_js) >= j1:
            # earlier take -> cut the run
            cuts.append((j0, j1, "earlier take of script tokens %d-%d (match %.2f)" % (s0, s1, ratio)))
        elif max(aligned_js) < j0:
            # the DP kept the first take; move those script tokens onto this (later) run
            sm = difflib.SequenceMatcher(None, [script_toks[i] for i in range(s0, s1)], run_toks)
            old_js = (min(aligned_js), max(aligned_js) + 1)
            for i in range(s0, s1):
                a[i] = None
            for tag, i0, i1, k0, k1 in sm.get_opcodes():
                if tag == "equal":
                    for d in range(i1 - i0):
                        a[s0 + i0 + d] = j0 + k0 + d
                elif tag == "replace":
                    for d in range(min(i1 - i0, k1 - k0)):
                        if token_sim(script_toks[s0 + i0 + d], run_toks[k0 + d]) >= 0.6:
                            a[s0 + i0 + d] = j0 + k0 + d
            cuts.append((old_js[0], old_js[1],
                         "earlier take of script tokens %d-%d, re-aligned to later take (match %.2f)"
                         % (s0, s1, ratio)))
    return cuts


# ----------------------------------------------------------------------------- timeline edits
def merge_intervals(iv):
    iv = sorted((s, e) for s, e in iv if e > s)
    out = []
    for s, e in iv:
        if out and s <= out[-1][1] + MIN_SEG:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


class Timeline:
    """Maps original-timeline seconds to cleaned-timeline seconds given removed intervals."""

    def __init__(self, removed, total):
        self.removed = merge_intervals(removed)
        self.total = total
        self.kept = []
        t = 0.0
        for s, e in self.removed:
            if s > t:
                self.kept.append((t, s))
            t = e
        if t < total:
            self.kept.append((t, total))
        # output offset of each kept segment (each join loses one crossfade length)
        self.offsets = []
        o = 0.0
        for k, (s, e) in enumerate(self.kept):
            self.offsets.append(o)
            o += (e - s) - (XFADE if k < len(self.kept) - 1 else 0.0)
        self.new_total = max(o, 0.0)

    def map(self, t):
        for k, (s, e) in enumerate(self.kept):
            if t <= e:
                if t < s:            # inside a removed span: snap to the cut point
                    return self.offsets[k]
                return self.offsets[k] + (t - s)
        return self.new_total

    def render(self, src_wav, out_wav):
        if not self.removed:
            shutil.copy(src_wav, out_wav)
            return
        parts, chain = [], []
        for k, (s, e) in enumerate(self.kept):
            parts.append("[0:a]atrim=start=%.6f:end=%.6f,asetpts=PTS-STARTPTS[s%d]" % (s, e, k))
        prev = "[s0]"
        for k in range(1, len(self.kept)):
            out = "[x%d]" % k if k < len(self.kept) - 1 else "[out]"
            chain.append("%s[s%d]acrossfade=d=%.3f:c1=tri:c2=tri%s" % (prev, k, XFADE, out))
            prev = out
        if len(self.kept) == 1:
            chain.append("[s0]acopy[out]")
        fc = ";".join(parts + chain)
        run(["ffmpeg", "-y", "-v", "error", "-i", src_wav, "-filter_complex", fc,
             "-map", "[out]", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", out_wav])


# ----------------------------------------------------------------------------- main
def fmt(t):
    return "%6.2f" % t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("audio", nargs="+")
    ap.add_argument("-o", "--output", required=True, help="timing.json to write")
    ap.add_argument("--trim-gaps", type=float, default=None, metavar="SEC",
                    help="cut any silence between paragraphs longer than SEC down to SEC")
    ap.add_argument("--clean-wav", default=None, help="write the edited narration here (48 kHz mono WAV)")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--vad", action="store_true", help="enable faster-whisper's VAD filter")
    ap.add_argument("--whisper-cache", default=None,
                    help="JSON file: reuse the transcription if present, else write it")
    ap.add_argument("--keep-retakes", action="store_true", help="do not cut retake spans from the audio")
    args = ap.parse_args()

    title, paras = parse_script(args.script)
    if not paras:
        sys.exit("no paragraphs found in %s" % args.script)

    tmp = tempfile.mkdtemp(prefix="sync_narration_")
    joined = os.path.join(tmp, "joined.wav")
    inputs, total = concat_inputs(args.audio, joined)
    print("Script: %s  (%d paragraphs)" % (title, len(paras)))
    for inp in inputs:
        print("  audio %-40s offset %s  dur %s" % (os.path.basename(inp["file"]), fmt(inp["offset"]), fmt(inp["duration"])))

    words = None
    if args.whisper_cache and os.path.exists(args.whisper_cache):
        words = json.load(open(args.whisper_cache))
        print("Transcript: %d words from cache %s" % (len(words), args.whisper_cache))
    else:
        print("Transcribing with faster-whisper %s ..." % args.model, flush=True)
        words = transcribe(joined, args.model, args.vad)
        if args.whisper_cache:
            json.dump(words, open(args.whisper_cache, "w"))
        print("Transcript: %d words" % len(words))
    if not words:
        sys.exit("whisper produced no words")

    # --- tokens
    ttoks = transcript_tokens(words)
    stoks, para_of_tok, word_of_tok = [], [], []      # script tokens, paragraph index, (para, word idx)
    para_words = []
    for pi, p in enumerate(paras):
        pw = script_words(p)
        para_words.append(pw)
        for wi, (_w, toks) in enumerate(pw):
            for t in toks:
                stoks.append(t)
                para_of_tok.append(pi)
                word_of_tok.append((pi, wi))

    a = align(stoks, [t["tok"] for t in ttoks])
    retake_cuts = [] if args.keep_retakes else fix_retakes(a, stoks, ttoks, para_of_tok)

    # --- per-paragraph spans on the ORIGINAL timeline
    para_info = []
    for pi, pw in enumerate(para_words):
        idx = [i for i, p in enumerate(para_of_tok) if p == pi]
        matched = [a[i] for i in idx if a[i] is not None]
        n_tok = len(idx)
        frac = len(matched) / max(1, n_tok)
        info = {"n_tok": n_tok, "n_match": len(matched), "frac": frac}
        if matched and (len(matched) >= 2 or n_tok <= 2) and frac >= 0.3:
            info["start"] = ttoks[min(matched)]["start"]
            info["end"] = ttoks[max(matched)]["end"]
            info["first_end"] = ttoks[min(matched)]["end"]    # reliable bounds: whisper tends to
            info["last_start"] = ttoks[max(matched)]["start"]  # smear a word's start/end into a pause
            info["conf"] = "high" if frac >= 0.8 else ("medium" if frac >= 0.5 else "low")
            info["estimated"] = False
        else:
            info["estimated"] = True
            info["conf"] = "low"
        para_info.append(info)

    # snap aligned paragraph edges to the real speech onset/offset (whisper tends to start a word
    # early after a pause and to clip the tail)
    energy = Energy(joined)
    aligned = [i for i, x in enumerate(para_info) if not x["estimated"]]
    for k, pi in enumerate(aligned):                       # pass 1: onsets
        info = para_info[pi]
        prev_end = para_info[aligned[k - 1]]["end"] if k > 0 else 0.0
        lo = max(prev_end + 0.05, info["start"] - 0.25)
        hi = min(info["first_end"] - 0.02, info["end"] - 0.05)
        if hi > lo:
            info["start"] = energy.snap_start(info["start"], lo, hi)
    for k, pi in enumerate(aligned):                       # pass 2: offsets
        info = para_info[pi]
        next_start = para_info[aligned[k + 1]]["start"] if k + 1 < len(aligned) else total
        lo = max(info["last_start"] + 0.02, info["start"] + 0.05)
        hi = min(next_start - 0.05, info["end"] + 0.45)
        if hi > lo:
            info["end"] = energy.snap_end(info["end"], lo, hi)

    # estimate missing paragraphs from neighbours (proportional to character length)
    def est_block(i0, i1):
        """paragraphs i0..i1-1 are all missing; fill the gap between neighbours."""
        left = para_info[i0 - 1]["end"] if i0 > 0 else 0.0
        right = para_info[i1]["start"] if i1 < len(para_info) else total
        gap = max(0.0, right - left)
        lens = [len(paras[i]) for i in range(i0, i1)]
        pause = min(0.9, gap / (len(lens) + 1) * 0.3)
        avail = max(0.0, gap - pause * (len(lens) + 1))
        t = left + pause
        for k, i in enumerate(range(i0, i1)):
            d = avail * lens[k] / max(1, sum(lens))
            para_info[i]["start"], para_info[i]["end"] = t, t + d
            t += d + pause
    i = 0
    while i < len(para_info):
        if para_info[i]["estimated"]:
            k = i
            while k < len(para_info) and para_info[k]["estimated"]:
                k += 1
            est_block(i, k)
            i = k
        else:
            i += 1
    # enforce monotonic order (a mis-alignment should not make paragraphs overlap)
    for i in range(1, len(para_info)):
        if para_info[i]["start"] < para_info[i - 1]["end"]:
            mid = (para_info[i]["start"] + para_info[i - 1]["end"]) / 2
            para_info[i - 1]["end"] = mid
            para_info[i]["start"] = max(mid, para_info[i]["start"])
            para_info[i]["end"] = max(para_info[i]["end"], para_info[i]["start"] + 0.2)

    # --- removal spans on the original timeline
    removed, report_cuts = [], []
    kept_js = set(x for x in a if x is not None)
    for j0, j1, why in retake_cuts:
        s = max(0.0, ttoks[j0]["start"] - PAD_BEFORE_WORD)
        # cut up to just before the next kept transcript token
        nxt = next((ttoks[j]["start"] for j in range(j1, len(ttoks)) if j in kept_js), None)
        e = (nxt - PAD_BEFORE_WORD) if nxt is not None else ttoks[j1 - 1]["end"]
        e = max(e, ttoks[j1 - 1]["end"] + 0.05)
        prev_kept_end = max([ttoks[j]["end"] for j in range(0, j0) if j in kept_js] + [0.0])
        s = max(s, prev_kept_end + 0.02)
        if e > s:
            removed.append((s, e))
            report_cuts.append((s, e, "retake: " + " ".join(t["tok"] for t in ttoks[j0:j1])[:70] + " — " + why))
    if args.trim_gaps is not None:
        X = args.trim_gaps
        bounds = [(0.0, para_info[0]["start"], "lead-in")]
        for i in range(1, len(para_info)):
            bounds.append((para_info[i - 1]["end"], para_info[i]["start"], "gap %d->%d" % (i - 1, i)))
        bounds.append((para_info[-1]["end"], total, "tail"))
        for s, e, label in bounds:
            # pieces of this gap that are not already being removed (retakes)
            pieces, t = [], s
            for rs, re_ in merge_intervals(removed):
                if re_ <= s or rs >= e:
                    continue
                if rs > t:
                    pieces.append((t, rs))
                t = max(t, re_)
            if e > t:
                pieces.append((t, e))
            pause = sum(b - a_ for a_, b in pieces)
            if pause <= X + 0.01:
                continue
            excess = pause - X
            if label == "lead-in":
                order = pieces                                   # take from the file start
            elif label == "tail":
                order = list(reversed(pieces))                   # take from the file end
            else:
                order = sorted(pieces, key=lambda ab: ab[0] - ab[1])   # largest piece first
            for a_, b in order:
                if excess <= 0.01:
                    break
                take = min(excess, b - a_)
                if label == "lead-in":
                    cs, ce = a_, a_ + take
                elif label == "tail":
                    cs, ce = b - take, b
                else:
                    mid = (a_ + b) / 2
                    cs, ce = mid - take / 2, mid + take / 2
                removed.append((cs, ce))
                report_cuts.append((cs, ce, "%s: pause %.2fs -> %.2fs" % (label, pause, X)))
                excess -= take
    tl = Timeline(removed, total)

    # --- build output on the cleaned timeline
    out_paras = []
    for pi, (p, pw, info) in enumerate(zip(paras, para_words, para_info)):
        # per-word times: from aligned tokens, interpolated for unaligned words
        wt = [[None, None] for _ in pw]
        for i, (ppi, wi) in enumerate(word_of_tok):
            if ppi != pi or a[i] is None:
                continue
            t = ttoks[a[i]]
            wt[wi][0] = t["start"] if wt[wi][0] is None else min(wt[wi][0], t["start"])
            wt[wi][1] = t["end"] if wt[wi][1] is None else max(wt[wi][1], t["end"])
        # interpolate gaps linearly between known anchors (or across the paragraph span)
        known = [k for k, (s, e) in enumerate(wt) if s is not None]
        for k in range(len(wt)):
            if wt[k][0] is not None:
                continue
            lo = max([x for x in known if x < k], default=None)
            hi = min([x for x in known if x > k], default=None)
            t0 = wt[lo][1] if lo is not None else info["start"]
            t1 = wt[hi][0] if hi is not None else info["end"]
            n = (hi if hi is not None else len(wt)) - (lo + 1 if lo is not None else 0)
            pos = k - (lo + 1 if lo is not None else 0)
            step = max(0.0, t1 - t0) / max(1, n)
            wt[k] = [t0 + step * pos, t0 + step * (pos + 1)]
        # keep words inside the (snapped) paragraph span
        wt = [[min(max(s, info["start"]), info["end"]), min(max(e, info["start"]), info["end"])] for s, e in wt]
        words_out = [{"w": w, "start": round(tl.map(s), 3), "end": round(tl.map(e), 3)}
                     for (w, _), (s, e) in zip(pw, wt)]
        entry = {"text": p, "start": round(tl.map(info["start"]), 3), "end": round(tl.map(info["end"]), 3),
                 "words": words_out}
        if info["conf"] != "high":
            entry["confidence"] = info["conf"]
        if info["estimated"]:
            entry["estimated"] = True
        out_paras.append(entry)

    if args.clean_wav:
        tl.render(joined, args.clean_wav)
        source = os.path.relpath(args.clean_wav, os.path.dirname(os.path.abspath(args.output)))
        duration = probe_duration(args.clean_wav)
    else:
        source = ", ".join(os.path.basename(f) for f in args.audio)
        duration = tl.new_total
        if tl.removed:
            print("\nNOTE: timing.json refers to the EDITED timeline (%d spans removed) but no --clean-wav was "
                  "written; pass --clean-wav to get matching audio." % len(tl.removed))
    out = {"source": source, "duration": round(duration, 3), "paragraphs": out_paras,
           "inputs": inputs, "original_duration": round(total, 3),
           "removed": [{"start": round(s, 3), "end": round(e, 3), "why": why}
                       for s, e, why in sorted(report_cuts)]}
    json.dump(out, open(args.output, "w"), indent=1, ensure_ascii=False)
    shutil.rmtree(tmp, ignore_errors=True)

    # --- report
    print("\n#   start    end   conf    matched  text")
    for i, (e, info) in enumerate(zip(out_paras, para_info)):
        flag = "EST" if info["estimated"] else ""
        print("%2d %s %s  %-6s %3d/%-3d %3s  %s" % (
            i, fmt(e["start"]), fmt(e["end"]), info["conf"], info["n_match"], info["n_tok"], flag,
            e["text"].split("\n")[0][:60]))
    if report_cuts:
        print("\nRemoved spans (original timeline):")
        for s, e, why in sorted(report_cuts):
            print("  %s - %s  (%.2fs)  %s" % (fmt(s), fmt(e), e - s, why))
    print("\nDuration: %.2fs original -> %.2fs cleaned  (%d spans, %.2fs removed)" % (
        total, duration, len(tl.removed), sum(e - s for s, e in tl.removed)))
    print("Wrote %s%s" % (args.output, ("  and " + args.clean_wav) if args.clean_wav else ""))


if __name__ == "__main__":
    main()
