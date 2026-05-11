"""Tests for perfect-stroke streak logic in ble/pm5.parse_stroke_data()."""
import struct
import pytest

import ble.pm5 as pm5_mod
from ble.pm5 import parse_stroke_data, state


def _make_stroke_bytes(
    drive_length_cm=130,
    drive_time_hundredths=75,   # 0.75s
    recovery_hundredths=150,    # 1.50s
    stroke_distance_cm=100,
    peak_force_n_tenths=2700,   # 270.0 N
    avg_force_n_tenths=1800,    # 180.0 N  → ratio 1.5 ✓
    work_per_stroke_tenths=500,
    stroke_count=1,
):
    """
    Build a 20-byte packet matching the parse_stroke_data() layout:
      [0–5]  unused (pad zeros)
      [6]    drive_length_cm
      [7]    drive_time (×100)
      [8–9]  recovery (×100, little-endian)
      [10–11] stroke_distance (×100, little-endian)
      [12–13] peak_force (×10, little-endian)
      [14–15] avg_force (×10, little-endian)
      [16–17] work_per_stroke (×10, little-endian)
      [18–19] stroke_count (little-endian)
    """
    data = bytearray(20)
    data[6]  = drive_length_cm
    data[7]  = drive_time_hundredths
    struct.pack_into("<H", data,  8, recovery_hundredths)
    struct.pack_into("<H", data, 10, stroke_distance_cm)
    struct.pack_into("<H", data, 12, peak_force_n_tenths)
    struct.pack_into("<H", data, 14, avg_force_n_tenths)
    struct.pack_into("<H", data, 16, work_per_stroke_tenths)
    struct.pack_into("<H", data, 18, stroke_count)
    return bytes(data)


@pytest.fixture(autouse=True)
def reset_state(tmp_db, monkeypatch):
    """Reset streak counters and patch DB path before each test."""
    monkeypatch.setattr(pm5_mod, "_DB_PATH", tmp_db)
    state["perfect_streak"]      = 0
    state["perfect_streak_best"] = 0
    state["expected_drive_cm"]   = 130
    state["session_id"]          = None   # skip DB log
    state["session_paused"]      = False
    # reset EMA so timing doesn't interfere
    pm5_mod._ema_interval_secs = None
    pm5_mod._stroke_times.clear()
    yield


class TestPerfectStreak:
    def test_good_stroke_increments_streak(self):
        # ratio=1.5, drive=0.75s, length=130 (matches expected 130) → perfect
        parse_stroke_data(_make_stroke_bytes())
        assert state["perfect_streak"] == 1

    def test_consecutive_good_strokes_build_streak(self):
        for _ in range(5):
            parse_stroke_data(_make_stroke_bytes())
        assert state["perfect_streak"] == 5
        assert state["perfect_streak_best"] == 5

    def test_bad_ratio_resets_streak(self):
        parse_stroke_data(_make_stroke_bytes())
        assert state["perfect_streak"] == 1
        # ratio = 400/100 = 4.0 — outside 1.3–1.8
        bad = _make_stroke_bytes(peak_force_n_tenths=4000, avg_force_n_tenths=1000)
        parse_stroke_data(bad)
        assert state["perfect_streak"] == 0

    def test_drive_time_too_short_resets_streak(self):
        parse_stroke_data(_make_stroke_bytes())
        # drive_time = 0.30s → below 0.5s minimum
        bad = _make_stroke_bytes(drive_time_hundredths=30)
        parse_stroke_data(bad)
        assert state["perfect_streak"] == 0

    def test_drive_time_too_long_resets_streak(self):
        parse_stroke_data(_make_stroke_bytes())
        # drive_time = 1.5s → above 1.2s maximum
        bad = _make_stroke_bytes(drive_time_hundredths=150)
        parse_stroke_data(bad)
        assert state["perfect_streak"] == 0

    def test_drive_length_too_far_from_expected_resets_streak(self):
        state["expected_drive_cm"] = 130
        parse_stroke_data(_make_stroke_bytes())
        # length = 80cm, expected = 130cm → delta 50 > 15 limit
        bad = _make_stroke_bytes(drive_length_cm=80)
        parse_stroke_data(bad)
        assert state["perfect_streak"] == 0

    def test_best_streak_preserved_after_bad_stroke(self):
        for _ in range(3):
            parse_stroke_data(_make_stroke_bytes())
        assert state["perfect_streak_best"] == 3
        # bad stroke resets current but best should stay
        bad = _make_stroke_bytes(peak_force_n_tenths=4000, avg_force_n_tenths=1000)
        parse_stroke_data(bad)
        assert state["perfect_streak"] == 0
        assert state["perfect_streak_best"] == 3

    def test_zero_avg_force_skips_evaluation(self):
        # avg_force_n = 0 → skip streak evaluation (division by zero guard)
        parse_stroke_data(_make_stroke_bytes(avg_force_n_tenths=0))
        assert state["perfect_streak"] == 0  # skipped, not incremented or reset

    def test_ratio_at_lower_boundary_is_perfect(self):
        # ratio exactly 1.3 → 1300/1000 = 1.3 → should be perfect
        stroke = _make_stroke_bytes(peak_force_n_tenths=1300, avg_force_n_tenths=1000)
        parse_stroke_data(stroke)
        assert state["perfect_streak"] == 1

    def test_ratio_above_upper_boundary_is_bad(self):
        # ratio = 1.9 → outside 1.3–1.8
        stroke = _make_stroke_bytes(peak_force_n_tenths=1900, avg_force_n_tenths=1000)
        parse_stroke_data(stroke)
        assert state["perfect_streak"] == 0
