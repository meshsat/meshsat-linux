# SPDX-License-Identifier: GPL-3.0-or-later
"""A chat's own encryption key, in MeshSat Android's words and rules (ui/screens/MessagesScreen.kt:
465-548, 854-969). The key lives in the Bridge's keystore (PUT/GET/DELETE /api/keys/{type}/
{address}, Bridge change B21): an SMS chat's key seals every SMS to that number and opens every SMS
from it, as Android's does; a mesh or satellite chat keeps a key that changes nothing on the air,
as on Android. Pure: no GTK, tested on the runner."""
import secrets
import urllib.parse

TITLE = "Conversation Encryption Key"
NOTE = "AES-256-GCM key for this conversation. Messages are encrypted/decrypted with this key."
FIELD = "Hex key (64 chars)"
LOCK = "Encryption key"
SHOW, HIDE, GENERATE, SAVE, COPY, PASTE, REMOVE = "Show", "Hide", "Generate", "Save", "Copy", "Paste", "Remove"
SAVED = "Key saved"
INVALID = "Invalid key — 64 hex chars required"
COPIED = "Key copied"
PASTED = "Key pasted"
NOT_A_KEY = "Clipboard doesn't contain a valid 64-char hex key"
REMOVED = "Key removed — messages will show encrypted"
HEX = set("0123456789abcdefABCDEF")


def valid(key: str) -> bool:
    """Exactly 64 of 0-9, a-f, A-F: not trimmed, as Android checks both a typed and a pasted key."""
    return len(key) == 64 and all(c in HEX for c in key)


def generate() -> str:
    """AesGcmCrypto.generateKey(): 32 random bytes as 64 lower-case hex characters."""
    return secrets.token_hex(32)


def address(chat: str) -> tuple:
    """(type, address) in the Bridge's keystore for a chat: "sms:<number>" is an SMS chat, the
    satellite chat is the iridium channel's, anything else a mesh node (or everyone)."""
    if chat.startswith("sms:"):
        return "sms", chat[4:]
    if chat == "satellite":
        return "iridium", "satellite"
    return "mesh", chat


def path(chat: str) -> str:
    """/api/keys/{type}/{address}, the address escaped ("+" stays a plus, "*" and "!" as they are)."""
    kind, where = address(chat)
    return f"/api/keys/{kind}/{urllib.parse.quote(where, safe='*!')}"


def lock_on(chat_key: str | None, global_key: str | None) -> bool:
    """The header's lock is closed and amber when the chat has its key, or when Messaging has a
    key (even with encryption off), as Android's activeKey."""
    return bool(chat_key) or bool((global_key or "").strip())
