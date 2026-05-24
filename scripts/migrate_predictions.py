"""Add tables for passages, patterns, and prediction snapshots."""
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH

migration = """
CREATE TABLE IF NOT EXISTS train_passages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    railroad TEXT,
    subdivision TEXT,
    direction TEXT,
    axle_count INTEGER,
    train_length_feet INTEGER,
    avg_speed_mph REAL,
    detector_event_ids TEXT,
    pattern_id INTEGER,
    is_amtrak INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS train_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT,
    direction TEXT,
    typical_axle_count INTEGER,
    typical_length_feet INTEGER,
    typical_speed_mph REAL,
    observation_count INTEGER DEFAULT 0,
    first_observed TEXT,
    last_observed TEXT,
    typical_dow_mask TEXT,
    typical_hour_distribution TEXT,
    confidence REAL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS prediction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    predicted_probability REAL NOT NULL,
    confidence REAL,
    n_observations INTEGER,
    actual_observed INTEGER,
    scored_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_passages_first_seen ON train_passages(first_seen);
CREATE INDEX IF NOT EXISTS idx_passages_pattern ON train_passages(pattern_id);
CREATE INDEX IF NOT EXISTS idx_predictions_window ON prediction_snapshots(window_start, window_end);
"""

conn = sqlite3.connect(DB_PATH)
conn.executescript(migration)
conn.commit()
conn.close()
print("Migration applied.")
