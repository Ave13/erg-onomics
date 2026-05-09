import sqlite3
import time
from datetime import date

_DB_PATH = "rowing.db"

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS training_plan ("
        "id          INTEGER PRIMARY KEY, "
        "day_of_week INTEGER NOT NULL UNIQUE, "  # 0=Mon … 6=Sun
        "workout_id  INTEGER, "
        "notes       TEXT, "
        "created_at  REAL)"
    )


def get_plan():
    """Return dict {day_of_week: (workout_id, notes)} for all assigned days."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure(conn)
            rows = conn.execute(
                "SELECT day_of_week, workout_id, notes FROM training_plan"
            ).fetchall()
        return {r[0]: (r[1], r[2] or "") for r in rows}
    except Exception:
        return {}


def set_day(day_of_week, workout_id, notes=""):
    """Assign a workout to a day of the week (0=Mon, 6=Sun)."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure(conn)
            conn.execute(
                "INSERT INTO training_plan (day_of_week, workout_id, notes, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(day_of_week) DO UPDATE SET "
                "  workout_id=excluded.workout_id, notes=excluded.notes, created_at=excluded.created_at",
                (day_of_week, workout_id, notes, time.time()),
            )
    except Exception:
        pass


def clear_day(day_of_week):
    """Remove the workout assignment for a given day."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure(conn)
            conn.execute(
                "DELETE FROM training_plan WHERE day_of_week=?", (day_of_week,)
            )
    except Exception:
        pass


def get_today():
    """Return (workout_id, notes) for today's plan entry, or (None, '')."""
    day = date.today().weekday()   # 0=Mon, 6=Sun
    return get_plan().get(day, (None, ""))


def day_name(day_of_week):
    return _DAY_NAMES[day_of_week % 7]
