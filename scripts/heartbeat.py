"""
Daily heartbeat ping via ntfy. Summarizes the last 24 hours of activity
so you can confirm the system is alive without checking the dashboard.
"""
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH, NTFY_TOPIC

NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def query_count(conn, sql, args=()):
    cur = conn.execute(sql, args)
    return cur.fetchone()[0]


def build_summary():
    conn = sqlite3.connect(DB_PATH)
    yesterday = (datetime.now() - timedelta(hours=24)).isoformat()

    tx_24h = query_count(conn, "SELECT COUNT(*) FROM transmissions WHERE timestamp > ?", (yesterday,))
    det_24h = query_count(conn, "SELECT COUNT(*) FROM detector_events WHERE timestamp > ?", (yesterday,))
    alert_24h = query_count(conn, "SELECT COUNT(*) FROM alerts WHERE alert_sent_at > ?", (yesterday,))
    tx_total = query_count(conn, "SELECT COUNT(*) FROM transmissions")
    det_total = query_count(conn, "SELECT COUNT(*) FROM detector_events")

    cur = conn.execute(
        "SELECT milepost, COUNT(*) FROM detector_events "
        "WHERE timestamp > ? GROUP BY milepost ORDER BY milepost",
        (yesterday,),
    )
    by_mp = cur.fetchall()
    conn.close()

    mp_str = ", ".join(f"MP{mp}:{n}" for mp, n in by_mp) if by_mp else "none"

    body = (
        f"Last 24h:\n"
        f"  {tx_24h} transmissions\n"
        f"  {det_24h} detector events ({mp_str})\n"
        f"  {alert_24h} alerts sent\n"
        f"\n"
        f"All-time: {tx_total} transmissions, {det_total} detector events"
    )
    return body


def send_heartbeat():
    body = build_summary()
    title = f"Trainwatch alive - {datetime.now().strftime('%a %b %d')}"
    req = urllib.request.Request(
        NTFY_URL,
        data=body.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "default",
            "Tags": "wave",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"Heartbeat sent: {title}")
        print(body)
    except Exception as e:
        print(f"Failed to send heartbeat: {e}")


if __name__ == "__main__":
    send_heartbeat()
