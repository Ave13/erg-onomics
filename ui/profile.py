from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle

from ble.pm5 import save_user_profile, state
from ui.keyboard import BigKeyboard
from ui.spinners import SpinDial, _MONTHS, _DAYS_IN_MONTH
from ui.theme import BG, CARD_BG, LABEL_COLOR, VALUE_COLOR, BTN_START, BTN_NEUTRAL, BTN_END


def _section_label(text):
    lbl = Label(
        text=text.upper(),
        font_size="16sp",
        color=LABEL_COLOR,
        size_hint_y=None,
        height=28,
        halign="left",
        valign="middle",
    )
    lbl.bind(size=lbl.setter("text_size"))
    return lbl


def _name_popup(current, on_done):
    """Sub-popup with BigKeyboard to enter the rower's name."""
    name_val = [current]
    content  = BoxLayout(orientation="vertical", padding=8, spacing=6)

    display = Button(
        text=current or "tap to enter",
        font_size="24sp",
        size_hint_y=None,
        height=64,
        background_normal="",
        background_color=CARD_BG,
    )
    content.add_widget(display)

    def _on_key(char):
        if char == "\b":
            name_val[0] = name_val[0][:-1]
        elif char == "\n":
            popup.dismiss()
            on_done(name_val[0])
            return
        else:
            name_val[0] += char
        display.text = name_val[0] or "tap to enter"

    content.add_widget(BigKeyboard(on_key=_on_key))

    done_btn = Button(
        text="Done",
        font_size="22sp",
        size_hint_y=None,
        height=64,
        background_normal="",
        background_color=BTN_START,
        on_press=lambda _: (popup.dismiss(), on_done(name_val[0])),
    )
    content.add_widget(done_btn)

    popup = Popup(
        title="Enter name",
        content=content,
        size_hint=(1, 1),
        auto_dismiss=False,
    )
    return popup


def build_profile_popup(on_save=None):
    # ── current values ────────────────────────────────────────────
    cur_name   = state.get("user_name") or ""
    cur_wt     = state.get("user_weight_kg") or 75.0
    cur_ht_cm  = state.get("user_height_cm") or 175.0

    cur_ft  = max(4, min(7, int(cur_ht_cm // 30.48)))
    cur_in  = max(0, min(11, round((cur_ht_cm - cur_ft * 30.48) / 2.54)))

    name_val = [cur_name]

    # ── root layout ───────────────────────────────────────────────
    content = BoxLayout(orientation="vertical", padding=10, spacing=8)
    with content.canvas.before:
        Color(*BG)
        _bg = Rectangle(pos=content.pos, size=content.size)
    content.bind(pos=lambda *a: setattr(_bg, 'pos', content.pos),
                 size=lambda *a: setattr(_bg, 'size', content.size))

    err = Label(text="", color=(1, 0.3, 0.3, 1), size_hint_y=None, height=24,
                halign="center")
    err.bind(size=err.setter("text_size"))

    # ── name row ─────────────────────────────────────────────────
    content.add_widget(_section_label("Name"))
    name_btn = Button(
        text=cur_name or "Tap to enter name",
        font_size="22sp",
        size_hint_y=None,
        height=64,
        background_normal="",
        background_color=CARD_BG,
    )
    def _open_name(_):
        _name_popup(
            current=name_val[0],
            on_done=lambda n: (name_btn.__setattr__('text', n or "Tap to enter name"),
                               name_val.__setitem__(0, n)),
        ).open()
    name_btn.bind(on_press=_open_name)
    content.add_widget(name_btn)

    # ── weight dial ───────────────────────────────────────────────
    content.add_widget(_section_label("Weight"))
    wt_row = BoxLayout(size_hint_y=None, height=180, spacing=8)
    wt_dial = SpinDial(
        values=list(range(30, 251)),
        initial=max(0, int(cur_wt) - 30),
        label="kg",
    )
    wt_row.add_widget(wt_dial)
    content.add_widget(wt_row)

    # ── height dials ──────────────────────────────────────────────
    content.add_widget(_section_label("Height"))
    ht_row = BoxLayout(size_hint_y=None, height=180, spacing=8)
    ft_dial = SpinDial(values=list(range(4, 8)),  initial=cur_ft - 4, label="ft")
    in_dial = SpinDial(values=list(range(0, 12)), initial=cur_in,     label="in")
    ht_row.add_widget(ft_dial)
    ht_row.add_widget(in_dial)
    content.add_widget(ht_row)

    # ── dob dials ─────────────────────────────────────────────────
    content.add_widget(_section_label("Date of birth"))
    dob_row = BoxLayout(size_hint_y=None, height=180, spacing=8)
    day_dial  = SpinDial(values=list(range(1, 32)),   initial=0,  label="day")
    mon_dial  = SpinDial(values=_MONTHS,              initial=0,  label="month")
    year_dial = SpinDial(values=list(range(1940, 2011)), initial=45, label="year")

    def _clamp_days(_=None):
        mon_idx  = mon_dial.index + 1
        max_days = _DAYS_IN_MONTH[mon_idx]
        if day_dial.index >= max_days:
            day_dial.set_index(max_days - 1)

    mon_dial._on_change = lambda _: _clamp_days()

    dob_row.add_widget(day_dial)
    dob_row.add_widget(mon_dial)
    dob_row.add_widget(year_dial)
    content.add_widget(dob_row)

    content.add_widget(err)

    # ── save ──────────────────────────────────────────────────────
    save_btn = Button(
        text="Save",
        font_size="24sp",
        size_hint_y=None,
        height=70,
        background_normal="",
        background_color=BTN_START,
    )
    content.add_widget(save_btn)

    popup = Popup(
        title="Your Profile",
        content=content,
        size_hint=(1, 1),
        auto_dismiss=False,
    )

    def _save(_):
        weight_kg = float(wt_dial.value)
        height_cm = round(ft_dial.value * 30.48 + in_dial.value * 2.54, 1)
        dob = f"{year_dial.value}-{mon_dial.index + 1:02d}-{day_dial.value:02d}"
        name = name_val[0].strip()

        if height_cm <= 0 or weight_kg <= 0:
            err.text = "Height and weight must be greater than zero."
            return

        result = save_user_profile(name, weight_kg, height_cm, dob)
        if result is None:
            err.text = "Could not save — check storage."
            return
        popup.dismiss()
        if on_save:
            on_save()

    save_btn.bind(on_press=_save)
    return popup
