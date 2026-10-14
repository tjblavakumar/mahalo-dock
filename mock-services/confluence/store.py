"""JSON-backed persistent store for the Mock Confluence service.

On first run (or when MOCK_RESET_ON_START=true) the store is initialized from
seed_data.py and written to data.json. On subsequent runs the data is loaded
from data.json. data.json is the source of truth, rewritten on save().
"""

import copy
import json
import os
import threading

import seed_data

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
_RESET = os.environ.get("MOCK_RESET_ON_START", "false").strip().lower() == "true"
_lock = threading.Lock()

SPACES: list = []
PAGES: list = []


def _seed_snapshot() -> dict:
    return {
        "SPACES": copy.deepcopy(seed_data.SPACES),
        "PAGES": copy.deepcopy(seed_data.PAGES),
    }


def _apply(data: dict) -> None:
    SPACES[:] = data.get("SPACES", [])
    PAGES[:] = data.get("PAGES", [])


def save() -> None:
    """Persist the current in-memory state to data.json (atomic write)."""
    with _lock:
        snapshot = {"SPACES": SPACES, "PAGES": PAGES}
        tmp = _DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        os.replace(tmp, _DATA_FILE)


def load() -> None:
    """Load data.json, or seed it from seed_data.py on first run / reset."""
    if _RESET or not os.path.exists(_DATA_FILE):
        _apply(_seed_snapshot())
        save()
        return
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            _apply(json.load(f))
    except (json.JSONDecodeError, OSError):
        _apply(_seed_snapshot())
        save()


# Initialize on import.
load()
