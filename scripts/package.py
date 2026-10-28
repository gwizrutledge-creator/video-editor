"""Render the packaged outputs described in edit/plan.json from the raw episode.

Usage: python3 scripts/package.py edit/<ep>/plan.json [name ...]
Names pick outputs by their "name" field (full, mid1, short03, ...); default renders all.

Every source range snaps to the footage's frame grid, the same way scripts/render.py does:
each piece is an input-seeked copy of the raw, trimmed to an exact frame count, then all
pieces are concatenated and encoded once. Graphics (GREATER lower-thirds, context card,
"coming up" tags, info cards, end screen, Shorts captions) are drawn in the same pass. Also
writes a CMX3600 .edl next to each file so the cut can be rebuilt by hand in Premiere or Resolve.

A "keep" entry is [start, end] or [start, end, "teaser"] (a re-hook: a later line played early).
The plan names the episode's transcript and layout map. Shorts follow the layout map
(scripts/layout.py): the crop switches between the speaker's tile in the two-up and the
full-screen punch-ins, centred on the faces scripts/find_faces.py found. The plan's "geometry"
overrides the camera-tile positions below, which were measured on EP 12.
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
# Camera tiles in the 1920x1080 two-up layout, measured on the footage. Shorts crop above
# the name bars: Jason's starts at y=734, Greg's at y=692 while it shows his handle line.
TILES = {"greg": (38, 939), "jason": (978, 1880)}
TILE_TOP = 286
TILE_CROP_BOTTOM = {"greg": 688, "jason": 730}
FULL_SIDE = 900  # square crop from a full-screen punch-in
GREATER = "GREATER"


def geometry(plan: dict) -> dict:
    geo = {"tiles": TILES, "tile_top": TILE_TOP, "crop_bottom": TILE_CROP_BOTTOM,
           "full_side": FULL_SIDE}
    geo.update(plan.get("geometry", {}))
    return geo


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
        self.items = []
        self.frames = 0

    def add_src(self, start: float, end: float, tag: str = "body", vchain: str = "") -> None:
        a, b = round(Fraction(start) * self.fps), round(Fraction(end) * self.fps)
        if b > a:
            self.items.append({"kind": "src", "a": a, "b": b, "tag": tag, "rec": self.frames,
                               "vchain": vchain})
            self.frames += b - a

    def add_slate(self, seconds: float, kind: str) -> None:
        n = round(Fraction(seconds) * self.fps)
        self.items.append({"kind": "slate", "n": n, "tag": kind, "rec": self.frames})
        self.frames += n

    def out_time(self, src_t: float, skip_tags=("hook", "coldopen", "teaser")) -> float:
        f = round(Fraction(src_t) * self.fps)
        for it in self.items:
            if it["kind"] == "src" and it["tag"] not in skip_tags and it["a"] <= f < it["b"]:
                return float((it["rec"] + f - it["a"]) / self.fps)
        raise ValueError(f"source time {src_t} is not in a kept piece")

    def spans(self, tag: str) -> list[tuple[float, float]]:
        return [(float(it["rec"] / self.fps), float((it["rec"] + it["b"] - it["a"]) / self.fps))
                for it in self.items if it["kind"] == "src" and it["tag"] == tag]

    @property
    def seconds(self) -> float:
        return float(self.frames / self.fps)


def piece_inputs(tl: Timeline, raw: Path, rate: int, size: tuple[int, int]):
    """ffmpeg input args and filter chains producing [cv][ca] from the timeline items."""
    fps = tl.fps
    args, graph, labels = [], [], []
    n_in = 0
    for i, it in enumerate(tl.items):
        if it["kind"] == "src":
            a, b = it["a"], it["b"]
            n = b - a
            # Seek half a frame early so frame `a` is the first one kept, robust to rounding.
            ss = max(Fraction(0), (a - Fraction(1, 2)) / fps)
            dur = n / fps + 1
            args += ["-threads", "1", "-ss", f"{float(ss):.6f}", "-t", f"{float(dur):.6f}",
                     "-i", str(raw)]
            aoff = a / fps - ss
            d = float(n / fps)
            graph.append(
                f"[{n_in}:v:0]trim=end_frame={n},setpts=PTS-STARTPTS{it['vchain']}[v{i}];"
                f"[{n_in}:a:0]atrim=start={float(aoff):.6f}:duration={d:.6f},asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates={rate}:channel_layouts=stereo,"
                f"afade=t=in:d=0.012,afade=t=out:st={max(0.0, d - 0.012):.6f}:d=0.012[a{i}]")
            n_in += 1
        else:
            d = float(it["n"] / fps)
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


def coming_up(t0: float, t1: float) -> list[str]:
    """Tag on a re-hook so the jump ahead reads as a tease, not a mistake."""
    en = f"enable='between(t,{t0:.3f},{t1:.3f})'"
    return [f"drawbox=x=1632:y=120:w=6:h=52:color={GOLD}:t=fill:{en}",
            f"drawtext=fontfile={FONT}:text='COMING UP':x=1652:y=128:fontsize=36:"
            f"fontcolor={GOLD}:{en}"]


def info_card(card: dict, t0: float, dur: float) -> list[str]:
    """Two-line card in the bottom band (e.g. where to find the guest)."""
    t1 = t0 + dur
    return [f"drawbox=x=760:y=838:w=400:h=3:color={GOLD}@0.9:t=fill:"
            f"enable='between(t,{t0:.3f},{t1:.3f})'",
            text(card["title"].upper(), "(w-text_w)/2", "866", 40, GOLD, t0, t1),
            text(card["line"], "(w-text_w)/2", "938", 34, "white", t0, t1, FONT_SEMI)]


def tease(card: dict, t0: float, dur: float) -> list[str]:
    """On-screen re-hook in the empty band above the cameras: "COMING UP" and one line about
    a moment still ahead."""
    t1 = t0 + dur
    return [text("COMING UP", "(w-text_w)/2", "112", 30, GOLD, t0, t1),
            f"drawbox=x=900:y=156:w=120:h=3:color={GOLD}@0.9:t=fill:"
            f"enable='between(t,{t0:.3f},{t1:.3f})'",
            text(card["text"], "(w-text_w)/2", "180", 46, "white", t0, t1, FONT_SEMI)]


def encode_args(out: Path, crf: int, preset: str = "medium") -> list[str]:
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-fps_mode", "passthrough",
            "-movflags", "+faststart", str(out)]


def write_edl(tl: Timeline, title: str, raw: Path, path: Path) -> None:
    reel = "AX"
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    ev = 0
    for it in tl.items:
        ev += 1
        rec = it["rec"]
        if it["kind"] == "src":
            a, b = it["a"], it["b"]
            lines.append(f"{ev:03d}  {reel:<8} AA/V  C        {tc(a, tl.fps)} {tc(b, tl.fps)} "
                         f"{tc(rec, tl.fps)} {tc(rec + b - a, tl.fps)}")
            lines.append(f"* FROM CLIP NAME: {raw.name}  ({it['tag']})")
        else:
            n = it["n"]
            lines.append(f"{ev:03d}  BL       V     C        00:00:00:00 {tc(n, tl.fps)} "
                         f"{tc(rec, tl.fps)} {tc(rec + n, tl.fps)}")
            lines.append(f"* SLATE: {it['tag']}")
    path.write_text("\n".join(lines) + "\n")


FILLERS = {"um", "umm", "uh", "uhh", "uhm", "erm", "hmm", "mm", "mhm"}
EMPHASIS = {"really", "very", "so", "no", "yes", "yeah", "go", "pay", "that's"}  # keep "really, really"
DEAD_AIR, DEAD_AIR_KEEP, QUIET_DB = 1.2, 0.5, -40.0


def tighten(keep: list, plan: dict) -> tuple[list, list]:
    """Cut transcribed fillers ("um", "uh"), the first word of a stutter ("the the"), and
    shorten quiet gaps longer than DEAD_AIR to
    DEAD_AIR_KEEP inside each body range. Gaps with sound in them (laughter, a breath before
    an emotional line) stay. Returns the split keep list and the trims [start, end, why]."""
    import array
    import wave
    words = [w for w in json.loads((ROOT / plan["transcript"]).read_text())["words"]
             if "start" in w and "end" in w]
    wav = wave.open(str((ROOT / plan["transcript"]).parent / "audio.wav"))
    rate = wav.getframerate()
    pcm = array.array("h", wav.readframes(wav.getnframes()))

    def loud_db(a: float, b: float) -> float:
        seg = pcm[int(a * rate):int(b * rate)]
        if not seg:
            return -99.0
        rms = (sum(x * x for x in seg[::4]) / len(seg[::4])) ** 0.5
        return 20 * __import__("math").log10(max(rms, 1) / 32768)

    out, trims = [], []
    for k in keep:
        a, b, tag = k[0], k[1], (k[2] if len(k) > 2 else "body")
        if tag != "body":
            out.append(k)
            continue
        inside = [w for w in words if w["start"] >= a and w["end"] <= b]
        cuts = []
        for i, w in enumerate(inside):
            prev_end = inside[i - 1]["end"] if i else a
            nxt = inside[i + 1]["start"] if i + 1 < len(inside) else b
            bare = w["word"].strip(".,?!;:-").lower()
            if bare in FILLERS:
                cuts.append((max(prev_end, w["start"] - 0.04), min(nxt, w["end"] + 0.04), "filler"))
            elif (i + 1 < len(inside) and bare.isalpha() and bare not in EMPHASIS
                  and w["word"][-1:].isalpha()
                  and inside[i + 1]["word"].strip(".,?!;:-").lower() == bare
                  and inside[i + 1]["start"] - w["end"] < 0.6):
                cuts.append((max(prev_end, w["start"] - 0.03), nxt - 0.02, "repeat"))
            if i + 1 < len(inside):
                gap0, gap1 = w["end"], inside[i + 1]["start"]
                if gap1 - gap0 > DEAD_AIR and loud_db(gap0 + 0.1, gap1 - 0.1) < QUIET_DB:
                    pad = DEAD_AIR_KEEP / 2
                    cuts.append((gap0 + pad, gap1 - pad, "dead air"))
        pos = a
        for c0, c1, why in sorted(cuts):
            if c1 - c0 < 0.12 or c0 < pos:
                continue
            out.append([pos, c0])
            trims.append([round(c0, 3), round(c1, 3), why])
            pos = c1
        out.append([pos, b])
    return out, trims


def render_landscape(spec: dict, plan: dict, raw: Path, fps: Fraction, size, rate: int) -> None:
    tl = Timeline(fps)
    for a, b in spec.get("hook", []):
        tl.add_src(a, b, "hook")
    for a, b in spec.get("coldopen", []):
        tl.add_src(a, b, "coldopen")
    keep = tighten(spec["keep"], plan)[0] if spec.get("tighten") else spec["keep"]
    for k in keep:
        tl.add_src(k[0], k[1], k[2] if len(k) > 2 else "body")
    if spec.get("end_screen"):
        tl.add_slate(spec["end_screen"], "end screen")

    args, graph = piece_inputs(tl, raw, rate, size)
    draws = []
    for lt in spec.get("lower_thirds", []):
        draws += lower_third(lt, tl.out_time(lt["at"]), lt.get("dur", 7.0))
    for card in spec.get("info", []):
        draws += info_card(card, tl.out_time(card["at"]), card.get("dur", 8.0))
    for card in spec.get("teases", []):
        draws += tease(card, tl.out_time(card["at"]), card.get("dur", 6.0))
    for t0, t1 in tl.spans("teaser"):
        draws += coming_up(t0, t1)
    if spec.get("card"):
        draws += context_card(spec["card"], tl.spans("hook")[-1][1], spec.get("card_dur", 3.0))
    if spec.get("end_screen"):
        draws += end_screen(tl.seconds - spec["end_screen"], tl.seconds, plan["guest"])
    vout = "[cv]" + (",".join(draws) if draws else "null") + "[v]"
    graph.append(vout)

    out = ROOT / spec["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = (["ffmpeg", "-y", "-v", "error", "-stats"] + args +
           ["-filter_complex", ";\n".join(graph), "-map", "[v]", "-map", "[ca]"] +
           encode_args(out, spec.get("crf", 18), spec.get("preset", "fast")))
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
            # Captions start sentences with a capital even where the transcript doesn't.
            if not out or out[-1]["word"][-1:] in ".?!":
                word = word[:1].upper() + word[1:]
            out.append({"word": word, "start": max(w["start"], start) - start,
                        "end": min(w["end"], end) - start})
    return out


# Shorts follow the v1.1 safe zone (YouTube Shorts, TikTok, Reels): everything that matters
# sits inside x 110-880, y 290-1250. Captions: bottom line ends above y 1250, centred at x 495,
# 2 lines of 3-5 words, 770 px max, one key word in gold. Eyes land around y 760-800.
SAFE_X0, SAFE_CX, SAFE_BOTTOM, CAP_MAX_W, CAP_SIZE = 110, 495, 1240, 740, 70
VIDEO_Y = 335  # top of the 1080x1080 face picture on the 9:16 canvas
STOP = set("""a about all an and any are as at be because been being but by can could do every
for from going gonna had has have he her his how i i'm if in into is it it's just know like me
more much my of on or our really she should so some someone something than that the their them
then there there's these they this those through to until up us very was we were what whatever
when where which while who why will with without would you your don't didn't doesn't i'll
i've you're we're they're that's""".split())


