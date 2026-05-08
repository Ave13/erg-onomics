import calendar

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle

from ble.pm5 import save_user_profile, state
from ui.keyboard import BigKeyboard
from ui.spinners import SpinDial, DIAL_H, _MONTHS
from ui.theme import BG, CARD_BG, LABEL_COLOR, BTN_START, BTN_NEUTRAL, BTN_END


def _section_label(text):
    lbl = Label(
        text=text.upper(),
        font_size="16sp",
        color=LABEL_COLOR,
        size_hint_y=None,
        height=26,
        halign="left",
        valign="middle",
    )
    lbl.bind(size=lbl.setter("text_size"))
    return lbl


def _name_popup(current, on_done):
    name_val = [current]
    content  = BoxLayout(orientation="vertical", padding=8, spacing=6)

    preview = Button(
        text=current or "Start typing…",
        font_size="26sp",
        size_hint_y=None,
        height=60,
        background_normal="",
        background_color=CARD_BG,
    )
    content.add_widget(preview)

    def _on_key(char):
        if char == "\b":
            name_val[0] = name_val[0][:-1]
        elif char == "\n":
            popup.dismiss()
            on_done(name_val[0])
            return
        else:
            if len(name_val[0]) < 40:
                name_val[0] += char
        preview.text = name_val[0] or "Start typing…"

    content.add_widget(BigKeyboard(on_key=_on_key))

    row = BoxLayout(size_hint_y=None, height=64, spacing=8)
    row.add_widget(Button(
        text="Clear",
        font_size="20sp",
        size_hint_x=0.3,
        background_normal="",
        background_color=BTN_NEUTRAL,
        on_press=lambda _: (name_val.__setitem__(0, ""),
                            preview.__setattr__("text", "Start typing…")),
    ))
    row.add_widget(Button(
        text="Done",
        font_size="20sp",
        background_normal="",
        background_color=BTN_START,
        on_press=lambda _: (popup.dismiss(), on_done(name_val[0])),
    ))
    content.add_widget(row)

    popup = Popup(
        title="Enter name",
        content=content,
        size_hint=(0.95, 0.75),
        auto_dismiss=False,
    )
    return popup


def build_profile_popup(on_save=None):
    # ── pre-fill from state ───────────────────────────────────────
    cur_name  = state.get("user_name") or ""
    cur_wt    = float(state.get("user_weight_kg") or 80.0)
    cur_ht_cm = float(state.get("user_height_cm") or 172.72)

    # weight: 0.5 kg steps 30–200
    wt_values = [30.0 + i * 0.5 for i in range(341)]
    wt_clamped = max(30.0, min(200.0, cur_wt))
    wt_idx = round((wt_clamped - 30.0) / 0.5)

    # height: ft + in
    total_in = cur_ht_cm / 2.54
    ft  = int(total_in // 12)
    inch = round(total_in % 12)
    if inch == 12: ft, inch = ft + 1, 0
    ft   = max(4, min(7, ft))
    inch = max(0, min(11, inch))

    name_val = [cur_name]

    # ── root ─────────────────────────────────────────────────────
    content = BoxLayout(orientation="vertical", padding=8, spacing=6)
    with content.canvas.before:
        Color(*BG)
        _bg = Rectangle(pos=content.pos, size=content.size)
    content.bind(pos=lambda *a: setattr(_bg, "pos", content.pos),
                 size=lambda *a: setattr(_bg, "size", content.size))

    err = Label(text="", color=(1, 0.3, 0.3, 1),
                size_hint_y=None, height=24, halign="center")
    err.bind(size=err.setter("text_size"))

    # ── name ─────────────────────────────────────────────────────
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
            on_done=lambda n: (
                name_val.__setitem__(0, n),
                name_btn.__setattr__("text", n or "Tap to enter name"),
            ),
        ).open()
    name_btn.bind(on_press=_open_name)
    content.add_widget(name_btn)

    # ── weight ───────────────────────────────────────────────────
    content.add_widget(_section_label("Weight"))
    wt_dial = SpinDial(
        values=wt_values,
        initial=wt_idx,
        fmt=lambda v: f"{v:.1f} kg",
        wrap=False,
    )
    content.add_widget(wt_dial)

    # ── height ───────────────────────────────────────────────────
    content.add_widget(_section_label("Height"))
    ht_row = BoxLayout(size_hint_y=None, height=DIAL_H, spacing=8)
    ft_dial = SpinDial(
        values=list(range(4, 8)),
        initial=ft - 4,
        fmt=lambda v: f"{v} ft",
        wrap=False,
        size_hint_x=0.5,
    )
    in_dial = SpinDial(
        values=list(range(0, 12)),
        initial=inch,
        fmt=lambda v: f"{v} in",
        wrap=False,
        size_hint_x=0.5,
    )
    ht_row.add_widget(ft_dial)
    ht_row.add_widget(in_dial)
    content.add_widget(ht_row)

    # ── date of birth ─────────────────────────────────────────────
    content.add_widget(_section_label("Date of birth  (optional)"))
    dob_row = BoxLayout(size_hint_y=None, height=DIAL_H, spacing=8)

    day_dial = SpinDial(
        values=list(range(1, 32)),
        initial=0,
        fmt=str,
        wrap=True,
        size_hint_x=0.26,
    )
    mon_dial = SpinDial(
        values=list(range(1, 13)),
        initial=0,
        fmt=lambda v: _MONTHS[v - 1],
        wrap=True,
        size_hint_x=0.33,
    )
    year_dial = SpinDial(
        values=list(range(1936, 2017)),
        initial=45,  # 1981 default (~44 y/o)
        fmt=str,
        wrap=False,
        size_hint_x=0.41,
    )

    def _clamp_days(_=None):
        max_day = calendar.monthrange(year_dial.value, mon_dial.value)[1]
        day_dial.set_max(max_day)
        # restore full range when stepping back
        full = list(range(1, 32))
        day_dial._values = full[:max_day]

    mon_dial._on_change  = _clamp_days
    year_dial._on_change = _clamp_days

    dob_row.add_widget(day_dial)
    dob_row.add_widget(mon_dial)
    dob_row.add_widget(year_dial)
    content.add_widget(dob_row)

    content.add_widget(err)

    # ── training plan link ────────────────────────────────────────
    plan_btn = Button(
        text="Training Plan",
        font_size="20sp",
        size_hint_y=None,
        height=58,
        background_normal="",
        background_color=BTN_NEUTRAL,
    )

    def _open_plan(_):
        from ui.plan import build_plan_popup
        build_plan_popup().open()

    plan_btn.bind(on_press=_open_plan)
    content.add_widget(plan_btn)

    # ── save ─────────────────────────────────────────────────────
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
        weight_kg = wt_dial.value
        height_cm = round(ft_dial.value * 30.48 + in_dial.value * 2.54, 1)
        dob = f"{year_dial.value:04d}-{mon_dial.value:02d}-{day_dial.value:02d}"
        result = save_user_profile(name_val[0].strip(), weight_kg, height_cm, dob)
        if result is None:
            err.text = "Could not save — check storage."
            return
        popup.dismiss()
        if on_save:
            on_save()

    save_btn.bind(on_press=_save)
    return popup
