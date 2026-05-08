"""
Side-by-side session comparison popup.
"""
import sqlite3
from datetime import datetime

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle

from ui.theme import BG, CARD_BG, LABEL_COLOR, VALUE_COLOR, HR_COLOR, BTN_NEUTRAL, BTN_START, BTN_END

_DB_PATH = "rowing.db"

_A_COLOR = (0.25, 0.60, 0.95, 1)   # blue
_B_COLOR = (0.95, 0.55, 0.15, 1)   # orange


def _bg(w):
    with w.canvas.before:
        Color(*BG)
        r = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda *a: setattr(r, "pos", w.pos),
           size=lambda *a: setattr(r, "size", w.size))


def _card_bg(w):
    with w.canvas.before:
        Color(*CARD_BG)
        r = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda *a: setattr(r, "pos", w.pos),
           size=lambda *a: setattr(r, "size", w.size))


def _pace_str(sec):
    if not sec:
        return "--:--"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def _time_str(secs):
    if not secs:
        return "--"
    h, rem = divmod(int(secs), 3600)
    m, s   = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _load_recent(n=20):
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            return conn.execute(
                "SELECT id, started_at, total_distance, total_time, avg_pace "
                "FROM sessions WHERE status='complete' AND total_distance > 0 "
                "ORDER BY started_at DESC LIMIT ?", (n,)
            ).fetchall()
    except Exception:
        return []


def _load_session(sid):
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            row = conn.execute(
                "SELECT total_distance, total_time, avg_pace, avg_watts, avg_spm, avg_hr "
                "FROM sessions WHERE id=?", (sid,)
            ).fetchone()
            pts = conn.execute(
                "SELECT elapsed_secs, speed_mm_s FROM stroke_log "
                "WHERE session_id=? AND speed_mm_s > 0 ORDER BY elapsed_secs", (sid,)
            ).fetchall()
        return row, pts
    except Exception:
        return None, []


class _DualGraph(Widget):
    """Overlaid pace graph for two sessions."""

    def __init__(self, pts_a, pts_b, **kwargs):
        super().__init__(**kwargs)
        self._pts_a = pts_a
        self._pts_b = pts_b
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.clear()
        w, h   = self.size
        x0, y0 = self.pos
        pad    = 10
        all_pts = self._pts_a + self._pts_b
        all_x = [p[0] for p in all_pts]
        all_y = [p[1] for p in all_pts if p[1] > 0]
        if not all_x or not all_y:
            return
        xspan = (max(all_x) - min(all_x)) or 1
        yspan = (max(all_y) * 1.1 - min(all_y) * 0.9) or 1
        xmin  = min(all_x)
        ymin  = min(all_y) * 0.9

        def _px(x, y):
            return (x0 + pad + (x - xmin) / xspan * (w - 2 * pad),
                    y0 + pad + (y - ymin) / yspan * (h - 2 * pad))

        with self.canvas:
            Color(*CARD_BG)
            Rectangle(pos=self.pos, size=self.size)
            for color, pts in ((_A_COLOR, self._pts_a), (_B_COLOR, self._pts_b)):
                coords = []
                for x, y in pts:
                    if y > 0:
                        px, py = _px(x, y)
                        coords += [px, py]
                if len(coords) >= 4:
                    Color(*color)
                    Line(points=coords, width=2)


def _stat_cell(label, val_a, val_b):
    box = BoxLayout(orientation="vertical", padding=(4, 4), spacing=2)
    _card_bg(box)
    lbl = Label(text=label.upper(), font_size="12sp", color=LABEL_COLOR,
                halign="center", size_hint_y=0.3)
    lbl.bind(size=lbl.setter("text_size"))
    row = BoxLayout(size_hint_y=0.7, spacing=4)
    va = Label(text=str(val_a), font_size="22sp", bold=True, color=_A_COLOR, halign="center")
    va.bind(size=va.setter("text_size"))
    vb = Label(text=str(val_b), font_size="22sp", bold=True, color=_B_COLOR, halign="center")
    vb.bind(size=vb.setter("text_size"))
    row.add_widget(va)
    row.add_widget(vb)
    box.add_widget(lbl)
    box.add_widget(row)
    return box