def text_width(t: str, size: int, font: str = FONT) -> int:
    from PIL import ImageFont
    return int(ImageFont.truetype(font, size).getlength(t))


def caption_chunks(words: list[dict]) -> list[list[list[dict]]]:
    """Group words into on-screen captions of at most two lines, each line 3-5 words that
    fit CAP_MAX_W. A sentence end or a pause starts a new caption."""
    chunks, lines = [], [[]]
    for i, w in enumerate(words):
        line = lines[-1]
        fits = text_width(" ".join(x["word"] for x in line + [w]), CAP_SIZE) <= CAP_MAX_W
        if line and (not fits or len(line) == 5):
            if len(lines) == 2:
                chunks.append(lines)
                lines = [[]]
            else:
                lines.append([])
        lines[-1].append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or w["word"][-1:] in ".?!" or nxt["start"] - w["end"] > 0.6:
            chunks.append(lines)
            lines = [[]]
        elif w["word"][-1:] in ",;:" and len(lines[-1]) >= 3 and len(lines) == 1:
            lines.append([])
    return [c for c in chunks if c[0]]


def key_word(chunk: list[list[dict]]) -> int:
    """Index (in reading order) of the word to put in gold: the longest non-filler word."""
    flat = [w["word"] for line in chunk for w in line]
    bare = [x.strip(".,?!;:\"'").lower() for x in flat]
    best = max(range(len(flat)), key=lambda k: (bare[k] not in STOP, len(bare[k])))
    return best


