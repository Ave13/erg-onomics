import sqlite3
from datetime import datetime, timezone

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle

from db.strive import calculate_strive_score, ZONE_COLORS, ZONE_NAMES, estimate_max_hr
from db.streak import get_streak
from ui.theme import BG, CARD_BG, LABEL_COLOR, VALUE_COLOR, HR_COLOR, BTN_NEUTRAL

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


class _LineGraph(Widget):
    """Generic multi-series line graph."""

    def __init__(self, series, **kwargs):
        # series: list of (label, color, [(x,y), ...])
        super().__init__(**kwargs)
        self._series = series
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.clear()
        if not self._series:
            return
        w, h   = self.size
        x0, y0 = self.pos
        pad    = 10

        all_x = [p[0] for _, _, pts in self._series for p in pts]
        all_y = [p[1] for _, _, pts in self._series for p in pts if p[1] > 0]
        if not all_x or not all_y:
            return

        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y) * 0.9, max(all_y) * 1.1
        x_span = x_max - x_min or 1
        y_span = y_max - y_min or 1

        def _px(x, y):
            return (x0 + pad + (x - x_min) / x_span * (w - 2 * pad),
                    y0 + pad + (y - y_min) / y_span * (h - 2 * pad))

        with self.canvas:
            Color(*CARD_BG)
            Rectangle(pos=self.pos, size=self.size)
            for _lbl, color, pts in self._series:
                Color(*color)
                coords = []
                for x, y in pts:
                    if y > 0:
                        px, py = _px(x, y)
                        coords += [px, py]
                if len(coords) >= 4:
                    Line(points=coords, width=2)


class _ZoneBars(Widget):
    """Horizontal stacked zone-time bar."""

    def __init__(self, zone_times, **kwargs):
        super().__init__(**kwargs)
        self._zone_times = zone_times
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.clear()
        total = sum(self._zone_times) or 1
        w, h  = self.size
        x0, y0 = self.pos
        pad   = 4
        bar_h = max(h - pad * 2, 20)
        x     = x0 + pad

        with self.canvas:
            Color(*CARD_BG)
            Rectangle(pos=self.pos, size=self.size)
            for i, (t, color) in enumerate(zip(self._zone_times, ZONE_COLORS)):
                seg_w = (t / total) * (w - pad * 2)
                if seg_w < 1:
                    continue
                Color(*color)
                Rectangle(pos=(x, y0 + pad), size=(seg_w, bar_h))
                x += seg_w


def _load_session(session_id):
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            sess = conn.execute(
                "SELECT started_at, ended_at, total_distance, total_time, "
                "       avg_pace, avg_watts, avg_spm, max_watts, calories, "
                "       avg_hr, max_hr, user_id, drag_factor, workout_id "
                "FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            speed_rows = conn.execute(
                "SELECT elapsed_secs, speed_mm_s FROM stroke_log "
                "WHERE session_id=? ORDER BY elapsed_secs", (session_id,)
            ).fetchall()
            force_rows = conn.execute(
                "SELECT elapsed_secs, avg_force_n, peak_force_n FROM stroke_log "
                "WHERE session_id=? AND avg_force_n IS NOT NULL "
                "ORDER BY elapsed_secs", (session_id,)
            ).fetchall()
            dob_row = conn.execute(
                "SELECT dob FROM user_profile WHERE id=("
                "SELECT user_id FROM sessions WHERE id=?)", (session_id,)
            ).fetchone()
        return sess, speed_rows, force_rows, (dob_row[0] if dob_row else None)
    except Exception:
        return None, [], [], None


