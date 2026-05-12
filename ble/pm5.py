import asyncio
import collections
import sqlite3
import time

from bleak import BleakClient, BleakScanner

ROWING_STATUS_UUID   = "CE060031-43E5-11E4-916C-0800200C9A66"
ADD_STATUS_UUID      = "CE060032-43E5-11E4-916C-0800200C9A66"
STROKE_DATA_UUID     = "CE060035-43E5-11E4-916C-0800200C9A66"
HR_UUID              = "CE06003A-43E5-11E4-916C-0800200C9A66"
WORKOUT_SUMMARY_UUID = "CE060039-43E5-11E4-916C-0800200C9A66"

_DB_PATH = "rowing.db"

state = {
    "pace": "--:--",
    "spm": "--",
    "interval": "--",
    "drive_time": "--",
    "recovery": "--",
    "drive_length": "--",
    "watts": 0,
    "distance": 0.0,
    "elapsed": 0.0,
    "workout_state": 0,
    "stroke_count": 0,
    "speed_mm_s": 0,
    "drag_factor": None,
    "stroke_state": 0,   # 0=idle 1=drive 2=decelerate 3=recovery
    "hr_bpm": "--",
    "session_id": None,
    "session_active": False,
    "session_paused": False,
    "session_prs": [],
    "target_pace_sec": None,
    "active_workout_id": None,
    "active_workout_name": "",
    # user profile
    "user_id": None,
    "user_name": "",
    "user_weight_kg": None,
    "user_height_cm": None,
    "expected_drive_cm": None,
    "expected_peak_n": None,
    # perfect-stroke streak (updated in parse_stroke_data)
    "perfect_streak": 0,
    "perfect_streak_best": 0,
    # raw numeric force/drive values for force-curve screen
    "peak_force_n": None,
    "avg_force_n": None,
    "drive_time_secs": None,
    "drive_length_cm_raw": None,
    "recovery_secs": None,
    # interval tracking (updated in server.py _update_interval_state)
    "interval_index": 0,
    "interval_phase": "work",   # "work" | "rest" | "done"
    "interval_remaining": None,
    # BLE connection status
    "ble_status": "scanning",   # "scanning" | "found" | "connecting" | "connected" | "disconnected"
    "ble_devices": [],          # [{"address": str, "name": str}] — discovered PM5s
    "ble_address": None,        # address of selected/connected device (set by user or auto)
    "ble_name": None,           # display name of connected device
}

_stroke_times = collections.deque(maxlen=10)
_STROKE_STALE_SECS = 10
_EMA_ALPHA = 0.25          # smoothing factor for interval EMA
_ema_interval_secs = None  # exponential moving average of inter-stroke interval


def speed_to_pace(speed_mm_s):
    if speed_mm_s == 0:
        return "--:--"
    speed_m_s = speed_mm_s / 1000
    pace_sec = 500 / speed_m_s
    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"


def pace_to_watts(pace_sec):
    if pace_sec == 0:
        return 0
    return round(2.80 / (pace_sec / 500) ** 3)


def _calc_spm():
    if not _stroke_times or _ema_interval_secs is None:
        return "--"
    if time.monotonic() - _stroke_times[-1] > _STROKE_STALE_SECS:
        return "--"
    return round(60 / _ema_interval_secs)


def _log_stroke(stroke_num, elapsed_secs, interval_secs, speed_mm_s,
                drive_time_secs=None, recovery_secs=None,
                drive_length_cm=None, avg_force_n=None, peak_force_n=None,
                work_per_stroke_j=None, stroke_distance_m=None):
    if state.get("session_paused"):
        return
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO stroke_log "
                "(stroke_num, elapsed_secs, interval_secs, speed_mm_s, logged_at, "
                " drive_time_secs, recovery_secs, drive_length_cm, avg_force_n, peak_force_n, "
                " session_id, hr_bpm, work_per_stroke_j, stroke_distance_m) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (stroke_num, elapsed_secs, round(interval_secs, 4), speed_mm_s, time.time(),
                 drive_time_secs, recovery_secs, drive_length_cm, avg_force_n, peak_force_n,
                 state["session_id"],
                 state["hr_bpm"] if isinstance(state["hr_bpm"], int) else None,
                 work_per_stroke_j, stroke_distance_m),
            )
    except Exception:
        pass