def write_ass(words: list[dict], path: Path, total: float) -> None:
    """Each caption stays up until the next one starts; the first is on screen at frame one."""
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
            "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Cap,Inter,{CAP_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,"
            "100,100,0,0,1,5,0,2,0,0,0,1\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    gold = "&H4CAFE8&"  # #E8AF4C in ASS BGR
    chunks = caption_chunks(words)
    ev = []
    for ci, ch in enumerate(chunks):
        s = 0.0 if ci == 0 else ch[0][0]["start"]
        e = chunks[ci + 1][0][0]["start"] if ci + 1 < len(chunks) else total
        k, n, lines = key_word(ch), 0, []
        for line in ch:
            parts = []
            for w in line:
                parts.append(f"{{\\c{gold}}}{w['word']}{{\\c&HFFFFFF&}}" if n == k else w["word"])
                n += 1
            lines.append(" ".join(parts))
        text = "\\N".join(lines)
        ev.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Cap,,0,0,0,,"
                  f"{{\\pos({SAFE_CX},{SAFE_BOTTOM})}}{text}")
    path.write_text(head + "\n".join(ev) + "\n")


def short_crop(layout: str, speaker: str, face, geo: dict) -> str:
    """Square crop with the face at x 495 of 1080 (the safe box's centre line), scaled to
    1080 and placed at VIDEO_Y (or the plan's geometry "video_y") on the 9:16 canvas."""
    if layout == "2up":
        top = geo["tile_top"]
        side, (x0, x1) = geo["crop_bottom"][speaker] - top, geo["tiles"][speaker]
        cx = face if face is not None else (x0 + x1) / 2
        x, y = int(min(max(cx - side * SAFE_CX / 1080, x0), x1 - side)), top
    else:
        side = geo["full_side"]
        cx, cy = face if face is not None else (960, 400)
        x = int(min(max(cx - side * SAFE_CX / 1080, 0), 1920 - side))
        y = int(min(max(cy - side * 0.40, 0), 1080 - side))
    return (f",crop={side}:{side}:{x}:{y},scale=1080:1080:flags=lanczos,"
            f"pad=1080:1920:0:{geo.get('video_y', VIDEO_Y)}:color={BG},setsar=1")


