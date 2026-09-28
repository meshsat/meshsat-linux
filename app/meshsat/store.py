# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app keeps on disk, as the Android app keeps its own database: the preferences, the
texts it sent, the node names it has heard. Every file is JSON, written to a temporary file
and renamed into place, so a crash mid-write never leaves half a file; a file that cannot be
read counts as empty and is kept aside rather than overwritten, so nothing the user typed is
lost to one bad byte."""
import json
import os
import threading
import time

try:
    from gi.repository import GLib
except (ImportError, ValueError):  # the unit tests on a machine without GTK
    GLib = None


def config_dir() -> str:
    if GLib is not None:
        return GLib.get_user_config_dir()
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")


def state_dir() -> str:
    if GLib is not None:
        return GLib.get_user_state_dir()
    return os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")


def read_json(path: str, default):
    """The file's JSON, or `default` when there is no file. A file that is not JSON is moved
    to `<path>.broken` (once) and counts as `default`."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        try:
            os.replace(path, path + ".broken")
        except OSError:
            pass
        return default


def write_json(path: str, data) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(path + ".tmp", path)
        return True
    except OSError:
        return False


class Prefs:
    """The app's preferences (night mode, the position typed in, the emergency contacts, the
    name in an SOS, the order of Home): one dict, written a second after the last change, so
    a name typed letter by letter is one write, not twenty."""

    DELAY = 1.0

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config_dir(), "meshsat", "app.json")
        loaded = read_json(self.path, {})
        self.data = loaded if isinstance(loaded, dict) else {}
        self._lock = threading.Lock()
        self._timer = None

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, **values) -> None:
        with self._lock:
            self.data.update(values)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.DELAY, self.flush)
            self._timer.daemon = True
            self._timer.start()

    def flush(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            data = dict(self.data)
        write_json(self.path, data)


# The texts this app sent, one JSON record per line (the Bridge keeps a sent mesh text only in
# its packet feed, in memory, gone at its next start, never in the message store). The last
# KEEP records are kept; the file is rewritten to that length when it grows past it.
KEEP = 2000


class SentLog:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(state_dir(), "meshsat", "sent.jsonl")
        self._records = None
        self._stamp = None

    def _load(self) -> list:
        try:
            stamp = os.stat(self.path).st_mtime_ns
        except OSError:
            self._records, self._stamp = [], None
            return self._records
        if self._records is not None and stamp == self._stamp:
            return self._records
        records = []
        try:
            with open(self.path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue  # one bad line loses that line, not the history
                    if isinstance(record, dict):
                        records.append(record)
        except OSError:
            pass
        if len(records) > KEEP:
            records = records[-KEEP:]
            self._rewrite(records)
        self._records, self._stamp = records, stamp
        return records

    def _rewrite(self, records: list) -> None:
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record) + "\n")
            os.replace(self.path + ".tmp", self.path)
        except OSError:
            pass

    def read(self) -> list:
        return list(self._load())

    def append(self, record: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except OSError:
            pass
        self._records = None


def sent_record(text: str, to: str | None, lane: str, me: str | None, everyone: str = "!ffffffff") -> dict:
    """A text this app just sent, in the shape of the Bridge's stored messages."""
    return {"id": -int(time.time() * 1000), "from_node": me or "", "to_node": to or everyone, "portnum": 1, "portnum_name": "TEXT_MESSAGE_APP",
            "decoded_text": text, "rx_time": int(time.time()), "direction": "tx", "transport": {"satellite": "iridium", "sms": "sms"}.get(lane, "radio"),
            "delivery_status": "sent", "local": True}
