# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh radio settings (0.9.0) against Android: the words of RadioConfigScreen.kt and
RegionCheck.kt, the limits of each field, what counts as a change, and the bodies the Bridge
lays over the node's own settings (MESHSAT-1405); the node's log relayed over Bluetooth
(MESHSAT-1406); the scripted Bridge's settings answers, which the e2e cases lean on."""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
sys.path.insert(0, HERE)

from fakebridge import FakeBridge, load_scenario  # noqa: E402
from meshsat.model import nodelog  # noqa: E402
from meshsat.model import radio as model  # noqa: E402

LORA = {"use_preset": True, "modem_preset": 0, "region": 3, "hop_limit": 3, "tx_enabled": True, "tx_power": 0, "spread_factor": 0, "bandwidth": 0, "coding_rate": 0}


class RegionCheckTest(unittest.TestCase):
    def test_a_region_that_fits_or_cannot_be_judged_says_nothing(self):
        self.assertIsNone(model.region_warning(3, "NL"))
        self.assertIsNone(model.region_warning(2, "DE"))
        self.assertIsNone(model.region_warning(1, "US"))
        self.assertIsNone(model.region_warning(1, None))
        self.assertIsNone(model.region_warning(1, "ZZ"))  # a country this app does not know
        self.assertIsNone(model.region_warning(13, "NL"))  # 2.4 GHz is allowed worldwide

    def test_unset_and_the_wrong_region(self):
        self.assertEqual(model.region_warning(0, None), "No region is set, so the radio does not transmit. Pick the region you are in.")
        self.assertEqual(model.region_warning(1, "NL"), "Your phone is set to Netherlands, where radios use EU 868 or EU 433. Check the region matches where you are: "
                                                        "the wrong one can be illegal there, and you will not hear nearby nodes.")
        self.assertIn("where radios use ANZ or NZ 865.", model.region_warning(3, "NZ"))
        self.assertIn("where radios use UA 868 or UA 433.", model.region_warning(3, "UA"))
        self.assertIn("where radios use MY 919 or MY 433.", model.region_warning(3, "MY"))
        self.assertIn("Your phone is set to United Kingdom,", model.region_warning(1, "GB"))

    def test_the_phones_country(self):
        self.assertEqual(model.phone_country({"LANG": "en_GB.UTF-8"}), "GB")
        self.assertEqual(model.phone_country({"LC_ALL": "nl_NL.UTF-8", "LANG": "en_US.UTF-8"}), "NL")
        self.assertIsNone(model.phone_country({"LC_ALL": "C.UTF-8", "LANG": "en_US.UTF-8"}))
        self.assertIsNone(model.phone_country({}))
        self.assertEqual(model.phone_country({"LANG": "en_US.UTF-8"}, sim_iso="nl"), "NL")  # the SIM first, as Android
        self.assertEqual(model.phone_country({"MESHSAT_APP_COUNTRY": "de", "LANG": "en_US.UTF-8"}), "DE")
        self.assertEqual(model.phone_country({"LANG": "sr_RS@latin"}), "RS")


class RadioTabTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(model.region_label(0), "Not set")
        self.assertEqual(model.region_label(3), "EU 868")
        self.assertEqual(model.region_label(99), "Region code 99")
        self.assertEqual(model.preset_label(8), "Short Turbo")
        self.assertEqual(model.preset_label(12), "Preset code 12")
        self.assertNotIn(0, [code for code, _l, _d in model.region_options()])
        self.assertEqual(len(model.preset_options()), 9)

    def test_preset_words(self):
        self.assertEqual(model.preset_button(LORA, 0, False), "Long Fast")
        custom = dict(LORA, use_preset=False, spread_factor=10, bandwidth=125, coding_rate=5)
        self.assertEqual(model.preset_button(custom, 0, False), "Custom settings")
        self.assertEqual(model.preset_button(custom, 4, True), "Medium Fast")
        self.assertEqual(model.preset_details(custom, 0, False), "Custom: spreading factor 10, bandwidth 125 kHz, coding rate 4/5. Picking a preset replaces these.")
        self.assertEqual(model.preset_details(LORA, 2, True), "Very Long Slow: spreading factor 12, bandwidth 62.5 kHz, coding rate 4/8. Radios on 2.4 GHz use wider bandwidths.")
        self.assertEqual(model.preset_details(LORA, 12, True), "This app does not know the details of this preset.")

    def test_only_what_changed_is_sent(self):
        self.assertEqual(model.radio_changes(LORA, 3, 0, False, "0", "3", True), {})
        self.assertEqual(model.radio_changes(LORA, 3, 0, False, "0", "5", True), {"hop_limit": 5})
        self.assertEqual(model.radio_changes(LORA, 1, 0, False, "0", "3", True), {"region": 1})
        self.assertEqual(model.radio_changes(LORA, 3, 0, True, "0", "3", True), {})  # the same preset picked again
        self.assertEqual(model.radio_changes(LORA, 3, 6, True, "0", "3", True), {"modem_preset": 6, "use_preset": True})
        custom = dict(LORA, use_preset=False)
        self.assertEqual(model.radio_changes(custom, 3, 0, True, "0", "3", True), {"modem_preset": 0, "use_preset": True})
        self.assertEqual(model.radio_changes(LORA, 3, 0, False, "20", "3", False), {"tx_power": 20, "tx_enabled": False})

    def test_limits(self):
        self.assertTrue(model.power_ok("30", LORA))
        self.assertFalse(model.power_ok("31", LORA))
        self.assertFalse(model.power_ok("", LORA))
        self.assertTrue(model.power_ok("33", dict(LORA, tx_power=33)))  # what the radio reported is accepted as it is
        self.assertTrue(model.hops_ok("7", LORA))
        self.assertFalse(model.hops_ok("0", LORA))
        self.assertFalse(model.hops_ok("8", LORA))
        self.assertTrue(model.hops_ok("0", dict(LORA, hop_limit=0)))
        self.assertEqual(model.radio_changes(LORA, 3, 0, False, "31", "9", True), {})  # out of range never goes out
        self.assertEqual(model.digits("2a0b7", 2), "20")

    def test_what_asks_first(self):
        self.assertEqual(model.radio_consequences(LORA, {"hop_limit": 5}), [])
        self.assertEqual(model.radio_consequences(LORA, {"region": 1}), ["Changing the region or preset can cut you off from other nodes until they change too."])
        both = model.radio_consequences(LORA, {"modem_preset": 6, "use_preset": True, "tx_enabled": False})
        self.assertEqual(both[1], "With transmit off, nothing you send reaches the mesh, and other nodes stop hearing your node.")
        self.assertEqual(model.section_body("lora", {"hop_limit": 5}), {"section": "lora", "config": {"hop_limit": 5}})


class NameAndChannelsTest(unittest.TestCase):
    def test_this_node(self):
        named = {"node_id": "!52cb81e7", "owner": {"hw_model": 37}, "metadata": {"firmware_version": "2.7.3.dev", "has_wifi": True, "can_shutdown": True}}
        self.assertEqual(model.node_facts(named, "PORTDUINO"), [("Node ID", "!52cb81e7", True), ("Hardware", "Portduino", False), ("Firmware", "2.7.3.dev", True),
                                                                ("Has", "WiFi, Power off", False)])
        self.assertEqual(model.node_facts({}), [("Node ID", "-", True), ("Hardware", "-", False), ("Firmware", "-", True), ("Has", "-", False)])
        self.assertEqual(model.node_facts({"owner": {"hw_model": 50}})[1][1], "LilyGO T-Deck")

    def test_name(self):
        owner = {"long_name": "Bench", "short_name": "BNCH"}
        self.assertFalse(model.can_save_name("Bench", "BNCH", owner))
        self.assertFalse(model.can_save_name(" Bench ", "BNCH", owner))
        self.assertTrue(model.can_save_name("Bench two", "BNCH", owner))
        self.assertFalse(model.can_save_name("  ", "BNCH", owner))
        self.assertEqual(model.owner_body(" Bench two ", "BN2 "), {"long_name": "Bench two", "short_name": "BN2"})

    def test_channel_words(self):
        main = {"index": 0, "role": 1, "name": "", "key": "default"}
        extra = {"index": 1, "role": 2, "name": "team", "key": "main", "uplink_enabled": True, "downlink_enabled": True}
        off = {"index": 2, "role": 0, "name": "", "key": "none"}
        self.assertEqual(model.channel_name(main), "Default name")
        self.assertEqual(model.channel_name(off), "No name")
        self.assertEqual(model.channel_role_line(main), "Main channel. Every node on this mesh shares it.")
        self.assertEqual(model.channel_role_line(extra), "Extra channel. A group channel beside the main one.")
        self.assertEqual(model.channel_role_line(off), "Off. Not in use.")
        self.assertEqual(model.channel_key(main), ("Channel key: default (not private)", "Every Meshtastic radio knows this key, so anyone can read it."))
        self.assertEqual(model.channel_key(extra), ("Channel key: same as the main channel", "It is as private as the main channel."))
        self.assertEqual(model.channel_key({"key": "private"})[0], "Channel key: private")
        self.assertEqual(model.channel_key({"key": "none"})[0], "Channel key: none (not encrypted)")
        self.assertEqual(model.mqtt_line(extra), "Send to MQTT, Receive from MQTT")
        self.assertEqual(model.mqtt_line(main), "")
        self.assertEqual([k for k, _n, _d in model.role_options(main)], [1, 2, 0])
        self.assertEqual([k for k, _n, _d in model.role_options(extra)], [2, 0])

    def test_channel_writes_never_carry_a_key(self):
        extra = {"index": 1, "role": 2, "name": "team"}
        body = model.channel_body(extra, " crew ", 0, True, False)
        self.assertEqual(body, {"index": 1, "name": "crew", "role": "DISABLED", "uplink_enabled": True, "downlink_enabled": False})
        self.assertNotIn("psk", body)
        self.assertEqual(model.channel_body({"index": 0, "role": 1}, "x", 2, False, False)["role"], "PRIMARY")  # channel 0 stays the main channel
        self.assertTrue(model.channel_needs_asking(extra, "crew", 2))
        self.assertTrue(model.channel_needs_asking(extra, "team", 0))
        self.assertFalse(model.channel_needs_asking(extra, "team", 2))
        self.assertFalse(model.channel_needs_asking({"index": 2, "role": 0, "name": ""}, "spare", 0))  # renaming a channel not in use


