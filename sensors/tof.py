"""
sensors/tof.py — VL53L0X time-of-flight seat position sensor.

Runs a background polling loop (~30 Hz) that:
  - Reads seat distance from the VL53L0X
  - Updates state["seat_mm"]  (current reading in mm)
  - Tracks per-stroke drive amplitude → state["seat_drive_mm"]
    (catch_distance − finish_distance, positive mm)
  - Logs raw samples to seat_log when a session is active

I2C wiring (Pi-style boards):
  VCC → 3.3 V    GND → GND
  SDA → GPIO 2 (pin 3)
  SCL → GPIO 3 (pin 5)

Default I2C bus: 1 (/dev/i2c-1). Default address: 0x29.
Change TOF_BUS / TOF_ADDR if needed.
"""
import sqlite3
import threading
import time

_DB_PATH = "rowing.db"
TOF_ADDR = 0x29
TOF_BUS  = 1       # /dev/i2c-1

try:
    import smbus2 as _smbus2
    _HAVE_SMBUS = True
except ImportError:
    _HAVE_SMBUS = False


# ── Minimal VL53L0X driver ────────────────────────────────────────────────────
# Initialization reads the device's per-unit stop variable (register 0x91),
# which must be written back before each measurement.  This is the sequence
# used by the ST API and all major open-source wrappers.

class _VL53L0X:
    """Minimal smbus2-based VL53L0X driver (single-shot ranging)."""

    def __init__(self):
        self._bus  = _smbus2.SMBus(TOF_BUS)
        self._stop = None

    def _w(self, reg, val):
        self._bus.write_byte_data(TOF_ADDR, reg, val)

    def _r(self, reg):
        return self._bus.read_byte_data(TOF_ADDR, reg)

    def _r16(self, reg):
        d = self._bus.read_i2c_block_data(TOF_ADDR, reg, 2)
        return (d[0] << 8) | d[1]

    def init(self):
        """Read device stop variable — required once before first measurement."""
        self._w(0x80, 0x01); self._w(0xFF, 0x01); self._w(0x00, 0x00)
        self._stop = self._r(0x91)
        self._w(0x00, 0x01); self._w(0xFF, 0x00); self._w(0x80, 0x00)

    def read_mm(self):
        """Trigger a single measurement; return distance in mm or None."""
        # Arm the sensor with the stop variable, then start single-shot
        self._w(0x80, 0x01); self._w(0xFF, 0x01); self._w(0x00, 0x00)
        self._w(0x91, self._stop)
        self._w(0x00, 0x01); self._w(0xFF, 0x00); self._w(0x80, 0x00)
        self._w(0x00, 0x01)  # start single-shot ranging

        # Poll until done (bit 0 of 0x00 clears), timeout ~200 ms
        for _ in range(100):
            if not (self._r(0x00) & 0x01):
                break
            time.sleep(0.002)
        else:
            return None  # timeout

        mm = self._r16(0x1E)
        return mm if mm < 8190 else None  # 8190 = out-of-range sentinel


def _init_sensor():
    if not _HAVE_SMBUS:
        return None
    try:
        s = _VL53L0X()
        s.init()
        mm = s.read_mm()
        if mm is None:
            return None  # no response — sensor not wired up
        return s
    except Exception:
        return None


# ── Database schema ───────────────────────────────────────────────────────────

def _ensure_schema():
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS seat_log ("
                "id           INTEGER PRIMARY KEY, "
                "session_id   INTEGER NOT NULL, "
                "elapsed_secs REAL    NOT NULL, "
                "seat_mm      INTEGER NOT NULL, "
                "stroke_state INTEGER NOT NULL, "
                "logged_at    REAL    NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS seat_log_session "
                "ON seat_log (session_id, elapsed_secs)"
            )
    except Exception:
        pass


def _log_seat(session_id, elapsed, seat_mm, stroke_state):
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO seat_log "
                "(session_id, elapsed_secs, seat_mm, stroke_state, logged_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, elapsed, seat_mm, stroke_state, time.time()),
            )
    except Exception:
        pass


# ── Main polling loop ─────────────────────────────────────────────────────────

def _tof_loop(state):
    _ensure_schema()
    sensor = _init_sensor()
    if sensor is None:
        return  # no sensor connected — exit silently; state fields stay None

    prev_stroke_state = 0
    seat_catch_mm     = None  # distance at catch (seat far from flywheel → high mm)
    seat_min_mm       = None  # minimum distance during drive (seat at finish → low mm)

    while True:
        try:
            mm = sensor.read_mm()
            if mm is None or mm <= 10:
                time.sleep(0.033)
                continue

            state["seat_mm"] = mm
            ss     = state.get("stroke_state", 0)
            active = state.get("session_active") and not state.get("session_paused")

            # Drive start — record catch position
            if ss == 1 and prev_stroke_state != 1:
                seat_catch_mm = mm
                seat_min_mm   = mm

            # During drive — track minimum (finish position)
            if ss == 1 and seat_min_mm is not None and mm < seat_min_mm:
                seat_min_mm = mm

            # Drive end — compute and store drive amplitude
            if ss != 1 and prev_stroke_state == 1:
                if seat_catch_mm is not None and seat_min_mm is not None:
                    amp = seat_catch_mm - seat_min_mm
                    if amp > 0:
                        state["seat_drive_mm"] = round(amp)
                seat_catch_mm = None
                seat_min_mm   = None

            prev_stroke_state = ss

            # High-frequency log during active sessions
            if active and state.get("session_id"):
                _log_seat(state["session_id"], state.get("elapsed", 0), mm, ss)

        except Exception:
            pass

        time.sleep(0.033)  # ~30 Hz


def start_tof(state):
    """Start the ToF sensor polling thread. Returns immediately.
    If no sensor is detected the thread exits quietly with no side effects."""
    t = threading.Thread(target=_tof_loop, args=(state,), daemon=True, name="tof")
    t.start()
