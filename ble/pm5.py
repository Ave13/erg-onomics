import asyncio
import collections
import sqlite3
import time

from bleak import BleakClient, BleakScanner

ROWING_STATUS_UUID = "CE060031-43E5-11E4-916C-0800200C9A66"
ADD_STATUS_UUID    = "CE060032-43E5-11E4-916C-0800200C9A66"

_DB_PATH = "rowing.db"

state = {
    "pace": "--:--",
    "spm": "--",
    "interval": "--",
    "watts": 0,
    "distance": 0.0,
    "elapsed": 0.0,
    "workout_state": 0,
    "stroke_count": 0,
}

_stroke_times = collections.deque(maxlen=10)
_prev_stroke_count = 0
_STROKE_STALE_SECS = 10


def speed_to_pace(speed_mm_s):
    if speed_mm_s == 0:
        return "--:--"
    speed_m_s = speed_mm_s / 1000
    pace_sec = 500 / speed_m_s
    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"


def pace_to_watts(pace_sec):
    if pace_sec == 0:
        return 0
    return round(2.80 / (pace_sec / 60) ** 3)


def _calc_spm():
    if len(_stroke_times) < 2:
        return "--"
    if time.monotonic() - _stroke_times[-1] > _STROKE_STALE_SECS:
        return "--"
    span = _stroke_times[-1] - _stroke_times[0]
    if span <= 0:
        return "--"
    return round((len(_stroke_times) - 1) / span * 60)


def _log_stroke(stroke_num, elapsed_secs, interval_secs, speed_mm_s):
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO stroke_log "
                "(stroke_num, elapsed_secs, interval_secs, speed_mm_s, logged_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (stroke_num, elapsed_secs, round(interval_secs, 4), speed_mm_s, time.time()),
            )
    except Exception:
        pass


def _init_db():
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS stroke_log ("
                "id INTEGER PRIMARY KEY, "
                "stroke_num INTEGER NOT NULL, "
                "elapsed_secs REAL NOT NULL, "
                "interval_secs REAL NOT NULL, "
                "speed_mm_s INTEGER NOT NULL, "
                "logged_at REAL NOT NULL)"
            )
    except Exception:
        pass


def parse_general_status(data):
    global _prev_stroke_count
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
        _stroke_times.clear()
        _prev_stroke_count = 0
        state["spm"] = "--"
        state["interval"] = "--"


def parse_add_status_1(data):
    global _prev_stroke_count
    if len(data) < 6:
        return
    speed_mm_s = int.from_bytes(data[0:2], "little")
    stroke_count = int.from_bytes(data[4:6], "little")
    pace_str = speed_to_pace(speed_mm_s)
    pace_sec = (500 / (speed_mm_s / 1000)) if speed_mm_s > 0 else 0
    state["pace"] = pace_str
    state["watts"] = pace_to_watts(pace_sec)
    state["stroke_count"] = stroke_count

    new_strokes = stroke_count - _prev_stroke_count
    if new_strokes > 0:
        now = time.monotonic()
        for _ in range(new_strokes):
            if _stroke_times:
                interval = now - _stroke_times[-1]
                state["interval"] = f"{interval:.2f}s"
                _log_stroke(stroke_count, state["elapsed"], interval, speed_mm_s)
            _stroke_times.append(now)
        _prev_stroke_count = stroke_count

    state["spm"] = _calc_spm()


async def ble_main():
    while True:
        devices = await BleakScanner.discover(timeout=10)
        pm5 = next((d for d in devices if d.name and "PM5" in d.name), None)
        if not pm5:
            await asyncio.sleep(5)
            continue
        try:
            async with BleakClient(pm5.address) as client:
                await client.start_notify(ROWING_STATUS_UUID, lambda s, d: parse_general_status(d))
                await client.start_notify(ADD_STATUS_UUID, lambda s, d: parse_add_status_1(d))
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception:
            await asyncio.sleep(3)


def start_ble():
    _init_db()
    asyncio.run(ble_main())