class PositionBluetoothWifiTest(unittest.TestCase):
    def test_position(self):
        position = {"gps_enabled": True, "fixed_position": False, "position_broadcast_secs": 900, "position_broadcast_smart_enabled": True}
        self.assertEqual(model.position_changes(position, True, False, "900", True), {})
        self.assertEqual(model.position_changes(position, False, True, "0", False),
                         {"gps_enabled": False, "fixed_position": True, "position_broadcast_secs": 0, "position_broadcast_smart_enabled": False})
        self.assertEqual(model.position_changes(position, True, False, "", True), {})

    def test_bluetooth(self):
        bt = {"enabled": True, "mode": 0, "fixed_pin": 123456}
        self.assertEqual(model.pairing_label(0), "PIN shown on the node's screen")
        self.assertEqual(model.pairing_label(5), "Pairing mode 5")
        self.assertEqual(model.pin_text(bt), "123456")
        self.assertEqual(model.pin_text({"fixed_pin": 42}), "000042")
        self.assertEqual(model.pin_text({"fixed_pin": 0}), "")
        self.assertTrue(model.pin_ok(0, ""))
        self.assertFalse(model.pin_ok(1, "12345"))
        self.assertEqual(model.bluetooth_changes(bt, True, 1, "123456"), {"mode": 1})
        self.assertEqual(model.bluetooth_changes(bt, True, 1, "654321"), {"mode": 1, "fixed_pin": 654321})
        self.assertEqual(model.bluetooth_changes(bt, False, 0, ""), {"enabled": False})

    def test_wifi(self):
        net = {"wifi_enabled": False, "wifi_ssid": "", "wifi_psk": ""}
        self.assertEqual(model.wifi_changes(net, False, "", ""), {})
        self.assertEqual(model.wifi_changes(net, True, "home", "secret"), {"wifi_enabled": True, "wifi_ssid": "home", "wifi_psk": "secret"})

    def test_restart_words(self):
        self.assertEqual(model.restart_delay(""), 5)
        self.assertEqual(model.restart_delay("30"), 30)
        self.assertEqual(model.restart_body(5), "In 5 seconds the phone loses the node, the mesh and the satellite modem until the node is back, usually within a minute. "
                                                "The phone reconnects by itself.")
        self.assertNotIn("satellite", model.restart_body(5, cover=True))
        self.assertEqual(model.restart_sent(10), "Sent to the radio. It restarts in 10 seconds.")
        self.assertEqual(model.refused(409, ""), "The node has not sent these settings yet; try again in a moment.")
        self.assertEqual(model.refused(503, ""), "The node is not connected.")
        self.assertEqual(model.refused(0, "no answer"), "The node is not connected.")
        self.assertEqual(model.refused(400, 'unknown lora setting "x"'), 'unknown lora setting "x"')


