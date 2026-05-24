"""
Broadcastify stream capture pipeline.
Ingests a Broadcastify Premium audio feed via ffmpeg, segments it into
60-second chunks, runs Whisper transcription, parses for detector
announcements, archives useful audio, and deletes blank/silent chunks.
"""
import re
import configparser
import subprocess
import sqlite3
import time
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH
from transcribe import transcribe
from parser import parse_detector
from alerts import evaluate_detector_event
from direction import update_direction_for_event

# Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "broadcastify.ini"
AUDIO_DIR = BASE_DIR / "audio" / "stream"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = BASE_DIR / "audio" / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# Chunk size: 60s captures full detector announcements without breaking them
SEGMENT_SECONDS = 60
SOURCE_LABEL = "broadcastify_46721"
FREQUENCY_MHZ = 160.590


def load_credentials():
    parser = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        print(f"ERROR: config file not found at {CONFIG_PATH}", flush=True)
        sys.exit(1)
    parser.read(CONFIG_PATH)
    return (
        parser.get("broadcastify", "username"),
        parser.get("broadcastify", "password"),
        parser.get("broadcastify", "url"),
    )


def log_transmission(audio_path, transcript, frequency_mhz, duration, source):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    tagged_transcript = f"[{source}] {transcript}"
    cur.execute(
        """INSERT INTO transmissions
           (timestamp, frequency_mhz, duration_seconds, audio_path, transcript)
           VALUES (?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), frequency_mhz, duration, str(audio_path), tagged_transcript),
    )
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    return tid


def log_detector_event(parsed, transmission_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO detector_events
           (transmission_id, timestamp, railroad, subdivision, milepost,
            axle_count, train_length_feet, speed_mph, temperature_f,
            defects_detected, direction, raw_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            transmission_id,
            datetime.now().isoformat(),
            parsed.get("railroad"),
            "North End",
            parsed.get("milepost"),
            parsed.get("axle_count"),
            parsed.get("train_length_feet"),
            parsed.get("speed_mph"),
            parsed.get("temperature_f"),
            parsed.get("defects_detected", 0),
            None,
            parsed.get("raw_text"),
        ),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


# Phrases (lowercase, whitespace-collapsed) that mean the chunk is junk:
# silence, music, ads, or Whisper hallucination on noise.
JUNK_PHRASES = {
    "[blank_audio]",
    "[silence]",
    "(silence)",
    "(buzzing)",
    "[music playing]",
    "[music]",
    "(music)",
    "[applause]",
    "[laughter]",
    "[ pause ]",
    "[pause]",
    "(pause)",
    "scanning...",
    "you",
    "thank you",
    "thank you.",
    "thanks for watching",
    "thanks for watching.",
    "subscribe",
    "the.",
    "the",
    ".",
    "(sound of engine)",
}


def _strip_for_junk_check(text):
    """
    Normalize a transcript: lowercase, remove all bracketed/parenthetical
    sound tags, drop repeated 'you'/'the' tokens (Whisper silence
    hallucination). Returns whatever meaningful content remains.
    """
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"\([^\)]*\)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    tokens = t.split()
    filtered = [tok for tok in tokens if tok.strip(".,!?") not in ("you", "the", "")]
    return " ".join(filtered).strip()


def is_blank_or_junk(transcript):
    """Return True if transcript is silence, music, hallucination, or stream junk."""
    if not transcript:
        return True
    stripped = transcript.strip().lower()
    if len(stripped) < 5:
        return True
    collapsed = re.sub(r"\s+", " ", stripped)
    if collapsed in JUNK_PHRASES:
        return True
    # Multi-line junk: every non-empty line is a junk phrase
    lines = [ln.strip() for ln in stripped.split("\n") if ln.strip()]
    if lines and all(ln in JUNK_PHRASES for ln in lines):
        return True
    # If after stripping markers and silence-hallucinations nothing real remains
    meaningful = _strip_for_junk_check(transcript)
    if len(meaningful) < 8:
        return True
    return False


def process_chunk(wav_path):
    print(f"Processing {wav_path.name}", flush=True)
    transcript = transcribe(wav_path)

    if is_blank_or_junk(transcript):
        preview = (transcript or "empty").replace("\n", " ")[:60]
        print(f"  Deleting (blank/junk): {preview}", flush=True)
        try:
            wav_path.unlink()
        except Exception:
            pass
        return

    print(f"  Transcript: {transcript}", flush=True)

    # Archive
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived = ARCHIVE_DIR / f"stream_{ts}.wav"
    try:
        wav_path.rename(archived)
    except Exception as e:
        print(f"  Archive failed: {e}", flush=True)
        archived = wav_path

    tid = log_transmission(archived, transcript, FREQUENCY_MHZ, SEGMENT_SECONDS, SOURCE_LABEL)

    parsed = parse_detector(transcript)
    if parsed and parsed.get("milepost") is not None:
        eid = log_detector_event(parsed, tid)
        mp = parsed.get("milepost")
        print(f"  Logged detector event id={eid}, milepost={mp}", flush=True)
        direction, speed = update_direction_for_event(eid)
        print(f"  Inferred direction={direction}, speed={speed}", flush=True)
        evaluate_detector_event(eid)
    else:
        print(f"  No detector found in transcript", flush=True)


def run_stream_capture():
    username, password, url = load_credentials()

    if "://" not in url:
        print(f"ERROR: URL must include scheme: {url}", flush=True)
        sys.exit(1)
    scheme, rest = url.split("://", 1)
    auth_url = f"{scheme}://{username}:{password}@{rest}"

    print(f"Starting Broadcastify stream capture from feed {SOURCE_LABEL}...", flush=True)
    print(f"Segmenting into {SEGMENT_SECONDS}-second chunks in {AUDIO_DIR}", flush=True)

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-reconnect", "1",
        "-reconnect_at_eof", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "30",
        "-i", auth_url,
        "-f", "segment",
        "-segment_time", str(SEGMENT_SECONDS),
        "-ac", "1",
        "-ar", "22050",
        "-acodec", "pcm_s16le",
        "-reset_timestamps", "1",
        "-strftime", "1",
        str(AUDIO_DIR / "chunk_%Y%m%d_%H%M%S.wav"),
    ]

    ff = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print(f"ffmpeg started, PID {ff.pid}", flush=True)

    seen = set()
    try:
        while True:
            if ff.poll() is not None:
                err = ff.stderr.read().decode("utf-8", errors="ignore") if ff.stderr else ""
                print(f"ffmpeg exited with code {ff.returncode}: {err[:500]}", flush=True)
                print("Restarting ffmpeg in 10s...", flush=True)
                time.sleep(10)
                ff = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                print(f"ffmpeg restarted, PID {ff.pid}", flush=True)
                continue

            chunks = sorted(AUDIO_DIR.glob("chunk_*.wav"))
            for wav in chunks:
                if wav.name in seen:
                    continue
                try:
                    size1 = wav.stat().st_size
                except FileNotFoundError:
                    continue
                if size1 == 0:
                    continue
                time.sleep(2)
                try:
                    size2 = wav.stat().st_size
                except FileNotFoundError:
                    continue
                if size1 != size2:
                    continue
                # Skip the newest file in case ffmpeg is still writing it
                if wav == chunks[-1] and len(chunks) > 1:
                    continue
                seen.add(wav.name)
                process_chunk(wav)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nStopping stream capture...", flush=True)
    finally:
        try:
            ff.terminate()
            ff.wait(timeout=5)
        except Exception:
            ff.kill()


if __name__ == "__main__":
    run_stream_capture()