def _init_db():
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS user_profile ("
                "id INTEGER PRIMARY KEY, "
                "name TEXT, "
                "weight_kg REAL NOT NULL, "
                "height_cm REAL NOT NULL, "
                "dob TEXT, "
                "created_at REAL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS stroke_log ("
                "id INTEGER PRIMARY KEY, "
                "stroke_num INTEGER NOT NULL, "
                "elapsed_secs REAL NOT NULL, "
                "interval_secs REAL NOT NULL, "
                "speed_mm_s INTEGER NOT NULL, "
                "logged_at REAL NOT NULL, "
                "drive_time_secs REAL, "
                "recovery_secs REAL, "
                "drive_length_cm INTEGER, "
                "avg_force_n REAL, "
                "peak_force_n REAL, "
                "session_id INTEGER, "
                "hr_bpm INTEGER, "
                "work_per_stroke_j REAL, "
                "stroke_distance_m REAL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id INTEGER PRIMARY KEY, "
                "user_id INTEGER, "
                "workout_id INTEGER, "
                "started_at REAL, "
                "ended_at REAL, "
                "status TEXT DEFAULT 'active', "
                "total_distance REAL, "
                "total_time INTEGER, "
                "avg_pace REAL, "
                "avg_watts REAL, "
                "avg_spm REAL, "
                "max_watts INTEGER, "
                "calories INTEGER, "
                "avg_hr INTEGER, "
                "max_hr INTEGER, "
                "tcx_path TEXT, "
                "raw_data JSON)"
            )
            for tbl, col, typedef in [
                ("stroke_log", "session_id",        "INTEGER"),
                ("stroke_log", "hr_bpm",             "INTEGER"),
                ("stroke_log", "work_per_stroke_j",  "REAL"),
                ("stroke_log", "stroke_distance_m",  "REAL"),
                ("sessions",   "user_id",            "INTEGER"),
                ("sessions",   "workout_id",         "INTEGER"),
                ("sessions",   "started_at",         "REAL"),
                ("sessions",   "ended_at",           "REAL"),
                ("sessions",   "status",             "TEXT DEFAULT 'active'"),
                ("sessions",   "avg_hr",             "INTEGER"),
                ("sessions",   "max_hr",             "INTEGER"),
                ("sessions",   "drag_factor",        "INTEGER"),
                ("sessions",   "tcx_path",           "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typedef}")
                except Exception:
                    pass
            # workouts table
            conn.execute(
                "CREATE TABLE IF NOT EXISTS workouts ("
                "id         INTEGER PRIMARY KEY, "
                "name       TEXT    NOT NULL, "
                "definition JSON    NOT NULL, "
                "is_preset  INTEGER DEFAULT 0, "
                "created_at REAL)"
            )
            # training plan table
            conn.execute(
                "CREATE TABLE IF NOT EXISTS training_plan ("
                "id          INTEGER PRIMARY KEY, "
                "day_of_week INTEGER NOT NULL UNIQUE, "
                "workout_id  INTEGER, "
                "notes       TEXT, "
                "created_at  REAL)"
            )
    except Exception:
        pass


def load_user_profile():
    """Load the most recent profile into state. Called at startup and after save."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            row = conn.execute(
                "SELECT id, name, weight_kg, height_cm, dob "
                "FROM user_profile ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row:
            uid, name, weight_kg, height_cm, dob = row
            state["user_id"]         = uid
            state["user_name"]       = name or ""
            state["user_weight_kg"]  = weight_kg
            state["user_height_cm"]  = height_cm
            state["user_dob"]        = dob  # ISO date string or None
            state["expected_drive_cm"] = round(height_cm * 0.50)
            state["expected_peak_n"]   = round(weight_kg * 4.5)
    except Exception:
        pass


def save_user_profile(name, weight_kg, height_cm, dob=None):
    """Insert a new profile record. Returns the new id, or None on failure."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            cur = conn.execute(
                "INSERT INTO user_profile (name, weight_kg, height_cm, dob, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, float(weight_kg), float(height_cm), dob or None, time.time())
            )
            uid = cur.lastrowid
        load_user_profile()
        return uid
    except Exception:
        return None


