"""Render the packaged outputs described in edit/plan.json from the raw episode.

Usage: python3 scripts/package.py edit/plan.json [name ...]
Names pick outputs by their "name" field (full, mid1, short03, ...); default renders all.

Every source range snaps to the footage's frame grid, the same way scripts/render.py does:
each piece is an input-seeked copy of the raw, trimmed to an exact frame count, then all
pieces are concatenated and encoded once. Graphics (GREATER lower-thirds, context card,
end screen, Shorts captions) are drawn in the same pass. Also writes a CMX3600 .edl next
to each file so the cut can be rebuilt by hand in Premiere or Resolve.
"""
import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
ROOT = Path(__file__).resolve().parent.parent

GOLD, BG, GREY = "0xE8AF4C", "0x0A0A0A", "0x6A6A6A"
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT_SEMI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
# Camera tiles in the 1920x1080 two-up layout, measured on the footage. The name bars
# start at y=734, so Shorts crop above them.
TILES = {"greg": (38, 939), "jason": (978, 1880)}
TILE_TOP, TILE_CROP_BOTTOM = 286, 730
GREATER = "GREATER"


def probe(path: Path) -> tuple[Fraction, int, int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate,sample_rate", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    streams = json.loads(out.stdout)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    a = next(s for s in streams if s["codec_type"] == "audio")
    return Fraction(v["r_frame_rate"]), v["width"], v["height"], int(a["sample_rate"])


def tc(frame: int, fps: Fraction) -> str:
    r = round(fps)
    s, f = divmod(frame, r)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


def esc(text: str) -> str:
    # drawtext text= escaping inside a single-quoted filter argument.
    return (text.replace("\\", "\\\\\\\\").replace("'", "’").replace(":", "\\:")
            .replace("%", "\\%").replace(",", "\\,"))


def fade(t0: float, t1: float, f: float = 0.35) -> str:
    return (f"if(lt(t\\,{t0:.3f})\\,0\\,if(lt(t\\,{t0 + f:.3f})\\,(t-{t0:.3f})/{f}\\,"
            f"if(lt(t\\,{t1 - f:.3f})\\,1\\,if(lt(t\\,{t1:.3f})\\,({t1:.3f}-t)/{f}\\,0))))")


def text(t: str, x: str, y: str, size: int, color: str, t0: float, t1: float,
         font: str = FONT, alpha: str | None = None) -> str:
    return (f"drawtext=fontfile={font}:text='{esc(t)}':x={x}:y={y}:fontsize={size}:"
            f"fontcolor={color}:enable='between(t,{t0:.3f},{t1:.3f})':"
            f"alpha='{alpha or fade(t0, t1)}'")


class Timeline:
    """Source pieces (and silent slates) in output order, with source->output time mapping."""

    def __init__(self, fps: Fraction):
        self.fps = fps
        self.items = []  # ("src", a, b, tag) or ("slate", frames, kind)
        self.frames = 0

    def add_src(self, start: float, end: float, tag: str = "body") -> None:
        a, b = round(Fraction(start) * self.fps), round(Fraction(end) * self.fps)
        if b > a:
            self.items.append(("src", a, b, tag, self.frames))
            self.frames += b - a

    def add_slate(self, seconds: float, kind: str) -> None:
        n = round(Fraction(seconds) * self.fps)
        self.items.append(("slate", n, kind, None, self.frames))
        self.frames += n

    def out_time(self, src_t: float, skip_tags=("hook", "coldopen")) -> float:
        f = round(Fraction(src_t) * self.fps)
        for it in self.items:
            if it[0] == "src" and it[3] not in skip_tags and it[1] <= f < it[2]:
                return float((it[4] + f - it[1]) / self.fps)
        raise ValueError(f"source time {src_t} is not in a kept piece")

    def tag_end(self, tag: str) -> float:
        ends = [it[4] + it[2] - it[1] for it in self.items if it[0] == "src" and it[3] == tag]
        return float(max(ends) / self.fps)

    @property
    def seconds(self) -> float:
        return float(self.frames / self.fps)


def piece_inputs(tl: Timeline, raw: Path, rate: int, size: tuple[int, int], vchain: str):
    """ffmpeg input args and filter chains producing [v{i}][a{i}] for each timeline item."""
    fps = tl.fps
    args, graph, labels = [], [], []
    n_in = 0
    for i, it in enumerate(tl.items):
        if it[0] == "src":
            _, a, b, _, _ = it
            n = b - a
            # Seek half a frame early so frame `a` is the first one kept, robust to rounding.
            ss = max(Fraction(0), (a - Fraction(1, 2)) / fps)
            dur = n / fps + 1
            args += ["-threads", "1", "-ss", f"{float(ss):.6f}", "-t", f"{float(dur):.6f}",
                     "-i", str(raw)]
            aoff = a / fps - ss
            d = float(n / fps)
            graph.append(
                f"[{n_in}:v:0]trim=end_frame={n},setpts=PTS-STARTPTS{vchain}[v{i}];"
                f"[{n_in}:a:0]atrim=start={float(aoff):.6f}:duration={d:.6f},asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates={rate}:channel_layouts=stereo,"
                f"afade=t=in:d=0.012,afade=t=out:st={max(0.0, d - 0.012):.6f}:d=0.012[a{i}]")
            n_in += 1
        else:
            _, n, kind, _, _ = it
            d = float(n / fps)
            graph.append(f"color=c={BG}:s={size[0]}x{size[1]}:r={fps}:d={d:.6f},"
                         f"format=yuv420p,setsar=1[v{i}];"
                         f"anullsrc=r={rate}:cl=stereo,atrim=duration={d:.6f}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    graph.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=1[cv][ca]")
    return args, graph


def lower_third(lt: dict, t0: float, dur: float) -> list[str]:
    """GREATER tracker in the empty bottom band: all seven letters, the current one gold,
    with its meaning underneath."""
    t1 = t0 + dur
    idx = lt["index"]  # 0..6 into GREATER (two E's, so the letter alone is ambiguous)
    step, size = 78, 64
    x0 = 960 - step * 7 // 2 + step // 2
    out = [f"drawbox=x=660:y=838:w=600:h=3:color={GOLD}@0.9:t=fill:"
           f"enable='between(t,{t0:.3f},{t1:.3f})'"]
    for k, ch in enumerate(GREATER):
        out.append(text(ch, f"{x0 + k * step}-text_w/2", "862", size,
                        GOLD if k == idx else GREY, t0, t1))
    out.append(text(lt["label"].upper(), "(w-text_w)/2", "952", 38, "white", t0, t1, FONT_SEMI))
    return out


def context_card(line: str, t0: float, dur: float) -> list[str]:
    t1 = t0 + dur
    a = fade(t0, t1, 0.25)
    return [f"drawbox=x=0:y=0:w=iw:h=ih:color={BG}:t=fill:enable='between(t,{t0:.3f},{t1:.3f})'",
            text("THE GREATER JOURNEY", "(w-text_w)/2", "430", 46, GOLD, t0, t1, alpha=a),
            f"drawbox=x=900:y=500:w=120:h=3:color={GOLD}:t=fill:"
            f"enable='between(t,{t0:.3f},{t1:.3f})'",
            text(line, "(w-text_w)/2", "540", 54, "white", t0, t1, FONT_SEMI, alpha=a)]


def end_screen(t0: float, t1: float, guest: str) -> list[str]:
    # Leaves a gold-framed 16:9 space on the left for YouTube's end-screen video element.
    a = fade(t0, t1 + 1, 0.4)
    return [text("THE GREATER JOURNEY", "(w-text_w)/2", "150", 56, GOLD, t0, t1 + 1, alpha=a),
            f"drawbox=x=170:y=330:w=900:h=506:color={GOLD}:t=4:"
            f"enable='between(t,{t0:.3f},{t1 + 1:.3f})'",
            text("WATCH THE", "1160", "430", 44, GREY, t0, t1 + 1, alpha=a),
            text("FULL CONVERSATION", "1160", "490", 64, "white", t0, t1 + 1, alpha=a),
            text(f"with {guest}", "1160", "580", 44, GOLD, t0, t1 + 1, FONT_SEMI, alpha=a)]


def encode_args(out: Path, crf: int) -> list[str]:
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-fps_mode", "passthrough",
            "-movflags", "+faststart", str(out)]


