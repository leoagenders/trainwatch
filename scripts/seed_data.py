"""Seed the database with detector locations and watch spots."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH

# CSX A-Line (North End Sub) detectors near Petersburg, VA
# Source: RadioReference ND-North End Sub
DETECTORS = [
    # (railroad, subdivision, milepost, latitude, longitude, description)
    ("CSX", "North End", 3.0, 37.4922, -77.4716, "Broad Rock detector (south Richmond)"),
    ("CSX", "North End", 17.4, 37.3014, -77.4032, "Petersburg detector (KBA440)"),
    ("CSX", "North End", 33.7, 37.0814, -77.4033, "Carson detector (KDX825)"),
    ("CSX", "North End", 58.2, 36.7487, -77.4942, "Emporia detector"),
]

# Your watch spots — places you might actually go to see trains
# milepost is approximate location on CSX A-Line (North End Sub)
# drive_time_minutes is from Fort Gregg-Adams area
WATCH_SPOTS = [
    # (name, railroad, subdivision, milepost, drive_time_min, lat, lon)
    ("Ettrick / Petersburg Amtrak", "CSX", "North End", 22.0, 15, 37.2389, -77.4361),
    ("Collier Yard north end", "CSX", "North End", 26.7, 18, 37.1850, -77.4150),
]

def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Wipe any existing seed data so we can re-run safely
    cur.execute("DELETE FROM detectors")
    cur.execute("DELETE FROM watch_spots")

    cur.executemany(
        "INSERT INTO detectors (railroad, subdivision, milepost, latitude, longitude, description) VALUES (?, ?, ?, ?, ?, ?)",
        DETECTORS,
    )
    cur.executemany(
        "INSERT INTO watch_spots (name, railroad, subdivision, milepost, drive_time_minutes, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?)",
        WATCH_SPOTS,
    )
    conn.commit()

    print(f"Seeded {len(DETECTORS)} detectors and {len(WATCH_SPOTS)} watch spots.")
    conn.close()

if __name__ == "__main__":
    seed()