def has_user_profile():
    """Return True if at least one profile row exists."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            return conn.execute(
                "SELECT 1 FROM user_profile LIMIT 1"
            ).fetchone() is not None
    except Exception:
        return False


def parse_general_status(data):
    if len(data) < 7:
        return
    elapsed = int.from_bytes(data[0:3], "little") / 100
    distance = int.from_bytes(data[3:6], "little") / 10
    workout_state = data[6]
    state["elapsed"] = elapsed
    state["distance"] = distance
    prev_ws = state["workout_state"]
    state["workout_state"] = workout_state
    if workout_state == 0 and prev_ws != 0:
        global _ema_interval_secs
        _ema_interval_secs = None
        _stroke_times.clear()
        state["spm"] = "--"
        state["interval"] = "--"
        state["drive_time"] = "--"
        state["recovery"] = "--"
        state["drive_length"] = "--"


def parse_add_status_1(data):
    if len(data) < 2:
        return
    speed_mm_s = int.from_bytes(data[0:2], "little")
    pace_str = speed_to_pace(speed_mm_s)
    pace_sec = (500 / (speed_mm_s / 1000)) if speed_mm_s > 0 else 0
    state["pace"]       = pace_str
    state["watts"]      = pace_to_watts(pace_sec)
    state["speed_mm_s"] = speed_mm_s
    if len(data) >= 3:
        state["stroke_state"] = data[2] & 0x03   # lower 2 bits: 0=idle,1=drive,2=decel,3=recovery
    if len(data) >= 4:
        # byte 3 carries drag factor (1–222 typical range on PM5)
        df = data[3]
        if df > 0:
            state["drag_factor"] = df


def parse_stroke_data(data):
    if len(data) < 20:
        return
    drive_length_cm   = data[6]
    drive_time_secs   = data[7] / 100
    recovery_secs     = int.from_bytes(data[8:10],  "little") / 100
    peak_force_n      = int.from_bytes(data[12:14], "little") / 10
    avg_force_n       = int.from_bytes(data[14:16], "little") / 10
    stroke_distance_m = int.from_bytes(data[10:12], "little") / 100
    work_per_stroke_j = int.from_bytes(data[16:18], "little") / 10
    stroke_count      = int.from_bytes(data[18:20], "little")

    state["drive_time"]        = f"{drive_time_secs:.2f}s"
    state["recovery"]          = f"{recovery_secs:.2f}s"
    state["drive_length"]      = f"{drive_length_cm}cm"
    state["stroke_count"]      = stroke_count
    state["peak_force_n"]      = peak_force_n
    state["avg_force_n"]       = avg_force_n
    state["drive_time_secs"]   = drive_time_secs
    state["drive_length_cm_raw"] = drive_length_cm
    state["recovery_secs"]     = recovery_secs

    now = time.monotonic()
    interval = None
    if _stroke_times:
        interval = now - _stroke_times[-1]
        state["interval"] = f"{interval:.2f}s"
    _stroke_times.append(now)

    global _ema_interval_secs
    if interval is not None:
        if _ema_interval_secs is None:
            _ema_interval_secs = interval
        else:
            _ema_interval_secs = _EMA_ALPHA * interval + (1 - _EMA_ALPHA) * _ema_interval_secs

    state["spm"] = _calc_spm()

    if interval is not None:
        _log_stroke(
            stroke_count, state["elapsed"], interval, state["speed_mm_s"],
            drive_time_secs, recovery_secs, drive_length_cm, avg_force_n, peak_force_n,
            work_per_stroke_j, stroke_distance_m,
        )

    # Perfect-stroke streak evaluation
    if avg_force_n and avg_force_n > 0 and peak_force_n:
        ratio = peak_force_n / avg_force_n
        exp_cm = state.get("expected_drive_cm") or drive_length_cm
        ratio_ok  = 1.3 <= ratio <= 1.8
        time_ok   = 0.5 <= drive_time_secs <= 1.2
        length_ok = abs(drive_length_cm - exp_cm) <= 15
        if ratio_ok and time_ok and length_ok:
            state["perfect_streak"] += 1
            if state["perfect_streak"] > state["perfect_streak_best"]:
                state["perfect_streak_best"] = state["perfect_streak"]
        else:
            state["perfect_streak"] = 0


def parse_heart_rate(data):
    if len(data) < 2:
        return
    hr = int.from_bytes(data[1:3], "little") if data[0] & 0x01 else data[1]
    state["hr_bpm"] = hr


def parse_workout_summary(data):
    pass  # stub — byte layout TBD; doesn't affect session stop flow


def start_session(resume_id=None, workout_id=None):
    global _ema_interval_secs
    _ema_interval_secs = None
    _stroke_times.clear()
    if resume_id:
        state["session_id"]     = resume_id
        state["session_active"] = True
        state["session_paused"] = False
        return resume_id
    wid = workout_id or state.get("active_workout_id")
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            cur = conn.execute(
                "INSERT INTO sessions (user_id, workout_id, started_at, status) VALUES (?, ?, ?, 'active')",
                (state["user_id"], wid, time.time())
            )
            session_id = cur.lastrowid
        state["session_id"]     = session_id
        state["session_active"] = True
        state["session_paused"] = False
        return session_id
    except Exception:
        return None


def stop_session():
    sid = state.get("session_id")
    if not sid:
        return None
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            agg = conn.execute(
                "SELECT AVG(speed_mm_s), MAX(speed_mm_s), COUNT(*), "
                "       AVG(hr_bpm), MAX(hr_bpm) "
                "FROM stroke_log WHERE session_id=?", (sid,)
            ).fetchone()
            avg_speed, max_speed, stroke_count, avg_hr, max_hr = agg

            elapsed  = state["elapsed"]
            distance = state["distance"]

            avg_pace_sec  = round(500 / (avg_speed / 1000)) if avg_speed else 0
            avg_watts_val = pace_to_watts(avg_pace_sec) if avg_pace_sec else 0
            max_watts_val = pace_to_watts(
                round(500 / (max_speed / 1000)) if max_speed else 0
            )
            avg_spm_val  = round(stroke_count / elapsed * 60) if elapsed else 0
            cal_per_hr   = (4 * avg_watts_val + 300) / 4.2
            calories_val = round(cal_per_hr * elapsed / 3600)

            conn.execute(
                "UPDATE sessions SET "
                "  status='complete', ended_at=?, "
                "  total_distance=?, total_time=?, "
                "  avg_pace=?, avg_watts=?, avg_spm=?, max_watts=?, "
                "  calories=?, avg_hr=?, max_hr=?, drag_factor=? "
                "WHERE id=?",
                (time.time(), distance, elapsed,
                 avg_pace_sec, avg_watts_val, avg_spm_val, max_watts_val,
                 calories_val,
                 int(avg_hr) if avg_hr else None,
                 int(max_hr) if max_hr else None,
                 state.get("drag_factor"),
                 sid)
            )
        stroke_rows = conn.execute(
                "SELECT elapsed_secs, speed_mm_s FROM stroke_log "
                "WHERE session_id=? ORDER BY elapsed_secs", (sid,)
            ).fetchall()
        state["session_id"]     = None
        state["session_active"] = False
        state["session_paused"] = False
    except Exception:
        return None

    from db.records import check_and_save_records
    prs = check_and_save_records(sid, state.get("user_id"), {
        "distance_m":   distance,
        "elapsed_secs": elapsed,
        "avg_watts":    avg_watts_val,
        "max_watts":    max_watts_val,
        "avg_spm":      avg_spm_val,
        "stroke_log_rows": stroke_rows,
    })
    state["session_prs"] = prs

    from db.export import export_tcx
    return export_tcx(sid)


def pause_session():
    if state["session_active"]:
        state["session_paused"] = True


def resume_session():
    state["session_paused"] = False


def find_resumable_session():
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            return conn.execute(
                "SELECT id, started_at FROM sessions "
                "WHERE status='active' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
    except Exception:
        return None


async def ble_main():
    while True:
        state["ble_status"] = "scanning"
        state["ble_devices"] = []
        try:
            devices = await BleakScanner.discover(timeout=10)
        except Exception:
            await asyncio.sleep(5)
            continue

        pm5_devs = [d for d in devices if d.name and "PM5" in d.name]
        if not pm5_devs:
            await asyncio.sleep(5)
            continue

        state["ble_devices"] = [{"address": d.address, "name": d.name} for d in pm5_devs]

        # Choose which device to connect to
        pref = state.get("ble_address")
        target = next((d for d in pm5_devs if d.address == pref), None) if pref else None

        if target is None and len(pm5_devs) == 1:
            # Only one erg — auto-select it
            target = pm5_devs[0]
            state["ble_address"] = target.address

        if target is None:
            # Multiple ergs, no preference yet — wait for user to pick via /api/ble/connect
            state["ble_status"] = "found"
            while not state.get("ble_address"):
                await asyncio.sleep(0.5)
            pref = state["ble_address"]
            target = next((d for d in pm5_devs if d.address == pref), None)
            if target is None:
                # Preference set but device not in last scan; clear and rescan
                state["ble_address"] = None
                continue

        state["ble_status"] = "connecting"
        state["ble_name"]   = target.name
        try:
            async with BleakClient(target.address) as client:
                state["ble_status"] = "connected"
                await client.start_notify(ROWING_STATUS_UUID,   lambda s, d: parse_general_status(d))
                await client.start_notify(ADD_STATUS_UUID,      lambda s, d: parse_add_status_1(d))
                await client.start_notify(STROKE_DATA_UUID,     lambda s, d: parse_stroke_data(d))
                await client.start_notify(HR_UUID,              lambda s, d: parse_heart_rate(d))
                await client.start_notify(WORKOUT_SUMMARY_UUID, lambda s, d: parse_workout_summary(d))
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception:
            pass
        state["ble_status"] = "disconnected"
        await asyncio.sleep(3)


def start_ble():
    _init_db()
    load_user_profile()
    asyncio.run(ble_main())
