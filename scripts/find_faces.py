"""Fill in face_x for each Short in edit/plan.json so its 9:16 crop is centred on the face.

Usage: ~/.cache/video-editor/tools-venv/bin/python scripts/find_faces.py edit/plan.json
Samples 9 frames inside each Short, finds the largest face in the speaker's camera tile
(OpenCV Haar cascade) and stores the median face centre (x in full-frame pixels).
"""
import json
import statistics
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from package import TILE_CROP_BOTTOM, TILE_TOP, TILES  # noqa: E402

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
    for s in plan.get("shorts", []):
        x0, x1 = TILES[s["speaker"]]
        xs = []
        for k in range(9):
            t = s["in"] + (s["out"] - s["in"]) * (k + 0.5) / 9
            tile = frame(raw, t)[TILE_TOP:TILE_CROP_BOTTOM, x0:x1]
            faces = CASCADE.detectMultiScale(tile, 1.1, 5, minSize=(80, 80))
            if len(faces):
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                xs.append(x0 + fx + fw / 2)
        if xs:
            s["face_x"] = round(statistics.median(xs))
        print(f"{s['name']}: {s['speaker']} face_x={s.get('face_x')} ({len(xs)}/9 frames)")
    plan_path.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
