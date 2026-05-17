"""
FastAPI web server — primary UI entry point.

Run:
    uvicorn server:app --host 0.0.0.0 --port 8501 --reload

Open http://erg.local:8501 (home WiFi) or http://10.0.0.1:8501 (ErgRower AP).
"""
import os
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sensors.tof import start_tof
from ble.pm5 import (
    state, start_ble, send_csafe, request_disconnect,
    start_session, stop_session, pause_session, resume_session,
    find_resumable_session, has_user_profile,
    save_user_profile, load_user_profile,
)
from ble.csafe import workout_frames
from ble.ftms import start_ftms
from ui.audio import check_and_cue, reset_cues
from db.workouts import list_workouts, get_workout, save_workout, update_workout, delete_workout, workout_summary
from db.training_plan import get_plan, set_day, clear_day, get_today
from db.strive import calculate_strive_score, ZONE_COLORS, ZONE_NAMES, estimate_max_hr
from db.streak import get_streak

_DB_PATH = "rowing.db"

# ── WiFi interface detection ──────────────────────────────────────────────────

def _detect_wlan():
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "dev"],
            capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            dev, _, typ = line.partition(":")
            if typ.strip() == "wifi":
                return dev.strip()
    except Exception:
        pass
    return "wlan0"

_WLAN = _detect_wlan()

app = FastAPI()

# ── Start background threads once at import time ─────────────────────────────
if os.environ.get("MOCK_BLE"):
    from ble.mock import start_mock
    start_mock()
else:
    threading.Thread(target=start_ble, daemon=True, name="ble").start()

start_ftms()
start_tof(state)

def _audio_loop():
    while True:
        check_and_cue()
        time.sleep(1.0)

threading.Thread(target=_audio_loop, daemon=True, name="audio").start()

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


