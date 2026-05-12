"""
FastAPI web server — primary UI entry point.

Run:
    uvicorn server:app --host 0.0.0.0 --port 8501 --reload

Open http://<UNO-Q-IP>:8501 in iPad Safari.
"""
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ble.pm5 import (
    state, start_ble,
    start_session, stop_session, pause_session, resume_session,
    find_resumable_session, has_user_profile,
    save_user_profile, load_user_profile,
)
from ble.ftms import start_ftms
from ui.audio import check_and_cue, reset_cues
from db.workouts import list_workouts, get_workout, save_workout, delete_workout, workout_summary
from db.training_plan import get_plan, set_day, clear_day, get_today
from db.strive import calculate_strive_score, ZONE_COLORS, ZONE_NAMES, estimate_max_hr
from db.streak import get_streak

_DB_PATH = "rowing.db"

app = FastAPI()

# ── Start background threads once at import time ─────────────────────────────
_ble_thread = threading.Thread(target=start_ble, daemon=True, name="ble")
_ble_thread.start()

start_ftms()

def _audio_loop():
    while True:
        check_and_cue()
        time.sleep(1.0)

threading.Thread(target=_audio_loop, daemon=True, name="audio").start()

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


# ── Live state ────────────────────────────────────────────────────────────────

def _update_interval_state():
    """Track which interval the rower is in based on active workout definition."""
    wid = state.get("active_workout_id")
    if not wid or not state.get("session_active"):
        state["interval_index"] = 0
        state["interval_phase"] = "work"
        state["interval_remaining"] = None
        return
    w = get_workout(wid)
    if not w:
        return
    intervals = w[2].get("intervals", [])
    if not intervals:
        return

    dist    = state.get("distance", 0)
    elapsed = state.get("elapsed", 0)
    cumulative_dist = 0.0
    cumulative_time = 0.0

    for i, iv in enumerate(intervals):
        iv_type = iv.get("type")
        rest    = iv.get("rest_secs", 0)

        if iv_type == "distance":
            work_end = cumulative_dist + iv.get("meters", 0)
            if dist < work_end:
                state["interval_index"] = i
                state["interval_phase"] = "work"
                state["interval_remaining"] = round(work_end - dist)
                return
            cumulative_dist = work_end
            # rest phase (time-based)
            if rest > 0:
                rest_end = cumulative_time + rest
                if elapsed < rest_end:
                    state["interval_index"] = i
                    state["interval_phase"] = "rest"
                    state["interval_remaining"] = round(rest_end - elapsed)
                    return
                cumulative_time += rest

        elif iv_type == "time":
            work_end = cumulative_time + iv.get("seconds", 0)
            if elapsed < work_end:
                state["interval_index"] = i
                state["interval_phase"] = "work"
                state["interval_remaining"] = round(work_end - elapsed)
                return
            cumulative_time = work_end
            if rest > 0:
                rest_end = cumulative_time + rest
                if elapsed < rest_end:
                    state["interval_index"] = i
                    state["interval_phase"] = "rest"
                    state["interval_remaining"] = round(rest_end - elapsed)
                    return
                cumulative_time += rest

    state["interval_index"] = len(intervals) - 1
    state["interval_phase"] = "done"
    state["interval_remaining"] = 0


@app.get("/api/state")
def api_state():
    _update_interval_state()
    s = dict(state)
    s["hr_bpm"] = s["hr_bpm"] if isinstance(s["hr_bpm"], int) else None
    s["spm"]    = s["spm"]    if isinstance(s["spm"], int)    else None
    elapsed = int(s.get("elapsed", 0))
    s["elapsed_str"] = f"{elapsed // 60}:{elapsed % 60:02d}"
    s["distance_str"] = f"{s.get('distance', 0):.0f}"
    # Pace colour vs target
    target = s.get("target_pace_sec")
    speed  = s.get("speed_mm_s", 0)
    if target and speed > 0:
        current = 500 / (speed / 1000)
        s["pace_color"] = "green" if current <= target * 1.02 else "red"
    else:
        s["pace_color"] = ""
    # Total intervals count for display
    wid = state.get("active_workout_id")
    if wid:
        w = get_workout(wid)
        s["interval_total"] = len(w[2].get("intervals", [])) if w else 0
    else:
        s["interval_total"] = 0
    return JSONResponse(s)


# ── Session control ───────────────────────────────────────────────────────────

@app.post("/api/start")
def api_start():
    reset_cues()
    sid = start_session(workout_id=state.get("active_workout_id"))
    return {"session_id": sid}


@app.post("/api/pause")
def api_pause():
    pause_session()
    return {"ok": True}


@app.post("/api/resume")
def api_resume():
    resume_session()
    return {"ok": True}


@app.post("/api/end")
def api_end():
    sid = state.get("session_id")
    stop_session()
    prs = state.get("session_prs", [])
    return {"session_id": sid, "prs": prs}


