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


def describe(level, voltage=None, hours_left: float | None = None, with_voltage: bool = True) -> str | None:
    """NodeBattery.describe as the node's own card calls it (SettingsScreen.kt:411-414): "82%,
    3.98 V, about 14 h left", "82%" when the node sends no voltage, "On USB power", None when it
    has reported no battery. The time left is hours_left() over the node's readings, which the
    Bridge keeps (GET /api/telemetry)."""
    level = int(level or 0)
    if level > 100:
        return "On USB power"
    if level <= 0:
        return None
    volts = float32(voltage)
    text = f"{level}%" + (f", {words.fixed(volts, 2)} V" if with_voltage and volts > 0 else "")
    return text + (f", {time_left_text(hours_left)}" if hours_left is not None else "")


# NodeBattery.hoursLeft (ble/NodeBattery.kt): the rate the level has really been falling
EXTERNAL_POWER = 101  # what Meshtastic sends as the battery level of a node on external power
WINDOW_S = 3 * 3600  # readings older than this do not count
MIN_SPAN_S = 30 * 60  # an estimate needs this much time on battery behind it...
MIN_DROP = 2  # ...and this many points of drop


def hours_left(readings: list, now: float) -> float | None:
    """Hours left at the rate the level has been falling: a least-squares line through the
    battery readings ((at, level), at in seconds) of the last three hours since the node last ran
    on external power. None until they span half an hour and fell by two points, so nothing is
    shown from a guess about the cell's capacity."""
    recent = sorted((r for r in readings if r[0] >= now - WINDOW_S), key=lambda r: r[0])
    last_usb = max((i for i, r in enumerate(recent) if r[1] > 100), default=-1)
    on_battery = [r for r in recent[last_usb + 1:] if 0 <= r[1] <= 100]
    if len(on_battery) < 3 or on_battery[-1][0] - on_battery[0][0] < MIN_SPAN_S:
        return None
    if max(r[1] for r in on_battery) - on_battery[-1][1] < MIN_DROP:
        return None
    t0 = on_battery[0][0]
    xs = [(r[0] - t0) / 3600.0 for r in on_battery]
    ys = [float(r[1]) for r in on_battery]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if slope >= 0:
        return None
    return on_battery[-1][1] / -slope


def time_left_text(hours: float) -> str:
    """"about 40 min left", "about 14 h left", "about 3 days left" (Kotlin's roundToInt, half up)."""
    if hours < 1:
        return f"about {max(half_up(hours * 60 / 5) * 5, 5)} min left"
    if hours < 48:
        return f"about {half_up(hours)} h left"
    return f"about {half_up(hours / 24)} days left"


def readings_of(telemetry: list) -> list:
    """(at, level) from the Bridge's telemetry records (GET /api/telemetry: battery_level,
    created_at in RFC 3339); records without a time or a level are skipped."""
    import datetime  # noqa: PLC0415
    import re  # noqa: PLC0415

    out = []
    for rec in telemetry or []:
        stamp = str((rec or {}).get("created_at") or "")
        level = (rec or {}).get("battery_level")
        if not stamp or level is None:
            continue
        stamp = re.sub(r"(\.\d{6})\d+", r"\1", stamp.replace("Z", "+00:00"))
        try:
            out.append((datetime.datetime.fromisoformat(stamp).timestamp(), int(level)))
        except ValueError:
            continue
    return out


def float32(value) -> float:
    """The node's voltage as the float it is (DeviceMetrics.voltage): Kotlin formats that float,
    so 3.975, which is 3.97499990... as a float, is "3.97" there and must be here."""
    import struct  # noqa: PLC0415

    try:
        return struct.unpack("<f", struct.pack("<f", float(value or 0)))[0]
    except (OverflowError, TypeError, ValueError):
        return 0.0


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


