import threading
import asyncio
from kivy.app import App
from kivy.clock import Clock
from ble.pm5 import BLEManager
from ui.app import RowingApp

if __name__ == "__main__":
    RowingApp().run()
