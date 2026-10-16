"""Write transcript/cuts.json as an editable timeline: ./cut.fcpxml.

Usage: python3 scripts/export_fcpxml.py raw/<clip> [path the clip has on the editing PC]
FCPXML 1.9 opens in DaVinci Resolve (File > Import > Timeline) and Final Cut Pro; CapCut
cannot import timelines, so use cut.mp4 there. Pieces snap to the same frame grid
as scripts/render.py, so the timeline matches cut.mp4 frame for frame. If the media
path is not given, the clip is referenced by file name only: relink it after import.
"""
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path, PureWindowsPath
from urllib.parse import quote
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate,channels,sample_rate:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    j = json.loads(out.stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    a = next(s for s in j["streams"] if s["codec_type"] == "audio")
    return {"w": v["width"], "h": v["height"], "fps": Fraction(v["r_frame_rate"]),
            "ch": a["channels"], "rate": int(a["sample_rate"]),
            "dur": float(j["format"]["duration"])}


def frame_ranges(segs, fps):
    # Same snapping as render.py.
    frames = []
    for s in segs:
        a, b = round(Fraction(s["start"]) * fps), round(Fraction(s["end"]) * fps)
        if frames and a < frames[-1][1]:
            a = frames[-1][1]
        if b > a:
            frames.append((a, b))
    return frames


def file_url(p: str) -> str:
    if len(p) > 1 and p[1] == ":":  # Windows drive path
        return "file:///" + quote(PureWindowsPath(p).as_posix(), safe="/:")
    return "file://" + quote(p if p.startswith("/") else "/" + p, safe="/")


def fcpxml(name, url, m, frames, total_src):
    fd = m["fps"].denominator
    num = m["fps"].numerator

    def t(n):  # n frames as an FCPXML rational time
        return f"{n * fd}/{num}s" if n else "0s"

    clips, off = [], 0
    for a, b in frames:
        clips.append(f'     <asset-clip ref="r2" name="{escape(name)}" offset="{t(off)}" '
                     f'start="{t(a)}" duration="{t(b - a)}" format="r1" tcFormat="NDF"/>')
        off += b - a
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
 <resources>
  <format id="r1" frameDuration="{fd}/{num}s" width="{m['w']}" height="{m['h']}"/>
  <asset id="r2" name="{escape(name)}" start="0s" duration="{t(total_src)}" hasVideo="1" hasAudio="1" format="r1" audioSources="1" audioChannels="{m['ch']}" audioRate="{m['rate']}">
   <media-rep kind="original-media" src="{escape(url)}"/>
  </asset>
 </resources>
 <library>
  <event name="{escape(Path(name).stem)} cut">
   <project name="{escape(Path(name).stem)} cut">
    <sequence format="r1" duration="{t(off)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="{m['rate'] // 1000}k">
     <spine>
{chr(10).join(clips)}
     </spine>
    </sequence>
   </project>
  </event>
 </library>
</fcpxml>
"""


def main() -> None:
    raw = Path(sys.argv[1]).resolve()
    pc_path = sys.argv[2] if len(sys.argv) > 2 else raw.name
    m = probe(raw)
    segs = json.loads((ROOT / "transcript/cuts.json").read_text())["segments"]
    frames = frame_ranges(segs, m["fps"])
    total_src = round(Fraction(m["dur"]) * m["fps"])
    url = file_url(pc_path) if ("/" in pc_path or "\\" in pc_path or ":" in pc_path) else pc_path
    name = Path(PureWindowsPath(pc_path).name).name
    (ROOT / "cut.fcpxml").write_text(fcpxml(name, url, m, frames, total_src))
    kept = sum(b - a for a, b in frames)
    print(f"{len(frames)} pieces, {kept} frames ({float(kept / m['fps']) / 60:.2f} min) "
          f"-> cut.fcpxml (media: {url})")


if __name__ == "__main__":
    main()
