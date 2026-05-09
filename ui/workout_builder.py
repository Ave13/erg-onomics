"""
Workout selector and interval builder popups.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle

from db.workouts import list_workouts, save_workout, delete_workout, workout_summary, _interval_label
from ui.spinners import SpinDial, DIAL_H
from ui.theme import BG, CARD_BG, LABEL_COLOR, VALUE_COLOR, BTN_START, BTN_END, BTN_NEUTRAL

_DIST_VALUES  = [100, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000, 2500, 3000, 5000, 10000]
_TIME_VALUES  = [30, 60, 90, 120, 150, 180, 240, 300, 360, 420, 480, 600, 900, 1200, 1800, 3600]
_REST_VALUES  = [0, 30, 60, 90, 120, 150, 180, 240, 300, 360, 420, 480, 600]


def _bg(widget):
    with widget.canvas.before:
        Color(*BG)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda *a: setattr(rect, "pos", widget.pos),
                size=lambda *a: setattr(rect, "size", widget.size))


def _card_bg(widget):
    with widget.canvas.before:
        Color(*CARD_BG)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda *a: setattr(rect, "pos", widget.pos),
                size=lambda *a: setattr(rect, "size", widget.size))


# ── Workout Selector ────────────────────────────────────────────────────────

def build_workout_selector(on_select, on_cancel=None):
    """
    Popup listing all workouts.
    on_select(workout_id, name, definition) called when user picks one.
    Includes a "New Custom" path to build_workout_editor.
    """
    root = BoxLayout(orientation="vertical", padding=0, spacing=0)
    _bg(root)

    popup = Popup(title="Select Workout", content=root,
                  size_hint=(0.95, 0.9), auto_dismiss=False)

    def _refresh():
        root.clear_widgets()
        _bg(root)

        inner = BoxLayout(orientation="vertical", padding=8, spacing=6, size_hint_y=None)
        inner.bind(minimum_height=inner.setter("height"))
        _bg(inner)

        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(inner)

        workouts = list_workouts()
        for wid, name, definition, is_preset in workouts:
            row = BoxLayout(size_hint_y=None, height=72, spacing=6)
            _card_bg(row)

            info = BoxLayout(orientation="vertical", size_hint_x=0.72, padding=(8, 4))
            title_lbl = Label(text=name, font_size="18sp", bold=True, color=VALUE_COLOR,
                              halign="left", valign="bottom", size_hint_y=0.55)
            title_lbl.bind(size=title_lbl.setter("text_size"))
            summ_lbl  = Label(text=workout_summary(definition), font_size="13sp",
                              color=LABEL_COLOR, halign="left", valign="top", size_hint_y=0.45)
            summ_lbl.bind(size=summ_lbl.setter("text_size"))
            info.add_widget(title_lbl)
            info.add_widget(summ_lbl)

            sel_btn = Button(text="Select", font_size="16sp",
                             background_normal="", background_color=BTN_START,
                             size_hint_x=0.28)

            def _pick(_, w=wid, n=name, d=definition):
                on_select(w, n, d)
                popup.dismiss()

            sel_btn.bind(on_press=_pick)

            if not is_preset:
                del_btn = Button(text="×", font_size="20sp",
                                 background_normal="", background_color=BTN_END,
                                 size_hint_x=0.10)
                def _del(_, w=wid):
                    delete_workout(w)
                    _refresh()
                del_btn.bind(on_press=_del)
                row.add_widget(info)
                row.add_widget(sel_btn)
                row.add_widget(del_btn)
            else:
                row.add_widget(info)
                row.add_widget(sel_btn)

            inner.add_widget(row)
            inner.add_widget(BoxLayout(size_hint_y=None, height=4))

        root.add_widget(scroll)

        btn_row = BoxLayout(size_hint_y=None, height=70, spacing=8, padding=(8, 4))
        new_btn = Button(text="New Custom", font_size="18sp",
                         background_normal="", background_color=BTN_NEUTRAL)
        cancel_btn = Button(text="Cancel", font_size="18sp",
                            background_normal="", background_color=BTN_END)

        def _new(_):
            popup.dismiss()
            def _on_saved(wid, wname, wdef):
                on_select(wid, wname, wdef)
            build_workout_editor(on_save=_on_saved).open()

        def _cancel(_):
            popup.dismiss()
            if on_cancel:
                on_cancel()

        new_btn.bind(on_press=_new)
        cancel_btn.bind(on_press=_cancel)
        btn_row.add_widget(new_btn)
        btn_row.add_widget(cancel_btn)
        root.add_widget(btn_row)

    _refresh()
    return popup


# ── Interval Editor ─────────────────────────────────────────────────────────

def build_workout_editor(initial_intervals=None, initial_name="", on_save=None):
    """
    Popup to build a custom interval workout.
    on_save(workout_id, name, definition) called on save.
    """
    from ui.keyboard import BigKeyboard

    intervals  = list(initial_intervals or [])
    name_state = [initial_name or "My Workout"]

    root = BoxLayout(orientation="vertical", padding=8, spacing=6)
    _bg(root)

    popup = Popup(title="Build Workout", content=root,
                  size_hint=(1, 1), auto_dismiss=False)

    # ── name row ────────────────────────────────────────────────────
    name_row = BoxLayout(size_hint_y=None, height=56, spacing=8)
    name_row.add_widget(Label(text="Name:", font_size="18sp", color=LABEL_COLOR,
                              size_hint_x=0.22))
    name_btn = Button(text=name_state[0], font_size="18sp",
                      background_normal="", background_color=CARD_BG,
                      color=VALUE_COLOR, size_hint_x=0.78)

    def _edit_name(_):
        nv = [name_state[0]]
        nc = BoxLayout(orientation="vertical", padding=8, spacing=6)
        prev = Button(text=nv[0] or "Start typing…", font_size="22sp",
                      size_hint_y=None, height=54,
                      background_normal="", background_color=CARD_BG,
                      color=VALUE_COLOR)

        def _key(ch):
            if ch == "\b":
                nv[0] = nv[0][:-1]
            elif ch == "\n":
                name_state[0] = nv[0]
                name_btn.text = nv[0] or "My Workout"
                np.dismiss()
                return
            else:
                if len(nv[0]) < 40:
                    nv[0] += ch
            prev.text = nv[0] or "Start typing…"

        nc.add_widget(prev)
        nc.add_widget(BigKeyboard(on_key=_key))
        nr = BoxLayout(size_hint_y=None, height=60, spacing=8)
        nr.add_widget(Button(text="Done", font_size="20sp",
                             background_normal="", background_color=BTN_START,
                             on_press=lambda _: (
                                 name_state.__setitem__(0, nv[0]),
                                 name_btn.__setattr__("text", nv[0] or "My Workout"),
                                 np.dismiss()
                             )))
        nc.add_widget(nr)
        np = Popup(title="Workout Name", content=nc,
                   size_hint=(0.95, 0.72), auto_dismiss=False)
        np.open()

    name_btn.bind(on_press=_edit_name)
    name_row.add_widget(name_btn)
    root.add_widget(name_row)

    # ── interval list ───────────────────────────────────────────────
    iv_inner = BoxLayout(orientation="vertical", padding=4, spacing=4, size_hint_y=None)
    iv_inner.bind(minimum_height=iv_inner.setter("height"))
    iv_scroll = ScrollView(do_scroll_x=False, size_hint_y=0.35)
    iv_scroll.add_widget(iv_inner)
    root.add_widget(iv_scroll)

    def _refresh_list():
        iv_inner.clear_widgets()
        if not intervals:
            iv_inner.add_widget(Label(text="No intervals yet — add one below.",
                                      font_size="15sp", color=LABEL_COLOR,
                                      size_hint_y=None, height=40))
        for i, iv in enumerate(intervals):
            row = BoxLayout(size_hint_y=None, height=50, spacing=6)
            _card_bg(row)
            row.add_widget(Label(
                text=f"#{i + 1}  {_interval_label(iv)}",
                font_size="15sp", color=VALUE_COLOR, halign="left", size_hint_x=0.82,
            ))
            db = Button(text="×", font_size="20sp",
                        background_normal="", background_color=BTN_END,
                        size_hint_x=0.18)
            db.bind(on_press=lambda _, idx=i: (_remove(idx)))
            row.add_widget(db)
            iv_inner.add_widget(row)

    def _remove(idx):
        if 0 <= idx < len(intervals):
            intervals.pop(idx)
            _refresh_list()

    _refresh_list()

    # ── type toggle + dials ─────────────────────────────────────────
    type_state = ["distance"]

    type_row = BoxLayout(size_hint_y=None, height=56, spacing=4)
    dist_btn = Button(text="Distance", font_size="18sp",
                      background_normal="", background_color=BTN_START)
    time_btn = Button(text="Time", font_size="18sp",
                      background_normal="", background_color=BTN_NEUTRAL)

    dist_dial = SpinDial(values=_DIST_VALUES, initial=_DIST_VALUES.index(500),
                         fmt=lambda v: f"{v}m", wrap=False)
    time_dial = SpinDial(values=_TIME_VALUES, initial=_TIME_VALUES.index(300),
                         fmt=lambda v: f"{v // 60}:{v % 60:02d}", wrap=False)
    rest_dial = SpinDial(values=_REST_VALUES, initial=_REST_VALUES.index(120),
                         fmt=lambda v: "no rest" if v == 0 else f"{v // 60}:{v % 60:02d} rest",
                         wrap=False)

    dial_row = BoxLayout(size_hint_y=None, height=DIAL_H, spacing=6)
    dial_row.add_widget(dist_dial)
    dial_row.add_widget(rest_dial)

    def _set_type(t):
        type_state[0] = t
        if t == "distance":
            dist_btn.background_color = BTN_START
            time_btn.background_color = BTN_NEUTRAL
            dial_row.clear_widgets()
            dial_row.add_widget(dist_dial)
            dial_row.add_widget(rest_dial)
        else:
            dist_btn.background_color = BTN_NEUTRAL
            time_btn.background_color = BTN_START
            dial_row.clear_widgets()
            dial_row.add_widget(time_dial)
            dial_row.add_widget(rest_dial)

    dist_btn.bind(on_press=lambda _: _set_type("distance"))
    time_btn.bind(on_press=lambda _: _set_type("time"))
    type_row.add_widget(dist_btn)
    type_row.add_widget(time_btn)
    root.add_widget(type_row)
    root.add_widget(dial_row)

    add_btn = Button(text="+ Add Interval", font_size="19sp", size_hint_y=None, height=58,
                     background_normal="", background_color=BTN_START)

    def _add(_):
        rest = rest_dial.value
        if type_state[0] == "distance":
            iv = {"type": "distance", "meters": dist_dial.value, "rest_secs": rest}
        else:
            iv = {"type": "time", "seconds": time_dial.value, "rest_secs": rest}
        intervals.append(iv)
        _refresh_list()

    add_btn.bind(on_press=_add)
    root.add_widget(add_btn)

    # ── Save / Cancel ───────────────────────────────────────────────
    btn_row = BoxLayout(size_hint_y=None, height=68, spacing=8)
    save_btn   = Button(text="Save", font_size="20sp",
                        background_normal="", background_color=BTN_START)
    cancel_btn = Button(text="Cancel", font_size="20sp",
                        background_normal="", background_color=BTN_END)

    def _do_save(_):
        if not intervals:
            return
        wid = save_workout(name_state[0] or "My Workout", intervals)
        popup.dismiss()
        if on_save and wid:
            on_save(wid, name_state[0], {"intervals": intervals})

    save_btn.bind(on_press=_do_save)
    cancel_btn.bind(on_press=lambda _: popup.dismiss())
    btn_row.add_widget(save_btn)
    btn_row.add_widget(cancel_btn)
    root.add_widget(btn_row)

    return popup
