# erg-onomics

Concept2 PM5 rowing app for Raspberry Pi 3B with 7" touchscreen.

## Stack
- Python 3 / bleak (BLE) / Kivy (UI) / SQLite

## Architecture
BLE runs in background asyncio thread → shared state dict → Kivy Clock polls at 2Hz → UI updates

## Phases
1. Live data display (pace, SPM, watts, distance)
2. Basic workout timer + session save
3. Custom interval workout builder
4. History & CSV export
