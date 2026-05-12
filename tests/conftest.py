"""Shared pytest fixtures."""
import sys
import types
import sqlite3
import pytest
from unittest.mock import MagicMock


# ── Stub hardware-dependent packages before any test module imports them ──────

def _stub(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

# bleak (BLE library) — not installed in test environment
_bleak = _stub("bleak")
_bleak.BleakClient  = MagicMock
_bleak.BleakScanner = MagicMock

# bless (FTMS peripheral library) — optional at runtime too
_stub("bless")


# ── Database fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Path to a fresh temporary SQLite database."""
    return str(tmp_path / "test_rowing.db")


@pytest.fixture
def tmp_db_conn(tmp_db):
    """Open connection to the temp DB (auto-closed after test)."""
    with sqlite3.connect(tmp_db) as conn:
        yield conn
