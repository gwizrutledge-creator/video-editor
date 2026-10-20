"""Render a timeline JSON (clips with layouts, title cards, text, captions) to an MP4.

Usage: python3 scripts/render_timeline.py <timeline.json>

Timeline keys:
  source    raw clip all "clip" items cut from
  out       output path
  canvas    [width, height]
  views     {name: ffmpeg filter chain} turning the raw frame into a canvas-sized frame;
            a chain may use labels [in] and [out] (multi-stream) or be a plain chain
  items     ordered list of {"clip": [start, end], "view": name}
            or {"card": image.png, "dur": seconds}
  texts     optional [{"textfile": path, "start": s, "end": s, "font": path, "size": px,
            "color": "white", "x": expr, "y": expr}], in output-timeline seconds
  ass       optional .ass subtitle file in output-timeline time, burned in last
  loudness  optional target integrated LUFS (default -14, YouTube)

Every clip snaps to the source frame grid as in render.py. Speech gets a gentle high-pass,
light denoise and two-pass loudnorm; the output frame count is checked against the timeline.
"""
import json
import os
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
ROOT = Path(__file__).resolve().parent.parent
AUDIO_FX = "highpass=f=70,afftdn=nr=8:nf=-45"


def fps_of(path: Path) -> Fraction:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return Fraction(out.stdout.strip())


def segments(tl, fps):
    """Group items into runs of consecutive same-view clips and cards, in frames."""
    segs, last_end = [], None
    for it in tl["items"]:
        if "card" in it:
            segs.append({"card": str(ROOT / it["card"]), "frames": round(Fraction(it["dur"]) * fps)})
            last_end = None
            continue
        a, b = (round(Fraction(t) * fps) for t in it["clip"])
        if last_end is not None and a < last_end and segs and segs[-1].get("view") == it["view"]:
            a = last_end  # never repeat a frame between abutting pieces of one run
        if b <= a:
            continue
        if segs and segs[-1].get("view") == it["view"]:
            segs[-1]["pieces"].append((a, b))
        else:
            segs.append({"view": it["view"], "pieces": [(a, b)]})
        last_end = b
    return segs