class RelayedLogTest(unittest.TestCase):
    def test_a_line_the_bridge_relays(self):
        line = nodelog.parse_record({"seq": 7, "received_at": "2026-09-29T00:10:02.123456789Z", "radio_time": 0, "level": "WARNING", "source": "IridiumPipe",
                                     "message": "modem did not answer\n"}, 0)
        self.assertEqual(line["level"], "WARN")
        self.assertEqual(line["received"], 1790640602)
        self.assertTrue(nodelog.format_line(line).endswith(" WARN [IridiumPipe] modem did not answer"))
        self.assertEqual(nodelog.tone(line), "amber")
        crit = nodelog.parse_record({"level": "CRITICAL", "message": "x", "radio_time": 1790640000}, 5)
        self.assertEqual(crit["level"], "CRIT")
        self.assertIsNone(nodelog.parse_record({"level": "", "message": "x"}, 5)["level"])


def call(url: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"} if data else {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


class ScriptedSettingsTest(unittest.TestCase):
    """The scripted Bridge answers as node_config.go does, so the H cases prove the app against
    the real API's rules."""

    def setUp(self):
        self.fake = FakeBridge(load_scenario("bluetooth-connected")).start()

    def tearDown(self):
        self.fake.stop()

    def test_writes_are_laid_over_the_nodes_own(self):
        url = self.fake.url
        status, named = call(url, "GET", "/api/config?format=names")
        self.assertEqual((status, named["node_id"], named["config"]["lora"]["region"]), (200, "!a1b3c2ec", 3))
        self.assertEqual(call(url, "POST", "/api/config/radio", {"section": "lora", "config": {"hop_limit": 5}})[0], 200)
        lora = call(url, "GET", "/api/config?format=names")[1]["config"]["lora"]
        self.assertEqual((lora["hop_limit"], lora["region"], lora["tx_enabled"]), (5, 3, True))
        self.assertEqual(call(url, "POST", "/api/config/radio", {"section": "lora", "config": {"hop_limt": 5}})[0], 400)
        self.assertEqual(call(url, "POST", "/api/config/radio", {"section": "display", "config": {"screen_on_secs": 5}})[0], 409)
        self.assertEqual(call(url, "POST", "/api/config/radio", {"section": "security", "config": {"private_key": "AA=="}})[0], 400)
        self.assertEqual(call(url, "POST", "/api/config/radio", {"section": "security", "config": {"debug_log_api_enabled": True}})[0], 200)

    def test_channels_owner_and_admin(self):
        url = self.fake.url
        self.assertEqual(call(url, "POST", "/api/channels", {"index": 1, "name": "crew", "role": "SECONDARY", "uplink_enabled": True, "downlink_enabled": False})[0], 200)
        channel = call(url, "GET", "/api/config?format=names")[1]["channels"][1]
        self.assertEqual((channel["name"], channel["key"], channel["uplink_enabled"]), ("crew", "private", True))
        self.assertEqual(call(url, "POST", "/api/channels", {"index": 0, "name": "x", "role": "SECONDARY"})[0], 400)
        self.assertEqual(call(url, "POST", "/api/channels", {"index": 8, "name": "x"})[0], 400)
        self.assertEqual(call(url, "POST", "/api/config/owner", {"long_name": "Deck", "short_name": "DK"})[0], 200)
        self.assertEqual(call(url, "GET", "/api/config?format=names")[1]["owner"]["long_name"], "Deck")
        for order in ("reboot", "factory_reset", "set_clock", "shutdown", "nodedb_reset"):
            self.assertEqual(call(url, "POST", f"/api/admin/{order}", {})[0], 200, order)

    def test_the_log_after_a_line_and_follow(self):
        url = self.fake.url
        status, body = call(url, "GET", "/api/mesh/radio-log?after=1&follow=1")
        self.assertEqual((status, body["count"], body["available"], body["following"], body["debug_log_api_enabled"]), (200, 1, True, True, False))
        self.assertEqual(call(url, "GET", "/__fake__/state")[1]["follows"], 1)
