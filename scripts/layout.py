"""Map which layout is on screen through an episode: the two-up ("2up") or anything else,
like a full-screen punch-in or the channel intro ("full"). Writes the plan's layout map
(e.g. edit/ep13/layout.json) as frame-exact runs; a new "full" run starts at every shot change.

Usage: ~/.cache/video-editor/tools-venv/bin/python scripts/layout.py edit/<ep>/plan.json
Pass 1 classifies 10 frames a second; pass 2 decodes every frame around each change.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from package import geometry  # noqa: E402

W, H = 192, 108  # one pixel per 10x10 block of the 1920x1080 frame
SHOT_CHANGE = 30  # mean grey-level jump between samples that starts a new "full" run


def frames(raw: Path, start: float = 0.0, dur: float | None = None, fps: str = "10"):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", str(raw), "-an", "-vf",
            (f"fps={fps}," if fps else "") + f"scale={W}:{H}:flags=area,format=gray",
            "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, H, W).astype(int)


def classifier(geo: dict):
    """Two-up: a dark band above the tiles (clear of the corner logo) and a dark gap between
    the tiles. Anything else is "full"."""
    left, right = sorted(geo["tiles"].values())
    c0, c1 = left[1] // 10 + 1, right[0] // 10
    r0, r1 = geo["tile_top"] // 10 + 2, 72

    def classify(f: np.ndarray) -> str:
        if f[4:geo["tile_top"] // 10 - 4, 20:172].mean() < 30 and f[r0:r1, c0:c1].mean() < 30:
            return "2up"
        return "full"
    return classify


def main() -> None:
    plan = json.loads(Path(sys.argv[1]).read_text())
    raw = (ROOT / plan["source"]).resolve()
    classify = classifier(geometry(plan))
    fr = frames(raw)
    labels = [classify(f) for f in fr]
    cut = [False] + [bool(np.abs(fr[i] - fr[i - 1]).mean() > SHOT_CHANGE) for i in range(1, len(fr))]

    runs, s = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[s] or (labels[i] == "full" and cut[i]):
            runs.append([s, i, labels[s]])
            s = i
    # Drop label flickers shorter than half a second (fades through black between shots).
    keep = [r for k, r in enumerate(runs)
            if r[1] - r[0] >= 5 or k == 0 or r[2] == "full" and runs[k - 1][2] == "full"]
    merged = []
    for r in keep:
        if merged and merged[-1][2] == r[2] == "2up":
            merged[-1][1] = r[1]
        else:
            merged.append(r)

    fps = 30
    out = []
    for k, (a, b, lab) in enumerate(merged):
        start = 0 if k == 0 else out[-1]["end_frame"]
        end = 10 ** 9
        if k + 1 < len(merged):
            # Refine the change to the exact frame: the first frame with the next label, or
            # for a cut between two "full" shots, the frame after the biggest jump.
            t0 = max(0.0, b / 10 - 0.6)
            fine = frames(raw, t0, 1.2, fps="")
            nxt = merged[k + 1][2]
            if nxt != lab:
                first = next((i for i, f in enumerate(fine) if classify(f) == nxt), len(fine) // 2)
            else:
                first = int(np.argmax([np.abs(fine[i] - fine[i - 1]).mean()
                                       for i in range(1, len(fine))])) + 1
            end = max(start + 1, round(t0 * fps) + first)
        out.append({"start_frame": start, "end_frame": end, "layout": lab})
    dest = ROOT / plan["layout"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"fps": fps, "runs": out}, indent=1) + "\n")
    for r in out:
        if r["layout"] == "full" or r is out[0]:
            print(f"{r['start_frame'] / fps:9.3f} - {min(r['end_frame'], 99999999) / fps:9.3f}  {r['layout']}")
    print(f"{len(out)} runs, {sum(r['layout'] == '2up' for r in out)} two-up")


if __name__ == "__main__":
    main()