class ResumeBody(BaseModel):
    session_id: int

@app.post("/api/resume-session")
def api_resume_session(body: ResumeBody):
    reset_cues()
    start_session(resume_id=body.session_id)
    return {"ok": True}


@app.get("/api/resumable")
def api_resumable():
    row = find_resumable_session()
    if not row:
        return {"session": None}
    sid, started_at = row
    ts = datetime.fromtimestamp(started_at).strftime("%H:%M") if started_at else "?"
    return {"session": {"id": sid, "started_at_str": ts}}


# ── Target pace ───────────────────────────────────────────────────────────────

class TargetBody(BaseModel):
    seconds: int | None = None   # None = clear

@app.post("/api/target")
def api_target(body: TargetBody):
    state["target_pace_sec"] = body.seconds
    return {"ok": True}


# ── Session summary ───────────────────────────────────────────────────────────

def _pace_str(sec):
    if not sec:
        return "--:--"
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"

def _time_str(sec):
    if not sec:
        return "--"
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@app.get("/api/summary/{session_id}")
def api_summary(session_id: int):
    with sqlite3.connect(_DB_PATH) as conn:
        sess = conn.execute(
            "SELECT started_at, ended_at, total_distance, total_time, "
            "       avg_pace, avg_watts, avg_spm, max_watts, calories, "
            "       avg_hr, max_hr, user_id, drag_factor, workout_id "
            "FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not sess:
            raise HTTPException(404, "session not found")

        speed_rows = conn.execute(
            "SELECT elapsed_secs, speed_mm_s FROM stroke_log "
            "WHERE session_id=? AND speed_mm_s > 0 ORDER BY elapsed_secs",
            (session_id,)
        ).fetchall()
        force_rows = conn.execute(
            "SELECT elapsed_secs, avg_force_n, peak_force_n FROM stroke_log "
            "WHERE session_id=? AND avg_force_n IS NOT NULL ORDER BY elapsed_secs",
            (session_id,)
        ).fetchall()
        dob_row = conn.execute(
            "SELECT dob FROM user_profile WHERE id="
            "(SELECT user_id FROM sessions WHERE id=?)", (session_id,)
        ).fetchone()

    (started_at, ended_at, dist, elapsed, avg_pace, avg_watts, avg_spm,
     max_watts, calories, avg_hr, max_hr, user_id, drag_factor, workout_id) = sess

    dob = dob_row[0] if dob_row else None
    max_hr_est = estimate_max_hr(dob) if dob else (max_hr or 185)
    score, zone_times = calculate_strive_score(session_id, max_hr_est)
    streak, longest = get_streak(user_id) if user_id else (0, 0)

    workout_name = None
    if workout_id:
        w = get_workout(workout_id)
        if w:
            workout_name = w[1]

    # Zone colours as hex
    zone_hex = [
        "#{:02x}{:02x}{:02x}".format(int(c[0]*255), int(c[1]*255), int(c[2]*255))
        for c in ZONE_COLORS
    ]

    return {
        "stats": {
            "distance":  f"{dist:.0f} m" if dist else "--",
            "time":      _time_str(elapsed),
            "avg_pace":  _pace_str(avg_pace),
            "avg_watts": f"{avg_watts:.0f} W" if avg_watts else "--",
            "avg_spm":   f"{avg_spm:.0f}" if avg_spm else "--",
            "avg_hr":    f"{avg_hr:.0f}" if avg_hr else "--",
        },
        "pace_series":  [{"x": r[0], "y": round(500 / (r[1]/1000), 1)} for r in speed_rows],
        "force_series": [{"x": r[0], "avg": r[1], "peak": r[2]} for r in force_rows],
        "strive": {
            "score":      score,
            "zone_times": zone_times,
            "zone_names": ZONE_NAMES,
            "zone_hex":   zone_hex,
        },
        "streak":       streak,
        "workout_name": workout_name,
        "drag_factor":  drag_factor,
        "prs":          state.get("session_prs", []),
    }


@app.get("/api/summary/{session_id}/splits")
def api_splits(session_id: int):
    """500m split breakdown for a session."""
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT elapsed_secs, speed_mm_s, hr_bpm "
            "FROM stroke_log WHERE session_id=? AND speed_mm_s > 0 "
            "ORDER BY elapsed_secs",
            (session_id,)
        ).fetchall()
        sess = conn.execute(
            "SELECT avg_pace FROM sessions WHERE id=?", (session_id,)
        ).fetchone()

    if not rows:
        return []

    session_avg_pace = sess[0] if sess else None
    split_m = 500
    splits = []
    bucket: list = []
    bucket_start_dist = 0.0
    running_dist = 0.0

    prev_elapsed = 0.0
    for elapsed, speed_mm_s, hr in rows:
        dt = elapsed - prev_elapsed
        prev_elapsed = elapsed
        if dt <= 0 or speed_mm_s <= 0:
            continue
        d = speed_mm_s / 1000 * dt
        running_dist += d
        bucket.append((elapsed, speed_mm_s, hr, dt))

        if running_dist - bucket_start_dist >= split_m:
            speeds  = [r[1] for r in bucket]
            hrs     = [r[2] for r in bucket if r[2]]
            dts     = [r[3] for r in bucket]
            avg_sp  = sum(speeds) / len(speeds)
            pace    = round(500 / (avg_sp / 1000)) if avg_sp > 0 else 0
            split_t = round(sum(dts))
            splits.append({
                "n":        len(splits) + 1,
                "dist":     f"{split_m}m",
                "pace":     _pace_str(pace),
                "pace_sec": pace,
                "time":     _time_str(split_t),
                "avg_hr":   round(sum(hrs) / len(hrs)) if hrs else None,
                "pace_vs_avg": "fast" if session_avg_pace and pace < session_avg_pace
                               else ("slow" if session_avg_pace and pace > session_avg_pace else ""),
            })
            bucket = []
            bucket_start_dist = running_dist

    return splits


