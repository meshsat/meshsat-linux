# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > "Ham radio, TAK and Reticulum": Android's AprsIsPasscodeTest and the callsign rule of
Ax25CodecTest ported case for case, the fields' input filters, what each switch and Save writes
to the Bridge, and the status rows' words (model/integrations.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import integrations as m  # noqa: E402

KISS_RECORD = {"type": "aprs", "enabled": True, "config": {"callsign": "N0CALL", "ssid": 10, "mode": "kiss", "kiss_host": "127.0.0.1", "kiss_port": 8001,
                                                         "tx_delay": 300, "beacon_secs": 0, "relay_third_party": False, "frequency_mhz": 144.8,
                                                         "aprs_is_server": "rotate.aprs2.net:14580", "aprs_is_passcode": ""}}


class PasscodeTest(unittest.TestCase):
    """AprsIsPasscodeTest.kt:12-58, with the values the same algorithm computes."""

    def test_known_callsign(self):
        self.assertEqual(m.passcode("N0CALL"), "13023")

    def test_the_ssid_is_ignored(self):
        self.assertEqual(m.passcode("PA3XYZ-10"), m.passcode("PA3XYZ"))

    def test_case_does_not_matter(self):
        self.assertEqual(m.passcode("pa3xyz"), m.passcode("PA3XYZ"))

    def test_empty_is_receive_only(self):
        self.assertEqual(m.passcode(""), "-1")
        self.assertEqual(m.passcode("-5"), "-1")

    def test_in_range_and_distinct(self):
        self.assertTrue(0 <= int(m.passcode("W3ADO")) <= 32767)
        self.assertNotEqual(m.passcode("PA3XYZ"), m.passcode("PA3ABC"))
        self.assertNotEqual(m.passcode("N0CAL"), "-1")
        self.assertEqual([m.passcode(c) for c in ("PA3XYZ", "PA3ABC", "W3ADO", "N0CAL")], ["18849", "21153", "10901", "12947"])


class FullCallsignTest(unittest.TestCase):
    """Ax25CodecTest's format with Android's service rule (GatewayService.kt:1429)."""

    def test_rule(self):
        self.assertEqual(m.full_callsign("PA3XYZ", "10"), "PA3XYZ-10")
        self.assertEqual(m.full_callsign("PA3XYZ", "0"), "PA3XYZ")
        self.assertEqual(m.full_callsign("PA3XYZ", ""), "PA3XYZ")
        self.assertEqual(m.full_callsign("PA3XYZ", "00"), "PA3XYZ-00")
        self.assertEqual(m.full_callsign("WIDE1", "1"), "WIDE1-1")


class InputFilterTest(unittest.TestCase):
    def test_filters(self):
        self.assertEqual(m.callsign("pa3xyz-10"), "PA3XYZ")
        self.assertEqual(m.ssid("1a5"), "15")
        self.assertEqual(m.ssid("123"), "12")
        self.assertEqual(m.port("80a01x9"), "80019")
        self.assertEqual(m.passcode_input("-1abc"), "-1")
        self.assertEqual(m.passcode_input("12-345678"), "12-345")
        self.assertEqual(m.radius("12345"), "1234")
        self.assertEqual(m.interval("1000"), "100")
        self.assertEqual(m.prefix("meshsat-team-x"), "MESHSAT-TE")

    def test_only_decimal_digits(self):
        self.assertEqual(m.port("٣٤"), "٣٤")  # Kotlin's isDigit takes other scripts' digits too
        self.assertEqual(m.port("½²"), "")


