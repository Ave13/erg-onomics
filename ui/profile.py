from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup

from ble.pm5 import save_user_profile, state
from ui.keyboard import BigKeyboard


def _row(label_text, hint):
    row = BoxLayout(size_hint_y=None, height=56, spacing=8)
    row.add_widget(Label(
        text=label_text,
        size_hint_x=0.32,
        halign="right",
        valign="middle",
    ))
    ti = TextInput(
        hint_text=hint,
        multiline=False,
        size_hint_x=0.68,
        use_bubble=False,
        use_handles=False,
    )
    row.add_widget(ti)
    return row, ti


def build_profile_popup(on_save=None):
    existing = {
        "name":      state.get("user_name", ""),
        "weight_kg": state.get("user_weight_kg"),
        "height_cm": state.get("user_height_cm"),
    }

    content = BoxLayout(orientation="vertical", padding=14, spacing=8)

    name_row,   name_in   = _row("Name",       "Your name")
    weight_row, weight_in = _row("Weight (kg)", "e.g. 75")
    height_row, height_in = _row("Height (cm)", "e.g. 178")
    dob_row,    dob_in    = _row("Born",        "YYYY-MM-DD  (optional)")

    if existing["name"]:
        name_in.text = existing["name"]
    if existing["weight_kg"]:
        weight_in.text = str(existing["weight_kg"])
    if existing["height_cm"]:
        height_in.text = str(existing["height_cm"])

    for row in (name_row, weight_row, height_row, dob_row):
        content.add_widget(row)

    err = Label(
        text="",
        color=(1, 0.35, 0.35, 1),
        size_hint_y=None,
        height=28,
        halign="center",
    )
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

    save_btn = Button(text="Save", size_hint_y=None, height=56)
    save_btn.bind(on_press=_save)
    return popup
