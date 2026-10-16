"""Print transcript/words.json as numbered lines for picking keep ranges.

Usage: python3 scripts/show_words.py [first_word] [last_word]
Each line: [word index] mm:ss.s  text..., breaking at sentence ends and at pauses.
Pauses of 1 s or more are shown inline as <2.4s>.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_cuts import ROOT, timed  # noqa: E402

GAP = 1.0


def main() -> None:
    words = timed(json.loads((ROOT / "transcript/words.json").read_text())["words"])
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else len(words) - 1
    line, first = [], lo
    for i in range(lo, hi + 1):
        w = words[i]
        if i > lo:
            gap = w["start"] - words[i - 1]["end"]
            if gap >= GAP:
                if line:
                    s = words[first]["start"]
                    print(f"[{first}] {int(s // 60):02d}:{s % 60:04.1f}  {' '.join(line)}")
                print(f"      <{gap:.1f}s>")
                line, first = [], i
        line.append(w["word"])
        if w["word"][-1:] in ".?!" and len(line) >= 12 or len(line) >= 40:
            s = words[first]["start"]
            print(f"[{first}] {int(s // 60):02d}:{s % 60:04.1f}  {' '.join(line)}")
            line, first = [], i + 1
    if line:
        s = words[first]["start"]
        print(f"[{first}] {int(s // 60):02d}:{s % 60:04.1f}  {' '.join(line)}")


if __name__ == "__main__":
    main()
