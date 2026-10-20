"""Apply transcript/edits.txt and tighten dead air, writing transcript/cuts.json.

Usage: python3 scripts/apply_edits.py
edits.txt lines are `<first word index> | <words to remove>`, or for long cuts
`<first>-<last> | <first words> ... <last words>`. Each is checked against words.json
(ignoring case and punctuation) and the run refuses to write on any mismatch.
`keep <first>-<last>` protects the pauses inside that word range from tightening;
`pause <word> <seconds>` shortens the silence after that word to the given length instead.
transcript/cut_report.txt lists every removed run with its time and length.
Every junction between kept words, whether made by a cut or by a pause longer than
MAX_PAUSE, keeps up to HOLD s of the original silence on each side, never reaching into a
removed word. A pause is only shortened if transcript/audio.wav is quiet across it, so
laughter or speech the transcript missed stays in.
"""
import json
import re
import sys
import wave

import numpy as np

from make_cuts import ROOT, timed

MAX_PAUSE = 1.0   # silences longer than this get shortened
HOLD = 0.3        # silence kept on each side of a junction
WIN = 0.05        # RMS window for the loudness check
LOUD_RUN = 0.3    # this much continuous sound in a pause means "not dead air"


def norm(s: str) -> str:
    return re.sub(r"[^\w']", "", s.lower())


def load_edits(words):
    removed, keep, pauses, errors = set(), set(), {}, []
    for n, line in enumerate((ROOT / "transcript/edits.txt").read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("keep "):
            a, b = map(int, line[5:].split("-"))
            keep.update(range(a, b))
            continue
        if line.startswith("pause "):
            i, secs = line[6:].split()
            pauses[int(i)] = float(secs)
            continue
        idx, phrase = (p.strip() for p in line.split("|", 1))
        if "-" in idx:  # a-b | first words ... last words
            i, j = map(int, idx.split("-"))
            head, tail = ([norm(t) for t in part.split() if norm(t)] for part in phrase.split("..."))
            ok = ([norm(w["word"]) for w in words[i:i + len(head)]] == head
                  and [norm(w["word"]) for w in words[j + 1 - len(tail):j + 1]] == tail)
            want = [norm(w["word"]) for w in words[i:j + 1]]
        else:
            i, want = int(idx), [norm(t) for t in phrase.split() if norm(t)]
            j = i + len(want) - 1
            ok = [norm(w["word"]) for w in words[i:j + 1]] == want
        if not ok:
            errors.append(f"line {n}: {line!r} does not match transcript "
                          f"{' '.join(norm(w['word']) for w in words[max(0, i - 3):i + 6])!r}")
        removed.update(range(i, j + 1))
    if errors:
        sys.exit("edits.txt does not match words.json:\n  " + "\n  ".join(errors))
    return removed, keep, pauses


def loudness():
    with wave.open(str(ROOT / "transcript/audio.wav")) as f:
        rate = f.getframerate()
        a = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)
    hop = int(WIN * rate)
    rms = np.sqrt(np.mean(a[: len(a) // hop * hop].reshape(-1, hop) ** 2, axis=1))
    return rms


def main() -> None:
    words = timed(json.loads((ROOT / "transcript/words.json").read_text())["words"])
    removed, keep, pauses = load_edits(words)
    rms = loudness()
    speech = np.median(rms[[int(w["start"] / WIN) for w in words if w["end"] - w["start"] > 0.1]])
    loud = rms > speech * 0.1  # ~20 dB under typical speech

    def has_sound(t0, t1):
        run = 0
        for x in loud[int(t0 / WIN):int(t1 / WIN)]:
            run = run + 1 if x else 0
            if run * WIN >= LOUD_RUN:
                return True
        return False

    kept = [i for i in range(len(words)) if i not in removed]
    pieces, kept_loud = [[kept[0], kept[0]]], 0
    for p, n in zip(kept, kept[1:]):
        gap = words[n]["start"] - words[p]["end"]
        if n == p + 1 and gap > MAX_PAUSE and has_sound(words[p]["end"], words[n]["start"]):
            kept_loud += 1
        if p in pauses:
            split = gap > pauses[p]
        else:
            split = gap > MAX_PAUSE and p not in keep and not has_sound(words[p]["end"], words[n]["start"])
        if n != p + 1 or split:
            pieces.append([n, n])
        else:
            pieces[-1][1] = n

    segs = []
    for a, b in pieces:
        before = words[a]["start"] - (words[a - 1]["end"] if a > 0 else 0.0)
        after = (words[b + 1]["start"] if b + 1 < len(words) else words[b]["end"] + 1.0) - words[b]["end"]
        hold_after = HOLD if b + 1 < len(words) else 1.0  # let the last word ring out
        hold_after = pauses[b] / 2 if b in pauses else hold_after
        hold_before = pauses[a - 1] / 2 if a - 1 in pauses else HOLD
        segs.append({"start": round(words[a]["start"] - min(before, hold_before), 3),
                     "end": round(words[b]["end"] + min(after, hold_after), 3),
                     "text": " ".join(w["word"] for w in words[a:b + 1])})

    runs, rep = [], []
    for i in sorted(removed):
        if runs and runs[-1][1] == i - 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    for a, b in runs:
        t, d = words[a]["start"], words[b]["end"] - words[a]["start"]
        rep.append(f"{int(t // 60):02d}:{t % 60:04.1f} {d:5.1f}s [{a}-{b}] "
                   + " ".join(w["word"] for w in words[a:b + 1]))
    (ROOT / "transcript/cut_report.txt").write_text("\n".join(rep) + "\n")

    (ROOT / "transcript/cuts.json").write_text(
        json.dumps({"segments": segs}, indent=1, ensure_ascii=False))
    total = words[-1]["end"]
    kept_s = sum(s["end"] - s["start"] for s in segs)
    print(f"{len(removed)} words removed, {len(segs)} pieces, "
          f"{kept_loud} long pauses left whole (sound in them)")
    print(f"{total / 60:.1f} min -> {kept_s / 60:.1f} min ({(total - kept_s) / 60:.1f} min cut)")


if __name__ == "__main__":
    main()
