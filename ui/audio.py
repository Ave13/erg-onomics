import subprocess
import threading
import time

from ble.pm5 import state

_INTERVAL_M   = 500    # speak every N metres
_INTERVAL_S   = 60     # speak every N seconds (whichever comes first)
_last_dist_cue = 0.0
_last_time_cue = 0.0
_lock          = threading.Lock()


def _speak(text):
    try:
        subprocess.Popen(
            ["espeak", "-s", "140", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass   # espeak not installed — silent


def _pace_words(pace_str):
    """'2:05' → 'two minutes five'"""
    try:
        parts = pace_str.split(":")
        mins  = int(parts[0])
        secs  = int(parts[1])
        return f"{mins} minute{'s' if mins != 1 else ''} {secs:02d}"
    except Exception:
        return pace_str


def check_and_cue():
    """
    Called periodically (e.g. every second via Clock).
    Fires audio cue when distance or time milestone is crossed.
    """
    global _last_dist_cue, _last_time_cue

    if not state.get("session_active") or state.get("session_paused"):
        return

    dist    = state.get("distance", 0)
    elapsed = state.get("elapsed", 0)
    pace    = state.get("pace", "--:--")
    hr      = state.get("hr_bpm", "--")

    with _lock:
        fire = False
        if dist - _last_dist_cue >= _INTERVAL_M:
            _last_dist_cue = (dist // _INTERVAL_M) * _INTERVAL_M
            fire = True
        elif elapsed - _last_time_cue >= _INTERVAL_S:
            _last_time_cue = (elapsed // _INTERVAL_S) * _INTERVAL_S
            fire = True

        if not fire:
            return

    parts = [f"{int(dist)} metres"]
    if pace != "--:--":
        parts.append(f"pace {_pace_words(pace)} per 500")
    if isinstance(hr, int):
        parts.append(f"heart rate {hr}")

    threading.Thread(target=_speak, args=(", ".join(parts),), daemon=True).start()


def reset_cues():
    """Call when a new session starts."""
    global _last_dist_cue, _last_time_cue
    with _lock:
        _last_dist_cue = 0.0
        _last_time_cue = 0.0
