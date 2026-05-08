import calendar as _calendar

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle

from ui.theme import CARD_BG, LABEL_COLOR, VALUE_COLOR, BTN_NEUTRAL

_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
           "Jul","Aug","Sep","Oct","Nov","Dec"]

_BTN_H  = 52   # up/down button height px
_VAL_H  = 44   # value label height px
DIAL_H  = _BTN_H * 2 + _VAL_H   # 148px total


class SpinDial(BoxLayout):
    """
    Up/down arrow spinner — fixed 52px buttons, no swipe gestures.
    height should be set to DIAL_H (148) by the caller.
    """

    def __init__(self, values, initial=0, fmt=str, wrap=False, on_change=None, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", DIAL_H)
        super().__init__(orientation="vertical", spacing=0, **kwargs)

        self._values    = list(values)
        self._idx       = max(0, min(initial, len(self._values) - 1))
        self._fmt       = fmt
        self._wrap      = wrap
        self._on_change = on_change

        with self.canvas.before:
            Color(*CARD_BG)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

        self._up = Button(
            text="▲",
            font_size="30sp",
            bold=True,
            size_hint_y=None,
            height=_BTN_H,
            background_normal="",
            background_color=BTN_NEUTRAL,
            on_press=lambda _: self._step(1),
        )
        self._val_lbl = Label(
            text=self._fmt(self._values[self._idx]),
            font_size="34sp",
            bold=True,
            color=VALUE_COLOR,
            size_hint_y=None,
            height=_VAL_H,
            halign="center",
            valign="middle",
        )
        self._val_lbl.bind(size=self._val_lbl.setter("text_size"))
        self._dn = Button(
            text="▼",
            font_size="30sp",
            bold=True,
            size_hint_y=None,
            height=_BTN_H,
            background_normal="",
            background_color=BTN_NEUTRAL,
            on_press=lambda _: self._step(-1),
        )

        self.add_widget(self._up)
        self.add_widget(self._val_lbl)
        self.add_widget(self._dn)

    @property
    def value(self):
        return self._values[self._idx]

    def set_index(self, idx):
        self._idx = max(0, min(idx, len(self._values) - 1))
        self._val_lbl.text = self._fmt(self._values[self._idx])

    def set_max(self, n):
        """Trim values to first n entries; clamp index if needed."""
        self._values = self._values[:n]
        self._idx = min(self._idx, n - 1)
        self._val_lbl.text = self._fmt(self._values[self._idx])

    def _step(self, direction):
        new_idx = self._idx + direction
        if self._wrap:
            self._idx = new_idx % len(self._values)
        else:
            self._idx = max(0, min(new_idx, len(self._values) - 1))
        self._val_lbl.text = self._fmt(self._values[self._idx])
        if self._on_change:
            self._on_change(self.value)

    def _upd(self, *_):
        self._rect.pos  = self.pos
        self._rect.size = self.size
