# CLAUDE.md

Guidance for Claude Code when working in this repository.

---

## Primary UI — FastAPI + `static/index.html`

The app is a single-page web app served by FastAPI on port 8501. The entire UI lives in **`static/index.html`** — one HTML file with embedded CSS and JS. No build step, no framework.

```bash
# Run (serves on http://erg.local:8501 or http://10.0.0.1:8501)
uvicorn server:app --host 0.0.0.0 --port 8501
```

The browser polls `/api/state` every 500 ms and re-renders the current screen in-place. This is the only UI that is actively developed.

### Deployment target

**Arduino UNO Q** at IP `192.168.0.224`, port 8501. The app runs as a systemd service (`erg.service`).

```bash
# On the UNO Q — pull + restart in one command:
bash restart.sh

# Verify which commit is live:
curl http://192.168.0.224:8501/api/version
# → {"version":"<git-hash> <date>"}
```

Always verify the live version via `/api/version` before assuming a fix worked or didn't work. Safari caches aggressively; `Cache-Control: no-store` is set on the index route.

### Fallback: Kivy local display

`main.py` + `ui/` are a Kivy app that displays on a screen connected directly to the UNO Q. It shares `ble/pm5.py` and the `db/` layer with the FastAPI app. It is **not** actively developed but is kept as a local-display fallback.

```bash
DISPLAY=:0 python main.py
```

---

## Architecture

### Data flow

```
PM5 (BLE notify)
    │
    ▼
ble/pm5.py  parse_*()          ← mutates shared state dict
    │
    ▼
GET /api/state  (every 500 ms) ← FastAPI reads state dict + computes derived fields
    │
    ▼
tick() in index.html           ← renders current screen in-place
```

`state` is a plain `dict` in `ble/pm5.py` shared across all modules. BLE callbacks mutate it from the asyncio thread; the API/audio threads read it. No locking — reads are cheap and torn values are invisible at polling rates.

BLE runs in a daemon `threading.Thread` calling `asyncio.run(ble_main())`. Never call FastAPI or Kivy APIs directly from BLE callbacks.

### Module map

| Module | Role |
|---|---|
| `server.py` | FastAPI app; all API endpoints; background BLE + audio threads |
| `static/index.html` | Entire web UI — CSS, JS, 6 screens, all rendering |
| `ble/pm5.py` | BLE scan/connect, parse functions, `state` dict, session lifecycle, SQLite init |
| `ble/ftms.py` | FTMS Rower BLE GATT broadcast (bless); silent no-op if bless absent |
| `db/records.py` | Personal records; sliding-window pace PR algorithm |
| `db/strive.py` | Strive Score from HR zone × time; Tanaka max-HR formula |
| `db/streak.py` | Consecutive training-day streak |
| `db/workouts.py` | 10 preset Concept2 workouts + custom workout CRUD |
| `db/training_plan.py` | Weekly plan (day_of_week → workout_id) |
| `db/export.py` | TCX export → `exports/` directory |
| `ui/audio.py` | espeak cues every 500 m or 60 s — **imported by server.py** |
| `ui/app.py` … | Kivy UI modules — fallback only, not actively developed |

### Database

Single SQLite file `rowing.db` (not in git). Schema in `ble/pm5.py _init_db()` using `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE … ADD COLUMN` guards. No migration tool.

Key tables: `sessions`, `stroke_log`, `user_profile`, `records`, `workouts`, `training_plan`.

`stroke_log` has one row per stroke: elapsed, speed, drive/recovery timing, force, HR, watts, peak_avg_ratio. Primary source for all post-session analytics.

### Session lifecycle

1. `POST /api/start` → `start_session()` → inserts `sessions` row (status=`active`)
2. Strokes arrive via BLE → `parse_stroke_data()` → `_log_stroke()` → `stroke_log`
3. `POST /api/end` → `stop_session()` → aggregates → updates `sessions` (status=`complete`) → `check_and_save_records()` → `export_tcx()`
4. Browser navigates to History and calls `showSummary(session_id)`

### SPM smoothing

Inter-stroke intervals → EMA (`_EMA_ALPHA = 0.25`) in `_ema_interval_secs`. `SPM = round(60 / _ema_interval_secs)`. Stale: if last stroke > 10 s ago, SPM → `"--"`.

---

## Web UI — `static/index.html`

### Page structure

Five top-nav tabs: Row · History · Workouts · Plan · Profile.

The **Row tab** (`#page-row`) uses CSS Grid:

```
grid-template-rows: auto auto auto auto 1fr auto
grid-row assignments:
  1 → #resume-prompt   (hidden unless resumable session exists)
  2 → #row-header      (BLE pill, screen dots; hidden during active session)
  3 → #screen-label    (screen name; hidden during active session)
  4 → #target-bar      (target pace indicator; hidden until set)
  5 → #screen-wrap     (1fr — always gets remaining space)
  6 → #session-bar     (slide-up session menu button)
```

`display:none` on a CSS Grid item removes it from layout; its `auto` row collapses to 0. `screen-wrap` always gets `1fr` regardless of which rows above it are visible.

### Six swipeable screens

