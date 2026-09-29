# SPDX-License-Identifier: GPL-3.0-or-later
"""Home's cards and the node banner in MeshSat Android's words and rules (ui/screens/
DashboardScreen.kt:105-805, ui/components/CheckMailboxButton.kt, ui/components/NodeLinkBanner.kt,
ui/screens/HomeLanes.kt:150-186). Pure: no GTK, tested on the runner."""
import math
import time

from . import words

# ── Arrange Home (DashboardScreen.kt:695-719) ─────────────────────────────────────────────────
HOME_CARDS = ("sos", "queue", "location", "signals", "mailbox", "activity")
CARD_LABELS = {"sos": "SOS", "queue": "Message queue", "location": "Location", "signals": "Signal history",
               "mailbox": "Satellite mailbox", "activity": "Recent messages"}
OLD_DEFAULT = "transports,signals,sos,location,queue,burst,reticulum,activity"
ARRANGE_TITLE = "Arrange Home"
ARRANGE_TEXT = "Move a card up or down. The lanes stay at the top."
APPLY, CANCEL = "Apply", "Cancel"


def home_order(saved: str | None) -> list:
    """Android's homeOrder: blank or the old default → the default; else the known ids in the
    saved order, each once, then the known ids not listed."""
    if not saved or not saved.strip() or saved == OLD_DEFAULT:
        return list(HOME_CARDS)
    out = []
    for part in saved.split(","):
        card = part.strip()
        if card in HOME_CARDS and card not in out:
            out.append(card)
    return out + [c for c in HOME_CARDS if c not in out]


def moved(order: list, index: int, up: bool) -> list:
    """The draft with one card swapped with its neighbour; the ends do not move further."""
    other = index - 1 if up else index + 1
    if not 0 <= index < len(order) or not 0 <= other < len(order):
        return list(order)
    draft = list(order)
    draft[index], draft[other] = draft[other], draft[index]
    return draft


# ── Getting started (Onboarding.kt:128-195) ───────────────────────────────────────────────────
GETTING_STARTED = "Getting started"
HIDE = "Hide"
DONE, TO_DO = "Done", "To do"


def checklist_count(steps: list) -> str:
    return f"{sum(1 for s in steps if s[2])} of {len(steps)} done"


def checklist_shown(steps: list, dismissed: bool) -> bool:
    return not dismissed and not all(s[2] for s in steps)


# ── Satellite mailbox (CheckMailboxButton.kt:30-105) ──────────────────────────────────────────
MAILBOX_TITLE = "Satellite mailbox"
CHECK_MAILBOX = "Check Mailbox"
CHECKING = "Checking mailbox..."


def mailbox_text(result: dict | None) -> str | None:
    """describeMailboxResult, from the Bridge's kept outcome (GET /api/iridium/mailbox)."""
    if not result:
        return None
    kind = result.get("kind")
    if kind == "not_connected":
        return "The modem is not connected."
    if kind == "held":
        return f"Held after a failed session: try again in {int(result.get('seconds') or 0)} s."
    if kind == "session_failed":
        mo = result.get("mo_status")
        return "No network: the modem sees no satellite. No credit used." if mo == 32 else f"The session failed (status {mo})."
    if kind == "no_answer":
        return "The modem did not answer."
    if kind == "link_lost":
        return "The link to the node dropped during the session; what it fetched is unknown."
    if kind == "checked":
        received, queued = int(result.get("received") or 0), int(result.get("still_queued") or 0)
        head = "No new messages." if received == 0 else "1 message received." if received == 1 else f"{received} messages received."
        return head + (f" {queued} more waiting." if queued > 0 else "")
    return None


# ── Your position (DashboardScreen.kt:157-175, 275-315) ───────────────────────────────────────
POSITION_TITLE = "Your position"
WAITING_FOR_FIX = "Waiting for a position. Location must be allowed, and the phone needs a view of the sky."


def fix_age(seconds: float) -> str:
    s = int(seconds)
    if s < 5:
        return "just now"
    if s < 60:
        return f"{s} s ago"
    return f"{s // 60} min ago"


def half_up(value: float, digits: int) -> str:
    """Kotlin's "%.Nf" (Locale.ROOT): half away from zero, not Python's half to even."""
    scale = 10 ** digits
    rounded = math.floor(abs(value) * scale + 0.5) / scale
    return f"{math.copysign(rounded, value) if value else 0.0:.{digits}f}"


def position_lines(fix: dict | None, now: float | None = None) -> list:
    """[coordinates, accuracy and age, the extras] or [the waiting sentence]. `fix`: latitude,
    longitude, accuracy (m, None unknown), altitude (m, None), speed (m/s, None), heading (deg, None), at (s)."""
    if not fix:
        return [WAITING_FOR_FIX]
    now = time.time() if now is None else now
    lines = [f"{half_up(fix['latitude'], 5)}, {half_up(fix['longitude'], 5)}"]
    accuracy = fix.get("accuracy")
    age = fix_age(now - fix["at"]) if fix.get("at") else "--"
    lines.append((f"within {int(accuracy)} m, " if accuracy is not None and accuracy >= 0 else "") + age)
    extras = []
    if fix.get("altitude") is not None:
        extras.append(f"Height {int(fix['altitude'])} m")
    speed = fix.get("speed")
    if speed is not None and speed >= 0.5:
        part = f"moving {half_up(speed * 3.6, 1)} km/h"
        if fix.get("heading") is not None and fix["heading"] >= 0:
            part += f", heading {int(fix['heading'])}°"
        extras.append(part)
    if extras:
        lines.append(". ".join(extras) + ".")
    return lines


