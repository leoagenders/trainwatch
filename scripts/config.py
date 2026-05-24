"""
Trainwatch configuration.

Sensitive values (location, ntfy topic) should be set via environment
variables or a local override that is gitignored. The defaults here are
placeholders suitable for a public repository.
"""
import os
from pathlib import Path

# ntfy topic — override via env var or local config
NTFY_TOPIC = os.environ.get("TRAINWATCH_NTFY_TOPIC", "trainwatch-your-topic-here")
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# Frequencies to monitor (MHz)
FREQUENCIES = {
    "CSX_A_LINE": 160.590,
}

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "trainwatch.db"

# Audio capture settings
SAMPLE_RATE = 22050
SQUELCH_LEVEL = 100

# Watch spot — override via env vars or set your real coordinates locally.
# Defaults below are the approximate center of Petersburg, VA (public reference point).
HOME_LATITUDE = float(os.environ.get("TRAINWATCH_HOME_LAT", "37.2279"))
HOME_LONGITUDE = float(os.environ.get("TRAINWATCH_HOME_LON", "-77.4019"))

# Local overrides (gitignored)
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