def write_edl(tl: Timeline, title: str, raw: Path, path: Path) -> None:
    reel = "AX"
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    ev = 0
    for it in tl.items:
        ev += 1
        if it[0] == "src":
            _, a, b, tag, rec = it
            lines.append(f"{ev:03d}  {reel:<8} AA/V  C        {tc(a, tl.fps)} {tc(b, tl.fps)} "
                         f"{tc(rec, tl.fps)} {tc(rec + b - a, tl.fps)}")
            lines.append(f"* FROM CLIP NAME: {raw.name}  ({tag})")
        else:
            _, n, kind, _, rec = it
            lines.append(f"{ev:03d}  BL       V     C        00:00:00:00 {tc(n, tl.fps)} "
                         f"{tc(rec, tl.fps)} {tc(rec + n, tl.fps)}")
            lines.append(f"* SLATE: {kind}")
    path.write_text("\n".join(lines) + "\n")


def render_landscape(spec: dict, plan: dict, raw: Path, fps: Fraction, size, rate: int) -> None:
    tl = Timeline(fps)
    for a, b in spec.get("hook", []):
        tl.add_src(a, b, "hook")
    for a, b in spec.get("coldopen", []):
        tl.add_src(a, b, "coldopen")
    for a, b in spec["keep"]:
        tl.add_src(a, b)
    if spec.get("end_screen"):
        tl.add_slate(spec["end_screen"], "end screen")

    args, graph = piece_inputs(tl, raw, rate, size, "")
    draws = []
    for lt in spec.get("lower_thirds", []):
        draws += lower_third(lt, tl.out_time(lt["at"]), lt.get("dur", 7.0))
    if spec.get("card"):
        draws += context_card(spec["card"], tl.tag_end("hook"), spec.get("card_dur", 3.0))
    if spec.get("end_screen"):
        draws += end_screen(tl.seconds - spec["end_screen"], tl.seconds, plan["guest"])
    vout = "[cv]" + (",".join(draws) if draws else "null") + "[v]"
    graph.append(vout)

    out = ROOT / spec["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = (["ffmpeg", "-y", "-v", "error", "-stats"] + args +
           ["-filter_complex", ";\n".join(graph), "-map", "[v]", "-map", "[ca]"] +
           encode_args(out, spec.get("crf", 18)))
    subprocess.run(cmd, check=True)
    write_edl(tl, spec.get("title", spec["name"]), raw, out.with_suffix(".edl"))
    verify(out, tl)


