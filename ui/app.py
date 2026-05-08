import threading
from kivy.app import App
from kivy.uix.label import Label
from kivy.clock import Clock
from ble.pm5 import state, start_ble


class RowingApp(App):
    def build(self):
        self.label = Label(
            text="Connecting to PM5...",
            font_size="32sp",
            halign="center",
        )
        Clock.schedule_interval(self.update_ui, 0.5)
        threading.Thread(target=start_ble, daemon=True).start()
        return self.label

    def update_ui(self, dt):
        self.label.text = (
            f"Pace:     {state['pace']}\n"
            f"SPM:      {state['spm']}\n"
            f"Interval: {state['interval']}\n"
            f"Watts:    {state['watts']}\n"
            f"Dist:     {state['distance']:.0f} m\n"
            f"Time:     {int(state['elapsed'])} s"
        )
