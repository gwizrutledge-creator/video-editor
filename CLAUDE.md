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
- WhisperX install from PyPI works here: whisperx 3.8.6 + torch 2.8.0 (takes several minutes; redo it in each new container).
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
- EP 12 delivered: edit/plan.json drives everything (python3 scripts/package.py edit/plan.json [names]); renders land
  in out/ (gitignored). Full edit ~45 min to render (preset fast), Cuts ~10 min each, Shorts <1 min each.
  edit/EDIT_LIST.md is the human edit list. The punch-ins (full-screen Jason/Greg) are in edit/layout.json.
- Big files reach the user with SendUserFile, capped at 400 MiB per file (a 932 MiB full edit was refused); split
  with ffmpeg -c copy -f segment (lossless) and send the parts. The Drive connector only takes inline base64.
- tools venv needs opencv-python-headless<5 (OpenCV 5 dropped CascadeClassifier).
