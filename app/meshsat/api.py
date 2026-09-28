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

try:
    from gi.repository import GLib
except ImportError:  # the unit tests, on a machine without GTK
    GLib = None


def state_dir() -> str:
    """Where this app keeps what it records (XDG state)."""
    if GLib is not None:
        return GLib.get_user_state_dir()
    return os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")


BRIDGE = os.environ.get("MESHSAT_APP_BRIDGE", "http://127.0.0.1:6050")
STATUS_PATH = os.environ.get("MESHSAT_APP_STATUS", "/run/meshsat-node/status")
# What this app sent, one JSON record per line: the Bridge keeps a sent mesh text only in its
# packet feed (in memory, gone at its next start), never in the message store, so the app keeps
# its own record, as the Android app keeps its own database.
SENT_LOG = os.path.join(state_dir(), "meshsat", "sent.jsonl")
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
    try:
        with open(NODES_CACHE, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_names(names: dict) -> None:
    try:
        os.makedirs(os.path.dirname(NODES_CACHE), exist_ok=True)
        with open(NODES_CACHE + ".tmp", "w", encoding="utf-8") as handle:
            json.dump(names, handle)
        os.replace(NODES_CACHE + ".tmp", NODES_CACHE)
    except OSError:
        pass


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
        self.last_tx = 0.0  # when this phone last transmitted, as far as the app can tell
        self.name_requests = []  # the asks for a nameless node's NodeInfo, newest last
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
        self.names = read_names()
        self.asker = NameAsker()
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
            nodes = (get("/api/nodes") or {}).get("nodes") or []
            if remember_names(nodes, self.names):
                write_names(self.names)
            s.nodes = name_nodes(nodes, self.names)
            stored = (get("/api/messages?limit=200") or {}).get("messages") or []
            me = bridge.get("node_id")
            sent = read_sent()
            packets = (get("/api/packets?limit=200") or {}).get("packets") or []
            s.messages = merge_messages(stored, sent, packet_texts(packets, me))
            s.last_tx = max(last_transmission(packets, sent), s.last_tx)
            candidates = s.nodes + recent_senders(s.messages, s.nodes, self.names)
            for node_id, outcome in self.asker.ask(candidates, me, s.last_tx):
                if outcome == "nodeinfo request sent":
                    s.last_tx = time.time()
            s.name_requests = self.asker.log
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
