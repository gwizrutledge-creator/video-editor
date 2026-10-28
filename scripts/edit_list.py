"""Write the human edit list for an episode: edit/<ep>/EDIT_LIST.md.

Usage: python3 scripts/edit_list.py edit/<ep>/plan.json
Reads the plan and edit/<ep>/reasons.json ({"<source start s>": [action, one-line reason]},
one entry per row of the full edit, covering the whole source in order). Applies the same
tightening as package.py, so every timecode matches the rendered files.
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from package import Timeline, probe, tighten  # noqa: E402

GREATER = "GREATER"


def tc(f: int, fps: int) -> str:
    s, ff = divmod(int(f), fps)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{ff:02d}"


def length(f: int, fps: int) -> str:
    s = round(f / fps)
    return f"{s // 60}:{s % 60:02d}"


def build(spec: dict, plan: dict, fps: Fraction):
    tl = Timeline(fps)
    for a, b in spec.get("hook", []):
        tl.add_src(a, b, "hook")
    for a, b in spec.get("coldopen", []):
        tl.add_src(a, b, "coldopen")
    keep, trims = tighten(spec["keep"], plan) if spec.get("tighten") else (spec["keep"], [])
    for k in keep:
        tl.add_src(k[0], k[1], k[2] if len(k) > 2 else "body")
    if spec.get("end_screen"):
        tl.add_slate(spec["end_screen"], "end screen")
    return tl, trims


def main() -> None:
    plan_path = Path(sys.argv[1]).resolve()
    plan = json.loads(plan_path.read_text())
    reasons = {float(k): v for k, v in
               json.loads((plan_path.parent / "reasons.json").read_text()).items()}
    fps, w, h, _ = probe(ROOT / plan["source"])
    F = round(fps)
    fr = lambda t: round(Fraction(t) * fps)  # noqa: E731
    out_fr = lambda tl, t: round(Fraction(tl.out_time(t)) * fps)  # noqa: E731
    duration = float(json.loads(__import__("subprocess").run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
         str(ROOT / plan["source"])], capture_output=True, text=True).stdout)["format"]["duration"])

    full = plan["full"]
    tl, trims = build(full, plan, fps)
    L = [f"# {Path(plan['source']).stem.replace('_', ' ')} · Edit list\n",
         f"Source: `{plan['source']}` ({w}×{h}, {F} fps, {length(fr(duration), F)}). Timecodes are "
         f"HH:MM:SS:FF at {F} fps (non-drop). **Source** = position in that file; **Edit** = "
         "position in the finished video. Every file also has a CMX3600 `.edl` next to it.\n",
         "## 1 · Full episode\n",
         f"**Title:** {full['title']}  \n**Length:** {length(tl.frames, F)}  \n"
         f"**File:** `{full['file']}`\n",
         "| # | Source in | Source out | Action | Edit in | Reason |", "|---|---|---|---|---|---|"]
    starts = sorted(reasons)
    for n, s in enumerate(starts, 1):
        e = starts[n] if n < len(starts) else duration
        act, why = reasons[s]
        edit_in = ""
        if act != "cut":
            first = next(it for it in tl.items if it["kind"] == "src" and it["a"] >= fr(s) - 1)
            edit_in = tc(first["rec"], F)
        L.append(f"| {n} | {tc(fr(s), F)} | {tc(fr(e), F)} | **{act}** | {edit_in} | {why} |")
    if trims:
        sec = sum(b - a for a, b, _ in trims)
        L += ["", f"**Small trims inside the kept rows** ({len(trims)} cuts, {sec:.1f} s): fillers "
              "(\"um\", \"uh\"), the first word of a stutter (\"the the\"), and quiet pauses over "
              "1.2 s shortened to 0.5 s. Pauses with laughter or other sound in them stay.\n",
              "| Source in | Source out | Trim |", "|---|---|---|"]
        L += [f"| {tc(fr(a), F)} | {tc(fr(b), F)} | {why} |" for a, b, why in trims]
    L += ["", "**GREATER lower-thirds** (bottom band, 7 s, current letter in gold):\n"]
    L += [f"- {GREATER[x['index']]} · {x['label']}: source {tc(fr(x['at']), F)}, edit "
          f"{tc(out_fr(tl, x['at']), F)}" for x in full.get("lower_thirds", [])]
    if full.get("teases"):
        L += ["", "**On-screen re-hooks** (\"COMING UP\" in the top band, 6 s):\n"]
        L += [f"- Edit {tc(out_fr(tl, x['at']), F)}: \"{x['text']}\"" for x in full["teases"]]
    for c in full.get("info", []):
        L += ["", f"**CTA card:** \"{c['title']}: {c['line']}\" at edit "
              f"{tc(out_fr(tl, c['at']), F)} for {c.get('dur', 8)} s."]

    card = next((m["card"] for m in plan.get("mids", []) if m.get("card")), "")
    L += ["", "## 2 · Mid-length cuts (16:9)\n",
          f"Each one: strongest line (under 15 s) → text card \"{card}\" (3 s, over the start of the "
          "body) → the story → ends on the guest's line → 10 s end screen with a framed slot for "
          "YouTube's \"full episode\" end-screen element.\n"]
    for m in plan.get("mids", []):
        mtl, _ = build(m, plan, fps)
        L += [f"### {m['title']}\n", f"`{m['file']}` · {length(mtl.frames, F)}\n",
              "| Part | Source in | Source out | Edit in |", "|---|---|---|---|",
              f"| Opener | {tc(fr(m['hook'][0][0]), F)} | {tc(fr(m['hook'][0][1]), F)} | 00:00:00:00 |"]
        for a, b in m["keep"]:
            first = next(it for it in mtl.items if it["kind"] == "src" and it["tag"] == "body"
                         and it["a"] >= fr(a) - 1)
            L.append(f"| Body | {tc(fr(a), F)} | {tc(fr(b), F)} | {tc(first['rec'], F)} |")
        L += [f"| End screen | | | {tc(mtl.frames - m['end_screen'] * F, F)} (10 s) |", "",
              "Lower-thirds: " + ", ".join(f"{GREATER[x['index']]} · {x['label']}"
                                           for x in m.get("lower_thirds", [])) + "\n"]

    L += ["## 3 · Shorts (9:16, 1080×1920, burned-in captions)\n",
          "One master file for YouTube Shorts, TikTok and Reels: captions and branding inside the "
          "safe box (x 110–880, y 290–1250), face centred at x 495, first words on screen at frame "
          "one. In YouTube Studio, set each Short's **Related video** to the video listed.\n",
          "| Short | Title | Source in | Source out | Length | Related video |",
          "|---|---|---|---|---|---|"]
    for s in plan.get("shorts", []):
        n = fr(s["out"]) - fr(s["in"])
        L.append(f"| {s['name']} | {s['title']} | {tc(fr(s['in']), F)} | {tc(fr(s['out']), F)} | "
                 f"{n / F:.1f} s | {s['links']} |")
    if any("desc" in s for s in plan.get("shorts", [])):
        L += ["", "**Captions for posting** (description · search keyword · hashtags):\n"]
        L += [f"- **{s['name']}** · {s['desc']} · *{s['keyword']}* · {s['hashtags']}"
              for s in plan["shorts"] if "desc" in s]
    (plan_path.parent / "EDIT_LIST.md").write_text("\n".join(L) + "\n")
    print(f"wrote {(plan_path.parent / 'EDIT_LIST.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
