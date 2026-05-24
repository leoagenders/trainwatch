"""Simulate a realistic train passing two detectors in sequence,
without specifying direction. Direction inference should figure it out."""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH
from alerts import evaluate_detector_event
from direction import update_direction_for_event


def insert_event(timestamp, railroad, subdivision, milepost,
                 axle_count, train_length_feet, speed_mph,
                 temperature_f, direction=None, label=""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO detector_events
           (timestamp, railroad, subdivision, milepost, axle_count,
            train_length_feet, speed_mph, temperature_f, direction, raw_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            timestamp, railroad, subdivision, milepost,
            axle_count, train_length_feet, speed_mph,
            temperature_f, direction,
            f"[SEQUENCE: {label}]" if label else "[SEQUENCE TEST]",
        ),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def run_sequence_test():
    """
    Simulate a southbound train -- 432 axles, 7200 ft, ~50 mph --
    hitting Broad Rock (MP 3.0) at T-18min, then Petersburg (MP 17.4) at T=0.
    No direction specified. We should infer S after the second detector fires.

    Then a different northbound train: 280 axles, 5400 ft, hitting
    Carson (MP 33.7), then Petersburg (MP 17.4).
    """
    now = datetime.now()
    t1 = (now - timedelta(minutes=18)).isoformat()
    t2 = now.isoformat()

    print("=== Simulating SOUTHBOUND train via two detectors ===")
    print(f"  Train: 432 axles, 7200 ft, ~50 mph")

    print(f"\n  T-18min: Broad Rock detector (MP 3.0) fires")
    e1 = insert_event(
        t1, "CSX", "North End", 3.0,
        432, 7200, 50, 60, direction=None, label="broadrock first hit",
    )
    print(f"    Event id={e1}")
    d1, s1 = update_direction_for_event(e1)
    print(f"    After inference: direction={d1}, speed={s1}")
    print(f"    (Expected: direction=None -- no prior detector to compare)")
    evaluate_detector_event(e1)

    print(f"\n  T=0: Petersburg detector (MP 17.4) fires for same train")
    e2 = insert_event(
        t2, "CSX", "North End", 17.4,
        432, 7200, 48, 61, direction=None, label="petersburg second hit",
    )
    print(f"    Event id={e2}")
    d2, s2 = update_direction_for_event(e2)
    print(f"    After inference: direction={d2}, speed={s2}")
    print(f"    (Expected: direction=S, speed ~48 mph)")
    evaluate_detector_event(e2)

    print("\n=== Simulating NORTHBOUND train ~25 min later ===")
    print(f"  Different train: 280 axles, 5400 ft, ~42 mph")
    t3 = (now + timedelta(minutes=25)).isoformat()
    t4 = (now + timedelta(minutes=46)).isoformat()

    print(f"\n  T+25min: Carson detector (MP 33.7) fires")
    e3 = insert_event(
        t3, "CSX", "North End", 33.7,
        280, 5400, 42, 62, direction=None, label="carson nb first",
    )
    print(f"    Event id={e3}")
    d3, s3 = update_direction_for_event(e3)
    print(f"    After inference: direction={d3}, speed={s3}")
    print(f"    (Expected: direction=None -- no prior detector for this train)")
    evaluate_detector_event(e3)

    print(f"\n  T+46min: Petersburg detector (MP 17.4) fires for same train")
    e4 = insert_event(
        t4, "CSX", "North End", 17.4,
        280, 5400, 40, 62, direction=None, label="petersburg nb second",
    )
    print(f"    Event id={e4}")
    d4, s4 = update_direction_for_event(e4)
    print(f"    After inference: direction={d4}, speed={s4}")
    print(f"    (Expected: direction=N, speed inferred from inter-detector time)")
    evaluate_detector_event(e4)


if __name__ == "__main__":
    run_sequence_test()