def build(tl, fps, video=True, loud=None):
    src = str(ROOT / tl["source"])
    W, H = tl["canvas"]
    # The measuring pass needs info-level logs: that is where loudnorm prints its JSON.
    log = ["-v", "error", "-stats"] if video else ["-hide_banner", "-nostats", "-v", "info"]
    args, graph, n_in, outs = ["ffmpeg", "-y", *log], [], 0, []
    for k, s in enumerate(segs := segments(tl, fps)):
        if "card" in s:
            dur = float(s["frames"] / fps)
            if video:
                args += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.6f}", "-i", s["card"]]
                graph.append(f"[{n_in}:v]scale={W}:{H},setsar=1,format=yuv420p,"
                             f"trim=end_frame={s['frames']},setpts=PTS-STARTPTS[sv{k}]")
                n_in += 1
            args += ["-f", "lavfi", "-t", f"{dur:.6f}", "-i", "anullsrc=r=48000:cl=stereo"]
            graph.append(f"[{n_in}:a]atrim=duration={dur:.6f},asetpts=PTS-STARTPTS[sa{k}]")
            n_in += 1
            outs.append(k)
            continue
        labels = []
        for j, (a, b) in enumerate(s["pieces"]):
            ss = max(Fraction(0), (a - Fraction(1, 2)) / fps)
            args += ["-threads", "1", "-ss", f"{float(ss):.6f}", "-i", src]
            n, aoff = b - a, a / fps - ss
            p = f"{k}_{j}"
            if video:
                graph.append(f"[{n_in}:v:0]trim=end_frame={n},setpts=PTS-STARTPTS[v{p}]")
            graph.append(f"[{n_in}:a:0]atrim=start={float(aoff):.6f}:duration={float(n / fps):.6f},"
                         f"asetpts=PTS-STARTPTS[a{p}]")
            labels.append(p)
            n_in += 1
        m = len(labels)
        if video:
            graph.append("".join(f"[v{p}][a{p}]" for p in labels)
                         + f"concat=n={m}:v=1:a=1[rv{k}][sa{k}]")
            chain = tl["views"][s["view"]]
            if "[in]" in chain:  # multi-stream view: give its inner labels a per-run prefix
                names = {"in": f"rv{k}", "out": f"vw{k}"}
                graph.append(re.sub(r"\[(\w+)\]",
                                    lambda mm: f"[{names.get(mm[1], f'k{k}_{mm[1]}')}]", chain))
            else:
                graph.append(f"[rv{k}]{chain}[vw{k}]")
            graph.append(f"[vw{k}]scale={W}:{H},setsar=1,format=yuv420p[sv{k}]")
        else:
            graph.append("".join(f"[a{p}]" for p in labels) + f"concat=n={m}:v=0:a=1[sa{k}]")
        outs.append(k)

    pairs = "".join((f"[sv{k}]" if video else "") + f"[sa{k}]" for k in outs)
    graph.append(f"{pairs}concat=n={len(outs)}:v={1 if video else 0}:a=1"
                 + ("[cv]" if video else "") + "[ca]")
    target = tl.get("loudness", -14)
    ln = f"loudnorm=I={target}:TP=-1.5:LRA=11"
    if loud and loud["input_i"] == "-inf":  # silence only: nothing to normalize
        ln = "anull"
    elif loud:
        ln += (f":measured_I={loud['input_i']}:measured_TP={loud['input_tp']}"
               f":measured_LRA={loud['input_lra']}:measured_thresh={loud['input_thresh']}"
               f":offset={loud['target_offset']}:linear=true")
    else:
        ln += ":print_format=json"
    graph.append(f"[ca]aformat=sample_rates=48000:channel_layouts=stereo,{AUDIO_FX},{ln},"
                 f"aresample=48000[a]")
    if video:
        chain = "[cv]"
        for i, t in enumerate(tl.get("texts", [])):
            f = (f"drawtext=fontfile={t['font']}:textfile={ROOT / t['textfile']}:fontsize={t['size']}:"
                 f"fontcolor={t.get('color', 'white')}:x={t['x']}:y={t['y']}:"
                 f"line_spacing={t.get('line_spacing', 8)}:"
                 f"enable='between(t,{t['start']},{t['end']})'")
            if t.get("box"):
                f += ":box=1:boxcolor=black@0.55:boxborderw=22"
            if t.get("fade"):
                fd, s0, s1 = t["fade"], t["start"], t["end"]
                f += (f":alpha='if(lt(t,{s0}+{fd}),(t-{s0})/{fd},"
                      f"if(gt(t,{s1}-{fd}),({s1}-t)/{fd},1))'")
            graph.append(f"{chain}{f}[tx{i}]")
            chain = f"[tx{i}]"
        if tl.get("ass"):
            ass = str(ROOT / tl["ass"]).replace(":", r"\:")
            graph.append(f"{chain}subtitles=filename='{ass}'[subs]")
            chain = "[subs]"
        graph.append(f"{chain}format=yuv420p[v]")
    args += ["-filter_complex", ";".join(graph)]
    if video:
        args += ["-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-fps_mode", "passthrough",
                 "-movflags", "+faststart", str(ROOT / tl["out"])]
    else:
        args += ["-map", "[a]", "-f", "null", "-"]
    want = sum(s["frames"] if "card" in s else sum(b - a for a, b in s["pieces"]) for s in segs)
    return args, want


def main() -> None:
    tl = json.loads(Path(sys.argv[1]).read_text())
    fps = fps_of(ROOT / tl["source"])
    args, _ = build(tl, fps, video=False)
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode:
        sys.exit(out.stderr[-3000:])
    loud = json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", out.stderr)[-1])
    print(f"measured {loud['input_i']} LUFS, TP {loud['input_tp']} -> {tl.get('loudness', -14)} LUFS")
    args, want = build(tl, fps, video=True, loud=loud)
    subprocess.run(args, check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                            "-show_entries", "stream=nb_read_frames:format=duration", "-of", "json",
                            str(ROOT / tl["out"])], capture_output=True, text=True, check=True)
    j = json.loads(probe.stdout)
    got = int(j["streams"][0]["nb_read_frames"])
    print(f"\n{tl['out']}: expected {want} frames ({float(want / fps):.2f} s), got {got} "
          f"({float(j['format']['duration']):.2f} s) -> {'MATCH' if got == want else 'MISMATCH'}")


if __name__ == "__main__":
    main()
