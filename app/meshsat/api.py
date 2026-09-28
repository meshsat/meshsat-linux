# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app knows, and where it comes from.

The MeshSat Bridge on this device serves its API on 127.0.0.1:6050; the node (meshtasticd)
is reached only through the Bridge, never on its own port (the daemon keeps one TCP client
and would drop the Bridge for us). The node's service state comes from systemd, the radio
watchdog's verdict from /run/meshsat-node/status. Everything is polled on a thread and
handed to the interface on the main loop.
"""
import datetime
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

from gi.repository import GLib

BRIDGE = os.environ.get("MESHSAT_APP_BRIDGE", "http://127.0.0.1:6050")
STATUS_PATH = os.environ.get("MESHSAT_APP_STATUS", "/run/meshsat-node/status")
# What this app sent, one JSON record per line: the Bridge keeps a sent mesh text only in its
# packet feed (in memory, gone at its next start), never in the message store, so the app keeps
# its own record, as the Android app keeps its own database.
SENT_LOG = os.path.join(GLib.get_user_state_dir(), "meshsat", "sent.jsonl")
EVERYONE = "!ffffffff"


def get(path: str, timeout: float = 2.0):
    """A JSON answer of the Bridge, or None when it does not answer."""
    try:
        with urllib.request.urlopen(BRIDGE + path, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def post(path: str, body: dict | None = None, timeout: float = 8.0, method: str = "POST"):
    data = json.dumps(body or {}).encode()
    request = urllib.request.Request(BRIDGE + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            return json.load(error)
        except ValueError:
            return {"error": str(error)}
    except (OSError, ValueError, urllib.error.URLError) as error:
        return {"error": str(error)}


def put(path: str, body: dict | None = None, timeout: float = 8.0):
    return post(path, body, timeout, method="PUT")


def record_sent(text: str, to: str | None, lane: str, me: str | None) -> dict:
    """A text this app just sent, in the shape of the Bridge's stored messages, appended to
    the sent log."""
    record = {"id": -int(time.time() * 1000), "from_node": me or "", "to_node": to or EVERYONE, "portnum": 1, "portnum_name": "TEXT_MESSAGE_APP",
              "decoded_text": text, "rx_time": int(time.time()), "direction": "tx", "transport": {"satellite": "iridium", "sms": "sms"}.get(lane, "radio"),
              "delivery_status": "sent", "local": True}
    try:
        os.makedirs(os.path.dirname(SENT_LOG), exist_ok=True)
        with open(SENT_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        pass
    return record


def read_sent() -> list:
    try:
        with open(SENT_LOG, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError):
        return []


def packet_texts(packets: list, me: str | None) -> list:
    """The texts the Bridge sent over the mesh, out of its packet feed (any client of the
    Bridge, this app included), as message records."""
    out = []
    for p in packets or []:
        if p.get("dir") != "tx" or p.get("portnum_name") != "TEXT_MESSAGE_APP" or not p.get("text"):
            continue
        # Go's RFC 3339 with as many fraction digits as it has (none to nine): the fraction goes.
        stamp = re.sub(r"\.\d+", "", str(p.get("time", "")))
        try:
            when = datetime.datetime.fromisoformat(stamp).timestamp()
        except ValueError:
            continue
        to = p.get("to") or EVERYONE
        out.append({"id": -int(when), "from_node": p.get("from") or me or "", "to_node": EVERYONE if to == "broadcast" else to, "portnum": 1, "portnum_name": "TEXT_MESSAGE_APP",
                    "decoded_text": p["text"], "rx_time": int(when), "direction": "tx", "transport": "radio", "delivery_status": "sent"})
    return out


def merge_messages(stored: list, sent: list, packets: list) -> list:
    """The Bridge's store, this app's sent log and the feed's sent texts as one list, newest
    first; a feed entry that repeats a logged send (same text within two minutes) is dropped."""
    out = list(stored) + list(sent)
    for p in packets:
        if any(m.get("direction") == "tx" and m.get("decoded_text") == p["decoded_text"] and abs((m.get("rx_time") or 0) - p["rx_time"]) < 120 for m in out):
            continue
        out.append(p)
    out.sort(key=lambda m: m.get("rx_time") or 0, reverse=True)
    return out


def unit_active(unit: str) -> bool:
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def watchdog_status() -> dict:
    try:
        with open(STATUS_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


class State:
    """One snapshot of everything the screens show. Fields are None until first polled."""

    def __init__(self):
        self.bridge = None  # /api/status, None = Bridge not answering
        self.nodes = []
        self.messages = []
        self.message_stats = None
        self.modem = None  # /api/iridium/modem
        self.signal = None  # /api/iridium/signal
        self.hub = None  # /api/routing/hub
        self.sos = None
        self.deadman = None
        self.keys = None
        self.cellular = None  # /api/cellular/status: the phone's SIM, through ModemManager
        self.sms = []  # /api/cellular/sms: texts sent and received through the SIM
        self.contacts = []  # emergency contacts, [{"name", "phone"}], kept by the app as Android does
        self.sos_name = ""
        self.node_service = False
        self.bridge_service = False
        self.watchdog = {}
        self.polled_at = 0.0
        self.unreachable_since = None  # when the Bridge lost the node, for the banner
        # Where this phone is, as Android's LocationFixes: geoclue's fix (lat, lon, accuracy_m, at),
        # a position typed in (lat, lon), and what to tell the user when there is neither.
        self.phone = None
        self.entered = None
        self.location_hint = ""

    def position(self):
        """(latitude, longitude, source) for the passes and the map: the phone's fix first, then
        the node's position (a fixed one included), then the one typed in."""
        override = os.environ.get("MESHSAT_APP_POSITION", "")
        if override:
            try:
                lat, lon = (float(v) for v in override.split(",")[:2])
                return lat, lon, "MESHSAT_APP_POSITION"
            except ValueError:
                pass
        if self.phone:
            return self.phone[0], self.phone[1], "GPS" if (self.phone[2] or 1e9) <= 50 else "Network"
        own = self.own_node()
        if own and own.get("latitude") and own.get("longitude"):
            return own["latitude"], own["longitude"], "your node"
        if self.entered:
            return self.entered[0], self.entered[1], "the position you entered"
        return None

    # What the Android app calls the lanes.
    def mesh_connected(self) -> bool:
        return bool(self.bridge and self.bridge.get("connected"))

    def modem_connected(self) -> bool:
        return bool(self.modem and self.modem.get("connected"))

    def hub_configured(self) -> bool:
        return bool(self.hub and self.hub.get("url"))

    def sms_ready(self) -> bool:
        """The SIM can send: a modem, a SIM in it, and a network."""
        c = self.cellular or {}
        return bool(c.get("connected")) and c.get("sim_state") == "READY" and str(c.get("registration", "")).startswith("registered")

    def sms_reason(self) -> str | None:
        """Why SMS cannot go, in the words the Android app uses for its own reasons; None when it can."""
        c = self.cellular or {}
        if not self.bridge:
            return "Connect your node first."
        if not c.get("connected"):
            return "This phone cannot send SMS."
        state = c.get("sim_state", "")
        if state in ("NOT_INSERTED", "NO_MODEM", "", "UNKNOWN"):
            return "No SIM in this phone."
        if state == "PIN_REQUIRED":
            return "The SIM needs its PIN."
        if state == "SIM_ERROR":
            return "The SIM does not work."
        registration = str(c.get("registration", ""))
        if registration == "denied":
            return "The network refused the SIM."
        if not registration.startswith("registered"):
            return "Waiting for the network."
        return None

    def sms_today(self) -> int:
        start = time.time() - (time.time() % 86400)
        return sum(1 for m in self.sms if (m.get("timestamp") or 0) >= start)

    def contact_name(self, phone: str) -> str:
        for c in self.contacts:
            if c.get("phone") == phone and c.get("name"):
                return c["name"]
        return phone

    def own_node(self) -> dict | None:
        if not self.bridge:
            return None
        node_id = self.bridge.get("node_id")
        for node in self.nodes:
            if node.get("user_id") == node_id:
                return node
        return None

    def others(self) -> list:
        node_id = self.bridge.get("node_id") if self.bridge else None
        return [n for n in self.nodes if n.get("user_id") != node_id]

    def heard_recently(self, minutes: int = 15) -> int:
        cutoff = time.time() - minutes * 60
        return sum(1 for n in self.others() if (n.get("last_heard") or 0) >= cutoff)


