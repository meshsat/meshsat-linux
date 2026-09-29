# SPDX-License-Identifier: GPL-3.0-or-later
"""People cards (ui/screens/ContactCards.kt, pair/ContactQR.kt): the card two people swap face
to face by QR code, `meshsat:contact:1:<base64url payload>.<base64url signature>`, the payload
being name, Ed25519 key, mesh node id, bridge id and issued-at joined by U+001F and the
signature over exactly those bytes. This phone's own card is signed by the Bridge's routing
identity (GET /api/contacts/card, MESHSAT-1416); the cards of others are checked here and kept
in the app's own store, as Android keeps them on the phone. Pure but for `cryptography`."""
import base64
import binascii
import hashlib
import re
import time

PREFIX = "meshsat:contact:1:"
SEP = "\x1f"
MAX_NAME = 48
DEFAULT_NAME = "MeshSat phone"
SCANNED, IMPORTED = "SCANNED", "IMPORTED"

# ── Words ────────────────────────────────────────────────────────────────────────────────────
TITLE = "People you carry"
DESCRIPTION = "Cards swapped face to face by QR code. Read the fingerprint aloud to each other: it is what says the card is theirs."
MY_CARD = "My card"
SCAN = "Scan a card"
PASTE = "Paste a card instead"
NO_CARDS = "No cards yet."
ALTERED = "That card has been altered since it was made. Not saved."
DAMAGED = "That is a MeshSat card, but a damaged one."
NOT_A_CARD = "That is not a MeshSat contact card."
SCAN_PROMPT = "Scan the other phone's card"
PASTE_TITLE = "Paste a card"
PASTE_TEXT = "A card that did not come through the camera is kept as imported: the signature still holds, but nothing says who passed it on."
PASTE_LABEL = "meshsat:contact:1:..."
READ_IT = "Read it"
CANCEL = "Cancel"
ADD_CHECK = "Check this fingerprint against the one on their screen. If it differs, the card is not theirs."
ADD_SCANNED = "Scanned from a screen in front of you."
ADD_IMPORTED = "Imported as text."
ADD = "Add"
FORGET = "Forget"
NO_KEY = "The gateway has not started yet, so this phone has no key to sign a card with."
READ_ALOUD = "Read this out to whoever scans it."
DONE = "Done"
COPY = "Copy"
COPIED = "Card copied"
QR_NAME = "This phone's contact card as a QR code"


def add_title(name: str) -> str:
    return f"Add {name}?"


def mesh_line(node_id: str) -> str:
    return f"Mesh node {node_id}"


def hub_line(bridge_id: str) -> str:
    return f"Hub {bridge_id}"


def no_scanner(reason) -> str:
    return f"No camera scanner: {reason}"


def row_line(card: dict) -> str:
    """"Scanned in person · mesh !bf6ee7bc · msa-flaneur" (ContactCards.kt:137-145)."""
    out = "Scanned in person" if card.get("trust") == SCANNED else "Imported as text"
    if (card.get("mesh_node_id") or "").strip():
        out += f" · mesh {card['mesh_node_id']}"
    if (card.get("bridge_id") or "").strip():
        out += f" · {card['bridge_id']}"
    return out


# ── The format ───────────────────────────────────────────────────────────────────────────────
_B64URL = re.compile(r"[A-Za-z0-9_-]*={0,2}")
_LONG = re.compile(r"[+-]?[0-9]+")


def unb64(text: str):
    """java.util.Base64.getUrlDecoder(): the URL alphabet only, padding optional but exact."""
    if not _B64URL.fullmatch(text):
        return None
    body = text.rstrip("=")
    pad = len(text) - len(body)
    if len(body) % 4 == 1 or (pad and (len(body) + pad) % 4):
        return None
    try:
        return base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
    except binascii.Error:
        return None


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def fingerprint(pub: bytes) -> str:
    """The first 8 bytes of SHA-256 over the raw key, four groups of four hex digits."""
    h = hashlib.sha256(pub).hexdigest()[:16]
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))


