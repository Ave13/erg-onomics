from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle

from ui.theme import CARD_BG, LABEL_COLOR, VALUE_COLOR, FONT_LABEL, FONT_VALUE
from ui.theme import BTN_NEUTRAL, BTN_DISABLED, FONT_BTN


class MetricCard(BoxLayout):
    """Label + large value display with dark card background."""

    def __init__(self, title, **kwargs):
        super().__init__(orientation="vertical", padding=(12, 10), spacing=2, **kwargs)
        with self.canvas.before:
            Color(*CARD_BG)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

        self._lbl = Label(
            text=title.upper(),
            color=LABEL_COLOR,
            font_size=FONT_LABEL,
            size_hint_y=0.3,
            halign="center",
            valign="bottom",
        )
        self._lbl.bind(size=self._lbl.setter("text_size"))

        self._val = Label(
            text="--",
            color=VALUE_COLOR,
            font_size=FONT_VALUE,
            bold=True,
            size_hint_y=0.7,
            halign="center",
            valign="middle",
        )
        self._val.bind(size=self._val.setter("text_size"))

        self.add_widget(self._lbl)
        self.add_widget(self._val)

    def set_value(self, text, color=None):
        self._val.text = str(text)
        if color:
            self._val.color = color

    def _update_rect(self, *_):
        self._rect.pos  = self.pos
        self._rect.size = self.size


class ActionButton(Button):
    """Flat coloured button with no default Kivy chrome."""

    def __init__(self, label, color, **kwargs):
        self._active_color   = color
        self._disabled_color = BTN_DISABLED
        super().__init__(
            text=label,
            font_size=FONT_BTN,
            bold=True,
            background_normal="",
            background_color=color,
            **kwargs,
        )

    def on_disabled(self, _instance, disabled):
        self.background_color = self._disabled_color if disabled else self._active_color
