"""
Re-run the parser over all existing detector events using their stored
transcripts. Updates any rows where the new parser extracts data the
old parser missed (axles, length, speed, temp, etc.).
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH
from parser import parse_detector


def backfill():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT d.id, d.milepost, d.axle_count, d.train_length_feet,
               d.speed_mph, d.temperature_f, d.defects_detected,
               t.transcript
        FROM detector_events d
        INNER JOIN transmissions t ON t.id = d.transmission_id
    """)
    rows = cur.fetchall()

    updated = 0
    for row in rows:
        # Strip the source tag
        transcript = row["transcript"]
        if "] " in transcript:
            transcript = transcript.split("] ", 1)[1]
        parsed = parse_detector(transcript)
        if not parsed:
            continue

        # Build update for any newly-extracted field
        changes = {}
        for field in ("milepost", "axle_count", "train_length_feet",
                      "speed_mph", "temperature_f"):
            new_val = parsed.get(field)
            old_val = row[field]
            if new_val is not None and old_val is None:
                changes[field] = new_val

        if changes:
            set_clause = ", ".join(f"{k} = ?" for k in changes)
            values = list(changes.values()) + [row["id"]]
            cur.execute(f"UPDATE detector_events SET {set_clause} WHERE id = ?", values)
            updated += 1
            print(f"Event {row['id']}: {changes}")

    conn.commit()
    conn.close()
    print(f"\nUpdated {updated} of {len(rows)} detector events")


if __name__ == "__main__":
    backfill()
