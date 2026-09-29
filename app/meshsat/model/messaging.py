# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Messaging (ui/screens/SettingsScreen.kt, the Encryption, Message compression and
Quick messages cards; codec/CannedCodebook.kt). MeshSat Android keeps these in its own settings
and applies them when it sends; here the Bridge sends, so each setting is a step in a link's
transform chain (PUT /api/interfaces/{id}/transforms, MESHSAT-1412):

- Encryption, as on Android, is the SMS link's: its send chain encrypts with the key, and
  "Auto-decrypt incoming SMS" puts an optional decrypt in its receive chain (a text from an
  ordinary phone is kept as it came, not dropped).
- Compression is per link: SMS and Iridium SBD; the Hub link has no chain here.
- A chain is written in send order and read in reverse on receive. Steps this page does not
  manage (fec, smaz2, zstd, llamazip) stay where they are.

Pure."""
import json
import re
import secrets

SMS = "cellular_0"
SBD = "iridium_0"
MANAGED = ("encrypt", "decrypt", "msvqsc", "base64")
KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")

# ── Encryption ───────────────────────────────────────────────────────────────────────────────
KEY_LABEL = "AES-256-GCM Key (hex)"
SCAN_KEY = "Scan QR Code (Hub Key Sync)"
SCAN_PROMPT = "Scan Hub encryption key QR code"
KEY_FROM_QR = "Key imported via QR"


def scanner_missing(reason) -> str:
    return f"QR scanner not available: {reason}"


FALLBACK_NOTE = ("Fallback key — used when no per-conversation key is set. "
                 "To sync with Hub: go to Hub dashboard > Devices > select device > Generate Key, "
                 "then scan the QR code or paste the 64-char hex key.")
KEY_GENERATED = "Key generated"
KEY_SAVED = "Key saved"
KEY_COPIED = "Key copied to clipboard"
KEY_PASTED = "Key imported from clipboard"
NOT_A_KEY = "Clipboard doesn't contain a valid 64-char hex key"
# Linux only: Android saves whatever is typed; the Bridge refuses a key that cannot encrypt.
BAD_KEY = "A key is 64 hexadecimal characters (0-9, a-f)."
NO_SMS_LINK = "This phone has no SMS link yet, so there is nothing to encrypt."


def valid_key(key: str) -> bool:
    return bool(KEY_RE.match(key or ""))


def generate_key() -> str:
    """AesGcmCrypto.generateKey: 32 random bytes as 64 lower-case hex characters."""
    return secrets.token_hex(32)


def steps(chain) -> list:
    """A chain as the Bridge keeps it (a JSON string of [{"type", "params"}]) as a list; an
    unreadable chain is empty."""
    if isinstance(chain, list):
        return [dict(s) for s in chain if isinstance(s, dict)]
    try:
        parsed = json.loads(chain or "[]")
    except (TypeError, ValueError):
        return []
    return [dict(s) for s in parsed if isinstance(s, dict)] if isinstance(parsed, list) else []


def chain_text(chain: list) -> str:
    return json.dumps(chain, separators=(",", ":"))


def step(chain: list, kind: str):
    return next((s for s in chain if s.get("type") == kind), None)


def inline_key(chain: list) -> str:
    """The inline key of the chain's encrypt or decrypt step ("" when it has none, or names a
    key_ref: a key kept by the Bridge's keystore, which this page does not show)."""
    for s in chain:
        if s.get("type") in ("encrypt", "decrypt"):
            return str((s.get("params") or {}).get("key") or "")
    return ""


def encrypts(chain: list) -> bool:
    return any(s.get("type") == "encrypt" for s in chain)


def decrypts(chain: list) -> bool:
    return any(s.get("type") in ("encrypt", "decrypt") for s in chain)


def compression(chain: list) -> str:
    """"msvqsc" or "off", as Android's per-link mode."""
    return "msvqsc" if step(chain, "msvqsc") else "off"


def stages(chain: list, default: str = "3") -> str:
    s = step(chain, "msvqsc")
    value = str(((s or {}).get("params") or {}).get("stages") or "")
    return value if value in STAGES else default


def build(chain: list, key: str | None, msvqsc_stages: str | None, text_link: bool, decrypt: bool = False) -> list:
    """A chain with this page's steps set and every other step kept: the steps it does not
    manage first (fec after the encryption), then MSVQ-SC, then the encryption, then base64
    when the link carries text and anything before it is binary. `decrypt` writes the receive
    side's optional decrypt instead of an encrypt."""
    others = [s for s in chain if s.get("type") not in MANAGED]
    before = [s for s in others if s.get("type") != "fec"]
    after = [s for s in others if s.get("type") == "fec"]
    out = list(before)
    if msvqsc_stages:
        out.append({"type": "msvqsc", "params": {"stages": str(msvqsc_stages)}})
    if key:
        if decrypt:
            out.append({"type": "decrypt", "params": {"key": key, "optional": "true"}})
        else:
            out.append({"type": "encrypt", "params": {"key": key}})
    out.extend(after)
    if out and text_link:
        out.append({"type": "base64"})
    return out


