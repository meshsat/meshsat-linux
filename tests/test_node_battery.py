# SPDX-License-Identifier: GPL-3.0-or-later
"""The node's battery as the phone shows it (model/nodes.py): Android's NodeBatteryTest ported
case for case (ble/NodeBatteryTest.kt at v2.19.4)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import nodes  # noqa: E402

T0 = 1_790_000_000.0


def at(minute: float) -> float:
    return T0 + minute * 60


def falling(start: float, per_hour: float, from_min: int, to_min: int) -> list:
    """A reading a minute, falling per_hour points an hour (Kotlin's toInt truncates)."""
    return [(at(m), int(start - per_hour * (m - from_min) / 60.0)) for m in range(from_min, to_min + 1)]


class NodeBatteryTest(unittest.TestCase):
    def test_time_left_follows_the_measured_rate_of_drop(self):
        hours = nodes.hours_left(falling(100.0, 6.0, 0, 60), at(60))
        self.assertIsNotNone(hours)
        self.assertAlmostEqual(hours, 94.0 / 6.0, delta=1.0)

    def test_no_estimate_from_too_little_time_or_too_little_drop(self):
        self.assertIsNone(nodes.hours_left(falling(100.0, 6.0, 0, 20), at(20)), "20 min is too short")
        self.assertIsNone(nodes.hours_left(falling(100.0, 1.0, 0, 60), at(60)), "1 point of drop is noise")
        self.assertIsNone(nodes.hours_left([(at(m), 88) for m in range(0, 91)], at(90)), "a flat level")
        self.assertIsNone(nodes.hours_left([], at(0)))

    def test_only_the_time_since_the_node_came_off_usb_power_counts(self):
        on_usb = [(at(m), nodes.EXTERNAL_POWER) for m in range(0, 41)]
        self.assertIsNone(nodes.hours_left(on_usb + falling(100.0, 6.0, 41, 60), at(60)), "19 min on battery")
        self.assertIsNotNone(nodes.hours_left(on_usb + falling(100.0, 6.0, 41, 101), at(101)))

    def test_readings_older_than_the_window_are_ignored(self):
        old = falling(100.0, 30.0, 0, 30)
        recent = falling(80.0, 4.0, 240, 330)
        hours = nodes.hours_left(old + recent, at(330))
        self.assertAlmostEqual(hours, 74.0 / 4.0, delta=2.0)

    def test_words_for_the_screen(self):
        self.assertEqual(nodes.describe(101, 4.9), "On USB power")
        self.assertEqual(nodes.describe(82, 3.98, 14.2), "82%, 3.98 V, about 14 h left")
        self.assertEqual(nodes.describe(82, 3.98, 14.2, with_voltage=False), "82%, about 14 h left")
        self.assertEqual(nodes.describe(82, 0), "82%")
        self.assertIsNone(nodes.describe(-1, 0))
        self.assertEqual(nodes.time_left_text(0.66), "about 40 min left")
        self.assertEqual(nodes.time_left_text(70.0), "about 3 days left")

    def test_readings_from_the_bridges_telemetry(self):
        records = [{"battery_level": 90, "created_at": "2026-09-29T19:00:00Z"},
                   {"battery_level": 89, "created_at": "2026-09-29T19:10:00.123456789Z"},
                   {"battery_level": None, "created_at": "2026-09-29T19:20:00Z"}, {"battery_level": 88}]
        got = nodes.readings_of(records)
        self.assertEqual([level for _, level in got], [90, 89])
        self.assertAlmostEqual(got[1][0] - got[0][0], 600.123456, places=3)


if __name__ == "__main__":
    unittest.main()
