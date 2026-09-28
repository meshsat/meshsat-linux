# SPDX-License-Identifier: GPL-3.0-or-later
"""The chat's words (model/chat.py) against Android's MessagesScreen.kt and SatelliteLimits.kt:
the placeholder, the line under the box, the size limit, the marks and the search."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from meshsat.model import chat  # noqa: E402


class ComposerTest(unittest.TestCase):
    def test_the_placeholders(self):
        self.assertEqual(chat.placeholder("iridium", False), "Message by satellite")
        self.assertEqual(chat.placeholder("mesh", True), "Message everyone on the mesh")
        self.assertEqual(chat.placeholder("mesh", False), "Message on the mesh")
        self.assertEqual(chat.placeholder("sms", False), "Text message")

    def test_the_satellite_line_says_the_size_and_the_cost_before_it_is_sent(self):
        self.assertEqual(chat.compose_hint("iridium", "", False, True, True), "By satellite.")
        self.assertEqual(chat.compose_hint("iridium", "", False, True, False), "By satellite, when the modem is back.")
        self.assertEqual(chat.compose_hint("iridium", "hello", False, True, True), "By satellite. 5 bytes, 1 credit.")
        self.assertEqual(chat.compose_hint("iridium", "x" * 51, False, True, False), "By satellite, when the modem is back. 51 bytes, 2 credits.")
        long = "x" * 341
        self.assertEqual(chat.compose_hint("iridium", long, False, True, True), "Too long for a satellite message: 341 bytes, 340 at most. Shorten it or send it in two.")
        self.assertFalse(chat.can_send("iridium", long))
        self.assertTrue(chat.can_send("iridium", "x" * 340))
        self.assertTrue(chat.fits(340))
        self.assertFalse(chat.fits(341))

    def test_bytes_not_characters_for_the_satellite(self):
        self.assertEqual(chat.byte_size("é" * 170), 340)
        self.assertEqual(chat.byte_size("é" * 171), 342)
        self.assertEqual(chat.compose_hint("iridium", "  ü  ", False, True, True), "By satellite. 2 bytes, 1 credit.")

    def test_the_mesh_and_sms_lines(self):
        self.assertEqual(chat.compose_hint("mesh", "x", True, False, False), "On the mesh, when your node is connected.")
        self.assertEqual(chat.compose_hint("mesh", "x", True, True, False), "To everyone on the mesh channel.")
        self.assertEqual(chat.compose_hint("mesh", "x", False, True, False), "Directly to this node on the mesh.")
        self.assertEqual(chat.compose_hint("sms", "", False, True, False), "By SMS from this phone.")
        self.assertEqual(chat.compose_hint("sms", " hello ", False, True, False), "By SMS from this phone, 5 characters.")
        self.assertFalse(chat.can_send("mesh", "   "))
        self.assertEqual(chat.NODE_NOT_CONNECTED, "Not sent: your MeshSat node is not connected. Connect it in Setup.")


class MarksTest(unittest.TestCase):
    def test_the_marks_as_chat_apps_show_them(self):
        self.assertEqual(chat.mark("queued"), ("outlined-schedule", "muted", "Queued"))
        self.assertEqual(chat.mark("sending"), ("outlined-schedule", "muted", "Queued"))
        self.assertEqual(chat.mark("unconfirmed"), ("outlined-help-outline", "amber", "May have been sent"))
        self.assertEqual(chat.mark("failed"), ("outlined-error-outline", "red", "Failed"))
        self.assertEqual(chat.mark("delivered"), ("outlined-done-all", "teal", "Delivered"))
        self.assertEqual(chat.mark("sent"), ("outlined-done", "teal", "Sent"))
        self.assertEqual(chat.mark(""), ("outlined-done", "teal", "Sent"))

    def test_the_badge_of_a_forwarded_message(self):
        self.assertEqual(chat.delivery_label("queued"), "Queued")
        self.assertEqual(chat.delivery_label("unconfirmed"), "May have been sent")
        self.assertEqual(chat.delivery_label("delivered"), "The Hub has it")
        self.assertEqual(chat.delivery_label("odd"), "Forwarded")


class SearchTest(unittest.TestCase):
    def test_the_search_ignores_case_and_keeps_everything_for_no_query(self):
        rows = [{"decoded_text": "First light"}, {"decoded_text": "mew"}, {"decoded_text": ""}]
        self.assertEqual(chat.search(rows, ""), rows)
        self.assertEqual(chat.search(rows, "  "), rows)
        self.assertEqual(chat.search(rows, "LIGHT"), [rows[0]])
        self.assertEqual(chat.search(rows, "nothing"), [])


if __name__ == "__main__":
    unittest.main()