# ── History ───────────────────────────────────────────────────────────────────

@app.get("/api/history")
def api_history():
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, started_at, total_distance, total_time, avg_pace "
            "FROM sessions WHERE status='complete' AND total_distance > 0 "
            "ORDER BY started_at DESC LIMIT 30"
        ).fetchall()
    return [
        {
            "id":      r[0],
            "label":   (datetime.fromtimestamp(r[1]).strftime("%b %d %H:%M") if r[1] else "?")
                       + f"  {r[2]:.0f}m  {_time_str(r[3])}  {_pace_str(r[4])}/500",
        }
        for r in rows
    ]


# ── Workouts ──────────────────────────────────────────────────────────────────

@app.get("/api/workouts")
def api_workouts():
    return [
        {"id": w[0], "name": w[1], "summary": workout_summary(w[2]), "is_preset": w[3]}
        for w in list_workouts()
    ]


class WorkoutBody(BaseModel):
    name: str
    intervals: list

@app.post("/api/workouts")
def api_save_workout(body: WorkoutBody):
    wid = save_workout(body.name, body.intervals)
    return {"id": wid}


class SelectWorkout(BaseModel):
    workout_id: int
    workout_name: str

@app.post("/api/workouts/select")
def api_select_workout(body: SelectWorkout):
    state["active_workout_id"]   = body.workout_id
    state["active_workout_name"] = body.workout_name
    return {"ok": True}


@app.delete("/api/workouts/{workout_id}")
def api_delete_workout(workout_id: int):
    delete_workout(workout_id)
    return {"ok": True}


# ── Training plan ─────────────────────────────────────────────────────────────

@app.get("/api/plan")
def api_plan():
    workouts = {w[0]: w[1] for w in list_workouts()}
    plan = get_plan()
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return [
        {
            "day": i,
            "name": days[i],
            "workout_id":   plan[i][0] if i in plan else None,
            "workout_name": workouts.get(plan[i][0], "") if i in plan else "",
        }
        for i in range(7)
    ]


class PlanBody(BaseModel):
    workout_id: int

@app.post("/api/plan/{day}")
def api_set_plan(day: int, body: PlanBody):
    set_day(day, body.workout_id)
    return {"ok": True}

@app.delete("/api/plan/{day}")
def api_clear_plan(day: int):
    clear_day(day)
    return {"ok": True}


# ── BLE device selection ─────────────────────────────────────────────────────

@app.get("/api/ble/devices")
def api_ble_devices():
    return {
        "status":  state.get("ble_status", "scanning"),
        "devices": state.get("ble_devices", []),
        "address": state.get("ble_address"),
        "name":    state.get("ble_name"),
    }


class BleConnectBody(BaseModel):
    address: str

@app.post("/api/ble/connect")
def api_ble_connect(body: BleConnectBody):
    """Set the preferred erg address. The BLE loop picks it up within 500 ms."""
    state["ble_address"] = body.address
    return {"ok": True}


# ── Profile ───────────────────────────────────────────────────────────────────

@app.get("/api/profile")
def api_profile():
    return {
        "name":       state.get("user_name", ""),
        "weight_kg":  state.get("user_weight_kg"),
        "height_cm":  state.get("user_height_cm"),
        "has_profile": has_user_profile(),
    }


class ProfileBody(BaseModel):
    name: str
    weight_kg: float
    height_cm: float
    dob: str | None = None

@app.post("/api/profile")
def api_save_profile(body: ProfileBody):
    uid = save_user_profile(body.name.strip(), body.weight_kg, body.height_cm, body.dob)
    return {"id": uid}
