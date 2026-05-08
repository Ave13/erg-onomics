import sqlite3

_DB_PATH = "rowing.db"

# Zone boundaries as fraction of max HR
# Zone: (lower_fraction, upper_fraction, multiplier)
ZONES = [
    (0.00, 0.60, 1),
    (0.60, 0.70, 2),
    (0.70, 0.80, 4),
    (0.80, 0.90, 8),
    (0.90, 1.00, 8),
]
ZONE_COLORS = [
    (0.30, 0.55, 0.85, 1),   # Zone 1 — blue
    (0.20, 0.75, 0.45, 1),   # Zone 2 — green
    (0.95, 0.75, 0.10, 1),   # Zone 3 — yellow
    (0.95, 0.45, 0.10, 1),   # Zone 4 — orange
    (0.90, 0.20, 0.20, 1),   # Zone 5 — red
]
ZONE_NAMES = ["Z1 Easy", "Z2 Aerobic", "Z3 Tempo", "Z4 Threshold", "Z5 Max"]


def estimate_max_hr(dob_str):
    """208 - 0.7 × age  (Tanaka formula)."""
    try:
        from datetime import date
        dob  = date.fromisoformat(dob_str)
        age  = (date.today() - dob).days / 365.25
        return round(208 - 0.7 * age)
    except Exception:
        return 185   # safe default


def calculate_strive_score(session_id, max_hr=185):
    """
    Return (score, zone_times) where zone_times is a list of seconds
    spent in each zone (index 0=Z1 … 4=Z5).
    """
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT elapsed_secs, hr_bpm FROM stroke_log "
                "WHERE session_id=? AND hr_bpm IS NOT NULL "
                "ORDER BY elapsed_secs",
                (session_id,)
            ).fetchall()
    except Exception:
        return 0, [0] * 5

    if not rows:
        return 0, [0] * 5

    zone_times = [0.0] * 5
    for i in range(len(rows)):
        elapsed, hr = rows[i]
        if i == 0:
            dt = elapsed
        else:
            dt = elapsed - rows[i - 1][0]
        dt = max(dt, 0)
        frac = hr / max_hr
        for z, (lo, hi, _) in enumerate(ZONES):
            if lo <= frac < hi or (z == 4 and frac >= hi):
                zone_times[z] += dt
                break

    score = sum(t * m for t, (_, _, m) in zip(zone_times, ZONES)) / 60
    return round(score, 1), [round(t) for t in zone_times]
