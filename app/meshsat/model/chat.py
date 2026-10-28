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
    if transport == "lxmf":
        return "Message by Reticulum"
    if transport == "mesh":
        return "Message everyone on the mesh" if everyone else "Message on the mesh"
    return "Text message"


def lane_of(message: dict) -> str:
    """A message's lane (its colour and its chat) from the transport the Bridge stored."""
    transport = message.get("transport")
    if transport in ("iridium", "iridium_imt", "sbd", "imt"):
        return "satellite"
    if transport in ("sms", "cellular"):
        return "sms"
    if transport in ("reticulum", "rns", "lxmf"):
        return "reticulum"
    return "mesh"


# ── Reticulum (LXMF) peers, as Android's Peers.kt (MESHSAT-1553) ────────────────────────────
LXMF_PREFIX = "lxmf:"  # the Bridge files an LXMF message's from and to as "lxmf:<hash>"
LXMF_ADDRESS_LABEL = "Or a Reticulum (LXMF) address, 32 hex characters"
MESSAGE_THIS_ADDRESS = "Message this address"


def is_lxmf(peer: str) -> bool:
    """An LXMF delivery address: 32 hex characters, what Sideband and CrossTalk show."""
    peer = peer or ""
    return len(peer) == 32 and all(c in "0123456789abcdefABCDEF" for c in peer)


def clean_lxmf_address(value: str) -> str:
    """An address as typed or pasted: trimmed, lower case, the angle brackets and spaces out."""
    out = (value or "").strip().lower()
    if out.startswith("<"):
        out = out[1:]
    if out.endswith(">"):
        out = out[:-1]
    return out.replace(" ", "")


def lxmf_hash(key: str) -> str:
    """The address in a chat key ("lxmf:<hash>")."""
    return key[len(LXMF_PREFIX):] if key.startswith(LXMF_PREFIX) else key


def lxmf_key(peer: str) -> str:
    return LXMF_PREFIX + peer


def lxmf_name(peer: str, peers: list) -> str:
    """What the user calls an LXMF peer (Peers.displayName): the name it announced, when the
    node has heard it, else "Reticulum" and the first eight characters of its address."""
    peer = lxmf_hash(peer)
    for p in peers or []:
        if str(p.get("dest_hash") or "").lower() == peer.lower() and (p.get("display_name") or "").strip():
            return str(p["display_name"]).strip()
    return f"Reticulum {peer[:8]}"


def lxmf_announced(peer: str, peers: list) -> str | None:
    """The display name an LXMF peer announced, when the node has heard it (Peers.lxmfName)."""
    name = lxmf_name(peer, peers)
    return None if name == f"Reticulum {lxmf_hash(peer)[:8]}" else name


def lxmf_detail(peer: str) -> str:
    """The line under the name (Peers.detail)."""
    return f"By Reticulum (LXMF), {lxmf_hash(peer)}"


def lxmf_known(peer: str, peers: list) -> bool:
    """Whether the node has a path to this address (it is in the Bridge's peer table)."""
    peer = lxmf_hash(peer).lower()
    return any(str(p.get("dest_hash") or "").lower() == peer for p in peers or [])


def lxmf_peer_row(peer: dict) -> tuple:
    """A peer's row in New message: (title, detail), as NewMessageDialog lists them."""
    dest = str(peer.get("dest_hash") or "")
    title = (peer.get("display_name") or "").strip() or f"Reticulum {dest[:8]}"
    from . import words  # noqa: PLC0415

    return title, f"By Reticulum, {dest[:16]}... {words.count(int(peer.get('hops') or 0), 'hop')} away"


def lxmf_hint(name: str | None, known: bool) -> str:
    """The line under the box of a Reticulum chat (composeHint's "lxmf" branch)."""
    if name and known:
        return f"By Reticulum to {name}. Direct waits for the far end, even by satellite."
    if known:
        return "By Reticulum. Direct waits for the far end, even by satellite."
    return "By Reticulum, once a path to this address is found."


def merge_lxmf(messages: list, window: int = 600) -> list:
    """The Bridge files its own row for an LXMF message it sent, when the worker sends it; this
    app's own record of the send (kept so the bubble shows at once) goes as soon as that row
    exists: the same address and the same text, the Bridge's row no earlier than a minute
    before and no later than `window` seconds after the app's."""
    stored = [m for m in messages if lane_of(m) == "reticulum" and m.get("direction") == "tx" and not m.get("local")]
    out = []
    for m in messages:
        if m.get("local") and lane_of(m) == "reticulum":
            at = m.get("rx_time") or 0
            if any(s.get("to_node") == m.get("to_node") and (s.get("decoded_text") or "") == (m.get("decoded_text") or "") and -60 <= (s.get("rx_time") or 0) - at <= window
                   for s in stored):
                continue
        out.append(m)
    return out


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


# New message (MessagesScreen.kt:1085-1172): a phone number is an SMS chat
NUMBER_LABEL = "Or a phone number, e.g. +31612345678"
TEXT_NUMBER = "Text this number"


def number_ok(value: str) -> bool:
    """At least 6 characters, only digits, "+" and spaces (NewMessageDialog's numberOk)."""
    n = (value or "").strip()
    return len(n) >= 6 and all(c.isdigit() or c in "+ " for c in n)


def number_of(value: str) -> str:
    """The number as the chat keeps it: trimmed, spaces out."""
    return (value or "").strip().replace(" ", "")
