# SPDX-License-Identifier: GPL-3.0-or-later
"""What MeshSat says outside its window: the notifications MeshSat Android posts, in its
words (GatewayService.kt, SosController.kt), and the status a panel, a lock screen or a tray
shows. Pure functions: the notifier service applies them, the tests run them without a
display."""

ICON_APP = "net.meshsat.Bridge"


def signal_icon(bars: int) -> str:
    """Android's ic_stat_iridium_N, as the themed icon the package installs."""
    return f"meshsat-iridium-{max(0, min(5, int(bars or 0)))}-symbolic"


def message_notification(item: dict) -> tuple[str, str]:
    """(title, text) for a text that arrived: "Mesh: !a1b3c2ec", "Iridium: 300434…",
    "SMS: +316…", with the text under it."""
    lane = item.get("lane")
    sender = item.get("from") or "?"
    title = {"satellite": f"Iridium: {sender}", "sms": f"SMS: {sender}"}.get(lane, f"Mesh: {sender}")
    return title, item.get("text", "")


def failure_notification(event: dict) -> tuple[str, str] | None:
    """(title, text) for a message that did not go, None for any other event."""
    kind = event.get("type")
    if kind not in ("delivery_dead", "forward_error"):
        return None
    data = event.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    channel = str(data.get("channel") or data.get("interface_id") or data.get("channel_type") or event.get("message") or "").lower()
    why = data.get("last_error") or data.get("error") or event.get("message") or "The message did not go."
    if "irid" in channel or "sbd" in channel or "imt" in channel or "sat" in channel:
        return "Iridium send failed", why
    if "cell" in channel or "sms" in channel:
        return "SMS not sent", why
    if "mesh" in channel:
        return "Not sent by mesh", why
    return "Message not sent", why


def signal_notification(modem: dict | None, signal: dict | None) -> tuple[str, str, str] | None:
    """(title, text, icon) of the satellite signal while the modem is connected, as the
    Android icon in the status bar: "Iridium signal 3/5"; None while there is no modem."""
    if not modem or not modem.get("connected"):
        return None
    bars = max(0, min(5, int((signal or {}).get("bars") or 0)))
    imei = str(modem.get("imei") or "")
    port = str(modem.get("port") or "")
    if not imei:
        text = "Iridium modem connected"
    elif port.lower().startswith("ble"):
        text = f"RockBLOCK {imei[-6:]} via the MeshSat node"
    else:
        text = f"RockBLOCK {imei[-6:]} on this device"
    return f"Iridium signal {bars}/5", text, signal_icon(bars)


def sos_notification(sos: dict | None, was_active: bool) -> tuple[str, str, bool] | None:
    """(title, text, ongoing) while an SOS is on and right after it was cancelled."""
    active = bool((sos or {}).get("active"))
    if active:
        sends = (sos or {}).get("sends") or (sos or {}).get("sent_count")
        text = f"Sent {sends} times so far. It keeps trying until you cancel." if sends else "Sending your position. It keeps trying until you cancel."
        return "SOS is on", text, True
    if was_active:
        return "SOS cancelled", "Telling everyone who got it that you are safe.", False
    return None


def status(bridge: dict | None, modem: dict | None, signal: dict | None, nodes: list | None, hardware: dict | None = None, ble: dict | None = None) -> dict:
    """The state of the two radios in a few words, for a quick-settings tile, a lock-screen
    widget or a tray: the words of the Home lanes."""
    hardware, ble = hardware or {}, ble or {}
    me = (bridge or {}).get("node_id")
    others = [n for n in nodes or [] if n.get("user_id") != me]
    if bridge and bridge.get("connected"):
        name = bridge.get("node_name") or "your node"
        mesh = {"state": "working", "nodes": len(others), "detail": f"Connected to {name}."}
    elif hardware.get("node") == "bluetooth" and not ble.get("address"):
        mesh = {"state": "off", "nodes": 0, "detail": "Connect a MeshSat node or a Meshtastic radio."}
    elif bridge is None:
        mesh = {"state": "off", "nodes": 0, "detail": "The Bridge is not running on this device."}
    else:
        mesh = {"state": "trying", "nodes": 0, "detail": "Reconnecting to your node."}
    if modem and modem.get("connected"):
        bars = max(0, min(5, int((signal or {}).get("bars") or 0)))
        satellite = {"state": "working", "bars": bars, "detail": f"Iridium signal {bars}/5"}
    elif modem and modem.get("port") not in ("", "supervisor", None):
        satellite = {"state": "trying", "bars": 0, "detail": "Checking the modem."}
    else:
        satellite = {"state": "off", "bars": 0, "detail": "No satellite modem."}
    parts = []
    if satellite["state"] == "working":
        parts.append(satellite_words(satellite["bars"]))
    if mesh["state"] == "working":
        parts.append(mesh_words(mesh["nodes"]))
    summary = ", ".join(parts) if parts else "Nothing can send yet."
    icon = signal_icon(satellite["bars"]) if satellite["state"] == "working" else "meshsat-transport-mesh-symbolic" if mesh["state"] == "working" else signal_icon(0)
    # One short line for a tile: the satellite when there is one (it is what Android's icon
    # shows), else the mesh, else what is missing.
    if satellite["state"] == "working":
        tile = satellite_words(satellite["bars"])
    elif mesh["state"] == "working":
        tile = mesh_words(mesh["nodes"])
    elif mesh["state"] == "trying" or satellite["state"] == "trying":
        tile = "Mesh: connecting" if mesh["state"] == "trying" else "Satellite: checking"
    else:
        tile = "MeshSat: no node"
    return {"satellite": satellite, "mesh": mesh, "summary": summary, "icon": icon, "tile": tile}


def mesh_words(nodes: int) -> str:
    """"Mesh: 2 nodes": the mesh and how many other nodes it has heard."""
    return f"Mesh: {nodes} node" + ("" if nodes == 1 else "s")


def satellite_words(bars: int) -> str:
    """"Satellite: 3/5": the modem's signal, as the bars of the icon beside it."""
    return f"Satellite: {max(0, min(5, int(bars or 0)))}/5"
