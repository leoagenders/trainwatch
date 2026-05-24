from flask import Flask, render_template_string, jsonify, redirect, url_for, send_from_directory, abort
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from config import DB_PATH

AUDIO_ROOT = Path(__file__).parent.parent / "audio"

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query_db(query, args=(), one=False):
    conn = get_db()
    cur = conn.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Trainwatch</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; max-width: 900px; margin: 1em auto; padding: 0 1em; background: #1a1a1a; color: #eee; }
        h1 { color: #4af; margin-bottom: 0.2em; }
        h2 { color: #8cf; border-bottom: 1px solid #333; padding-bottom: 0.3em; margin-top: 2em; }
        .meta { color: #888; font-size: 0.85em; margin-bottom: 1.5em; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.5em; }
        .stat { background: #2a2a2a; padding: 0.7em 1em; border-radius: 8px; }
        .stat-label { color: #aaa; font-size: 0.8em; }
        .stat-num { font-size: 1.6em; color: #4af; font-weight: bold; }
        .event, .alert-row, .tx { border-left: 3px solid #4af; padding: 0.6em 1em; margin: 0.4em 0; background: #2a2a2a; border-radius: 0 8px 8px 0; }
        .alert-row { border-left-color: #fa4; }
        .tx { border-left-color: #6c6; }
        .tx.detector { border-left-color: #4af; }
        .saw { border-left-color: #4f4; opacity: 0.75; }
        .missed { border-left-color: #f44; opacity: 0.75; }
        .dismissed { border-left-color: #888; opacity: 0.6; }
        time { color: #888; font-size: 0.85em; }
        .transcript { color: #ddd; margin-top: 0.3em; font-family: monospace; font-size: 0.9em; }
        audio { width: 100%; margin-top: 0.5em; height: 36px; }
        .feedback { margin-top: 0.5em; }
        .btn { background: #333; color: #eee; border: 1px solid #555; padding: 0.3em 0.8em; border-radius: 5px; font-size: 0.85em; margin-right: 0.3em; text-decoration: none; display: inline-block; }
        .btn:hover { background: #444; }
        .btn-saw { border-color: #4f4; color: #4f4; }
        .btn-missed { border-color: #f66; color: #f66; }
        .btn-dismiss { border-color: #888; color: #aaa; }
        .btn-undo { border-color: #555; color: #aaa; font-size: 0.75em; padding: 0.2em 0.5em; }
        .feedback-status { color: #aaa; font-size: 0.9em; }
        .empty { color: #777; font-style: italic; }
        a { color: #4af; }
        .muted { color: #888; font-size: 0.85em; }
    </style>
</head>
<body>
    <h1>🚂 Trainwatch</h1>
    <div class="meta">Last updated {{ now }} · auto-refresh 30s · <a href="/transmissions">all transmissions</a></div>

    <div class="stats">
        <div class="stat">
            <div class="stat-label">Transmissions</div>
            <div class="stat-num">{{ total_transmissions }}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Detector events</div>
            <div class="stat-num">{{ total_detectors }}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Alerts sent</div>
            <div class="stat-num">{{ total_alerts }}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Last 24h</div>
            <div class="stat-num">{{ tx_24h }}</div>
        </div>
    </div>

    <h2>Recent transmissions (last 20)</h2>
    {% if recent_tx %}
        {% for t in recent_tx %}
        <div class="tx {% if t.has_detector %}detector{% endif %}">
            <time>{{ t.timestamp[:19].replace('T', ' ') }}</time>
            <span class="muted">· {{ '%.3f' % t.frequency_mhz }} MHz</span>
            {% if t.has_detector %} · <strong style="color:#4af">⚙ DETECTOR</strong>{% endif %}
            <div class="transcript">{{ t.transcript or '(no transcript)' }}</div>
            {% if t.audio_url %}
            <audio controls preload="none" src="{{ t.audio_url }}"></audio>
            {% endif %}
        </div>
        {% endfor %}
    {% else %}
        <p class="empty">No transmissions logged yet. Capture pipeline is running and waiting for audio.</p>
    {% endif %}

    <h2>Recent alerts</h2>
    {% if recent_alerts %}
        {% for a in recent_alerts %}
        <div class="alert-row {% if a.feedback %}{{ a.feedback }}{% endif %}">
            <time>{{ a.alert_sent_at[:16].replace('T', ' ') }}</time><br>
            <strong>{{ a.spot_name }}</strong> · predicted {{ a.predicted_arrival[11:16] if a.predicted_arrival else '?' }}<br>
            <span class="muted">{{ a.railroad or '?' }} MP {{ a.detector_milepost or '?' }}, {{ a.direction or '?' }}-bound, {{ a.speed_mph or '?' }} mph</span>
            <div class="feedback">
                {% if not a.feedback %}
                    <a class="btn btn-saw" href="/feedback/{{ a.id }}/saw">Saw it</a>
                    <a class="btn btn-missed" href="/feedback/{{ a.id }}/missed">Missed it</a>
                    <a class="btn btn-dismiss" href="/feedback/{{ a.id }}/dismissed">Dismiss</a>
                {% else %}
                    <span class="feedback-status">
                        {% if a.feedback == 'saw' %}✓ Saw it{% endif %}
                        {% if a.feedback == 'missed' %}✗ Missed it{% endif %}
                        {% if a.feedback == 'dismissed' %}— Dismissed{% endif %}
                    </span>
                    <a class="btn btn-undo" href="/feedback/{{ a.id }}/clear">undo</a>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    {% else %}
        <p class="empty">No alerts yet.</p>
    {% endif %}
</body>
</html>
"""


TRANSMISSIONS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>All Transmissions - Trainwatch</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; max-width: 900px; margin: 1em auto; padding: 0 1em; background: #1a1a1a; color: #eee; }
        h1 { color: #4af; }
        .tx { border-left: 3px solid #6c6; padding: 0.5em 1em; margin: 0.3em 0; background: #2a2a2a; border-radius: 0 8px 8px 0; }
        .tx.detector { border-left-color: #4af; }
        time { color: #888; font-size: 0.85em; }
        .transcript { color: #ddd; margin-top: 0.3em; font-family: monospace; font-size: 0.85em; }
        audio { width: 100%; margin-top: 0.5em; height: 36px; }
        .muted { color: #888; font-size: 0.85em; }
        a { color: #4af; }
    </style>
</head>
<body>
    <h1><a href="/">← back</a> · All transmissions ({{ total }})</h1>
    {% for t in transmissions %}
    <div class="tx {% if t.has_detector %}detector{% endif %}">
        <time>{{ t.timestamp[:19].replace('T', ' ') }}</time>
        <span class="muted">· {{ '%.3f' % t.frequency_mhz }} MHz</span>
        {% if t.has_detector %} · ⚙ DETECTOR{% endif %}
        <div class="transcript">{{ t.transcript or '(no transcript)' }}</div>
        {% if t.audio_url %}
        <audio controls preload="none" src="{{ t.audio_url }}"></audio>
        {% endif %}
    </div>
    {% endfor %}
</body>
</html>
"""


def annotate(rows):
    """Add detector flag and audio URL to each transmission row."""
    conn = get_db()
    de_ids = {r["transmission_id"] for r in conn.execute(
        "SELECT transmission_id FROM detector_events WHERE transmission_id IS NOT NULL"
    ).fetchall()}
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["has_detector"] = d["id"] in de_ids
        if d.get("audio_path"):
            p = Path(d["audio_path"])
            try:
                if p.exists() and p.resolve().is_relative_to(AUDIO_ROOT.resolve()):
                    rel = p.resolve().relative_to(AUDIO_ROOT.resolve())
                    d["audio_url"] = f"/audio/{rel}"
                else:
                    d["audio_url"] = None
            except Exception:
                d["audio_url"] = None
        else:
            d["audio_url"] = None
        out.append(d)
    return out


@app.route("/")
def dashboard():
    total_transmissions = query_db("SELECT COUNT(*) as c FROM transmissions", one=True)["c"]
    total_detectors = query_db("SELECT COUNT(*) as c FROM detector_events", one=True)["c"]
    total_alerts = query_db("SELECT COUNT(*) as c FROM alerts", one=True)["c"]

    yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
    tx_24h = query_db(
        "SELECT COUNT(*) as c FROM transmissions WHERE timestamp > ?",
        (yesterday,), one=True,
    )["c"]

    recent_tx = annotate(query_db(
        "SELECT * FROM transmissions ORDER BY id DESC LIMIT 20"
    ))

    recent_alerts = query_db(
        """SELECT a.*, ws.name as spot_name, de.milepost as detector_milepost,
                  de.railroad, de.direction, de.speed_mph
           FROM alerts a
           LEFT JOIN watch_spots ws ON ws.id = a.watch_spot_id
           LEFT JOIN detector_events de ON de.id = a.detector_event_id
           ORDER BY a.id DESC LIMIT 10"""
    )

    return render_template_string(
        DASHBOARD_HTML,
        total_transmissions=total_transmissions,
        total_detectors=total_detectors,
        total_alerts=total_alerts,
        tx_24h=tx_24h,
        recent_tx=recent_tx,
        recent_alerts=recent_alerts,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/transmissions")
def all_transmissions():
    total = query_db("SELECT COUNT(*) as c FROM transmissions", one=True)["c"]
    transmissions = annotate(query_db(
        "SELECT * FROM transmissions ORDER BY id DESC LIMIT 500"
    ))
    return render_template_string(TRANSMISSIONS_HTML, transmissions=transmissions, total=total)


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    """Serve audio clips from the audio directory."""
    safe_root = AUDIO_ROOT.resolve()
    target = (safe_root / filename).resolve()
    try:
        target.relative_to(safe_root)
    except ValueError:
        abort(404)
    if not target.exists():
        abort(404)
    return send_from_directory(safe_root, filename, mimetype="audio/wav")


@app.route("/feedback/<int:alert_id>/<action>")
def feedback(alert_id, action):
    if action not in ("saw", "missed", "dismissed", "clear"):
        return "bad action", 400
    value = None if action == "clear" else action
    conn = get_db()
    conn.execute("UPDATE alerts SET feedback = ? WHERE id = ?", (value, alert_id))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/api/recent")
def api_recent():
    events = query_db("SELECT * FROM detector_events ORDER BY id DESC LIMIT 50")
    return jsonify([dict(e) for e in events])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
