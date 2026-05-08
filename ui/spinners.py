from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle

from ui.theme import CARD_BG, LABEL_COLOR, VALUE_COLOR, BTN_NEUTRAL

_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
           "Jul","Aug","Sep","Oct","Nov","Dec"]

_DAYS_IN_MONTH = [31,29,28,31,30,31,30,31,31,30,31,30,31]


class SpinDial(BoxLayout):
    """
    Up/down arrow spinner for a list of values.
    Large touch targets — no swipe gestures needed.
    """

    def __init__(self, values, initial=0, label="", on_change=None, **kwargs):
        super().__init__(orientation="vertical", spacing=2, **kwargs)
        self._values    = list(values)
        self._idx       = initial
        self._on_change = on_change

        with self.canvas.before:
            Color(*CARD_BG)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

        up_btn = Button(
            text="▲",
            font_size="28sp",
            bold=True,
            size_hint_y=0.28,
            background_normal="",
            background_color=BTN_NEUTRAL,
            on_press=lambda _: self._step(1),
        )
        self._val_lbl = Label(
            text=self._display(),
            font_size="40sp",
            bold=True,
            color=VALUE_COLOR,
            size_hint_y=0.44,
            halign="center",
            valign="middle",
        )
        self._val_lbl.bind(size=self._val_lbl.setter("text_size"))

        down_btn = Button(
            text="▼",
            font_size="28sp",
            bold=True,
            size_hint_y=0.28,
            background_normal="",
            background_color=BTN_NEUTRAL,
            on_press=lambda _: self._step(-1),
        )

        if label:
            lbl = Label(
                text=label.upper(),
                font_size="16sp",
                color=LABEL_COLOR,
                size_hint_y=None,
                height=24,
                halign="center",
            )
            lbl.bind(size=lbl.setter("text_size"))
            self.add_widget(lbl)

        self.add_widget(up_btn)
        self.add_widget(self._val_lbl)
        self.add_widget(down_btn)

    @property
    def value(self):
        return self._values[self._idx]

    @property
    def index(self):
        return self._idx

    def set_index(self, idx):
        self._idx = max(0, min(idx, len(self._values) - 1))
        self._val_lbl.text = self._display()

    def _step(self, direction):
        self._idx = (self._idx + direction) % len(self._values)
        self._val_lbl.text = self._display()
        if self._on_change:
            self._on_change(self.value)

    def _display(self):
        return str(self._values[self._idx])

    def _upd(self, *_):
        self._rect.pos  = self.pos
        self._rect.size = self.size
