import sqlite3
import threading
import time
from datetime import datetime

import streamlit as st

from ble.pm5 import (
    state, start_ble,
    start_session, stop_session, pause_session, resume_session,
    find_resumable_session, has_user_profile, save_user_profile,
)
from ble.ftms import start_ftms
from ui.audio import check_and_cue, reset_cues
from db.streak import get_streak
from db.training_plan import get_plan, set_day, clear_day, get_today
from db.workouts import (
    get_workout, list_workouts, save_workout, delete_workout,
    workout_summary, _interval_label,
)
from db.strive import (
    calculate_strive_score, ZONE_COLORS, ZONE_NAMES, estimate_max_hr,
)
from streamlit_css import CSS

try:
    import plotly.graph_objects as go
    _PLOTLY = True
except ImportError:
    _PLOTLY = False

_DB = "rowing.db"

# ── Thread singletons (process-wide, not per browser session) ─────
_BLE_STARTED = False
_BLE_LOCK = threading.Lock()


def _start_threads():
    global _BLE_STARTED
    if _BLE_STARTED:
        return
    with _BLE_LOCK:
        if _BLE_STARTED:
            return
        threading.Thread(target=start_ble, daemon=True, name="ble").start()
        start_ftms()

        def _audio():
            while True:
                check_and_cue()
                time.sleep(1.0)

        threading.Thread(target=_audio, daemon=True, name="audio-cue").start()
        _BLE_STARTED = True


_start_threads()

