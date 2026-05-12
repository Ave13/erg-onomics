# erg-onomics

Concept2 PM5 rowing app for the Arduino UNO Q. Connects to the PM5 over BLE, logs every stroke to SQLite, and delivers real-time analytics with no cloud dependency. The UI is a FastAPI web app — open it on iPad or iPhone via Safari over the UNO Q's own WiFi hotspot. The UNO Q simultaneously broadcasts live data as an FTMS Rower for ErgZone and Zwift.

## Screenshots

| Live Display | Post-Session Summary |
|---|---|
| ![Live display](docs/screenshots/live.png) | ![Session summary](docs/screenshots/summary.png) |

| Workout Selector | Training Plan |
|---|---|
| ![Workout selector](docs/screenshots/workouts.png) | ![Training plan](docs/screenshots/plan.png) |

> To add screenshots: open the app on iPad, take a screenshot, and drop it in `docs/screenshots/`.

## Features

**5 swipeable Row screens** — Power, Endurance, Technique, Force Curve, and Intervals. Swipe left/right on the Row tab to switch. Tap any card to cycle through alternate metrics for that slot.

**Live metrics** — Pace, Watts, SPM (EMA-smoothed), Distance, Time, HR, Drive/Recovery timing, Peak/Avg force, Drag factor — all from the PM5 over BLE with no cables.

**Force curve** — Approximate Bezier drive curve drawn per stroke versus an ideal reference. Counts consecutive "perfect stroke" streaks (peak/avg force ratio, drive time, drive length vs expected).

**HR zone strip** — Live Z1–Z5 colour bar on the Endurance screen using the Tanaka max-HR formula.

**Interval tracking** — Work/rest phase countdown when a workout is loaded; shows current interval, remaining distance or time, and a progress bar.

**Session recording** — Every stroke logged to SQLite: drive/recovery timing, avg/peak force, work per stroke, HR. Sessions survive restarts and can be resumed.

**Post-session summary** — Pace graph, force curve trend, 500 m split table, Strive Score (HR-zone × time), streak count, personal records.

**Personal records** — Tracked per user for 2k/5k/10k pace, distance, time, avg/peak watts, avg SPM.

**Workout library** — 10 preset Concept2 pieces (2k Test, 5k Test, 6×500m, 4×1000m, etc.) plus an interval builder for custom sessions (distance, time, or calorie type; up to 50 reps).

**Training plan** — Assign workouts to days of the week.

**Multi-erg selection** — If two PM5s are in the same room a picker sheet appears; the browser remembers your choice.

**Pace target** — Set a /500m target; the pace card turns green/red live.

**Audio cues** — espeak announces distance, pace, and HR every 500 m or 60 s.

**FTMS broadcast** — Broadcasts as an FTMS Rower over BLE so ErgZone and Zwift on iPad/iPhone can connect directly.

**TCX export** — Every session exported to `exports/` for Apple Health (via HealthFit), Garmin Connect, or Strava.

## Stack

- **Python 3** — `bleak` (BLE central), `bless` (FTMS peripheral), `fastapi` + `uvicorn` (web UI), `SQLite` (storage)
- **Target** — Arduino UNO Q (Qualcomm QRB2210, ARM Cortex-A53, BT 5.1), Debian Linux, 4 GB model recommended
- **Client** — Any browser; optimised for iPad/iPhone Safari

---

## Setup (first time)

Run the installer once after cloning. It handles everything — packages, WiFi AP, systemd service:

```bash
bash install.sh
```

The script will:
1. Install system packages (`python3-pip`, `espeak`, `hostapd`, `dnsmasq`)
2. Install Python packages (`bleak`, `bless`, `fastapi`, `uvicorn`)
3. Add your user to the `bluetooth` group
4. Configure a WiFi access point — **SSID: ErgRower / Password: rowrow12**
5. Set a static IP of `10.0.0.1` on the WiFi interface
6. Create and enable a systemd `erg` service that starts the app on boot
7. Prompt to reboot

After reboot:
- Connect iPad/iPhone to the **ErgRower** WiFi network
- Open Safari and go to **`http://10.0.0.1:8501`**

---

## Starting the app

### Automatic (after running install.sh)

The app starts automatically on boot via systemd. No action needed after the initial setup and reboot.

```bash
# Check whether the service is running
sudo systemctl status erg

# View live logs
sudo journalctl -u erg -f

# Restart after pulling an update
sudo systemctl restart erg
```

### Manual (development / SSH session)

If you haven't run `install.sh` or want to run it directly:

```bash
uvicorn server:app --host 0.0.0.0 --port 8501 --reload
```

Then open `http://<UNO-Q-IP>:8501` in your browser. To find the IP, run `hostname -I` on the board.

---

## Automatic boot — manual setup

If you prefer to configure the systemd service yourself instead of using `install.sh`:

```bash
# 1. Find where uvicorn is installed
which uvicorn

# 2. Create the service file
sudo tee /etc/systemd/system/erg.service > /dev/null <<EOF
[Unit]
Description=Erg-onomics rowing app
After=network.target bluetooth.target

[Service]
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(which uvicorn) server:app --host 0.0.0.0 --port 8501
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 3. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable erg
sudo systemctl start erg

# 4. Verify
sudo systemctl status erg
```

### Updating the app

```bash
# Pull latest code
git pull

# Restart the service to pick up changes
sudo systemctl restart erg
```

---

## Connecting from iPad / iPhone

| | |
|---|---|
| **WiFi network** | ErgRower |
| **Password** | rowrow12 |
| **URL** | http://10.0.0.1:8501 |

Add to Home Screen in Safari for a full-screen experience (no browser chrome).

---

## Data

All data is stored in `rowing.db` (SQLite) in the working directory. The database is not checked in. Per-stroke data is in `stroke_log`; session summaries in `sessions`. Both are readable by any SQLite tool for custom analysis.

TCX files land in `exports/` and can be imported directly into Garmin Connect or Apple Health via HealthFit.

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

68 tests covering conversion math, workout CRUD, streak calculation, HR zone/Strive Score, PR detection, perfect-stroke streak, and interval state tracking.
