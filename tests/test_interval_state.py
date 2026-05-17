"""
Tests for _update_interval_state() in server.py.

server.py starts BLE/FTMS threads at import time, so we mock those
entry points before importing.

Requires fastapi and uvicorn to be installed; skipped otherwise.
"""
import sys
import types
from unittest.mock import MagicMock, patch
import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")


def _make_fake_pm5_state():
    return {
        "distance": 0.0,
        "elapsed": 0.0,
        "session_active": True,
        "active_workout_id": None,
        "interval_index": 0,
        "interval_phase": "work",
        "interval_remaining": None,
    }


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Import server.py with BLE/FTMS/audio side-effects suppressed."""
    fake_state = _make_fake_pm5_state()

    # Patch the ble.pm5 module before server imports it
    fake_pm5 = MagicMock()
    fake_pm5.state = fake_state
    fake_pm5.start_ble = MagicMock()
    fake_pm5.start_session = MagicMock(return_value=1)
    fake_pm5.stop_session = MagicMock()
    fake_pm5.pause_session = MagicMock()
    fake_pm5.resume_session = MagicMock()
    fake_pm5.find_resumable_session = MagicMock(return_value=None)
    fake_pm5.has_user_profile = MagicMock(return_value=False)
    fake_pm5.save_user_profile = MagicMock(return_value=1)
    fake_pm5.load_user_profile = MagicMock()

    sys.modules["ble.pm5"]  = fake_pm5
    sys.modules["ble.ftms"] = MagicMock()
    sys.modules["ui.audio"] = MagicMock()

    # Prevent actual threading in server module-level code
    with patch("threading.Thread"):
        import server as srv
    return srv, fake_state


def _set_state(fake_state, **kwargs):
    fake_state.update(_make_fake_pm5_state())
    fake_state.update(kwargs)


class TestUpdateIntervalStateNoWorkout:
    def test_no_active_workout_resets_to_defaults(self, server, tmp_db, monkeypatch):
        srv, fake_state = server
        _set_state(fake_state, active_workout_id=None, session_active=True)
        srv._update_interval_state()
        assert fake_state["interval_index"] == 0
        assert fake_state["interval_phase"] == "work"
        assert fake_state["interval_remaining"] is None

    def test_no_active_session_resets(self, server, tmp_db, monkeypatch):
        srv, fake_state = server
        _set_state(fake_state, session_active=False, active_workout_id=99)
        srv._update_interval_state()
        assert fake_state["interval_index"] == 0
        assert fake_state["interval_phase"] == "work"


class TestUpdateIntervalStateDistance:
    """Distance-based interval tracking."""

    def test_within_first_interval_work_phase(self, server, tmp_db, monkeypatch):
        import db.workouts as wk_mod
        monkeypatch.setattr(wk_mod, "_DB_PATH", tmp_db)
        wid = wk_mod.save_workout("Test", [
            {"type": "distance", "meters": 500, "rest_secs": 0},
        ])
        srv, fake_state = server

        def fake_get(wid_arg):
            return wk_mod.get_workout(wid_arg)

        monkeypatch.setattr(srv, "get_workout", fake_get)
        _set_state(fake_state, active_workout_id=wid, session_active=True, distance=250.0)
        srv._update_interval_state()
        assert fake_state["interval_index"] == 0
        assert fake_state["interval_phase"] == "work"
        assert fake_state["interval_remaining"] == 250  # 500 - 250

    def test_past_all_intervals_shows_done(self, server, tmp_db, monkeypatch):
        import db.workouts as wk_mod
        monkeypatch.setattr(wk_mod, "_DB_PATH", tmp_db)
        wid = wk_mod.save_workout("Test2", [
            {"type": "distance", "meters": 500, "rest_secs": 0},
        ])
        srv, fake_state = server
        monkeypatch.setattr(srv, "get_workout", lambda w: wk_mod.get_workout(w))
        _set_state(fake_state, active_workout_id=wid, session_active=True, distance=600.0)
        srv._update_interval_state()
        assert fake_state["interval_phase"] == "done"

    def test_rest_phase_after_work_complete(self, server, tmp_db, monkeypatch):
        import db.workouts as wk_mod
        monkeypatch.setattr(wk_mod, "_DB_PATH", tmp_db)
        wid = wk_mod.save_workout("TestRest", [
            {"type": "distance", "meters": 500, "rest_secs": 60},
            {"type": "distance", "meters": 500, "rest_secs": 0},
        ])
        srv, fake_state = server
        monkeypatch.setattr(srv, "get_workout", lambda w: wk_mod.get_workout(w))

        # First detection: rest stamp is set to elapsed=300, full 60s remaining.
        _set_state(fake_state, active_workout_id=wid, session_active=True,
                   distance=550.0, elapsed=300.0)
        srv._update_interval_state()
        assert fake_state["interval_phase"] == "rest"
        assert fake_state["interval_remaining"] == 60  # full rest at first detection

        # Mid-rest: 30s later (elapsed=330), stamp already set → 30s remaining.
        fake_state["elapsed"] = 330.0
        srv._update_interval_state()
        assert fake_state["interval_phase"] == "rest"
        assert fake_state["interval_remaining"] == 30  # 60 - 30 elapsed in rest

        # Rest complete: elapsed=361 → moves to next interval.
        fake_state["elapsed"] = 361.0
        srv._update_interval_state()
        assert fake_state["interval_index"] == 1
        assert fake_state["interval_phase"] == "work"


class TestUpdateIntervalStateTime:
    """Time-based interval tracking."""

    def test_within_first_time_interval(self, server, tmp_db, monkeypatch):
        import db.workouts as wk_mod
        monkeypatch.setattr(wk_mod, "_DB_PATH", tmp_db)
        wid = wk_mod.save_workout("TimeTest", [
            {"type": "time", "seconds": 300, "rest_secs": 0},
        ])
        srv, fake_state = server
        monkeypatch.setattr(srv, "get_workout", lambda w: wk_mod.get_workout(w))
        _set_state(fake_state, active_workout_id=wid, session_active=True, elapsed=120.0)
        srv._update_interval_state()
        assert fake_state["interval_index"] == 0
        assert fake_state["interval_phase"] == "work"
        assert fake_state["interval_remaining"] == 180  # 300 - 120

    def test_second_time_interval(self, server, tmp_db, monkeypatch):
        import db.workouts as wk_mod
        monkeypatch.setattr(wk_mod, "_DB_PATH", tmp_db)
        wid = wk_mod.save_workout("TimeTest2", [
            {"type": "time", "seconds": 60,  "rest_secs": 0},
            {"type": "time", "seconds": 120, "rest_secs": 0},
        ])
        srv, fake_state = server
        monkeypatch.setattr(srv, "get_workout", lambda w: wk_mod.get_workout(w))
        # Past first interval (60s), 90s elapsed → second interval, 30s remaining
        _set_state(fake_state, active_workout_id=wid, session_active=True, elapsed=90.0)
        srv._update_interval_state()
        assert fake_state["interval_index"] == 1
        assert fake_state["interval_phase"] == "work"
        assert fake_state["interval_remaining"] == 90  # (60+120) - 90
