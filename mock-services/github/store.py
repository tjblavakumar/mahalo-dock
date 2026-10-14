"""JSON-backed persistent store for the Mock GitHub service.

On first run (or when MOCK_RESET_ON_START=true) the store is initialized from
seed_data.py and written to data.json. On subsequent runs the data is loaded
from data.json, so any changes made at runtime (e.g. created branches/commits)
persist across restarts. data.json is the source of truth, rewritten on save().
"""

import copy
import json
import os
import threading

import seed_data

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
_RESET = os.environ.get("MOCK_RESET_ON_START", "false").strip().lower() == "true"
_lock = threading.Lock()

# Collections managed by the store. BRANCHES and CONTRIBUTOR_STATS are dicts;
# REPOS, PULL_REQUESTS, COMMITS are lists. main.py mutates these in place and
# calls save() afterwards.
REPOS: list = []
BRANCHES: dict = {}
PULL_REQUESTS: list = []
COMMITS: list = []
CONTRIBUTOR_STATS: dict = {}


def _seed_snapshot() -> dict:
    return {
        "REPOS": copy.deepcopy(seed_data.REPOS),
        "BRANCHES": copy.deepcopy(seed_data.BRANCHES),
        "PULL_REQUESTS": copy.deepcopy(seed_data.PULL_REQUESTS),
        "COMMITS": copy.deepcopy(seed_data.COMMITS),
        "CONTRIBUTOR_STATS": copy.deepcopy(seed_data.CONTRIBUTOR_STATS),
    }


def _apply(data: dict) -> None:
    """Populate the in-memory collections in place (preserving identity)."""
    REPOS[:] = data.get("REPOS", [])
    BRANCHES.clear()
    BRANCHES.update(data.get("BRANCHES", {}))
    PULL_REQUESTS[:] = data.get("PULL_REQUESTS", [])
    COMMITS[:] = data.get("COMMITS", [])
    CONTRIBUTOR_STATS.clear()
    CONTRIBUTOR_STATS.update(data.get("CONTRIBUTOR_STATS", {}))


def save() -> None:
    """Persist the current in-memory state to data.json (atomic write)."""
    with _lock:
        snapshot = {
            "REPOS": REPOS,
            "BRANCHES": BRANCHES,
            "PULL_REQUESTS": PULL_REQUESTS,
            "COMMITS": COMMITS,
            "CONTRIBUTOR_STATS": CONTRIBUTOR_STATS,
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
        _apply(_seed_snapshot())
        save()


# Initialize on import.
load()
