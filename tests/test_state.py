# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's State: every field the screens read exists from the start, and the helpers
answer sensibly with nothing polled yet (an attribute missing here took every poll's
on_state down before the screens were updated, 28 Sep 2026)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import api  # noqa: E402


class StateTest(unittest.TestCase):
    def test_every_helper_works_on_a_fresh_state(self):
        s = api.State()
        self.assertFalse(s.mesh_connected())
        self.assertFalse(s.modem_connected())
        self.assertFalse(s.hub_configured())
        self.assertFalse(s.sms_ready())
        self.assertIsNone(s.position())
        self.assertEqual(s.own_node(), None)
        self.assertEqual(s.others(), [])
        self.assertEqual(s.heard_recently(), 0)
        self.assertEqual(s.node_mode(), "cover")
        self.assertEqual(s.sms_today(), 0)
        for name in ("bridge", "nodes", "messages", "sms", "contacts", "watchdog", "hardware", "ble", "phone", "entered", "location_hint", "last_tx", "name_requests", "unreachable_since", "polled_at"):
            self.assertTrue(hasattr(s, name), name)

    def test_node_mode_follows_the_hardware_file(self):
        s = api.State()
        s.hardware = {"node": "bluetooth", "why": "forced by /etc/meshsat/hardware.conf"}
        self.assertEqual(s.node_mode(), "bluetooth")
        s.hardware = {}
        self.assertEqual(s.node_mode(), "cover")

    def test_hardware_file_missing(self):
        old = api.HARDWARE_PATH
        api.HARDWARE_PATH = "/nonexistent/hardware.json"
        try:
            self.assertEqual(api.hardware(), {})
        finally:
            api.HARDWARE_PATH = old


if __name__ == "__main__":
    unittest.main()
