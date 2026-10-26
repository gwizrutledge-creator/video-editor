"""Map which layout is on screen through the raw episode: the two-up ("2up") or a
full-screen punch-in on Jason ("J") or Greg ("G"). Writes edit/layout.json as frame-exact runs.

Usage: ~/.cache/video-editor/tools-venv/bin/python scripts/layout.py raw/<clip>
Pass 1 classifies 10 frames a second; pass 2 decodes every frame around each change.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
W, H = 96, 54


def frames(raw: Path, start: float = 0.0, dur: float | None = None, fps: str = "10"):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", str(raw), "-an", "-vf",
            (f"fps={fps}," if fps else "") + f"scale={W}:{H}:flags=area,format=gray",
            "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, H, W).astype(int)


def classify(f: np.ndarray) -> str:
    # Two-up: black band above the tiles and a black gap between them.
    if f[2:12, 10:86].mean() < 30 and f[18:38, 47:48].mean() < 30:
        return "2up"
    # Jason's punch-in is a pale wall; Greg's room is darker.
    return "J" if f[5:50, 5:91].mean() > 150 else "G"


def main() -> None:
    raw = Path(sys.argv[1]).resolve()
    labels = [classify(f) for f in frames(raw)]
    runs, s = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[s]:
            runs.append([s, i, labels[s]])
            s = i
    # Drop flickers shorter than half a second (fades through black between shots).
    runs = [r for r in runs if r[1] - r[0] >= 5 or r is runs[0]]
    merged = []
    for r in runs:
        if merged and merged[-1][2] == r[2]:
            merged[-1][1] = r[1]
        else:
            merged.append(r)

    fps = 30
    out = []
    for k, (a, b, lab) in enumerate(merged):
        start = 0 if k == 0 else out[-1]["end_frame"]
        if k + 1 < len(merged):
            # Refine the change to the exact frame: first frame that matches the next label.
            t0 = max(0.0, b / 10 - 0.6)
            fine = frames(raw, t0, 1.2, fps="")
            nxt = merged[k + 1][2]
            first = next(i for i, f in enumerate(fine) if classify(f) == nxt)
            end = round(t0 * fps) + first
        else:
            end = None
        out.append({"start_frame": start, "end_frame": end, "layout": lab})
    out[-1]["end_frame"] = 10 ** 9
    (ROOT / "edit").mkdir(exist_ok=True)
    (ROOT / "edit/layout.json").write_text(json.dumps({"fps": fps, "runs": out}, indent=1) + "\n")
    for r in out:
        print(f"{r['start_frame'] / fps:9.3f} - {min(r['end_frame'], 99999999) / fps:9.3f}  {r['layout']}")


if __name__ == "__main__":
    main()
