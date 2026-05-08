from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout

_ROWS = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
]

_HEIGHT = 72   # px per key row
_SPACING = 6


class BigKeyboard(BoxLayout):
    """Large-key on-screen keyboard. Calls on_key(char) for each tap."""

    def __init__(self, on_key=None, **kwargs):
        super().__init__(orientation="vertical", spacing=_SPACING, **kwargs)
        self._on_key = on_key
        self.size_hint_y = None
        self.height = (_HEIGHT + _SPACING) * 4 + _SPACING + _HEIGHT  # 4 rows + special row

        for row in _ROWS:
            self.add_widget(self._make_row(row))
        self.add_widget(self._make_special_row())

    def _make_row(self, keys):
        row = GridLayout(
            cols=len(keys),
            size_hint_y=None,
            height=_HEIGHT,
            spacing=_SPACING,
        )
        for ch in keys:
            btn = Button(
                text=ch,
                font_size="22sp",
                on_press=lambda b, c=ch: self._emit(c),
            )
            row.add_widget(btn)
        return row

    def _make_special_row(self):
        row = BoxLayout(size_hint_y=None, height=_HEIGHT, spacing=_SPACING)

        row.add_widget(Button(
            text="123",
            font_size="18sp",
            size_hint_x=0.2,
            on_press=lambda _: self._toggle_nums(),
        ))
        row.add_widget(Button(
            text="space",
            font_size="18sp",
            on_press=lambda _: self._emit(" "),
        ))
        row.add_widget(Button(
            text="⌫",
            font_size="22sp",
            size_hint_x=0.2,
            on_press=lambda _: self._emit("\b"),
        ))
        row.add_widget(Button(
            text="Done",
            font_size="18sp",
            size_hint_x=0.22,
            on_press=lambda _: self._emit("\n"),
        ))
        return row

    def _emit(self, char):
        if self._on_key:
            self._on_key(char)

    def _toggle_nums(self):
        self.clear_widgets()
        num_rows = [
            list("1234567890"),
            list("-/:;()$&@\""),
            list(".,?!'"),
        ]
        for row in num_rows:
            self.add_widget(self._make_row(row))
        self.add_widget(self._make_special_row_abc())

    def _make_special_row_abc(self):
        row = BoxLayout(size_hint_y=None, height=_HEIGHT, spacing=_SPACING)
        row.add_widget(Button(
            text="ABC",
            font_size="18sp",
            size_hint_x=0.2,
            on_press=lambda _: self._reset_alpha(),
        ))
        row.add_widget(Button(
            text="space",
            font_size="18sp",
            on_press=lambda _: self._emit(" "),
        ))
        row.add_widget(Button(
            text="⌫",
            font_size="22sp",
            size_hint_x=0.2,
            on_press=lambda _: self._emit("\b"),
        ))
        row.add_widget(Button(
            text="Done",
            font_size="18sp",
            size_hint_x=0.22,
            on_press=lambda _: self._emit("\n"),
        ))
        return row

    def _reset_alpha(self):
        self.clear_widgets()
        for row in _ROWS:
            self.add_widget(self._make_row(row))
        self.add_widget(self._make_special_row())
