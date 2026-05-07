from kivy.config import Config
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '600')

import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from ble.pm5 import state, start_ble

# ── palette ──────────────────────────────────────────────────────────────────
BG         = (0.10, 0.10, 0.10, 1)
PANEL      = (0.15, 0.15, 0.15, 1)
STATUSBAR  = (0.07, 0.07, 0.07, 1)
GREEN      = (0.00, 1.00, 0.53, 1)
WHITE      = (1.00, 1.00, 1.00, 1)
GRAY       = (0.55, 0.55, 0.55, 1)


def _bg(widget, color):
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(size=widget.size, pos=widget.pos)
    widget.bind(
        size=lambda w, v: setattr(rect, 'size', v),
        pos=lambda w, v: setattr(rect, 'pos', v),
    )
    return rect


class MetricPanel(BoxLayout):
    def __init__(self, title, **kwargs):
        super().__init__(orientation='vertical', padding=[0, 12, 0, 8], **kwargs)
        _bg(self, PANEL)

        self._title = Label(
            text=title,
            font_size='17sp',
            color=GRAY,
            size_hint_y=0.30,
            halign='center',
            valign='middle',
        )
        self._value = Label(
            text='--',
            font_size='58sp',
            bold=True,
            color=WHITE,
            size_hint_y=0.70,
            halign='center',
            valign='middle',
        )
        self._title.bind(size=self._title.setter('text_size'))
        self._value.bind(size=self._value.setter('text_size'))
        self.add_widget(self._title)
        self.add_widget(self._value)

    def set(self, value):
        self._value.text = str(value)


class Dashboard(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=0, **kwargs)
        _bg(self, BG)

        # ── pace block (top ~50%) ─────────────────────────────────────────────
        pace_block = BoxLayout(
            orientation='vertical',
            size_hint_y=0.50,
            padding=[0, 20, 0, 0],
        )

        pace_title = Label(
            text='PACE  /500m',
            font_size='19sp',
            color=GRAY,
            size_hint_y=0.22,
            halign='center',
            valign='middle',
        )
        self._pace = Label(
            text='--:--',
            font_size='130sp',
            bold=True,
            color=GREEN,
            size_hint_y=0.78,
            halign='center',
            valign='middle',
        )
        pace_title.bind(size=pace_title.setter('text_size'))
        self._pace.bind(size=self._pace.setter('text_size'))

        pace_block.add_widget(pace_title)
        pace_block.add_widget(self._pace)

        # ── secondary metrics (4 columns, ~42%) ──────────────────────────────
        grid = GridLayout(cols=4, size_hint_y=0.42, spacing=4, padding=[4, 0, 4, 4])

        self._spm   = MetricPanel('SPM')
        self._watts = MetricPanel('WATTS')
        self._dist  = MetricPanel('DIST  m')
        self._time  = MetricPanel('TIME')

        grid.add_widget(self._spm)
        grid.add_widget(self._watts)
        grid.add_widget(self._dist)
        grid.add_widget(self._time)

        # ── status bar (bottom ~8%) ───────────────────────────────────────────
        status_bar = BoxLayout(size_hint_y=0.08, padding=[24, 0])
        _bg(status_bar, STATUSBAR)

        self._status = Label(
            text='Scanning for PM5…',
            font_size='15sp',
            markup=True,
            color=GRAY,
            halign='left',
            valign='middle',
        )
        self._status.bind(size=self._status.setter('text_size'))
        status_bar.add_widget(self._status)

        self.add_widget(pace_block)
        self.add_widget(grid)
        self.add_widget(status_bar)

    def refresh(self, pace, spm, watts, distance, elapsed, connected, device_name):
        self._pace.text = pace
        self._spm.set(spm if spm else '--')
        self._watts.set(watts if watts else '--')
        self._dist.set(f'{distance:,.0f}' if distance else '--')

        if elapsed:
            m, s = divmod(int(elapsed), 60)
            self._time.set(f'{m}:{s:02d}')
        else:
            self._time.set('--')

        if connected:
            self._status.text = f'[color=00ff88]●[/color]  {device_name}'
        else:
            self._status.text = '[color=888888]○[/color]  Scanning for PM5…'


class RowingApp(App):
    def build(self):
        self.title = 'erg-onomics'
        self._dash = Dashboard()
        Clock.schedule_interval(self._tick, 0.5)
        threading.Thread(target=start_ble, daemon=True).start()
        return self._dash

    def _tick(self, dt):
        self._dash.refresh(
            pace=state['pace'],
            spm=state['spm'],
            watts=state['watts'],
            distance=state['distance'],
            elapsed=state['elapsed'],
            connected=state['connected'],
            device_name=state['device_name'],
        )
