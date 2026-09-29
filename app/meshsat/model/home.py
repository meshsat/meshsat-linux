# SPDX-License-Identifier: GPL-3.0-or-later
"""Home's answer to "can my message get out, and how" (ui/screens/HomeLanes.kt): one lane per
way out with its state and its words, the sentence above them, and the SOS card's reach
sentence (SosScreens.kt). Pure functions of the polled state, so the tests can hold every
state up against Android's words."""
from . import dashboard, hub, words


def depths(stats: list | None) -> dict:
    """Each lane's queue as Android counts it (MessageDeliveryDao.queueDepth): the deliveries on
    its channels that are queued, retrying, held or sending (GET /api/deliveries/stats)."""
    return {lane: dashboard.lane_depth(stats or [], lane) for lane in ("satellite", "mesh", "sms")}


def satellite_lane(s, depth: int = 0, pass_line: str | None = None) -> tuple:
    """(state, detail, figure). This edition's modem is a RockBLOCK on USB-C, or the modem of
    a node adopted over Bluetooth (its pipe, once the Bridge reads it). `depth`: the satellite
    queue; `pass_line`: dashboard.pass_line() of Home's passes."""
    modem = s.modem or {}
    queue_line = dashboard.queue_prefix(depth)
    if not s.bridge:
        return "off", "Connect a MeshSat node to use its satellite modem.", ""
    ble = s.ble or {}
    if s.node_mode() == "bluetooth" and ble.get("satellite_link_broken"):
        # HomeLanes.kt:170-174: the pipe to the node takes no writes; the satellite is not the problem
        return "failed", (queue_line + "The phone cannot reach the node's modem. Getting the link back.").strip(), ""
    if s.modem_connected():
        bars = (s.signal or {}).get("bars", 0)
        return "working", (queue_line + (pass_line or "Modem ready.")).strip(), f"{bars}/5"
    if modem.get("port") not in ("", "supervisor", None):
        if modem.get("silent"):
            return "failed", "The node's modem does not answer. Check its power and cable.", ""
        return "trying", "Checking the modem.", ""
    if s.node_mode() == "bluetooth":
        ble = s.ble or {}
        if ble.get("adapter_powered") is False and ble.get("address"):
            return "failed", (queue_line + "Bluetooth is off on this phone. Switch it on to reach the node's modem.").strip(), ""
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
        if ble.get("adapter_powered") is False and ble.get("address"):
            return "failed", "Bluetooth is off on this phone. Switch it on to reach your node.", ""
        if ble.get("mode") in ("scanning", "pairing", "connecting"):
            return "trying", "Connecting to your node.", ""
        if ble.get("address"):
            return "trying", "Reconnecting to your node.", ""
        return "off", "Connect a MeshSat node or a Meshtastic radio.", ""
    if s.node_service:
        return "trying", "Connecting to your node." if not s.bridge else "Reconnecting to your node.", ""
    return "off", "Connect a MeshSat node or a Meshtastic radio.", ""


def sms_lane(s, depth: int = 0) -> tuple:
    if s.sms_ready():
        if depth:
            return "working", f"{words.count(depth, 'message')} waiting to go out.", f"{s.sms_today()} today"
        return "working", "Ready.", f"{s.sms_today()} today"
    return "off", s.sms_reason() or "Allow SMS to send and receive texts.", ""


def hub_lane(s) -> tuple:
    """HomeLanes.kt:217-223 from the Bridge's word on the link (model/hub.py, MESHSAT-1417)."""
    state, sentence = hub.lane(s.hub, bool(s.bridge))
    return state, sentence, ""


def lanes(s, stats: list | None = None, pass_line: str | None = None) -> dict:
    depth = depths(stats)
    return {"satellite": satellite_lane(s, depth["satellite"], pass_line), "mesh": mesh_lane(s), "sms": sms_lane(s, depth["sms"]), "hub": hub_lane(s)}


def sentence(lane_states: dict, s, stats: list | None = None) -> tuple:
    """(the sentence, the line under it or None); the line counts the three queues together."""
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
    waiting = sum(depths(stats).values())
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


def checklist(s, lane_states: dict | None = None) -> list:
    """Onboarding.kt's steps as (title, detail, done, route): the node, the Hub, and with a
    modem in the phone SMS and the emergency contacts. In cover mode the first step is this
    edition's own (the node is the LoRa back cover, started, not paired)."""
    bluetooth = s.node_mode() == "bluetooth"
    if bluetooth:
        first = ("Pair your MeshSat node", "The radios: mesh and satellite", bool((s.ble or {}).get("address")), "setup/node")
    else:
        first = ("Start your MeshSat node", "The radio: the LoRa back cover", bool(s.node_service) or s.mesh_connected(), "setup/node")
    steps = [first, ("Scan the Hub's QR code", "Optional: the control room", s.hub_configured(), "setup/hub")]
    if (s.cellular or {}).get("connected"):
        steps += [("Allow SMS", "Messages and SOS by the phone's own SIM", s.sms_ready(), "setup/sms"),
                  ("Add emergency contacts", "Who an SOS goes to by SMS", bool(s.contacts), "setup/safety")]
    return steps