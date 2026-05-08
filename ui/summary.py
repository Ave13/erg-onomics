import sqlite3
from datetime import datetime, timezone

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle

from ui.theme import BG, CARD_BG, LABEL_COLOR, VALUE_COLOR, HR_COLOR, BTN_START, BTN_NEUTRAL

_DB_PATH = "rowing.db"

_PR_NAMES = {
    "longest_distance": "Best distance",
    "longest_time":     "Longest time",
    "best_avg_watts":   "Best avg watts",
    "best_max_watts":   "Best peak watts",
    "best_avg_spm":     "Best avg SPM",
}


def _pace_str(pace_sec):
    if not pace_sec:
        return "--:--"
    m, s = divmod(int(pace_sec), 60)
    return f"{m}:{s:02d}"


def _time_str(secs):
    if not secs:
        return "--"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _stat_cell(label, value, value_color=None):
    box = BoxLayout(orientation="vertical", padding=(8, 6), spacing=2)
    with box.canvas.before:
        Color(*CARD_BG)
        rect = Rectangle(pos=box.pos, size=box.size)
    box.bind(pos=lambda *a: setattr(rect, "pos", box.pos),
             size=lambda *a: setattr(rect, "size", box.size))

    lbl = Label(text=label.upper(), font_size="14sp", color=LABEL_COLOR,
                halign="center", valign="bottom", size_hint_y=0.38)
    lbl.bind(size=lbl.setter("text_size"))

    val = Label(text=str(value), font_size="30sp", bold=True,
                color=value_color or VALUE_COLOR,
                halign="center", valign="middle", size_hint_y=0.62)
    val.bind(size=val.setter("text_size"))

    box.add_widget(lbl)
    box.add_widget(val)
    return box


class _PaceGraph(Widget):
    """Simple line chart of pace (speed_mm_s) over elapsed time."""

    def __init__(self, rows, **kwargs):
        super().__init__(**kwargs)
        self._rows = rows
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.clear()
        rows = self._rows
        if not rows or len(rows) < 2:
            return

        w, h   = self.size
        x0, y0 = self.pos

        speeds  = [r[1] for r in rows if r[1] > 0]
        if not speeds:
            return
        t_min   = rows[0][0]
        t_max   = rows[-1][0]
        s_min   = min(speeds) * 0.95
        s_max   = max(speeds) * 1.05
        t_span  = t_max - t_min or 1
        s_span  = s_max - s_min or 1

        pad = 12

        def _px(elapsed, speed):
            nx = (elapsed - t_min) / t_span
            ny = (speed   - s_min) / s_span
            return x0 + pad + nx * (w - 2 * pad), y0 + pad + ny * (h - 2 * pad)

        with self.canvas:
            # background
            Color(*CARD_BG)
            Rectangle(pos=self.pos, size=self.size)

            # pace line
            Color(0.2, 0.75, 0.55, 1)
            pts = []
            for elapsed, speed in rows:
                if speed > 0:
                    px, py = _px(elapsed, speed)
                    pts += [px, py]
            if len(pts) >= 4:
                Line(points=pts, width=2)

            # axis labels
            Color(*LABEL_COLOR)


def _load_session(session_id):
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            sess = conn.execute(
                "SELECT started_at, ended_at, total_distance, total_time, "
                "       avg_pace, avg_watts, avg_spm, max_watts, calories, "
                "       avg_hr, max_hr "
                "FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            rows = conn.execute(
                "SELECT elapsed_secs, speed_mm_s FROM stroke_log "
                "WHERE session_id=? ORDER BY elapsed_secs", (session_id,)
            ).fetchall()
        return sess, rows
    except Exception:
        return None, []


def build_summary_popup(session_id, prs=None, on_close=None):
    sess, stroke_rows = _load_session(session_id)

    content = BoxLayout(orientation="vertical", padding=8, spacing=6)
    with content.canvas.before:
        Color(*BG)
        _bg = Rectangle(pos=content.pos, size=content.size)
    content.bind(pos=lambda *a: setattr(_bg, "pos", content.pos),
                 size=lambda *a: setattr(_bg, "size", content.size))

    if not sess:
        content.add_widget(Label(text="No session data.", color=LABEL_COLOR))
    else:
        (started_at, ended_at, dist, elapsed, avg_pace,
         avg_watts, avg_spm, max_watts, calories, avg_hr, max_hr) = sess

        start_str = (datetime.fromtimestamp(started_at).strftime("%H:%M")
                     if started_at else "--")

        # ── stats grid ────────────────────────────────────────────
        grid = GridLayout(cols=3, rows=2, spacing=4, size_hint_y=0.38)
        grid.add_widget(_stat_cell("Distance",  f"{dist:.0f} m"         if dist    else "--"))
        grid.add_widget(_stat_cell("Time",      _time_str(elapsed)))
        grid.add_widget(_stat_cell("Avg Pace",  _pace_str(avg_pace)))
        grid.add_widget(_stat_cell("Avg Watts", f"{avg_watts:.0f} W"    if avg_watts else "--"))
        grid.add_widget(_stat_cell("Avg SPM",   f"{avg_spm:.0f}"        if avg_spm   else "--"))
        hr_val = f"{avg_hr:.0f}" if avg_hr else "--"
        grid.add_widget(_stat_cell("Avg HR", hr_val, value_color=HR_COLOR if avg_hr else None))
        content.add_widget(grid)

        # ── pace graph ────────────────────────────────────────────
        graph = _PaceGraph(stroke_rows, size_hint_y=0.35)
        content.add_widget(graph)

        # ── PRs ───────────────────────────────────────────────────
        if prs:
            pr_box = BoxLayout(orientation="vertical", size_hint_y=None,
                               height=28 * len(prs) + 8, spacing=2)
            for rtype, old, new in prs:
                if rtype.startswith("pace_"):
                    dist_label = rtype.replace("pace_", "").replace("m", "") + "m"
                    txt = f"  ★  {dist_label} pace  {_pace_str(new)}/500m"
                else:
                    txt = f"  ★  {_PR_NAMES.get(rtype, rtype)}  {new:.0f}"
                pr_box.add_widget(Label(
                    text=txt,
                    font_size="18sp",
                    color=(1.0, 0.82, 0.12, 1),
                    halign="left",
                    size_hint_y=None,
                    height=28,
                ))
            content.add_widget(pr_box)

    popup = Popup(
        title="Session Complete",
        content=content,
        size_hint=(1, 1),
        auto_dismiss=False,
    )

    def _close(_):
        popup.dismiss()
        if on_close:
            on_close()

    close_btn = Button(
        text="Close",
        font_size="22sp",
        size_hint_y=None,
        height=70,
        background_normal="",
        background_color=BTN_NEUTRAL,
        on_press=_close,
    )
    content.add_widget(close_btn)
    return popup
