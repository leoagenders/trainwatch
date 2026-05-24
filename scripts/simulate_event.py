"""Simulate detector events for testing the alert pipeline."""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH
from alerts import evaluate_detector_event


def simulate(railroad="CSX", subdivision="North End", milepost=17.4,
             direction="S", speed_mph=42, axle_count=380,
             train_length_feet=6800, temperature_f=58, label=""):
    """Insert a fake detector event and run alert evaluation against it."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO detector_events
           (timestamp, railroad, subdivision, milepost, axle_count,
            train_length_feet, speed_mph, temperature_f, direction, raw_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            railroad, subdivision, milepost,
            axle_count, train_length_feet, speed_mph,
            temperature_f, direction,
            f"[SIMULATED EVENT{': ' + label if label else ''}]",
        ),
    )
    event_id = cur.lastrowid
    conn.commit()
    conn.close()

    print(f"Simulated event id={event_id}: "
          f"{railroad} MP {milepost} {direction}-bound at {speed_mph} mph")
    print("Running alert evaluation...")
    fired = evaluate_detector_event(event_id)
    if fired:
        print(f"Alerts fired for: {', '.join(fired)}")
    else:
        print("No alerts fired (no watch spots in path or warning too short/long)")


if __name__ == "__main__":
    print("\n=== Test 1: Southbound at Petersburg detector (MP 17.4), 42 mph ===")
    print("(Expected: SUPPRESSED -- detector too close, train will beat you there)")
    simulate(milepost=17.4, direction="S", speed_mph=42,
             label="petersburg southbound 42mph")

    print("\n=== Test 2: Northbound at Carson detector (MP 33.7), 38 mph ===")
    print("(Expected: SUPPRESSED -- only ~4.5 min warning after drive time)")
    simulate(milepost=33.7, direction="N", speed_mph=38,
             label="carson northbound 38mph")

    print("\n=== Test 3: Southbound at Broad Rock (MP 3.0), 50 mph ===")
    print("(Expected: ALERT FIRES -- ~9 min warning, phone should buzz)")
    simulate(milepost=3.0, direction="S", speed_mph=50,
             label="broad rock southbound 50mph")

    print("\n=== Test 4: Northbound at Petersburg detector (MP 17.4), 40 mph ===")
    print("(Expected: NO ALERT -- train going wrong direction, already past spot)")
    simulate(milepost=17.4, direction="N", speed_mph=40,
             label="petersburg northbound wrong way")

    print("\n=== Test 5: Slower northbound at Carson (MP 33.7), 25 mph ===")
    print("(Expected: ALERT FIRES -- slower train means more warning time)")
    simulate(milepost=33.7, direction="N", speed_mph=25,
             label="carson northbound 25mph")
