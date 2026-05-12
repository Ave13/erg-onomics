# Data Streaming — Keeping the UI Live Per Stroke

## Goal

Every metric on screen should reflect the most recent stroke within one polling cycle. No value should freeze, flicker, or animate incorrectly because of how the UI renders.

---

## Data Flow

```
PM5 (BLE notify)
    │
    ▼
ble/pm5.py  parse_stroke_data()        ← fires once per stroke (~20–40 strokes/min)
ble/pm5.py  parse_general_status()     ← fires every ~100 ms (elapsed, distance, speed)
ble/pm5.py  parse_additional_status()  ← fires every ~100 ms (drag, stroke_state)
    │
    ▼  mutates
state dict  (shared, no lock — BLE thread writes, API thread reads)
    │
    ▼  polled
GET /api/state  (browser, every 500 ms)
    │
    ▼  renders
static/index.html  tick() → renderScreen()
```

### What updates per stroke

`parse_stroke_data()` is the per-stroke callback. It updates:

| Field | Type | Notes |
|---|---|---|
| `drive_time_secs` | float | seconds |
| `recovery_secs` | float | seconds |
| `drive_length_cm_raw` | float | raw cm |
| `drive_length` | str | formatted, e.g. `"135cm"` |
| `drive_time` | str | formatted, e.g. `"0.72s"` |
| `recovery` | str | formatted, e.g. `"1.13s"` |
| `peak_force_n` | float | Newtons |
| `avg_force_n` | float | Newtons |
| `stroke_count` | int | cumulative |
| `spm` | int | EMA-smoothed (`_EMA_ALPHA = 0.25`) |
| `perfect_streak` | int | consecutive perfect strokes |
| `perfect_streak_best` | int | session best streak |
| `pace` | str | formatted `/500m` |
| `watts` | int | `round(2.80 / (pace_sec/500)**3)` |

### What updates continuously (between strokes)

`parse_general_status()` fires ~10×/s and updates `elapsed`, `distance`, `speed_mm_s`, `workout_state`.

---

## API State — Computed Fields

`GET /api/state` adds these on top of the raw state dict:

| Field | Computation |
|---|---|
| `pace_sec` | `round(500_000 / speed_mm_s)` — numeric seconds per 500m; `None` when stopped |
| `elapsed_str` | `"M:SS"` formatted from `elapsed` |
| `distance_str` | `f"{distance:.0f}"` metres |
| `pace_color` | `"green"` / `"red"` / `""` vs `target_pace_sec` |
| `interval_total` | count of intervals in active workout |
| `spm` | `None` if not int (stale guard) |
| `hr_bpm` | `None` if not int |

---

## Render Rules

The browser rebuilds screen HTML every 500 ms. Two screens are exceptions — they keep a stable DOM and update in-place to avoid destroying stateful elements.

### Stable screens (DOM built once per arrival)

| Screen | Why stable | In-place update |
|---|---|---|
| **Screen 3 — Force Curve** | `<canvas>` loses its drawn content if the element is destroyed | `drawForce()` called each tick via `requestAnimationFrame`; streak numbers patched via `fc-streak-num` / `fc-streak-best` |
| **Screen 4 — Intervals** | Progress bar has `transition: width 0.5s`; rebuilding the element resets the transition to instant | `_updateIntervalsInPlace()` patches `iv-idx`, `iv-of`, `iv-phase`, `iv-bar`, `iv-rem` each tick |

### Screens that rebuild each tick (acceptable)

Power, Endurance, Technique — no canvas, no transitions that need continuity.

---

## Canvas Sizing

`drawForce()` uses `getBoundingClientRect()` inside a `requestAnimationFrame` callback. This is the only reliable way to get real pixel dimensions:

- `canvas.offsetWidth` is `0` before the first paint.
- `clientWidth` on a flex child can be wrong before layout.
- `getBoundingClientRect()` is correct after layout, which has happened by the time rAF fires.

If dimensions are still `< 10px` (layout not ready), `drawForce` re-queues itself:

```js
if (W < 10 || H < 10) { requestAnimationFrame(drawForce); return; }
```

---

## BLE Connection State Machine

`ble_status` transitions: `scanning` → `found` → `connecting` → `connected` → `disconnected` → `scanning`.

The browser guards against calling `selectErg()` (which POSTs `/api/ble/connect`) on every tick while status is `found`. The `_bleConnecting` flag is set on first call and cleared when status becomes `connected` or `disconnected`.

---

## Adding a New Live Metric

1. **BLE side** — update `parse_stroke_data()` or `parse_general_status()` in `ble/pm5.py`. Add the field to the `state` dict initialisation at the top of `pm5.py`.

2. **API side** — if it needs formatting or computation, add it to the `api_state()` block in `server.py` (same place as `pace_sec`, `elapsed_str`, etc.).

3. **UI side** — add an alt to one of the `alts_*()` functions in `index.html`, or add a new `mc()` cell to the relevant `renderX()` function. If the metric belongs on a stable screen (3 or 4), also update `_updateIntervalsInPlace()` or the force-curve in-place block.

4. **Never** call `renderScreen()` or set `innerHTML` from inside a `requestAnimationFrame` callback — this destroys the stable DOM on the next frame before the browser paints it.
