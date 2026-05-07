import asyncio
from bleak import BleakClient, BleakScanner

ROWING_STATUS_UUID = "CE060031-43E5-11E4-916C-0800200C9A66"
ADD_STATUS_UUID    = "CE060032-43E5-11E4-916C-0800200C9A66"

state = {
    "pace": "--:--",
    "spm": 0,
    "watts": 0,
    "distance": 0.0,
    "elapsed": 0.0,
    "connected": False,
    "device_name": "",
}

def speed_to_pace(speed_mm_s):
    if speed_mm_s == 0:
        return "--:--"
    speed_m_s = speed_mm_s / 1000
    pace_sec = 500 / speed_m_s
    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"

def pace_to_watts(pace_sec):
    if pace_sec == 0:
        return 0
    return round(2.80 / (pace_sec / 60) ** 3)

def parse_general_status(data):
    state["elapsed"] = int.from_bytes(data[0:3], "little") / 100
    state["distance"] = int.from_bytes(data[3:6], "little") / 10

def parse_add_status_1(data):
    speed_mm_s = int.from_bytes(data[0:2], "little")
    spm = data[3]
    pace_str = speed_to_pace(speed_mm_s)
    pace_sec = (500 / (speed_mm_s / 1000)) if speed_mm_s > 0 else 0
    state["pace"] = pace_str
    state["spm"] = spm
    state["watts"] = pace_to_watts(pace_sec)

async def ble_main():
    while True:
        state["connected"] = False
        state["device_name"] = ""
        devices = await BleakScanner.discover(timeout=10)
        pm5 = next((d for d in devices if d.name and "PM5" in d.name), None)
        if not pm5:
            await asyncio.sleep(5)
            continue
        try:
            async with BleakClient(pm5.address) as client:
                state["connected"] = True
                state["device_name"] = pm5.name or "PM5"
                await client.start_notify(ROWING_STATUS_UUID, lambda s, d: parse_general_status(d))
                await client.start_notify(ADD_STATUS_UUID, lambda s, d: parse_add_status_1(d))
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception:
            pass
        await asyncio.sleep(3)

def start_ble():
    asyncio.run(ble_main())
