"""
Schedule background WAV recordings around Amtrak arrival times.

Usage:
    python scripts/schedule_recordings.py

Reads a list of (train_name, arrival_datetime) and creates 'at' jobs that
trigger recordings 15 minutes before each arrival, lasting 30 minutes.
Overlapping windows are merged.
"""
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
FREQUENCY_HZ = 160_590_000
GAIN = 40
SAMPLE_RATE = 22050
PRE_MINUTES = 15   # start this many min before scheduled time
POST_MINUTES = 15  # keep recording this many min after scheduled time
                   # (so total default window is 30 min)
RECORDINGS_DIR = Path.home() / "trainwatch" / "audio" / "scheduled"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Paste your schedule here -- (train name, scheduled datetime ISO format)
# These are arrival times at Petersburg (PTB)
SCHEDULE = [
    ("NER_87",        "2026-05-16T21:56"),
    ("SilverMeteor_97","2026-05-16T22:21"),
    ("SilverMeteor_98","2026-05-17T02:50"),
    ("Floridian_40",  "2026-05-17T12:02"),
    ("Floridian_41",  "2026-05-17T16:41"),
]


def parse_iso(s):
    return datetime.fromisoformat(s)


def build_windows(schedule):
    """Convert (name, time) entries into (start, end, names) windows,
    merging overlapping ones."""
    windows = []
    for name, t in schedule:
        sched = parse_iso(t)
        start = sched - timedelta(minutes=PRE_MINUTES)
        end = sched + timedelta(minutes=POST_MINUTES)
        windows.append([start, end, [name]])

    # Sort and merge overlapping
    windows.sort(key=lambda w: w[0])
    merged = [windows[0]]
    for w in windows[1:]:
        if w[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], w[1])
            merged[-1][2].extend(w[2])
        else:
            merged.append(w)
    return merged


def schedule_recording(start, end, names):
    """Schedule an `at` job that records audio from start to end."""
    duration_seconds = int((end - start).total_seconds())
    label = "_".join(names)
    out_path = RECORDINGS_DIR / f"{start.strftime('%Y%m%d_%H%M')}_{label}.wav"

    # Build the command that will run at the scheduled time
    cmd = (
        f"timeout {duration_seconds} "
        f"rtl_fm -f {FREQUENCY_HZ} -M fm -s {SAMPLE_RATE} "
        f"-l 0 -g {GAIN} - 2>/dev/null | "
        f"sox -t raw -r {SAMPLE_RATE} -b 16 -e signed -c 1 - "
        f"'{out_path}'"
    )

    # Don't schedule jobs in the past
    if start < datetime.now():
        print(f"SKIP (past): {start} {label}")
        return

    # at-format time string: "HH:MM YYYY-MM-DD"
    at_time = start.strftime("%H:%M %Y-%m-%d")

    # Submit to `at`
    proc = subprocess.run(
        ["at", at_time],
        input=cmd,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        print(f"SCHEDULED: {start.strftime('%a %H:%M')} -> {end.strftime('%H:%M')} "
              f"({duration_seconds//60}min) for {label}")
    else:
        print(f"FAILED to schedule {label}: {proc.stderr.strip()}")


def main():
    windows = build_windows(SCHEDULE)
    print(f"Built {len(windows)} recording windows from {len(SCHEDULE)} train events:")
    for start, end, names in windows:
        schedule_recording(start, end, names)
    print("\nView scheduled jobs with: atq")
    print("Cancel a job with: atrm <jobnumber>")
    print(f"Recordings will appear in: {RECORDINGS_DIR}")


if __name__ == "__main__":
    main()
