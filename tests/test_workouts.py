"""Tests for db/workouts.py — CRUD, summary formatting, interval labels."""
import pytest
import db.workouts as workouts_mod
from db.workouts import workout_summary, _interval_label


# ── _interval_label ──────────────────────────────────────────────────────────

class TestIntervalLabel:
    def test_distance_meters(self):
        assert _interval_label({"type": "distance", "meters": 500, "rest_secs": 0}) == "500m"

    def test_time_interval(self):
        assert _interval_label({"type": "time", "seconds": 60, "rest_secs": 0}) == "1:00"

    def test_time_interval_multi_minute(self):
        assert _interval_label({"type": "time", "seconds": 300, "rest_secs": 0}) == "5:00"

    def test_calorie_interval(self):
        assert _interval_label({"type": "calorie", "calories": 50, "rest_secs": 0}) == "50 kcal"

    def test_rest_seconds_appended(self):
        label = _interval_label({"type": "distance", "meters": 1000, "rest_secs": 120})
        assert "2:00 rest" in label

    def test_undefined_rest_shows_athlete(self):
        label = _interval_label({"type": "distance", "meters": 500, "rest_secs": -1})
        assert "athlete rest" in label

    def test_no_rest_no_suffix(self):
        label = _interval_label({"type": "distance", "meters": 500, "rest_secs": 0})
        assert "rest" not in label

    def test_rest_90_seconds(self):
        label = _interval_label({"type": "time", "seconds": 60, "rest_secs": 90})
        assert "1:30 rest" in label


# ── workout_summary ──────────────────────────────────────────────────────────

class TestWorkoutSummary:
    def test_empty_definition(self):
        assert workout_summary({"intervals": []}) == "Empty"

    def test_single_distance(self):
        defn = {"intervals": [{"type": "distance", "meters": 2000, "rest_secs": 0}]}
        assert workout_summary(defn) == "2000m"

    def test_single_time(self):
        defn = {"intervals": [{"type": "time", "seconds": 1800, "rest_secs": 0}]}
        assert workout_summary(defn) == "30:00"

    def test_repeated_identical_intervals(self):
        iv = {"type": "distance", "meters": 500, "rest_secs": 120}
        defn = {"intervals": [iv] * 6}
        result = workout_summary(defn)
        assert result.startswith("6×")
        assert "500m" in result

    def test_mixed_intervals_shows_count(self):
        defn = {"intervals": [
            {"type": "distance", "meters": 500, "rest_secs": 60},
            {"type": "time",     "seconds": 300, "rest_secs": 0},
        ]}
        result = workout_summary(defn)
        assert "2" in result
        assert "interval" in result.lower()


# ── CRUD ─────────────────────────────────────────────────────────────────────

class TestWorkoutCRUD:
    def test_list_workouts_returns_presets(self, tmp_db, monkeypatch):
        monkeypatch.setattr(workouts_mod, "_DB_PATH", tmp_db)
        rows = workouts_mod.list_workouts()
        assert len(rows) > 0
        assert all(r[3] for r in rows)  # all is_preset=True on fresh DB

    def test_save_and_get_workout(self, tmp_db, monkeypatch):
        monkeypatch.setattr(workouts_mod, "_DB_PATH", tmp_db)
        workouts_mod.list_workouts()  # seed presets
        intervals = [{"type": "distance", "meters": 500, "rest_secs": 60}] * 4
        wid = workouts_mod.save_workout("4×500", intervals)
        assert wid is not None

        row = workouts_mod.get_workout(wid)
        assert row is not None
        assert row[1] == "4×500"
        assert row[2]["intervals"] == intervals
        assert row[3] is False  # not a preset

    def test_delete_custom_workout(self, tmp_db, monkeypatch):
        monkeypatch.setattr(workouts_mod, "_DB_PATH", tmp_db)
        workouts_mod.list_workouts()
        wid = workouts_mod.save_workout("Temp", [{"type": "time", "seconds": 60, "rest_secs": 0}])
        assert workouts_mod.get_workout(wid) is not None

        workouts_mod.delete_workout(wid)
        assert workouts_mod.get_workout(wid) is None

    def test_delete_preset_is_ignored(self, tmp_db, monkeypatch):
        monkeypatch.setattr(workouts_mod, "_DB_PATH", tmp_db)
        presets = workouts_mod.list_workouts()
        preset_id = presets[0][0]
        workouts_mod.delete_workout(preset_id)
        assert workouts_mod.get_workout(preset_id) is not None

    def test_get_nonexistent_workout_returns_none(self, tmp_db, monkeypatch):
        monkeypatch.setattr(workouts_mod, "_DB_PATH", tmp_db)
        assert workouts_mod.get_workout(99999) is None
