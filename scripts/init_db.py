import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trainwatch.db"

schema = """
CREATE TABLE IF NOT EXISTS transmissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    frequency_mhz REAL NOT NULL,
    duration_seconds REAL,
    audio_path TEXT,
    transcript TEXT,
    confidence REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS detector_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transmission_id INTEGER,
    timestamp TEXT NOT NULL,
    railroad TEXT,
    milepost REAL,
    subdivision TEXT,
    axle_count INTEGER,
    train_length_feet INTEGER,
    speed_mph REAL,
    temperature_f REAL,
    defects_detected INTEGER DEFAULT 0,
    direction TEXT,
    raw_text TEXT,
    FOREIGN KEY (transmission_id) REFERENCES transmissions(id)
);

CREATE TABLE IF NOT EXISTS detectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    railroad TEXT NOT NULL,
    subdivision TEXT,
    milepost REAL NOT NULL,
    latitude REAL,
    longitude REAL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS watch_spots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    railroad TEXT,
    subdivision TEXT,
    milepost REAL,
    drive_time_minutes INTEGER,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detector_event_id INTEGER,
    watch_spot_id INTEGER,
    alert_sent_at TEXT NOT NULL,
    predicted_arrival TEXT,
    confirmed_seen INTEGER DEFAULT NULL,
    notes TEXT,
    FOREIGN KEY (detector_event_id) REFERENCES detector_events(id),
    FOREIGN KEY (watch_spot_id) REFERENCES watch_spots(id)
);

CREATE INDEX IF NOT EXISTS idx_transmissions_timestamp ON transmissions(timestamp);
CREATE INDEX IF NOT EXISTS idx_detector_events_timestamp ON detector_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_detector_events_milepost ON detector_events(milepost);
"""

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(DB_PATH)
conn.executescript(schema)
conn.commit()
conn.close()
print(f"Database initialized at {DB_PATH}")
