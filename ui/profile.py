from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup

from ble.pm5 import save_user_profile, state
from ui.keyboard import BigKeyboard

_ACTIVE_COLOR   = (0.2, 0.6, 1, 1)
_INACTIVE_COLOR = (0.25, 0.25, 0.25, 1)


def build_profile_popup(on_save=None):
    values = ["", "", "", ""]
    v = state.get("user_name", "")
    if v: values[0] = str(v)
    v = state.get("user_weight_kg")
    if v: values[1] = str(v)
    v = state.get("user_height_cm")
    if v: values[2] = str(v)

    active = [0]

    content = BoxLayout(orientation="vertical", padding=8, spacing=6)

    # Field display: label | value-button pairs
    field_grid = GridLayout(cols=2, size_hint_y=None, height=200, spacing=4)
    labels = ["Name", "Weight (kg)", "Height (cm)", "Born"]
    field_btns = []
    for i, lbl_text in enumerate(labels):
        lbl = Label(text=lbl_text, size_hint_x=0.38, halign="right", valign="middle")
        lbl.bind(size=lbl.setter("text_size"))
        field_grid.add_widget(lbl)
        btn = Button(
            text=values[i] or "tap to enter",
            font_size="20sp",
            halign="left",
            background_color=_INACTIVE_COLOR,
        )
        btn.bind(on_press=lambda b, i=i: _select(i))
        field_btns.append(btn)
        field_grid.add_widget(btn)

    content.add_widget(field_grid)

    err = Label(text="", color=(1, 0.35, 0.35, 1), size_hint_y=None, height=24)
    content.add_widget(err)

    def _on_key(char):
        i = active[0]
        if char == "\b":
            values[i] = values[i][:-1]
        elif char == "\n":
            _select((i + 1) % len(labels))
            return
        else:
            values[i] += char
        field_btns[i].text = values[i] or "tap to enter"

    content.add_widget(BigKeyboard(on_key=_on_key))

    save_btn = Button(text="Save", size_hint_y=None, height=64, font_size="22sp")
    content.add_widget(save_btn)

    popup = Popup(
        title="Your Profile",
        content=content,
        size_hint=(1, 1),
        auto_dismiss=False,
    )

    def _select(i):
        active[0] = i
        for j, b in enumerate(field_btns):
            b.background_color = _ACTIVE_COLOR if j == i else _INACTIVE_COLOR

    _select(0)

    def _save(_):
        name = values[0].strip()
        try:
            weight = float(values[1].strip())
            height = float(values[2].strip())
        except ValueError:
            err.text = "Weight and height must be numbers."
            return
        if weight <= 0 or height <= 0:
            err.text = "Weight and height must be > 0."
            return
        dob = values[3].strip() or None
        result = save_user_profile(name, weight, height, dob)
        if result is None:
            err.text = "Could not save — check storage."
            return
        popup.dismiss()
        if on_save:
            on_save()

    save_btn.bind(on_press=_save)
    return popup
