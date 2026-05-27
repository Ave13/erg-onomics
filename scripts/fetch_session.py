#!/usr/bin/env python3
"""Fetch rowing session data from the erg to data/session_{id}.json.

Usage:
    python scripts/fetch_session.py                       # interactive
    python scripts/fetch_session.py --session 42
    python scripts/fetch_session.py --all
    python scripts/fetch_session.py --host 10.0.0.1:8501
    ERG_HOST=http://192.168.0.224:8501 python scripts/fetch_session.py
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

DEFAULT_HOST = "http://192.168.0.224:8501"
DATA_DIR = Path(__file__).parent.parent / "data"


def _get(host: str, path: str):
    url = f"{host}{path}"
    try:
        with urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except URLError as e:
        print(f"Error: {url} — {e}", file=sys.stderr)
        sys.exit(1)


def fetch_and_save(host: str, session_id: int) -> Path:
    meta = _get(host, f"/api/summary/{session_id}")
    strokes = _get(host, f"/api/summary/{session_id}/strokes")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"session_{session_id}.json"
    out.write_text(json.dumps({"session_id": session_id, "meta": meta, "strokes": strokes}, indent=2))
    print(f"Saved {len(strokes)} strokes → {out}")
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch rowing session data from the erg.")
    parser.add_argument("--host", default=os.getenv("ERG_HOST", DEFAULT_HOST),
                        help="Erg server URL (default: ERG_HOST env or 192.168.0.224:8501)")
    parser.add_argument("--session", type=int, metavar="ID", help="Fetch a specific session ID")
    parser.add_argument("--all", dest="all_sessions", action="store_true",
                        help="Fetch all recent sessions (up to 30)")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    if "://" not in host:
        host = "http://" + host

    if args.all_sessions:
        for s in _get(host, "/api/history"):
            fetch_and_save(host, s["id"])
        return

    if args.session:
        fetch_and_save(host, args.session)
        return

    # Interactive
    sessions = _get(host, "/api/history")
    if not sessions:
        print("No completed sessions found.")
        return

    print("\nRecent sessions:")
    for i, s in enumerate(sessions, 1):
        print(f"  {i:2d}.  [{s['id']:>4}]  {s['label']}")
    print()

    raw = input("Enter number (or session ID, or 'all'): ").strip()
    if raw.lower() == "all":
        for s in sessions:
            fetch_and_save(host, s["id"])
        return

    try:
        n = int(raw)
        session_id = sessions[n - 1]["id"] if 1 <= n <= len(sessions) else n
    except (ValueError, IndexError):
        print(f"Invalid choice: {raw!r}", file=sys.stderr)
        sys.exit(1)

    fetch_and_save(host, session_id)


if __name__ == "__main__":
    main()
