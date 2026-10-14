"""JSON-backed persistent store for the Mock ServiceNow service.

On first run (or when MOCK_RESET_ON_START=true) the store is initialized from
seed_data.py and written to data.json. On subsequent runs the data is loaded
from data.json, so runtime changes (e.g. created incidents) persist across
restarts. data.json is the source of truth, rewritten on save().
"""

import copy
import json
import os
import threading

import seed_data

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
_RESET = os.environ.get("MOCK_RESET_ON_START", "false").strip().lower() == "true"
_lock = threading.Lock()

SERVICES: list = []
DEPLOYMENTS: list = []
INCIDENTS: list = []


def _seed_snapshot() -> dict:
    return {
        "SERVICES": copy.deepcopy(seed_data.SERVICES),
        "DEPLOYMENTS": copy.deepcopy(seed_data.DEPLOYMENTS),
        "INCIDENTS": copy.deepcopy(seed_data.INCIDENTS),
    }


def _apply(data: dict) -> None:
    """Populate the in-memory collections in place (preserving identity)."""
    SERVICES[:] = data.get("SERVICES", [])
    DEPLOYMENTS[:] = data.get("DEPLOYMENTS", [])
    INCIDENTS[:] = data.get("INCIDENTS", [])


def save() -> None:
    """Persist the current in-memory state to data.json (atomic write)."""
    with _lock:
        snapshot = {
            "SERVICES": SERVICES,
            "DEPLOYMENTS": DEPLOYMENTS,
            "INCIDENTS": INCIDENTS,
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
