"""Build a vertical Short: stacked layout, title band, word captions, closing question.

Usage: python3 scripts/build_short.py <short.json>
short.json keys: source, out, workdir (default projects/ep12), views (9:16 views JSON),
  ranges [[s, e], ...] in source time (intersected with transcript/cuts.json, so the Short
  gets the episode's cuts and tightened pauses),
  title ["line", ...] (top band while the Short plays), question ["line", ...] (replaces the
  title for the last question_dur seconds), question_dur.
Writes <out stem>_timeline.json and <out stem>.ass, ready for render_timeline.py.
"""
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_cuts import ROOT  # noqa: E402
from render_timeline import fps_of  # noqa: E402

BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
GOLD = "0xF2B13C"
CAPTION_Y = 955  # centre of the band between the two panels


def main() -> None:
    sh = json.loads(Path(sys.argv[1]).read_text())
    fps = fps_of(ROOT / sh["source"])
    cuts = json.loads((ROOT / "transcript/cuts.json").read_text())["segments"]
    sh["clips"] = [[round(max(a, c["start"]), 3), round(min(b, c["end"]), 3)]
                   for a, b in sh["ranges"] for c in cuts if c["start"] < b and c["end"] > a]
    work = sh.get("workdir", "projects/ep12")
    stem = f"{work}/{Path(sh['out']).stem}"
    total = sum(Fraction(round(Fraction(b) * fps) - round(Fraction(a) * fps)) / fps
                for a, b in sh["clips"])
    q0 = round(float(total) - sh["question_dur"], 3)
    tdir = ROOT / work / "text"
    tdir.mkdir(exist_ok=True)

    texts = [{"textfile": "", "start": 0, "end": round(float(total), 3), "font": BOLD, "size": 30,
              "color": GOLD, "x": "(w-text_w)/2", "y": "70", "_t": "THE GREATER JOURNEY"}]
    for lines, start, end, color in ((sh["title"], 0, q0, "white"),
                                     (sh["question"], q0, round(float(total), 3), GOLD)):
        y0 = 175 - 34 * (len(lines) - 1)
        for i, line in enumerate(lines):
            texts.append({"textfile": "", "start": start, "end": end, "font": BLACK, "size": 58,
                          "color": color, "x": "(w-text_w)/2", "y": str(y0 + 68 * i), "_t": line,
                          "fade": 0.25 if start else 0})
    for i, t in enumerate(texts):
        f = tdir / f"{Path(stem).name}_{i}.txt"
        f.write_text(t.pop("_t"))
        t["textfile"] = str(f.relative_to(ROOT))
        if "fade" in t and not t["fade"]:
            t.pop("fade")

    tl = {"source": sh["source"], "out": sh["out"], "canvas": [1080, 1920],
          "views": json.loads((ROOT / sh["views"]).read_text()),
          "items": [{"clip": c, "view": "stack"} for c in sh["clips"]],
          "texts": texts, "ass": f"{stem}.ass", "loudness": -14}
    tl_path = ROOT / f"{stem}_timeline.json"
    tl_path.write_text(json.dumps(tl, indent=1))
    subprocess.run([sys.executable, str(ROOT / "scripts/make_captions.py"), str(tl_path),
                    str(ROOT / f"{stem}.ass"), str(CAPTION_Y)], check=True)
    print(f"{Path(sh['out']).name}: {float(total):.1f} s, {len(sh['clips'])} clips -> {tl_path.name}")


if __name__ == "__main__":
    main()
