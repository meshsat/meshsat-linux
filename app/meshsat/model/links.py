# SPDX-License-Identifier: GPL-3.0-or-later
"""Links' words (ui/screens/InterfacesScreen.kt): each way the phone sends and receives, its
state, its rules, groups, backup links and health, from the Bridge's records (/api/interfaces,
/api/interfaces/health, /api/access-rules, /api/object-groups, /api/failover-groups). Pure."""
from . import rules, words

TABS = ("Links", "Rules", "Capabilities", "Groups", "Backup links", "Health")
INTRO = "Each way this phone can send and receive messages, and how well it is working."
SUBTITLES = {
    "Capabilities": "What each link can carry, and how it retries.",
    "Health": "A score out of 100 for each link, from its signal, how many messages got through, how fast, and what it costs.",
    "Rules": "The routing rules of every link. Change them in Routing rules.",
    "Groups": "Named groups of nodes, senders or message types that rules can match.",
    "Backup links": "Groups of links that stand in for each other, or that all carry the same message.",
}
EMPTY = {
    "Links": "No links yet. They appear once the MeshSat service is running.",
    "Capabilities": "Nothing to show yet. It appears once the MeshSat service is running.",
    "Health": "No scores yet. They appear once the MeshSat service is running.",
    "Rules": "No routing rules yet. Add them in Routing rules.",
    "Groups": "No groups yet.",
    "Backup links": "No backup links set up.",
}
RECONNECT = "Try to connect now"
NOT_CONNECTED = "Not connected"

# The Bridge's channel table (internal/channel/defaults.go), by channel type: what each link can
# carry and how it retries. Android reads its own registry; the Bridge's links are the Bridge's.
CHANNELS = {
    "mesh": {"label": "Meshtastic LoRa", "max_payload": 237, "can_send": True, "can_receive": True, "binary": True, "paid": False, "retry": None},
    "iridium": {"label": "Iridium SBD", "max_payload": 340, "can_send": True, "can_receive": True, "binary": True, "paid": True, "retry": (180, 1800, 10, "isu")},
    "iridium_imt": {"label": "Iridium IMT", "max_payload": 102400, "can_send": True, "can_receive": True, "binary": True, "paid": True, "retry": (30, 300, 10, "exponential")},
    "cellular": {"label": "Cellular SMS", "max_payload": 160, "can_send": True, "can_receive": True, "binary": False, "paid": True, "retry": (30, 300, 3, "exponential")},
    "zigbee": {"label": "ZigBee 3.0", "max_payload": 100, "can_send": True, "can_receive": True, "binary": True, "paid": False, "retry": (2, 30, 3, "exponential")},
    "webhook": {"label": "Webhook HTTP", "max_payload": 0, "can_send": True, "can_receive": True, "binary": False, "paid": False, "retry": (5, 300, 5, "exponential")},
    "aprs": {"label": "APRS", "max_payload": 256, "can_send": True, "can_receive": True, "binary": False, "paid": False, "retry": None},
    "tak": {"label": "TAK/CoT", "max_payload": 0, "can_send": True, "can_receive": True, "binary": False, "paid": False, "retry": (5, 300, 5, "exponential")},
    "mqtt": {"label": "MQTT Broker", "max_payload": 0, "can_send": True, "can_receive": True, "binary": False, "paid": False, "retry": (1, 60, 10, "exponential")},
}


def sort_key(id_: str) -> int:
    """Mesh first, then satellite, then SMS."""
    if id_.startswith("mesh"):
        return 0
    if id_.startswith("iridium"):
        return 1
    if id_.startswith("sms"):
        return 2
    return 3


def sorted_interfaces(interfaces: list) -> list:
    return sorted(interfaces, key=lambda i: (sort_key(i.get("id", "")), i.get("id", "")))


def state_of(iface: dict, lanes: dict | None = None) -> str:
    """The link's state in Android's five words' keys: online, connecting, offline, error,
    disabled. The Bridge's interface manager binds USB devices; a link it calls "unbound" (no
    device to bind: the mesh over the daemon or Bluetooth, the SIM through ModemManager, the
    Hub) is working when the app sees that lane working."""
    if not iface.get("enabled", True):
        return "disabled"
    state = str(iface.get("state") or "").lower()
    if state == "binding":
        return "connecting"
    if state == "unbound":
        return "online" if lanes and lanes.get(words.channel_lane(iface.get("id", ""))) else "offline"
    return state if state in ("online", "offline", "error") else "offline"


def state_tone(state: str) -> str:
    """Working, trying, failed; a link that is off or switched off is grey, never red."""
    return {"online": "green", "connecting": "amber", "error": "red"}.get(state, "muted")


def state_text(state: str) -> str:
    return words.link_state(state)


def switch_name(id_: str) -> str:
    return f"Use {words.channel(id_)}"


def times_line(iface: dict, now: float) -> str:
    """When it last worked and last carried a message."""
    parts = []
    online = words.stamp_epoch(iface.get("last_online"))
    if online:
        parts.append(f"Last working {words.ago(online, now)}")
    activity = words.stamp_epoch(iface.get("last_activity"))
    if activity:
        parts.append(f"last message {words.ago(activity, now)}")
    return " · ".join(parts)


def reconnect_line(iface: dict) -> str:
    attempts = int(iface.get("reconnect_attempts") or 0)
    return f"Tried to reconnect {words.count(attempts, 'time')}" if attempts > 0 else ""


