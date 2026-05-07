# Concept2 Pi Rowing App — Technical Research Report

## Bottom Line Up Front

**Recommended stack:** `bleak` (Python BLE) + `Kivy` (UI) + `SQLite` (storage)  
**Platform:** Raspberry Pi 3B, 32-bit Raspberry Pi OS Bookworm, 7" touchscreen  
**Estimated build time:** 85–120 hours across 4 phases  

---

## 1. Concept2 PM5 BLE Protocol

### Service UUID Base
All PM5 BLE services share the base: `XXXXXXXX-43E5-11E4-916C-0800200C9A66`

### Key Services

| Service | UUID Prefix | Description |
|---|---|---|
| Device Info | `CE060010` | Firmware version, serial number |
| Control | `CE060020` | Send commands to PM5 |
| **Rowing** | `CE060030` | **All live workout data** |
| Discovery | `CE060040` | PM5 discovery/pairing |

### Critical Rowing Characteristics (all under CE060030)

| Characteristic | UUID | Data | Notify Rate |
|---|---|---|---|
| General Status | `CE060031` | Distance, workout state, elapsed time, workout type | ~500ms |
| Additional Status 1 | `CE060032` | Stroke rate (spm), speed (mm/s), stroke count, avg pace | ~500ms |
| Additional Status 2 | `CE060033` | Interval count, rest time | ~500ms |
| Stroke Data | `CE060035` | Per-stroke drive/recovery time, power | Per stroke |
| Heart Rate | `CE06003A` | Heart rate (bpm) | ~1s |
| Workout Summary | `CE060039` | End-of-workout totals | On complete |

### ⚠️ Critical Gotcha
**You cannot `read()` PM5 characteristics.** Direct GATT reads return zeros or stale data.  
Every data characteristic must be subscribed via `start_notify()`.

### Data Calculations

```python
# Speed from PM5 is in mm/s — convert to pace (min/500m)
def speed_to_pace(speed_mm_s):
    if speed_mm_s == 0:
        return None
    speed_m_s = speed_mm_s / 1000
    pace_sec_per_500m = 500 / speed_m_s
    mins = int(pace_sec_per_500m // 60)
    secs = int(pace_sec_per_500m % 60)
    return f"{mins}:{secs:02d}"

# Watts from pace
def pace_to_watts(pace_sec_per_500m):
    if pace_sec_per_500m == 0:
        return 0
    pace_min = pace_sec_per_500m / 60
    return round(2.80 / (pace_min ** 3))
```

