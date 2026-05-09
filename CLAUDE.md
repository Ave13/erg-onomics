# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Standard launch (requires a display connected or X11 running)
DISPLAY=:0 python main.py

# From SSH session
DISPLAY=:0 python main.py &

# If Kivy has rendering issues on the UNO Q's Adreno GPU, force SDL2 backend
KIVY_GL_BACKEND=sdl2 DISPLAY=:0 python main.py
```

The app auto-connects to any BLE device whose name contains "PM5". No PM5 present? The UI still launches; all BLE notifications simply never fire.

## Installing Dependencies

```bash
# Core
pip install bleak "kivy[base]"

# FTMS Rower broadcast (ErgZone / Zwift on iPad)
sudo apt install -y python3-dbus python3-gi
pip install bless
sudo usermod -aG bluetooth $USER   # then log out/in once

# Audio cues
sudo apt install espeak
```

## Architecture

### Data Flow

```
PM5 (BLE notify) ──► ble/pm5.py parse_*() ──► state dict
                                                    │
                                    Kivy Clock (2Hz)┘
                                                    │
                                              ui/app.py update_ui()
```

`state` is a plain `dict` in `ble/pm5.py` shared across all modules. BLE callbacks mutate it from the asyncio thread; the Kivy main thread reads it every 500 ms. No locking — reads are cheap and occasional torn values are invisible at display refresh rates.

BLE runs in a background `threading.Thread` that calls `asyncio.run(ble_main())`. Kivy's event loop is on the main thread. Never call Kivy APIs from inside BLE callbacks; use `Clock.schedule_once` if you need to trigger UI from a BLE event.

### Module Map

| Module | Role |
|---|---|
| `ble/pm5.py` | BLE scan/connect, all parse functions, `state` dict, session lifecycle (`start_session`, `stop_session`, `pause_session`), SQLite init |
| `ble/ftms.py` | FTMS Rower BLE GATT server broadcast (bless); silent no-op if bless not installed |
| `db/records.py` | Personal records: `check_and_save_records()` called by `stop_session()`; sliding-window pace PR algorithm |
| `db/strive.py` | Strive Score calculation from HR zone × time (Peloton-style); Tanaka max-HR formula |
| `db/streak.py` | Consecutive training-day streak calculation |
| `db/workouts.py` | 10 preset Concept2 workouts + custom workout CRUD; seeds presets on first run |
| `db/training_plan.py` | Weekly plan (day_of_week → workout_id); `get_today()` used in status bar |
| `db/export.py` | TCX file export → `exports/` directory; called at end of every session |
| `ui/app.py` | Root Kivy app; 6-card metric grid; button row; `update_ui` polling loop |
| `ui/summary.py` | Post-session popup: stats grid, pace graph, force curve, Strive Score, streak, PRs, drag factor, Compare button |
| `ui/comparison.py` | Two-session side-by-side popup with overlaid pace graph |
| `ui/workout_builder.py` | Workout selector popup + interval editor (SpinDial-based) |
| `ui/plan.py` | 7-day training plan editor popup |
| `ui/profile.py` | User profile popup (SpinDials for weight/height/DOB; BigKeyboard for name) |
| `ui/audio.py` | espeak cues every 500 m or 60 s during a session |
| `ui/keyboard.py` | `BigKeyboard` — Button-grid QWERTY/numeric; 350 ms debounce |
| `ui/spinners.py` | `SpinDial` — ▲/▼ spinner widget, 52 px buttons, 148 px total height |
| `ui/widgets.py` | `MetricCard`, `ActionButton` |
| `ui/theme.py` | All colours and font sizes (single source of truth) |

### Database

Single SQLite file `rowing.db` in the working directory (not checked in). Schema is created/migrated by `_init_db()` in `ble/pm5.py` using `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE … ADD COLUMN` guards — no migration tool needed.

Key tables: `sessions`, `stroke_log`, `user_profile`, `records`, `workouts`, `training_plan`.

`stroke_log` stores one row per stroke with elapsed time, speed, drive/recovery timing, force, HR. This is the primary data source for all post-session analytics.

### Session Lifecycle

1. `start_session()` — inserts a row in `sessions` (status=`active`); sets `state["session_id"]`
2. Strokes arrive via BLE → `parse_stroke_data()` → `_log_stroke()` inserts into `stroke_log`
3. `stop_session()` — aggregates stroke_log → updates `sessions` row (status=`complete`); calls `check_and_save_records()`; calls `export_tcx()`; returns TCX path
4. `ui/app.py._on_end()` captures `session_id` **before** calling `stop_session()` (stop clears `state["session_id"]`), then opens `build_summary_popup(sid)`

### SPM Smoothing

Raw inter-stroke intervals go through an EMA (`_EMA_ALPHA = 0.25`) stored in `_ema_interval_secs`. SPM is `round(60 / _ema_interval_secs)`. Stale detection: if the last stroke timestamp is >10 s old, SPM reverts to `"--"`.

### Kivy UI Constraints

- **`ActionButton`**: `_active_color` and `_disabled_color` **must** be assigned before `super().__init__()` — Kivy fires `on_disabled` during init, before instance variables would otherwise exist.
- **`SpinDial`**: always set explicit pixel heights (`size_hint_y=None, height=DIAL_H`). Fraction-based heights inside fixed-height parents produce near-invisible buttons.
- **`BigKeyboard`**: uses Button widgets (not TextInput) to avoid Kivy's virtual keyboard focus system. `on_key` callback receives `"\b"` for backspace, `"\n"` for Done.
- All canvas background rectangles must be updated in both `pos` and `size` bind callbacks or they drift on resize.

### PM5 BLE Characteristics

All under service base `XXXXXXXX-43E5-11E4-916C-0800200C9A66`:

| Characteristic | UUID prefix | Parsed fields |
|---|---|---|
| General Status | `CE060031` | elapsed (0.01 s), distance (0.1 m), workout_state |
| Additional Status 1 | `CE060032` | speed_mm_s (bytes 0–1), stroke_state (byte 2), drag_factor (byte 3) |
| Stroke Data | `CE060035` | drive_length, drive_time, recovery, peak/avg force, stroke_distance, work_per_stroke, stroke_count |
| Heart Rate | `CE06003A` | hr_bpm |
| Workout Summary | `CE060039` | (stub — not yet parsed) |

> **Critical**: PM5 characteristics cannot be `read()` — only `start_notify()`. Direct reads return zeros.

### Target Hardware

**Arduino UNO Q** — quad-core ARM Cortex-A53 @ 2 GHz, 2–4 GB RAM, 16–32 GB eMMC, Bluetooth 5.1, Debian Linux. The 4 GB model is recommended. Everything in this repo runs on it unmodified; it is a Linux ARM board in the same class as a Raspberry Pi.

### FTMS Broadcast (`ble/ftms.py`)

Broadcasts live data as an FTMS Rower (service `0x1826`, Rower Data `0x2AD1`) every 500 ms. ErgZone and Zwift on iPad/iPhone can connect directly via BLE. The UNO Q's Qualcomm BT 5.1 chip handles central (→ PM5) and peripheral (← iPad) simultaneously via BlueZ dual-role. Requires `pip install bless` plus the D-Bus system packages above. Gracefully disabled if bless is absent.
