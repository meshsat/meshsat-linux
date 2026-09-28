# SPDX-License-Identifier: GPL-3.0-or-later
"""Home's answer to "can my message get out, and how" (ui/screens/HomeLanes.kt): one lane per
way out with its state and its words, the sentence above them, and the SOS card's reach
sentence (SosScreens.kt). Pure functions of the polled state, so the tests can hold every
state up against Android's words."""
from . import words


def queued(s) -> int:
    return sum(1 for m in s.messages if m.get("delivery_status") in ("queued", "pending", "sending"))


def satellite_lane(s) -> tuple:
    """(state, detail, figure). This edition's modem is a RockBLOCK on USB-C, or the modem of
    a node adopted over Bluetooth (its pipe, once the Bridge reads it)."""
    modem = s.modem or {}
    waiting = queued(s)
    queue_line = f"{words.count(waiting, 'message')} waiting to go out. " if waiting else ""
    if not s.bridge:
        return "off", "Connect a MeshSat node to use its satellite modem.", ""
    if s.modem_connected():
        bars = (s.signal or {}).get("bars", 0)
        return "working", (queue_line + "Modem ready.").strip(), f"{bars}/5"
    if modem.get("port") not in ("", "supervisor", None):
        if modem.get("silent"):
            return "failed", "The node's modem does not answer. Check its power and cable.", ""
        return "trying", "Checking the modem.", ""
    if s.node_mode() == "bluetooth":
        ble = s.ble or {}
        if not s.mesh_connected():
            if ble.get("address"):
                return "trying", (queue_line + "Reconnecting to your MeshSat node.").strip(), ""
            return "off", "Connect a MeshSat node to use its satellite modem.", ""
        if ble.get("satellite_owner") == "node":
            return "trying", "The node is using its modem. The phone takes it next.", ""
        if ble.get("satellite_pipe"):
            return "trying", "Asking the node for its modem.", ""
        return "off", "This radio has no satellite modem.", ""
    return "off", "This radio has no satellite modem. Plug a RockBLOCK into USB-C.", ""


def mesh_lane(s) -> tuple:
    """(state, detail, figure)."""
    if s.mesh_connected():
        own = s.own_node() or {}
        name = (s.bridge or {}).get("node_name") or own.get("long_name") or ""
        detail = f"Connected to {name}" if name else "Connected"
        rssi = own.get("rssi") or 0
        if rssi:
            detail += f", signal {rssi} dBm"
        detail += "."
        battery = own.get("battery_level") or 0
        if battery > 100:
            detail += " On USB power."
        elif battery:
            detail += f" Battery {battery}%."
        return "working", detail, words.count(len(s.others()), "node")
    if s.node_mode() == "bluetooth":
        ble = s.ble or {}
        if ble.get("adapter") is False and ble.get("address"):
            return "failed", "Bluetooth is off on this phone. Switch it on to reach your node.", ""
        if ble.get("mode") in ("scanning", "pairing", "connecting"):
            return "trying", "Connecting to your node.", ""
        if ble.get("address"):
            return "trying", "Reconnecting to your node.", ""
        return "off", "Connect a MeshSat node or a Meshtastic radio.", ""
    if s.node_service:
        return "trying", "Connecting to your node." if not s.bridge else "Reconnecting to your node.", ""
    return "off", "Connect a MeshSat node or a Meshtastic radio.", ""


def sms_lane(s) -> tuple:
    if s.sms_ready():
        waiting = sum(1 for m in s.messages if m.get("transport") == "sms" and m.get("delivery_status") in ("queued", "pending", "sending"))
        if waiting:
            return "working", f"{words.count(waiting, 'message')} waiting to go out.", f"{s.sms_today()} today"
        return "working", "Ready.", f"{s.sms_today()} today"
    return "off", s.sms_reason() or "Allow SMS to send and receive texts.", ""


def hub_lane(s) -> tuple:
    """The Bridge tells the app its Hub settings, not yet whether the link is up (Bridge change
    B12): with settings and no word on the link it is "trying", never "working" on a guess."""
    hub = s.hub or {}
    if not s.bridge or not hub.get("url"):
        return "off", "Scan the Hub's QR code to connect this phone.", ""
    link = hub.get("link") or hub.get("state") or ""
    if link == "connected":
        return "working", f"Connected as {hub.get('bridge_id') or ''}.", ""
    if link == "error":
        return "failed", "Cannot reach the Hub. It keeps trying by itself.", ""
    if link == "disconnected":
        return "trying", "Not connected. It keeps trying by itself.", ""
    return "trying", "Connecting to the Hub.", ""


def lanes(s) -> dict:
    return {"satellite": satellite_lane(s), "mesh": mesh_lane(s), "sms": sms_lane(s), "hub": hub_lane(s)}


def sentence(lane_states: dict, s) -> tuple:
    """(the sentence, the line under it or None)."""
    ways = []
    if lane_states["satellite"][0] == "working":
        ways.append("satellite")
    if lane_states["mesh"][0] == "working":
        ways.append("mesh")
    if lane_states["sms"][0] == "working":
        ways.append("SMS")
    if lane_states["hub"][0] == "working":
        ways.append("the Hub")
    first = "Nothing can send yet." if not ways else f"Messages can go out by {words.join_and(ways)}."
    waiting = queued(s)
    if waiting:
        second = f"{words.count(waiting, 'message')} on the way."
    elif not ways:
        second = "Start with your MeshSat node, below."
    else:
        second = None
    return first, second


def reach_sentence(s, lane_states: dict | None = None) -> str:
    """SosReach.sentence(): where an SOS would go from here."""
    lane_states = lane_states or lanes(s)
    parts = []
    if lane_states["satellite"][0] == "working":
        parts.append("satellite")
    if lane_states["mesh"][0] == "working":
        parts.append("the mesh")
    can_sms = s.sms_ready()
    if can_sms and s.contacts:
        parts.append("SMS to " + ((s.contacts[0].get("name") or "1 person") if len(s.contacts) == 1 else f"{len(s.contacts)} people"))
    if lane_states["hub"][0] == "working":
        parts.append("the Hub")
    if not parts:
        if can_sms:
            return "An SOS has nowhere to go yet. Add emergency contacts, or connect your node."
        return "An SOS has nowhere to go yet. Connect your MeshSat node, or set up the Hub."
    return f"Sends your position by {words.join_and(parts)}, and keeps trying until you cancel."


def contacts_button(s) -> str:
    """SosCard: the text button under the hold bar."""
    if not s.sms_ready():
        return "Connect your node"
    if not s.contacts:
        return "Add emergency contacts"
    return "Emergency contacts"


def checklist(s, lane_states: dict) -> list:
    """Onboarding.kt's four steps as (title, detail, done): the node, the Hub, the modem, and
    the emergency contacts."""
    bluetooth = s.node_mode() == "bluetooth"
    node_done = s.mesh_connected() or (bluetooth and bool((s.ble or {}).get("address")))
    return [("Pair your MeshSat node" if bluetooth else "Start your MeshSat node", "The radios: mesh and satellite" if bluetooth else "The radio: the LoRa back cover", node_done),
            ("Paste the Hub's key", "Optional: the control room", lane_states["hub"][0] in ("working", "trying")),
            ("Plug the satellite modem", "A RockBLOCK on USB-C", s.modem_connected()),
            ("Add emergency contacts", "Who an SOS goes to by SMS", bool(s.contacts))]
