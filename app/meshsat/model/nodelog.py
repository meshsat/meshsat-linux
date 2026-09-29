# SPDX-License-Identifier: GPL-3.0-or-later
"""The node's log (ble/NodeLog.kt, ui/screens/NodeLogScreen.kt): lines "HH:mm:ss LEVEL [source]
message", newest last, at most 2000 kept; while paused, new lines are held and appended on
resume. On this phone with the LoRa back cover the node is meshtasticd, and its log is the
service's journal; its lines are read into the same shape. A node over Bluetooth sends its log
over the link while security.debug_log_api_enabled is set, and the Bridge relays it (MESHSAT-1406).
Pure."""
import re
import time

CAPACITY = 2000
LEVELS = {"TRACE": "TRACE", "DEBUG": "DEBUG", "INFO": "INFO", "WARN": "WARN", "WARNING": "WARN", "ERROR": "ERROR", "CRIT": "CRIT", "CRITICAL": "CRIT"}
TONES = {"ERROR": "red", "CRIT": "red", "WARN": "amber", "DEBUG": "muted", "TRACE": "muted"}
SHARE_EMPTY = "Nothing to share yet."
COVER_NOTE = "The node runs on this phone: this is its own log, as its service writes it. Newest at the bottom."
NOT_CONNECTED = "Connect your MeshSat node first."
STREAMING_NOTE = "The node sends every log line while this switch is on; it may drop lines in a burst. Newest at the bottom."
SWITCH = "Stream the node's log"
FOLLOW_FAILED = "The node's log could not be followed: " + "the node refused the subscription."
# MeshtasticBle.setNodeDebugLog's reasons, for the Bridge's 503 and 409.
NODE_GONE = "The node is not connected."
NO_SECURITY = "The node has not sent its security settings yet; try again in a moment."
OFF_NOTE = "Sets the node's debug log over Bluetooth (security.debug_log_api_enabled); a setting the node keeps. The node restarts once to apply it, and the link comes back by itself."  # noqa: E501

# meshtasticd writes "INFO  | 12:04:09 1234 [Router] Received text msg ..." (level, the node's
# clock, its uptime in seconds, the thread in brackets).
DAEMON_LINE = re.compile(r"^\s*(?P<level>[A-Z]+)\s*\|\s*(?P<clock>\d\d:\d\d:\d\d)\s+(?:[\d.]+\s+)?(?:\[(?P<source>[^\]]*)\]\s*)?(?P<message>.*)$")


def parse_daemon(line: str, received: float) -> dict | None:
    """One meshtasticd journal line as a log line, or None for a line that is not one."""
    text = line.rstrip("\r\n")
    if not text.strip():
        return None
    match = DAEMON_LINE.match(text)
    if not match:
        return {"clock": time.strftime("%H:%M:%S", time.localtime(received)), "level": None, "source": "", "message": text.strip(), "received": received}
    level = LEVELS.get(match.group("level"))
    return {"clock": match.group("clock"), "level": level, "source": (match.group("source") or "").strip(), "message": match.group("message").strip(), "received": received}


def received_at(stamp: str, fallback: float) -> float:
    """The Bridge's receive time (RFC 3339, nanoseconds, UTC) as Unix seconds."""
    try:
        import calendar  # noqa: PLC0415

        whole = time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
        return calendar.timegm(whole)
    except (TypeError, ValueError):
        return fallback


def parse_record(record: dict, received: float) -> dict:
    """A LogRecord as the Bridge relays it from a node over Bluetooth (GET /api/mesh/radio-log,
    MESHSAT-1406: {seq, received_at, radio_time, level, source, message}): the node's time when
    it has one, else when the Bridge received it."""
    at = int(record.get("radio_time") or record.get("time") or 0)
    got = received_at(record.get("received_at") or "", received)
    clock = time.strftime("%H:%M:%S", time.localtime(at if at > 0 else got))
    level = LEVELS.get(str(record.get("level") or "").upper())
    return {"clock": clock, "level": level, "source": str(record.get("source") or ""), "message": str(record.get("message") or "").rstrip("\r\n"), "received": got}


def format_line(line: dict) -> str:
    """"HH:mm:ss LEVEL [source] message": the node's time when it has one, else the phone's."""
    out = line["clock"]
    if line.get("level"):
        out += " " + line["level"]
    if line.get("source"):
        out += f" [{line['source']}]"
    return out + " " + line.get("message", "")


def tone(line: dict) -> str:
    return TONES.get(line.get("level") or "", "primary")


class Buffer:
    """The lines kept for the screen, newest last, at most `capacity`; while paused, new lines
    are held and appended on resume, so nothing that arrived during a look is lost."""

    def __init__(self, capacity: int = CAPACITY):
        self.capacity = capacity
        self.kept = []
        self.held = []
        self.paused = False

    def add(self, lines: list) -> None:
        (self.held if self.paused else self.kept).extend(lines)
        self._trim()

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        self.kept.extend(self.held)
        self.held = []
        self._trim()

    def clear(self) -> None:
        self.kept, self.held = [], []

    def text(self) -> str:
        return "\n".join(format_line(l) for l in self.kept + self.held)

    def _trim(self) -> None:
        if len(self.kept) > self.capacity:
            del self.kept[: len(self.kept) - self.capacity]
        if len(self.held) > self.capacity:
            del self.held[: len(self.held) - self.capacity]


def share_name(now: float | None = None) -> str:
    return time.strftime("meshsat-node-log-%Y%m%d-%H%M.txt", time.localtime(now if now is not None else time.time()))
