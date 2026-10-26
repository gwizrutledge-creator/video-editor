"""Write the reel source log (markdown tables) from reel specs and the window offsets.

Usage: python3 scripts/reel_log.py <project dir> <spec.json>...
Reads <project>/sources.json ({clip stem: {title, url, drive_id, guest}}),
<project>/window_offsets.json (clip start in the source, seconds) and the clips'
.words.json; prints one table per spec: reel time, episode, speaker, source in/out, words.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def tc(s):
    m, s = divmod(s, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m:02d}:{s:04.1f}"


def main():
    proj = ROOT / sys.argv[1]
    meta = json.loads((proj / "sources.json").read_text())
    off = json.loads((proj / "window_offsets.json").read_text())
    for f in sys.argv[2:]:
        spec = json.loads((ROOT / f).read_text())
        print(f"\n### `{spec['out']}`\n")
        print("| Reel time | Episode | Who speaks | Source in–out (±0.3 s) | Words in the piece |")
        print("|---|---|---|---|---|")
        t = 0.0
        for it in spec["items"]:
            d = it.get("dur", it.get("out", 0) - it.get("in", 0))
            if "card" in it:
                print(f"| {tc(t)}–{tc(t + d)} | End card | — | — | Help G-Wiz become Top Host. / Vote for Gregory Rutledge. / tophost.org/2026/gregory-rutledge |")
            else:
                n = Path(it["src"]).stem
                words = json.loads((ROOT / it["src"]).with_suffix(".words.json").read_text())["words"]
                text = " ".join(w["word"] for w in words
                                if "start" in w and it["in"] - 0.05 <= w["start"] < it["out"] - 0.05)
                a, b = off[n] + it["in"], off[n] + it["out"]
                print(f"| {tc(t)}–{tc(t + d)} | {meta[n]['guest']} | {it.get('speaker', '?')} | "
                      f"{tc(a)}–{tc(b)} | “{text}” |")
            t += d


if __name__ == "__main__":
    main()