# ── Page config ────────────────────────────────────────────────────
st.set_page_config(
    page_title="Erg-onomics",
    page_icon="🚣",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(CSS, unsafe_allow_html=True)

# ── session_state defaults ─────────────────────────────────────────
def _ss(k, v):
    if k not in st.session_state:
        st.session_state[k] = v


_ss("last_sid", None)
_ss("last_prs", [])
_ss("target_pace_sec", None)
_ss("resume_checked", False)
_ss("show_target", False)
_ss("new_wk_intervals", [])

# ── Helpers ────────────────────────────────────────────────────────

def _pace_str(sec):
    if not sec:
        return "--:--"
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def _time_str(sec):
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _card(label, value, color="#f2f2f8"):
    return (
        f'<div style="background:#1e2030;border-radius:12px;padding:14px 8px 10px;'
        f'text-align:center;margin:2px 0">'
        f'<div style="font-size:13px;color:#737aaa;text-transform:uppercase;'
        f'letter-spacing:.07em;margin-bottom:6px">{label}</div>'
        f'<div style="font-size:2.5rem;font-weight:700;color:{color};line-height:1.1">{value}</div>'
        f'</div>'
    )


def _zone_bar_html(zone_times):
    total = sum(zone_times) or 1
    segs = "".join(
        f'<span title="{ZONE_NAMES[i]}" style="display:inline-block;height:100%;'
        f'width:{t / total * 100:.1f}%;'
        f'background:rgb({int(c[0]*255)},{int(c[1]*255)},{int(c[2]*255)})"></span>'
        for i, (t, c) in enumerate(zip(zone_times, ZONE_COLORS))
        if t > 0
    )
    return (
        f'<div style="display:flex;height:20px;border-radius:5px;overflow:hidden;'
        f'margin:4px 0 8px">{segs}</div>'
    )


# ── Summary renderer ───────────────────────────────────────────────

def _render_summary(session_id, prs):
    with sqlite3.connect(_DB) as conn:
        sess = conn.execute(
            "SELECT started_at, ended_at, total_distance, total_time, avg_pace, "
            "       avg_watts, avg_spm, max_watts, calories, avg_hr, max_hr, "
            "       user_id, drag_factor, workout_id "
            "FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not sess:
            st.warning("Session data not found.")
            return
        speed_rows = conn.execute(
            "SELECT elapsed_secs, speed_mm_s FROM stroke_log "
            "WHERE session_id=? AND speed_mm_s > 0 ORDER BY elapsed_secs",
            (session_id,),
        ).fetchall()
        force_rows = conn.execute(
            "SELECT elapsed_secs, avg_force_n, peak_force_n FROM stroke_log "
            "WHERE session_id=? AND avg_force_n IS NOT NULL ORDER BY elapsed_secs",
            (session_id,),
        ).fetchall()
        dob_row = conn.execute(
            "SELECT dob FROM user_profile WHERE id=("
            "SELECT user_id FROM sessions WHERE id=?)", (session_id,)
        ).fetchone()

    (started_at, ended_at, dist, elapsed, avg_pace,
     avg_watts, avg_spm, max_watts, calories,
     avg_hr, max_hr, user_id, drag_factor, workout_id) = sess
    dob = dob_row[0] if dob_row else None

    # Stats grid
    c1, c2, c3 = st.columns(3)
    c1.metric("Distance",  f"{dist:.0f} m"      if dist      else "--")
    c2.metric("Time",      _time_str(elapsed))
    c3.metric("Avg Pace",  f"{_pace_str(avg_pace)}/500" if avg_pace else "--")
    c4, c5, c6 = st.columns(3)
    c4.metric("Avg Watts", f"{avg_watts:.0f} W"  if avg_watts else "--")
    c5.metric("Avg SPM",   f"{avg_spm:.0f}"      if avg_spm   else "--")
    c6.metric("Avg HR",    f"{avg_hr:.0f} bpm"   if avg_hr    else "--")

    # Workout + drag factor metadata
    meta = []
    if workout_id:
        w = get_workout(workout_id)
        if w:
            meta.append(w[1])
    if drag_factor:
        meta.append(f"Drag {drag_factor}")
    if meta:
        st.caption("  ·  ".join(meta))

    # Pace graph
    if speed_rows and _PLOTLY:
        xs = [r[0] for r in speed_rows]
        ys = [500 / (r[1] / 1000) for r in speed_rows]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color="#33bf8a", width=2), name="s/500m",
        ))
        fig.update_layout(
            height=180, margin=dict(l=40, r=10, t=10, b=30),
            paper_bgcolor="#1e2030", plot_bgcolor="#1e2030",
            font=dict(color="#737aaa"),
            yaxis=dict(autorange="reversed", title="s/500m"),
            xaxis=dict(title="elapsed (s)"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Force curve
    if force_rows and _PLOTLY:
        xs = [r[0] for r in force_rows]
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=xs, y=[r[1] for r in force_rows],
                                  mode="lines", line=dict(color="#4080f2", width=2),
                                  name="Avg N"))
        fig2.add_trace(go.Scatter(x=xs, y=[r[2] for r in force_rows],
                                  mode="lines", line=dict(color="#f27320", width=2),
                                  name="Peak N"))
        fig2.update_layout(
            height=150, margin=dict(l=40, r=10, t=10, b=30),
            paper_bgcolor="#1e2030", plot_bgcolor="#1e2030",
            font=dict(color="#737aaa"),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Strive Score
    max_hr_est = estimate_max_hr(dob) if dob else (max_hr or 185)
    score, zone_times = calculate_strive_score(session_id, max_hr_est)
    if score > 0:
        st.markdown(f"**Strive Score: {score:.0f}**")
        st.markdown(_zone_bar_html(zone_times), unsafe_allow_html=True)
        legend = "  ".join(
            f'<span style="color:rgb({int(c[0]*255)},{int(c[1]*255)},{int(c[2]*255)})">'
            f'● {ZONE_NAMES[i]}: {_time_str(t)}</span>'
            for i, (t, c) in enumerate(zip(zone_times, ZONE_COLORS)) if t > 0
        )
        st.markdown(f'<div style="font-size:.8rem">{legend}</div>', unsafe_allow_html=True)

    # Streak
    if user_id:
        cur_s, longest = get_streak(user_id)
        if cur_s > 0:
            txt = f"{cur_s}-day streak"
            if longest > cur_s:
                txt += f"  (longest {longest})"
            st.info(txt)

    # PRs
    _PR_NAMES = {
        "longest_distance": "Best distance",
        "longest_time":     "Longest time",
        "best_avg_watts":   "Best avg watts",
        "best_max_watts":   "Best peak watts",
        "best_avg_spm":     "Best avg SPM",
    }
    for rtype, _old, new in (prs or []):
        if rtype.startswith("pace_"):
            dist_label = rtype.replace("pace_", "").replace("m", "") + "m"
            txt = f"★  {dist_label} pace  {_pace_str(new)}/500m"
        else:
            txt = f"★  {_PR_NAMES.get(rtype, rtype)}  {new:.0f}"
        st.markdown(
            f'<div style="background:#2d2a10;border-left:4px solid #e6c21a;'
            f'border-radius:4px;padding:6px 12px;margin:3px 0;color:#e6c21a">{txt}</div>',
            unsafe_allow_html=True,
        )


# ── Comparison renderer ────────────────────────────────────────────

def _render_comparison(sid_a, sid_b):
    def _load(sid):
        with sqlite3.connect(_DB) as conn:
            sess = conn.execute(
                "SELECT total_distance, total_time, avg_pace, avg_watts, avg_spm, avg_hr "
                "FROM sessions WHERE id=?", (sid,)
            ).fetchone()
            pts = conn.execute(
                "SELECT elapsed_secs, speed_mm_s FROM stroke_log "
                "WHERE session_id=? AND speed_mm_s > 0 ORDER BY elapsed_secs", (sid,)
            ).fetchall()
        return sess, pts

    row_a, pts_a = _load(sid_a)
    row_b, pts_b = _load(sid_b)

    if row_a and row_b:
        da, ta, pa, wa, sa, ha = row_a
        db, tb, pb, wb, sb, hb = row_b
        c1, c2, c3 = st.columns(3)
        c1.metric("Distance A", f"{da:.0f}m" if da else "--",
                  delta=f"{da-db:+.0f}m" if da and db else None)
        c2.metric("Avg Pace A", _pace_str(pa),
                  delta=f"{_pace_str(pa)} vs {_pace_str(pb)}" if pa and pb else None,
                  delta_color="off")
        c3.metric("Avg Watts A", f"{wa:.0f}W" if wa else "--",
                  delta=f"{wa-wb:+.0f}W" if wa and wb else None)

    if (pts_a or pts_b) and _PLOTLY:
        fig = go.Figure()
        if pts_a:
            fig.add_trace(go.Scatter(
                x=[p[0] for p in pts_a],
                y=[500 / (p[1] / 1000) for p in pts_a],
                mode="lines", name="A", line=dict(color="#4080f2", width=2),
            ))
        if pts_b:
            fig.add_trace(go.Scatter(
                x=[p[0] for p in pts_b],
                y=[500 / (p[1] / 1000) for p in pts_b],
                mode="lines", name="B", line=dict(color="#f27320", width=2),
            ))
        fig.update_layout(
            height=220, margin=dict(l=40, r=10, t=10, b=30),
            paper_bgcolor="#1e2030", plot_bgcolor="#1e2030",
            font=dict(color="#737aaa"),
            yaxis=dict(autorange="reversed", title="s/500m"),
            xaxis=dict(title="elapsed (s)"),
        )
        st.plotly_chart(fig, use_container_width=True)


# ── Startup check ──────────────────────────────────────────────────
if not st.session_state.resume_checked:
    st.session_state.resume_checked = True
    if not has_user_profile():
        st.session_state._force_settings = True
    else:
        row = find_resumable_session()
        if row:
            st.session_state._resumable = row

# ── Tabs ───────────────────────────────────────────────────────────
tab_row, tab_hist, tab_wkt, tab_set = st.tabs(["🚣 Row", "📊 History", "🏋 Workouts", "⚙ Settings"])


# ══════════════════════════════════════════════════════════════════
# ROW TAB
# ══════════════════════════════════════════════════════════════════
with tab_row:
    # Resume banner
    if "_resumable" in st.session_state and not state["session_active"]:
        sid_r, started_at_r = st.session_state._resumable
        ts_r = datetime.fromtimestamp(started_at_r).strftime("%H:%M") if started_at_r else "?"
        st.info(f"Incomplete session from {ts_r} — resume or start new?")
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("Resume Session", use_container_width=True, key="btn_resume"):
                reset_cues()
                start_session(resume_id=sid_r)
                del st.session_state._resumable
                st.rerun()
        with rc2:
            if st.button("Discard & Start New", use_container_width=True, key="btn_discard"):
                with sqlite3.connect(_DB) as _c:
                    _c.execute("UPDATE sessions SET status='abandoned' WHERE id=?", (sid_r,))
                del st.session_state._resumable
                st.rerun()

    # ── Live metric fragment ───────────────────────────────────────
    @st.fragment(run_every=0.5)
    def _live():
        state["target_pace_sec"] = st.session_state.target_pace_sec
        s = state
        elapsed = int(s.get("elapsed", 0))
        time_str = f"{elapsed // 60}:{elapsed % 60:02d}"

        # Pace colour
        pace_color = "#f2f2f8"
        target = s.get("target_pace_sec")
        speed = s.get("speed_mm_s", 0)
        if target and speed > 0:
            cur_pace = 500 / (speed / 1000)
            pace_color = "#26da72" if cur_pace <= target * 0.98 else (
                "#ff5940" if cur_pace > target * 1.02 else "#f2f2f8"
            )

        hr = s.get("hr_bpm", "--")
        hr_color = "#f25757" if isinstance(hr, int) else "#f2f2f8"

        # 6 metric cards
        r1a, r1b, r1c = st.columns(3)
        r2a, r2b, r2c = st.columns(3)
        r1a.markdown(_card("Pace",   s.get("pace",     "--:--"), pace_color), unsafe_allow_html=True)
        r1b.markdown(_card("Watts",  s.get("watts",    0)),                   unsafe_allow_html=True)
        r1c.markdown(_card("SPM",    s.get("spm",      "--")),                unsafe_allow_html=True)
        r2a.markdown(_card("Dist m", f"{s.get('distance', 0):.0f}"),          unsafe_allow_html=True)
        r2b.markdown(_card("Time",   time_str),                               unsafe_allow_html=True)
        r2c.markdown(_card("HR",     str(hr),           hr_color),            unsafe_allow_html=True)

        # Status bar
        if s.get("session_paused"):
            bar = '<span style="color:#2e8cd9;font-weight:700">⏸ Paused</span>'
        elif s.get("session_active"):
            bar = '<span style="color:#26b870;font-weight:700">● Recording</span>'
        else:
            extras = []
            name = s.get("user_name", "")
            if name:
                extras.append(name)
            uid = s.get("user_id")
            if uid:
                cur, _ = get_streak(uid)
                if cur > 1:
                    extras.append(f"{cur}-day streak")
                wid, _ = get_today()
                if wid:
                    w = get_workout(wid)
                    if w:
                        extras.append(f"Today: {w[1]}")
            bar = "  ·  ".join(extras) if extras else "Ready"

        st.markdown(
            f'<div style="text-align:center;padding:6px 0 2px;color:#9aa0c0;font-size:.95rem">'
            f'{bar}</div>',
            unsafe_allow_html=True,
        )

        # ── Session controls (inside fragment so disabled state auto-refreshes) ──
        active = s.get("session_active", False)
        paused = s.get("session_paused", False)
        bc1, bc2, bc3 = st.columns(3)

        with bc1:
            st.markdown('<div class="btn-start">', unsafe_allow_html=True)
            if st.button("Start", disabled=active, use_container_width=True, key="btn_start"):
                reset_cues()
                start_session()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        with bc2:
            st.markdown('<div class="btn-pause">', unsafe_allow_html=True)
            lbl = "Resume" if paused else "Pause"
            if st.button(lbl, disabled=not active, use_container_width=True, key="btn_pause"):
                resume_session() if paused else pause_session()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        with bc3:
            st.markdown('<div class="btn-end">', unsafe_allow_html=True)
            if st.button("End", disabled=not active, use_container_width=True, key="btn_end"):
                sid = s.get("session_id")
                stop_session()
                st.session_state.last_sid = sid
                st.session_state.last_prs = state.get("session_prs", [])
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Target pace + workout info strip
        xc1, xc2 = st.columns(2)
        with xc1:
            cur = st.session_state.target_pace_sec
            cur_str = _pace_str(cur) if cur else "Off"
            if st.button(f"Target: {cur_str}/500", use_container_width=True, key="btn_tgt"):
                st.session_state.show_target = not st.session_state.show_target
                st.rerun()
        with xc2:
            wname = s.get("active_workout_name", "")
            wlabel = wname[:14] if wname else "No workout"
            st.markdown(
                f'<div style="background:#1e2030;border-radius:10px;height:60px;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:1rem;color:#9aa0c0;padding:0 12px">{wlabel}</div>',
                unsafe_allow_html=True,
            )

    _live()

    # Target pace expander (outside fragment — shown on toggle)
    if st.session_state.show_target:
        with st.expander("Set Target Pace /500m", expanded=True):
            cur = st.session_state.target_pace_sec or 105
            tm_col, ts_col = st.columns(2)
            tgt_m = tm_col.number_input("Min", 1, 9,  int(cur // 60), key="tgt_m")
            tgt_s = ts_col.number_input("Sec", 0, 59, int(cur % 60),  key="tgt_s")
            set_col, clr_col = st.columns(2)
            if set_col.button("Set", use_container_width=True, key="tgt_set"):
                st.session_state.target_pace_sec = tgt_m * 60 + tgt_s
                state["target_pace_sec"] = tgt_m * 60 + tgt_s
                st.session_state.show_target = False
                st.rerun()
            if clr_col.button("Clear", use_container_width=True, key="tgt_clr"):
                st.session_state.target_pace_sec = None
                state["target_pace_sec"] = None
                st.session_state.show_target = False
                st.rerun()


# ══════════════════════════════════════════════════════════════════
# HISTORY TAB
# ══════════════════════════════════════════════════════════════════
with tab_hist:
    if st.session_state.last_sid:
        st.subheader("Session Complete")
        _render_summary(st.session_state.last_sid, st.session_state.last_prs)
        if st.button("Dismiss", key="dismiss_summary", use_container_width=True):
            st.session_state.last_sid = None
            st.session_state.last_prs = []
            st.rerun()
        st.divider()

    with sqlite3.connect(_DB) as _conn:
        hist_rows = _conn.execute(
            "SELECT id, started_at, total_distance, total_time, avg_pace "
            "FROM sessions WHERE status='complete' AND total_distance > 0 "
            "ORDER BY started_at DESC LIMIT 30"
        ).fetchall()

    if not hist_rows:
        if not st.session_state.last_sid:
            st.info("No completed sessions yet — start rowing!")
    else:
        for _sid, _sat, _dist, _elapsed, _pace in hist_rows:
            _ts = datetime.fromtimestamp(_sat).strftime("%Y-%m-%d %H:%M") if _sat else "?"
            _lbl = f"{_ts}  ·  {_dist:.0f}m  ·  {_time_str(_elapsed)}  ·  {_pace_str(_pace)}/500"
            with st.expander(_lbl):
                _render_summary(_sid, [])

    if len(hist_rows) >= 2:
        st.divider()
        st.subheader("Compare Two Sessions")
        _hist_labels = [
            f"{datetime.fromtimestamp(r[1]).strftime('%m/%d %H:%M')}  {r[2]:.0f}m"
            for r in hist_rows
        ]
        _hist_ids = [r[0] for r in hist_rows]
        ca, cb = st.columns(2)
        ia = ca.selectbox("Session A", range(len(_hist_ids)),
                          format_func=lambda i: _hist_labels[i], key="cmp_a")
        ib = cb.selectbox("Session B", range(len(_hist_ids)),
                          format_func=lambda i: _hist_labels[i],
                          index=min(1, len(_hist_ids) - 1), key="cmp_b")
        if ia != ib:
            _render_comparison(_hist_ids[ia], _hist_ids[ib])


# ══════════════════════════════════════════════════════════════════
# WORKOUTS TAB
# ══════════════════════════════════════════════════════════════════
with tab_wkt:
    st.subheader("Select Workout")
    _workouts = list_workouts()

    for _wid, _wname, _wdef, _is_preset in _workouts:
        _tag = "[Preset] " if _is_preset else ""
        _summary = workout_summary(_wdef)
        wc1, wc2, wc3 = st.columns([3, 1, 1])
        wc1.markdown(
            f'<div style="padding:10px 0;color:#c8ceeb">'
            f'<strong>{_wname}</strong><br>'
            f'<span style="color:#737aaa;font-size:.85rem">{_tag}{_summary}</span></div>',
            unsafe_allow_html=True,
        )
        with wc2:
            if st.button("Select", key=f"sel_{_wid}", use_container_width=True):
                state["active_workout_id"]   = _wid
                state["active_workout_name"] = _wname
                st.success(f"Workout set: {_wname}")
                st.rerun()
        with wc3:
            if not _is_preset:
                if st.button("Delete", key=f"del_{_wid}", use_container_width=True):
                    delete_workout(_wid)
                    st.rerun()

    st.divider()
    st.subheader("Create Custom Workout")

    with st.form("new_workout", clear_on_submit=False):
        _new_name = st.text_input("Workout name", value="My Workout", key="new_wk_name")
        _iv_type = st.radio("Interval type", ["Distance", "Time"], horizontal=True, key="iv_type")

        _dist_values = [100, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000, 2500, 3000, 5000, 10000]
        _time_values = [30, 60, 90, 120, 150, 180, 240, 300, 360, 420, 480, 600, 900, 1200, 1800, 3600]
        _rest_values = [0, 30, 60, 90, 120, 150, 180, 240, 300, 360, 420, 480, 600]

        if _iv_type == "Distance":
            _meters = st.selectbox("Distance (m)", _dist_values,
                                   index=_dist_values.index(500), key="iv_dist")
        else:
            _seconds = st.selectbox(
                "Duration", _time_values,
                format_func=lambda v: f"{v // 60}:{v % 60:02d}",
                index=_time_values.index(300), key="iv_time",
            )
        _rest = st.selectbox(
            "Rest between intervals", _rest_values,
            format_func=lambda v: "No rest" if v == 0 else f"{v // 60}:{v % 60:02d}",
            key="iv_rest",
        )
        _reps = st.number_input("Repetitions", min_value=1, max_value=20, value=1, key="iv_reps")

        if st.form_submit_button("Save Workout", use_container_width=True):
            if _iv_type == "Distance":
                _ivs = [{"type": "distance", "meters": _meters, "rest_secs": _rest}] * _reps
            else:
                _ivs = [{"type": "time", "seconds": _seconds, "rest_secs": _rest}] * _reps
            _new_wid = save_workout(_new_name or "My Workout", _ivs)
            if _new_wid:
                st.success(f"Saved: {_new_name}")
                st.rerun()


# ══════════════════════════════════════════════════════════════════
# SETTINGS TAB
# ══════════════════════════════════════════════════════════════════
with tab_set:
    st.subheader("Profile")

    _cur_name   = state.get("user_name", "")
    _cur_wt     = float(state.get("user_weight_kg") or 80.0)
    _cur_ht_cm  = float(state.get("user_height_cm") or 172.72)
    _total_in   = _cur_ht_cm / 2.54
    _cur_ft     = int(_total_in // 12)
    _cur_in     = round(_total_in % 12)

    if st.session_state.get("_force_settings"):
        st.warning("Please fill in your profile before starting a session.")

    with st.form("profile_form"):
        _name = st.text_input("Name", value=_cur_name)
        _weight_kg = st.number_input("Weight (kg)", min_value=30.0, max_value=200.0,
                                     value=_cur_wt, step=0.5)
        _hcol1, _hcol2 = st.columns(2)
        _ht_ft = _hcol1.number_input("Height (ft)", min_value=4, max_value=7, value=_cur_ft)
        _ht_in = _hcol2.number_input("(in)",        min_value=0, max_value=11, value=_cur_in)
        _dob   = st.date_input("Date of Birth (for Strive Score max-HR estimate)", value=None)

        if st.form_submit_button("Save Profile", use_container_width=True):
            _height_cm = round(_ht_ft * 30.48 + _ht_in * 2.54, 1)
            _dob_str = _dob.isoformat() if _dob else None
            _uid = save_user_profile(_name.strip(), _weight_kg, _height_cm, _dob_str)
            if _uid:
                st.session_state.pop("_force_settings", None)
                st.success("Profile saved.")
                st.rerun()
            else:
                st.error("Save failed — check storage.")

    st.divider()
    st.subheader("Training Plan")

    _plan     = get_plan()
    _all_wkts = list_workouts()
    _wkt_map  = {w[0]: w[1] for w in _all_wkts}
    _wkt_names = ["(Rest)"] + [w[1] for w in _all_wkts]
    _wkt_ids   = [None]     + [w[0] for w in _all_wkts]
    _DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for _day in range(7):
        _wid_today, _notes = _plan.get(_day, (None, ""))
        _current_name = _wkt_map.get(_wid_today, "(Rest)") if _wid_today else "(Rest)"
        _dc1, _dc2, _dc3 = st.columns([1, 3, 1])
        _dc1.markdown(f"**{_DAY_NAMES[_day]}**")
        _sel = _dc2.selectbox(
            f"plan_{_day}", _wkt_names,
            index=(_wkt_ids.index(_wid_today) if _wid_today in _wkt_ids else 0),
            label_visibility="collapsed", key=f"plan_sel_{_day}",
        )
        if _dc3.button("Set", key=f"plan_set_{_day}", use_container_width=True):
            _sel_idx = _wkt_names.index(_sel)
            if _sel == "(Rest)":
                clear_day(_day)
            else:
                set_day(_day, _wkt_ids[_sel_idx])
            st.rerun()
