"""
Whisper transcription wrapper for railroad audio.
Uses whisper.cpp with a railroad-biased prompt to improve recognition of
detector announcements, mileposts, and standard railroad terminology.
"""
import subprocess
from pathlib import Path

WHISPER_CLI = Path("/home/fefifofum/whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL = Path("/home/fefifofum/whisper.cpp/models/ggml-base.en.bin")

# Prompt biases Whisper toward railroad terminology. Examples of decimal
# mileposts help it punctuate numbers like "forty six point eight" as
# "46.8" instead of "4, 6.8". Including specific detector mileposts on
# this line helps even more.
RAILROAD_PROMPT = (
    "CSX detector, milepost 17.4, milepost 33.7, milepost 46.8, milepost 58.2. "
    "No defects, repeat no defects. Total axles 480. Train length 6800 feet. "
    "Speed 47 miles per hour. Temperature 72 degrees. Detector out. "
    "Norfolk Southern, Amtrak, dispatcher. Track one, track two."
)


def transcribe(wav_path):
    """Transcribe a WAV file via whisper.cpp. Returns the transcript text or empty string."""
    out_base = "/tmp/whisper_out"
    try:
        result = subprocess.run(
            [
                str(WHISPER_CLI),
                "-m", str(WHISPER_MODEL),
                "-f", str(wav_path),
                "--prompt", RAILROAD_PROMPT,
                "-nt",  # no timestamps
                "-otxt", "-of", out_base,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  whisper-cli failed: {result.stderr[:200]}", flush=True)
            return ""
        out_file = Path(out_base + ".txt")
        if out_file.exists():
            transcript = out_file.read_text().strip()
            try:
                out_file.unlink()
            except Exception:
                pass
            return transcript
        return ""
    except subprocess.TimeoutExpired:
        print(f"  whisper-cli timed out on {wav_path.name}", flush=True)
        return ""
    except Exception as e:
        print(f"  whisper-cli error: {e}", flush=True)
        return ""