# ---------------------------------------------------------------- Shorts (9:16)

def ass_time(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def caption_words(plan_words: list[dict], start: float, end: float, fixes: dict) -> list[dict]:
    out = []
    for w in plan_words:
        if w["end"] <= start or w["start"] >= end:
            continue
        word = fixes.get(w["word"], w["word"])
        if word:
            out.append({"word": word, "start": max(w["start"], start) - start,
                        "end": min(w["end"], end) - start})
    return out


def write_ass(words: list[dict], path: Path, total: float) -> None:
    """Up to three words on screen, the one being spoken in gold. Each chunk stays up until
    the next one starts, so there is never a blank caption mid-sentence."""
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or w["word"][-1:] in ".?!,;:":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
            "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,Inter,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,"
            "0,0,1,6,0,5,60,60,0,1\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev = []
    gold = "&H4CAFE8&"  # #E8AF4C in ASS BGR
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        for wi, w in enumerate(ch):
            s = 0.0 if ci == 0 and wi == 0 else w["start"]  # first words on screen at once
            e = ch[wi + 1]["start"] if wi + 1 < len(ch) else nxt
            parts = [(f"{{\\c{gold}}}{x['word']}{{\\c&HFFFFFF&}}" if j == wi else x["word"])
                     for j, x in enumerate(ch)]
            ev.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Cap,,0,0,0,,"
                      f"{{\\pos(540,1640)}}{' '.join(parts)}")
    path.write_text(head + "\n".join(ev) + "\n")


