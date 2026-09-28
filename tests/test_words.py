# SPDX-License-Identifier: GPL-3.0-or-later
"""The words for the app's machinery, as ui/Words.kt gives them."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat.model import words  # noqa: E402


class WordsTest(unittest.TestCase):
    def test_channel_ids_read_as_the_user_knows_them(self):
        self.assertEqual(words.channel("iridium_0"), "Satellite")
        self.assertEqual(words.channel("iridium9704_0"), "Satellite (RockBLOCK 9704)")
        self.assertEqual(words.channel("mesh_0"), "Mesh")
        self.assertEqual(words.channel("sms_0"), "SMS")
        self.assertEqual(words.channel("hub_relay_0"), "Hub relay")
        self.assertEqual(words.channel("hub_0"), "Hub")
        self.assertEqual(words.channel("mqtt_0"), "MQTT broker")
        self.assertEqual(words.channel("aprs_0"), "Ham radio")
        self.assertEqual(words.channel("tcp_rns_0"), "Reticulum")
        self.assertEqual(words.channel(""), "Unknown")
        self.assertEqual(words.channel("zigbee_0"), "zigbee_0")

    def test_transports(self):
        for raw, shown in (("iridium", "Satellite"), ("sbd", "Satellite"), ("mesh", "Mesh"), ("radio", "Mesh"), ("cellular", "SMS"), ("mqtt", "Hub"),
                           ("aprs", "Ham radio"), ("rns", "Reticulum"), ("tak", "TAK"), ("zigbee", "Zigbee")):
            self.assertEqual(words.transport(raw), shown, raw)
        self.assertEqual(words.transport_lane("iridium"), "satellite")
        self.assertEqual(words.channel_lane("hub_relay_0"), "hub")

    def test_delivery_states_and_tones(self):
        self.assertEqual(words.delivery_state("retry"), "Waiting to retry")
        self.assertEqual(words.delivery_state("dead"), "Gave up")
        self.assertEqual(words.delivery_state("held"), "On hold until the link is back")
        self.assertEqual(words.delivery_state("denied"), "Blocked by a rule")
        self.assertEqual(words.delivery_state("odd"), "Odd")
        self.assertEqual(words.delivery_tone("acked"), "green")
        self.assertEqual(words.delivery_tone("held"), "amber")
        self.assertEqual(words.delivery_tone("expired"), "red")
        self.assertEqual(words.delivery_tone("odd"), "muted")

    def test_link_states(self):
        self.assertEqual(words.link_state("online"), "Working")
        self.assertEqual(words.link_state("error"), "Not working")
        self.assertEqual(words.link_state("disabled"), "Switched off")
        self.assertEqual(words.link_state("binding"), "Binding")

    def test_count_has_a_singular(self):
        self.assertEqual(words.count(1, "node"), "1 node")
        self.assertEqual(words.count(2, "node"), "2 nodes")
        self.assertEqual(words.count(0, "message"), "0 messages")
        self.assertEqual(words.count(1, "entry", "entries"), "1 entry")

    def test_ago_as_android_words_it(self):
        now = 1_000_000.0
        self.assertEqual(words.ago(0, now), "never")
        self.assertEqual(words.ago(now - 10, now), "just now")
        self.assertEqual(words.ago(now - 44, now), "just now")
        self.assertEqual(words.ago(now - 45, now), "1 min ago")
        self.assertEqual(words.ago(now - 250, now), "4 min ago")
        self.assertEqual(words.ago(now - 7200, now), "2 h ago")
        self.assertEqual(words.ago(now - 3 * 86400, now), "3 days ago")
        self.assertEqual(words.ago(now - 86400, now), "1 day ago")

    def test_in_time(self):
        now = 1_000_000.0
        self.assertEqual(words.in_time(now + 20, now), "now")
        self.assertEqual(words.in_time(now + 250, now), "in 4 min")
        self.assertEqual(words.in_time(now + 7800, now), "in 2 h 10 min")

    def test_join_and(self):
        self.assertEqual(words.join_and([]), "")
        self.assertEqual(words.join_and(["a"]), "a")
        self.assertEqual(words.join_and(["a", "b"]), "a and b")
        self.assertEqual(words.join_and(["a", "b", "c"]), "a, b and c")


if __name__ == "__main__":
    unittest.main()
