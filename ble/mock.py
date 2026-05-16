"""
ble/mock.py — Fake PM5 data for offline development.

Set MOCK_BLE=1 env var to start this instead of real BLE.
Simulates ~24 SPM / 2:10/500m pace by calling the same parse_*
functions as live BLE callbacks — all server.py logic works unchanged.
"""
import struct
import threading
import time

from ble.pm5 import (
    _init_db, load_user_profile,
    parse_general_status, parse_add_status_1, parse_stroke_data,
    parse_heart_rate, state,
)

# ── Realistic constants ───────────────────────────────────────────────────────
_SPEED_MM_S  = 3846   # 2:10 / 500m
_DRAG        = 127
_DRIVE_CM    = 86     # drive length
_DRIVE_TICKS = 60     # * 0.01 s = 0.60 s
_REC_TICKS   = 190    # * 0.01 s = 1.90 s  →  2.50 s/stroke → 24 SPM
_PEAK_N10    = 2800   # peak force * 10
_AVG_N10     = 1950   # avg  force * 10
_STROKE_CM2  = 960    # stroke distance * 100 = 9.60 m
_WORK_J10    = 2450   # work per stroke * 10
_HR_BASE     = 142


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
    state["ble_status"] = "connected"
    state["ble_name"]   = "Mock PM5"

    t0           = time.monotonic()
    stroke_count = 0
    next_stroke  = 2.5          # seconds until first stroke event
    stroke_period = 2.5         # seconds per stroke at 24 SPM

    while True:
        elapsed    = time.monotonic() - t0
        elapsed_cs = round(elapsed * 100)
        dist_m     = elapsed * (_SPEED_MM_S / 1000)
        dist_dm    = round(dist_m * 10)

        # Drive for first 0.60 s of each 2.50 s cycle
        ss = 1 if (elapsed % stroke_period) < 0.60 else 3

        parse_general_status(_gs(elapsed_cs, dist_dm))
        parse_add_status_1(_as1(_SPEED_MM_S, ss, _DRAG))

        if elapsed >= next_stroke:
            stroke_count += 1
            parse_stroke_data(_sd(
                _DRIVE_CM, _DRIVE_TICKS, _REC_TICKS, _STROKE_CM2,
                _PEAK_N10, _AVG_N10, _WORK_J10, stroke_count,
            ))
            if stroke_count % 2 == 0:
                parse_heart_rate(_hr(_HR_BASE + stroke_count % 6))
            next_stroke += stroke_period

        time.sleep(0.2)


def start_mock():
    """Start mock PM5 thread. Call instead of start_ble() when MOCK_BLE=1."""
    _init_db()
    load_user_profile()
    threading.Thread(target=_mock_loop, daemon=True, name="mock-pm5").start()
