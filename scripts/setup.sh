#!/usr/bin/env bash
# Prepare a fresh cloud container for the video editor, so a session can transcribe and
# render straight away: WhisperX (CPU-only PyTorch), the OpenCV tools venv, NLTK punkt_tab,
# and the large-v3-turbo + alignment model weights.
#
# Paste this whole file into the environment's Setup script (cloud environment menu > Edit),
# or run it by hand: bash scripts/setup.sh. Re-running skips whatever is already in place.
# VE_CACHE moves the venvs (default ~/.cache/video-editor).
set -euo pipefail

CACHE="${VE_CACHE:-$HOME/.cache/video-editor}"
PY=/usr/bin/python3.11
WX="$CACHE/whisperx-venv"
TOOLS="$CACHE/tools-venv"
mkdir -p "$CACHE"

# WhisperX. The CPU wheels of torch/torchaudio/torchvision satisfy whisperx's pins and skip
# ~3 GB of CUDA libraries this GPU-less container can't use. They are served from
# download-r2.pytorch.org; if the network policy blocks that host, fall back to PyPI's build.
if ! "$WX/bin/python" -c "import whisperx" 2>/dev/null; then
  uv venv -q --allow-existing -p "$PY" "$WX"
  VIRTUAL_ENV="$WX" uv pip install -q whisperx==3.8.6 \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match ||
  { echo "setup.sh: CPU-only torch unavailable (allow download-r2.pytorch.org); using PyPI's build"
    VIRTUAL_ENV="$WX" uv pip install -q whisperx==3.8.6; }
fi

# OpenCV 4 for face finding (OpenCV 5 dropped CascadeClassifier).
if ! "$TOOLS/bin/python" -c "import cv2; cv2.CascadeClassifier" 2>/dev/null; then
  uv venv -q --allow-existing -p "$PY" "$TOOLS"
  VIRTUAL_ENV="$TOOLS" uv pip install -q "opencv-python-headless<5" numpy
fi

# WhisperX alignment needs punkt_tab; NLTK's own downloader refuses to run through a proxy.
if [ ! -d "$HOME/nltk_data/tokenizers/punkt_tab" ]; then
  mkdir -p "$HOME/nltk_data/tokenizers"
  curl -sSfL -o "$HOME/nltk_data/tokenizers/punkt_tab.zip" \
    https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip
  "$PY" -m zipfile -e "$HOME/nltk_data/tokenizers/punkt_tab.zip" "$HOME/nltk_data/tokenizers"
  rm "$HOME/nltk_data/tokenizers/punkt_tab.zip"
fi

# Model weights (Hugging Face + download.pytorch.org). Not fatal: transcribe.py fetches
# them itself if this step is blocked.
"$WX/bin/python" - <<'EOF' || echo "setup.sh: model prefetch failed; transcribe.py will download on first use"
import faster_whisper.utils, whisperx
faster_whisper.utils.download_model("large-v3-turbo")
whisperx.load_align_model(language_code="en", device="cpu")
EOF

echo "setup.sh: ready ($WX, $TOOLS)"