def rows(node: dict, mine: bool, now_s: float, live: dict | None = None) -> list:
    """(label, value, mono) in the sheet's order: Last heard and Signal only for someone else's
    node, Hardware only when known. `live`: the newest packet heard from it over the air."""
    out = []
    if not mine:
        out.append((LAST_HEARD, words.ago(node.get("last_heard") or 0, now_s), False))
    level = battery(node.get("battery_level"))
    out.append((BATTERY, level or NOT_REPORTED, bool(level) and int(node.get("battery_level") or 0) <= 100))
    if not mine:
        out.append((SIGNAL, node_signal(node, live)["long"], False))
    if node.get("hw_model"):
        out.append((HARDWARE, words.hardware_name(node.get("hw_model"), node.get("hw_model_name") or ""), False))
    out.append((POSITION, position(node, now_s), has_position(node)))
    return out


def live_hops(packet: dict | None) -> int:
    """A packet's hops as Android counts them: 0 heard directly, more relayed, -1 not known (the
    Bridge counts `hops` only for a packet that carried `hop_start`, which it reports since Bridge change B23)."""
    if not packet:
        return -1
    if int(packet.get("hop_start") or 0) <= 0:
        return -1
    return int(packet.get("hops") or 0)


def node_signal(node: dict, live: dict | None = None) -> dict:
    """{"short", "long", "direct", "snr", "hops"}: `live` is the newest packet this phone's node
    heard over the air from that node ({snr, rssi, hops, hop_start}); else the node list."""
    def direct(snr: float, rssi: int, measured: str) -> dict:
        long = f"Heard directly. SNR {half_up(snr, 1)} dB" + (f", RSSI {int(rssi)} dBm" if rssi else "") + measured
        return {"short": f"{half_up(snr, 1)} dB", "long": long, "direct": True, "snr": float(snr), "hops": 0}

    def relayed(hops: int) -> dict:
        return {"short": words.count(hops, "hop"), "long": f"Heard through other nodes, {words.count(hops, 'hop')} away.",
                "direct": False, "snr": None, "hops": hops}

    hops = live_hops(live)
    if live is not None and hops == 0:
        return direct(float(live.get("snr") or 0), int(live.get("rssi") or 0), ".")
    if live is not None and hops > 0:
        return relayed(hops)
    node_hops = int(node.get("hops_away") or 0)  # the Bridge leaves out a 0 (omitempty)
    snr = float(node.get("snr") or 0)
    if node_hops == 0 and snr != 0:
        return direct(snr, 0, ", as your node last measured it.")
    if node_hops > 0:
        return relayed(node_hops)
    return {"short": "-", "long": NOT_MEASURED, "direct": False, "snr": None, "hops": -1}


def signal_order(sig: dict) -> tuple:
    """Android's Signal sort: heard directly first by SNR high to low, then relayed by fewest hops,
    then not measured."""
    if sig["direct"]:
        return (0, -(sig["snr"] or 0))
    if sig["hops"] > 0:
        return (1, sig["hops"])
    return (2, 0)


def name_order(node: dict) -> str:
    """Android's Name sort: the long name, else the short one, else the id, lower-cased."""
    return ((node.get("long_name") or "").strip() or (node.get("short_name") or "").strip() or node_id(node)).lower()


def battery_cell(level) -> str:
    """NodeBattery's cell: "USB" above 100, "N%" when reported, "-" otherwise."""
    level = int(level or 0)
    if level > 100:
        return "USB"
    return f"{level}%" if level > 0 else "-"


def live_packet(packets: list, node: str) -> dict | None:
    """The newest packet this phone's node heard over the air from `node` (the Bridge's packet
    feed: bearer lora, dir rx), as Android keeps the last link signal per node."""
    newest, newest_at = None, -1.0
    for p in packets or []:
        if p.get("bearer") == "lora" and p.get("dir") == "rx" and p.get("from") == node:
            at = _packet_time(p)
            if at >= newest_at:
                newest, newest_at = p, at
    return newest


def _packet_time(p: dict) -> float:
    import datetime  # noqa: PLC0415
    import re  # noqa: PLC0415

    try:
        return datetime.datetime.fromisoformat(re.sub(r"\.\d+", "", str(p.get("time", ""))).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0

