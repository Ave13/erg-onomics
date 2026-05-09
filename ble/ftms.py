"""
FTMS Rower Profile BLE broadcast.

Allows Zwift, ErgZone, and other fitness apps to connect to this Pi and
receive live rowing data as if it were an FTMS Rower device.

Requires `bless` (pip install bless / apt install python3-bless).
Silently disabled if bless is not installed.
"""
import asyncio
import struct
import threading

try:
    from bless import (
        BlessServer,
        BlessGATTCharacteristic,
        GATTCharacteristicProperties,
        GATTAttributePermissions,
    )
    _BLESS_OK = True
except ImportError:
    _BLESS_OK = False

# FTMS service and key characteristics (Bluetooth SIG assigned numbers)
_FTMS_SERVICE   = "00001826-0000-1000-8000-00805f9b34fb"
_ROWER_DATA     = "00002ad1-0000-1000-8000-00805f9b34fb"
_FTMS_FEATURE   = "00002acc-0000-1000-8000-00805f9b34fb"
_FTMS_STATUS    = "00002ada-0000-1000-8000-00805f9b34fb"
_FTMS_CONTROL   = "00002ad9-0000-1000-8000-00805f9b34fb"

# Rower Data flags we'll always send:
# bit 2 = Total Distance, bit 3 = Instantaneous Pace,
# bit 5 = Instantaneous Power, bit 9 = Heart Rate, bit 11 = Elapsed Time
_FLAGS = (1 << 2) | (1 << 3) | (1 << 5) | (1 << 9) | (1 << 11)

_server = None
_loop   = None


def _rower_bytes():
    """Build FTMS Rower Data characteristic bytes from current state."""
    from ble.pm5 import state

    spm = state.get("spm", 0)
    stroke_rate = int(spm * 2) if isinstance(spm, (int, float)) else 0  # unit 0.5/min
    stroke_count = int(state.get("stroke_count", 0)) & 0xFFFF

    dist_m = int(state.get("distance", 0))

    speed_mm_s = state.get("speed_mm_s", 0)
    if speed_mm_s and speed_mm_s > 0:
        pace_hundredths = int(500 / (speed_mm_s / 1000) * 100)
    else:
        pace_hundredths = 0
    pace_hundredths = min(pace_hundredths, 65535)

    power = int(state.get("watts", 0))
    power = max(-32768, min(32767, power))

    hr = state.get("hr_bpm", 0)
    hr_val = hr if isinstance(hr, int) else 0
    hr_val = min(255, max(0, hr_val))

    elapsed = min(int(state.get("elapsed", 0)), 65535)

    data = struct.pack("<HBH", _FLAGS, stroke_rate, stroke_count)
    data += struct.pack("<I", dist_m)[:3]          # uint24 total distance
    data += struct.pack("<H", pace_hundredths)     # instantaneous pace
    data += struct.pack("<h", power)               # instantaneous power (sint16)
    data += struct.pack("<B", hr_val)              # heart rate
    data += struct.pack("<H", elapsed)             # elapsed time
    return bytearray(data)


async def _ftms_loop():
    global _server

    _server = BlessServer(name="ErgRower")

    await _server.add_new_service(_FTMS_SERVICE)

    # FTMS Feature characteristic (read-only; advertise Rowing Machine bit)
    # Fitness Machine Feature word: bit 10 = Cadence Supported, bit 9 = Power Supported
    feature_val = bytearray(struct.pack("<II", (1 << 9) | (1 << 10), 0))
    await _server.add_new_characteristic(
        _FTMS_SERVICE, _FTMS_FEATURE,
        GATTCharacteristicProperties.read,
        feature_val,
        GATTAttributePermissions.readable,
    )

    # Rower Data (notify + read)
    await _server.add_new_characteristic(
        _FTMS_SERVICE, _ROWER_DATA,
        GATTCharacteristicProperties.notify | GATTCharacteristicProperties.read,
        _rower_bytes(),
        GATTAttributePermissions.readable,
    )

    await _server.start()

    while True:
        await asyncio.sleep(0.5)
        try:
            _server.get_characteristic(_ROWER_DATA).value = _rower_bytes()
            await _server.update_value(_FTMS_SERVICE, _ROWER_DATA)
        except Exception:
            pass


def start_ftms():
    """
    Launch the FTMS broadcast in a background daemon thread.
    No-op if bless is not installed.
    """
    if not _BLESS_OK:
        return

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _loop.run_until_complete(_ftms_loop())
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="ftms-broadcast").start()


def is_available():
    return _BLESS_OK
