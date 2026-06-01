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

## Metrics

### BLE Data Sources

The PM5 pushes data on three notify-only characteristics (reads return zeros):

| Characteristic | UUID prefix | Rate | Fields |
|---|---|---|---|
| General Status | `CE060031` | ~1 Hz | elapsed time, distance, workout state |
| Additional Status 1 | `CE060032` | ~5 Hz | instantaneous speed, stroke state, drag factor |
| Stroke Data | `CE060035` | once per stroke | drive/recovery timing, forces, work, stroke count |
| Force Curve | `CE06003D` | 18 packets/stroke | one force sample per packet (Newtons) |
| Heart Rate | `CE06003A` | on change | HR from paired ANT+ strap |

### Computed Metrics

| Metric | Source | How |
|---|---|---|
| **Pace** | CE060035 | `stroke_period / stroke_distance_m × 500` — 3-stroke rolling average |
| **Watts** | CE060035 | `2.80 / (pace_sec / 500)³` — Concept2 standard formula |
| **SPM** | CE060035 | `60 / stroke_period` — 3-stroke rolling average; `--` if last stroke > 10 s ago |
| **Cal/hr** | derived | `4 × current_watts + 300` |
| **Calories** | derived | `(4 × avg_watts + 300) × elapsed / 3600` |
| **Avg pace / watts** | session | `elapsed × 500 / distance` and watts formula applied to avg pace |
| **Drive:Rec ratio** | CE060035 | `drive_time / recovery_time` |
| **Peak/Avg force ratio** | CE060035 | `avg_force_n / peak_force_n` |

### Sample Stroke (demo mode, ~24 SPM / 2:10 pace)

Below is a representative snapshot of `state` after one complete stroke:

**CE060031 — General Status** (1 Hz)
```
elapsed_cs:    1250   →  12.50 s
distance_dm:   480    →  48.0 m
workout_state: 3      (in-use)
```

**CE060032 — Additional Status 1** (5 Hz, three packets per stroke)
```
speed_mm_s:   4446   (drive surge: +600 over baseline)
              3646   (decelerate:  −200)
              3446   (recovery:    −400)
stroke_state: 1 / 2 / 3   (drive / decel / recovery)
drag_factor:  127
```

**CE060035 — Stroke Data** (once per stroke)
```
drive_length:   86 cm     →  state["drive_length"]  = "0.86m"
drive_time:     60 ticks  →  state["drive_time"]    = "0.60s"
recovery:      190 ticks  →  state["recovery"]      = "1.90s"
stroke_distance: 960 cm²  →  9.60 m
peak_force:    2800 /10   →  280.0 N
avg_force:     1950 /10   →  195.0 N
work/stroke:   3975 /10   →  397.5 J
stroke_count:  5
```

**Derived from stroke data**
```
stroke_period  = 0.60 + 1.90 = 2.50 s
pace           = 2.50 / 9.60 × 500 = 130.2 s  →  "2:10"
watts          = 2.80 / (130.2 / 500)³         →  159 W
spm            = round(60 / 2.50)              →  24
dr:rec ratio   = 0.60 / 1.90                   →  0.32
```

**CE06003D — Force Curve** (18 samples per stroke, in Newtons)
```
index:  0     1     2     3     4     5     6     7  …  17
force:  0.0  52.5 168.0 252.0 280.0 241.5 189.0 140.0 … 0.0
              ↑ ramp up        ↑ peak         ↑ decay tail
```

**Server-derived fields (api_state)**
```
elapsed_str:  "0:12"
distance_str: "48 m"
avg_pace:     "2:10"
avg_watts:    159
cal_hr:       936    (4 × 159 + 300)
calories:     3      (936 × 12.5 / 3600)
```

**What each Row screen shows at this moment**

| Screen | Hero | Key cards |
|---|---|---|
| Power (0) | 159 W | 2:10 pace · 24 SPM · 48 m · 0:12 elapsed · 936 cal/hr |
| Endurance (1) | -- bpm | 2:10 · 159 W · 48 m |
| Technique (2) | — | 0.60 s drive · 1.90 s rec · ratio 0.32 · 0.86 m length |
| Force Curve (3) | canvas | peak 280 N · avg 195 N · P/A ratio 0.70 |
| Stroke Timing (4) | ratio bar | 0.60 s · 1.90 s · 0.32 |

---

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
