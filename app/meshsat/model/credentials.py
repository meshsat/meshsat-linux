# SPDX-License-Identifier: GPL-3.0-or-later
"""Certificates and keys (ui/screens/CredentialsScreen.kt): the Bridge's stored credentials
(/api/credentials) as cards, with Android's words. Pure."""
import time

IMPORT = "Import PEM"
EMPTY = ("No credentials stored", "Import PEM files or receive via Hub sync")
IMPORTED = "Certificate imported"
PROVIDER = "local"  # what Android stores an imported PEM under


def import_failed(why) -> str:
    return f"Import failed: {why}"


def fingerprint_text(hex_digest: str) -> str:
    """Android shows the first 8 bytes of the SHA-256, "AB:CD:EF:01:23:45:67:89"; the Bridge
    keeps the whole digest in hex."""
    digest = "".join(c for c in (hex_digest or "") if c in "0123456789abcdefABCDEF")
    return ":".join(digest[i:i + 2].upper() for i in range(0, min(len(digest), 16), 2))


def expiry_date(not_after: str) -> str:
    """The day the certificate expires, "yyyy-MM-dd", from what the Bridge stored."""
    text = (not_after or "").strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else text


def expiry_tone(not_after: str, now: float | None = None) -> str:
    """Red when expired, amber within 30 days, green after that; muted when unknown."""
    day = expiry_date(not_after)
    if not day:
        return "muted"
    try:
        expiry = time.mktime(time.strptime(day, "%Y-%m-%d"))
    except ValueError:
        return "muted"
    days_left = (expiry - (time.time() if now is None else now)) // 86400
    if days_left < 0:
        return "red"
    if days_left < 30:
        return "amber"
    return "green"


def badges(cred: dict) -> list:
    return [b for b in (cred.get("provider"), cred.get("cred_type"), cred.get("source")) if b]


def lines(cred: dict) -> list:
    """(text, kind): the card's lines under its name and badges."""
    out = []
    if cred.get("cert_fingerprint"):
        out.append((f"SHA-256: {fingerprint_text(cred['cert_fingerprint'])}", "mono"))
    if cred.get("cert_subject"):
        out.append((f"Subject: {cred['cert_subject']}", "plain"))
    if cred.get("cert_not_after"):
        out.append((f"Expires: {expiry_date(cred['cert_not_after'])}", "expiry"))
    out.append((f"v{cred.get('version', 1)}", "plain"))
    return out


def delete_dialog(cred: dict) -> dict:
    return {"title": "Delete Credential?", "body": f"Remove '{cred.get('name', '')}' ({cred.get('provider', '')})? This cannot be undone.", "ok": "Delete", "cancel": "Cancel"}


def multipart(fields: dict, file_field: str, filename: str, data: bytes, boundary: str) -> bytes:
    """A multipart/form-data body, as the Bridge's upload handler reads it."""
    parts = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode())
    safe = filename.replace('"', "")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{safe}\"\r\nContent-Type: application/x-pem-file\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)
