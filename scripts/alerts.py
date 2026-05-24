"""Alert logic: decide when to notify, calculate ETA, send push."""
import sqlite3
import requests
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH, NTFY_URL

# Minimum warning time we care about. If we have less than this until the train
# reaches the spot, don't bother alerting -- you can't make it.
MIN_WARNING_MINUTES = 8

# Maximum warning time. If a detector is far enough away that ETA is huge,
# the prediction is probably unreliable.
MAX_WARNING_MINUTES = 60


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_eta_minutes(detector_milepost, spot_milepost, speed_mph, direction):
    """
    Given a detector firing, how long until the train reaches the watch spot?
    Returns minutes (float) or None if the train is going the wrong way.

    On the CSX A-Line, milepost increases southbound from Richmond.
    direction = 'S' means southbound (milepost increasing).
    direction = 'N' means northbound (milepost decreasing).
    """
    if speed_mph is None or speed_mph < 5:
        # No speed info or stopped train -- assume average freight speed
        speed_mph = 35

    distance_miles = spot_milepost - detector_milepost

    if direction == "S" and distance_miles > 0:
        # Southbound, spot is south of detector -- train is coming
        pass
    elif direction == "N" and distance_miles < 0:
        # Northbound, spot is north of detector -- train is coming
        distance_miles = abs(distance_miles)
    else:
        # Wrong direction -- train already past spot, or going away
        return None

    eta_hours = distance_miles / speed_mph
    return eta_hours * 60


def evaluate_detector_event(event_id):
    """
    Given the ID of a freshly-logged detector_event, check all watch_spots,
    fire alerts for spots that are reachable in time.
    """
    conn = get_db()
    event = conn.execute(
        "SELECT * FROM detector_events WHERE id = ?", (event_id,)
    ).fetchone()

    if event is None:
        print(f"No detector event with id {event_id}")
        conn.close()
        return

    spots = conn.execute(
        "SELECT * FROM watch_spots WHERE railroad = ? AND subdivision = ?",
        (event["railroad"], event["subdivision"]),
    ).fetchall()

    alerts_fired = []

    for spot in spots:
        eta = calculate_eta_minutes(
            event["milepost"],
            spot["milepost"],
            event["speed_mph"],
            event["direction"],
        )

        if eta is None:
            continue

        drive_time = spot["drive_time_minutes"] or 0
        warning_time = eta - drive_time

        if warning_time < MIN_WARNING_MINUTES:
            print(f"  Spot '{spot['name']}': only {warning_time:.1f} min warning -- too late")
            continue
        if warning_time > MAX_WARNING_MINUTES:
            print(f"  Spot '{spot['name']}': {warning_time:.1f} min -- probably unreliable")
            continue

        # Good alert
        arrival = datetime.now() + timedelta(minutes=eta)
        msg = (
            f"{event['railroad']} train approaching {spot['name']}\n"
            f"ETA at spot: {arrival.strftime('%-I:%M %p')} ({eta:.0f} min)\n"
            f"Drive time: {drive_time} min, warning: {warning_time:.0f} min\n"
            f"Direction: {event['direction']}, Speed: {event['speed_mph'] or '?'} mph\n"
            f"Length: {event['train_length_feet'] or '?'} ft, {event['axle_count'] or '?'} axles"
        )

        send_notification(msg, title=f"Train inbound: {warning_time:.0f} min")

        # Log the alert
        conn.execute(
            """INSERT INTO alerts
               (detector_event_id, watch_spot_id, alert_sent_at, predicted_arrival)
               VALUES (?, ?, ?, ?)""",
            (event_id, spot["id"], datetime.now().isoformat(), arrival.isoformat()),
        )
        conn.commit()
        alerts_fired.append(spot["name"])

    conn.close()
    return alerts_fired


def send_notification(message, title="Trainwatch"):
    """Push a notification via ntfy."""
    try:
        # ntfy headers must be ASCII; strip non-ASCII chars from title
        safe_title = title.encode("ascii", "ignore").decode("ascii")
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": safe_title,
                "Priority": "default",
                "Tags": "steam_locomotive",
            },
            timeout=5,
        )
        print(f"Sent notification: {safe_title}")
    except Exception as e:
        print(f"Failed to send notification: {e}")


if __name__ == "__main__":
    # Quick smoke test
    send_notification("Alert system online", title="Trainwatch test")