# ── Message queue (DashboardScreen.kt:316-340, QueueBar, StatBadge) ───────────────────────────
QUEUE_TITLE = "Message queue"
OPEN_QUEUE = "Open the queue"
LANES = (("Satellite", ("iridium_0", "iridium_imt_0")), ("Mesh", ("mesh_0",)), ("SMS", ("cellular_0",)))
WAITING_STATES = ("queued", "retry", "held", "sending")


def queue_counts(stats: list) -> dict:
    """{"lanes": [(label, depth, fill)], "badges": [(label, count, tone)]} from GET /api/deliveries/stats."""
    rows = [r for r in stats or [] if isinstance(r, dict)]
    lanes = []
    for label, channels in LANES:
        depth = sum(int(r.get("count") or 0) for r in rows if r.get("channel") in channels and r.get("status") in WAITING_STATES)
        fill = min(max(depth / 20.0, 0.05), 1.0) if depth > 0 else 0.0
        lanes.append((label, depth, fill))

    def total(*states) -> int:
        return sum(int(r.get("count") or 0) for r in rows if r.get("status") in states)

    badges = [("Waiting", total("queued", "retry", "held"), "amber"), ("Sending", total("sending"), "amber"),
              ("Failed", total("failed"), "red"), ("Gave up", total("dead"), "muted")]
    return {"lanes": lanes, "badges": badges}


def lane_depth(stats: list, lane: str) -> int:
    channels = dict(LANES).get({"satellite": "Satellite", "mesh": "Mesh", "sms": "SMS"}.get(lane, lane), ())
    return sum(int(r.get("count") or 0) for r in stats or [] if isinstance(r, dict) and r.get("channel") in channels and r.get("status") in WAITING_STATES)


# ── Signal charts (SignalChart, DashboardScreen.kt:433-571) ───────────────────────────────────
MOBILE_TITLE = "Mobile signal, last 6 hours"
MOBILE_RANGE = (-120.0, -50.0)
BUCKET_MS = 1_800_000


def chart_points(records: list) -> list:
    """The 30-minute bucket averages (sorted) when there are at least two buckets, else the raw
    values. `records`: {"timestamp" (ms), "value" (dBm)}."""
    buckets = {}
    for r in sorted(records, key=lambda r: r["timestamp"]):
        buckets.setdefault(r["timestamp"] // BUCKET_MS, []).append(float(r["value"]))
    if len(buckets) >= 2:
        return [sum(v) / len(v) for _, v in sorted(buckets.items())]
    return [float(r["value"]) for r in sorted(records, key=lambda r: r["timestamp"])]


def dbm(value: float) -> str:
    """formatValue: ${v.toInt()} dBm (toward zero)."""
    return f"{int(value)} dBm"


def chart_summary(records: list) -> dict | None:
    """{"latest", "min", "avg", "max"} as their labels, or None with nothing to draw."""
    if not records:
        return None
    points = chart_points(records)
    latest = max(records, key=lambda r: r["timestamp"])["value"]
    return {"latest": dbm(latest), "min": f"min: {dbm(min(points))}", "avg": f"avg: {dbm(sum(points) / len(points))}", "max": f"max: {dbm(max(points))}"}


# ── The satellite lane's pass line (HomeLanes.kt:156-165) ─────────────────────────────────────
HIGH_PASS_DEG = 40.0


def pass_line(passes: list, now: float) -> str | None:
    ordered = sorted(passes or [], key=lambda p: p.get("aos", 0))
    for p in ordered:
        if p.get("is_active") and p.get("peak_elev_deg", 0) >= HIGH_PASS_DEG and p.get("los", 0) > now:
            return "A satellite is high overhead now."
    for p in ordered:
        if p.get("aos", 0) > now and p.get("peak_elev_deg", 0) >= HIGH_PASS_DEG:
            return f"Next high pass {words.in_time(p['aos'], now)}."
    return None


def queue_prefix(depth: int) -> str:
    return f"{words.count(depth, 'message')} waiting to go out. " if depth > 0 else ""


# ── The node banner (NodeLinkBanner.kt:117-139) ───────────────────────────────────────────────
def node_link_banner_text(bluetooth_off: bool, mesh_up: bool, since: str | None, minutes: int) -> str:
    how = "" if since is None else f" since {since}" + (f" ({minutes} min)" if minutes >= 1 else "")
    if bluetooth_off:
        return f"Bluetooth is off{how}, so the phone cannot reach your MeshSat node. Nothing goes out by mesh or satellite. Tap to switch it on."
    what = "the node's modem" if mesh_up else "your MeshSat node"
    return f"Cannot reach {what}{how}. Nothing goes out by mesh or satellite. Tap to see."


# ── Recent messages (DashboardScreen.kt:341-368, ActivityLogEntry) ────────────────────────────
RECENT_TITLE = "Recent messages"
NO_MESSAGES = "No messages yet."


def recent_text(text: str) -> str:
    """The first 80 characters, newlines as spaces."""
    return (text or "").replace("\r", " ").replace("\n", " ")[:80]


def recent(messages: list, sms: list, limit: int = 20) -> list:
    """The 20 newest texts of every transport, newest first: the Bridge's messages with words
    (its SMS rows come in `sms`, the SIM's store in the same shape, messages.sms_as_messages)."""
    texts = [m for m in messages or [] if m.get("portnum_name") == "TEXT_MESSAGE_APP" and m.get("decoded_text") and m.get("transport") != "sms"]
    texts += [m for m in sms or [] if m.get("decoded_text")]
    texts.sort(key=lambda m: m.get("rx_time") or 0, reverse=True)
    return texts[:limit]


def recent_lane(transport: str | None) -> str | None:
    """ActivityLogEntry's colours: mesh, satellite and SMS in their lane's colour, anything else muted (None)."""
    lane = words.transport_lane(transport or "mesh")
    return lane if lane in ("mesh", "satellite", "sms") else None
