"""Tests for pure-math conversion functions in ble/pm5.py and db/strive.py."""
import pytest

from ble.pm5 import speed_to_pace, pace_to_watts
from db.strive import estimate_max_hr


class TestSpeedToPace:
    def test_zero_speed_returns_placeholder(self):
        assert speed_to_pace(0) == "--:--"

    def test_1000_mm_s_gives_8_20(self):
        # 1 m/s → 500s per 500m = 8:20
        assert speed_to_pace(1000) == "8:20"

    def test_2000_mm_s_gives_4_10(self):
        # 2 m/s → 250s per 500m = 4:10
        assert speed_to_pace(2000) == "4:10"

    def test_typical_race_pace_2_min(self):
        # Exact 2:00/500m → speed exactly 500/120 m/s; avoid integer rounding by
        # using the exact fractional mm/s the formula inverts from
        result = speed_to_pace(4167)   # ≈ 4.167 m/s → 119.97s ≈ 1:59
        assert result in ("1:59", "2:00")

    def test_sub_minute_pace_format(self):
        # 500m in 55s → speed = 500000/55 ≈ 9091 mm/s
        speed = round(500_000 / 55)
        result = speed_to_pace(speed)
        assert result.startswith("0:")

    def test_format_is_mm_colon_ss(self):
        result = speed_to_pace(2000)
        parts = result.split(":")
        assert len(parts) == 2
        assert len(parts[1]) == 2  # seconds always zero-padded


class TestPaceToWatts:
    def test_zero_pace_returns_zero(self):
        assert pace_to_watts(0) == 0

    def test_two_minute_pace_approx_200W(self):
        # 2:00/500m ≈ 200W per Concept2 standard
        w = pace_to_watts(120)
        assert 195 <= w <= 210

    def test_one_forty_pace_approx_350W(self):
        # 1:40/500m ≈ 350W
        w = pace_to_watts(100)
        assert 340 <= w <= 360

    def test_two_thirty_pace_approx_104W(self):
        # 2:30/500m ≈ 104W
        w = pace_to_watts(150)
        assert 99 <= w <= 110

    def test_faster_pace_gives_more_watts(self):
        assert pace_to_watts(100) > pace_to_watts(120) > pace_to_watts(150)

    def test_returns_int(self):
        assert isinstance(pace_to_watts(120), int)


class TestEstimateMaxHr:
    def test_age_30_tanaka(self):
        # 208 - 0.7×30 = 187
        hr = estimate_max_hr("1996-01-01")
        assert 185 <= hr <= 190

    def test_age_50_tanaka(self):
        # 208 - 0.7×50 = 173
        hr = estimate_max_hr("1976-01-01")
        assert 170 <= hr <= 176

    def test_invalid_dob_returns_default(self):
        assert estimate_max_hr("not-a-date") == 185
        assert estimate_max_hr("") == 185
        assert estimate_max_hr(None) == 185

    def test_older_age_lower_max_hr(self):
        young = estimate_max_hr("2000-01-01")
        old = estimate_max_hr("1960-01-01")
        assert young > old
