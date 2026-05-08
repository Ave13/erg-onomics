import os
import sqlite3
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

_EXPORT_DIR = "exports"
_DB_PATH    = "rowing.db"


def export_tcx(session_id: int, db_path: str = _DB_PATH) -> str:
    os.makedirs(_EXPORT_DIR, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        session = conn.execute(
            "SELECT started_at, ended_at, total_distance, total_time, avg_hr, max_hr "
            "FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        strokes = conn.execute(
            "SELECT elapsed_secs, speed_mm_s, hr_bpm, stroke_count "
            "FROM stroke_log WHERE session_id=? ORDER BY elapsed_secs",
            (session_id,)
        ).fetchall()

    if not session:
        return ""

    started_at, ended_at, total_dist, total_time, avg_hr, max_hr = session
    start_dt = datetime.fromtimestamp(started_at or 0, tz=timezone.utc)

    NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    root = ET.Element("TrainingCenterDatabase",
                      attrib={"xmlns": NS,
                              "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"})
    workouts = ET.SubElement(root, "Workouts")
    workout  = ET.SubElement(workouts, "Workout", Sport="Other")
    ET.SubElement(workout, "Name").text = f"Rowing {start_dt.strftime('%Y-%m-%d %H:%M')}"

    lap = ET.SubElement(workout, "Lap", StartTime=start_dt.isoformat())
    ET.SubElement(lap, "TotalTimeSeconds").text = str(round(total_time or 0))
    ET.SubElement(lap, "DistanceMeters").text   = str(round(total_dist or 0))
    ET.SubElement(lap, "Intensity").text        = "Active"
    ET.SubElement(lap, "TriggerMethod").text    = "Manual"

    if avg_hr:
        el = ET.SubElement(lap, "AverageHeartRateBpm")
        ET.SubElement(el, "Value").text = str(int(avg_hr))
    if max_hr:
        el = ET.SubElement(lap, "MaximumHeartRateBpm")
        ET.SubElement(el, "Value").text = str(int(max_hr))

    track = ET.SubElement(lap, "Track")
    cum_dist = 0.0
    prev_elapsed = 0.0
    for elapsed, speed_mm_s, hr_bpm, stroke_count in strokes:
        dt_delta = elapsed - prev_elapsed
        cum_dist += (speed_mm_s / 1000) * dt_delta if speed_mm_s else 0
        prev_elapsed = elapsed

        tp = ET.SubElement(track, "Trackpoint")
        tp_dt = datetime.fromtimestamp(started_at + elapsed, tz=timezone.utc)
        ET.SubElement(tp, "Time").text           = tp_dt.isoformat()
        ET.SubElement(tp, "DistanceMeters").text = f"{cum_dist:.1f}"
        if hr_bpm:
            el = ET.SubElement(tp, "HeartRateBpm")
            ET.SubElement(el, "Value").text = str(int(hr_bpm))
        if stroke_count:
            ET.SubElement(tp, "Cadence").text = str(stroke_count)

    filename = f"session_{session_id}_{start_dt.strftime('%Y%m%d_%H%M%S')}.tcx"
    filepath = os.path.join(_EXPORT_DIR, filename)
    ET.ElementTree(root).write(filepath, encoding="UTF-8", xml_declaration=True)

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE sessions SET tcx_path=? WHERE id=?", (filepath, session_id))
    except Exception:
        pass

    return filepath
