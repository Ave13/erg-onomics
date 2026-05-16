"""
ble/csafe.py — CSAFE framing and PM5 workout programming commands.

Reference: Concept2 PM5 BLE Fitness Equipment Interface Specification
and the CSAFE (Communication Standards for Fitness Equipment) standard.

NOTE: PM5-specific long command bytes (PM_SET_*) are based on community
research and the ErgConnect / py-ergo-erg implementations.  Verify against
Concept2's BLE spec before shipping to production hardware.

CSAFE frame layout:
  0xF1  [data_len]  [cmd_bytes...]  [xor_checksum]  0xF2

Multiple commands may be concatenated inside a single frame.
"""

# Writable BLE characteristic on the PM5 for CSAFE commands (host → PM5).
# Located in the C2 Rowing Primary Service (CE060000-…).
CSAFE_TX_UUID = "CE060020-43E5-11E4-916C-0800200C9A66"

# ── Standard CSAFE short commands (no data payload) ──────────────────────────
CMD_GO_IDLE      = 0x01
CMD_GO_HAVE_ID   = 0x02
CMD_GO_IN_USE    = 0x04
CMD_GO_FINISHED  = 0x05
CMD_RESET        = 0x11
CMD_SET_PROGRAM  = 0x24  # 2-byte payload: [program_id, program_number]

# ── Concept2 PM-specific long commands (wrapped in 0x76) ──────────────────────
# Payload: 0x76 [total_payload_len] [pm_cmd] [data...]
PM_SET_WORKOUT_TYPE    = 0x1A  # 1 byte: 0=just row, 4=interval dist, 5=interval time
PM_SET_TOTAL_INTERVALS = 0x20  # 1 byte: number of intervals
PM_SET_WORK_DISTANCE   = 0x1D  # 2 bytes LE: metres
PM_SET_WORK_TIME       = 0x1E  # 3 bytes: minutes, seconds, tenths
PM_SET_REST_TIME       = 0x1F  # 3 bytes: minutes, seconds, tenths


# ── Frame builder ─────────────────────────────────────────────────────────────

def frame(commands: bytes) -> bytes:
    """Wrap concatenated command bytes in a CSAFE transmission frame."""
    crc = len(commands)
    for b in commands:
        crc ^= b
    return bytes([0xF1, len(commands)]) + commands + bytes([crc & 0xFF, 0xF2])


def _short(cmd: int) -> bytes:
    return bytes([cmd])


def _pm(pm_cmd: int, data: bytes) -> bytes:
    """Encode one PM5-specific long command."""
    payload = bytes([pm_cmd]) + data
    return bytes([0x76, len(payload)]) + payload


# ── Command constructors ──────────────────────────────────────────────────────

def cmd_go_idle() -> bytes:
    return _short(CMD_GO_IDLE)


def cmd_go_in_use() -> bytes:
    return _short(CMD_GO_IN_USE)


def cmd_set_workout_type(wtype: int) -> bytes:
    return _pm(PM_SET_WORKOUT_TYPE, bytes([wtype & 0xFF]))


def cmd_set_total_intervals(n: int) -> bytes:
    return _pm(PM_SET_TOTAL_INTERVALS, bytes([n & 0xFF]))


def cmd_set_work_distance(meters: int) -> bytes:
    return _pm(PM_SET_WORK_DISTANCE, meters.to_bytes(2, 'little'))


def cmd_set_work_time(total_secs: int) -> bytes:
    mins = (total_secs // 60) & 0xFF
    secs = (total_secs % 60) & 0xFF
    return _pm(PM_SET_WORK_TIME, bytes([mins, secs, 0]))


def cmd_set_rest_time(total_secs: int) -> bytes:
    mins = max(0, total_secs // 60) & 0xFF
    secs = max(0, total_secs % 60) & 0xFF
    return _pm(PM_SET_REST_TIME, bytes([mins, secs, 0]))


# ── High-level: build frames for a complete workout ───────────────────────────

def workout_frames(intervals: list) -> list[bytes]:
    """
    Return a list of CSAFE frames to program a workout onto the PM5.

    The PM5 natively supports one repeated interval type (all intervals the
    same).  If the workout is mixed (heterogeneous intervals), we program
    only the FIRST interval's type/goal/rest — app-side tracking handles the
    rest as an overlay.  Each returned bytes object is ready to write to
    CSAFE_TX_UUID.

    Returns [reset_frame, config_frame] — send in order with a short gap.
    """
    if not intervals:
        return [frame(cmd_go_idle())]

    iv   = intervals[0]
    itype = iv.get("type", "distance")
    rest  = max(0, iv.get("rest_secs", 0))
    n     = len(intervals)

    # Frame 1: idle (reset PM5 workout state before programming)
    f1 = frame(cmd_go_idle())

    # Frame 2: workout config + start
    cmds = bytearray()
    if itype == "distance":
        meters = iv.get("meters", 500)
        cmds += cmd_set_workout_type(4)           # 4 = interval by distance
        cmds += cmd_set_work_distance(meters)
    else:  # time or calorie — map to time interval
        secs = iv.get("seconds", 60)
        cmds += cmd_set_workout_type(5)           # 5 = interval by time
        cmds += cmd_set_work_time(secs)

    cmds += cmd_set_total_intervals(n)
    if rest > 0:
        cmds += cmd_set_rest_time(rest)
    cmds += cmd_go_in_use()

    f2 = frame(bytes(cmds))
    return [f1, f2]
