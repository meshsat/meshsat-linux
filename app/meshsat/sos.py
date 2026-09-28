# SPDX-License-Identifier: GPL-3.0-or-later
"""The words of an SOS, as sos/SosMessages.kt on Android: the same texts on the mesh, by SMS
to the emergency contacts, and when the alarm is cancelled."""
import datetime
import time

STALE_FIX = 30 * 60  # a position older than this is "Last position", not "At"


def clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    return name[:40] if name else "A MeshSat user"


def quiet_name(name: str) -> str:
    return clean_name(name)


def utc_time(ts) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%H:%M UTC")


def where_text(position, now=None) -> str:
    """'At 52.16207, 4.50974 (within 12 m) at 14:03 UTC.', or the last position, or none.
    position is (lat, lon, source) or (lat, lon, source, accuracy_m, at)."""
    if not position:
        return "Position unknown."
    lat, lon = position[0], position[1]
    accuracy = position[3] if len(position) > 3 else None
    at = position[4] if len(position) > 4 else None
    now = now or time.time()
    within = f" (within {round(accuracy)} m)" if accuracy and accuracy > 0 else ""
    lead = "Last position" if at and now - at > STALE_FIX else "At"
    return f"{lead} {lat:.5f}, {lon:.5f}{within} at {utc_time(at or now)}."


def mesh_text(name: str, position) -> str:
    """Broadcast on the mesh."""
    return f"SOS: {clean_name(name)} needs help. {where_text(position)}"


def sms_text(name: str, position) -> str:
    """To each emergency contact, from the phone's own SIM: plain ASCII with a map link, at
    most 160 characters so it goes as one SMS whatever the name and the position."""
    ascii_name = "".join(ch for ch in clean_name(name) if 32 <= ord(ch) <= 126).strip() or "A MeshSat user"
    base = f"SOS: {ascii_name} needs help. {where_text(position)}"
    if not position:
        return f"{base} Sent by MeshSat."
    return f"{base} https://osm.org/?mlat={position[0]:.5f}&mlon={position[1]:.5f}"


def cancel_text(name: str) -> str:
    """Sent on every route that carried the SOS, once the user cancels it."""
    return f"Alarm cancelled: {quiet_name(name)} is safe and needs no help now."


def test_text(name: str) -> str:
    """A test of the alarm routes: says it is a test and raises nothing at the Hub."""
    return f"Test from {quiet_name(name)}: checking the MeshSat alarm routes. No help needed."


def join_and(items) -> str:
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
