# SPDX-License-Identifier: GPL-3.0-or-later
"""People cards (0.11.0) against MeshSat Android v2.19.4: ContactQRTest ported case for case,
and the fixed vector (seed 00..1f) that the Bridge's Go test (MESHSAT-1416) and this app must
both produce byte for byte."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from meshsat.model import cards  # noqa: E402

TEXT = ("meshsat:contact:1:S3lyaWFrb3MfQTZFSHZfUE9FTDRkY04wWTUwdkFtV2ZrMWpDYnBRMWZIZHlHWkJKVk1iZx8hYmY2ZWU3YmMfbXNhLWZsYW5ldXIfMTc4OTkwMDAwMA."
        "oKXEDt4bFgUMr1qBHOBVgUiKRqAi50xVXnxeSukzSnMqXztpxqSABg4L9xSqbDVJdlTrh76ycQN_f1A22DgaAA")
MINE = ("meshsat:contact:1:TWVzaFNhdCBwaG9uZR9BNkVIdl9QT0VMNGRjTjBZNTB2QW1XZmsxakNicFExZkhkeUdaQkpWTWJnHx8fMTc4OTkwMDAwMA."
        "OGA5_8_Q-mGL0x0kavwMIeFHryIyk4UagJH4KlmSgNDR4Xq9Nzzi98e7TS9eN3ZSCTeAV8GmhK5YVVk8H_sxAA")
ALTERED = ("meshsat:contact:1:TWFsbG9yeR9BNkVIdl9QT0VMNGRjTjBZNTB2QW1XZmsxakNicFExZkhkeUdaQkpWTWJnHyFiZjZlZTdiYx9tc2EtZmxhbmV1ch8xNzg5OTAwMDAw."
           "oKXEDt4bFgUMr1qBHOBVgUiKRqAi50xVXnxeSukzSnMqXztpxqSABg4L9xSqbDVJdlTrh76ycQN_f1A22DgaAA")
OTHER_KEY = ("meshsat:contact:1:S3lyaWFrb3MfQTZFSHZfUE9FTDRkY04wWTUwdkFtV2ZrMWpDYnBRMWZIZHlHWkJKVk1iZx8hYmY2ZWU3YmMfbXNhLWZsYW5ldXIfMTc4OTkwMDAwMA."
             "bzVpCUzl6papc7cjSF6c6f67AnKGbXYA7RVHYIMjlXk6T9N0tezkxBJzSNIInfIZ-BmTx1nNe_nKvH94qHjcDg")


def key(seed: bytes):
    private = Ed25519PrivateKey.from_private_bytes(seed)
    return private, private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class ContactQRTest(unittest.TestCase):
    """app/src/test/java/net/meshsat/android/ContactQRTest.kt"""

    def setUp(self):
        self.private, self.pub = key(bytes(range(32)))

    def card(self, name="Kyriakos", node="!bf6ee7bc", bridge="msa-flaneur", issued=1_789_900_000):
        return cards.encode(name, self.pub, node, bridge, issued, self.private.sign)

    def test_a_card_survives_the_round_trip(self):
        text = self.card()
        self.assertTrue(text.startswith(cards.PREFIX))
        result, card = cards.decode(text)
        self.assertEqual(result, "Ok")
        self.assertEqual(card, {"name": "Kyriakos", "signing_pub": self.pub, "mesh_node_id": "!bf6ee7bc", "bridge_id": "msa-flaneur", "issued_at": 1_789_900_000})

    def test_a_card_altered_in_transit_is_refused(self):
        text = self.card()
        body = text[len(cards.PREFIX):]
        payload, sig = body.split(".")
        forged = cards.unb64(payload).decode().replace("Kyriakos", "Mallory", 1).encode()
        self.assertEqual(cards.decode(cards.PREFIX + cards.b64(forged) + "." + sig)[0], "BadSignature")

    def test_a_card_signed_by_another_key_is_refused(self):
        other, _ = key(bytes([7]) * 32)
        text = cards.encode("Kyriakos", self.pub, "!bf6ee7bc", "msa-flaneur", 1_789_900_000, other.sign)
        self.assertEqual(cards.decode(text)[0], "BadSignature")

    def test_anything_that_is_not_a_card_is_told_apart_from_a_broken_one(self):
        self.assertEqual(cards.decode("https://meshsat.net")[0], "NotACard")
        self.assertEqual(cards.decode("")[0], "NotACard")
        self.assertEqual(cards.decode("meshsat:contact:2:abc.def")[0], "NotACard")
        self.assertEqual(cards.decode(cards.PREFIX + "no-dot")[0], "Malformed")
        self.assertEqual(cards.decode(cards.PREFIX + "!!!.???")[0], "Malformed")

    def test_a_key_of_the_wrong_length_is_refused_before_it_reaches_the_verifier(self):
        payload = cards.b64("Someone\x1fAAAA\x1f\x1f\x1f0".encode())
        self.assertEqual(cards.decode(cards.PREFIX + payload + ".AAAA")[0], "Malformed")

    def test_a_name_carrying_the_separator_is_refused_rather_than_reshaping_the_record(self):
        with self.assertRaises(ValueError) as caught:
            self.card(name="Kyriakos\x1ffake-key")
        self.assertIn("separator", str(caught.exception))

    def test_the_fingerprint_is_stable_readable_and_different_per_identity(self):
        _result, card = cards.decode(self.card())
        fp = cards.fingerprint(card["signing_pub"])
        self.assertEqual(fp, cards.fingerprint(self.pub))
        self.assertEqual(len(fp), 19)
        self.assertEqual(fp.count(" "), 3)
        self.assertNotEqual(fp, cards.fingerprint(key(bytes([7]) * 32)[1]))


class FixedVectorTest(unittest.TestCase):
    """The same bytes as the Bridge's Go test and Android's JVM (Ed25519 is deterministic)."""

    def setUp(self):
        self.private, self.pub = key(bytes(range(32)))

    def test_the_vector(self):
        self.assertEqual(cards.encode("Kyriakos", self.pub, "!bf6ee7bc", "msa-flaneur", 1789900000, self.private.sign), TEXT)
        self.assertEqual(cards.encode(cards.DEFAULT_NAME, self.pub, "", "", 1789900000, self.private.sign), MINE)
        self.assertEqual(cards.fingerprint(self.pub), "5647 5aa7 5463 474c")
        self.assertEqual(cards.fingerprint(key(bytes([7]) * 32)[1]), "fe81 2c12 f3ab 4ce6")

    def test_the_verdicts(self):
        self.assertEqual(cards.decode(ALTERED)[0], "BadSignature")
        self.assertEqual(cards.decode(OTHER_KEY)[0], "BadSignature")
        self.assertEqual(cards.decode("meshsat:contact:1:U29tZW9uZR9BQUFBHx8fMA.AAAA")[0], "Malformed")
        self.assertEqual(cards.decode("  " + TEXT + "\n")[0], "Ok")
        self.assertEqual(cards.verdict("BadSignature"), "That card has been altered since it was made. Not saved.")
        self.assertEqual(cards.verdict("Malformed"), "That is a MeshSat card, but a damaged one.")
        self.assertEqual(cards.verdict("NotACard"), "That is not a MeshSat contact card.")
        self.assertIsNone(cards.verdict("Ok"))

    def test_javas_base64_rules(self):
        for text, size in (("AAAA", 3), ("AA", 1), ("AAA", 2), ("AB", 1), ("AA==", 1), ("", 0)):
            self.assertEqual(len(cards.unb64(text)), size, text)
        for text in ("A", "AA=", "A+A/", "AAAA\n"):
            self.assertIsNone(cards.unb64(text), text)

    def test_the_name_limit_counts_utf16_units(self):
        sign = self.private.sign
        cards.encode("😀" * 24, self.pub, "", "", 1, sign)
        with self.assertRaises(ValueError) as caught:
            cards.encode("😀" * 24 + "a", self.pub, "", "", 1, sign)
        self.assertEqual(str(caught.exception), "name over 48 characters")
        with self.assertRaises(ValueError):
            cards.encode("  ", self.pub, "", "", 1, sign)


class ListTest(unittest.TestCase):
    def setUp(self):
        _p, self.pub = key(bytes(range(32)))
        _p, self.pub2 = key(bytes([7]) * 32)

    def test_rows_in_androids_words(self):
        self.assertEqual(cards.row_line({"trust": cards.SCANNED, "mesh_node_id": "!bf6ee7bc", "bridge_id": ""}), "Scanned in person · mesh !bf6ee7bc")
        self.assertEqual(cards.row_line({"trust": cards.IMPORTED, "mesh_node_id": "!bf6ee7bc", "bridge_id": "msa-flaneur"}), "Imported as text · mesh !bf6ee7bc · msa-flaneur")
        self.assertEqual(cards.row_line({"trust": cards.IMPORTED, "mesh_node_id": "", "bridge_id": ""}), "Imported as text")

    def test_record_upsert_forget_and_order(self):
        card = {"name": "kyriakos", "signing_pub": self.pub, "mesh_node_id": "", "bridge_id": "", "issued_at": 1789900000}
        row = cards.record(card, cards.SCANNED, now_ms=5)
        self.assertEqual(row, {"fingerprint": "5647 5aa7 5463 474c", "name": "kyriakos", "signing_pub": "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=", "mesh_node_id": "",
                               "bridge_id": "", "trust": "SCANNED", "issued_at": 1789900000, "added_at": 5})
        rows = cards.upsert([], row)
        other = cards.record({**card, "name": "Anna", "signing_pub": self.pub2}, cards.IMPORTED)
        rows = cards.upsert(rows, other)
        self.assertEqual([r["name"] for r in cards.ordered(rows)], ["Anna", "kyriakos"])
        again = cards.record({**card, "name": "Kyriakos K"}, cards.IMPORTED)
        rows = cards.upsert(rows, again)  # the same key: the row replaced, trust included
        self.assertEqual(len(rows), 2)
        self.assertEqual([(r["name"], r["trust"]) for r in rows if r["fingerprint"] == "5647 5aa7 5463 474c"], [("Kyriakos K", "IMPORTED")])
        self.assertEqual(len(cards.forget(rows, "5647 5aa7 5463 474c")), 1)
        self.assertEqual(cards.ascii_fold("ÄBc"), "Äbc")


if __name__ == "__main__":
    unittest.main()
