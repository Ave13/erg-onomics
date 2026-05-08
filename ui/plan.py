"""
Weekly training plan editor popup.
7-day grid; tap a day to assign or clear its workout.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle

from db.training_plan import get_plan, set_day, clear_day, day_name
from db.workouts import get_workout, workout_summary
from ui.theme import BG, CARD_BG, LABEL_COLOR, VALUE_COLOR, BTN_START, BTN_END, BTN_NEUTRAL

_DAY_COLORS = [
    (0.25, 0.60, 0.95, 1),   # Mon — blue
    (0.25, 0.60, 0.95, 1),   # Tue
    (0.25, 0.60, 0.95, 1),   # Wed
    (0.25, 0.60, 0.95, 1),   # Thu
    (0.25, 0.60, 0.95, 1),   # Fri
    (0.20, 0.75, 0.45, 1),   # Sat — green (weekend)
    (0.20, 0.75, 0.45, 1),   # Sun
]


def _bg(w):
    with w.canvas.before:
        Color(*BG)
        r = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda *a: setattr(r, "pos", w.pos),
           size=lambda *a: setattr(r, "size", w.size))


def build_plan_popup():
    root = BoxLayout(orientation="vertical", padding=8, spacing=6)
    _bg(root)

    popup = Popup(title="Weekly Training Plan", content=root,
                  size_hint=(1, 1), auto_dismiss=False)

    def _refresh():
        root.clear_widgets()
        _bg(root)

        plan = get_plan()

        grid = GridLayout(cols=1, spacing=6)

        for day in range(7):
            row = BoxLayout(size_hint_y=None, height=72, spacing=6)
            with row.canvas.before:
                Color(*CARD_BG)
                rr = Rectangle(pos=row.pos, size=row.size)
            row.bind(pos=lambda *a, r=rr: setattr(r, "pos", a[0].pos),
                     size=lambda *a, r=rr: setattr(r, "size", a[0].size))

            day_lbl = Label(
                text=day_name(day),
                font_size="18sp", bold=True,
                color=_DAY_COLORS[day],
                size_hint_x=0.15,
                halign="center",
            )
            day_lbl.bind(size=day_lbl.setter("text_size"))

            wid, notes = plan.get(day, (None, ""))
            if wid:
                w = get_workout(wid)
                if w:
                    desc_txt = f"{w[1]}  ({workout_summary(w[2])})"
                else:
                    desc_txt = "Unknown workout"
            else:
                desc_txt = "Rest"

            desc_lbl = Label(
                text=desc_txt, font_size="15sp",
                color=VALUE_COLOR if wid else LABEL_COLOR,
                halign="left", size_hint_x=0.55,
            )
            desc_lbl.bind(size=desc_lbl.setter("text_size"))

            assign_btn = Button(
                text="Assign", font_size="15sp", size_hint_x=0.18,
                background_normal="", background_color=BTN_START,
            )
            clear_btn = Button(
                text="Clear", font_size="15sp", size_hint_x=0.12,
                background_normal="",
                background_color=BTN_END if wid else BTN_NEUTRAL,
                disabled=not wid,
            )

            def _assign(_, d=day):
                from ui.workout_builder import build_workout_selector

                def _selected(wid, wname, wdef):
                    set_day(d, wid)
                    _refresh()

                build_workout_selector(on_select=_selected).open()

            def _clear(_, d=day):
                clear_day(d)
                _refresh()

            assign_btn.bind(on_press=_assign)
            clear_btn.bind(on_press=_clear)

            row.add_widget(day_lbl)
            row.add_widget(desc_lbl)
            row.add_widget(assign_btn)
            row.add_widget(clear_btn)
            grid.add_widget(row)

        root.add_widget(grid)

        close_btn = Button(
            text="Done", font_size="22sp", size_hint_y=None, height=70,
            background_normal="", background_color=BTN_NEUTRAL,
        )
        close_btn.bind(on_press=lambda _: popup.dismiss())
        root.add_widget(close_btn)

    _refresh()
    return popup
