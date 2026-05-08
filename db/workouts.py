import json
import sqlite3
import time

_DB_PATH = "rowing.db"

_PRESETS = [
    ("2k Test",    [{"type": "distance", "meters": 2000, "rest_secs": 0}]),
    ("5k Test",    [{"type": "distance", "meters": 5000, "rest_secs": 0}]),
    ("30 min",     [{"type": "time",     "seconds": 1800, "rest_secs": 0}]),
    ("60 min",     [{"type": "time",     "seconds": 3600, "rest_secs": 0}]),
    ("6 × 500m",   [{"type": "distance", "meters": 500,  "rest_secs": 120}] * 6),
    ("4 × 1000m",  [{"type": "distance", "meters": 1000, "rest_secs": 180}] * 4),
    ("3 × 2000m",  [{"type": "distance", "meters": 2000, "rest_secs": 300}] * 3),
    ("8 × 250m",   [{"type": "distance", "meters": 250,  "rest_secs": 60}]  * 8),
    ("10 × 1 min", [{"type": "time",     "seconds": 60,  "rest_secs": 60}]  * 10),
    ("5 × 5 min",  [{"type": "time",     "seconds": 300, "rest_secs": 180}] * 5),
]


def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workouts ("
        "id         INTEGER PRIMARY KEY, "
        "name       TEXT    NOT NULL, "
        "definition JSON    NOT NULL, "
        "is_preset  INTEGER DEFAULT 0, "
        "created_at REAL)"
    )
    if conn.execute("SELECT COUNT(*) FROM workouts WHERE is_preset=1").fetchone()[0] == 0:
        for name, intervals in _PRESETS:
            conn.execute(
                "INSERT INTO workouts (name, definition, is_preset, created_at) VALUES (?, ?, 1, ?)",
                (name, json.dumps({"intervals": intervals}), time.time()),
            )


def list_workouts():
    """Return [(id, name, definition_dict, is_preset), ...]."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure(conn)
            rows = conn.execute(
                "SELECT id, name, definition, is_preset FROM workouts "
                "ORDER BY is_preset DESC, name"
            ).fetchall()
        return [(r[0], r[1], json.loads(r[2]), bool(r[3])) for r in rows]
    except Exception:
        return []


def get_workout(workout_id):
    """Return (id, name, definition_dict, is_preset) or None."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure(conn)
            row = conn.execute(
                "SELECT id, name, definition, is_preset FROM workouts WHERE id=?",
                (workout_id,),
            ).fetchone()
        if row:
            return row[0], row[1], json.loads(row[2]), bool(row[3])
    except Exception:
        pass
    return None


def save_workout(name, intervals):
    """Insert custom workout. Returns new id, or None on failure."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _ensure(conn)
            cur = conn.execute(
                "INSERT INTO workouts (name, definition, is_preset, created_at) VALUES (?, ?, 0, ?)",
                (name, json.dumps({"intervals": intervals}), time.time()),
            )
            return cur.lastrowid
    except Exception:
        return None


def delete_workout(workout_id):
    """Delete a custom (non-preset) workout."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "DELETE FROM workouts WHERE id=? AND is_preset=0", (workout_id,)
            )
    except Exception:
        pass


def workout_summary(definition):
    """Short human-readable summary of a workout definition dict."""
    intervals = definition.get("intervals", [])
    if not intervals:
        return "Empty"
    first = intervals[0]
    if len(intervals) > 1 and all(i == first for i in intervals):
        reps = len(intervals)
        return f"{reps}×  {_interval_label(first)}"
    if len(intervals) == 1:
        return _interval_label(first)
    return f"{len(intervals)} intervals"


def _interval_label(iv):
    if iv.get("type") == "distance":
        txt = f"{iv.get('meters', 0)}m"
    else:
        s = iv.get("seconds", 0)
        txt = f"{s // 60}:{s % 60:02d}"
    rest = iv.get("rest_secs", 0)
    if rest:
        txt += f"  +{rest // 60}:{rest % 60:02d} rest"
    return txt
