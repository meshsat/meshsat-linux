# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hub page, the Setup row and the Home lane in MeshSat Android's words
(SettingsScreen.kt:1625-1900, SetupScreen.kt:115-133, HomeLanes.kt:215-223), read from the
Bridge's GET /api/routing/hub: its settings, `enabled` ("Use the Hub"), and the link's `state`,
`last_error` and `running_as` (MESHSAT-1417). A Bridge from before that change reports only
`link` (connected, disconnected or none), which reads as the nearest of Android's states."""

TITLE = "Hub"
CARD = "Hub connection"
USE = "Use the Hub"
SWITCHED_OFF = "Switched off"
CONNECTING = "Connecting"
CANNOT_REACH = "Cannot reach the Hub"
NOT_CONNECTED = "Not connected"
NOT_SET_UP = "Not set up: scan the Hub's QR code"
SCAN = "Scan the Hub's QR code"
SCAN_NOTE = "On the Hub, open Fleet and add a bridge for this phone: the QR code it shows fills in everything, certificates included."
TEST = "Test the connection"
TESTING = "..."
DETAILS = "Connection details"
HIDE_DETAILS = "Hide connection details"
URL_LABEL, URL_HINT = "Hub MQTT URL", "wss://mqtt-hub.meshsat.net/mqtt"
# Android's placeholder is "auto (Android ID)": a Bridge left without one runs as its
# MESHSAT_BRIDGE_ID, else the host name.
BRIDGE_LABEL, BRIDGE_HINT = "Bridge ID", "auto (host name)"
CALLSIGN_LABEL, CALLSIGN_HINT = "Callsign", "TAK callsign"
USERNAME_LABEL = "Username"
PASSWORD_LABEL = "Password"
PASSWORD_KEPT = "••••••••"  # the Bridge never gives the password back; Android shows its own masked
SHOW_PASSWORD, HIDE_PASSWORD = "Show password", "Hide password"
INTERVAL_LABEL = "Health interval (seconds)"
INTERVAL_DEFAULT = "30"
SAVE = "Save"
# Android: "Saved. Restart the app to use them." Its settings apply when its gateway service
# starts; here they apply when the Bridge starts, and restarting the app would not restart it.
SAVED = "Saved. Restarting the Bridge to use them."
NOT_SAVED = "The Hub settings were not saved."
CLOSING = ("The Hub is the control room: with it, this phone shows in the fleet and on the map, "
           "and SOS alerts reach it over the internet as well as by satellite.")

# The Setup list's row (SetupScreen.kt:117-131)
ROW_NOT_SET_UP = "Not set up. Scan the Hub's QR code."
ROW_CONNECTED = "Connected"


def state(hub: dict | None) -> str:
    """"connecting", "connected", "error", "disconnected", or "" when no Hub link runs."""
    hub = hub or {}
    if "state" in hub:
        return hub.get("state") or ""
    return {"connected": "connected", "disconnected": "disconnected"}.get(hub.get("link") or "", "")


def enabled(hub: dict | None) -> bool:
    return (hub or {}).get("enabled") is not False


def running_as(hub: dict | None) -> str:
    hub = hub or {}
    return hub.get("running_as") or hub.get("bridge_id") or ""


def dot(hub: dict | None) -> str:
    """The dot follows the link, never the switch (SettingsScreen.kt:1629-1634)."""
    return {"connected": "green", "connecting": "amber", "error": "red"}.get(state(hub), "muted")


def status(hub: dict | None) -> str:
    """The Hub page's status line (SettingsScreen.kt:1635-1643), in Android's order."""
    s = state(hub)
    if not enabled(hub):
        return SWITCHED_OFF
    if s == "connected":
        return f"Connected as {running_as(hub)}"
    if s == "connecting":
        return CONNECTING
    if s == "error":
        return CANNOT_REACH
    if s == "disconnected":
        return NOT_CONNECTED
    return NOT_SET_UP


def why(hub: dict | None) -> str:
    """"Why: …" only with the switch on, the link failed and a reason given (:1681-1690)."""
    reason = ((hub or {}).get("last_error") or "").strip()
    if enabled(hub) and state(hub) == "error" and reason:
        return f"Why: {(hub or {}).get('last_error')}"
    return ""


def setup_row(hub: dict | None) -> tuple:
    """(detail, tone) of the Setup list's Hub row; it does not look at the switch."""
    return {"connected": (ROW_CONNECTED, "green"), "connecting": (CONNECTING, "amber"), "error": (CANNOT_REACH, "red"),
            "disconnected": (NOT_CONNECTED, "amber")}.get(state(hub), (ROW_NOT_SET_UP, "muted"))


def lane(hub: dict | None, bridge_up: bool = True) -> tuple:
    """(lane state, sentence) of the Home lane (HomeLanes.kt:217-223); it does not look at the
    switch either."""
    s = state(hub) if bridge_up else ""
    if s == "connected":
        return "working", f"Connected as {running_as(hub)}."
    if s == "connecting":
        return "trying", "Connecting to the Hub."
    if s == "error":
        return "failed", "Cannot reach the Hub. It keeps trying by itself."
    if s == "disconnected":
        return "trying", "Not connected. It keeps trying by itself."
    return "off", "Scan the Hub's QR code to connect this phone."


def card_waited(seconds: int) -> str:
    """The Hub card's line while a provisioning claim waits (SettingsScreen.kt:1664-1680)."""
    return f"Getting the Hub's settings, {max(0, int(seconds))} s"


def cut_utf16(value: str, units: int) -> str:
    """The first `units` UTF-16 units, as Kotlin's take(); a surrogate pair is never split."""
    out, used = [], 0
    for ch in value:
        size = 2 if ord(ch) > 0xFFFF else 1
        if used + size > units:
            break
        out.append(ch)
        used += size
    return "".join(out)


def ping_result(status_code: int, body, error: str | None) -> str:
    """"142ms", "Not connected", or "failed: " and the first 30 units of the reason (:1726-1741)."""
    if status_code == 200 and isinstance(body, dict) and "elapsed_ms" in body:
        return f"{int(body['elapsed_ms'])}ms"
    if status_code == 409:
        return NOT_CONNECTED
    message = error if error is not None else None
    return "failed: " + (cut_utf16(message, 30) if message is not None else "null")


def ping_green(result: str) -> bool:
    """Green when the text ends with "ms", Android's own rule (a reason ending so shows green too)."""
    return result.endswith("ms")


def interval_digits(value: str) -> str:
    """The field keeps digits only, at most four (:1828)."""
    return "".join(ch for ch in value if ch.isdigit())[:4]


def form(hub: dict | None) -> dict:
    """The form's fields as the Bridge has them; the password never comes back."""
    hub = hub or {}
    interval = hub.get("health_interval") or 0
    return {"url": hub.get("url") or "", "bridge_id": hub.get("bridge_id") or "", "callsign": hub.get("callsign") or "",
            "username": hub.get("username") or "", "interval": str(interval) if interval else INTERVAL_DEFAULT,
            "has_password": bool(hub.get("has_password"))}


def save_body(url: str, bridge_id: str, callsign: str, username: str, password: str, interval: str) -> dict:
    """What Save writes: every field as typed, as Android stores them. The Bridge keeps a URL, a
    bridge id, a username or a password sent empty; an empty callsign clears it; an interval
    that is not a number is 0, the Bridge's default (Android reads it as 30, the same)."""
    body = {"url": url, "bridge_id": bridge_id, "callsign": callsign, "username": username,
            "health_interval": int(interval) if interval.isdigit() else 0}
    if password:
        body["password"] = password
    return body