| # | Name | Hero | Cards | Notes |
|---|---|---|---|---|
| 0 | Power | Watts (tap → Avg Force) | Pace/SPM, SPM/Interval, Strokes/SPM, Dist/Strokes, Time/Drag | |
| 1 | Endurance | HR (tap → Calories) | Pace, Dist, Time | Zone strip, Tanaka max-HR |
| 2 | Technique | — | Drive, Recovery, Ratio, Drive Length, Expected, Delta, Peak Force, Avg Force, Peak/Avg, Drag, SPM | Good/warn/bad colouring |
| 3 | Force Curve | — | Canvas drive curve + streak | Stable DOM: canvas never rebuilt |
| 4 | Intervals | Interval counter | Pace, Dist | Stable DOM: progress bar transitions |
| 5 | Video | — | Angle pills (Catch/Layback/Dr:Rec) | Stable DOM: camera never re-init |

### Stable DOM rule (screens 3, 4, 5)

Screens with stateful elements (canvas, camera, progress bar transitions) must never have their DOM rebuilt on every tick. In `renderScreen()`:

```javascript
if (_screen === N) {
  if (changed) { w.innerHTML = renderXxxHTML(); initXxx(); }
  else          _updateXxxInPlace();   // patch text/style only
  return;
}
```

Screens 0–2 rebuild innerHTML only when `_screen !== _lastScreen` (i.e., on swipe arrival).

### Flip cards

Cards tagged `data-flip="key"` cycle through an alts array on tap. State: `_flip[key]` (integer, increments). Modulo is applied at render time inside `card()` and `heroCard()`. Tapping sets `_lastScreen = -1` to force a re-render.

Do NOT use `JSON.stringify` to store functions in `data-alts` — functions are stripped. The pattern is: increment `_flip[key]`, re-render, let the render function read the alts array fresh.

### Session panel

`#session-panel` is a fixed-position slide-up sheet (not in the page flow). `toggleSessionPanel()` / `closeSessionPanel()` control it. Start/Pause/End/Target Pace/Workout buttons live here. The session bar button label reflects current state: Ready / Recording / Paused.

During an active session, `#row-header` and `#screen-label` are hidden (via `tick()`) to give screen-wrap more space.

---

## PM5 BLE Characteristics

All under service base `XXXXXXXX-43E5-11E4-916C-0800200C9A66`:

| Characteristic | UUID prefix | Parsed fields |
|---|---|---|
| General Status | `CE060031` | elapsed (0.01 s), distance (0.1 m), workout_state |
| Additional Status 1 | `CE060032` | speed_mm_s (bytes 0–1), stroke_state (byte 2), drag_factor (byte 3) |
| Stroke Data | `CE060035` | drive_length, drive_time, recovery, peak/avg force, stroke_distance, work_per_stroke, stroke_count |
| Heart Rate | `CE06003A` | hr_bpm |
| Workout Summary | `CE060039` | (stub — byte layout not yet parsed) |

> **Critical**: PM5 characteristics cannot be `read()` — only `start_notify()`. Direct reads return zeros.

### FTMS Broadcast

Broadcasts live data as FTMS Rower (service `0x1826`, Rower Data `0x2AD1`) every 500 ms so ErgZone and Zwift on iPad can connect via BLE. The UNO Q's BT 5.1 chip handles central (→ PM5) and peripheral (← iPad) simultaneously.

---

## Installing Dependencies

```bash
# Full install — run once after cloning:
bash install.sh

# Manual:
pip install fastapi "uvicorn[standard]" bleak bless
sudo apt install -y python3-dbus python3-gi espeak
sudo usermod -aG bluetooth $USER   # then reboot

# Kivy fallback only:
pip install "kivy[base]"
```

---

## Development Rules

These were established through iteration and must be followed:

1. **One issue per commit.** Don't batch unrelated fixes. If two things are broken, fix them in separate commits with separate messages.

2. **Verify deployment before declaring success.** After pushing, the user must `git pull` + restart on the UNO Q. Check `/api/version` returns the expected hash before assuming a fix works or doesn't work.

3. **No blind CSS tweaks.** When layout is broken, understand WHY before changing values. Document the root cause in the commit message.

4. **Stable DOM for screens 3/4/5.** Never rebuild the canvas, video, or progress-bar DOM on every tick. Only rebuild on screen arrival (`changed === true`).

5. **`static/index.html` is the only UI file.** All web UI changes go here. The Kivy `ui/` modules are fallback-only; don't touch them unless explicitly asked.

6. **Drive length displays in meters** (`0.72m`), not cm. The `state["drive_length"]` field is pre-formatted as `"X.XXm"` by `parse_stroke_data()`.

7. **`_bleConnecting` guard.** Set to `true` before calling `selectErg()`, reset on connected/disconnected. Prevents `selectErg()` firing every 500 ms tick while BLE is connecting.

8. **Ask before making layout changes that affect iPhone Safari.** `100dvh`, `env(safe-area-inset-bottom)`, `-webkit-overflow-scrolling:touch`, and `display:block` on `.page.active` are load-bearing. Test on the actual device.
