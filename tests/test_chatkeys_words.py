# SPDX-License-Identifier: GPL-3.0-or-later
"""A chat's own key (model/chatkeys.py), from MessagesScreen.kt:465-548 and 854-969."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import chatkeys as ck  # noqa: E402

KEY = "00112233445566778899aabbccddeeff00112233445566778899AABBCCDDEEFF"


class ChatKeyTest(unittest.TestCase):
    def test_validation_as_android(self):
        self.assertTrue(ck.valid(KEY))
        self.assertFalse(ck.valid(KEY[:63]))
        self.assertFalse(ck.valid(KEY + "0"))
        self.assertFalse(ck.valid(" " + KEY[1:]), "not trimmed: a leading space is not a key")
        self.assertFalse(ck.valid(KEY[:63] + "g"))

    def test_generated_keys(self):
        a, b = ck.generate(), ck.generate()
        self.assertTrue(ck.valid(a) and a == a.lower() and len(a) == 64)
        self.assertNotEqual(a, b)

    def test_where_the_bridge_keeps_it(self):
        self.assertEqual(ck.address("sms:+31600000000"), ("sms", "+31600000000"))
        self.assertEqual(ck.path("sms:+31600000000"), "/api/keys/sms/%2B31600000000")
        self.assertEqual(ck.path("!a1b3c2ec"), "/api/keys/mesh/!a1b3c2ec")
        self.assertEqual(ck.path("!ffffffff"), "/api/keys/mesh/!ffffffff")
        self.assertEqual(ck.path("satellite"), "/api/keys/iridium/satellite")

    def test_the_lock(self):
        """activeKey: the chat's key, else Messaging's key even with encryption off."""
        self.assertTrue(ck.lock_on(KEY, ""))
        self.assertTrue(ck.lock_on(None, KEY))
        self.assertFalse(ck.lock_on(None, ""))
        self.assertFalse(ck.lock_on(None, None))

    def test_androids_words(self):
        self.assertEqual((ck.SAVED, ck.INVALID, ck.COPIED, ck.PASTED), ("Key saved", "Invalid key — 64 hex chars required", "Key copied", "Key pasted"))
        self.assertEqual(ck.NOT_A_KEY, "Clipboard doesn't contain a valid 64-char hex key")
        self.assertEqual(ck.REMOVED, "Key removed — messages will show encrypted")


if __name__ == "__main__":
    unittest.main()
