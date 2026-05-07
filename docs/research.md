# Concept2 Pi Rowing App — Technical Research Report

## Bottom Line Up Front

**Recommended stack:** `bleak` (Python BLE) + `Kivy` (UI) + `SQLite` (storage)  
**Platform:** Arduino Uno Q (4GB variant), Debian Linux on MPU  
**Display:** Waveshare 7" Capacitive Touch Screen LCD (H), 1024×600, HDMI + USB touch  
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
- Works on Debian Linux via BlueZ backend
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
        await asyncio.sleep(3600)

asyncio.run(run())
```

---

## 3. Arduino Uno Q Hardware

### Architecture — Dual Processor

The Uno Q has two independent processors on one board:

| Processor | Chip | Role |
|---|---|---|
| **MPU** | Qualcomm Dragonwing QRB2210, 4× Cortex-A53 @ 2.0 GHz | Runs Debian Linux, Python, Kivy, bleak |
| **MCU** | ST STM32U585, Cortex-M33 @ 160 MHz | Zephyr RTOS, Arduino sketches, real-time I/O |

This app lives entirely on the MPU side (Linux + Python). The MCU is available for future real-time sensor work if needed, with a Bridge library for inter-processor communication.

### Memory & Storage

| Variant | RAM | Storage |
|---|---|---|
| ABX00162 | 2 GB | 16 GB |
| **ABX00173 (recommended)** | **4 GB** | **32 GB** |

### Connectivity
- **Bluetooth 5.1** (WCBN3536A module, dedicated antenna — no sharing with WiFi)
- **WiFi 5** dual-band 2.4/5 GHz (separate from BT, no interference)

### OS
- MPU: **Debian Linux** (64-bit, upstream kernel support)
- No custom OS image required — standard Debian package ecosystem

### RAM Budget at Runtime

| Component | RAM Usage |
|---|---|
| Debian base | ~300MB |
| Kivy app | ~80–100MB |
| bleak + asyncio | ~20MB |
| SQLite | ~5MB |
| **Total** | **~405–425MB** |
| **Available headroom (4GB variant)** | **~3.6GB** |

No memory pressure at all. The WiFi/BT antenna sharing issue from Pi 3B does not exist here.

---

## 4. Waveshare 7" Capacitive Touch Screen LCD (H)

### Specs
- **Resolution:** 1024×600
- **Panel:** IPS, 170° viewing angle
- **Touch:** 5-point capacitive, USB HID (driver-free on Linux)
- **Video input:** HDMI
- **Audio:** 3.5mm jack + 24-pin header

### Connection to Arduino Uno Q
- HDMI out → display HDMI in
- USB (touch) → any USB port on the Uno Q
- No kernel drivers or overlays needed; Linux auto-detects both

### Driver Setup (Linux)
No driver installation required. Touch is a standard USB HID device. If HDMI resolution doesn't auto-negotiate to 1024×600, force it:

```bash
# /etc/X11/xorg.conf.d/99-waveshare.conf
Section "Monitor"
    Identifier "HDMI-1"
    Modeline "1024x600_60" 49.00 1024 1072 1168 1312 600 603 613 624 -hsync +vsync
    Option "PreferredMode" "1024x600_60"
EndSection
```

---

## 5. UI Framework: Kivy (Recommended)

### Why Kivy

| Framework | RAM | Touch | Looks Modern | Uno Q Safe |
|---|---|---|---|---|
| Pygame | ~30MB | Manual | No | ✓ |
| **Kivy** | **~80MB** | **Native** | **Yes** | **✓** |
| PyQt5 | ~120MB | Native | Yes | ✓ |
| Electron | ~400MB+ | Native | Yes | ✓ (unlike Pi 3B) |
| Flask + Chromium | ~500MB+ | Native | Yes | ✓ (unlike Pi 3B) |

With 4GB RAM the Uno Q can handle any of these, but Kivy remains the cleanest fit for a touch-first kiosk app with Python.

### Installation on Uno Q (Debian)

```bash
sudo apt-get install -y python3-pip python3-kivy
# Or via pip for newer version:
pip3 install kivy[base]
```

### Kivy + bleak Integration Pattern

BLE runs in a background asyncio thread. Kivy's `Clock` polls shared state at 2Hz — no blocking, no threading issues.

```python
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.label import Label
import asyncio, threading

