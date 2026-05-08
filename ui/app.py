import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from datetime import datetime

from ble.pm5 import (
    state, start_ble,
    start_session, stop_session, pause_session, resume_session,
    find_resumable_session, has_user_profile,
)
from ui.profile import build_profile_popup
from ui.widgets import MetricCard, ActionButton
from ui.theme import BG, LABEL_COLOR, VALUE_COLOR, HR_COLOR, BTN_START, BTN_PAUSE, BTN_END, BTN_NEUTRAL


_PR_NAMES = {
    "longest_distance": "Distance",
    "longest_time":     "Time",
    "best_avg_watts":   "Avg watts",
    "best_max_watts":   "Peak watts",
    "best_avg_spm":     "Avg SPM",
}


def _pr_label(record):
    rtype, old, new = record
    if rtype.startswith("pace_"):
        dist = rtype.replace("pace_", "").replace("m", "")
        mins, secs = divmod(int(new), 60)
        return f"{dist}m {mins}:{secs:02d}/500m"
    name = _PR_NAMES.get(rtype, rtype)
    return f"{name} {new:.0f}"


class RowingApp(App):
    def build(self):
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(*BG)
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)

        # ── metric grid ──────────────────────────────────────────
        grid = GridLayout(cols=3, rows=2, spacing=4, padding=4)

        self._pace  = MetricCard("Pace")
        self._watts = MetricCard("Watts")
        self._spm   = MetricCard("SPM")
        self._dist  = MetricCard("Dist")
        self._time  = MetricCard("Time")
        self._hr    = MetricCard("HR")

        for card in (self._pace, self._watts, self._spm,
                     self._dist, self._time, self._hr):
            grid.add_widget(card)

        # ── status bar ───────────────────────────────────────────
        self._status = Label(
            text="",
            font_size="18sp",
            color=LABEL_COLOR,
            size_hint_y=None,
            height=36,
            halign="center",
            valign="middle",
        )
        self._status.bind(size=self._status.setter("text_size"))

        # ── button row ───────────────────────────────────────────
        btn_row = BoxLayout(size_hint_y=None, height=90, spacing=4, padding=(4, 4))

        self.start_btn   = ActionButton("Start",   BTN_START)
        self.pause_btn   = ActionButton("Pause",   BTN_PAUSE,  disabled=True)
        self.end_btn     = ActionButton("End",     BTN_END,    disabled=True)
        self.profile_btn = ActionButton("Profile", BTN_NEUTRAL, size_hint_x=0.6)

        self.start_btn.bind(on_press=self._on_start)
        self.pause_btn.bind(on_press=self._on_pause)
        self.end_btn.bind(on_press=self._on_end)
        self.profile_btn.bind(on_press=self._on_profile)

        for b in (self.start_btn, self.pause_btn, self.end_btn, self.profile_btn):
            btn_row.add_widget(b)

        root.add_widget(grid)
        root.add_widget(self._status)
        root.add_widget(btn_row)

        Clock.schedule_interval(self.update_ui, 0.5)
        threading.Thread(target=start_ble, daemon=True).start()

        if not has_user_profile():
            Clock.schedule_once(lambda dt: self._show_profile_setup(), 0.3)
        else:
            resumable = find_resumable_session()
            if resumable:
                Clock.schedule_once(lambda dt: self._show_resume_prompt(resumable), 0.5)

        return root

    def _update_bg(self, instance, _value):
        self._bg_rect.pos  = instance.pos
        self._bg_rect.size = instance.size

    def update_ui(self, dt):
        self._pace.set_value(state["pace"])
        self._watts.set_value(state["watts"])
        self._spm.set_value(state["spm"])
        self._dist.set_value(f"{state['distance']:.0f} m")
        elapsed = int(state["elapsed"])
        self._time.set_value(f"{elapsed // 60}:{elapsed % 60:02d}")

        hr = state["hr_bpm"]
        self._hr.set_value(f"{hr}", color=HR_COLOR if isinstance(hr, int) else LABEL_COLOR)

        if state["session_paused"]:
            status_text = "⏸  Paused"
        elif state["session_active"]:
            status_text = "⬤  Recording"
        else:
            status_text = "Ready"

        name = state.get("user_name") or ""
        self._status.text = f"{name}   {status_text}" if name else status_text

    def _on_start(self, _):
        start_session()
        self.start_btn.disabled = True
        self.pause_btn.disabled = False
        self.end_btn.disabled   = False

    def _on_pause(self, _):
        if state["session_paused"]:
            resume_session()
            self.pause_btn.text = "Pause"
        else:
            pause_session()
            self.pause_btn.text = "Resume"

    def _on_end(self, _):
        tcx_path = stop_session()
        self.start_btn.disabled = False
        self.pause_btn.disabled = True
        self.pause_btn.text     = "Pause"
        self.end_btn.disabled   = True
        prs = state.get("session_prs", [])
        if prs:
            labels = [_pr_label(r) for r in prs]
            self._status.text = "PR: " + "  ·  ".join(labels)
        elif tcx_path:
            self._status.text = "Session saved"

    def _on_profile(self, _):
        build_profile_popup(on_save=self._on_profile_saved).open()

    def _show_profile_setup(self):
        build_profile_popup(on_save=self._on_profile_saved).open()

    def _on_profile_saved(self):
        resumable = find_resumable_session()
        if resumable:
            Clock.schedule_once(lambda dt: self._show_resume_prompt(resumable), 0.3)

    def _show_resume_prompt(self, row):
        session_id, started_at = row
        started_str = datetime.fromtimestamp(started_at).strftime("%H:%M") if started_at else "?"

        content = BoxLayout(orientation="vertical", padding=16, spacing=12)
        content.add_widget(Label(
            text=f"Incomplete session from {started_str}.\nResume or start new?",
            halign="center",
            font_size="22sp",
        ))
        btn_row = BoxLayout(size_hint_y=None, height=80, spacing=8)

        popup = Popup(title="Resume session?", content=content,
                      size_hint=(0.75, 0.38), auto_dismiss=False)

        def on_resume(_):
            start_session(resume_id=session_id)
            self.start_btn.disabled = True
            self.pause_btn.disabled = False
            self.end_btn.disabled   = False
            popup.dismiss()

        def on_new(_):
            import sqlite3
            try:
                with sqlite3.connect("rowing.db") as conn:
                    conn.execute(
                        "UPDATE sessions SET status='abandoned' WHERE id=?",
                        (session_id,)
                    )
            except Exception:
                pass
            start_session()
            self.start_btn.disabled = True
            self.pause_btn.disabled = False
            self.end_btn.disabled   = False
            popup.dismiss()

        btn_row.add_widget(ActionButton("Resume", BTN_START, on_press=on_resume))
        btn_row.add_widget(ActionButton("New",    BTN_NEUTRAL, on_press=on_new))
        content.add_widget(btn_row)
        popup.open()