def sms_chains(egress: list, ingress: list, enabled: bool, auto_decrypt: bool, key: str, compress: str, msvqsc_stages: str) -> tuple:
    """The SMS link's two chains for the page's settings."""
    use_key = key if valid_key(key) else ""
    out = build(egress, use_key if enabled else None, msvqsc_stages if compress == "msvqsc" else None, text_link=True)
    back = build(ingress, use_key if auto_decrypt else None, None, text_link=True, decrypt=True)
    return out, back


def link_chain(egress: list, compress: str, msvqsc_stages: str, text_link: bool) -> list:
    """A link's send chain with its compression set (the satellite link: bytes, no base64)."""
    return build(egress, inline_key(egress) if encrypts(egress) else None, msvqsc_stages if compress == "msvqsc" else None, text_link)


# ── Message compression ──────────────────────────────────────────────────────────────────────
COMPRESSION_NOTE = ("Only for links where the other end is MeshSat too: anyone else sees a line of "
                    "letters. MSVQ-SC keeps the meaning, not the exact words. Mesh messages always go "
                    "out as typed, because a mesh channel is shared with other radios. ")
MODES = (("off", "Off"), ("msvqsc", "MSVQ-SC"))
STAGES = ("2", "3", "4", "6", "8")
STAGE_LABELS = {"2": "2 (5B)", "3": "3 (7B)", "4": "4 (9B)", "6": "6 (13B)", "8": "8 (17B)"}
STAGES_HINT = "MSVQ-SC stages (fewer = smaller, lower fidelity)"
# Linux only: the Bridge compresses with MSVQ-SC only when its encoder runs beside it.
NO_ENCODER = "MSVQ-SC needs its encoder beside the Bridge, and this phone has none, so messages go out as typed."
# (link id, Android's row label, whether the link carries text)
LINKS = ((SMS, "SMS", True), (SBD, "Iridium SBD", False))


# ── Quick messages ───────────────────────────────────────────────────────────────────────────
CODEBOOK = {
    1: "Copy.", 2: "Roger.", 3: "Negative.", 4: "Affirmative.", 5: "Stand by.", 6: "All clear.", 7: "Moving out.", 8: "Returning to base.",
    9: "Position confirmed.", 10: "Mission complete.", 11: "Need resupply.", 12: "Requesting backup.", 13: "Medical emergency.", 14: "Evacuate immediately.",
    15: "Hold position.", 16: "Proceed to waypoint.", 17: "Enemy contact.", 18: "All personnel accounted for.", 19: "Weather deteriorating.",
    20: "Low battery warning.", 21: "Signal lost.", 22: "Relay message.", 23: "Check in.", 24: "Going silent.", 25: "SOS — need immediate help.",
    26: "Camp established.", 27: "Trail blocked — rerouting.", 28: "Water source found.", 29: "Shelter located.", 30: "Search area clear — no findings.",
}
HEADER_CANNED = 0xCA
WIRE_NOTE = "Wire format: 2 bytes (0xCA + message ID). Auto-detected on receive."


def loaded_line() -> str:
    return f"{len(CODEBOOK)} brevity codes loaded"


def shown_codes() -> list:
    """The first 10, as Android's card: (text, "#id")."""
    return [(CODEBOOK[i], f"#{i}") for i in sorted(CODEBOOK)[:10]]


def more_line() -> str:
    return f"... and {len(CODEBOOK) - 10} more" if len(CODEBOOK) > 10 else ""


def encode_canned(code: int) -> bytes:
    return bytes([HEADER_CANNED, code])


def decode_canned(data: bytes) -> str:
    if len(data) != 2 or data[0] != HEADER_CANNED or data[1] not in CODEBOOK:
        raise ValueError("codec: unknown canned message")
    return CODEBOOK[data[1]]


# ── SMS: where a text goes with no recipient ─────────────────────────────────────────────────
NO_RECIPIENT_TITLE = "Where a text goes with no recipient"
NUMBER_LABEL = "Optional number, e.g. +31612345678"
NO_RECIPIENT_NOTE = ("Only used when a message has no recipient of its own: a routing rule that "
                     "forwards to SMS without naming a number. Messages you write carry their own "
                     "recipient, and SOS texts go to your emergency contacts under Safety. Leave it "
                     "empty and a text with no recipient is not sent.")
SAVED = "Saved"
NUMBER_RE = re.compile(r"^\+?[0-9 ()-]{3,20}$")
BAD_NUMBER = "Enter a phone number, e.g. +31612345678."  # Linux only: the Bridge dials what it is given


def default_number(config: dict) -> str:
    numbers = (config or {}).get("destination_numbers") or []
    return str(numbers[0]) if numbers else ""


def number_ok(value: str) -> bool:
    value = (value or "").strip()
    return value == "" or bool(NUMBER_RE.match(value))


def cellular_body(gateway: dict | None, number: str) -> dict:
    """PUT /api/gateways/cellular: the gateway's config as the Bridge gave it (its secrets
    masked, which the Bridge keeps, MESHSAT-1412) with the one default number, or none; its
    switch as it is, since a PUT without it switches the gateway off."""
    gateway = gateway or {}
    config = dict(gateway.get("config") or {})
    number = (number or "").strip().replace(" ", "")
    config["destination_numbers"] = [number] if number else []
    return {"enabled": bool(gateway.get("enabled")), "config": config}
