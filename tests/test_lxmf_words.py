# SPDX-License-Identifier: GPL-3.0-or-later
"""The Reticulum (LXMF) lane of Messages (model/chat.py) against Android's Peers.kt and
MessagesScreen.kt: who a chat is with, its name and its line, the composer's words, the New
message rows, and this app's own record of a send giving way to the Bridge's row."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from meshsat import events  # noqa: E402
from meshsat.model import chat  # noqa: E402

PEER = "1234567890abcdef" * 2
PEERS = [{"dest_hash": PEER, "display_name": "Sideband test", "hops": 1, "last_seen": "2026-10-28 10:00:00"},
         {"dest_hash": "fedcba0987654321" * 2, "display_name": "", "hops": 3, "last_seen": "2026-10-28 09:00:00"}]


class LaneTest(unittest.TestCase):
    def test_the_lane_of_a_message(self):
        self.assertEqual(chat.lane_of({"transport": "reticulum"}), "reticulum")
        self.assertEqual(chat.lane_of({"transport": "lxmf"}), "reticulum")
        self.assertEqual(chat.lane_of({"transport": "iridium"}), "satellite")
        self.assertEqual(chat.lane_of({"transport": "sms"}), "sms")
        self.assertEqual(chat.lane_of({"transport": "radio"}), "mesh")
        self.assertEqual(chat.lane_of({}), "mesh")

    def test_an_address(self):
        self.assertTrue(chat.is_lxmf(PEER))
        self.assertTrue(chat.is_lxmf(PEER.upper()))
        self.assertFalse(chat.is_lxmf(PEER[:31]))
        self.assertFalse(chat.is_lxmf("g" * 32))
        self.assertEqual(chat.clean_lxmf_address(f"  <{PEER.upper()}> "), PEER)
        self.assertEqual(chat.clean_lxmf_address("1234 5678"), "12345678")
        self.assertEqual(chat.lxmf_key(PEER), "lxmf:" + PEER)
        self.assertEqual(chat.lxmf_hash("lxmf:" + PEER), PEER)
        self.assertEqual(chat.lxmf_hash(PEER), PEER)

    def test_the_name_and_the_line(self):
        self.assertEqual(chat.lxmf_name("lxmf:" + PEER, PEERS), "Sideband test")
        self.assertEqual(chat.lxmf_name("lxmf:" + "fedcba0987654321" * 2, PEERS), "Reticulum fedcba09")
        self.assertEqual(chat.lxmf_name("lxmf:" + "ab" * 16, []), "Reticulum abababab")
        self.assertEqual(chat.lxmf_announced("lxmf:" + PEER, PEERS), "Sideband test")
        self.assertIsNone(chat.lxmf_announced("lxmf:" + "ab" * 16, PEERS))
        self.assertEqual(chat.lxmf_detail("lxmf:" + PEER), f"By Reticulum (LXMF), {PEER}")
        self.assertTrue(chat.lxmf_known("lxmf:" + PEER, PEERS))
        self.assertFalse(chat.lxmf_known("lxmf:" + "ab" * 16, PEERS))

    def test_the_composers_words(self):
        self.assertEqual(chat.placeholder("lxmf", False), "Message by Reticulum")
        self.assertEqual(chat.lxmf_hint("Sideband test", True), "By Reticulum to Sideband test. Direct waits for the far end, even by satellite.")
        self.assertEqual(chat.lxmf_hint(None, True), "By Reticulum. Direct waits for the far end, even by satellite.")
        self.assertEqual(chat.lxmf_hint(None, False), "By Reticulum, once a path to this address is found.")
        self.assertEqual(chat.lxmf_hint("Sideband test", False), "By Reticulum, once a path to this address is found.")
        self.assertEqual(chat.LXMF_ADDRESS_LABEL, "Or a Reticulum (LXMF) address, 32 hex characters")
        self.assertEqual(chat.MESSAGE_THIS_ADDRESS, "Message this address")

    def test_the_new_message_rows(self):
        self.assertEqual(chat.lxmf_peer_row(PEERS[0]), ("Sideband test", "By Reticulum, 1234567890abcdef... 1 hop away"))
        self.assertEqual(chat.lxmf_peer_row(PEERS[1]), ("Reticulum fedcba09", "By Reticulum, fedcba0987654321... 3 hops away"))


class MergeTest(unittest.TestCase):
    def test_this_apps_record_gives_way_to_the_bridges_row(self):
        local = {"id": -1, "to_node": "lxmf:" + PEER, "decoded_text": "hi", "rx_time": 1000, "direction": "tx", "transport": "reticulum", "local": True}
        stored = {"id": 9, "to_node": "lxmf:" + PEER, "decoded_text": "hi", "rx_time": 1004, "direction": "tx", "transport": "reticulum"}
        self.assertEqual(chat.merge_lxmf([stored, local]), [stored])
        self.assertEqual(chat.merge_lxmf([local]), [local], "no row yet: the record stays")
        other = dict(stored, to_node="lxmf:" + "ab" * 16)
        self.assertEqual(chat.merge_lxmf([other, local]), [other, local], "another address's row is not this send")
        late = dict(stored, rx_time=1000 + 601)
        self.assertEqual(chat.merge_lxmf([late, local]), [late, local], "a row long after is another message")
        note_local = dict(local, decoded_text="")
        note_stored = dict(stored, decoded_text="")
        self.assertEqual(chat.merge_lxmf([note_stored, note_local]), [note_stored], "a note without text matches a text-less row")
        mesh = {"id": 5, "decoded_text": "hi", "direction": "tx", "transport": "radio", "local": True}
        self.assertEqual(chat.merge_lxmf([mesh]), [mesh], "other lanes are not touched")


class EventTest(unittest.TestCase):
    def test_an_inbound_lxmf_event_is_the_reticulum_lane(self):
        item = events.inbound_text({"type": "inbound", "data": {"source": "lxmf_0", "from": "lxmf:" + PEER, "text": "hello"}})
        self.assertEqual(item, {"lane": "reticulum", "from": "lxmf:" + PEER, "text": "hello"})
        item = events.inbound_text({"type": "inbound", "data": {"iface": "tcp_rns_0", "from": "lxmf:" + PEER, "text": "hello"}})
        self.assertEqual(item["lane"], "reticulum")
        self.assertEqual(events.inbound_text({"type": "inbound", "data": {"source": "iridium_0", "from": "1", "text": "x"}})["lane"], "satellite")


if __name__ == "__main__":
    unittest.main()
