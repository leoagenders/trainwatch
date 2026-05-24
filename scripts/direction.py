"""Direction inference: figure out N/S from detector firing sequence."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH

# How far back to look for matching detector hits (minutes).
# Trains take ~30-60 min to cross our monitored stretch (Broad Rock to Carson is 30mi).
LOOKBACK_MINUTES = 90

# How close axle counts and lengths must match to count as "same train".
# Defect detectors are usually exact, but transcription errors might shift digits.
AXLE_TOLERANCE = 4
LENGTH_TOLERANCE_FEET = 200


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_prior_match(event):
    """
    Look for a recent detector event that's likely the same train.
    Returns the matching prior event row, or None.
    """
    conn = get_db()
    cutoff = (datetime.fromisoformat(event["timestamp"]) - timedelta(minutes=LOOKBACK_MINUTES)).isoformat()

    # Find candidates: same railroad, same subdivision, recent, different milepost
    candidates = conn.execute(
        """SELECT * FROM detector_events
           WHERE railroad = ?
             AND subdivision = ?
             AND timestamp > ?
             AND timestamp < ?
             AND id != ?
             AND milepost != ?
           ORDER BY timestamp DESC""",
        (
            event["railroad"], event["subdivision"],
            cutoff, event["timestamp"],
            event["id"], event["milepost"],
        ),
    ).fetchall()
    conn.close()

    if not candidates:
        return None

    # Score each candidate by how well its train fingerprint matches
    best = None
    best_score = -1
    for c in candidates:
        score = 0
        if event["axle_count"] and c["axle_count"]:
            if abs(event["axle_count"] - c["axle_count"]) <= AXLE_TOLERANCE:
                score += 2
            else:
                continue  # axle mismatch is disqualifying
        if event["train_length_feet"] and c["train_length_feet"]:
            if abs(event["train_length_feet"] - c["train_length_feet"]) <= LENGTH_TOLERANCE_FEET:
                score += 2
            else:
                continue  # length mismatch disqualifying
        # Time proximity: closer in time = more likely same train
        dt = (datetime.fromisoformat(event["timestamp"])
              - datetime.fromisoformat(c["timestamp"])).total_seconds() / 60
        if dt > 0 and dt < LOOKBACK_MINUTES:
            score += max(0, 2 - dt / 30)  # diminishing
        if score > best_score:
            best_score = score
            best = c

    # Require minimum score to claim a match
    if best_score >= 2:
        return best
    return None


def infer_direction(event):
    """
    Determine if this event represents a northbound or southbound train.
    Returns 'N', 'S', or None.

    Mileposts on CSX A-Line North End Sub increase southbound from Richmond.
    So if prior event has lower milepost than current -> southbound (S).
    If prior event has higher milepost than current -> northbound (N).
    """
    if event.get("direction") in ("N", "S"):
        # Already known (e.g., from simulation or manual entry)
        return event["direction"]

    prior = find_prior_match(event)
    if prior is None:
        return None

    if prior["milepost"] < event["milepost"]:
        return "S"
    elif prior["milepost"] > event["milepost"]:
        return "N"
    return None


def calculate_speed_between(event, prior):
    """
    Given two detector events for the same train, calculate average mph
    between them. Returns mph or None.
    """
    if not prior:
        return None
    distance = abs(event["milepost"] - prior["milepost"])
    t1 = datetime.fromisoformat(event["timestamp"])
    t2 = datetime.fromisoformat(prior["timestamp"])
    hours = abs((t1 - t2).total_seconds()) / 3600
    if hours <= 0:
        return None
    return distance / hours


def update_direction_for_event(event_id):
    """
    Look up an event by id, infer its direction (and possibly improve speed
    from inter-detector calculation), and update the database row.
    Returns the (direction, speed) tuple after update.
    """
    conn = get_db()
    event = conn.execute(
        "SELECT * FROM detector_events WHERE id = ?", (event_id,)
    ).fetchone()
    if event is None:
        conn.close()
        return None, None

    event_dict = dict(event)
    direction = infer_direction(event_dict)

    prior = find_prior_match(event_dict) if direction else None
    inter_speed = calculate_speed_between(event_dict, prior) if prior else None

    # Only update direction if we discovered something
    if direction and direction != event["direction"]:
        conn.execute(
            "UPDATE detector_events SET direction = ? WHERE id = ?",
            (direction, event_id),
        )

    # If we computed an inter-detector speed and current speed is missing or wildly off,
    # use the inter-detector speed (more reliable than transcribed announcement)
    final_speed = event["speed_mph"]
    if inter_speed and (event["speed_mph"] is None or
                        abs(inter_speed - (event["speed_mph"] or 0)) > 15):
        conn.execute(
            "UPDATE detector_events SET speed_mph = ? WHERE id = ?",
            (round(inter_speed, 1), event_id),
        )
        final_speed = round(inter_speed, 1)

    conn.commit()
    conn.close()
    return direction, final_speed


if __name__ == "__main__":
    # Smoke test against existing simulated events in the database
    conn = get_db()
    events = conn.execute(
        "SELECT id FROM detector_events ORDER BY id"
    ).fetchall()
    conn.close()
    for row in events:
        d, s = update_direction_for_event(row["id"])
        print(f"Event {row['id']}: direction={d}, speed={s}")
