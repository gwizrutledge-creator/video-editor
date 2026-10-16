# Starter AI video editor

Layout: raw/ (raw clip), transcript/ (words.json, cuts.json), scripts/, vendor/ (cloned connectors).

## Setup notes
- This folder is being run from a Claude Code **cloud session** (Linux container, no GPU), not on the user's own computer.
  The container cannot see or drive desktop apps (Premiere, Resolve), so only file outputs (FCPXML, MP4) can be produced here.
- Tools present in the container: ffmpeg/ffprobe 6.1.1, uv 0.11, git 2.43, Python 3.11 (uv sees /usr/bin/python3.11), Node 22.22.
- No NVIDIA GPU: WhisperX runs CPU int8.
- Network (fresh session, 2026-10-16): huggingface.co, download.pytorch.org model files, pypi.org and
  drive.usercontent.google.com all reachable. WhisperX installs with `uv pip install whisperx` (torch 2.8 CPU path).
- WhisperX alignment needs NLTK `punkt_tab`; nltk.download() refuses the agent proxy (SSRF guard), so fetch
  https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip with curl and unzip
  into ~/nltk_data/tokenizers/. Large-v3 CPU int8 ASR on 4 cores: ~27 min for the 64-min EP 14.
- WhisperX venv: ~/.cache/video-editor/whisperx-venv (container-local; gone when the container is reclaimed).
- scripts/render.py verified on a 1080x1920 29.97 fps test clip: frame-exact pieces, frame count matches.
- User edits in **CapCut** (no Premiere; may install DaVinci Resolve later). CapCut can't import timelines, so the
  deliverable is cut.mp4; scripts/export_fcpxml.py writes cut.fcpxml for Resolve if they get it.
- Current footage: Drive folder "EP 14 Broderick Valentine" (id 1TCPdmMONgC7zwQ7tuQroJnYXraEBdmw5), file
  "EP 14 Brock Valentine.mp4" id 1B8NWVid7RBkkpWGTjkUnTrg0Wqc_v6Uu (2.23 GB, 64 min, 1920x1080 30 fps, StreamYard
  two-up: host Gregory Rutledge + guest Brock Valentine). Saved as raw/EP14_Brock_Valentine.mp4. User wants the whole
  episode cut. Download: curl -L "https://drive.usercontent.google.com/download?id=<id>&export=download&confirm=t".
  Subfolders "BV Opus Reels" / "BV Streamyard Reels" hold reels already made from it.
- Delivery: SendUserFile caps uploads at 400 MiB (one call said 500; 421 MiB was refused), so split long renders losslessly at keyframes inside pauses
  (ffmpeg -c copy -f segment -segment_frames N,...; keyframe index = pts*fps - 1 here) and verify frame totals.
- EP 13 (Mark Drake) is already edited by the user on their PC; dropped.
