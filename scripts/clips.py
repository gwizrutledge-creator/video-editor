"""Render vertical (1080x1920) social clips with burned-in word-by-word captions.

Usage: python3 scripts/clips.py raw/<clip> [clips.json]
clips.json (default transcript/clips.json):
  {"clips": [{"name": "slug", "first": i, "last": j, "crop_x": 0.5}, ...]}
first/last are inclusive indexes into words.json "words"; crop_x (0-1, default 0.5) is where
the 9:16 window is centred across a wider frame. Writes clips/NN_slug.mp4, each cut on the
footage's frame grid (same seek + trim as render.py) and checked for its frame count.
"""
import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from make_cuts import POST, PRE, timed
from render import count, probe

os.environ.setdefault("PYTHONUTF8", "1")
ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1920
MAX_WORDS, MAX_CHARS, GAP = 3, 16, 0.5
HOLD = 0.4  # how long the last caption of a run stays up after its word ends

ASS_HEAD = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Inter Black,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,0,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
HILITE = r"{\c&H0000D4FF&}"  # yellow, ASS colours are &HBBGGRR


def ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def clean(word: str) -> str:
    return word.strip().strip(",.;:\"").replace("{", "").replace("}", "").replace("\\", "").upper()


def captions(words: list[dict], t0: float, dur: float) -> str:
    # Group words into short runs, breaking at sentence ends and pauses.
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        text = " ".join(clean(x["word"]) for x in cur)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (nxt is None or len(cur) >= MAX_WORDS or len(text) >= MAX_CHARS
                or w["word"].rstrip()[-1:] in ".?!" or nxt["start"] - w["end"] > GAP):
            groups.append(cur)
            cur = []

    lines = []
    for g, grp in enumerate(groups):
        g_end = grp[-1]["end"] + HOLD
        if g + 1 < len(groups):
            g_end = min(g_end, groups[g + 1][0]["start"])
        for k, w in enumerate(grp):
            s = grp[0]["start"] if k == 0 else w["start"]
            e = grp[k + 1]["start"] if k + 1 < len(grp) else g_end
            s, e = max(0.0, s - t0), min(dur, e - t0)
            if e <= s:
                continue
            text = " ".join(HILITE + clean(x["word"]) + r"{\r}" if j == k else clean(x["word"])
                            for j, x in enumerate(grp))
            lines.append(f"Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,{text}")
    return ASS_HEAD + "\n".join(lines) + "\n"


def main() -> None:
    raw = Path(sys.argv[1]).resolve()
    spec = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "transcript/clips.json"
    clips = json.loads(spec.read_text())["clips"]
    words = timed(json.loads((ROOT / "transcript/words.json").read_text())["words"])
    outdir = ROOT / "clips"
    outdir.mkdir(exist_ok=True)

    v = probe(raw)
    fps = Fraction(v["r_frame_rate"])
    rot = next((abs(int(sd.get("rotation", 0))) for sd in v.get("side_data_list", [])), 0)
    sw, sh = (v["height"], v["width"]) if rot in (90, 270) else (v["width"], v["height"])
    print(f"raw: {sw}x{sh}, {float(fps):.3f} fps")

    report = []
    for n, c in enumerate(clips, 1):
        a_i, b_i = c["first"], c["last"]
        start = max(words[a_i]["start"] - PRE, words[a_i - 1]["end"] if a_i > 0 else 0.0)
        end = words[b_i]["end"] + POST
        if b_i + 1 < len(words):
            end = min(end, max(words[b_i + 1]["start"], words[b_i]["end"]))
        a, b = round(Fraction(start) * fps), round(Fraction(end) * fps)
        nf = b - a
        t0, dur = float(a / fps), float(nf / fps)

        out = outdir / f"{n:02d}_{c['name']}.mp4"
        ass = outdir / f"{n:02d}_{c['name']}.ass"
        ass.write_text(captions(words[a_i:b_i + 1], t0, dur), encoding="utf-8")

        if sw * 16 > sh * 9:  # wider than 9:16: crop a vertical window, then scale
            cw = round(sh * 9 / 16) // 2 * 2
            x = min(max(0, round(c.get("crop_x", 0.5) * sw - cw / 2)), sw - cw)
            geo = f"crop={cw}:{sh}:{x}:0,scale={W}:{H}:flags=lanczos"
        else:
            geo = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}"
        ss = max(Fraction(0), (a - Fraction(1, 2)) / fps)
        aoff = a / fps - ss
        assarg = str(ass).replace("\\", "/").replace(":", r"\:")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{float(ss):.6f}", "-i", str(raw),
             "-vf", f"trim=end_frame={nf},setpts=PTS-STARTPTS,{geo},setsar=1,ass='{assarg}'",
             "-af", f"atrim=start={float(aoff):.6f}:duration={dur:.6f},asetpts=PTS-STARTPTS,"
                    "loudnorm=I=-14:TP=-1.5:LRA=11",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-fps_mode", "passthrough",
             "-movflags", "+faststart", str(out)],
            check=True)
        got, odur = count(out)
        ok = "MATCH" if got == nf else "MISMATCH"
        report.append(f"  {out.name}: {dur:5.1f} s, {nf} frames, file has {got} -> {ok}")
        print(report[-1], flush=True)

    print(f"\n{len(clips)} clips in {outdir}:")
    print("\n".join(report))


if __name__ == "__main__":
    main()
