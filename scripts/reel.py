"""Multi-source highlight reel: layouts, matched loudness, captions, graphics, SRT.

Usage: python3 scripts/reel.py <reel.json> [--clean]
reel.json keys:
  out, canvas [w, h], fps, bg
  layouts   {name: {"stack": [[cw, ch, cx, cy], [cw, ch, cx, cy]], "y": top, "gap": px}
             or {"side": [[...], [...]], "w": panel width, "gap": px, "y": top}
             or {"single": [cw, ch, cx, cy], "w": w, "h": h, "y": top}} (crops in source pixels)
  caption_y {layout name: caption centre y}
  items     [{"src": clip, "in": s, "out": e, "layout": name}  (seconds in that clip)
             or {"card": png, "dur": s}]
  graphics  [{"style": "Name|Title|Card1|Card2|Card3", "text": "...", "start": s, "end": s}]
  emphasis  words shown in gold in captions (lower case, punctuation ignored)
Each clip's words come from <clip>.words.json. Writes <out>.ass (captions + graphics),
<out stem>.srt, and renders <out>; with --clean renders <out stem>_clean.mp4 with graphics
but no captions. Speech is levelled per piece to a common loudness, lightly denoised,
then the whole reel gets two-pass loudnorm to -14 LUFS. Frame count is verified.
"""
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CREAM, GOLD = "&H00DDEBF3&", "&H004BA2C9&"  # #F3EBDD, #C9A24B (ASS is BGR)
LEVEL = -18.0  # per-source speech level before the final loudnorm


def norm(w):
    return re.sub(r"[^\w']", "", w.lower())


