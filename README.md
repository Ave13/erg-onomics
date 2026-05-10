# erg-onomics

Concept2 PM5 rowing app for the Arduino UNO Q. Connects to the PM5 over BLE, logs every stroke to SQLite, and delivers post-workout analytics with no cloud dependency. The primary UI runs as a Streamlit web app — open it on iPad or iPhone via Safari over local WiFi. The UNO Q simultaneously broadcasts live data as an FTMS Rower for ErgZone and Zwift.

## Screenshots

| Live Display | Post-Session Summary |
|---|---|
| ![Live display](docs/screenshots/live.png) | ![Session summary](docs/screenshots/summary.png) |

| Workout Selector | Training Plan |
|---|---|
| ![Workout selector](docs/screenshots/workouts.png) | ![Training plan](docs/screenshots/plan.png) |

> To add screenshots: open the app on iPad, take a screenshot, and drop it in `docs/screenshots/`.

## Features

**Live metrics** — Pace, Watts, SPM (EMA-smoothed), Distance, Time, HR — all from the PM5 over BLE with no cables. Pace card turns green/red vs your target.

**Session recording** — Every stroke logged to SQLite: drive/recovery timing, avg/peak force, work per stroke, HR. Sessions survive restarts and can be resumed.

**Post-session summary** — Pace graph, force curve trend, Strive Score (HR-zone × time), streak count, personal records.

**Personal records** — Tracked per user for 2k/5k/10k pace, distance, time, avg/peak watts, avg SPM.

**Workout library** — 10 preset Concept2 pieces (2k Test, 5k Test, 6×500m, 4×1000m, etc.) plus an interval builder for custom sessions.

**Training plan** — Assign workouts to days of the week; today's workout appears in the status bar.

**Pace target** — Set a /500m target; the pace card turns green/red live.

**Audio cues** — espeak announces distance, pace, and HR every 500 m or 60 s.

**FTMS broadcast** — Broadcasts as an FTMS Rower over BLE so ErgZone and Zwift on iPad/iPhone can connect directly (requires `pip install bless`).

**TCX export** — Every session exported to `exports/` for Apple Health (via HealthFit), Garmin Connect, or Strava.

**Session comparison** — Overlay pace graphs and compare stats for any two past sessions side by side.

## Stack

- **Python 3** — `bleak` (BLE central), `bless` (FTMS peripheral), `streamlit` + `plotly` (web UI), `SQLite` (storage)
- **Target** — Arduino UNO Q (Qualcomm QRB2210, ARM Cortex-A53, BT 5.1), Debian Linux, 4 GB model recommended
- **Client** — Any browser; optimised for iPad/iPhone Safari

## Quick Start

```bash
# 1. Install dependencies
pip install bleak streamlit plotly
sudo apt install -y python3-dbus python3-gi espeak
pip install bless                          # enables FTMS broadcast to ErgZone / Zwift
sudo usermod -aG bluetooth $USER           # then log out/in once

# 2. Run the Streamlit app
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

Open `http://<UNO-Q-IP>:8501` in iPad or iPhone Safari — no app download needed.

Power on the PM5 and start rowing. The app auto-discovers it by name over BLE. On first launch, go to **Profile** to set your name, weight, height, and date of birth. Open **ErgZone** on iPad and it will also find "ErgRower" over Bluetooth simultaneously.

### Kivy fallback (local display)

If you have a display connected directly to the UNO Q:

```bash
pip install "kivy[base]"

DISPLAY=:0 python main.py

# If Kivy has rendering issues on the Adreno GPU:
KIVY_GL_BACKEND=sdl2 DISPLAY=:0 python main.py
```

## Data

All data is stored in `rowing.db` (SQLite) in the working directory. The database is not checked in. Per-stroke data is in `stroke_log`; session summaries in `sessions`. Both are readable by any SQLite tool for custom analysis.

TCX files land in `exports/` and can be imported directly into Garmin Connect or Apple Health via HealthFit.
