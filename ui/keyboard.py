import time

from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout

_DEBOUNCE_SECS = 0.35

_ALPHA = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    ["⇧"] + list("ZXCVBNM") + ["⌫"],
    ["123", " ", "Done"],
]

_NUMS = [
    list("1234567890"),
    list("-/:;()$&@."),
    list(",?!'\"+=%_"),
    ["ABC", " ", "Done"],
]

_KEY_H = 80
_SPACING = 5


class BigKeyboard(BoxLayout):
    def __init__(self, on_key, **kwargs):
        super().__init__(orientation="vertical", spacing=_SPACING, **kwargs)
        self._on_key = on_key
        self._caps = False
        self._layout = "alpha"
        self._last_press = 0.0
        self._render()

    def _render(self):
        self.clear_widgets()
        rows = _ALPHA if self._layout == "alpha" else _NUMS
        for row in rows:
            self.add_widget(self._make_row(row))
        total_rows = len(rows)
        self.height = total_rows * (_KEY_H + _SPACING) + _SPACING
        self.size_hint_y = None

    def _make_row(self, keys):
        row = BoxLayout(
            size_hint_y=None,
            height=_KEY_H,
            spacing=_SPACING,
        )
        for k in keys:
            wide = k in ("123", "ABC", "Done", " ", "⌫", "⇧")
            btn = Button(
                text=k,
                font_size="24sp",
                size_hint_x=2 if k == " " else (1.4 if wide else 1),
                on_press=lambda b, key=k: self._handle(key),
            )
            row.add_widget(btn)
        return row

    def _handle(self, key):
        now = time.monotonic()
        if now - self._last_press < _DEBOUNCE_SECS:
            return
        self._last_press = now

        if key == "⌫":
            self._on_key("\b")
        elif key == "Done":
            self._on_key("\n")
        elif key == " ":
            self._on_key(" ")
        elif key == "⇧":
            self._caps = not self._caps
        elif key == "123":
            self._layout = "nums"
            self._render()
        elif key == "ABC":
            self._layout = "alpha"
            self._render()
        else:
            ch = key.upper() if self._caps else key.lower()
            self._on_key(ch)