def _git_version():
    try:
        h = subprocess.check_output(["git","rev-parse","--short","HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        d = subprocess.check_output(["git","log","-1","--format=%ci"], stderr=subprocess.DEVNULL).decode().strip()[:16]
        return f"{h} {d}"
    except Exception:
        return "unknown"

_VERSION = _git_version()

@app.get("/")
def index():
    return FileResponse(
        "static/index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate",
                 "X-App-Version": _VERSION}
    )

@app.get("/api/version")
def api_version():
    return {"version": _VERSION}


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
            # rest phase: stamp when rest began so countdown is relative, not absolute
            if rest > 0:
                rest_key = f"_rest_t{i}"
                if state.get(rest_key) is None:
                    state[rest_key] = state.get("elapsed", 0)
                rest_start = state[rest_key]
                if state.get("elapsed", 0) < rest_start + rest:
                    state["interval_index"] = i
                    state["interval_phase"] = "rest"
                    state["interval_remaining"] = round(rest_start + rest - state.get("elapsed", 0))
                    return
                state.pop(rest_key, None)

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
    speed = s.get("speed_mm_s", 0)
    s["pace_sec"] = round(500_000 / speed) if speed > 0 else None
    # Pace colour vs target
    target = s.get("target_pace_sec")
    speed  = s.get("speed_mm_s", 0)
    if target and speed > 0:
        current = 500 / (speed / 1000)
        s["pace_color"] = "green" if current <= target * 1.02 else "red"
    else:
        s["pace_color"] = ""
    # Total intervals count + current interval coaching targets
    wid = state.get("active_workout_id")
    if wid:
        w = get_workout(wid)
        if w:
            intervals = w[2].get("intervals", [])
            s["interval_total"] = len(intervals)
            idx = state.get("interval_index", 0)
            if 0 <= idx < len(intervals):
                iv = intervals[idx]
                s["interval_target_spm"]     = iv.get("target_spm")
                s["interval_target_hr_zone"] = iv.get("target_hr_zone")
                s["interval_target_watts"]   = iv.get("target_watts")
                s["interval_goal_type"]      = iv.get("type")
                s["interval_goal_value"]     = (
                    iv.get("meters")   if iv.get("type") == "distance" else
                    iv.get("seconds")  if iv.get("type") == "time"     else
                    iv.get("calories") if iv.get("type") == "calorie"  else
                    None
                )
                s["interval_rest_secs"] = iv.get("rest_secs", 0)
            else:
                s["interval_target_spm"] = s["interval_target_hr_zone"] = s["interval_target_watts"] = None
                s["interval_goal_type"] = s["interval_goal_value"] = s["interval_rest_secs"] = None
        else:
            s["interval_total"] = 0
            s["interval_target_spm"] = s["interval_target_hr_zone"] = s["interval_target_watts"] = None
            s["interval_goal_type"] = s["interval_goal_value"] = s["interval_rest_secs"] = None
    else:
        s["interval_total"] = 0
        s["interval_target_spm"] = s["interval_target_hr_zone"] = s["interval_target_watts"] = None
        s["interval_goal_type"] = s["interval_goal_value"] = s["interval_rest_secs"] = None
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
            "SELECT elapsed_secs, speed_mm_s, hr_bpm, watts, peak_avg_ratio "
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
    for elapsed, speed_mm_s, hr, watts, peak_avg_ratio in rows:
        dt = elapsed - prev_elapsed
        prev_elapsed = elapsed
        if dt <= 0 or speed_mm_s <= 0:
            continue
        d = speed_mm_s / 1000 * dt
        running_dist += d
        bucket.append((elapsed, speed_mm_s, hr, dt, watts, peak_avg_ratio))

        if running_dist - bucket_start_dist >= split_m:
            speeds   = [r[1] for r in bucket]
            hrs      = [r[2] for r in bucket if r[2]]
            dts      = [r[3] for r in bucket]
            wattses  = [r[4] for r in bucket if r[4]]
            ratios   = [r[5] for r in bucket if r[5]]
            avg_sp   = sum(speeds) / len(speeds)
            pace     = round(500 / (avg_sp / 1000)) if avg_sp > 0 else 0
            split_t  = round(sum(dts))
            splits.append({
                "n":           len(splits) + 1,
                "dist":        f"{split_m}m",
                "pace":        _pace_str(pace),
                "pace_sec":    pace,
                "time":        _time_str(split_t),
                "avg_hr":      round(sum(hrs) / len(hrs)) if hrs else None,
                "avg_watts":   round(sum(wattses) / len(wattses)) if wattses else None,
                "avg_ratio":   round(sum(ratios) / len(ratios), 2) if ratios else None,
                "pace_vs_avg": "fast" if session_avg_pace and pace < session_avg_pace
                               else ("slow" if session_avg_pace and pace > session_avg_pace else ""),
            })
            bucket = []
            bucket_start_dist = running_dist

    return splits


@app.get("/api/summary/{session_id}/strokes")
def api_strokes(session_id: int):
    """Per-stroke data for correlation analysis and future video frame sync."""
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT elapsed_secs, speed_mm_s, drive_length_cm, drive_time_secs, "
            "       recovery_secs, peak_force_n, avg_force_n, "
            "       watts, peak_avg_ratio, hr_bpm, logged_at "
            "FROM stroke_log WHERE session_id=? ORDER BY elapsed_secs",
            (session_id,)
        ).fetchall()
    return [
        {
            "elapsed":       r[0],
            "pace_sec":      round(500_000 / r[1]) if r[1] and r[1] > 0 else None,
            "drive_length":  r[2],
            "drive_time":    r[3],
            "recovery":      r[4],
            "peak_force_n":  r[5],
            "avg_force_n":   r[6],
            "watts":         r[7],
            "peak_avg_ratio": r[8],
            "hr_bpm":        r[9],
            "logged_at":     r[10],
        }
        for r in rows
    ]


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
    # Sync workout to PM5 over BLE (no-op if disconnected or mock)
    if state.get("ble_status") == "connected" and not os.environ.get("MOCK_BLE"):
        w = get_workout(body.workout_id)
        if w:
            intervals = w[2].get("intervals", [])
            send_csafe(workout_frames(intervals))
    return {"ok": True}


@app.get("/api/workouts/{workout_id}")
def api_get_workout(workout_id: int):
    w = get_workout(workout_id)
    if not w:
        raise HTTPException(status_code=404, detail="Not found")
    wid, name, defn, is_preset = w
    return {"id": wid, "name": name, "intervals": defn.get("intervals", []), "is_preset": is_preset}


@app.put("/api/workouts/{workout_id}")
def api_update_workout(workout_id: int, body: WorkoutBody):
    wid = update_workout(workout_id, body.name, body.intervals)
    return {"id": wid}


