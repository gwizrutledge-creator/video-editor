"""Fill in "faces" for each Short in edit/plan.json so every 9:16 crop is centred on the face.

Usage: ~/.cache/video-editor/tools-venv/bin/python scripts/find_faces.py edit/<ep>/plan.json
For each layout a Short passes through (the plan's layout map), samples frames, finds the largest
face (OpenCV Haar cascade) and stores the median centre: x in the speaker's tile for the two-up,
[x, y] in the full frame for a full-screen punch-in.
"""
import json
import statistics
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from package import geometry, layout_pieces  # noqa: E402

CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def frame(raw: Path, t: float) -> np.ndarray:
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(raw),
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(1080, 1920)


def main() -> None:
    plan_path = Path(sys.argv[1]).resolve()
    plan = json.loads(plan_path.read_text())
    raw = ROOT / plan["source"]
    geo = geometry(plan)
    for s in plan.get("shorts", []):
        found = {}
        for a, b, lay in layout_pieces(s["in"], s["out"], Fraction(30), plan["layout"]):
            pts = []
            for k in range(7):
                img = frame(raw, a + (b - a) * (k + 0.5) / 7)
                if lay == "2up":
                    (x0, x1), top = geo["tiles"][s["speaker"]], geo["tile_top"]
                    img = img[top:geo["crop_bottom"][s["speaker"]], x0:x1]
                    ox, oy = x0, top
                else:
                    ox = oy = 0
                faces = CASCADE.detectMultiScale(img, 1.1, 5, minSize=(80, 80))
                if len(faces):
                    fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                    pts.append((ox + fx + fw / 2, oy + fy + fh / 2))
            if pts:
                x = round(statistics.median(p[0] for p in pts))
                y = round(statistics.median(p[1] for p in pts))
                found.setdefault(lay, x if lay == "2up" else [x, y])
            print(f"{s['name']} {lay:4s} {a:8.2f}-{b:8.2f}: {found.get(lay)} ({len(pts)}/7)")
        s["faces"] = found
    plan_path.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
