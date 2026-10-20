"""Burned-in caption track (.ass) for a timeline's clips, from transcript/words.json.

Usage: python3 scripts/make_captions.py <timeline.json> <out.ass> [center_y]
Words are grouped into short phrases (at most 3 words / 18 characters, breaking at
punctuation and pauses); the phrase stays on screen while each word lights up in brand gold
as it is spoken. Times follow the timeline's frame-snapped clips, so captions match the cut.
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_cuts import ROOT, timed  # noqa: E402
from render_timeline import fps_of  # noqa: E402

GOLD = "&H003CB1F2&"  # #F2B13C in ASS BGR order
MAX_WORDS, MAX_CHARS, BREAK_GAP = 3, 18, 0.35


def ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def clean(w: str) -> str:
    return w.strip().rstrip(",.;:").replace("{", "").replace("}", "")


def main() -> None:
    tl = json.loads(Path(sys.argv[1]).read_text())
    W, H = tl["canvas"]
    cy = int(sys.argv[3]) if len(sys.argv) > 3 else H // 2
    fps = fps_of(ROOT / tl["source"])
    words = timed(json.loads((ROOT / "transcript/words.json").read_text())["words"])

    # Map every spoken word inside a clip to output time.
    out, off = [], Fraction(0)
    for it in tl["items"]:
        if "card" in it:
            off += round(Fraction(it["dur"]) * fps) / fps
            continue
        a, b = (round(Fraction(t) * fps) / fps for t in it["clip"])
        for w in words:
            if w["start"] >= a - 0.02 and w["end"] <= b + 0.05:
                out.append({"word": clean(w["word"]), "raw": w["word"],
                            "start": float(off + Fraction(w["start"]) - a),
                            "end": float(off + min(Fraction(w["end"]), b) - a)})
        off += b - a

    phrases, cur = [], []
    for i, w in enumerate(out):
        if not w["word"]:
            continue
        cur.append(w)
        nxt = out[i + 1] if i + 1 < len(out) else None
        text = " ".join(x["word"] for x in cur)
        if (nxt is None or len(cur) >= MAX_WORDS or w["raw"][-1:] in ".,?!;:"
                or nxt["start"] - w["end"] > BREAK_GAP
                or len(text) + 1 + len(nxt["word"]) > MAX_CHARS):
            phrases.append(cur)
            cur = []

    lines = []
    for k, ph in enumerate(phrases):
        end_ph = ph[-1]["end"] + 0.12
        if k + 1 < len(phrases):
            end_ph = min(end_ph + 0.25, phrases[k + 1][0]["start"])
        for i, w in enumerate(ph):
            t0 = w["start"] if i else ph[0]["start"]
            t1 = ph[i + 1]["start"] if i + 1 < len(ph) else end_ph
            text = " ".join((f"{{\\c{GOLD}}}{x['word']}{{\\c&H00FFFFFF&}}" if j == i else x["word"])
                            for j, x in enumerate(ph))
            lines.append(f"Dialogue: 0,{ts(t0)},{ts(t1)},Cap,,0,0,0,,{{\\pos({W // 2},{cy})}}{text}")

    Path(sys.argv[2]).write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Inter Display Black,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,2,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(lines) + "\n")
    print(f"{len(out)} words, {len(phrases)} caption phrases -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