@app.delete("/api/workouts/{workout_id}")
def api_delete_workout(workout_id: int):
    delete_workout(workout_id)
    return {"ok": True}


@app.post("/api/ble/disconnect")
def api_ble_disconnect():
    """Drop the current PM5 connection and clear saved address."""
    request_disconnect()
    return {"ok": True}


@app.post("/api/demo")
def api_demo_toggle():
    """Toggle mock PM5 emulator on/off. Returns new demo_active state."""
    if state.get("demo_active"):
        state["demo_active"]    = False   # loop sees this and exits
        state["session_active"] = False
        state["session_paused"] = False
        return {"demo_active": False}
    from ble.mock import start_mock
    start_mock()
    return {"demo_active": True}


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


# ── WiFi management ──────────────────────────────────────────────────────────

def _nmcli(*args, timeout=15):
    for cmd in [["nmcli"], ["sudo", "nmcli"]]:
        r = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return r
    return r


@app.get("/api/wifi/status")
def api_wifi_status():
    try:
        out = _nmcli("-t", "-f", "NAME,TYPE,STATE", "con", "show", "--active", timeout=5).stdout
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 2:
                continue
            name, con_type = parts[0], parts[1]
            if "wireless" not in con_type:
                continue
            ip = ""
            try:
                dev_out = _nmcli("-t", "-f", "IP4.ADDRESS", "con", "show", name, timeout=3).stdout
                for dl in dev_out.splitlines():
                    if dl.startswith("IP4.ADDRESS"):
                        ip = dl.split(":")[-1].split("/")[0]
                        break
            except Exception:
                pass
            return {"connection": name, "ip": ip,
                    "ap_mode": name == "ErgRower", "interface": _WLAN}
        return {"connection": "", "ip": "", "ap_mode": False, "interface": _WLAN}
    except Exception:
        return {"connection": "", "ip": "", "ap_mode": False, "interface": _WLAN}


@app.get("/api/wifi/scan")
def api_wifi_scan():
    try:
        out = _nmcli("-t", "-f", "SSID,SIGNAL,SECURITY",
                     "dev", "wifi", "list",
                     "ifname", _WLAN, "--rescan", "yes", timeout=20).stdout
        seen, networks = set(), []
        for line in out.splitlines():
            # nmcli -t escapes ':' as '\:' in values
            parts = line.replace("\\:", "\x00").split(":")
            parts = [p.replace("\x00", ":") for p in parts]
            if len(parts) < 2:
                continue
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            networks.append({
                "ssid":     ssid,
                "signal":   int(parts[1]) if parts[1].isdigit() else 0,
                "security": parts[2].strip() if len(parts) > 2 else "",
            })
        networks.sort(key=lambda x: -x["signal"])
        return {"networks": networks}
    except Exception:
        return {"networks": []}


class WifiConnectBody(BaseModel):
    ssid: str
    password: str = ""

@app.post("/api/wifi/connect")
def api_wifi_connect(body: WifiConnectBody):
    try:
        args = ["dev", "wifi", "connect", body.ssid]
        if body.password:
            args += ["password", body.password]
        args += ["ifname", _WLAN]
        result = _nmcli(*args, timeout=30)
        ok = result.returncode == 0
        msg = result.stdout.strip() if ok else (result.stderr.strip() or result.stdout.strip())
        return {"ok": ok, "message": msg}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Connection timed out — wrong password?"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@app.get("/api/wifi/saved")
def api_wifi_saved():
    try:
        out = _nmcli("-t", "-f", "NAME,TYPE,DEVICE", "con", "show", timeout=5).stdout
        networks = []
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and "wireless" in parts[1] and parts[0] != "ErgRower":
                networks.append({
                    "ssid":      parts[0],
                    "connected": len(parts) > 2 and parts[2] not in ("", "--"),
                })
        return {"networks": networks}
    except Exception:
        return {"networks": []}


class WifiForgetBody(BaseModel):
    ssid: str

@app.post("/api/wifi/forget")
def api_wifi_forget(body: WifiForgetBody):
    try:
        r = _nmcli("con", "delete", body.ssid, timeout=10)
        return {"ok": r.returncode == 0}
    except Exception:
        return {"ok": False}


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
        "name":        state.get("user_name", ""),
        "weight_kg":   state.get("user_weight_kg"),
        "height_cm":   state.get("user_height_cm"),
        "dob":         state.get("user_dob"),
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