def _build_comparison_view(root, sid_a, sid_b, popup):
    root.clear_widgets()
    _bg(root)

    inner = BoxLayout(orientation="vertical", padding=8, spacing=6, size_hint_y=None)
    inner.bind(minimum_height=inner.setter("height"))
    _bg(inner)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(inner)

    row_a, pts_a = _load_session(sid_a)
    row_b, pts_b = _load_session(sid_b)

    # Legend
    legend = BoxLayout(size_hint_y=None, height=28, spacing=8, padding=(8, 0))
    legend.add_widget(Label(text="■  A", font_size="15sp", color=_A_COLOR, halign="left", size_hint_x=0.5))
    legend.add_widget(Label(text="■  B", font_size="15sp", color=_B_COLOR, halign="left", size_hint_x=0.5))
    inner.add_widget(legend)

    if row_a and row_b:
        da, ta, pa, wa, sa, ha = row_a
        db, tb, pb, wb, sb, hb = row_b

        grid = GridLayout(cols=3, rows=2, spacing=4, size_hint_y=None, height=200)
        grid.add_widget(_stat_cell("Distance",
                                   f"{da:.0f}m" if da else "--",
                                   f"{db:.0f}m" if db else "--"))
        grid.add_widget(_stat_cell("Time",
                                   _time_str(ta), _time_str(tb)))
        grid.add_widget(_stat_cell("Avg Pace",
                                   _pace_str(pa), _pace_str(pb)))
        grid.add_widget(_stat_cell("Avg Watts",
                                   f"{wa:.0f}W" if wa else "--",
                                   f"{wb:.0f}W" if wb else "--"))
        grid.add_widget(_stat_cell("Avg SPM",
                                   f"{sa:.0f}" if sa else "--",
                                   f"{sb:.0f}" if sb else "--"))
        grid.add_widget(_stat_cell("Avg HR",
                                   f"{ha:.0f}" if ha else "--",
                                   f"{hb:.0f}" if hb else "--"))
        inner.add_widget(grid)

    if pts_a or pts_b:
        inner.add_widget(Label(text="PACE OVER TIME", font_size="13sp", color=LABEL_COLOR,
                               size_hint_y=None, height=22, halign="left"))
        inner.add_widget(_DualGraph(pts_a, pts_b, size_hint_y=None, height=150))

    root.add_widget(scroll)
    close_btn = Button(text="Close", font_size="20sp", size_hint_y=None, height=70,
                       background_normal="", background_color=BTN_NEUTRAL)
    close_btn.bind(on_press=lambda _: popup.dismiss())
    root.add_widget(close_btn)


# ── Public entry point ──────────────────────────────────────────────────────

def build_comparison_popup():
    """
    Two-phase popup: first tap session A, then tap session B → shows comparison.
    """
    sessions = _load_recent()

    root = BoxLayout(orientation="vertical", padding=8, spacing=6)
    _bg(root)

    popup = Popup(title="Compare Sessions", content=root,
                  size_hint=(1, 1), auto_dismiss=False)

    selected = {"a": None, "b": None}
    sel_labels = {}

    if not sessions:
        root.add_widget(Label(text="No completed sessions yet.",
                              color=LABEL_COLOR, font_size="20sp"))
    else:
        hint = Label(
            text="Tap A session, then B session to compare.",
            font_size="16sp", color=LABEL_COLOR, size_hint_y=None, height=34, halign="center"
        )
        hint.bind(size=hint.setter("text_size"))
        root.add_widget(hint)

        inner = BoxLayout(orientation="vertical", padding=4, spacing=4, size_hint_y=None)
        inner.bind(minimum_height=inner.setter("height"))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(inner)

        for sid, started_at, dist, elapsed, avg_pace in sessions:
            ts  = datetime.fromtimestamp(started_at).strftime("%m/%d %H:%M") if started_at else "?"
            txt = f"{ts}  {dist:.0f}m  {_time_str(elapsed)}  {_pace_str(avg_pace)}/500"

            row = BoxLayout(size_hint_y=None, height=56, spacing=6)
            _card_bg(row)

            badge = Label(text="", font_size="20sp", bold=True,
                          color=_A_COLOR, size_hint_x=0.12, halign="center")
            badge.bind(size=badge.setter("text_size"))
            desc  = Label(text=txt, font_size="14sp", color=VALUE_COLOR,
                          halign="left", size_hint_x=0.88)
            desc.bind(size=desc.setter("text_size"))
            sel_labels[sid] = badge
            row.add_widget(badge)
            row.add_widget(desc)

            tap_btn = Button(background_normal="", background_color=(0, 0, 0, 0),
                             pos=row.pos, size=row.size)

            def _tap(_, s=sid):
                if selected["a"] is None:
                    selected["a"] = s
                    sel_labels[s].text = "A"
                    sel_labels[s].color = _A_COLOR
                elif selected["b"] is None and s != selected["a"]:
                    selected["b"] = s
                    sel_labels[s].text = "B"
                    sel_labels[s].color = _B_COLOR
                    _build_comparison_view(root, selected["a"], selected["b"], popup)

            # Use the whole row as the tap target via a transparent overlay Button approach;
            # simpler: just bind on_touch_down on the row itself
            row.bind(on_touch_down=lambda inst, touch, fn=_tap, r=row:
                     fn(None) if r.collide_point(*touch.pos) else None)
            inner.add_widget(row)

        root.add_widget(scroll)

    close_btn = Button(text="Close", font_size="20sp", size_hint_y=None, height=70,
                       background_normal="", background_color=BTN_NEUTRAL)
    close_btn.bind(on_press=lambda _: popup.dismiss())
    root.add_widget(close_btn)

    return popup
