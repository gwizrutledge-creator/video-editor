"""Build edit/SCHEDULE.csv and edit/SCHEDULE.md: the posting calendar for EP 13, EP 12 and EP 14
from the audit's 3-week calendars (long videos 11:00 a.m. Central, Shorts 12:30 p.m. on three platforms).

Usage: python3 scripts/schedule.py <saved copy of the audit page's HTML>
(The audit page supplies the full-episode descriptions and tags.)
"""
import csv, json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
CT = timezone(timedelta(hours=-6))  # Central Standard Time (Nov-Mar)
LONG_T, SHORT_T = (11, 0), (12, 30)
LINKS = "📖 Get Gregory's book, From Waiter to Greater: https://amzn.to/3TRTGQe\n🔗 Connect with Gregory: https://linktr.ee/gregoryrutledge"

def plan(ep): return json.loads((ROOT / f"edit/{ep}/plan.json").read_text())

# ---------- per-episode content
EP = {}
p12 = plan("ep12")
ep12_cut_desc = {
 "mid1": "Jason McKenzie had over a decade of business experience when he suddenly couldn't send a bill. In this conversation from The Greater Journey, he traces that money block back to a childhood memory, then shares the reframe that freed him: every payment is a thank you. Gregory Rutledge shares his own money block and the question that changed how he charges: \"Are you willing to receive it?\"",
 "mid2": "Who is your ideal customer? If the answer is \"anyone with a home\" or \"anyone who drinks water,\" this one is for you. Jason McKenzie explains why saying no to the wrong customers grew his business, how core values decide who you serve, and the courage it took to land his first paying client.",
 "mid3": "A client told him \"we need you,\" and Jason McKenzie realized he had built a cage around himself. Here's how he went from Fireman Jason, putting out every fire, to taking most of October off while his business kept running, and why a business can only grow as fast as its owner does.",
 "mid4": "Jason McKenzie's ventures kept failing until he believed he was cursed. He shares what pulled him back, what he saw at Myron Golden's Offer Mastery Live, and a fresh look at Paul's thorn in the flesh: what if the thing God won't remove is the thing that makes you great?",
}
ep12_cut_tags = {"mid1": "#ChristianEntrepreneur #MoneyMindset #TheGreaterJourney", "mid2": "#ChristianEntrepreneur #SmallBusiness #TheGreaterJourney",
                 "mid3": "#ChristianEntrepreneur #FounderBurnout #TheGreaterJourney", "mid4": "#ChristianEntrepreneur #Faith #TheGreaterJourney"}
ep12_short = {  # name: (description, hashtags) — hashtags from the audit, descriptions drafted
 "S1": ("Jason McKenzie had over a decade of experience when he suddenly got scared to send a bill.", "#ChristianEntrepreneur #MoneyMindset #Shorts"),
 "S2": ("Jason McKenzie traced his money block back to the gifts he got as a little kid.", "#MoneyMindset #ChristianEntrepreneur #Shorts"),
 "S3": ("Gregory Rutledge on the limits we end up defending: if we're not careful, we fight for limitations we don't even want.", "#ChristianEntrepreneur #Mindset #Shorts"),
 "S4": ("Jason McKenzie on a new way to see paying anyone: when someone pays you money, it's an expression of gratitude.", "#MoneyMindset #ChristianEntrepreneur #Shorts"),
 "S5": ("The question that got Gregory Rutledge to start charging: are you willing to receive it?", "#ChristianEntrepreneur #MoneyMindset #Shorts"),
 "S6": ("Who do you want to work with? If the answer is \"anyone that drinks water,\" Jason McKenzie has news for you.", "#SmallBusiness #ChristianEntrepreneur #Shorts"),
 "S7": ("IT services and snow removal under the same business name. Jason McKenzie on why that confuses everyone.", "#SmallBusiness #Entrepreneur #Shorts"),
 "S8": ("A client said \"we need you,\" and Jason McKenzie realized he had built a cage.", "#FounderBurnout #ChristianEntrepreneur #Shorts"),
 "S9": ("Gregory Rutledge: if your business can't survive without you, you don't have a business. You have an expensive job.", "#FounderBurnout #ChristianEntrepreneur #Shorts"),
 "S10": ("Jason McKenzie on Paul's thorn: maybe you can make greatness out of it, because we're not going to outsmart God.", "#Faith #ChristianEntrepreneur #Shorts"),
}
ep12_titles = {"S1":"Scared to Send a Bill After 10 Years in Business","S2":"The Childhood Memory Behind His Money Block","S3":"You're Fighting for Limits You Don't Even Want","S4":"Every Payment Is a Thank You","S5":"Are You Willing to Receive It?","S6":"\"Anyone Who Drinks Water\" Is Not Your Customer","S7":"IT Services and Snow Removal Under One Name?","S8":"\"We Need You\": The Day He Realized He Built a Cage","S9":"If Your Business Needs You Every Day, You Have a Job","S10":"What If Your Thorn Is Where Your Greatness Starts?"}
ep12_links = {"S1":"Full episode","S2":"Full episode","S3":"Cut 1","S4":"Cut 1","S5":"Cut 1","S6":"Cut 2","S7":"Cut 2","S8":"Full episode","S9":"Cut 3","S10":"Cut 4"}
EP["ep12"] = dict(label="EP 12 · Jason McKenzie", guest_link="🌐 Boise Web: https://boiseweb.net",
  full_title="He Was Scared to Send a Bill. The Reason Went Back to Childhood.",
  cuts={m["name"]: (m["title"], m["file"], ep12_cut_desc[m["name"]], ep12_cut_tags[m["name"]]) for m in p12["mids"]},
  shorts={s["name"]: (ep12_titles[s["name"]], s["file"], *ep12_short[s["name"]], ep12_links[s["name"]]) for s in p12["shorts"]},
  weeks=[["full","S1","S2","mid1","S3","mid3","S9"],[None,"S4","S8","mid2","S6","mid4","S10"],[None,"S5","S7",None,None,None,None]])

