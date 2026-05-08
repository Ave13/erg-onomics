from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
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
        readonly=True,
    )
    row.add_widget(ti)
    return row, ti


def build_profile_popup(on_save=None):
    """
    Build a profile entry Popup with a large custom keyboard.
    on_save() is called after a successful save.
    """
    existing = {
        "name":      state.get("user_name", ""),
        "weight_kg": state.get("user_weight_kg"),
        "height_cm": state.get("user_height_cm"),
    }

    content = BoxLayout(orientation="vertical", padding=10, spacing=6)

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

    fields = [name_in, weight_in, height_in, dob_in]
    _active = [name_in]  # currently focused field

    for row in (name_row, weight_row, height_row, dob_row):
        content.add_widget(row)

    err = Label(
        text="",
        color=(1, 0.35, 0.35, 1),
        size_hint_y=None,
        height=24,
        halign="center",
    )
    content.add_widget(err)

    def _on_key(char):
        ti = _active[0]
        if char == "\b":
            ti.text = ti.text[:-1]
        elif char == "\n":
            idx = fields.index(ti)
            if idx + 1 < len(fields):
                _active[0] = fields[idx + 1]
                _highlight()
        else:
            ti.text += char

    def _highlight():
        for f in fields:
            f.background_color = (1, 1, 1, 1)
        _active[0].background_color = (0.85, 0.95, 1, 1)

    def _focus(ti):
        _active[0] = ti
        _highlight()

    for f in fields:
        f.bind(on_touch_down=lambda widget, touch, f=f:
               _focus(f) if widget.collide_point(*touch.pos) else None)

    _highlight()

    keyboard = BigKeyboard(on_key=_on_key, size_hint_y=None)
    content.add_widget(keyboard)

    popup = Popup(
        title="Your Profile",
        content=content,
        size_hint=(1, 1),
        auto_dismiss=False,
    )

    def _save(_):
        name = name_in.text.strip()
        try:
            weight = float(weight_in.text.strip())
            height = float(height_in.text.strip())
        except ValueError:
            err.text = "Weight and height must be numbers."
            return
        if weight <= 0 or height <= 0:
            err.text = "Weight and height must be greater than zero."
            return

        dob = dob_in.text.strip() or None
        result = save_user_profile(name, weight, height, dob)
        if result is None:
            err.text = "Could not save — check storage."
            return
        popup.dismiss()
        if on_save:
            on_save()

    save_btn = Button(text="Save", size_hint_y=None, height=56)
    save_btn.bind(on_press=_save)
    content.add_widget(save_btn)

    return popup
