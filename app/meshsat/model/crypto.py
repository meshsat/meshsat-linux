# SPDX-License-Identifier: GPL-3.0-or-later
"""AES-256-GCM as MeshSat Android (crypto/AesGcmCrypto.kt), the Bridge (engine/transform.go) and
the Hub write it: a 64-character hex key, a random 12-byte nonce, the wire being
nonce || ciphertext || 16-byte tag, base64 for a text. And where the app finds the key: the
Bridge's "encrypt" transform on its links (the key Setup > Messaging will save, 0.9.1)."""
import base64
import binascii
import json
import os

NONCE = 12
TAG = 16
NO_KEY = "No encryption key configured. Go to Settings to set one."
HELP = ("Paste a base64 ciphertext from an SMS to decrypt it, or type plaintext to encrypt it. Uses the AES-256-GCM key from Settings — must match the key on "
        "MeshSat Pi.")


class CryptoError(Exception):
    pass


def _key(hex_key: str) -> bytes:
    try:
        key = binascii.unhexlify((hex_key or "").strip())
    except (binascii.Error, ValueError) as error:
        raise CryptoError("the key is not hex") from error
    if len(key) != 32:
        raise CryptoError(f"the key must be 32 bytes (got {len(key)})")
    return key


def _aead(hex_key: str):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415
    except ImportError as error:  # python3-cryptography is a dependency of the package
        raise CryptoError("python3-cryptography is not installed") from error
    return AESGCM(_key(hex_key))


def encrypt(plaintext: bytes, hex_key: str, nonce: bytes | None = None) -> bytes:
    nonce = os.urandom(NONCE) if nonce is None else nonce
    return nonce + _aead(hex_key).encrypt(nonce, plaintext, None)


def decrypt(wire: bytes, hex_key: str) -> bytes:
    if len(wire) <= NONCE:
        raise CryptoError("Data too short for AES-GCM")
    try:
        return _aead(hex_key).decrypt(wire[:NONCE], wire[NONCE:], None)
    except CryptoError:
        raise
    except Exception as error:  # cryptography's InvalidTag: the wrong key or a changed text
        raise CryptoError("the text does not open with this key") from error


def encrypt_to_base64(text: str, hex_key: str) -> str:
    return base64.b64encode(encrypt(text.encode("utf-8"), hex_key)).decode("ascii")


def decrypt_from_base64(text: str, hex_key: str) -> str:
    try:
        wire = base64.b64decode("".join(text.split()), validate=True)
    except (binascii.Error, ValueError) as error:
        raise CryptoError("not base64") from error
    try:
        return decrypt(wire, hex_key).decode("utf-8")
    except UnicodeDecodeError as error:
        raise CryptoError("the text is not UTF-8") from error


def key_from_links(interfaces: list) -> str:
    """The 64-hex key of the first "encrypt" transform on the Bridge's links (egress first,
    then ingress), or "" when there is none or it is kept by reference."""
    for field in ("egress_transforms", "ingress_transforms"):
        for iface in interfaces:
            raw = iface.get(field) or "[]"
            try:
                chain = json.loads(raw) if isinstance(raw, str) else raw
            except ValueError:
                continue
            for step in chain or []:
                if isinstance(step, dict) and step.get("type") in ("encrypt", "decrypt"):
                    key = str((step.get("params") or {}).get("key") or "").strip()
                    if len(key) == 64 and all(c in "0123456789abcdefABCDEF" for c in key):
                        return key
    return ""