class Poller:
    """Polls the Bridge every few seconds on a thread; `on_update(state)` runs on the main loop."""

    def __init__(self, on_update, interval: float = 4.0):
        self.on_update = on_update
        self.interval = interval
        self.state = State()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def poll_now(self):
        threading.Thread(target=self._poll_once, daemon=True).start()

    def _run(self):
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(self.interval)

    def _poll_once(self):
        s = self.state
        bridge = get("/api/status")
        s.bridge = bridge
        if bridge is not None:
            s.nodes = (get("/api/nodes") or {}).get("nodes") or []
            stored = (get("/api/messages?limit=200") or {}).get("messages") or []
            me = bridge.get("node_id")
            s.messages = merge_messages(stored, read_sent(), packet_texts((get("/api/packets?limit=200") or {}).get("packets") or [], me))
            s.message_stats = get("/api/messages/stats")
            s.modem = get("/api/iridium/modem")
            s.signal = get("/api/iridium/signal")
            s.hub = get("/api/routing/hub")
            s.sos = get("/api/sos/status")
            s.deadman = get("/api/deadman")
            s.keys = get("/api/keys/stats")
            s.cellular = get("/api/cellular/status")
            sms = get("/api/cellular/sms?limit=200")
            s.sms = sms if isinstance(sms, list) else []
        s.node_service = unit_active("meshtasticd.service")
        s.bridge_service = unit_active("meshsat-bridge.service")
        s.watchdog = watchdog_status()
        if s.mesh_connected():
            s.unreachable_since = None
        elif s.unreachable_since is None:
            s.unreachable_since = time.time()
        s.polled_at = time.time()
        GLib.idle_add(self.on_update, s)
