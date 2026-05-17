"""
ble/mock.py — Fake PM5 data for offline development.

Set MOCK_BLE=1 env var to start at server launch, or POST /api/demo to
toggle at runtime. Simulates ~24 SPM / 2:10/500m pace with realistic
per-stroke variation so all screens animate as during actual rowing.
"""
import math
import struct
import sys
import threading
import time

from ble.pm5 import (
    _init_db, load_user_profile,
    parse_general_status, parse_add_status_1, parse_stroke_data,
    parse_heart_rate, state,
)

# ── Constants ─────────────────────────────────────────────────────────────────
_SPEED_BASE   = 3846   # 2:10/500m in mm/s
_DRAG         = 127
_DRIVE_CM     = 86
_DRIVE_TICKS  = 60     # * 0.01 s = 0.60 s drive time
_REC_TICKS    = 190    # * 0.01 s = 1.90 s recovery  →  24 SPM
_WORK_J10     = 3975   # 159W × 2.5s stroke ≈ 397.5J → consistent with _SPEED_BASE
_HR_BASE      = 142

_running = False


def _gs(elapsed_cs: int, distance_dm: int, ws: int = 3) -> bytes:
    d = bytearray(7)
    d[0:3] = elapsed_cs.to_bytes(3, 'little')
    d[3:6] = distance_dm.to_bytes(3, 'little')
    d[6]   = ws
    return bytes(d)


def _as1(speed: int, ss: int, drag: int) -> bytes:
    d = bytearray(4)
    struct.pack_into('<H', d, 0, speed)
    d[2] = ss
    d[3] = drag
    return bytes(d)


def _sd(drive_cm, drive_ticks, rec_ticks, stroke_cm2,
        peak_n10, avg_n10, work_j10, count) -> bytes:
    d = bytearray(20)
    d[6] = drive_cm
    d[7] = drive_ticks
    struct.pack_into('<H', d,  8, rec_ticks)
    struct.pack_into('<H', d, 10, stroke_cm2)
    struct.pack_into('<H', d, 12, peak_n10)
    struct.pack_into('<H', d, 14, avg_n10)
    struct.pack_into('<H', d, 16, work_j10)
    struct.pack_into('<H', d, 18, count)
    return bytes(d)


def _hr(bpm: int) -> bytes:
    return bytes([0x00, bpm & 0xFF])


def _mock_loop():
    global _running
    state["ble_status"]     = "connected"
    state["ble_name"]       = "Mock PM5"
    state["session_active"] = True
    state["session_paused"] = False

    t0            = time.monotonic()
    stroke_count  = 0
    next_stroke   = 2.5
    stroke_period = 2.5

    # Per-stroke varying targets (updated at each stroke event)
    stroke_speed  = _SPEED_BASE   # target speed for current stroke

    while state.get("demo_active"):
        try:
            elapsed    = time.monotonic() - t0
            elapsed_cs = round(elapsed * 100)
            dist_dm    = round(elapsed * (_SPEED_BASE / 1000) * 10)

            # Phase within the current stroke cycle
            phase = elapsed % stroke_period

            if phase < 0.60:
                ss    = 1                         # drive
                speed = stroke_speed + 600        # surge during drive
            elif phase < 0.80:
                ss    = 2                         # decelerate
                speed = stroke_speed - 200
            else:
                ss    = 3                         # recovery
                speed = stroke_speed - 400

            speed = max(500, speed)

            parse_general_status(_gs(elapsed_cs, dist_dm))
            parse_add_status_1(_as1(speed, ss, _DRAG))

            if elapsed >= next_stroke:
                stroke_count += 1
                n = stroke_count

                # Force values vary realistically per stroke
                peak_n10 = 2800 + round(400 * math.sin(n * 0.83))
                avg_n10  = 1950 + round(200 * math.sin(n * 0.61))
                drive_cm = _DRIVE_CM + round(4 * math.sin(n * 1.1))
                stroke_cm2 = 960 + round(40 * math.sin(n * 0.5))

                parse_stroke_data(_sd(
                    drive_cm, _DRIVE_TICKS, _REC_TICKS, stroke_cm2,
                    peak_n10, avg_n10, _WORK_J10, n,
                ))
                if n % 2 == 0:
                    parse_heart_rate(_hr(_HR_BASE + n % 8))

                # Next stroke's speed target varies around baseline
                stroke_speed = _SPEED_BASE + round(300 * math.sin(n * 1.37))
                next_stroke += stroke_period

        except Exception as e:
            print(f"[mock] {e}", file=sys.stderr)

        time.sleep(0.2)

    # Teardown
    state["session_active"] = False
    state["ble_status"]     = "scanning"
    state["ble_name"]       = None
    _running = False


def start_mock():
    """Start mock PM5 thread. Safe to call multiple times — no-ops if already running."""
    global _running
    if _running:
        return
    _running = True
    _init_db()
    load_user_profile()
    state["demo_active"] = True
    threading.Thread(target=_mock_loop, daemon=True, name="mock-pm5").start()