p13 = plan("ep13")
ep13_cut_desc = {
 "mid1": "At 18 he left a Dallas gang. In 2002 he was making $7.25 an hour when God promised him he'd be the richest man he knew. Christian entrepreneur Mark Drake shares how he went from no degree and no skill set to a director's seat and his own business.",
 "mid2": "Mark Drake can start a business in his sleep. He used to procrastinate, until he got organized. He shares why you can't have hope without wisdom, the Super Bowl playbook for an organized mind, and why business runs on structure, not feelings.",
 "mid3": "Mark Drake had to learn when to let go of the Porsche. Then he traced the imposter syndrome he'd carried for 20 years back to one year: sixth grade. Here's how finding the root cause set him free, and why you'll bleed on people who didn't cut you until you heal.",
 "mid4": "Keep your heart right, give God something to work with, and find someone to serve. Mark Drake's three pillars, and the motto that grew his business through referrals: partnership before profit.",
 "mid5": "How do you stay resilient? A friend who faced 20 years in prison taught Mark Drake to keep every setback in perspective. Plus his definition of greater, and the one step to take if you feel stuck: go back to the last thing God told you to do.",
}
ep13_cut_tags = {"mid1":"#ChristianEntrepreneur #TrustGod #TheGreaterJourney","mid2":"#ChristianEntrepreneur #SmallBusiness #TheGreaterJourney","mid3":"#ChristianEntrepreneur #ImposterSyndrome #TheGreaterJourney","mid4":"#ChristianEntrepreneur #FaithAndBusiness #TheGreaterJourney","mid5":"#ChristianEntrepreneur #Resilience #TheGreaterJourney"}
EP["ep13"] = dict(label="EP 13 · Mark Drake", guest_link="📸 Follow Mark: https://instagram.com/beingmarkdrake",
  full_title="Former Gang Member Can Now Start a Business in His Sleep",
  cuts={m["name"]: (m["title"], m["file"], ep13_cut_desc[m["name"]], ep13_cut_tags[m["name"]]) for m in p13["mids"]},
  shorts={s["name"]: (s["title"], s["file"], s["desc"], s["hashtags"], s["links"]) for s in p13["shorts"]},
  keywords={s["name"]: s.get("keyword", "") for s in p13["shorts"]},
  weeks=[["full","S1","S2","mid1","S3","mid2","S4"],[None,"S5","S6","mid3","S7","mid4","S8"],[None,"S9",None,"mid5","S10",None,None]])

p14 = plan("ep14")
ep14_cut_tags = {"mid1":"#ChristianEntrepreneur #SuccessStory #TheGreaterJourney","mid2":"#ChristianEntrepreneur #Consistency #TheGreaterJourney","mid3":"#ChristianEntrepreneur #Consistency #TheGreaterJourney","mid4":"#ChristianEntrepreneur #ReinventYourself #TheGreaterJourney"}
EP["ep14"] = dict(label="EP 14 · Brock Valentine", guest_link="🌐 Brock Valentine: https://thebvalentine.com [confirm]",
  full_title="It Doesn't Matter What You Offer If You Can't Get in the Room",
  cuts={m["name"]: (m["title"], m["file"], m["desc"], ep14_cut_tags[m["name"]]) for m in p14["mids"]},
  shorts={s["name"]: (s["title"], s["file"], s["desc"], s["hashtags"], s["links"]) for s in p14["shorts"]},
  keywords={s["name"]: s.get("keyword", "") for s in p14["shorts"]},
  # audit calendar with its cuts renumbered (audit Cut 4 -> 3, Cut 5 -> 4, Cuts 2+3 -> 2)
  weeks=[["full","S1","S3","mid1","S2","mid3","S8"],[None,"S9","S7","mid4","S10","mid2","S6"],[None,None,None,None,"S4",None,"S5"]])

