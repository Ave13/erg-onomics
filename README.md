# erg-onomics

Concept2 PM5 rowing app for the Arduino UNO Q. Connects to the PM5 over BLE, logs every stroke to SQLite, and delivers post-workout analytics with no cloud dependency. Live metrics stream to an iPad or iPhone via FTMS broadcast (ErgZone, Zwift).

## Screenshots

| Live Display | Post-Session Summary |
|---|---|
| ![Live display](docs/screenshots/live.png) | ![Session summary](docs/screenshots/summary.png) |

| Workout Selector | Training Plan |
|---|---|
| ![Workout selector](docs/screenshots/workouts.png) | ![Training plan](docs/screenshots/plan.png) |

> To add screenshots: SSH into the UNO Q and run `scrot docs/screenshots/live.png` while the app is running.

## Features

**Live metrics** — Pace, Watts, SPM (EMA-smoothed), Distance, Time, HR — all from the PM5 over BLE with no cables.

**Session recording** — Every stroke logged to SQLite: drive/recovery timing, avg/peak force, work per stroke, HR. Sessions survive restarts and can be resumed.

**Post-session summary** — Pace graph, force curve trend, Strive Score (HR-zone × time), streak count, personal records.

**Personal records** — Tracked per user for 2k/5k/10k pace, distance, time, avg/peak watts, avg SPM.

**Workout library** — 10 preset Concept2 pieces (2k Test, 5k Test, 6×500m, 4×1000m, etc.) plus a touchscreen interval builder for custom sessions.

**Training plan** — Assign workouts to days of the week; today's workout appears in the status bar.

**Pace target** — Set a /500m target; the pace card turns green/red live.

**Audio cues** — espeak announces distance, pace, and HR every 500 m or 60 s.

**FTMS broadcast** — Broadcasts as an FTMS Rower over BLE so Zwift and ErgZone can connect directly (requires `pip install bless`).

**TCX export** — Every session exported to `exports/` for Apple Health (via HealthFit), Garmin Connect, or Strava.

**Session comparison** — Overlay pace graphs and compare stats for any two past sessions side by side.

## Stack

- **Python 3** — `bleak` (BLE), `Kivy` (UI), `SQLite` (storage)
- **Target** — Arduino UNO Q (Qualcomm QRB2210, ARM Cortex-A53, BT 5.1), Debian Linux, 4 GB model recommended

## Quick Start

```bash
# Install dependencies
pip install bleak "kivy[base]"
sudo apt install -y python3-dbus python3-gi espeak
pip install bless                          # enables FTMS broadcast to iPad
sudo usermod -aG bluetooth $USER           # then log out/in once

# Run
DISPLAY=:0 python main.py

# If Kivy has rendering issues on the Adreno GPU:
KIVY_GL_BACKEND=sdl2 DISPLAY=:0 python main.py
```

Power on the PM5, start rowing — the app auto-discovers it by name over BLE. First launch prompts for a user profile (name, weight, height, date of birth). Open **ErgZone** on iPad and it will find "ErgRower" over Bluetooth.

## Data

All data is stored in `rowing.db` (SQLite) in the working directory. The database is not checked in. Per-stroke data is in `stroke_log`; session summaries in `sessions`. Both are readable by any SQLite tool for custom analysis.

TCX files land in `exports/` and can be imported directly into Garmin Connect or Apple Health via HealthFit.
