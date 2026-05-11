"""Tests for db/strive.py — HR zone assignment and Strive Score."""
import sqlite3
import pytest
import db.strive as strive_mod
from db.strive import calculate_strive_score, ZONES

SESSION_ID = 42
MAX_HR = 200


def _make_stroke_log(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS stroke_log ("
        "id INTEGER PRIMARY KEY, session_id INTEGER, "
        "elapsed_secs REAL, hr_bpm INTEGER)"
    )
    conn.commit()


def _insert_hr_rows(conn, session_id, rows):
    """rows: list of (elapsed_secs, hr_bpm)."""
    conn.executemany(
        "INSERT INTO stroke_log (session_id, elapsed_secs, hr_bpm) VALUES (?, ?, ?)",
        [(session_id, e, hr) for e, hr in rows],
    )
    conn.commit()


class TestCalculateStriveScore:
    def test_no_hr_data_returns_zero(self, tmp_db, monkeypatch):
        monkeypatch.setattr(strive_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_stroke_log(conn)
        score, zone_times = calculate_strive_score(SESSION_ID, MAX_HR)
        assert score == 0
        assert zone_times == [0, 0, 0, 0, 0]

    def test_z1_only_low_score(self, tmp_db, monkeypatch):
        monkeypatch.setattr(strive_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_stroke_log(conn)
            # HR at 50% max = Z1 for 60 seconds
            hr = int(MAX_HR * 0.50)
            _insert_hr_rows(conn, SESSION_ID, [(60, hr)])
        score, zone_times = calculate_strive_score(SESSION_ID, MAX_HR)
        # Z1 multiplier=1, 60s → score = 60×1/60 = 1.0
        assert score == 1.0
        assert zone_times[0] == 60
        assert all(t == 0 for t in zone_times[1:])

    def test_z4_high_score(self, tmp_db, monkeypatch):
        monkeypatch.setattr(strive_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_stroke_log(conn)
            # HR at 85% max = Z4, multiplier=8, 60 seconds
            hr = int(MAX_HR * 0.85)
            _insert_hr_rows(conn, SESSION_ID, [(60, hr)])
        score, zone_times = calculate_strive_score(SESSION_ID, MAX_HR)
        # Z4: 60s × 8 / 60 = 8.0
        assert score == 8.0
        assert zone_times[3] == 60

    def test_zone_boundary_at_60_pct_is_z2(self, tmp_db, monkeypatch):
        monkeypatch.setattr(strive_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_stroke_log(conn)
            hr = int(MAX_HR * 0.60)  # exactly at Z2 lower bound
            _insert_hr_rows(conn, SESSION_ID, [(10, hr)])
        _, zone_times = calculate_strive_score(SESSION_ID, MAX_HR)
        assert zone_times[1] == 10   # Z2
        assert zone_times[0] == 0    # not Z1

    def test_z5_max_hr_or_above(self, tmp_db, monkeypatch):
        monkeypatch.setattr(strive_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_stroke_log(conn)
            hr = MAX_HR  # 100% max HR → Z5
            _insert_hr_rows(conn, SESSION_ID, [(30, hr)])
        _, zone_times = calculate_strive_score(SESSION_ID, MAX_HR)
        assert zone_times[4] == 30

    def test_multiple_zones_accumulate_correctly(self, tmp_db, monkeypatch):
        monkeypatch.setattr(strive_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_stroke_log(conn)
            _insert_hr_rows(conn, SESSION_ID, [
                (30,  int(MAX_HR * 0.55)),   # Z1 for 30s
                (60,  int(MAX_HR * 0.65)),   # Z2 for 30s
                (120, int(MAX_HR * 0.75)),   # Z3 for 60s
            ])
        score, zone_times = calculate_strive_score(SESSION_ID, MAX_HR)
        assert zone_times[0] == 30
        assert zone_times[1] == 30
        assert zone_times[2] == 60
        # score = (30×1 + 30×2 + 60×4) / 60 = (30+60+240)/60 = 5.5
        assert score == 5.5