# Full-episode descriptions, tags and notes come from the audit page (saved HTML copy passed as argv[1]).
import re, sys
AUDIT = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else ""
CONSTS = {"LINKS": LINKS, "BROCK": "🌐 Brock Valentine: https://thebvalentine.com [confirm]"}
def audit_field(ep, field):
    block = AUDIT.split(f"id: '{ep}'", 1)[1].split("\n  id: '", 1)[0] if f"id: '{ep}'" in AUDIT else ""
    m = re.search(field + r": `(.*?)`", block, re.S)
    return re.sub(r"\$\{(\w+)\}", lambda g: CONSTS.get(g.group(1), g.group(0)), m.group(1)) if m else ""
for ep in EP:
    EP[ep]["full_desc"] = audit_field(ep, "description")
    EP[ep]["full_tags"] = audit_field(ep, "tags")
EP["ep13"]["full_note"] = "End screen → the Jeff Caliguire episode (per the audit)"

ORDER = ["ep13", "ep12", "ep14"]
START = date(2026, 11, 9)  # first Monday after today

rows = []
day0 = START
for ep in ORDER:
    e = EP[ep]
    cutnum = {n: i + 1 for i, n in enumerate(e["cuts"])}
    for w, week in enumerate(e["weeks"]):
        for d, item in enumerate(week):
            if not item:
                continue
            day = day0 + timedelta(days=7 * w + d)
            if item == "full":
                t = datetime(day.year, day.month, day.day, *LONG_T, tzinfo=CT)
                rows.append(dict(date=day.isoformat(), time_ct="11:00 AM", utc=t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    episode=e["label"], item="Full episode", platform="YouTube", file="(your full-episode upload)",
                    title=e["full_title"], caption=e["full_desc"], hashtags=e["full_tags"],
                    keyword="", related=e.get("full_note", "")))
            elif item.startswith("mid"):
                title, f, desc, tags = e["cuts"][item]
                t = datetime(day.year, day.month, day.day, *LONG_T, tzinfo=CT)
                caption = f"{desc}\n\n▶️ Full episode: [link to the full episode]\n{e['guest_link']}\n{LINKS}"
                rows.append(dict(date=day.isoformat(), time_ct="11:00 AM", utc=t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    episode=e["label"], item=f"Cut {cutnum[item]}", platform="YouTube", file=f, title=title,
                    caption=caption, hashtags=tags, keyword="", related="End screen → full episode"))
            else:
                title, f, desc, tags, link = e["shorts"][item]
                kw = e.get("keywords", {}).get(item, "")
                t = datetime(day.year, day.month, day.day, *SHORT_T, tzinfo=CT)
                for plat in ("YouTube Shorts", "TikTok", "Instagram Reels"):
                    rows.append(dict(date=day.isoformat(), time_ct="12:30 PM", utc=t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        episode=e["label"], item=item, platform=plat, file=f, title=title,
                        caption=desc, hashtags=tags, keyword=kw,
                        related=(link if plat == "YouTube Shorts" else f"Link in bio → {link}")))
    day0 += timedelta(weeks=3)

# A Short must link to a video that is already live when it posts.
live = {(r["episode"], r["item"]): r["date"] for r in rows if r["platform"] == "YouTube"}
for r in rows:
    target = r["related"].replace("Link in bio → ", "")
    if target.startswith("Cut") and live.get((r["episode"], target), "9999") > r["date"]:
        print("relinked", r["episode"], r["item"], r["platform"], target, "-> Full episode")
        r["related"] = r["related"].replace(target, "Full episode")

with (ROOT / "edit/SCHEDULE.csv").open("w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
    wr.writeheader(); wr.writerows(rows)

# Markdown calendar
L = ["# Posting calendar · EP 13, EP 12, EP 14\n",
     f"Follows each episode's 3-week calendar from your audit, back to back: EP 13 from {START:%a %b %-d}, then EP 12, then EP 14 "
     "(\"start the week after the previous run ends\"). Long videos (full episode, cuts) at **11:00 a.m. Central** on YouTube; "
     "Shorts at **12:30 p.m. Central** on YouTube Shorts, TikTok and Instagram Reels. Every row, with its exact file, title, "
     "caption and UTC time, is in `edit/SCHEDULE.csv` (one row per platform).\n",
     f"Totals: {sum(r['item'].startswith('Cut') for r in rows)} cuts, {sum(1 for r in rows if r['platform']=='YouTube Shorts')} Shorts "
     f"× 3 platforms = {sum(1 for r in rows if r['item'].startswith('S'))} Short posts, plus 3 full episodes.\n"]
cur = None
for r in rows:
    if r["platform"] in ("TikTok", "Instagram Reels"):
        continue
    if r["episode"] != cur:
        cur = r["episode"]; L += ["", f"## {cur}\n", "| Date | Time (CT) | Post | Where | Title | Related video |", "|---|---|---|---|---|---|"]
    d = datetime.fromisoformat(r["date"])
    where = "YouTube" if r["platform"] == "YouTube" else "YouTube Shorts · TikTok · Reels"
    L.append(f"| {d:%a %b %-d} | {r['time_ct']} | {r['item']} | {where} | {r['title']} | {r['related']} |")
(ROOT / "edit/SCHEDULE.md").write_text("\n".join(L) + "\n")
print(len(rows), "rows;", rows[0]["date"], "to", rows[-1]["date"])
