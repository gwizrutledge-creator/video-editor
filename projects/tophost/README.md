# Top Host campaign reel — editable project

Everything here is plain text, so any piece can be changed and the videos re-rendered.

| File | What it is |
|---|---|
| `reel_v2.json` | Flagship vertical reel (89.9 s): every piece (source clip, in/out, layout, speaker), caption positions, gold-emphasis words, name card and end card |
| `reel_30s.json` | 30-second cutdown (31.6 s) |
| `reel_16x9.json` | 1920×1080 version of the flagship |
| `reel_v1.json` | First rough cut (91.1 s), kept for reference |
| `src/*.mp4`, `src/*.words.json` | Downloaded source windows and their word-level transcripts *(the videos are kept out of git)* |
| `window_offsets.json`, `sources.json` | Where each window starts in its episode; episode titles, URLs and Drive ids |
| `SOURCE_LOG.md` | Source log: every excerpt with source in/out, speaker and exact words |
| `POST_COPY.md` | Post text with the voting link |

## Re-render

```
python3 scripts/reel.py projects/tophost/reel_v2.json           # captioned, plus .srt and .ass
python3 scripts/reel.py projects/tophost/reel_v2.json --clean   # same reel, no captions
python3 scripts/reel.py projects/tophost/reel_30s.json
python3 scripts/reel.py projects/tophost/reel_16x9.json
python3 scripts/reel_log.py projects/tophost projects/tophost/reel_v2.json projects/tophost/reel_30s.json
```

To swap or trim a moment, edit that item's `in`/`out` (seconds in its `src` clip) and
re-render. Captions, end-card timing, the frame count check and the log all follow
automatically. Re-render needs Bebas Neue and Barlow in `~/.fonts`; the Clip Index lists
where each moment lives.

## Look and sound

- Vertical layout: host panel on top, guest below, captions in the band between; the top and
  bottom 250 px stay clear for platform buttons.
- Colors: black `#0B0B0B`, cream `#F3EBDD`, restrained gold `#C9A24B`. Fonts: Bebas Neue (display)
  and Barlow (text).
- Audio: each piece levelled to the same speech loudness (host and guest were recorded at very
  different levels on some calls), light noise reduction, then −14 LUFS overall with peaks
  under −1.5 dB. No music.