def ts_ass(t):
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def ts_srt(t):
    ms = max(0, round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def frames(it, fps):
    return round(Fraction(it["dur"] if "card" in it else it["out"] - it["in"]).limit_denominator(1000) * fps)


def piece_gain(src, start, dur):
    """Gain that brings this piece's speech to LEVEL: pieces are mostly one speaker, and
    guests and host are often recorded at very different levels on the same call."""
    out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-ss", f"{start:.3f}",
                          "-t", f"{dur:.3f}", "-i", str(src), "-vn", "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1])
    return max(-12.0, min(16.0, LEVEL - i))


def layout_chain(lay, W, H, bg):
    if "stack" in lay:
        (aw, ah, ax, ay), (bw, bh, bx, by) = lay["stack"]
        th = round(W * ah / aw / 2) * 2
        bh2 = round(W * bh / bw / 2) * 2
        return (f"split=2[a][b];[a]crop={aw}:{ah}:{ax}:{ay},scale={W}:{th}:flags=lanczos,"
                f"pad={W}:{th + lay['gap']}:0:0:color={bg}[t];[b]crop={bw}:{bh}:{bx}:{by},"
                f"scale={W}:{bh2}:flags=lanczos[u];[t][u]vstack=2,pad={W}:{H}:0:{lay['y']}:color={bg}")
    if "side" in lay:  # two panels side by side, each lay["w"] wide, centred
        (aw, ah, ax, ay), (bw, bh, bx, by) = lay["side"]
        pw, g = lay["w"], lay["gap"]
        ph = round(pw * ah / aw / 2) * 2
        return (f"split=2[a][b];[a]crop={aw}:{ah}:{ax}:{ay},scale={pw}:{ph}:flags=lanczos,"
                f"pad={pw + g}:{ph}:0:0:color={bg}[t];[b]crop={bw}:{bh}:{bx}:{by},"
                f"scale={pw}:{ph}:flags=lanczos[u];[t][u]hstack=2,"
                f"pad={W}:{H}:(ow-iw)/2:{lay['y']}:color={bg}")
    cw, ch, cx, cy = lay["single"]
    return (f"crop={cw}:{ch}:{cx}:{cy},scale={lay['w']}:{lay['h']}:flags=lanczos,"
            f"pad={W}:{H}:(ow-iw)/2:{lay['y']}:color={bg}")


def captions(spec, fps):
    """Phrases (at most 2 balanced lines) per clip item, in output time."""
    emph = {norm(w) for w in spec.get("emphasis", [])}
    # Every spoken word in output time; a block is a run of pieces that continue one sentence.
    seq, t = [], Fraction(0)
    for it in spec["items"]:
        n = frames(it, fps)
        if "card" not in it:
            words = json.loads((ROOT / Path(it["src"]).with_suffix(".words.json")).read_text())["words"]
            ws = [dict(w) for w in words if "start" in w and it["in"] - 0.05 <= w["start"] < it["out"] - 0.05]
            cont = not it.get("sentence_start", True)
            if ws and ws[0]["word"][:1].islower() and not cont:
                ws[0]["word"] = ws[0]["word"][0].upper() + ws[0]["word"][1:]  # piece opens mid-sentence
            for j, w in enumerate(ws):
                seq.append({"word": w["word"], "y": spec["caption_y"][it["layout"]],
                            "start": float(t) + max(0.0, w["start"] - it["in"]),
                            "end": float(t) + min(it["out"], w["end"]) - it["in"],
                            "new": j == 0 and not cont})
        else:
            seq.append(None)  # cards break phrases
        t += Fraction(n, fps)

    phrases, cur = [], []
    for i, w in enumerate(seq):
        if w is None:
            continue
        cur.append(w)
        text = " ".join(x["word"] for x in cur)
        nxt = seq[i + 1] if i + 1 < len(seq) else None
        # Words left before this sentence ends: never strand one or two of them.
        rest = next((j for j in range(i + 1, min(i + 3, len(seq)))
                     if seq[j] and not seq[j]["new"] and seq[j]["word"][-1] in ".?!"), None)
        tail = " ".join(x["word"] for x in seq[i + 1:rest + 1]) if rest is not None else ""
        if (nxt is None or nxt["new"] or (w["word"][-1] in ".?!" and len(text) >= 12)
                or (w["word"][-1] in ",;" and len(text) >= 20)
                or (nxt["start"] - w["end"] > 0.85 and len(text) >= 8)
                or (len(text) + 1 + len(nxt["word"]) > 40
                    and not (tail and len(text) + 1 + len(tail) <= 50))):
            phrases.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                            "words": [x["word"] for x in cur], "y": cur[0]["y"]})
            cur = []
    for a, b in zip(phrases, phrases[1:]):  # linger a moment, never overlapping the next phrase
        a["end"] = min(a["end"] + 0.4, b["start"])
    if phrases:
        phrases[-1]["end"] += 0.3
    for p in phrases:
        words = p["words"]
        lines = [" ".join(words)]
        if len(lines[0]) > 22 and len(words) > 1:  # two lines, split nearest the middle
            cut = min(range(1, len(words)),
                      key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
            lines = [" ".join(words[:cut]), " ".join(words[cut:])]
        p["plain"] = "\n".join(lines)
        p["ass"] = "\\N".join(" ".join(f"{{\\c{GOLD}}}{w}{{\\c{CREAM}}}" if norm(w) in emph else w
                                      for w in ln.split()) for ln in lines)
    return phrases, float(t)


def write_subs(spec, phrases, path_ass, path_srt, with_captions=True):
    W, H = spec["canvas"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Barlow SemiBold,66,{CREAM},{CREAM},&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,5,2,5,60,60,0,1
Style: Name,Bebas Neue,74,{GOLD},{GOLD},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,8,60,60,0,1
Style: Title,Barlow Medium,40,{CREAM},{CREAM},&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,0,0,8,60,60,0,1
Style: Card1,Bebas Neue,118,{CREAM},{CREAM},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,5,70,70,0,1
Style: Card2,Barlow SemiBold,66,{CREAM},{CREAM},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,70,70,0,1
Style: Card3,Barlow Bold,58,{GOLD},{GOLD},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for g in spec.get("graphics", []):
        pos = f"{{\\pos({g['x']},{g['y']})}}" if "x" in g else ""
        fade = "{\\fad(250,250)}"
        ev.append(f"Dialogue: 1,{ts_ass(g['start'])},{ts_ass(g['end'])},{g['style']},,0,0,0,,{fade}{pos}{g['text']}")
    if with_captions:
        for p in phrases:
            ev.append(f"Dialogue: 0,{ts_ass(p['start'])},{ts_ass(p['end'])},Cap,,0,0,0,,"
                      f"{{\\pos({W // 2},{p['y']})}}{p['ass']}")
    Path(path_ass).write_text(head + "\n".join(ev) + "\n")
    if path_srt:
        Path(path_srt).write_text("".join(f"{i}\n{ts_srt(p['start'])} --> {ts_srt(p['end'])}\n{p['plain']}\n\n"
                                          for i, p in enumerate(phrases, 1)))


def build(spec, ass, fps, measure=False, loud=None):
    W, H = spec["canvas"]
    bg = spec.get("bg", "0x0B0B0B")
    args = ["ffmpeg", "-nostdin", "-y"] + (["-hide_banner", "-nostats", "-v", "info"] if measure
                                          else ["-v", "error", "-stats"])
    graph, pairs = [], ""
    for k, it in enumerate(spec["items"]):
        n = frames(it, fps)
        dur = n / fps
        if "card" in it:
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.2:.4f}", "-i", str(ROOT / it["card"])]
            graph.append(f"[{2 * k}:v]scale={W}:{H},setsar=1,format=yuv420p,trim=end_frame={n},"
                         f"setpts=PTS-STARTPTS[v{k}]")
            args += ["-f", "lavfi", "-t", f"{dur:.4f}", "-i", "anullsrc=r=48000:cl=stereo"]
            graph.append(f"[{2 * k + 1}:a]atrim=duration={dur:.4f},asetpts=PTS-STARTPTS[a{k}]")
        else:
            src = ROOT / it["src"]
            gain = piece_gain(src, it["in"], dur)
            args += ["-ss", f"{it['in']:.3f}", "-t", f"{dur + 0.5:.4f}", "-i", str(src)]
            args += ["-f", "lavfi", "-t", "0.04", "-i", "anullsrc=r=48000:cl=stereo"]  # keeps input numbering even
            lay = spec["layouts"][it["layout"]]
            graph.append(f"[{2 * k}:v]fps={fps},trim=end_frame={n},setpts=PTS-STARTPTS,"
                         f"{layout_chain(lay, W, H, bg)},setsar=1,format=yuv420p[v{k}]")
            graph.append(f"[{2 * k}:a]aresample=48000,aformat=channel_layouts=stereo,"
                         f"atrim=duration={dur:.4f},asetpts=PTS-STARTPTS,volume={gain:.2f}dB,"
                         f"afade=t=in:d=0.02,afade=t=out:st={max(0, dur - 0.03):.4f}:d=0.03[a{k}]")
        pairs += f"[a{k}]" if measure else f"[v{k}][a{k}]"
    if measure:  # audio-only graph: drop the video chains
        graph = [g for g in graph if not g.startswith("[") or ":a]" in g.split("]")[0] + "]"]
    graph.append(f"{pairs}concat=n={len(spec['items'])}:v={0 if measure else 1}:a=1"
                 + ("[ca]" if measure else "[cv][ca]"))
    ln = "loudnorm=I=-14:TP=-1.5:LRA=11"
    ln += (f":measured_I={loud['input_i']}:measured_TP={loud['input_tp']}:measured_LRA={loud['input_lra']}"
           f":measured_thresh={loud['input_thresh']}:offset={loud['target_offset']}:linear=true"
           if loud else ":print_format=json")
    graph.append(f"[ca]highpass=f=70,afftdn=nr=6:nf=-45,{ln},aresample=48000[a]")
    sub = str(ass).replace(":", r"\:")
    if not measure:
        graph.append(f"[cv]subtitles=filename='{sub}':fontsdir=/root/.fonts,format=yuv420p[v]")
    args += ["-filter_complex", ";".join(graph)]
    if measure:
        return args + ["-map", "[a]", "-f", "null", "-"]
    return args + ["-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k",
                   "-movflags", "+faststart"]


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    clean = "--clean" in sys.argv
    fps = spec.get("fps", 30)
    out = ROOT / spec["out"]
    phrases, total = captions(spec, fps)
    ass_full, ass_clean = out.with_suffix(".ass"), out.with_name(out.stem + "_clean.ass")
    write_subs(spec, phrases, ass_full, out.with_suffix(".srt"), with_captions=True)
    write_subs(spec, phrases, ass_clean, None, with_captions=False)
    ass = ass_clean if clean else ass_full
    target = out.with_name(out.stem + "_clean.mp4") if clean else out
    m = subprocess.run(build(spec, ass, fps, measure=True), capture_output=True, text=True)
    if m.returncode:
        sys.exit(m.stderr[-3000:])
    loud = json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", m.stderr)[-1])
    subprocess.run(build(spec, ass, fps, loud=loud) + [str(target)], check=True)
    want = sum(frames(it, fps) for it in spec["items"])
    p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                   "-show_entries", "stream=nb_read_frames:format=duration", "-of", "json",
                                   str(target)], capture_output=True, text=True).stdout)
    got = int(p["streams"][0]["nb_read_frames"])
    print(f"{target.name}: {len(phrases)} caption phrases; expected {want} frames ({want / fps:.2f} s), "
          f"got {got} ({float(p['format']['duration']):.2f} s) -> {'MATCH' if got == want else 'MISMATCH'}")


if __name__ == "__main__":
    main()
