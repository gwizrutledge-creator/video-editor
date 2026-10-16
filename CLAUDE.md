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
