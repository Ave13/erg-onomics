import sqlite3
import time

_DB_PATH = "rowing.db"

# Standard distances (m) we track pace PRs for
_PR_DISTANCES = [500, 1000, 2000, 5000, 10000]

# Record types that don't depend on distance
_SESSION_RECORDS = [
    "longest_distance",   # m
    "longest_time",       # secs
    "best_avg_watts",     # watts
    "best_max_watts",     # watts
    "best_avg_spm",       # spm
]


def _init_records_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS records ("
        "id          INTEGER PRIMARY KEY, "
        "user_id     INTEGER NOT NULL, "
        "record_type TEXT    NOT NULL, "   # e.g. 'pace_2000m', 'best_avg_watts'
        "value       REAL    NOT NULL, "   # lower=better for pace, higher=better otherwise
        "session_id  INTEGER, "
        "set_at      REAL"
        ")"
    )
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_records_user_type "
                     "ON records (user_id, record_type)")
    except Exception:
        pass


def _get_record(conn, user_id, record_type):
    row = conn.execute(
        "SELECT value FROM records WHERE user_id=? AND record_type=?",
        (user_id, record_type)
    ).fetchone()
    return row[0] if row else None


def _upsert_record(conn, user_id, record_type, value, session_id):
    conn.execute(
        "INSERT INTO records (user_id, record_type, value, session_id, set_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, record_type) DO UPDATE SET "
        "  value=excluded.value, session_id=excluded.session_id, set_at=excluded.set_at",
        (user_id, record_type, value, session_id, time.time())
    )


def check_and_save_records(session_id, user_id, session_stats):
    """
    Compare session_stats against stored records. Return list of
    (record_type, old_value, new_value) tuples for every PR broken.

    session_stats keys: distance_m, elapsed_secs, avg_watts, max_watts,
                        avg_spm, avg_pace_sec (per 500m), stroke_log_rows
    """
    if not user_id:
        return []

    broken = []
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _init_records_table(conn)

            def _check(record_type, new_val, lower_is_better=False):
                old = _get_record(conn, user_id, record_type)
                is_pr = (old is None or
                         (lower_is_better and new_val < old) or
                         (not lower_is_better and new_val > old))
                if is_pr and new_val and new_val > 0:
                    _upsert_record(conn, user_id, record_type, new_val, session_id)
                    broken.append((record_type, old, new_val))

            d   = session_stats.get("distance_m", 0)
            t   = session_stats.get("elapsed_secs", 0)
            aw  = session_stats.get("avg_watts", 0)
            mw  = session_stats.get("max_watts", 0)
            spm = session_stats.get("avg_spm", 0)

            _check("longest_distance", d)
            _check("longest_time",     t)
            _check("best_avg_watts",   aw)
            _check("best_max_watts",   mw)
            _check("best_avg_spm",     spm)

            # pace PRs: only if session covered at least that distance
            rows = session_stats.get("stroke_log_rows", [])
            if rows and d:
                # build cumulative distance+time from stroke log for each PR distance
                for pr_dist in _PR_DISTANCES:
                    if d < pr_dist:
                        continue
                    pace_sec = _best_pace_for_distance(rows, pr_dist)
                    if pace_sec:
                        _check(f"pace_{pr_dist}m", pace_sec, lower_is_better=True)

    except Exception:
        pass

    return broken


def _best_pace_for_distance(rows, target_m):
    """
    Sliding window over stroke_log rows (elapsed_secs, speed_mm_s) to find
    the fastest contiguous segment covering target_m metres.
    Returns best pace in seconds per 500m, or None.
    """
    # rows: list of (elapsed_secs, speed_mm_s)
    if not rows:
        return None

    best_pace = None
    n = len(rows)

    # Build cumulative distance array
    cum_dist = [0.0] * (n + 1)
    for i, (elapsed, speed) in enumerate(rows):
        if i == 0:
            dt = elapsed
        else:
            dt = elapsed - rows[i - 1][0]
        cum_dist[i + 1] = cum_dist[i] + (speed / 1000) * max(dt, 0)

    left = 0
    for right in range(1, n + 1):
        while cum_dist[right] - cum_dist[left] >= target_m and left < right:
            seg_dist = cum_dist[right] - cum_dist[left]
            seg_time = rows[right - 1][0] - (rows[left][0] if left > 0 else 0)
            if seg_time > 0:
                pace = (target_m / seg_dist) * seg_time / target_m * 500
                # simpler: pace = 500 * seg_time / seg_dist
                pace = 500 * seg_time / seg_dist
                if best_pace is None or pace < best_pace:
                    best_pace = pace
            left += 1

    return round(best_pace, 2) if best_pace else None


def get_all_records(user_id):
    """Return dict of record_type -> (value, set_at) for display."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _init_records_table(conn)
            rows = conn.execute(
                "SELECT record_type, value, set_at FROM records WHERE user_id=?",
                (user_id,)
            ).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}
    except Exception:
        return {}
