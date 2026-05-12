"""Tests for db/streak.py — consecutive training day streak."""
import sqlite3
import time
from datetime import date, timedelta

import pytest
import db.streak as streak_mod
from db.streak import get_streak

USER_ID = 1


def _make_sessions(conn, days_ago_list):
    """Insert completed sessions at given day offsets from today."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "id INTEGER PRIMARY KEY, user_id INTEGER, started_at REAL, status TEXT)"
    )
    today = date.today()
    for offset in days_ago_list:
        d = today - timedelta(days=offset)
        ts = time.mktime(d.timetuple())
        conn.execute(
            "INSERT INTO sessions (user_id, started_at, status) VALUES (?, ?, 'complete')",
            (USER_ID, ts),
        )
    conn.commit()


class TestGetStreak:
    def test_no_sessions_returns_zero(self, tmp_db, monkeypatch):
        monkeypatch.setattr(streak_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_sessions(conn, [])
        assert get_streak(USER_ID) == (0, 0)

    def test_single_session_today(self, tmp_db, monkeypatch):
        monkeypatch.setattr(streak_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_sessions(conn, [0])
        current, longest = get_streak(USER_ID)
        assert current == 1
        assert longest == 1

    def test_three_consecutive_days(self, tmp_db, monkeypatch):
        monkeypatch.setattr(streak_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_sessions(conn, [0, 1, 2])
        current, longest = get_streak(USER_ID)
        assert current == 3
        assert longest == 3

    def test_gap_breaks_current_streak(self, tmp_db, monkeypatch):
        monkeypatch.setattr(streak_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            # today and yesterday, then a 2-day gap, then 5 days ago
            _make_sessions(conn, [0, 1, 5, 6, 7])
        current, longest = get_streak(USER_ID)
        assert current == 2
        assert longest == 3

    def test_longest_streak_ignores_gap(self, tmp_db, monkeypatch):
        monkeypatch.setattr(streak_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            # 5-day historical run, then gap, then 1 day today
            _make_sessions(conn, [0, 10, 11, 12, 13, 14])
        current, longest = get_streak(USER_ID)
        assert current == 1
        assert longest == 5

    def test_multiple_sessions_same_day_count_once(self, tmp_db, monkeypatch):
        monkeypatch.setattr(streak_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            # Three sessions today (should still count as 1 day)
            _make_sessions(conn, [0, 0, 0])
        current, _ = get_streak(USER_ID)
        assert current == 1

    def test_yesterday_only_gives_streak_1(self, tmp_db, monkeypatch):
        monkeypatch.setattr(streak_mod, "_DB_PATH", tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            _make_sessions(conn, [1])
        current, _ = get_streak(USER_ID)
        assert current == 1
