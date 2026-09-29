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
import threading
import time
import urllib.error
import urllib.request

from . import store, system, trace

try:
    from gi.repository import GLib
except (ImportError, ValueError):  # the unit tests, on a machine without GTK
    GLib = None


def state_dir() -> str:
    """Where this app keeps what it records (XDG state)."""
    return store.state_dir()


BRIDGE = os.environ.get("MESHSAT_APP_BRIDGE", "http://127.0.0.1:6050")
STATUS_PATH = os.environ.get("MESHSAT_APP_STATUS", "/run/meshsat-node/status")
EVERYONE = "!ffffffff"


class Answer:
    """One answer of the Bridge: `status` (0 when it did not answer at all), `body` (the JSON,
    or None), `error` (the Bridge's own words, or the reason there was no answer)."""

    __slots__ = ("status", "body", "error")

    def __init__(self, status: int = 0, body=None, error: str | None = None):
        self.status, self.body, self.error = status, body, error

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def down(self) -> bool:
        """No answer at all: the Bridge is not running, or not yet."""
        return self.status == 0

    def __repr__(self) -> str:
        return f"Answer({self.status}, error={self.error!r})"


def request(method: str, path: str, body: dict | None = None, timeout: float = 8.0, raw: bytes | None = None, content_type: str | None = None) -> Answer:
    """One call to the Bridge, on the calling thread. `raw` sends those bytes as they are
    (a multipart upload), under `content_type`."""
    if raw is not None:
        data, headers = raw, {"Content-Type": content_type or "application/octet-stream"}
    else:
        data = json.dumps(body or {}).encode() if method != "GET" else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(BRIDGE + path, data=data, headers=headers, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            answer = Answer(response.status, json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        try:
            parsed = json.load(error)
        except ValueError:
            parsed = None
        words = parsed.get("error") if isinstance(parsed, dict) and parsed.get("error") else f"HTTP {error.code}"
        answer = Answer(error.code, parsed, str(words))
    except ValueError:
        answer = Answer(200, None, "The Bridge answered something that is not JSON.")
    except (OSError, urllib.error.URLError) as error:
        answer = Answer(0, None, f"The Bridge is not answering: {getattr(error, 'reason', error)}")
    trace.event("http", method=method, path=path, status=answer.status, ms=int((time.time() - started) * 1000), error=answer.error)
    return answer


def upload(path: str, fields: dict, file_field: str, filename: str, data: bytes, on_done, timeout: float = 20.0) -> None:
    """A file to the Bridge as multipart/form-data (the credential upload), off the main loop."""
    import uuid  # noqa: PLC0415

    from .model.credentials import multipart  # noqa: PLC0415

    boundary = "meshsat" + uuid.uuid4().hex
    body = multipart(fields, file_field, filename, data, boundary)

    def run() -> None:
        answer = request("POST", path, raw=body, content_type=f"multipart/form-data; boundary={boundary}", timeout=timeout)
        if GLib is not None:
            GLib.idle_add(lambda: on_done(answer) or False)
        else:
            on_done(answer)

    threading.Thread(target=run, daemon=True).start()


def fetch(path: str, on_done, method: str = "GET", body: dict | None = None, timeout: float = 8.0) -> None:
    """A call off the main loop; `on_done(answer)` on it (straight from the thread when there
    is no main loop, as in the unit tests)."""
    def run() -> None:
        answer = request(method, path, body, timeout)
        if GLib is not None:
            GLib.idle_add(lambda: on_done(answer) or False)
        else:
            on_done(answer)

    threading.Thread(target=run, daemon=True).start()


def get(path: str, timeout: float = 2.0):
    """A JSON answer of the Bridge, or None when it does not answer or answers with an error."""
    answer = request("GET", path, timeout=timeout)
    return answer.body if answer.ok else None


def post(path: str, body: dict | None = None, timeout: float = 8.0, method: str = "POST"):
    """The Bridge's JSON answer; on any failure a dict with `error` in the Bridge's own words,
    or the reason it did not answer."""
    answer = request(method, path, body, timeout)
    if answer.ok:
        return answer.body if answer.body is not None else {}
    if isinstance(answer.body, dict) and answer.body.get("error"):
        return answer.body
    return {"error": answer.error or f"HTTP {answer.status}"}


def put(path: str, body: dict | None = None, timeout: float = 8.0):
    return post(path, body, timeout, method="PUT")


def delete(path: str, timeout: float = 8.0):
    return post(path, None, timeout, method="DELETE")


# The texts this app sent, as the Android app keeps its own database (store.SentLog).
sent_log = store.SentLog()


def record_sent(text: str, to: str | None, lane: str, me: str | None) -> dict:
    """A text this app just sent, in the shape of the Bridge's stored messages, appended to
    the sent log."""
    record = store.sent_record(text, to, lane, me, EVERYONE)
    sent_log.append(record)
    return record


def read_sent() -> list:
    return sent_log.read()


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


def packet_time(p: dict) -> float:
    """A packet feed entry's time as a timestamp, 0 when unreadable (Go's RFC 3339 with none
    to nine fraction digits)."""
    stamp = re.sub(r"\.\d+", "", str(p.get("time", "")))
    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0


def recent_senders(messages: list, nodes: list, names: dict, now: float | None = None, within: float = 3600) -> list:
    """Mesh nodes that texted in the last hour and that the Bridge no longer lists (its node
    table is rebuilt from the daemon's at every restart, and the daemon writes a node to its
    database only once it has that node's NodeInfo), as rows the name asker can work on. A
    node whose name the cache knows is not one."""
    now = now or time.time()
    known = {n.get("user_id") for n in nodes or []}
    out = {}
    for m in messages or []:
        sender = m.get("from_node") or ""
        if m.get("direction") != "rx" or m.get("transport") not in (None, "", "radio") or sender in known or sender in names or sender in out:
            continue
        if len(sender) != 9 or not sender.startswith("!") or (now - (m.get("rx_time") or 0)) > within:
            continue
        try:
            num = int(sender[1:], 16)
        except ValueError:
            continue
        if not num or num == 0xFFFFFFFF:
            continue
        out[sender] = {"user_id": sender, "num": num, "long_name": "", "short_name": "", "last_heard": m.get("rx_time") or 0, "unlisted": True}
    return list(out.values())


def last_transmission(packets: list, sent: list) -> float:
    """When this phone last transmitted, as far as the app can tell: the Bridge's packet feed
    (anything it sent) and this app's own sent log."""
    times = [packet_time(p) for p in packets or [] if p.get("dir") == "tx"]
    times += [m.get("rx_time") or 0 for m in sent or [] if m.get("transport") == "radio"]
    return max(times, default=0.0)


# The names this app has seen, by node id. The Bridge keeps its node table in memory (empty
# again after every restart, and every package install restarts it) and the node's own
# database holds only the NodeInfo it managed to decode, so a name heard once is kept here,
# as the Android app keeps its own node table.
NODES_CACHE = os.path.join(state_dir(), "meshsat", "nodes.json")
NAME_FIELDS = ("num", "long_name", "short_name", "hw_model", "hw_model_name")


def read_names() -> dict:
    data = store.read_json(NODES_CACHE, {})
    return data if isinstance(data, dict) else {}


def write_names(names: dict) -> None:
    store.write_json(NODES_CACHE, names)


def remember_names(nodes: list, names: dict, now: float | None = None) -> bool:
    """Every named node of the Bridge's list into `names`; True when a name is new or changed."""
    changed = False
    for n in nodes or []:
        uid = n.get("user_id")
        if not uid or not (n.get("long_name") or n.get("short_name")) or n.get("name_cached"):
            continue
        record = {k: n.get(k) or ("" if k.endswith("name") else 0) for k in NAME_FIELDS}
        old = names.get(uid) or {}
        if any(old.get(k) != record[k] for k in NAME_FIELDS):
            changed = True
        record["seen"] = int(now or time.time())
        names[uid] = record
    return changed


def name_nodes(nodes: list, names: dict) -> list:
    """The Bridge's nodes with the cached name filled in where the Bridge has none."""
    for n in nodes or []:
        if n.get("long_name") or n.get("short_name"):
            continue
        cached = names.get(n.get("user_id"))
        if not cached:
            continue
        n["long_name"] = cached.get("long_name") or ""
        n["short_name"] = cached.get("short_name") or ""
        if not n.get("hw_model") and cached.get("hw_model"):
            n["hw_model"] = cached["hw_model"]
            n["hw_model_name"] = cached.get("hw_model_name") or ""
        n["name_cached"] = True
    return nodes


class NameAsker:
    """Asks the Bridge for the name of a node the phone has heard but has no NodeInfo from
    (`POST /api/nodes/request-info`), on a cadence the node's firmware honours. The daemon and
    the Bridge both ask the moment a new node is heard; a node running Meshtastic 2.7 answers a
    request only from a node it has not heard for twelve hours ("Skip send NodeInfo since we
    heard the requester <12h ago", read on a T-Deck's own log on 28 Sep 2026), and older
    firmware at most once per five minutes. So: one more ask six minutes after the node was
    first heard, in case the first one was lost, then one per twelve hours; the name otherwise
    comes with the node's own periodic broadcast. Never within 30 s of this phone's own
    transmission: the back cover cannot receive for a while after it sends."""

    FIRST = 6 * 60
    EVERY = 12 * 3600
    QUIET = 30
    RECENT = 3600
    RETRY = 30
    RETRIES = 5

    def __init__(self, post_fn=None):
        self.post = post_fn or post
        self.seen = {}
        self.log = []

    def due(self, nodes: list, me: str | None, last_tx: float, now: float) -> list:
        if now - last_tx < self.QUIET:
            return []
        out = []
        for n in nodes or []:
            uid = n.get("user_id")
            if not uid or uid == me or n.get("long_name") or n.get("short_name") or not n.get("num"):
                continue
            heard = max(n.get("last_heard") or 0, n.get("last_message_time") or 0)
            if not heard or now - heard > self.RECENT:
                continue
            record = self.seen.setdefault(uid, {"first": heard, "asked": 0, "last": 0.0, "errors": 0})
            if record.get("retry"):
                if now >= record["retry"]:
                    out.append(n)
                continue
            wait = self.FIRST if record["asked"] == 0 else self.EVERY
            if now - (record["last"] or record["first"]) >= wait:
                out.append(n)
        return out

    def ask(self, nodes: list, me: str | None, last_tx: float, now: float | None = None) -> list:
        """Asks for every node that is due; returns the (node id, outcome) pairs. An ask the
        Bridge could not send (it was restarting, say) is tried again 30 s later, a few times,
        without counting."""
        now = now or time.time()
        asked = []
        for n in self.due(nodes, me, last_tx, now):
            result = self.post("/api/nodes/request-info", {"node_num": n["num"]}) or {}
            record = self.seen[n["user_id"]]
            record["last"] = now
            outcome = result.get("error") or result.get("status") or "sent"
            if result.get("error") and record["errors"] < self.RETRIES:
                record["errors"] += 1
                record["retry"] = now + self.RETRY
            else:
                record["asked"] += 1
                record["errors"] = 0
                record.pop("retry", None)
            self.log.append({"time": now, "node": n["user_id"], "outcome": outcome})
            del self.log[:-50]
            asked.append((n["user_id"], outcome))
        return asked


HARDWARE_PATH = os.environ.get("MESHSAT_APP_HARDWARE", "/run/meshsat/hardware.json")


def hardware() -> dict:
    """What meshsat-hardware found at boot (or when last asked): {"node": "cover"|"bluetooth",
    "why", "model", "checked_at"}; {} on a device without the package's detection."""
    try:
        with open(HARDWARE_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def check_hardware() -> str | None:
    """Asks the device to look for its node again (the cover put on or taken off): starts
    meshsat-hardware.service, which polkit allows the person at the screen. None when it
    worked, else the reason."""
    return system.start_unit("meshsat-hardware.service")


# The node over Bluetooth: the Bridge scans, pairs, connects and remembers (MESHSAT-1390); the
# app only shows and asks, as MeshSat Android's screens do over its own BLE stack.
def ble_scan(seconds: int = 8):
    return get(f"/api/mesh/ble/scan?seconds={seconds}", timeout=seconds + 6.0)


def ble_connect(address: str):
    return post("/api/mesh/ble/connect", {"address": address}, timeout=45.0)


def ble_pair(pin: str):
    return post("/api/mesh/ble/pair", {"pin": pin}, timeout=10.0)


def ble_status():
    return get("/api/mesh/ble/status")


def ble_forget(bond: bool = False):
    """Disconnect (the bond stays, as Android's Disconnect leaves it); bond=True forgets the
    node entirely, which clears a stale bond."""
    return post("/api/mesh/ble" + ("?bond=1" if bond else ""), None, timeout=15.0, method="DELETE")


def unit_active(unit: str) -> bool:
    return system.unit_active(unit)


def watchdog_status() -> dict:
    try:
        with open(STATUS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# What the Bridge answers about itself and its links; cleared when it stops answering, so no
# lane keeps saying "ready" about a modem or a SIM nobody can reach.
LIVE = ("modem", "signal", "hub", "sos", "deadman", "keys", "cellular", "message_stats", "ble")


class State:
    """One snapshot of everything the screens show. Fields are None until first polled."""

    def __init__(self):
        self.bridge = None  # /api/status, None = Bridge not answering
        self.nodes = []
        self.messages = []
        self.packets = []  # /api/packets: the frames the Bridge saw, the newest 200 (People's live signal)
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
        self.last_tx = 0.0  # when this phone last transmitted, as far as the app can tell
        self.name_requests = []  # the asks for a nameless node's NodeInfo, newest last
        self.hardware = {}  # /run/meshsat/hardware.json: the LoRa cover, or a node over Bluetooth
        self.ble = None  # /api/mesh/ble/status when the node is over Bluetooth
        # Where this phone is, as Android's LocationFixes: geoclue's fix (lat, lon, accuracy_m, at),
        # a position typed in (lat, lon), and what to tell the user when there is neither.
        self.phone = None
        # The same fix as Home's "Your position" reads it (DashboardScreen.kt:275-315): latitude,
        # longitude, accuracy, altitude, speed, heading (None when geoclue does not know) and at.
        self.fix = None
        self.entered = None
        self.location_hint = ""

    def node_mode(self) -> str:
        """"cover" (the PinePhone's LoRa back cover runs the node) or "bluetooth" (a node adopted
        over Bluetooth, as on the other apps)."""
        return self.hardware.get("node") or "cover"

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
        return bool(self.bridge and self.modem and self.modem.get("connected"))

    def hub_configured(self) -> bool:
        return bool(self.bridge and self.hub and self.hub.get("url"))

    def sms_ready(self) -> bool:
        """The SIM can send: the Bridge answering, a modem, a SIM in it, and a network."""
        c = self.cellular or {}
        return bool(self.bridge) and bool(c.get("connected")) and c.get("sim_state") == "READY" and str(c.get("registration", "")).startswith("registered")

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


class Throttled(Exception):
    """The Bridge answered 429: it is up, and asks every client on this address to slow down
    (MESHSAT_API_RATE_LIMIT requests a minute). Not "down", not "nothing there"."""


def polled(path: str):
    """A poll's GET: the body, or None when the Bridge has nothing or does not answer; a 429
    raises Throttled, so the poll keeps what the screens show instead of blanking it."""
    answer = request("GET", path, timeout=2.0)
    if answer.status == 429:
        raise Throttled(path)
    return answer.body if answer.ok else None


def poll_state(s: "State", names: dict, asker: "NameAsker") -> "State":
    """One poll of everything the screens show, into `s`, on the calling thread: pure of GTK,
    so the unit tests run it against a scripted Bridge. A 429 on any call ends the poll there:
    what was read before it is fresh, the rest stays as it was."""
    try:
        return _poll_state(s, names, asker)
    except Throttled:
        s.polled_at = time.time()
        return s


def _poll_state(s: "State", names: dict, asker: "NameAsker") -> "State":
    get = polled  # every GET of the poll goes through the 429 check
    bridge = get("/api/status")
    s.bridge = bridge
    if bridge is None:
        for field in LIVE:
            setattr(s, field, None)
        s.sms = []
        s.packets = []
    else:
        nodes = (get("/api/nodes") or {}).get("nodes") or []
        if remember_names(nodes, names):
            write_names(names)
        s.nodes = name_nodes(nodes, names)
        stored = (get("/api/messages?limit=200") or {}).get("messages") or []
        me = bridge.get("node_id")
        sent = read_sent()
        packets = (get("/api/packets?limit=200") or {}).get("packets") or []
        s.packets = packets
        s.messages = merge_messages(stored, sent, packet_texts(packets, me))
        s.last_tx = max(last_transmission(packets, sent), s.last_tx)
        candidates = s.nodes + recent_senders(s.messages, s.nodes, names)
        for _node_id, outcome in asker.ask(candidates, me, s.last_tx):
            if outcome == "nodeinfo request sent":
                s.last_tx = time.time()
        s.name_requests = asker.log
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
    s.hardware = hardware()
    if bridge is not None and s.node_mode() == "bluetooth":
        s.ble = ble_status()
    s.node_service = unit_active("meshtasticd.service")
    s.bridge_service = unit_active("meshsat-bridge.service")
    # The radio watchdog watches the cover; its last verdict means nothing to a node over Bluetooth.
    s.watchdog = watchdog_status() if s.node_mode() == "cover" else {}
    if s.mesh_connected():
        s.unreachable_since = None
    elif s.unreachable_since is None:
        s.unreachable_since = time.time()
    s.polled_at = time.time()
    return s


class Poller:
    """Polls the Bridge every few seconds on one worker thread; `on_update(state)` runs on the
    main loop. `poll_now()` wakes the worker (never a second thread on the same state); the
    pace slows while the window is not in front."""

    FRONT = float(os.environ.get("MESHSAT_APP_POLL", "4"))
    BEHIND = max(FRONT, 15.0)

    def __init__(self, on_update, interval: float | None = None):
        self.on_update = on_update
        self.interval = interval or self.FRONT
        self.state = State()
        self.names = read_names()
        self.asker = NameAsker()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def poll_now(self):
        self._wake.set()

    def set_pace(self, in_front: bool) -> None:
        self.interval = self.FRONT if in_front else self.BEHIND

    def _run(self):
        while not self._stop.is_set():
            self._wake.clear()
            self._poll_once()
            self._wake.wait(self.interval)

    def _poll_once(self):
        s = poll_state(self.state, self.names, self.asker)
        if GLib is not None:
            GLib.idle_add(self.on_update, s)
        else:
            self.on_update(s)
