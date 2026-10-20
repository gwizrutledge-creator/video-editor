"""Assemble the full-episode timeline: cold open, title card, then the edited conversation.

Usage: python3 scripts/build_episode.py <episode.json>
episode.json keys:
  source, out, views (path to a views JSON), card, card_dur
  cold_open  [{"clip": [s, e], "view": v, "text": {...}?}, ...]   source times
  punch_ins  [{"range": [s, e], "view": v}, ...]   conversation stretches shown as close-ups
  texts      extra timed text in source time: [{"src": [s, e], ...drawtext keys}]
  chapters   [["mm:ss", "title"], ...] in source time
Writes <out stem>_timeline.json (for render_timeline.py) and prints the chapters re-timed to
the exported video. The conversation comes from transcript/cuts.json.
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_cuts import ROOT  # noqa: E402
from render_timeline import fps_of  # noqa: E402


def mmss(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def secs(s: str) -> float:
    parts = [float(p) for p in s.split(":")]
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts)))


def main() -> None:
    ep = json.loads(Path(sys.argv[1]).read_text())
    fps = fps_of(ROOT / ep["source"])
    items, texts, t_out = [], [], Fraction(0)

    def add_clip(s, e, view, text=None):
        nonlocal t_out
        a, b = round(Fraction(s) * fps), round(Fraction(e) * fps)
        if b <= a:
            return
        if text:
            texts.append(dict(text, start=round(float(t_out) + text.get("delay", 0), 3),
                              end=round(float(t_out + Fraction(b - a) / fps), 3)))
        items.append({"clip": [s, e], "view": view})
        t_out += Fraction(b - a) / fps

    for c in ep["cold_open"]:
        add_clip(*c["clip"], c["view"], c.get("text"))
    cold_len = t_out
    items.append({"card": ep["card"], "dur": ep["card_dur"]})
    t_out += Fraction(round(Fraction(ep["card_dur"]) * fps)) / fps

    # Conversation: split cut pieces at punch-in boundaries; remember source->output mapping.
    punches = sorted(ep.get("punch_ins", []), key=lambda p: p["range"][0])
    mapping = []
    for seg in json.loads((ROOT / "transcript/cuts.json").read_text())["segments"]:
        s, e = seg["start"], seg["end"]
        cuts = sorted({s, e, *[x for p in punches for x in p["range"] if s < x < e]})
        for a, b in zip(cuts, cuts[1:]):
            view = next((p["view"] for p in punches if p["range"][0] <= a and b <= p["range"][1]), "two")
            mapping.append((a, b, float(t_out)))
            add_clip(a, b, view)

    def to_out(t):
        for a, b, o in mapping:
            if t < a:
                return o
            if t < b:
                return o + t - a
        return float(t_out)

    for x in ep.get("texts", []):
        texts.append({k: v for k, v in x.items() if k != "src"}
                     | {"start": round(to_out(x["src"][0]), 3), "end": round(to_out(x["src"][1]), 3)})

    views = json.loads((ROOT / ep["views"]).read_text())
    tl = {"source": ep["source"], "out": ep["out"], "canvas": [1920, 1080], "views": views,
          "items": items, "texts": texts, "loudness": ep.get("loudness", -14)}
    out_tl = ROOT / (str(Path(ep["out"]).with_suffix("")) + "_timeline.json")
    out_tl.write_text(json.dumps(tl, indent=1))

    print(f"cold open {float(cold_len):.1f} s + card {ep['card_dur']} s; "
          f"total {mmss(float(t_out))} ({float(t_out):.2f} s); {len(items)} items -> {out_tl.name}")
    chapters = []
    for i, (ts, title) in enumerate(ep.get("chapters", [])):
        chapters.append(f"{'00:00' if i == 0 else mmss(to_out(secs(ts)))} {title}")
    if chapters:
        print("\n".join(chapters))
        (ROOT / ep["chapters_out"]).write_text("\n".join(chapters) + "\n")


if __name__ == "__main__":
    main()
