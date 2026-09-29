# SPDX-License-Identifier: GPL-3.0-or-later
"""Key bundles from the Setup scanner (0.11.0) against MeshSat Android v2.19.4: KeyBundleImporterTest
ported case for case (the builder mirrors the Bridge's MarshalBundleV2, as Android's does), the
fixed v2 vector signed with the seed 00..1f, and the Setup router's 64-hex key."""
import base64
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from meshsat.model import keybundle as kb  # noqa: E402

VECTOR = ("meshsat://key/AhERERERERERERERERERERFqr7TgAQOhB7_zzhC-HXDdGOdLwJln5NYwm6UNXx3chmQSVTG4U4PzAaj8Us_uyyvdJbUUwhRDp2WDH5nAjAoWf2neGKiVws9ztfVnwTLREd9rdQ0-"
          "alcK620z2n8sEs8vHw9_CQAMKzMxNjEyMzQ1Njc4IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiI")


def keypair(seed: bytes):
    private = Ed25519PrivateKey.from_private_bytes(seed)
    return private, private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def build(version: int, private, pub: bytes, kit: bytes = bytes([0x11]) * 16, stamp: int = 1789900000, entries=None) -> bytes:
    """The Bridge's marshal: header (22) [+ key (32)] + signature (64) + entries."""
    entries = entries if entries is not None else [(0x00, "+31612345678", bytes([0x22]) * 32), (0x01, "!abc12345", bytes([0x33]) * 32)]
    body = b"".join(bytes([kind, len(addr.encode())]) + addr.encode() + key for kind, addr, key in entries)
    header = bytes([version]) + kit + struct.pack(">I", stamp) + bytes([len(entries)])
    if version == 1:
        return header + private.sign(header + body) + body
    return header + pub + private.sign(header + pub + body) + body


def url(raw: bytes) -> str:
    return kb.PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


class KeyBundleImporterTest(unittest.TestCase):
    """app/src/test/java/net/meshsat/android/KeyBundleImporterTest.kt"""

    def setUp(self):
        self.private, self.pub = keypair(bytes(range(32)))
        self.private2, self.pub2 = keypair(bytes([7]) * 32)

    def test_v2_valid_bundle_first_import_pins_key(self):
        result, detail, pins = kb.check(url(build(2, self.private, self.pub)), {}, now_ms=1)
        self.assertEqual((result, detail["trust"], detail["entries"]), ("Import", kb.NEW_TRUSTED, 2))
        self.assertEqual(list(pins), ["11" * 16])
        self.assertEqual(pins["11" * 16]["pubkey"], base64.b64encode(self.pub).decode())
        self.assertEqual(pins["11" * 16]["label"], "Bridge 11111111")

    def test_v2_valid_bundle_second_import_verifies_against_pin(self):
        link = url(build(2, self.private, self.pub))
        _r, _d, pins = kb.check(link, {}, now_ms=1)
        result, detail, pins = kb.check(link, pins, now_ms=2)
        self.assertEqual((result, detail["trust"]), ("Import", kb.EXISTING_TRUSTED))
        self.assertEqual(pins["11" * 16]["count"], 2)

    def test_v2_forged_signature_rejected(self):
        raw = bytearray(build(2, self.private, self.pub))
        raw[55] ^= 0xFF
        result, reason, pins = kb.check(url(bytes(raw)), {})
        self.assertEqual((result, reason), ("InvalidSignature", "Ed25519 signature does not match bundle contents"))
        self.assertEqual(pins, {})

    def test_v2_tampered_entry_data_rejected(self):
        raw = bytearray(build(2, self.private, self.pub))
        raw[-1] ^= 0xFF
        self.assertEqual(kb.check(url(bytes(raw)), {})[0], "InvalidSignature")

    def test_v2_swapped_pubkey_signature_fails(self):
        raw = bytearray(build(2, self.private, self.pub))
        raw[22:54] = self.pub2
        self.assertEqual(kb.check(url(bytes(raw)), {})[0], "InvalidSignature")

    def test_v2_pubkey_rotation_without_force_key_mismatch(self):
        _r, _d, pins = kb.check(url(build(2, self.private, self.pub)), {}, now_ms=1)
        result, detail, _pins = kb.check(url(build(2, self.private2, self.pub2)), pins, now_ms=2)
        self.assertEqual(result, "KeyMismatch")
        self.assertEqual((detail["stored"], detail["presented"]), (base64.b64encode(self.pub).decode(), base64.b64encode(self.pub2).decode()))
        self.assertEqual(detail["kit"], "11" * 16)

    def test_v2_pubkey_rotation_with_force_re_pins(self):
        _r, _d, pins = kb.check(url(build(2, self.private, self.pub)), {}, now_ms=1)
        result, detail, pins = kb.check(url(build(2, self.private2, self.pub2)), pins, force=True, now_ms=2)
        self.assertEqual((result, detail["trust"]), ("Import", kb.NEW_TRUSTED))
        self.assertEqual(pins["11" * 16]["pubkey"], base64.b64encode(self.pub2).decode())

    def test_v1_bundle_imported_as_unverified(self):
        result, detail, pins = kb.check(url(build(1, self.private, self.pub)), {})
        self.assertEqual((result, detail["trust"]), ("Import", kb.UNVERIFIED_V1))
        self.assertEqual(pins, {})

    def test_malformed_url_rejected(self):
        self.assertEqual(kb.check("https://example.com", {})[:2], ("Malformed", "Not a meshsat key URL"))

    def test_truncated_bundle_rejected(self):
        self.assertEqual(kb.check(url(bytes(10)), {})[:2], ("Malformed", "Bundle too short: 10 bytes"))

    def test_unsupported_version_rejected(self):
        raw = bytearray(120)
        raw[0] = 0x03
        self.assertEqual(kb.check(url(bytes(raw)), {})[:2], ("Malformed", "Unsupported bundle version: 0x03"))