### Official Resources
- [Concept2 Developer Page](https://www.concept2.com/support/software-development)
- [PM5 BLE Interface Definition PDF](http://www.concept2.cn/files/pdf/us/monitors/PM5_BluetoothSmartInterfaceDefinition.pdf)

---

## 2. Best Available Libraries

### Recommended: `bleak` (Python)

```bash
pip install bleak
```

- Actively maintained (2024 commits), 4.2k GitHub stars
- Works on Raspberry Pi OS via BlueZ backend
- Full async/await — integrates cleanly with asyncio event loop
- Best BLE library for Python on Linux

### Reference Implementation: `ergarcade/pm5-base`

```bash
pip install pm5  # or clone from github.com/ergarcade/pm5-base
```

- Purpose-built for Concept2 PM5 over BLE
- Handles UUID mapping, byte parsing, and state machine
- Good starting reference even if you rewrite from scratch

### Other Notable Projects
- **pROWess** (github.com/janick/pROWess) — Pi + bleak + Concept2, active project, reference for async patterns
- **openrowingmonitor** (github.com/laberning/openrowingmonitor) — more complex, connects via ANT+/BLE, good architecture reference
- **raralabs/pm5-emulator** — useful for development without the rower physically present

### Minimal bleak Connection Example

```python
import asyncio
from bleak import BleakClient, BleakScanner

ROWING_STATUS_UUID = "CE060031-43E5-11E4-916C-0800200C9A66"
ADD_STATUS_UUID    = "CE060032-43E5-11E4-916C-0800200C9A66"

def parse_general_status(data: bytearray):
    elapsed_time = int.from_bytes(data[0:3], 'little') / 100  # seconds
    distance     = int.from_bytes(data[3:6], 'little') / 10   # meters
    workout_state = data[6]   # 0=idle, 1=countdown, 2=rowing, 3=paused
    return elapsed_time, distance, workout_state

def parse_add_status_1(data: bytearray):
    speed_mm_s   = int.from_bytes(data[0:2], 'little')
    stroke_rate  = data[3]    # strokes per minute
    stroke_count = int.from_bytes(data[4:6], 'little')
    return speed_mm_s, stroke_rate, stroke_count

async def run():
    # Scan for PM5
    devices = await BleakScanner.discover(timeout=10)
    pm5 = next((d for d in devices if d.name and "PM5" in d.name), None)
    if not pm5:
        print("No PM5 found")
        return

    async with BleakClient(pm5.address) as client:
        await client.start_notify(ROWING_STATUS_UUID,
            lambda s, d: print(parse_general_status(d)))
        await client.start_notify(ADD_STATUS_UUID,
            lambda s, d: print(parse_add_status_1(d)))
        await asyncio.sleep(3600)  # run for 1 hour

asyncio.run(run())
```

---

## 3. Raspberry Pi 3B Constraints

### Hardware
- CPU: ARM Cortex-A53 quad-core 1.2GHz
- RAM: 1GB LPDDR2
- Bluetooth: BCM43438 — BLE 4.1 ✓
- **⚠️ WiFi and Bluetooth share the same antenna** — disable WiFi if BLE drops

### OS Recommendation
**32-bit Raspberry Pi OS Bookworm** (not 64-bit)
- Saves ~66MB RAM vs 64-bit build — critical on 1GB
- Full package support
- Use Raspberry Pi Imager → Raspberry Pi OS (32-bit)

### BLE Reliability Fixes

```bash
# /etc/bluetooth/main.conf — add these lines
[Policy]
AutoEnable=true

# Enable experimental features (required for some BLE notifications)
# Edit /lib/systemd/system/bluetooth.service
# Change: ExecStart=/usr/lib/bluetooth/bluetoothd
# To:     ExecStart=/usr/lib/bluetooth/bluetoothd --experimental

sudo systemctl daemon-reload
sudo systemctl restart bluetooth

# Disable WiFi to prevent interference
sudo rfkill block wifi
# Or permanently in /boot/config.txt:
# dtoverlay=disable-wifi
```

### RAM Budget at Runtime

| Component | RAM Usage |
|---|---|
| Pi OS base | ~200MB |
| Kivy app | ~80–100MB |
| bleak + asyncio | ~20MB |
| SQLite | ~5MB |
| **Total** | **~305–325MB** |
| **Available headroom** | **~675MB** |

Chromium kiosk mode alone uses 400MB+ — ruled out for Pi 3B.

### Screen Recommendation
- **Official 7" Pi Touchscreen** (800×480) — plug-and-play, DSI connector, no config needed. ~$60–80.
- **Waveshare 7" HDMI** — 1024×600, HDMI + USB touch, more resolution. ~$55.
- Avoid screens requiring manual kernel drivers.

---

## 4. UI Framework: Kivy (Recommended)

### Why Kivy

| Framework | RAM | Touch | Looks Modern | Pi 3B Safe |
|---|---|---|---|---|
| Pygame | ~30MB | Manual | No | ✓ |
| **Kivy** | **~80MB** | **Native** | **Yes** | **✓** |
| PyQt5 | ~120MB | Native | Yes | Marginal |
| Electron | ~400MB+ | Native | Yes | ✗ |
| Flask + Chromium | ~500MB+ | Native | Yes | ✗ |

### Installation on Pi

```bash
sudo apt-get install -y python3-kivy
# Or via pip (slower but newer version):
pip install kivy[base] kivy_examples
```

### Kivy + bleak Integration Pattern

BLE runs in a background asyncio thread. Kivy's `Clock` polls shared state at 2Hz for UI updates — no blocking, no threading issues.

```python
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.label import Label
import asyncio, threading

# Shared state dict — written by BLE thread, read by Kivy
state = {"pace": "--:--", "spm": 0, "watts": 0, "distance": 0}

def ble_thread():
    asyncio.run(ble_main())  # runs your bleak code

class RowingApp(App):
    def build(self):
        self.label = Label(text="Connecting...")
        Clock.schedule_interval(self.update_ui, 0.5)  # 2Hz
        threading.Thread(target=ble_thread, daemon=True).start()
        return self.label

    def update_ui(self, dt):
        self.label.text = (
            f"Pace: {state['pace']}\n"
            f"SPM:  {state['spm']}\n"
            f"Watts:{state['watts']}\n"
            f"Dist: {state['distance']}m"
        )

RowingApp().run()
```

---

## 5. App Architecture

### Data Flow

```
PM5 (BLE) 
    │ notify callbacks (~2Hz)
    ▼
bleak async loop (background thread)
    │ writes to shared `state` dict
    ▼
Kivy Clock (0.5s interval)
    │ reads from `state` dict
    ▼
Kivy UI (updates labels/graphs)
    │
    ▼
SQLite (writes on workout complete)
```

### Workout State Machine

```
IDLE ──[row detected]──► ACTIVE
  ▲                         │
  │                    [stop/pause]
  │                         ▼
  │                      PAUSED
  │                         │
  │                    [resume or rest]
  │                         ▼
  │                       REST ──[timer done]──► ACTIVE (next interval)
  │                         │
  └──────[workout done]─────┘
                             │
                          COMPLETE ──► save to SQLite
```

### Custom Workout Data Model

```python
from dataclasses import dataclass, field
from typing import List, Literal
import json

@dataclass
class Interval:
    type: Literal["time", "distance"]  # "time" or "distance"
    value: int                          # seconds or meters
    rest_type: Literal["time", "button"] # fixed rest or button-press
    rest_seconds: int = 0
    target_pace_secs: int = 0          # 0 = no target
    target_watts: int = 0              # 0 = no target

@dataclass
class Workout:
    name: str
    intervals: List[Interval] = field(default_factory=list)
    warmup_seconds: int = 0
    cooldown_seconds: int = 0

    def to_json(self) -> str:
        return json.dumps(self.__dict__, default=lambda o: o.__dict__)

# Example: 4 × 500m with 2:00 rest
workout = Workout(
    name="4x500m Classic",
    intervals=[
        Interval(type="distance", value=500, rest_type="time", rest_seconds=120)
        for _ in range(4)
    ]
)

# Example: 8 × 1min on / 20sec off
workout2 = Workout(
    name="8x1min Intervals",
    intervals=[
        Interval(type="time", value=60, rest_type="time", rest_seconds=20)
        for _ in range(8)
    ]
)
```

### SQLite Schema

```sql
CREATE TABLE workouts (
    id INTEGER PRIMARY KEY,
    name TEXT,
    definition JSON,    -- full Workout object as JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    workout_id INTEGER REFERENCES workouts(id),
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_distance REAL,
    total_time INTEGER,   -- seconds
    avg_pace REAL,        -- sec/500m
    avg_watts REAL,
    avg_spm REAL,
    max_watts INTEGER,
    calories INTEGER,
    raw_data JSON         -- full stroke-by-stroke data
);
```

---

## 6. Custom Workout Builder — Features

### Must Have (Phase 3)
- Create intervals: time-based or distance-based
- Set rest: fixed duration or "press to start next"
- Set target pace or target watts per interval (shown as reference line)
- Alert when more than ±5 sec/500m off target (color flash)
- Save/load workout presets
- Drag to reorder intervals
- Duplicate interval

### Built-In Preset Workouts (ship with app)
- 30-minute steady state
- 4 × 500m / 2:00 rest
- 8 × 1:00 / 0:20 rest
- 2K time trial
- 5K time trial
- Pyramid: 1:00 / 2:00 / 3:00 / 2:00 / 1:00

---

## 7. Development Roadmap

### Phase 1 — Live Data Display (MVP)
**Goal:** Connect to PM5, show pace, SPM, watts, distance, elapsed time on screen  
**Hours:** ~20–25 hrs

- [ ] Set up Pi OS, Kivy, bleak environment
- [ ] BLE scan and auto-connect to PM5
- [ ] Parse General Status + Additional Status 1 characteristics
- [ ] Basic full-screen Kivy layout with large metrics
- [ ] Auto-reconnect on BLE drop

### Phase 2 — Basic Workout Timer
**Goal:** Start/stop rowing session, show countdown, save result  
**Hours:** ~15–20 hrs

- [ ] Detect workout state from PM5 (idle/rowing/paused)
- [ ] Simple session timer with start/stop
- [ ] End-of-session summary screen
- [ ] SQLite: save session data

### Phase 3 — Custom Workout Builder
**Goal:** Build, save, and execute custom interval workouts  
**Hours:** ~30–40 hrs

- [ ] Workout definition data model
- [ ] Workout builder UI (add/remove/reorder intervals)
- [ ] Interval state machine (active → rest → next interval)
- [ ] Target pace/watts overlay during workout
- [ ] Deviation alert (color flash when off target)
- [ ] Save/load workout presets
- [ ] Countdown to next interval display

### Phase 4 — History & Export
**Goal:** View past sessions, export to CSV/ErgData  
**Hours:** ~15–20 hrs

- [ ] Session history list view
- [ ] Session detail: pace graph over time
- [ ] Export to CSV (compatible with CTC/rowsandall)
- [ ] Optional: Concept2 Logbook API upload

**Total: ~80–105 hours**

---

## 8. Pi Setup Checklist

```bash
# 1. Flash Pi OS 32-bit Bookworm via Raspberry Pi Imager

# 2. Enable SSH, set hostname, WiFi (temporarily for install)

# 3. Install dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-kivy bluetooth bluez

# 4. Install Python packages
pip3 install bleak pm5

# 5. Fix BLE — enable experimental mode
sudo nano /lib/systemd/system/bluetooth.service
# Add --experimental to ExecStart line
sudo systemctl daemon-reload && sudo systemctl restart bluetooth

# 6. Disable WiFi (after setup complete)
sudo rfkill block wifi

# 7. Kiosk boot — auto-launch app on startup
# Add to /etc/rc.local before exit 0:
# su -l pi -c "DISPLAY=:0 python3 /home/pi/rowing_app/main.py &"

# 8. Test BLE discovery
python3 -c "import asyncio; from bleak import BleakScanner; asyncio.run(BleakScanner.discover(timeout=10))"
```

---

## Sources

- [Concept2 Developer Page](https://www.concept2.com/support/software-development)
- [PM5 BLE Interface Definition](http://www.concept2.cn/files/pdf/us/monitors/PM5_BluetoothSmartInterfaceDefinition.pdf)
- [ergarcade/pm5-base (GitHub)](https://github.com/ergarcade/pm5-base)
- [pROWess — Pi + bleak reference (GitHub)](https://github.com/janick/pROWess)
- [openrowingmonitor (GitHub)](https://github.com/laberning/openrowingmonitor)
- [bleak BLE library (GitHub)](https://github.com/hbldh/bleak)
- [Kivy for Pi Touchscreen (element14)](https://community.element14.com/products/raspberry-pi/b/blog/posts/essential-raspberry-pi-peripherals-3-the-kivy-framework-for-small-display-and-touch-screens)