def render_short(spec: dict, plan: dict, words: list[dict], raw: Path, fps: Fraction,
                 rate: int) -> None:
    tl = Timeline(fps)
    tl.add_src(spec["in"], spec["out"])
    dur = tl.seconds
    out = ROOT / spec["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    ass = out.with_suffix(".ass")
    write_ass(caption_words(words, spec["in"], spec["out"], plan.get("caption_fixes", {})),
              ass, dur)

    side = TILES[spec["speaker"]]
    h = TILE_CROP_BOTTOM - TILE_TOP
    cx = spec.get("face_x", (side[0] + side[1]) / 2)
    x = int(min(max(cx - h / 2, side[0]), side[1] - h))
    name = plan["people"][spec["speaker"]].upper()
    vchain = (f",crop={h}:{h}:{x}:{TILE_TOP},scale=1080:1080:flags=lanczos,"
              f"pad=1080:1920:0:420:color={BG},setsar=1")
    args, graph = piece_inputs(tl, raw, rate, (1080, 1920), vchain)
    draws = [f"drawtext=fontfile={FONT}:text='THE GREATER JOURNEY':x=(w-text_w)/2:y=300:"
             f"fontsize=48:fontcolor={GOLD}",
             f"drawbox=x=480:y=376:w=120:h=3:color={GOLD}:t=fill",
             f"drawtext=fontfile={FONT_SEMI}:text='{esc(name)}':x=(w-text_w)/2:y=1512:"
             f"fontsize=36:fontcolor={GOLD}",
             f"subtitles=filename='{ass}':fontsdir=/usr/share/fonts/opentype/inter"]
    graph.append("[cv]" + ",".join(draws) + "[v]")
    cmd = (["ffmpeg", "-y", "-v", "error", "-stats"] + args +
           ["-filter_complex", ";\n".join(graph), "-map", "[v]", "-map", "[ca]"] +
           encode_args(out, spec.get("crf", 18)))
    subprocess.run(cmd, check=True)
    write_edl(tl, spec.get("title", spec["name"]), raw, out.with_suffix(".edl"))
    verify(out, tl)


def verify(out: Path, tl: Timeline) -> None:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames,width,height:format=duration", "-of", "json",
         str(out)], capture_output=True, text=True, check=True)
    j = json.loads(res.stdout)
    got = int(j["streams"][0]["nb_read_frames"])
    print(f"{out.relative_to(ROOT)}: {j['streams'][0]['width']}x{j['streams'][0]['height']}, "
          f"{got} frames ({float(j['format']['duration']):.2f} s), expected {tl.frames} -> "
          f"{'MATCH' if got == tl.frames else 'MISMATCH'}")


def main() -> None:
    plan_path = Path(sys.argv[1]).resolve()
    plan = json.loads(plan_path.read_text())
    want = set(sys.argv[2:])
    raw = (ROOT / plan["source"]).resolve()
    fps, w, h, rate = probe(raw)
    if min(w, h) < 1080:
        sys.exit(f"source is {w}x{h}, under 1080p: stopping before any edit.")
    for spec in [plan["full"]] + plan.get("mids", []):
        if not want or spec["name"] in want:
            render_landscape(spec, plan, raw, fps, (w, h), rate)
    shorts = [s for s in plan.get("shorts", []) if not want or s["name"] in want]
    if shorts:
        words = json.loads((ROOT / "transcript/words.json").read_text())["words"]
        words = [x for x in words if "start" in x and "end" in x]
        for spec in shorts:
            render_short(spec, plan, words, raw, fps, rate)


if __name__ == "__main__":
    main()
