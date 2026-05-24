"""
Audio capture pipeline: rtl_fm -> sox VAD segmenting -> Whisper -> parser
-> direction inference -> alerts. Archives each processed clip with a
timestamped filename so the dashboard can play it back later.
"""
import subprocess
import sqlite3
import time
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH, FREQUENCIES, SAMPLE_RATE
from transcribe import transcribe
from parser import parse_detector
from alerts import evaluate_detector_event
from direction import update_direction_for_event

AUDIO_DIR = Path(__file__).parent.parent / "audio"
AUDIO_DIR.mkdir(exist_ok=True)
ARCHIVE_DIR = AUDIO_DIR / "archive"
ARCHIVE_DIR.mkdir(exist_ok=True)

FREQUENCY_HZ = int(FREQUENCIES["CSX_A_LINE"] * 1_000_000)
FREQUENCY_LABEL = "CSX_A_LINE"


def log_transmission(audio_path, transcript, frequency_mhz, duration):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO transmissions
           (timestamp, frequency_mhz, duration_seconds, audio_path, transcript)
           VALUES (?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), frequency_mhz, duration, str(audio_path), transcript),
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


def process_clip(wav_path):
    print(f"Processing {wav_path.name}", flush=True)
    transcript = transcribe(wav_path)
    if not transcript:
        print("  No transcript, skipping", flush=True)
        try:
            wav_path.unlink()
        except Exception:
            pass
        return

    print(f"  Transcript: {transcript}", flush=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived = ARCHIVE_DIR / f"clip_{ts}.wav"
    try:
        wav_path.rename(archived)
    except Exception as e:
        print(f"  Failed to archive: {e}", flush=True)
        archived = wav_path

    duration = 0
    tid = log_transmission(archived, transcript, FREQUENCY_HZ / 1_000_000, duration)

    parsed = parse_detector(transcript)
    if parsed and parsed.get("milepost") is not None:
        eid = log_detector_event(parsed, tid)
        print(f"  Logged detector event id={eid}, milepost={parsed['milepost']}", flush=True)
        direction, speed = update_direction_for_event(eid)
        print(f"  Inferred direction={direction}, speed={speed}", flush=True)
        evaluate_detector_event(eid)
    else:
        print(f"  No detector found in transcript", flush=True)


def run_capture():
    rtl_cmd = [
        "rtl_fm",
        "-f", str(FREQUENCY_HZ),
        "-M", "fm",
        "-s", "22050",
        "-l", "100",
        "-g", "49.6",
        "-",
    ]
    sox_cmd = [
        "sox",
        "-t", "raw", "-r", "22050", "-b", "16", "-e", "signed", "-c", "1",
        "-",
        str(AUDIO_DIR / "clip.wav"),
        "silence", "1", "0.2", "0.3%",
        "1", "1.0", "0.3%",
        ":", "newfile", ":", "restart",
    ]

    print(f"Starting capture at {FREQUENCY_HZ/1_000_000:.3f} MHz...", flush=True)
    rtl = subprocess.Popen(rtl_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    sox = subprocess.Popen(sox_cmd, stdin=rtl.stdout, stderr=subprocess.DEVNULL)

    seen = set()
    print(f"Watching {AUDIO_DIR} for clip*.wav files...", flush=True)
    try:
        while True:
            wavs = sorted(AUDIO_DIR.glob("clip*.wav"))
            for wav in wavs:
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
                print(f"New stable file: {wav.name} ({size2} bytes)", flush=True)
                seen.add(wav.name)
                process_clip(wav)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nStopping capture...", flush=True)
    finally:
        rtl.terminate()
        sox.terminate()


if __name__ == "__main__":
    run_capture()
