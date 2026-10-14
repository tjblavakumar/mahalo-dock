"""JSON-backed persistent store for the Mock Jira service.

On first run (or when MOCK_RESET_ON_START=true) the store is initialized from
seed_data.py and written to data.json. On subsequent runs the data is loaded
from data.json, so any changes made at runtime (e.g. created stories) persist
across restarts. Reads stay in-memory-fast; data.json is the source of truth
that is rewritten on every save().
"""

import copy
import json
import os
import threading

import seed_data

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
_RESET = os.environ.get("MOCK_RESET_ON_START", "false").strip().lower() == "true"
_lock = threading.Lock()

# Collections managed by the store. main.py imports these names and mutates them
# in place; call save() afterwards to persist.
DEVELOPERS: list = []
PROJECTS: list = []
SPRINTS: list = []
STORIES: list = []


def _seed_snapshot() -> dict:
    """A deep copy of the seed data so we never mutate the module defaults."""
    return {
        "DEVELOPERS": copy.deepcopy(seed_data.DEVELOPERS),
        "PROJECTS": copy.deepcopy(seed_data.PROJECTS),
        "SPRINTS": copy.deepcopy(seed_data.SPRINTS),
        "STORIES": copy.deepcopy(seed_data.STORIES),
    }


def _apply(data: dict) -> None:
    """Populate the in-memory collections in place (preserving identity)."""
    DEVELOPERS[:] = data.get("DEVELOPERS", [])
    PROJECTS[:] = data.get("PROJECTS", [])
    SPRINTS[:] = data.get("SPRINTS", [])
    STORIES[:] = data.get("STORIES", [])


def save() -> None:
    """Persist the current in-memory state to data.json (atomic write)."""
    with _lock:
        snapshot = {
            "DEVELOPERS": DEVELOPERS,
            "PROJECTS": PROJECTS,
            "SPRINTS": SPRINTS,
            "STORIES": STORIES,
        }
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
        # Corrupt/unreadable store: fall back to seed and rewrite.
        _apply(_seed_snapshot())
        save()


# Initialize on import.
load()