def can_reconnect(state: str) -> bool:
    """Reconnect only when off or not working."""
    return state in ("offline", "error")


def bind_target(iface: dict) -> str:
    """The device the Bridge is asked to bind: the link's own device, else its port."""
    return iface.get("device_id") or iface.get("device_port") or ""


def switch_off_dialog(id_: str) -> dict:
    """Switching a link off is confirmed first: it stops everything that goes by it. Android
    has a sentence of its own for the satellite ("The phone stops using the satellite modem and
    stops reconnecting to it. Nothing goes out or comes in by satellite ..."), true of its own
    modem over Bluetooth; the Bridge keeps a switched-off modem connected and still reads what
    comes in, so every link gets the sentence that is true of the Bridge (MESHSAT-1401)."""
    link = words.channel(id_)
    body = f"Messages stop going out by {link} until you switch it back on. Messages waiting for it stay in the queue."
    return {"title": f"Switch off {link}?", "body": body, "ok": "Switch off", "cancel": "Keep it on"}


def toast_on(id_: str) -> str:
    return f"{words.channel(id_)} switched on"


def toast_off(id_: str) -> str:
    return f"{words.channel(id_)} switched off"


def toast_reconnect(id_: str) -> str:
    return f"Trying to connect {words.channel(id_)} now"


def badges(interfaces: list, scores: list, lanes: dict | None = None) -> dict:
    """The Links tab counts the links that work, the Health tab the low scores."""
    return {"Links": sum(1 for i in interfaces if state_of(i, lanes) == "online"), "Health": sum(1 for s in scores if int(s.get("score") or 0) < 50 and s.get("available"))}


# Capabilities
def capability_rows(channel_type: str) -> list:
    """(label, value) rows of one channel type, as Android's CapabilityRow."""
    ch = CHANNELS.get(channel_type or "")
    if ch is None:
        return []
    return [("Largest message", f"{ch['max_payload']} bytes" if ch["max_payload"] > 0 else "No limit"), ("Sends", "Yes" if ch["can_send"] else "No"),
            ("Receives", "Yes" if ch["can_receive"] else "No"), ("Carries data, not only text", "Yes" if ch["binary"] else "No"), ("Cost", "Paid" if ch["paid"] else "Free")]


def retries_text(channel_type: str) -> str:
    ch = CHANNELS.get(channel_type or "")
    if ch is None or ch["retry"] is None:
        return ""
    first, longest, times, backoff = ch["retry"]
    how_often = "waits for the next satellite pass" if backoff == "isu" else f"first after {first} s, then up to {longest} s apart"
    return f"Retries: {how_often}" + (f", at most {words.count(times, 'time')}." if times > 0 else ".")


def channel_label(iface: dict) -> str:
    ch = CHANNELS.get(iface.get("channel_type") or "")
    return iface.get("label") or (ch["label"] if ch else iface.get("channel_type") or "")


# Groups and backup links
def group_type_label(type_: str) -> str:
    """A group's type ("node_group", "sender_group", ...) in plain words."""
    bare = (type_ or "").lower()
    if bare.endswith("_group"):
        bare = bare[: -len("_group")]
    named = {"node": "Nodes", "sender": "Senders", "portnum": "Message types", "contact": "Contacts"}.get(bare)
    if named:
        return named
    plain = (type_ or "").replace("_", " ")
    return plain[:1].upper() + plain[1:]


def member_count(members) -> int:
    import json  # noqa: PLC0415

    if isinstance(members, list):
        return len(members)
    try:
        parsed = json.loads(members or "[]")
    except ValueError:
        return 0
    return len(parsed) if isinstance(parsed, list) else 0


def group_title(group: dict) -> str:
    return (group.get("label") or "").strip() or group.get("id", "")


def failover_mode(mode: str) -> str:
    named = {"failover": "Uses the first link that works", "broadcast": "Sends on every link"}.get((mode or "").lower())
    return named or ((mode[:1].upper() + mode[1:]) if mode else "")


# Health
def score_tone(score) -> str:
    score = int(score or 0)
    if score >= 80:
        return "green"
    if score >= 50:
        return "amber"
    if score > 0:
        return "red"
    return "muted"


def speed_score(latency_ms) -> int:
    latency_ms = int(latency_ms or 0)
    return 100 - min(latency_ms // 1000, 100) if latency_ms > 0 else 0


def score_parts(hs: dict) -> list:
    """The parts of the score, each out of 100: (label, value)."""
    return [("Signal", int(hs.get("signal") or 0)), ("Got through", int(float(hs.get("success_rate") or 0) * 100)), ("Speed", speed_score(hs.get("latency_ms"))),
            ("Low cost", int(hs.get("cost_score") or 0))]


# The read-only rules tab
def rule_route(rule: dict) -> str:
    source, target = rule.get("interface_id") or "", rule.get("forward_to") or ""
    if rule.get("direction") == "egress":
        return f"Messages leaving by {words.channel(source)}"
    if rule.get("action") == "forward" and target.strip():
        return f"{words.channel(source)} to {words.channel(target)}"
    return f"Messages from {words.channel(source)}"


def rule_line(rule: dict) -> str:
    return f"{rules.action_label(rule.get('action', ''))}: {rule_route(rule)}"
