"""
FTMS Rower Profile BLE broadcast.

Allows ErgZone, Kinomap, and other FTMS-aware fitness apps on iPad/iPhone
to connect to this Pi and receive live rowing data.

The Pi simultaneously acts as BLE central (connected to PM5) and peripheral
(advertising FTMS) — the BCM43438 on Pi 3B supports dual-role at the BlueZ level.

Requires:
    sudo apt install python3-dbus python3-gi
    pip install bless

Silent no-op if bless is not installed.
"""
import asyncio
import logging
import struct
import threading

log = logging.getLogger(__name__)

try:
    from bless import BlessServer, GATTCharacteristicProperties, GATTAttributePermissions
    _BLESS_OK = True
except ImportError:
    _BLESS_OK = False

# Bluetooth SIG FTMS UUIDs
_FTMS_SERVICE = "00001826-0000-1000-8000-00805f9b34fb"
_ROWER_DATA   = "00002ad1-0000-1000-8000-00805f9b34fb"   # notify + read
_FTMS_FEATURE = "00002acc-0000-1000-8000-00805f9b34fb"   # read-only

# Rower Data flags (always present fields):
# bit 2 = Total Distance, bit 3 = Inst. Pace,
# bit 5 = Inst. Power, bit 9 = Heart Rate, bit 11 = Elapsed Time
_FLAGS = (1 << 2) | (1 << 3) | (1 << 5) | (1 << 9) | (1 << 11)

# FTMS Feature bitmap: bit 1 = Cadence, bit 14 = Power Measurement
_FEATURE_WORD = struct.pack("<II", (1 << 1) | (1 << 14), 0)

_server = None


def _rower_bytes():
    """Pack current state into an FTMS Rower Data characteristic payload."""
    from ble.pm5 import state

    spm = state.get("spm", 0)
    # Stroke rate field: units of 0.5 /min  →  value = SPM * 2
    stroke_rate  = int(spm * 2) if isinstance(spm, (int, float)) else 0
    stroke_count = int(state.get("stroke_count", 0)) & 0xFFFF

    dist_m = int(state.get("distance", 0))

    speed_mm_s = state.get("speed_mm_s", 0) or 0
    if speed_mm_s > 0:
        pace_hundredths = min(int(500 / (speed_mm_s / 1000) * 100), 65535)
    else:
        pace_hundredths = 0

    power = max(-32768, min(int(state.get("watts", 0)), 32767))

    hr    = state.get("hr_bpm", 0)
    hr_val = min(hr if isinstance(hr, int) else 0, 255)

    elapsed = min(int(state.get("elapsed", 0)), 65535)

    data  = struct.pack("<HBH", _FLAGS, stroke_rate, stroke_count)
    data += struct.pack("<I", dist_m)[:3]       # uint24 total distance (m)
    data += struct.pack("<H", pace_hundredths)   # inst. pace (0.01 s/500m)
    data += struct.pack("<h", power)             # inst. power (sint16, W)
    data += struct.pack("<B", hr_val)            # heart rate (uint8, bpm)
    data += struct.pack("<H", elapsed)           # elapsed time (uint16, s)
    return bytearray(data)


async def _notify(char_uuid):
    """Update characteristic value and trigger BLE notification."""
    global _server
    char = _server.get_characteristic(char_uuid)
    char.value = _rower_bytes()
    result = _server.update_value(_FTMS_SERVICE, char_uuid)
    if asyncio.iscoroutine(result):
        await result


async def _ftms_loop():
    global _server

    _server = BlessServer(name="ErgRower")

    await _server.add_new_service(_FTMS_SERVICE)

    await _server.add_new_characteristic(
        _FTMS_SERVICE, _FTMS_FEATURE,
        GATTCharacteristicProperties.read,
        bytearray(_FEATURE_WORD),
        GATTAttributePermissions.readable,
    )
    await _server.add_new_characteristic(
        _FTMS_SERVICE, _ROWER_DATA,
        GATTCharacteristicProperties.notify | GATTCharacteristicProperties.read,
        _rower_bytes(),
        GATTAttributePermissions.readable,
    )

    await _server.start()
    log.info("FTMS broadcast started — advertising as 'ErgRower'")

    while True:
        await asyncio.sleep(0.5)
        try:
            await _notify(_ROWER_DATA)
        except Exception as exc:
            log.debug("FTMS notify error: %s", exc)


def start_ftms():
    """
    Start FTMS Rower broadcast in a background daemon thread.
    No-op if bless is not installed.
    """
    if not _BLESS_OK:
        log.info("bless not installed — FTMS broadcast disabled")
        return

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_ftms_loop())
        except Exception as exc:
            log.warning("FTMS broadcast stopped: %s", exc)

    threading.Thread(target=_run, daemon=True, name="ftms-broadcast").start()


def is_available():
    return _BLESS_OK
