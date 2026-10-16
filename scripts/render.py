"""Render transcript/cuts.json from the raw clip to ./cut.mp4 and verify it.

Usage: python3 scripts/render.py raw/<clip>
Every cut point snaps to the footage's frame grid. One ffmpeg run: each piece is an
input-seeked copy of the raw, trimmed to an exact frame count, then concatenated
and encoded once (H.264 + AAC, -fps_mode passthrough).
"""
import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
ROOT = Path(__file__).resolve().parent.parent


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:stream_side_data=rotation",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["streams"][0]


def count(path: Path) -> tuple[int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    j = json.loads(out.stdout)
    return int(j["streams"][0]["nb_read_frames"]), float(j["format"]["duration"])


def main() -> None:
    raw = Path(sys.argv[1]).resolve()
    out = ROOT / "cut.mp4"
    v = probe(raw)
    fps = Fraction(v["r_frame_rate"])
    rot = next((abs(int(sd.get("rotation", 0))) for sd in v.get("side_data_list", [])), 0)
    w, h = (v["height"], v["width"]) if rot in (90, 270) else (v["width"], v["height"])
    print(f"raw: {w}x{h} ({'vertical' if h > w else 'horizontal'}), {float(fps):.3f} fps "
          f"({fps}), avg {v['avg_frame_rate']}")

    segs = json.loads((ROOT / "transcript/cuts.json").read_text())["segments"]
    frames = []
    for s in segs:
        a, b = round(Fraction(s["start"]) * fps), round(Fraction(s["end"]) * fps)
        if frames and a < frames[-1][1]:
            a = frames[-1][1]
        if b > a:
            frames.append((a, b))

    args = ["ffmpeg", "-y", "-v", "error", "-stats"]
    graph = []
    for i, (a, b) in enumerate(frames):
        # Seek half a frame early so frame `a` is the first one kept, robust to rounding.
        ss = max(Fraction(0), (a - Fraction(1, 2)) / fps)
        # One decoder thread per input: pieces decode one at a time, and hundreds of
        # multi-threaded 1080p decoders would exhaust memory.
        args += ["-threads", "1", "-ss", f"{float(ss):.6f}", "-i", str(raw)]
        n = b - a
        aoff = a / fps - ss
        graph.append(f"[{i}:v:0]trim=end_frame={n},setpts=PTS-STARTPTS[v{i}];"
                     f"[{i}:a:0]atrim=start={float(aoff):.6f}:duration={float(n / fps):.6f},"
                     f"asetpts=PTS-STARTPTS[a{i}]")
    graph.append("".join(f"[v{i}][a{i}]" for i in range(len(frames)))
                 + f"concat=n={len(frames)}:v=1:a=1[v][a]")
    args += ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-fps_mode", "passthrough",
             "-movflags", "+faststart", str(out)]
    subprocess.run(args, check=True)

    want = sum(b - a for a, b in frames)
    got, dur = count(out)
    print(f"\n{len(frames)} pieces (cuts.json has {len(segs)}):")
    for i, (a, b) in enumerate(frames, 1):
        print(f"  {i:3d}  frames {a}-{b}  = {b - a} frames ({float((b - a) / fps):.3f} s)")
    print(f"expected {want} frames ({float(want / fps):.3f} s); "
          f"cut.mp4 has {got} frames, duration {dur:.3f} s -> "
          f"{'MATCH' if got == want else 'MISMATCH'}")


if __name__ == "__main__":
    main()
