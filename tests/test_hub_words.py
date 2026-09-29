# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hub page, the Setup row and the connection test in MeshSat Android's words and rules
(SettingsScreen.kt:1625-1900, SetupScreen.kt:115-133), from the Bridge's answers (MESHSAT-1417)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import hub  # noqa: E402

LINKED = {"url": "wss://mqtt-hub.meshsat.net/mqtt", "bridge_id": "", "running_as": "meshsat-pinephone-pro", "enabled": True}


class StatusTest(unittest.TestCase):
    def test_the_six_states_in_androids_order(self):
        cases = [({"enabled": False, "state": "connected"}, "Switched off", "green"),
                 (dict(LINKED, state="connected"), "Connected as meshsat-pinephone-pro", "green"),
                 (dict(LINKED, state="connecting"), "Connecting", "amber"),
                 (dict(LINKED, state="error", last_error="network Error : dial tcp: connection refused"), "Cannot reach the Hub", "red"),
                 (dict(LINKED, state="disconnected"), "Not connected", "muted"),
                 (dict(LINKED, state=""), "Not set up: scan the Hub's QR code", "muted")]
        for answer, words, dot in cases:
            self.assertEqual((hub.status(answer), hub.dot(answer)), (words, dot), answer)

    def test_the_dot_follows_the_link_not_the_switch(self):
        self.assertEqual(hub.dot({"enabled": False, "state": "error"}), "red")

    def test_an_older_bridge_reports_only_link(self):
        self.assertEqual(hub.status({"url": "x", "link": "connected", "bridge_id": "kit"}), "Connected as kit")
        self.assertEqual(hub.status({"url": "x", "link": "disconnected"}), "Not connected")
        self.assertEqual(hub.status({"url": "x"}), "Not set up: scan the Hub's QR code")

    def test_why_only_switched_on_failed_and_with_a_reason(self):
        failed = dict(LINKED, state="error", last_error="tls: bad certificate")
        self.assertEqual(hub.why(failed), "Why: tls: bad certificate")
        self.assertEqual(hub.why(dict(failed, enabled=False)), "")
        self.assertEqual(hub.why(dict(failed, last_error="  ")), "")
        self.assertEqual(hub.why(dict(failed, state="disconnected")), "")

    def test_the_setup_row_ignores_the_switch(self):
        self.assertEqual(hub.setup_row({"enabled": False, "state": "connected"}), ("Connected", "green"))
        self.assertEqual(hub.setup_row(dict(LINKED, state="disconnected")), ("Not connected", "amber"))
        self.assertEqual(hub.setup_row(dict(LINKED, state="error")), ("Cannot reach the Hub", "red"))
        self.assertEqual(hub.setup_row(None), ("Not set up. Scan the Hub's QR code.", "muted"))

    def test_the_wait_on_the_card(self):
        self.assertEqual(hub.card_waited(12), "Getting the Hub's settings, 12 s")
        self.assertEqual(hub.card_waited(-3), "Getting the Hub's settings, 0 s")


class PingTest(unittest.TestCase):
    def test_elapsed_in_milliseconds_without_a_space_and_green(self):
        result = hub.ping_result(200, {"elapsed_ms": 142}, None)
        self.assertEqual(result, "142ms")
        self.assertTrue(hub.ping_green(result))

    def test_no_link_says_not_connected(self):
        self.assertEqual(hub.ping_result(409, {"error": "not connected"}, "not connected"), "Not connected")
        self.assertFalse(hub.ping_green("Not connected"))

    def test_a_failure_gives_its_first_thirty_units(self):
        self.assertEqual(hub.ping_result(502, None, "no answer within 10s from the broker at all"), "failed: no answer within 10s from the ")
        self.assertEqual(hub.ping_result(0, None, None), "failed: null")
        self.assertEqual(hub.cut_utf16("a" * 29 + "😀", 30), "a" * 29)  # a surrogate pair is never split


class FormTest(unittest.TestCase):
    def test_the_form_from_the_bridge(self):
        values = hub.form({"url": "wss://h/mqtt", "bridge_id": "kit-a", "callsign": "Team", "username": "kit-a", "has_password": True, "health_interval": 45})
        self.assertEqual(values, {"url": "wss://h/mqtt", "bridge_id": "kit-a", "callsign": "Team", "username": "kit-a", "interval": "45", "has_password": True})
        self.assertEqual(hub.form({})["interval"], "30")

    def test_digits_only_at_most_four(self):
        self.assertEqual(hub.interval_digits("1a2b3c45"), "1234")
        self.assertEqual(hub.interval_digits(""), "")

    def test_save_sends_what_was_typed(self):
        self.assertEqual(hub.save_body("wss://h/mqtt", "", "", "kit-a", "", "60"),
                         {"url": "wss://h/mqtt", "bridge_id": "", "callsign": "", "username": "kit-a", "health_interval": 60})
        body = hub.save_body("", "", "Team", "", "secret", "")
        self.assertEqual((body["password"], body["health_interval"], body["callsign"]), ("secret", 0, "Team"))


if __name__ == "__main__":
    unittest.main()