def layout_pieces(start: float, end: float, fps: Fraction,
                  layout: str) -> list[tuple[float, float, str]]:
    runs = json.loads((ROOT / layout).read_text())["runs"]
    a, b = round(Fraction(start) * fps), round(Fraction(end) * fps)
    out = []
    for r in runs:
        lo, hi = max(a, r["start_frame"]), min(b, r["end_frame"])
        if hi > lo:
            out.append((float(lo / fps), float(hi / fps), r["layout"]))
    return out


def render_short(spec: dict, plan: dict, words: list[dict], raw: Path, fps: Fraction,
                 rate: int) -> None:
    tl = Timeline(fps)
    faces = spec.get("faces", {})
    geo = geometry(plan)
    for a, b, lay in layout_pieces(spec["in"], spec["out"], fps, plan["layout"]):
        tl.add_src(a, b, lay, short_crop(lay, spec["speaker"], faces.get(lay), geo))
    dur = tl.seconds
    out = ROOT / spec["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    ass = out.with_suffix(".ass")
    write_ass(caption_words(words, spec["in"], spec["out"], plan.get("caption_fixes", {})),
              ass, dur)

    # Brand top-left inside the safe box, then who is speaking.
    name = plan["people"][spec["speaker"]].upper()
    brand_w = text_width("THE GREATER JOURNEY", 32)
    args, graph = piece_inputs(tl, raw, rate, (1080, 1920))
    draws = [f"drawtext=fontfile={FONT}:text='THE GREATER JOURNEY':x={SAFE_X0}:y=294:"
             f"fontsize=32:fontcolor={GOLD}",
             f"drawtext=fontfile={FONT_SEMI}:text='|  {esc(name)}':x={SAFE_X0 + brand_w + 18}:"
             f"y=294:fontsize=32:fontcolor=white",
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
    print(f"{out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: {j['streams'][0]['width']}x{j['streams'][0]['height']}, "
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
        words = json.loads((ROOT / plan["transcript"]).read_text())["words"]
        words = [x for x in words if "start" in x and "end" in x]
        for spec in shorts:
            render_short(spec, plan, words, raw, fps, rate)


if __name__ == "__main__":
    main()