def build_summary_popup(session_id, prs=None, on_close=None):
    sess, speed_rows, force_rows, dob = _load_session(session_id)

    # Scrollable content so everything fits on 768px
    inner = BoxLayout(orientation="vertical", padding=8, spacing=6,
                      size_hint_y=None)
    inner.bind(minimum_height=inner.setter("height"))

    with inner.canvas.before:
        Color(*BG)
        _bg = Rectangle(pos=inner.pos, size=inner.size)
    inner.bind(pos=lambda *a: setattr(_bg, "pos", inner.pos),
               size=lambda *a: setattr(_bg, "size", inner.size))

    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(inner)

    root = BoxLayout(orientation="vertical", padding=0, spacing=0)
    with root.canvas.before:
        Color(*BG)
        _rbg = Rectangle(pos=root.pos, size=root.size)
    root.bind(pos=lambda *a: setattr(_rbg, "pos", root.pos),
              size=lambda *a: setattr(_rbg, "size", root.size))

    if not sess:
        inner.add_widget(Label(text="No session data.", color=LABEL_COLOR,
                               size_hint_y=None, height=60))
    else:
        (started_at, ended_at, dist, elapsed, avg_pace,
         avg_watts, avg_spm, max_watts, calories, avg_hr, max_hr,
         user_id, drag_factor, workout_id) = sess

        # ── stats grid ────────────────────────────────────────────
        grid = GridLayout(cols=3, rows=2, spacing=4,
                          size_hint_y=None, height=200)
        grid.add_widget(_stat_cell("Distance",  f"{dist:.0f} m"      if dist      else "--"))
        grid.add_widget(_stat_cell("Time",      _time_str(elapsed)))
        grid.add_widget(_stat_cell("Avg Pace",  _pace_str(avg_pace)))
        grid.add_widget(_stat_cell("Avg Watts", f"{avg_watts:.0f} W" if avg_watts else "--"))
        grid.add_widget(_stat_cell("Avg SPM",   f"{avg_spm:.0f}"     if avg_spm   else "--"))
        hr_col = HR_COLOR if avg_hr else None
        grid.add_widget(_stat_cell("Avg HR",    f"{avg_hr:.0f}"      if avg_hr    else "--",
                                   value_color=hr_col))
        inner.add_widget(grid)

        # ── workout name + drag factor ────────────────────────────
        meta_parts = []
        if workout_id:
            try:
                from db.workouts import get_workout
                w = get_workout(workout_id)
                if w:
                    meta_parts.append(w[1])
            except Exception:
                pass
        if drag_factor:
            meta_parts.append(f"Drag {drag_factor}")
        if meta_parts:
            inner.add_widget(Label(
                text="  ".join(meta_parts),
                font_size="15sp", color=LABEL_COLOR,
                size_hint_y=None, height=24, halign="left",
            ))

        # ── pace graph ────────────────────────────────────────────
        if speed_rows:
            inner.add_widget(Label(text="PACE", font_size="14sp", color=LABEL_COLOR,
                                   size_hint_y=None, height=22, halign="left"))
            pace_series = [("Pace", (0.2, 0.75, 0.55, 1),
                            [(r[0], r[1]) for r in speed_rows if r[1] > 0])]
            inner.add_widget(_LineGraph(pace_series, size_hint_y=None, height=130))

        # ── force curve trend ─────────────────────────────────────
        if force_rows:
            inner.add_widget(Label(text="FORCE", font_size="14sp", color=LABEL_COLOR,
                                   size_hint_y=None, height=22, halign="left"))
            force_series = [
                ("Avg",  (0.25, 0.55, 0.95, 1), [(r[0], r[1]) for r in force_rows]),
                ("Peak", (0.95, 0.45, 0.15, 1), [(r[0], r[2]) for r in force_rows]),
            ]
            inner.add_widget(_LineGraph(force_series, size_hint_y=None, height=120))

        # ── strive score ──────────────────────────────────────────
        max_hr_est = estimate_max_hr(dob) if dob else (max_hr or 185)
        score, zone_times = calculate_strive_score(session_id, max_hr_est)
        if score > 0:
            inner.add_widget(Label(text="STRIVE SCORE", font_size="14sp",
                                   color=LABEL_COLOR, size_hint_y=None, height=22,
                                   halign="left"))
            score_row = BoxLayout(size_hint_y=None, height=44, spacing=8)
            score_row.add_widget(Label(
                text=f"{score:.0f}",
                font_size="32sp", bold=True, color=(0.95, 0.82, 0.12, 1),
                size_hint_x=0.2, halign="center",
            ))
            score_row.add_widget(_ZoneBars(zone_times, size_hint_x=0.8))
            inner.add_widget(score_row)

            zone_row = BoxLayout(size_hint_y=None, height=22, spacing=4)
            for name, t, color in zip(ZONE_NAMES, zone_times, ZONE_COLORS):
                m, s = divmod(t, 60)
                lbl = Label(text=f"{name} {m}:{s:02d}",
                            font_size="13sp", color=color, halign="center")
                zone_row.add_widget(lbl)
            inner.add_widget(zone_row)

        # ── streak ────────────────────────────────────────────────
        if user_id:
            cur_streak, longest = get_streak(user_id)
            if cur_streak > 0:
                streak_txt = (f"  {cur_streak} day streak"
                              + (f"  ·  longest {longest}" if longest > cur_streak else ""))
                inner.add_widget(Label(
                    text=streak_txt,
                    font_size="18sp",
                    color=(0.95, 0.82, 0.12, 1),
                    size_hint_y=None, height=32,
                    halign="left",
                ))

        # ── PRs ───────────────────────────────────────────────────
        if prs:
            for rtype, old, new in prs:
                if rtype.startswith("pace_"):
                    dist_label = rtype.replace("pace_", "").replace("m", "") + "m"
                    txt = f"  ★  {dist_label} pace  {_pace_str(new)}/500m"
                else:
                    txt = f"  ★  {_PR_NAMES.get(rtype, rtype)}  {new:.0f}"
                inner.add_widget(Label(
                    text=txt, font_size="18sp",
                    color=(1.0, 0.82, 0.12, 1),
                    halign="left", size_hint_y=None, height=28,
                ))

    btn_row = BoxLayout(size_hint_y=None, height=70, spacing=6)

    compare_btn = Button(
        text="Compare", font_size="20sp",
        size_hint_x=0.4,
        background_normal="", background_color=BTN_NEUTRAL,
    )
    close_btn = Button(
        text="Close", font_size="22sp",
        background_normal="", background_color=BTN_NEUTRAL,
    )

    def _on_compare(_):
        from ui.comparison import build_comparison_popup
        build_comparison_popup().open()

    compare_btn.bind(on_press=_on_compare)

    btn_row.add_widget(compare_btn)
    btn_row.add_widget(close_btn)

    root.add_widget(scroll)
    root.add_widget(btn_row)

    popup = Popup(title="Session Complete", content=root,
                  size_hint=(1, 1), auto_dismiss=False)

    close_btn.bind(on_press=lambda _: (popup.dismiss(),
                                        on_close() if on_close else None))
    return popup
