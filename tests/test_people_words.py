# SPDX-License-Identifier: GPL-3.0-or-later
"""People's signal words and sorts (model/nodes.py), from NodeDetailSheet.kt:48-84,
PeersScreen.kt:108-114 and NodeBatteryTest's "words for the screen"."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import nodes  # noqa: E402


class NodeSignalTest(unittest.TestCase):
    def test_heard_directly_on_the_air(self):
        sig = nodes.node_signal({}, {"snr": 6.46, "rssi": -71, "hops": 0, "hop_start": 3})
        self.assertEqual(sig["short"], "6.5 dB")
        self.assertEqual(sig["long"], "Heard directly. SNR 6.5 dB, RSSI -71 dBm.")
        self.assertEqual(nodes.node_signal({}, {"snr": 6.46, "rssi": 0, "hops": 0, "hop_start": 3})["long"], "Heard directly. SNR 6.5 dB.")

    def test_relayed(self):
        self.assertEqual(nodes.node_signal({}, {"snr": 4, "hops": 1, "hop_start": 3})["short"], "1 hop")
        self.assertEqual(nodes.node_signal({}, {"snr": 4, "hops": 2, "hop_start": 3})["long"], "Heard through other nodes, 2 hops away.")

    def test_unknown_hop_count_falls_to_the_node_list(self):
        """A packet without hop_start (the Bridge's hops is 0 then) says nothing about the path."""
        sig = nodes.node_signal({"hops_away": 0, "snr": 7.25}, {"snr": 1.0, "hops": 0, "hop_start": 0})
        self.assertEqual(sig["short"], "7.3 dB")
        self.assertEqual(sig["long"], "Heard directly. SNR 7.3 dB, as your node last measured it.")

    def test_nothing_known(self):
        sig = nodes.node_signal({}, None)
        self.assertEqual((sig["short"], sig["long"]), ("-", "Not measured yet. Your node measures it when it hears this node transmit."))

    def test_signal_sort(self):
        heard = [nodes.node_signal({"hops_away": 0, "snr": s}) for s in (2.0, 9.5)] + [nodes.node_signal({"hops_away": h}) for h in (3, 1)] + [nodes.node_signal({})]
        ordered = sorted(heard, key=nodes.signal_order)
        self.assertEqual([s["short"] for s in ordered], ["9.5 dB", "2.0 dB", "1 hop", "3 hops", "-"])

    def test_name_sort_and_battery(self):
        self.assertEqual(nodes.name_order({"long_name": " Anna ", "short_name": "AN"}), "anna")
        self.assertEqual(nodes.name_order({"short_name": "Bo", "user_id": "!0000000b"}), "bo")
        self.assertEqual(nodes.name_order({"user_id": "!0000000C"}), "!0000000c")
        self.assertEqual([nodes.battery_cell(v) for v in (101, 55, 0, None)], ["USB", "55%", "-", "-"])


if __name__ == "__main__":
    unittest.main()