class VectorAndWordsTest(unittest.TestCase):
    def test_the_fixed_v2_vector(self):
        private, pub = keypair(bytes(range(32)))
        raw = build(2, private, pub, entries=[(0x00, "+31612345678", bytes([0x22]) * 32)])
        self.assertEqual(len(raw), 164)
        self.assertEqual(url(raw), VECTOR)
        result, detail, _pins = kb.check(VECTOR, {})
        self.assertEqual((result, detail["trust"], detail["kit"][:8]), ("Import", kb.NEW_TRUSTED, "11111111"))
        self.assertEqual(kb.imported(1, kb.NEW_TRUSTED, detail["kit"]), "Imported 1 key(s) — new bridge 11111111 pinned")

    def test_truncated_entries_keep_the_pin(self):
        private, pub = keypair(bytes(range(32)))
        raw = bytearray(build(2, private, pub))
        raw[21] = 3  # three entries announced, two there; re-signed so only the entries are wrong
        header, body = bytes(raw[:22]), bytes(raw[118:])
        raw = header + pub + private.sign(header + pub + body) + body
        result, reason, pins = kb.check(url(raw), {})
        self.assertEqual((result, reason), ("Malformed", "Entry parse failed: Truncated entry 2"))
        self.assertEqual(list(pins), ["11" * 16])

    def test_base64_messages_are_javas(self):
        self.assertEqual(kb.check(kb.PREFIX + "AAAA.AAA", {})[:2], ("Malformed", "Base64 decode failed: Illegal base64 character 2e"))

    def test_words(self):
        self.assertEqual(kb.imported(2, kb.EXISTING_TRUSTED, "x"), "Imported 2 key(s) — signature verified against pinned bridge")
        self.assertEqual(kb.imported(2, kb.UNVERIFIED_V1, "x"), "Imported 2 key(s) — UNVERIFIED (legacy v1 bundle, no signature check)")
        self.assertEqual(kb.invalid("why"), "⚠ Bundle signature INVALID — possibly tampered. why")
        self.assertEqual(kb.malformed("why"), "Bundle malformed: why")
        self.assertEqual(kb.repinned(3), "New kit key saved, 3 key(s) imported")
        self.assertTrue(kb.changed_text("0123456789abcdef").startswith("Kit 01234567 signed these keys"))
        self.assertTrue(kb.is_hex_key("A" * 64))
        self.assertFalse(kb.is_hex_key("g" * 64))
        self.assertFalse(kb.is_hex_key("a" * 63))


if __name__ == "__main__":
    unittest.main()
