"""Turn kept word ranges into padded transcript/cuts.json.

Usage: python3 scripts/make_cuts.py keep.json
keep.json: [[first_word_index, last_word_index], ...] (inclusive, indexes into words.json "words").
Pads 0.08 s before and 0.12 s after each piece, never into a cut word, and splits
the gap between kept pieces that sit closer than the pad so nothing overlaps.
"""
import json
import sys
from pathlib import Path

PRE, POST = 0.08, 0.12
ROOT = Path(__file__).resolve().parent.parent


def timed(words):
    # Some tokens (numbers, symbols) come back without times: borrow from neighbours.
    out = []
    for i, w in enumerate(words):
        s, e = w.get("start"), w.get("end")
        if s is None:
            s = next((p["end"] for p in reversed(words[:i]) if "end" in p), 0.0)
        if e is None:
            e = next((n["start"] for n in words[i + 1:] if "start" in n), s)
        out.append({"word": w["word"], "start": s, "end": max(e, s)})
    return out


def main() -> None:
    data = json.loads((ROOT / "transcript/words.json").read_text())
    words = timed(data["words"])
    ranges = json.loads(Path(sys.argv[1]).read_text())

    segs = []
    for a, b in ranges:
        start = words[a]["start"] - PRE
        end = words[b]["end"] + POST
        start = max(start, words[a - 1]["end"] if a > 0 else 0.0)
        if b + 1 < len(words):
            end = min(end, words[b + 1]["start"])
        segs.append({"start": start, "end": end, "first": a, "last": b,
                     "text": " ".join(w["word"] for w in words[a:b + 1])})

    for prev, nxt in zip(segs, segs[1:]):
        if prev["end"] > nxt["start"]:
            mid = (words[prev["last"]]["end"] + words[nxt["first"]]["start"]) / 2
            prev["end"], nxt["start"] = mid, mid

    cuts = {"segments": [{"start": round(s["start"], 3), "end": round(s["end"], 3),
                          "text": s["text"]} for s in segs]}
    (ROOT / "transcript/cuts.json").write_text(json.dumps(cuts, indent=1, ensure_ascii=False))
    total = sum(s["end"] - s["start"] for s in cuts["segments"])
    print(f"{len(segs)} pieces, {total:.2f} s kept")


if __name__ == "__main__":
    main()
