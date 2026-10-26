"""Word-level transcripts for several short clips, loading WhisperX once.

Usage: ~/.cache/video-editor/whisperx-venv/bin/python scripts/transcribe_many.py <clip.mp4>...
Writes <clip>.words.json next to each clip (same shape as transcript/words.json) and
skips clips that already have one.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")


def main() -> None:
    import whisperx

    clips = [Path(p) for p in sys.argv[1:] if not Path(p).with_suffix(".words.json").exists()]
    if not clips:
        return
    model = whisperx.load_model("large-v3", "cpu", compute_type="int8", language="en")
    align, meta = whisperx.load_align_model(language_code="en", device="cpu")
    for clip in clips:
        wav = clip.with_suffix(".wav")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(clip), "-vn", "-ac", "1",
                        "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
        audio = whisperx.load_audio(str(wav))
        result = model.transcribe(audio, batch_size=8, language="en")
        aligned = whisperx.align(result["segments"], align, meta, audio, "cpu",
                                 return_char_alignments=False)
        words = [{k: w[k] for k in ("word", "start", "end", "score") if k in w}
                 for seg in aligned["segments"] for w in seg.get("words", [])]
        clip.with_suffix(".words.json").write_text(json.dumps({
            "source": clip.name,
            "segments": [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                         for s in aligned["segments"]],
            "words": words}, indent=1, ensure_ascii=False))
        print(f"{clip.name}: {len(words)} words", flush=True)


if __name__ == "__main__":
    main()
