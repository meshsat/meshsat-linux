# SPDX-License-Identifier: GPL-3.0-or-later
"""The words the app shows for its own machinery, as ui/Words.kt: one place, so a channel or a
state is called the same thing on every screen. Internal ids (iridium_0, sms_0) and raw states
(dead, retry) never reach the user: they read Satellite, SMS, "Gave up", "Waiting to retry"."""
import re
import time


def channel(id_: str) -> str:
    """An interface or channel id, as the user knows it."""
    # Android's 9704 link is iridium9704_0; the Bridge's is iridium_imt_0 (the IMT channel).
    if id_.startswith("iridium9704") or id_.startswith("iridium_imt"):
        return "Satellite (RockBLOCK 9704)"
    if id_.startswith("iridium"):
        return "Satellite"
    if id_.startswith("mesh"):
        return "Mesh"
    if id_.startswith("sms"):
        return "SMS"
    if "relay" in id_:  # before hub: the relay is a tunnel to another bridge, not the Hub itself
        return "Hub relay"
    if id_.startswith("hub"):
        return "Hub"
    if id_.startswith("mqtt"):
        return "MQTT broker"
    if id_.startswith("aprs"):
        return "Ham radio"
    if id_.startswith("tcp_rns") or id_.startswith("rns"):
        return "Reticulum"
    if not id_.strip():
        return "Unknown"
    return id_


def transport(t: str) -> str:
    """A message's transport field ("iridium", "mesh", "sms", ...), as the user knows it."""
    low = (t or "").lower()
    if low in ("iridium", "sbd", "iridium9704", "imt", "iridium_imt"):
        return "Satellite"
    if low in ("mesh", "meshtastic", "lora", "radio"):
        return "Mesh"
    if low in ("sms", "cellular"):
        return "SMS"
    if low in ("mqtt", "hub"):
        return "Hub"
    if low == "aprs":
        return "Ham radio"
    if low in ("reticulum", "rns"):
        return "Reticulum"
    if low == "tak":
        return "TAK"
    return t[:1].upper() + t[1:] if t else ""


def transport_lane(t: str) -> str:
    """The lane (the colour) of a transport: satellite, mesh, sms, hub, radio, or none."""
    return {"Satellite": "satellite", "Mesh": "mesh", "SMS": "sms", "Hub": "hub", "Hub relay": "hub", "Ham radio": "radio"}.get(transport(t), "none")


def channel_lane(id_: str) -> str:
    """The lane (the colour) of a channel id."""
    if id_.startswith("iridium"):
        return "satellite"
    if id_.startswith("mesh"):
        return "mesh"
    if id_.startswith("sms"):
        return "sms"
    if id_.startswith("mqtt") or id_.startswith("hub") or "relay" in id_:
        return "hub"
    if id_.startswith("aprs"):
        return "radio"
    return "none"


def delivery_state(status: str) -> str:
    """A delivery's status in the queue."""
    return {"queued": "Waiting", "retry": "Waiting to retry", "held": "On hold until the link is back", "sending": "Sending", "sent": "Sent",
            "delivered": "Delivered", "acked": "Delivered", "failed": "Failed", "dead": "Gave up", "expired": "Expired", "denied": "Blocked by a rule",
            "cancelled": "Cancelled"}.get((status or "").lower(), (status[:1].upper() + status[1:]) if status else "")


def delivery_tone(status: str) -> str:
    """The colour of a delivery status: working (green), trying (amber), failed (red), or muted."""
    low = (status or "").lower()
    if low in ("sent", "delivered", "acked"):
        return "green"
    if low in ("queued", "retry", "held", "sending"):
        return "amber"
    if low in ("failed", "dead", "expired", "denied"):
        return "red"
    return "muted"


def link_state(state: str) -> str:
    """An interface's link state."""
    return {"online": "Working", "connecting": "Connecting", "offline": "Off", "error": "Not working", "disabled": "Switched off"}.get(
        (state or "").lower(), (state[:1].upper() + state[1:]) if state else "")


def count(n: int, one: str, many: str | None = None) -> str:
    """"1 message", "3 messages"."""
    return f"{n} {one if n == 1 else (many or one + 's')}"


