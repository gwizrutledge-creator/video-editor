"""Transcribe the raw clip with WhisperX (large-v3, word-level alignment).

Usage: ~/.cache/video-editor/whisperx-venv/bin/python scripts/transcribe.py raw/<clip> [out_dir]
Set WHISPER_MODEL to use another model (e.g. large-v3-turbo, ~4x faster on CPU).
Writes audio.wav (16 kHz mono) and words.json to out_dir (default transcript/).
Skips the work if words.json already exists for the same footage.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "transcript"
MODEL = os.environ.get("WHISPER_MODEL", "large-v3")


def fingerprint(path: Path) -> str:
    # Size plus the first and last 8 MB: fast and unique enough for footage.
    h = hashlib.sha256(str(path.stat().st_size).encode())
    with path.open("rb") as f:
        h.update(f.read(8 << 20))
        f.seek(max(0, path.stat().st_size - (8 << 20)))
        h.update(f.read(8 << 20))
    return h.hexdigest()


def main() -> None:
    raw = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else OUT
    fp = fingerprint(raw)
    words_path = out / "words.json"
    if words_path.exists() and json.loads(words_path.read_text()).get("fingerprint") == fp:
        print(f"{words_path} already holds this footage; not transcribing again.")
        return

    out.mkdir(parents=True, exist_ok=True)
    wav = out / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )

    import torch
    import whisperx

    device, compute = ("cuda", "float16") if torch.cuda.is_available() else ("cpu", "int8")
    audio = whisperx.load_audio(str(wav))
    # The unaligned result is cached so a failed alignment doesn't cost a re-transcription.
    asr_path = out / "asr.json"
    asr = json.loads(asr_path.read_text()) if asr_path.exists() else {}
    if asr.get("fingerprint") == fp and asr.get("model") == MODEL:
        result, device, compute = asr["result"], asr["device"], asr["compute"]
        print(f"Reusing {asr_path} ({MODEL}); aligning only.")
    else:
        try:
            model = whisperx.load_model(MODEL, device, compute_type=compute)
            result = model.transcribe(audio, batch_size=8 if device == "cpu" else 16)
        except RuntimeError as e:
            if device != "cuda":
                raise
            print(f"CUDA failed ({e}); falling back to CPU int8.")
            device, compute = "cpu", "int8"
            model = whisperx.load_model(MODEL, device, compute_type=compute)
            result = model.transcribe(audio, batch_size=8)
        asr_path.write_text(json.dumps({"fingerprint": fp, "model": MODEL, "device": device,
                                        "compute": compute, "result": result},
                                       ensure_ascii=False))

    lang = result["language"]
    align_model, meta = whisperx.load_align_model(language_code=lang, device=device)
    aligned = whisperx.align(result["segments"], align_model, meta, audio, device,
                             return_char_alignments=False)

    words = []
    for seg in aligned["segments"]:
        for w in seg.get("words", []):
            words.append({k: w[k] for k in ("word", "start", "end", "score") if k in w})

    words_path.write_text(json.dumps({
        "source": raw.name,
        "fingerprint": fp,
        "language": lang,
        "model": MODEL,
        "device": f"{device}/{compute}",
        "segments": [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                     for s in aligned["segments"]],
        "words": words,
    }, indent=1, ensure_ascii=False))
    print(f"Wrote {words_path}: {len(words)} words, language {lang}, {device}/{compute}.")


if __name__ == "__main__":
    main()
