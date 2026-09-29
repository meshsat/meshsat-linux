# SPDX-License-Identifier: GPL-3.0-or-later
"""What an SOS says on each route, as sos/SosMessages.kt on Android. The Hub raises an alarm for
any incoming text that contains one of HUB_ALARM_WORDS, anywhere and in any case, and a
MeshSat kit on the same mesh forwards what it hears to the Hub: so an SOS says "SOS", and a
test or a cancellation must never contain one of those words, not even inside the sender's
name."""
import datetime
import time

HUB_ALARM_WORDS = ("SOS", "MAYDAY", "EMERGENCY")
MAX_NAME = 24  # longest name used in a message, so an SMS stays in one part
NO_NAME = "A MeshSat user"
STALE_FIX = 2 * 60  # a fix older than this is called the last known position


def contains_alarm_word(text: str) -> bool:
    upper = (text or "").upper()
    return any(word in upper for word in HUB_ALARM_WORDS)


def clean_name(name: str) -> str:
    """The user's name as it goes into a message: printable, trimmed, short."""
    printable = "".join(ch for ch in (name or "") if ch.isprintable() and ch not in "\t\n\r").strip()
    printable = " ".join(printable.split())
    return printable[:MAX_NAME].strip() or NO_NAME


def name_for_sos(sos_name: str, callsign: str) -> str:
    """The name an SOS, its test and its cancellation carry: the SOS name, or the Hub callsign
    when the name is blank (SosController.start: sosName.ifBlank { hubCallsign }); clean_name
    makes a blank one "A MeshSat user"."""
    return sos_name if (sos_name or "").strip() else (callsign or "")


def name_placeholder(callsign: str) -> str:
    """Safety's name field when it is empty (SosScreens.kt:502: callsign.ifBlank { "A MeshSat
    user" }): the name the SOS would carry."""
    return callsign if (callsign or "").strip() else NO_NAME


def quiet_name(name: str) -> str:
    """The name for a message that must not raise an alarm."""
    clean = clean_name(name)
    return "This phone" if contains_alarm_word(clean) else clean


def coordinates(lat: float, lon: float) -> str:
    return f"{lat:.5f}, {lon:.5f}"


def utc_time(ts) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%H:%M") + " UTC"


def where_text(position, now=None) -> str:
    """'At 52.16207, 4.50974 (within 12 m) at 14:03 UTC.', or the last position, or none.
    position is (lat, lon, source) or (lat, lon, source, accuracy_m, at)."""
    if not position:
        return "Position unknown."
    lat, lon = position[0], position[1]
    accuracy = position[3] if len(position) > 3 else None
    at = position[4] if len(position) > 4 else None
    now = time.time() if now is None else now
    within = f" (within {round(accuracy)} m)" if accuracy and accuracy > 0 else ""
    lead = "Last position" if at is not None and now - at > STALE_FIX else "At"
    return f"{lead} {coordinates(lat, lon)}{within} at {utc_time(at if at is not None else now)}."


def mesh_text(name: str, position, now=None) -> str:
    """Broadcast on the mesh."""
    return f"SOS: {clean_name(name)} needs help. {where_text(position, now)}"


def sms_text(name: str, position, now=None) -> str:
    """To each emergency contact, from the phone's own SIM: plain ASCII with a map link, at
    most 160 characters so it goes as one SMS whatever the name and the position."""
    ascii_name = "".join(ch for ch in clean_name(name) if 32 <= ord(ch) <= 126).strip() or NO_NAME
    base = f"SOS: {ascii_name} needs help. {where_text(position, now)}"
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
