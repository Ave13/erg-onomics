"""Tests for db/records.py — PR detection and sliding-window pace."""
import sqlite3
import pytest
import db.records as records_mod
from db.records import _best_pace_for_distance, check_and_save_records, get_all_records

USER_ID = 1
SESSION_ID = 10


def _init_db(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS records ("
        "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
        "record_type TEXT NOT NULL, value REAL NOT NULL, "
        "session_id INTEGER, set_at REAL)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_records_user_type "
        "ON records (user_id, record_type)"
    )
    conn.commit()


# ── _best_pace_for_distance ───────────────────────────────────────────────────

class TestBestPaceForDistance:
    def test_empty_rows_returns_none(self):
        assert _best_pace_for_distance([], 500) is None

    def test_constant_speed_500m(self):
        # 2 m/s for 250 seconds covers 500m; pace should be 250s per 500m
        rows = [(t, 2000) for t in range(1, 251)]  # speed 2000 mm/s = 2 m/s
        pace = _best_pace_for_distance(rows, 500)
        assert pace is not None
        assert 245 <= pace <= 255  # ≈ 250s / 500m = 4:10

    def test_faster_segment_wins(self):
        # Slow start (1 m/s), fast finish (4 m/s), target 500m
        slow = [(t, 1000) for t in range(1, 101)]   # 100s at 1 m/s = 100m
        fast = [(100 + t, 4000) for t in range(1, 151)]  # 150s at 4 m/s = 600m
        rows = slow + fast
        pace = _best_pace_for_distance(rows, 500)
        assert pace is not None
        # Fast segment: 500m at 4 m/s ≈ 125s → 500/4 = 125s per 500m
        assert pace < 200  # should pick the fast segment

    def test_distance_shorter_than_target_returns_none(self):
        # Only 100m covered, asking for 500m
        rows = [(t, 2000) for t in range(1, 51)]   # 50s at 2 m/s = 100m
        assert _best_pace_for_distance(rows, 500) is None

    def test_result_is_positive(self):
        rows = [(t, 3000) for t in range(1, 201)]
        pace = _best_pace_for_distance(rows, 500)
        assert pace is not None
        assert pace > 0


# ── check_and_save_records ────────────────────────────────────────────────────

class TestCheckAndSaveRecords:
    def _base_stats(self, **overrides):
        stats = {
            "distance_m": 2000,
            "elapsed_secs": 480,
            "avg_watts": 200,
            "max_watts": 280,
            "avg_spm": 22,
            "stroke_log_rows": [(t, 3000) for t in range(1, 481)],
        }
        stats.update(overrides)
        return stats

    def test_no_user_id_returns_empty(self, tmp_db, monkeypatch):
        monkeypatch.setattr(records_mod, "_DB_PATH", tmp_db)
        result = check_and_save_records(SESSION_ID, None, self._base_stats())
        assert result == []

    def test_first_session_breaks_all_records(self, tmp_db, monkeypatch):
        monkeypatch.setattr(records_mod, "_DB_PATH", tmp_db)
        broken = check_and_save_records(SESSION_ID, USER_ID, self._base_stats())
        record_types = [r[0] for r in broken]
        assert "longest_distance" in record_types
        assert "longest_time"     in record_types
        assert "best_avg_watts"   in record_types
        # first run → old_value is None for all
        assert all(r[1] is None for r in broken)

    def test_improvement_detected(self, tmp_db, monkeypatch):
        monkeypatch.setattr(records_mod, "_DB_PATH", tmp_db)
        check_and_save_records(SESSION_ID, USER_ID, self._base_stats(avg_watts=200))
        broken = check_and_save_records(SESSION_ID + 1, USER_ID, self._base_stats(avg_watts=250))
        types = [r[0] for r in broken]
        assert "best_avg_watts" in types
        match = next(r for r in broken if r[0] == "best_avg_watts")
        assert match[1] == 200   # old value
        assert match[2] == 250   # new value

    def test_no_improvement_not_recorded(self, tmp_db, monkeypatch):
        monkeypatch.setattr(records_mod, "_DB_PATH", tmp_db)
        check_and_save_records(SESSION_ID, USER_ID, self._base_stats(avg_watts=250))
        broken = check_and_save_records(SESSION_ID + 1, USER_ID, self._base_stats(avg_watts=200))
        types = [r[0] for r in broken]
        assert "best_avg_watts" not in types

    def test_pace_pr_skipped_if_distance_too_short(self, tmp_db, monkeypatch):
        monkeypatch.setattr(records_mod, "_DB_PATH", tmp_db)
        stats = self._base_stats(distance_m=400)  # under 500m
        broken = check_and_save_records(SESSION_ID, USER_ID, stats)
        types = [r[0] for r in broken]
        assert "pace_500m"   not in types
        assert "pace_1000m"  not in types

    def test_get_all_records_after_session(self, tmp_db, monkeypatch):
        monkeypatch.setattr(records_mod, "_DB_PATH", tmp_db)
        check_and_save_records(SESSION_ID, USER_ID, self._base_stats())
        records = get_all_records(USER_ID)
        assert "longest_distance" in records
        val, set_at = records["longest_distance"]
        assert val == 2000
        assert set_at > 0
