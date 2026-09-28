# SPDX-License-Identifier: GPL-3.0-or-later
"""A trace of what the app does, for the tests: one JSON object per line in the file named by
MESHSAT_APP_TRACE (toasts, routes opened, calls to the Bridge with their status and time,
commands run). Off without the variable, and never in the way: a write that fails is dropped."""
import json
import os
import threading
import time

PATH = os.environ.get("MESHSAT_APP_TRACE", "")
_lock = threading.Lock()


def on() -> bool:
    return bool(PATH)


def event(kind: str, **fields) -> None:
    if not PATH:
        return
    record = {"t": round(time.time(), 3), "kind": kind}
    record.update(fields)
    try:
        with _lock, open(PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass
