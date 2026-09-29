# SPDX-License-Identifier: GPL-3.0-or-later
"""Key bundles from the Setup scanner (crypto/KeyBundleImporter.kt, SettingsScreen.kt:222-259,
295-333): `meshsat://key/<base64url bundle>`, a kit's keys signed by its routing identity. The
app checks what Android checks before anything is stored: the format, the version, the
signature of a v2 bundle, and the key each kit signed with the first time (trust on first use,
Android's `bridge_trust` table, kept here in bridge_trust.json). The Bridge then stores the keys
(POST /api/keys/import), and its count is the one the toast gives. Pure but for `cryptography`.

Wire: version (1), kit hash (16), timestamp (4, big-endian), entry count (1); v1: signature
(64); v2: the signer's Ed25519 key (32) and the signature (64); then the entries: channel type
(1), address length (1), address, AES-256 key (32). Signed: every byte but the signature."""
import base64
import re
import struct
import time

PREFIX = "meshsat://key/"
HEADER = 22
V1_MIN = HEADER + 64
V2_MIN = HEADER + 32 + 64
NEW_TRUSTED, EXISTING_TRUSTED, UNVERIFIED_V1 = "NEW_TRUSTED", "EXISTING_TRUSTED", "UNVERIFIED_V1"

# ── Words ────────────────────────────────────────────────────────────────────────────────────
CHANGED_TITLE = "This kit's key has changed"
TRUST_NEW = "Trust the new key"
KEEP_OLD = "Keep the old key"
HEX_IMPORTED = "Key imported via QR"
NOT_A_KEY = "QR code doesn't contain a valid key or bundle"


def changed_text(kit: str) -> str:
    return (f"Kit {kit[:8]} signed these keys with a different key from the one this phone saved the first time. That is expected after the kit "
            "was reinstalled or its key was renewed. It is also what an impostor looks like. Trust the new key only if you know the kit's key changed.")


def imported(count: int, trust: str, kit: str) -> str:
    if trust == NEW_TRUSTED:
        return f"Imported {count} key(s) — new bridge {kit[:8]} pinned"
    if trust == EXISTING_TRUSTED:
        return f"Imported {count} key(s) — signature verified against pinned bridge"
    return f"Imported {count} key(s) — UNVERIFIED (legacy v1 bundle, no signature check)"


def invalid(reason: str) -> str:
    return f"⚠ Bundle signature INVALID — possibly tampered. {reason}"


def malformed(reason: str) -> str:
    return f"Bundle malformed: {reason}"


def repinned(count: int) -> str:
    return f"New kit key saved, {count} key(s) imported"


def not_imported(result: str) -> str:
    return f"Not imported: {result}"


# ── Decoding ─────────────────────────────────────────────────────────────────────────────────
_URL_ALPHABET = re.compile(r"[A-Za-z0-9_-]")


def unb64(text: str) -> bytes:
    """Java's URL decoder, padded or not, with its messages for what it refuses."""
    body = text.rstrip("=")
    for ch in body:
        if not _URL_ALPHABET.fullmatch(ch):
            raise ValueError(f"Illegal base64 character {ord(ch):x}")
    if len(body) % 4 == 1:
        raise ValueError("Last unit does not have enough valid bits")
    return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))


def parse(url: str) -> dict:
    """The bundle's parts, or ValueError("Malformed", reason) / ("InvalidSignature", reason)
    raised as (kind, reason) in the exception's args, in Android's order."""
    if not url.startswith(PREFIX):
        raise ValueError("Malformed", "Not a meshsat key URL")
    try:
        raw = unb64(url[len(PREFIX):])
    except ValueError as error:
        raise ValueError("Malformed", f"Base64 decode failed: {error}") from error
    if len(raw) < V1_MIN:
        raise ValueError("Malformed", f"Bundle too short: {len(raw)} bytes")
    version = raw[0]
    if version not in (1, 2):
        raise ValueError("Malformed", f"Unsupported bundle version: 0x{version:02x}")
    kit = raw[1:17].hex()
    timestamp = struct.unpack(">I", raw[17:21])[0]
    count = raw[21]
    if version == 1:
        return {"version": 1, "kit": kit, "timestamp": timestamp, "count": count, "signer": None, "entries_at": V1_MIN, "raw": raw}
    if len(raw) < V2_MIN:
        raise ValueError("Malformed", f"v2 bundle too short: {len(raw)} bytes (need {V2_MIN})")
    signer, signature = raw[22:54], raw[54:118]
    signed = raw[:22] + signer + raw[118:]
    from cryptography.exceptions import InvalidSignature  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: PLC0415

    try:
        Ed25519PublicKey.from_public_bytes(signer).verify(signature, signed)
    except InvalidSignature:
        raise ValueError("InvalidSignature", "Ed25519 signature does not match bundle contents") from None
    except Exception as error:  # noqa: BLE001 - any other failure: Android's "verification error"
        raise ValueError("InvalidSignature", f"Signature verification error: {error}") from error
    return {"version": 2, "kit": kit, "timestamp": timestamp, "count": count, "signer": signer, "entries_at": V2_MIN, "raw": raw}


def entries(bundle: dict) -> list:
    """(channel type, address, key) of each entry; ValueError("Malformed", "Entry parse failed:
    Truncated entry i[ data]") where one is cut short."""
    raw, at, out = bundle["raw"], bundle["entries_at"], []
    for i in range(bundle["count"]):
        if at + 2 > len(raw):
            raise ValueError("Malformed", f"Entry parse failed: Truncated entry {i}")
        kind, size = raw[at], raw[at + 1]
        if at + 2 + size + 32 > len(raw):
            raise ValueError("Malformed", f"Entry parse failed: Truncated entry {i} data")
        out.append((kind, raw[at + 2:at + 2 + size].decode("utf-8", errors="replace"), raw[at + 2 + size:at + 2 + size + 32]))
        at += 2 + size + 32
    return out


# ── Trust on first use (the `bridge_trust` table) ────────────────────────────────────────────
def check(url: str, pins: dict, force: bool = False, now_ms: int | None = None) -> tuple:
    """(result, detail, pins) as KeyBundleImporter.importFromURL decides before storing:
    ("Import", trust) with the bundle's parts and the pins to keep; ("KeyMismatch", {kit,
    stored, presented, first_seen}); ("Malformed", reason); ("InvalidSignature", reason). A pin
    made for a v2 bundle stays even when its entries turn out cut short, as on Android."""
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    pins = dict(pins)
    try:
        bundle = parse(url)
    except ValueError as error:
        return error.args[0], error.args[1], pins
    trust = UNVERIFIED_V1
    if bundle["version"] == 2:
        kit, signer = bundle["kit"], base64.b64encode(bundle["signer"]).decode()
        pin = pins.get(kit)
        if pin is None:
            pins[kit] = {"pubkey": signer, "first_seen": now_ms, "last_seen": now_ms, "label": f"Bridge {kit[:8]}", "count": 1}
            trust = NEW_TRUSTED
        elif pin.get("pubkey") == signer:
            pins[kit] = {**pin, "last_seen": now_ms, "count": int(pin.get("count", 0)) + 1}
            trust = EXISTING_TRUSTED
        elif force:
            pins[kit] = {**pin, "pubkey": signer, "last_seen": now_ms, "count": int(pin.get("count", 0)) + 1}
            trust = NEW_TRUSTED
        else:
            return "KeyMismatch", {"kit": kit, "stored": pin.get("pubkey"), "presented": signer, "first_seen": pin.get("first_seen")}, pins
    try:
        found = entries(bundle)
    except ValueError as error:
        return error.args[0], error.args[1], pins
    return "Import", {"trust": trust, "kit": bundle["kit"], "version": bundle["version"], "entries": len(found), "bundle": bundle}, pins


def is_hex_key(text: str) -> bool:
    """A 64-character AES key in hex, as the Setup scanner takes one (either case)."""
    return len(text) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in text)
