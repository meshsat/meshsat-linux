# SPDX-License-Identifier: GPL-3.0-or-later
"""The node's own card over Bluetooth in Android's words: NodeBattery.describe (model/nodes.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import nodes  # noqa: E402


class NodeCardTest(unittest.TestCase):
    def test_the_battery_as_node_battery_describe_says_it(self):
        self.assertEqual(nodes.describe(82, 3.98), "82%, 3.98 V")
        self.assertEqual(nodes.describe(82, 0), "82%")
        self.assertEqual(nodes.describe(82, None), "82%")
        self.assertEqual(nodes.describe(101, 4.2), "On USB power")
        self.assertIsNone(nodes.describe(0, 3.9))  # the Bridge's 0 is Android's "not reported"
        self.assertIsNone(nodes.describe(None, None))

    def test_the_voltage_is_the_nodes_float_formatted_as_kotlin_does(self):
        # 3.975f is 3.97499990463...: Kotlin's "%.2f" writes 3.97; the JSON's 3.975 read as a double would give 3.98
        self.assertEqual(nodes.describe(50, 3.975), "50%, 3.97 V")
        self.assertEqual(nodes.describe(50, 4.0), "50%, 4.00 V")
        self.assertEqual(nodes.describe(50, 3.9749999046325684), "50%, 3.97 V")


if __name__ == "__main__":
    unittest.main()