def encode(name: str, pub: bytes, mesh_node_id: str, bridge_id: str, issued_at: int, sign) -> str:
    """ContactQR.encode; `sign(payload) -> 64 bytes`. Raises ValueError with Android's words."""
    if not name.strip():
        raise ValueError("a card needs a name")
    if utf16_len(name) > MAX_NAME:
        raise ValueError(f"name over {MAX_NAME} characters")
    if any(SEP in field for field in (name, mesh_node_id, bridge_id)):
        raise ValueError("a field may not contain the separator")
    payload = SEP.join((name, b64(pub), mesh_node_id, bridge_id, str(int(issued_at)))).encode("utf-8")
    return PREFIX + b64(payload) + "." + b64(sign(payload))


def decode(text: str) -> tuple:
    """ContactQR.decode, in its order: ("Ok", card), ("BadSignature", None), ("Malformed", None) or
    ("NotACard", None). A card is {name, signing_pub (32 bytes), mesh_node_id, bridge_id,
    issued_at}."""
    t = (text or "").strip()
    if not t.startswith(PREFIX):
        return "NotACard", None
    body = t[len(PREFIX):]
    dot = body.find(".")
    if dot <= 0 or dot == len(body) - 1:
        return "Malformed", None
    payload, sig = unb64(body[:dot]), unb64(body[dot + 1:])
    if payload is None or sig is None:
        return "Malformed", None
    fields = payload.decode("utf-8", errors="replace").split(SEP)
    if len(fields) != 5:
        return "Malformed", None
    pub = unb64(fields[1])
    if pub is None or len(pub) != 32 or not _LONG.fullmatch(fields[4]) or not -2 ** 63 <= int(fields[4]) < 2 ** 63:
        return "Malformed", None
    if not fields[0].strip():
        return "Malformed", None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: PLC0415

        Ed25519PublicKey.from_public_bytes(pub).verify(sig, payload)
    except Exception:  # noqa: BLE001 - any failure to verify is a card that does not hold
        return "BadSignature", None
    return "Ok", {"name": fields[0], "signing_pub": pub, "mesh_node_id": fields[2], "bridge_id": fields[3], "issued_at": int(fields[4])}


def verdict(result: str):
    """The toast for a card that cannot be added, or None for one that can."""
    return {"BadSignature": ALTERED, "Malformed": DAMAGED, "NotACard": NOT_A_CARD}.get(result)


# ── The list (the Room table `contacts`, kept in cards.json) ─────────────────────────────────
def record(card: dict, trust: str, now_ms: int | None = None) -> dict:
    """The eight columns Android writes (ContactCards.kt:221-230)."""
    return {"fingerprint": fingerprint(card["signing_pub"]), "name": card["name"], "signing_pub": base64.b64encode(card["signing_pub"]).decode(),
            "mesh_node_id": card["mesh_node_id"], "bridge_id": card["bridge_id"], "trust": trust, "issued_at": int(card["issued_at"]),
            "added_at": int(now_ms if now_ms is not None else time.time() * 1000)}


def upsert(cards: list, row: dict) -> list:
    """INSERT OR REPLACE by fingerprint: a new card from the same key replaces the row, trust
    included."""
    out = [c for c in cards if c.get("fingerprint") != row["fingerprint"]]
    out.append(row)
    return out


def forget(cards: list, fp: str) -> list:
    return [c for c in cards if c.get("fingerprint") != fp]


def ascii_fold(text: str) -> str:
    """SQLite's NOCASE: A-Z folded to a-z, nothing else."""
    return "".join(chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in text)


def ordered(cards: list) -> list:
    """By name COLLATE NOCASE; ties keep the order they were added in."""
    return sorted(cards, key=lambda c: ascii_fold(c.get("name", "")))
