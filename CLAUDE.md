# Starter AI video editor

Layout: raw/ (raw clip), transcript/ (words.json, cuts.json), scripts/, vendor/ (cloned connectors).

## Setup notes
- This folder is being run from a Claude Code **cloud session** (Linux container, no GPU), not on the user's own computer.
  The container cannot see or drive desktop apps (Premiere, Resolve), so only file outputs (FCPXML, MP4) can be produced here.
- Tools present in the container: ffmpeg/ffprobe 6.1.1, uv 0.11, git 2.43, Python 3.11 (uv sees /usr/bin/python3.11), Node 22.22.
- No NVIDIA GPU: WhisperX runs CPU int8.
- Network policy blocks huggingface.co (+ *.hf.co CDN) and download.pytorch.org, which WhisperX needs for large-v3 and
  the alignment model. pypi.org works (whisperx installs fine). Allow those hosts in the environment's Network access.
- WhisperX venv: ~/.cache/video-editor/whisperx-venv (container-local; gone when the container is reclaimed).
- scripts/render.py verified on a 1080x1920 29.97 fps test clip: frame-exact pieces, frame count matches.
- Footage: Google Drive "EP 13 Mark Drake.mp4" (2.14 GB, podcast episode with a guest; user wants the WHOLE episode cut), file id
  1mL78jgcUMP5fiYDYZ4QG1sa_MX84bvVO (identical-size copy 1c8RUEB6OJtTiHOCsHacm26zDurYwxC7r in subfolder "EP. 13 Mark Drake").
  The Drive connector returns files as base64 in the chat, which can't carry 2 GB; download it with curl from
  drive.usercontent.google.com instead (needs the file shared "anyone with the link" and that host allowed).
- Allowing hosts in Network access did not reach the already-running container; the new policy applies to a fresh session.
- WhisperX install from PyPI works here: whisperx 3.8.6 + torch 2.8.0. scripts/setup.sh does it (5.6 min from a warm uv
  cache); CPU-only torch would skip ~3 GB of CUDA wheels but download-r2.pytorch.org is blocked, so it falls back to PyPI.
- EP 12 Jason McKenzie: the user's chosen source is Drive "From Thorn to Greatness: A Greater Journey.mp4", file id
  1pC3LmO7KT-Q0DZxG_MhDbInTiPjbbVuI (folder "Gregory Podcast Episodes - Packaging/Jason McKenzie"), 1920x1080 30 fps, 51:28,
  saved as raw/EP12_Jason_McKenzie.mp4. Already has a cold open (0:00-0:41) and title card (0:41-0:43); remote two-up layout
  (Greg tile x 38-939, Jason x 978-1880, y 286-792, name bars from y 734). Audio is dual-mono: no per-speaker channels.
- Drive downloads can fail with "Quota exceeded" (HTML instead of video); another copy of the file may still work.
- WhisperX alignment needs NLTK punkt_tab; NLTK's downloader refuses the proxy, so curl
  raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip into ~/nltk_data/tokenizers/.
- transcribe.py caches the unaligned ASR in transcript/asr.json; WHISPER_MODEL=large-v3-turbo took ~15 min for 51 min here.
- scripts/package.py renders edit/plan.json (full edit, mid-length cuts, 9:16 Shorts with captions) + an EDL per file;
  scripts/find_faces.py (tools venv ~/.cache/video-editor/tools-venv with opencv) centres Shorts on the speaker's face.
- Per-episode folders: transcript/<ep>/ (words.json, audio.wav), edit/<ep>/ (plan.json, layout.json, reasons.json,
  EDIT_LIST.md), out/<ep>/ (renders, gitignored). Workflow for a new episode:
  1. bash scripts/setup.sh (skip if the environment's setup script already ran it)
  2. curl the footage into raw/; check it is 1080p+
  3. WHISPER_MODEL=large-v3-turbo ~/.cache/video-editor/whisperx-venv/bin/python scripts/transcribe.py raw/<clip> transcript/<ep>
  4. write edit/<ep>/plan.json (source, transcript, layout, geometry = camera tiles measured on a frame)
  5. tools-venv python scripts/layout.py edit/<ep>/plan.json; then fill full/mids/shorts in the plan
  6. tools-venv python scripts/find_faces.py edit/<ep>/plan.json
  7. python3 scripts/package.py edit/<ep>/plan.json [names]; python3 scripts/edit_list.py edit/<ep>/plan.json
  Render times on 4 cores: full ~45 min (preset fast), cuts ~8-10 min each, Shorts <1 min each.
- The user's BLOOM prompt and per-episode audits live in their claude.ai artifact S4ff86efYz3bdbsHYV8ksY (episode data
  sits in the page's script; grep the saved HTML for "id: 'epNN'"). Master prompt v1.1 (26 Oct 2026) adds filler/stutter
  cuts, recap bridges <=5 s, an on-screen re-hook every 5-8 min, and the Shorts safe zone (x 110-880, y 290-1250).
- "tighten": true in a plan spec cuts transcribed fillers, stutter repeats and quiet gaps >1.2 s (keeps laughter).
- EP 13 Mark Drake: Drive file 1RYwAFROXCZMep7G-9t6L1eY1G4d5ds1L ("EP 13 Mark Drake YouTube Final.mp4", 55:42), saved as
  raw/EP13_Mark_Drake.mp4. Two-up only (Greg x 32-943, Mark x 976-1887, y 286-793); channel intro 0:37.6-0:48.9.
- Big files reach the user with SendUserFile, capped at 400 MiB per file (a 932 MiB full edit was refused); split
  with ffmpeg -c copy -f segment (lossless) and send the parts. The Drive connector only takes inline base64.
- tools venv needs opencv-python-headless<5 (OpenCV 5 dropped CascadeClassifier).