def ago(epoch_s: float, now_s: float | None = None) -> str:
    """A moment in the past, relative: "just now", "4 min ago", "2 h ago", "3 days ago"."""
    if not epoch_s or epoch_s <= 0:
        return "never"
    now_s = time.time() if now_s is None else now_s
    s = max(0, int(now_s - epoch_s))
    if s < 45:
        return "just now"
    if s < 3600:
        return f"{(s + 30) // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return count(s // 86400, "day") + " ago"


def in_time(epoch_s: float, now_s: float | None = None) -> str:
    """A moment ahead, relative: "now", "in 4 min", "in 2 h 10 min"."""
    now_s = time.time() if now_s is None else now_s
    s = int(epoch_s - now_s)
    if s <= 30:
        return "now"
    if s < 3600:
        return f"in {(s + 30) // 60} min"
    return f"in {s // 3600} h {(s % 3600) // 60} min"


# MeshtasticProtocol.hardwareNames: the models people know by another name than the proto's.
HARDWARE_NAMES = {4: "LilyGO T-Beam", 7: "LilyGO T-Echo", 9: "RAK WisBlock 4631", 12: "LilyGO T-Beam Supreme", 43: "Heltec V3", 44: "Heltec Wireless Stick Lite V3",
                  48: "Heltec Wireless Tracker", 50: "LilyGO T-Deck", 51: "LilyGO T-Watch S3", 65: "Heltec Capsule Sensor V3", 69: "Heltec Mesh Node T114",
                  71: "Seeed Card Tracker T1000-E", 80: "M5Stack CoreS3", 81: "Seeed XIAO ESP32-S3", 88: "Seeed XIAO nRF52840 kit", 89: "ThinkNode M1", 90: "ThinkNode M2",
                  94: "Heltec Mesh Pocket", 95: "Seeed Solar Node", 99: "Seeed Wio Tracker L1", 102: "LilyGO T-Deck Pro", 103: "LilyGO T-Lora Pager", 110: "Heltec V4",
                  255: "Custom hardware"}


def hardware_name(code, proto_name: str = "") -> str:
    """A node's hardware model as people recognise it (MeshtasticProtocol.hardwareName): the
    table, else the proto's enum name in words ("HELTEC_V3" -> "Heltec V3"), else the code."""
    try:
        code = int(code or 0)
    except (TypeError, ValueError):
        code = 0
    if code == 0 and not proto_name:
        return "Unknown model"
    if code in HARDWARE_NAMES:
        return HARDWARE_NAMES[code]
    if proto_name:
        return " ".join(w if any(c.isdigit() for c in w) or len(w) <= 3 else w.lower().capitalize() for w in proto_name.split("_"))
    return f"Unknown model (code {code})"


def fixed(value, digits: int = 1) -> str:
    """A number with `digits` decimals as Kotlin's "%.1f".format writes it: the double's exact
    value rounded half up (-3.25 is "-3.3"; Python's own format would write "-3.2")."""
    from decimal import ROUND_HALF_UP, Decimal  # noqa: PLC0415

    quantum = Decimal(1).scaleb(-digits)
    return str(Decimal(float(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def stamp_epoch(value) -> float | None:
    """A time stamp of the Bridge as seconds since the epoch: RFC 3339 ("2026-09-28T17:00:00Z",
    with or without fractions), SQLite's "2026-09-28 17:00:00" (UTC), or a number already;
    None for nothing, Go's zero time, or words that are not a time (AuditScreen.kt's
    parseUtcStamp)."""
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    t = (value or "").strip() if isinstance(value, str) else ""
    if not t or t.startswith("0001-01-01"):
        return None
    from datetime import datetime, timezone  # noqa: PLC0415

    t = re.sub(r"(\.\d{6})\d+", r"\1", t)  # Go writes nanoseconds; Python reads microseconds
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(t)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def local_stamp(epoch_s: float, now_s: float | None = None) -> str:
    """The clock time, local: "17:04:09" today, "27 Sep 17:04:09" another day (AuditScreen.kt's
    localStamp)."""
    now_s = time.time() if now_s is None else now_s
    at, today = time.localtime(epoch_s), time.localtime(now_s)
    if at[:3] == today[:3]:
        return time.strftime("%H:%M:%S", at)
    return f"{at.tm_mday} {time.strftime('%b %H:%M:%S', at)}"


def join_and(items: list) -> str:
    """"a", "a and b", "a, b and c"."""
    items = [str(i) for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
