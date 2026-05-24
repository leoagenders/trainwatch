"""
Daily SQLite backup. Uses sqlite3's online backup API so the live
capture pipeline doesn't have to stop. Keeps last 30 daily snapshots.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH

BACKUP_DIR = Path(__file__).parent.parent / "data" / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
KEEP_DAYS = 30


def backup_db():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"trainwatch_{ts}.db"

    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(str(backup_path))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()

    size_kb = backup_path.stat().st_size // 1024
    print(f"Backed up to {backup_path.name} ({size_kb} KB)")
    return backup_path


def prune_old_backups():
    cutoff = datetime.now().timestamp() - (KEEP_DAYS * 86400)
    pruned = 0
    for f in BACKUP_DIR.glob("trainwatch_*.db"):
        if f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                pruned += 1
            except Exception as e:
                print(f"Could not delete {f.name}: {e}")
    if pruned:
        print(f"Pruned {pruned} backup(s) older than {KEEP_DAYS} days")


if __name__ == "__main__":
    backup_db()
    prune_old_backups()
