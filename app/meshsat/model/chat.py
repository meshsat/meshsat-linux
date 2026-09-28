# SPDX-License-Identifier: GPL-3.0-or-later
"""The chat's words (ui/screens/MessagesScreen.kt, engine/SatelliteLimits.kt): the composer's
placeholder and the line under it, the size limit of a satellite message, the delivery mark on
a message the phone sent, and the search over the messages. Pure."""

MAX_MO_BYTES = 340  # one satellite message is one SBD frame, and nothing longer is sent (MESHSAT-1280)
NODE_NOT_CONNECTED = "Not sent: your MeshSat node is not connected. Connect it in Setup."
SEARCH_PLACEHOLDER = "Search messages..."


def placeholder(transport: str, everyone: bool) -> str:
    if transport == "iridium":
        return "Message by satellite"
    if transport == "mesh":
        return "Message everyone on the mesh" if everyone else "Message on the mesh"
    return "Text message"


def byte_size(text: str) -> int:
    return len((text or "").strip().encode("utf-8"))


def fits(size: int) -> bool:
    return size <= MAX_MO_BYTES


def too_long(size: int) -> str:
    """What to tell a person whose message is too long, in the words of the compose bar."""
    return f"Too long for a satellite message: {size} bytes, {MAX_MO_BYTES} at most. Shorten it or send it in two."


def compose_hint(transport: str, text: str, everyone: bool, mesh_up: bool, sat_up: bool) -> str:
    """The line under the message box: how this message goes, and for a satellite message its
    size and cost before it is sent (Rock7 bills up to 50 bytes per credit)."""
    size = byte_size(text)
    if transport == "iridium":
        if not fits(size):
            return too_long(size)
        credits = (size + 49) // 50
        tail = "" if size == 0 else f" {size} bytes, {credits} {'credit' if credits == 1 else 'credits'}."
        return ("By satellite." if sat_up else "By satellite, when the modem is back.") + tail
    if transport == "mesh":
        if not mesh_up:
            return "On the mesh, when your node is connected."
        return "To everyone on the mesh channel." if everyone else "Directly to this node on the mesh."
    chars = len((text or "").strip())
    return "By SMS from this phone." if chars == 0 else f"By SMS from this phone, {chars} characters."


def can_send(transport: str, text: str) -> bool:
    return bool((text or "").strip()) and (transport != "iridium" or fits(byte_size(text)))


def mark(delivery_status: str) -> tuple:
    """The delivery mark on a message the phone sent, as chat apps show it: (icon, tone, label).
    A clock while it waits, one check once it has left the phone, a red mark when it failed, a
    question mark when the link dropped after the upload, and two checks only on a confirmation
    from the far end (the Hub's receipt, the carrier's delivery report). A mesh message never
    gets a second check."""
    low = (delivery_status or "").lower()
    if low in ("queued", "pending", "sending", "retry", "held"):
        return "outlined-schedule", "muted", "Queued"
    if low in ("unconfirmed", "may_have_been_sent"):
        return "outlined-help-outline", "amber", "May have been sent"
    if low in ("failed", "dead", "expired", "denied", "error"):
        return "outlined-error-outline", "red", "Failed"
    if low in ("delivered", "acked", "hub"):
        return "outlined-done-all", "teal", "Delivered"
    return "outlined-done", "teal", "Sent"


def delivery_label(delivery_status: str) -> str:
    """The badge on a forwarded message in All Messages."""
    low = (delivery_status or "").lower()
    return {"queued": "Queued", "pending": "Queued", "unconfirmed": "May have been sent", "sent": "Sent", "delivered": "The Hub has it", "acked": "Delivered",
            "sending": "Sending", "failed": "Failed", "dead": "Failed"}.get(low, "Forwarded")


def search(messages: list, query: str) -> list:
    """The messages whose text holds the query, whatever the case; all of them for no query."""
    q = (query or "").strip().lower()
    if not q:
        return list(messages)
    return [m for m in messages if q in (m.get("decoded_text") or "").lower()]