state = {"pace": "--:--", "spm": 0, "watts": 0, "distance": 0}

def ble_thread():
    asyncio.run(ble_main())

class RowingApp(App):
    def build(self):
        self.label = Label(text="Connecting...")
        Clock.schedule_interval(self.update_ui, 0.5)
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

## 6. App Architecture

### Data Flow

```
PM5 (BLE)
    │ notify callbacks (~2Hz)
    ▼
bleak async loop (background thread, MPU)
    │ writes to shared `state` dict
    ▼
Kivy Clock (0.5s interval, MPU)
    │ reads from `state` dict
    ▼
Kivy UI — 1024×600 on Waveshare LCD (HDMI)
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
    type: Literal["time", "distance"]
    value: int                          # seconds or meters
    rest_type: Literal["time", "button"]
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
```

### SQLite Schema

```sql
CREATE TABLE workouts (
    id INTEGER PRIMARY KEY,
    name TEXT,
    definition JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    workout_id INTEGER REFERENCES workouts(id),
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_distance REAL,
    total_time INTEGER,
    avg_pace REAL,
    avg_watts REAL,
    avg_spm REAL,
    max_watts INTEGER,
    calories INTEGER,
    raw_data JSON
);
```

---

## 7. Custom Workout Builder — Features

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

## 8. Development Roadmap

### Phase 1 — Live Data Display (MVP)
**Goal:** Connect to PM5, show pace, SPM, watts, distance, elapsed time on screen  
**Hours:** ~20–25 hrs

- [ ] Set up Debian, Kivy, bleak environment on Uno Q
- [ ] BLE scan and auto-connect to PM5 (BT 5.1)
- [ ] Parse General Status + Additional Status 1 characteristics
- [ ] Basic full-screen Kivy layout with large metrics (1024×600)
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

## 9. Uno Q Setup Checklist

```bash
# 1. Flash Debian Linux image via Arduino Uno Q Imager tool
#    (or follow Arduino's official Getting Started guide)

# 2. Connect display: HDMI cable → Waveshare LCD, USB cable → USB port (touch)

# 3. SSH in, install dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-kivy bluetooth bluez

# 4. Install Python packages
pip3 install bleak

# 5. Verify BLE (BT 5.1 — no experimental flag needed)
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
python3 -c "import asyncio; from bleak import BleakScanner; asyncio.run(BleakScanner.discover(timeout=10))"

# 6. Force display resolution if HDMI doesn't auto-detect 1024×600
# Create /etc/X11/xorg.conf.d/99-waveshare.conf (see Section 4)

# 7. Kiosk boot — auto-launch app on startup
# /etc/systemd/system/rowing.service:
# [Service]
# ExecStart=/usr/bin/python3 /home/user/erg-onomics/main.py
# Environment=DISPLAY=:0
# Restart=always
# [Install]
# WantedBy=graphical.target
sudo systemctl enable rowing

# 8. Test BLE discovery
python3 -c "import asyncio; from bleak import BleakScanner; asyncio.run(BleakScanner.discover(timeout=10))"
```

---

## Sources

- [Arduino Uno Q Official Page](https://www.arduino.cc/product-uno-q/)
- [Arduino Uno Q Documentation](https://docs.arduino.cc/hardware/uno-q/)
- [Concept2 Developer Page](https://www.concept2.com/support/software-development)
- [PM5 BLE Interface Definition](http://www.concept2.cn/files/pdf/us/monitors/PM5_BluetoothSmartInterfaceDefinition.pdf)
- [ergarcade/pm5-base (GitHub)](https://github.com/ergarcade/pm5-base)
- [pROWess — bleak reference (GitHub)](https://github.com/janick/pROWess)
- [openrowingmonitor (GitHub)](https://github.com/laberning/openrowingmonitor)
- [bleak BLE library (GitHub)](https://github.com/hbldh/bleak)
- [Waveshare 7" Capacitive Touch LCD (H)](https://www.waveshare.com/7inch-hdmi-lcd-h.htm)
- [Waveshare Wiki](https://www.waveshare.com/wiki/7inch_HDMI_LCD_(H)_(with_case))
