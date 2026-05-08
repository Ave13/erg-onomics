import sqlite3
from datetime import date, timedelta

_DB_PATH = "rowing.db"


def get_streak(user_id):
    """
    Return (current_streak, longest_streak) for the given user.
    A streak counts consecutive calendar days with at least one
    completed session.
    """
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT date(started_at, 'unixepoch', 'localtime') AS d "
                "FROM sessions "
                "WHERE user_id=? AND status='complete' AND started_at IS NOT NULL "
                "GROUP BY d ORDER BY d DESC",
                (user_id,)
            ).fetchall()
    except Exception:
        return 0, 0

    if not rows:
        return 0, 0

    dates = [date.fromisoformat(r[0]) for r in rows]
    today = date.today()

    # Current streak
    current = 0
    check   = today
    for d in dates:
        if d == check or d == check - timedelta(days=1):
            if d == check - timedelta(days=1):
                check = d
            else:
                pass
            current += 1
            check = d - timedelta(days=1)
        elif d < check:
            break

    # Longest streak
    longest = 1
    run     = 1
    for i in range(1, len(dates)):
        if dates[i] == dates[i - 1] - timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return current, longest
