# SPDX-License-Identifier: GPL-3.0-or-later
"""A node's sheet, as People opens it (ui/components/NodeDetailSheet.kt, ble/NodeBattery.kt):
the title, the id line, the rows in Android's words, and whether "Show on map" can go
anywhere. The node is the Bridge's (/api/nodes); Android's battery level -1 ("not reported")
is the Bridge's 0. Pure."""
from . import words
from .geofence import half_up

NOT_REPORTED = "Not reported"
NOT_SHARED = "Not shared yet. It appears once the node sends its position."
NOT_MEASURED = "Not measured yet. Your node measures it when it hears this node transmit."
YOUR_NODE = " (your node)"
MESSAGE = "Message"
SHOW_ON_MAP = "Show on map"
LAST_HEARD, BATTERY, SIGNAL, HARDWARE, POSITION = "Last heard", "Battery", "Signal", "Hardware", "Position"


def node_id(node: dict) -> str:
    return node.get("user_id") or f"!{int(node.get('num') or 0):08x}"


def title(node: dict, mine: bool) -> str:
    """The long name, else the id, and " (your node)" for this phone's own."""
    return ((node.get("long_name") or "").strip() or node_id(node)) + (YOUR_NODE if mine else "")


def subtitle(node: dict) -> str:
    """The short name and the id, two spaces apart."""
    return "  ".join(part for part in ((node.get("short_name") or "").strip(), node_id(node)) if part)


def battery(level) -> str | None:
    """NodeBattery.describe without the voltage: "82%", "On USB power", or None when the node
    has reported none."""
    level = int(level or 0)
    if level > 100:
        return "On USB power"
    if level > 0:
        return f"{level}%"
    return None


def signal(node: dict) -> str:
    """nodeSignal's long form from what the node list knows: the SNR only for a node heard
    directly (on a relayed packet it is the relay's), the hop count for one heard through
    others."""
    hops = node.get("hops_away")
    snr = node.get("snr") or 0
    if hops:
        return f"Heard through other nodes, {words.count(int(hops), 'hop')} away."
    if snr:
        return f"Heard directly. SNR {half_up(snr, 1)} dB, as your node last measured it."
    return NOT_MEASURED


def has_position(node: dict) -> bool:
    return bool(node.get("latitude")) and bool(node.get("longitude"))


def position(node: dict, now_s: float) -> str:
    """"52.12345, 5.12345, 4 min ago", or the words for a node that has sent none."""
    if not has_position(node):
        return NOT_SHARED
    return f"{half_up(node['latitude'], 5)}, {half_up(node['longitude'], 5)}, {words.ago(node.get('last_heard') or 0, now_s)}"


def rows(node: dict, mine: bool, now_s: float) -> list:
    """(label, value, mono) in the sheet's order: Last heard and Signal only for someone else's
    node, Hardware only when known."""
    out = []
    if not mine:
        out.append((LAST_HEARD, words.ago(node.get("last_heard") or 0, now_s), False))
    level = battery(node.get("battery_level"))
    out.append((BATTERY, level or NOT_REPORTED, bool(level) and int(node.get("battery_level") or 0) <= 100))
    if not mine:
        out.append((SIGNAL, signal(node), False))
    if node.get("hw_model"):
        out.append((HARDWARE, words.hardware_name(node.get("hw_model"), node.get("hw_model_name") or ""), False))
    out.append((POSITION, position(node, now_s), has_position(node)))
    return out
