# SPDX-License-Identifier: GPL-3.0-or-later
"""The Bridge's event stream, for what cannot wait for the next poll: a text that arrives, a
send that fails. `/api/events` is server-sent events, one `data: {json}` line per event; the
Bridge keeps 32 events for a slow reader and restarts with every package install, so the
reader reconnects by itself and never assumes it saw everything (the polls remain the truth).
No GTK here: the notifier runs without a window, and the tests without a display."""
import json
import threading
import time
import urllib.error
import urllib.request

from . import api


def parse_line(line: bytes | str) -> dict | None:
    """One line of the stream as an event, None for anything that is not one."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", "replace")
    line = line.strip()
    if not line.startswith("data:"):
        return None
    try:
        event = json.loads(line[5:].strip())
    except ValueError:
        return None
    return event if isinstance(event, dict) and event.get("type") else None


def inbound_text(event: dict) -> dict | None:
    """The text a person should be told about, out of an event: {"lane", "from", "text"}.
    Mesh texts come as `packet` events (one per text, whatever the number of hops it was
    heard over), satellite and other gateway texts as `inbound`, SMS as `sms_received`."""
    kind = event.get("type")
    data = event.get("data") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    if kind == "packet":
        if data.get("dir") != "rx" or data.get("portnum_name") != "TEXT_MESSAGE_APP" or not data.get("text"):
            return None
        lane = {"lora": "mesh", "iridium": "satellite", "sbd": "satellite", "imt": "satellite", "cellular": "sms", "sms": "sms"}.get(data.get("bearer", "lora"), "mesh")
        return {"lane": lane, "from": data.get("from") or "", "text": data["text"]}
    if kind == "inbound":
        text = data.get("text") or data.get("decoded_text") or event.get("message") or ""
        if not text:
            return None
        source = str(data.get("source") or data.get("interface") or data.get("gateway") or "")
        lane = "sms" if "cell" in source or "sms" in source else "satellite" if "irid" in source or "sbd" in source or "imt" in source else "mesh"
        return {"lane": lane, "from": data.get("from") or data.get("sender") or data.get("imei") or "", "text": text}
    if kind == "sms_received":
        text = data.get("text") or event.get("message") or ""
        if not text:
            return None
        return {"lane": "sms", "from": data.get("phone") or data.get("sender") or data.get("from") or "", "text": text}
    return None


class Seen:
    """Drops a text already told about: the same words from the same sender within two
    minutes (a text heard again through a relay, or reported by two event kinds)."""

    def __init__(self, window: float = 120.0):
        self.window = window
        self.items = {}

    def new(self, sender: str, text: str, now: float | None = None) -> bool:
        now = now or time.time()
        for key, at in list(self.items.items()):
            if now - at > self.window:
                del self.items[key]
        key = (sender, text)
        if key in self.items:
            return False
        self.items[key] = now
        return True


class EventStream:
    """Reads the stream on a thread and hands every event to `on_event` (called on that
    thread); reconnects after 1, 2, 4 … 30 s."""

    def __init__(self, on_event, url: str | None = None, opener=None):
        self.on_event = on_event
        self.url = url or api.BRIDGE + "/api/events"
        self.opener = opener or (lambda url: urllib.request.urlopen(url, timeout=90))
        self.connected = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def read(self, response) -> None:
        """Every event of one connection, until it ends."""
        for line in response:
            if self._stop.is_set():
                return
            event = parse_line(line)
            if event is None:
                continue
            self.connected = True
            if event.get("type") != "connected_to_stream":
                self.on_event(event)

    def _run(self) -> None:
        wait = 1.0
        while not self._stop.is_set():
            try:
                with self.opener(self.url) as response:
                    wait = 1.0
                    self.read(response)
            except (OSError, ValueError, urllib.error.URLError):
                pass
            self.connected = False
            self._stop.wait(wait)
            wait = min(wait * 2, 30.0)
