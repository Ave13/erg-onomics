import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.clock import Clock
from datetime import datetime

from ble.pm5 import (
    state, start_ble,
    start_session, stop_session, pause_session, resume_session,
    find_resumable_session, has_user_profile,
)
from ui.profile import build_profile_popup


class RowingApp(App):
    def build(self):
        layout = BoxLayout(orientation="vertical")

        self.label = Label(
            font_size="28sp",
            halign="center",
            valign="middle",
        )
        self.hr_label = Label(
            font_size="20sp",
            halign="center",
            size_hint_y=0.08,
        )

        btn_row = BoxLayout(size_hint_y=0.12, spacing=4, padding=4)
        self.start_btn   = Button(text="Start")
        self.pause_btn   = Button(text="Pause",   disabled=True)
        self.end_btn     = Button(text="End",     disabled=True)
        self.profile_btn = Button(text="Profile", size_hint_x=0.55)
        self.start_btn.bind(on_press=self._on_start)
        self.pause_btn.bind(on_press=self._on_pause)
        self.end_btn.bind(on_press=self._on_end)
        self.profile_btn.bind(on_press=self._on_profile)
        for b in (self.start_btn, self.pause_btn, self.end_btn, self.profile_btn):
            btn_row.add_widget(b)

        layout.add_widget(self.label)
        layout.add_widget(self.hr_label)
        layout.add_widget(btn_row)

        Clock.schedule_interval(self.update_ui, 0.5)
        threading.Thread(target=start_ble, daemon=True).start()

        # First-run: block until profile is set up
        if not has_user_profile():
            Clock.schedule_once(lambda dt: self._show_profile_setup(), 0.3)
        else:
            resumable = find_resumable_session()
            if resumable:
                Clock.schedule_once(lambda dt: self._show_resume_prompt(resumable), 0.5)

        return layout

    def update_ui(self, dt):
        self.label.text = (
            f"Pace:     {state['pace']}\n"
            f"SPM:      {state['spm']}\n"
            f"Interval: {state['interval']}\n"
            f"Watts:    {state['watts']}\n"
            f"Dist:     {state['distance']:.0f} m\n"
            f"Time:     {int(state['elapsed'])} s"
        )
        status = (
            "Paused" if state["session_paused"]
            else "Recording" if state["session_active"]
            else "No session"
        )
        hr   = state["hr_bpm"]
        name = state.get("user_name") or ""
        self.hr_label.text = f"{name}  HR: {hr} bpm   {status}"

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
        if tcx_path:
            self.hr_label.text = f"Saved: {tcx_path}"

    def _on_profile(self, _):
        popup = build_profile_popup(on_save=self._on_profile_saved)
        popup.open()

    def _show_profile_setup(self):
        popup = build_profile_popup(on_save=self._on_profile_saved)
        popup.open()

    def _on_profile_saved(self):
        name = state.get("user_name") or "Rower"
        w    = state.get("user_weight_kg")
        h    = state.get("user_height_cm")
        self.hr_label.text = f"{name}  {w}kg  {h}cm"
        resumable = find_resumable_session()
        if resumable:
            Clock.schedule_once(lambda dt: self._show_resume_prompt(resumable), 0.3)

    def _show_resume_prompt(self, row):
        session_id, started_at = row
        started_str = datetime.fromtimestamp(started_at).strftime("%H:%M") if started_at else "?"

        content = BoxLayout(orientation="vertical", padding=10, spacing=10)
        content.add_widget(Label(
            text=f"Incomplete session from {started_str}.\nResume or start new?",
            halign="center",
        ))
        btn_row = BoxLayout(size_hint_y=0.4, spacing=8)

        popup = Popup(title="Resume session?", content=content,
                      size_hint=(0.8, 0.4), auto_dismiss=False)

        def on_resume(_):
            start_session(resume_id=session_id)
            self.start_btn.disabled = True
            self.pause_btn.disabled = False
            self.end_btn.disabled   = False
            popup.dismiss()

        def on_new(_):
            # mark old session abandoned
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

        resume_btn = Button(text="Resume")
        new_btn    = Button(text="New")
        resume_btn.bind(on_press=on_resume)
        new_btn.bind(on_press=on_new)
        btn_row.add_widget(resume_btn)
        btn_row.add_widget(new_btn)
        content.add_widget(btn_row)
        popup.open()