class AprsBodyTest(unittest.TestCase):
    def test_a_toggle_sends_the_stored_config_and_enabled(self):
        body = m.aprs_flag_body(KISS_RECORD, enabled=False)
        self.assertEqual(body["enabled"], False)
        self.assertEqual(body["config"], KISS_RECORD["config"])
        body = m.aprs_flag_body(KISS_RECORD, mode="is")
        self.assertIs(body["enabled"], True)
        self.assertEqual(body["config"]["mode"], "is")
        self.assertEqual(body["config"]["tx_delay"], 300)

    def test_kiss_save(self):
        fields = {"callsign": "N0CALL", "ssid": "7", "kiss_host": "", "kiss_port": "x"}
        body = m.aprs_save_body(KISS_RECORD, True, "kiss", fields, None)
        c = body["config"]
        self.assertEqual((body["enabled"], c["ssid"], c["kiss_host"], c["kiss_port"], c["external_direwolf"]), (True, 7, "localhost", 8001, True))
        self.assertEqual((c["tx_delay"], c["beacon_secs"], c["relay_third_party"], c["frequency_mhz"]), (300, 0, False, 144.8))
        self.assertNotIn("kiss_device", c)

    def test_is_save(self):
        record = {"enabled": True, "config": dict(KISS_RECORD["config"], aprs_is_passcode="****")}
        fields = {"callsign": "N0CALL", "ssid": "10", "is_host": "", "is_port": "", "passcode": "", "radius": "", "beacon": True, "interval": ""}
        c = m.aprs_save_body(record, True, "is", fields, (52.3676, 4.9041))["config"]
        self.assertEqual((c["aprs_is_server"], c["aprs_is_passcode"], c["aprs_is_filter_km"], c["position_beacon"], c["position_beacon_min"]),
                         ("rotate.aprs2.net:14580", "****", 100, True, 10))
        self.assertEqual((c["aprs_is_filter_lat"], c["aprs_is_filter_lon"]), (52.3676, 4.9041))
        c = m.aprs_save_body(None, False, "is", dict(fields, passcode="13023", radius="50"), None)["config"]
        self.assertEqual((c["aprs_is_passcode"], c["aprs_is_filter_km"], c["aprs_is_filter_lat"]), ("13023", 50, 0.0))

    def test_the_form_from_the_bridge(self):
        form = m.aprs_form(KISS_RECORD)
        self.assertEqual((form["callsign"], form["ssid"], form["mode"], form["is_host"], form["is_port"], form["passcode"]),
                         ("N0CALL", "10", "kiss", "rotate.aprs2.net", "14580", "-1"))
        self.assertEqual(m.aprs_form(None)["ssid"], "10")
        masked = {"enabled": True, "config": {"aprs_is_passcode": "****"}}
        self.assertEqual(m.aprs_form(masked)["passcode"], "")
        self.assertEqual(m.aprs_form(masked, "13023")["passcode"], "13023")
        self.assertEqual(m.split_server("[2001:db8::1]:14580"), ("[2001:db8::1]", "14580"))


class TakBodyTest(unittest.TestCase):
    def test_first_write_carries_androids_defaults(self):
        body = m.tak_body(None, enabled=True)
        self.assertEqual(body, {"enabled": True, "config": {"callsign_prefix": "MESHSAT", "multicast": True, "hub_export": True}})

    def test_each_switch_changes_its_own_flag(self):
        record = {"enabled": True, "config": {"callsign_prefix": "TEAM1", "multicast": True, "hub_export": True, "cot_stale_seconds": 300}}
        body = m.tak_body(record, atak=False)
        self.assertEqual((body["enabled"], body["config"]["multicast"], body["config"]["hub_export"], body["config"]["cot_stale_seconds"]), (True, False, True, 300))
        self.assertEqual(m.tak_body(record, prefix="E2E")["config"]["callsign_prefix"], "E2E")


class RnsTest(unittest.TestCase):
    def test_config_and_defaults(self):
        self.assertEqual(m.rns_config(" reticulum.example ", "", True), {"host": "reticulum.example", "port": 4242, "tls": True})
        self.assertEqual(m.rns_form(None, {})["port"], "4242")
        iface = {"id": "tcp_rns_0", "enabled": True, "config": {"host": "h", "port": 443, "tls": False}}
        self.assertEqual(m.rns_form(iface, {}), {"enabled": True, "host": "h", "port": "443", "tls": False})


class StatusWordsTest(unittest.TestCase):
    def test_aprs_rows(self):
        self.assertIsNone(m.aprs_status({"enabled": False}, {"connected": True}))
        self.assertEqual(m.aprs_status(KISS_RECORD, {"state": "connected"}), ("KISS TNC", "Connected", True))
        self.assertEqual(m.aprs_status(KISS_RECORD, {"state": "connecting"})[1], "Connecting...")
        self.assertEqual(m.aprs_status(KISS_RECORD, {"state": "error"})[1], "Error")
        self.assertEqual(m.aprs_status(KISS_RECORD, {"state": "disconnected"})[1], "Disconnected")
        is_record = {"enabled": True, "config": {"mode": "is"}}
        self.assertEqual(m.aprs_status(is_record, {"state": "connected", "aprs_is_verified": True})[0], "APRS-IS (verified)")
        self.assertEqual(m.aprs_status(is_record, {"state": "connected", "aprs_is_verified": False})[0], "APRS-IS")

    def test_an_older_bridge(self):
        self.assertEqual(m.aprs_status(KISS_RECORD, {"connected": True})[1], "Connected")
        self.assertEqual(m.aprs_status(KISS_RECORD, {"connected": False, "kiss_addr": "127.0.0.1:8001"})[1], "Connecting...")
        self.assertEqual(m.aprs_status(KISS_RECORD, {"connected": False})[1], "Error")
        self.assertEqual(m.aprs_status({"enabled": False}, {}, pending=True)[1], "Connecting...")

    def test_rns_rows(self):
        self.assertIsNone(m.rns_status(None))
        self.assertIsNone(m.rns_status({"enabled": False, "online": True}))
        self.assertEqual(m.rns_status({"enabled": True, "online": True}), ("RNS TCP", "Connected", True))
        self.assertEqual(m.rns_status({"enabled": True, "running": True})[1], "Connecting...")
        self.assertEqual(m.rns_status({"enabled": True, "running": True, "last_error": "refused"})[1], "Disconnected")
        self.assertEqual(m.rns_status({"enabled": True})[1], "Error")


if __name__ == "__main__":
    unittest.main()
