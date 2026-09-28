# SPDX-License-Identifier: GPL-3.0-or-later
"""Routing rules' words and records (model/rules.py) against Android's RulesScreen.kt:
RuleLinkChoicesTest and DuplicatesTheHubTest ported, then the tabs, the cards, the editor's
checks and the record a save writes."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from meshsat.model import rules as r  # noqa: E402
from meshsat.model import words  # noqa: E402


def rule(**more) -> dict:
    out = {"id": 3, "interface_id": "mesh_0", "direction": "ingress", "priority": 10, "name": "SOS to satellite", "enabled": True, "action": "forward", "forward_to": "iridium_0",
           "filters": "{}", "filter_node_group": None, "filter_sender_group": None, "filter_portnum_group": None, "schedule_type": "none", "schedule_config": "",
           "forward_options": "{}", "qos_level": 1, "rate_limit_per_min": 0, "rate_limit_window": 0, "match_count": 0, "last_match_at": None}
    out.update(more)
    return out


class RuleLinkChoicesTest(unittest.TestCase):
    """What the rule editor offers, and what it calls it (MESHSAT-1281)."""

    def test_the_link_that_reaches_the_hub_is_the_one_called_hub(self):
        self.assertEqual(words.channel("hub_0"), "Hub")
        self.assertEqual(words.channel("hub_relay"), "Hub relay")
        self.assertEqual(words.channel("mqtt_0"), "MQTT broker")

    def test_no_two_links_share_a_name(self):
        ids = ["mesh_0", "iridium_0", "iridium9704_0", "sms_0", "hub_0", "hub_relay", "mqtt_0", "aprs_0"]
        names = [words.channel(i) for i in ids]
        self.assertEqual(len(names), len(set(names)))
        # The Bridge's own links: its 9704 link is iridium_imt_0.
        bridge = ["mesh_0", "iridium_0", "iridium_imt_0", "cellular_0", "hub_0", "mqtt_0", "aprs_0"]
        self.assertEqual(words.channel("iridium_imt_0"), "Satellite (RockBLOCK 9704)")
        self.assertEqual(len({words.channel(i) for i in bridge}), len(bridge))

    def test_a_switched_off_link_is_not_offered(self):
        all_links = [("mesh_0", False), ("mqtt_0", True), ("hub_0", False), ("aprs_0", True)]
        self.assertEqual(r.link_choices(all_links, keep=""), ["mesh_0", "hub_0"])

    def test_the_link_a_saved_rule_already_names_stays_switched_off_or_not(self):
        all_links = [("mesh_0", False), ("mqtt_0", True), ("hub_0", False)]
        self.assertEqual(r.link_choices(all_links, keep="mqtt_0"), ["mesh_0", "mqtt_0", "hub_0"])

    def test_the_bridges_interfaces_become_choices_with_androids_fallback(self):
        self.assertEqual(r.available_links([{"id": "mesh_0", "enabled": True}, {"id": "hub_0", "enabled": False}]), ["mesh_0"])
        self.assertEqual(r.available_links([]), ["mesh_0", "iridium_0", "sms_0"])


class DuplicatesTheHubTest(unittest.TestCase):
    def test_satellite_to_the_hub_duplicates_what_the_provider_already_sends(self):
        self.assertTrue(r.duplicates_the_hub("iridium_0", "hub_0"))
        self.assertTrue(r.duplicates_the_hub("iridium9704_0", "hub_0"))

    def test_mesh_and_sms_to_the_hub_are_the_point_of_the_feature(self):
        self.assertFalse(r.duplicates_the_hub("mesh_0", "hub_0"))
        self.assertFalse(r.duplicates_the_hub("sms_0", "hub_0"))
        self.assertFalse(r.duplicates_the_hub("aprs_0", "hub_0"))

    def test_satellite_anywhere_else_is_not_the_hubs_business(self):
        self.assertFalse(r.duplicates_the_hub("iridium_0", "sms_0"))
        self.assertFalse(r.duplicates_the_hub("iridium_0", "mesh_0"))
        self.assertFalse(r.duplicates_the_hub("iridium_0", "hub_relay"))


class TabsAndCardsTest(unittest.TestCase):
    def test_every_rule_lands_on_exactly_one_tab(self):
        self.assertEqual(r.tab_of(rule(interface_id="mesh_0")), "From mesh")
        self.assertEqual(r.tab_of(rule(interface_id="iridium_0", forward_to="mesh_0")), "Into mesh")
        self.assertEqual(r.tab_of(rule(interface_id="sms_0", action="drop", forward_to="")), "Between links")
        self.assertEqual(r.tab_of(rule(interface_id="iridium_0", action="log", forward_to="")), "Between links")
        badges = r.badges([rule(), rule(id=4, interface_id="sms_0", action="drop", forward_to="")], 5)
        self.assertEqual(badges, {"From mesh": 1, "Into mesh": 0, "Between links": 1, "Deliveries": 0, "Queue": 5})

    def test_the_route_line_in_androids_words(self):
        self.assertEqual(r.route_text(rule()), "Forward: Mesh to Satellite")
        self.assertEqual(r.route_text(rule(action="drop", interface_id="sms_0", forward_to="")), "Drop: messages from SMS")
        self.assertEqual(r.route_text(rule(action="log", direction="egress", interface_id="iridium_0")), "Log only: messages leaving by Satellite")
        parts = r.route_parts(rule())
        self.assertEqual(parts[0], ("Forward: ", "bold"))
        self.assertEqual(parts[1], ("Mesh", "mesh"))
        self.assertEqual(parts[3], ("Satellite", "satellite"))

    def test_the_meta_line(self):
        now = words.stamp_epoch("2027-01-15T10:00:00Z")
        plain = rule()
        self.assertEqual(r.meta_line(plain, now), "No matches yet")
        busy = rule(match_count=3, last_match_at="2027-01-15T09:58:00Z", rate_limit_per_min=5, rate_limit_window=60, qos_level=0, priority=0)
        self.assertEqual(r.meta_line(busy, now), "3 matches · last 2 min ago · At most 5 messages per minute · Try once · Critical")
        self.assertEqual(r.rate_limit_text(2, 30), "At most 2 messages per 30 seconds")
        self.assertIsNone(r.rate_limit_text(5, 0))
        self.assertEqual(r.matches_text(rule(match_count=1)), "1 match")

    def test_the_filter_summary(self):
        packed = rule(filters=json.dumps({"keyword": "SOS", "channels": "[0,1]", "nodes": ["!a1b3c2ec"], "portnums": "[]"}), filter_node_group="north", filter_sender_group="crew",
                      filter_portnum_group="texts")
        self.assertEqual(r.filter_summary(packed), "Contains “SOS” · Mesh channels 0, 1 · From nodes !a1b3c2ec · Node group north · Sender group crew · Message type group texts")
        self.assertEqual(r.filter_summary(rule()), "")
        self.assertEqual(r.filter_summary(rule(filters="not json")), "")

    def test_the_names_and_the_switch(self):
        self.assertEqual(r.name_of(rule(name="")), "Rule 3")
        self.assertEqual(r.switch_name(rule()), "Rule SOS to satellite is on")
        self.assertEqual(r.switch_name(rule(enabled=False)), "Rule SOS to satellite is off")

    def test_what_deleting_changes(self):
        self.assertEqual(r.delete_consequence(rule()), "Messages that matched it will no longer be forwarded to Satellite.")
        self.assertEqual(r.delete_consequence(rule(forward_to="")), "Messages that matched it will no longer be forwarded.")
        self.assertEqual(r.delete_consequence(rule(action="drop")), "Messages it stopped can get through again, if another rule passes them on.")
        self.assertEqual(r.delete_consequence(rule(action="log")), "Its matches will no longer be counted. Messages are not affected.")
        dialog = r.delete_dialog(rule())
        self.assertEqual(dialog["body"], "Messages that matched it will no longer be forwarded to Satellite. You cannot undo this.")
        self.assertEqual((dialog["ok"], dialog["cancel"]), ("Delete", "Keep it"))


class EditorTest(unittest.TestCase):
    def test_the_keyword_is_merged_into_the_other_filters(self):
        self.assertEqual(r.merge_keyword_filter(None, ""), "{}")
        self.assertEqual(r.merge_keyword_filter("", "SOS"), '{"keyword":"SOS"}')
        self.assertEqual(r.merge_keyword_filter('{"channels":"[0]","keyword":"old"}', "new"), '{"channels":"[0]","keyword":"new"}')
        self.assertEqual(r.merge_keyword_filter('{"channels":"[0]","keyword":"old"}', ""), '{"channels":"[0]"}')
        self.assertEqual(r.merge_keyword_filter("garbage", ""), "garbage")
        self.assertEqual(r.merge_keyword_filter("garbage", "x"), '{"keyword":"x"}')

    def test_the_hidden_settings_are_named(self):
        self.assertEqual(r.hidden_settings(None), [])
        self.assertEqual(r.hidden_settings(rule()), [])
        packed = rule(filters='{"channels":"[0]","nodes":"[]","portnums":"[1]"}', filter_portnum_group="g", forward_options='{"ttl_seconds":600}')
        self.assertEqual(r.hidden_settings(packed), ["mesh channels", "message types", "a message type group", "forwarding options"])
        self.assertEqual(r.hidden_settings(rule(filters="garbage")), ["filters this screen cannot read"])
        self.assertEqual(r.hidden_note(["mesh channels", "forwarding options"]), "This rule also has settings this screen does not show (mesh channels, forwarding options). Saving keeps them.")

    def test_the_defaults_follow_the_tab(self):
        self.assertEqual(r.defaults_for_tab("From mesh"), ("mesh_0", "iridium_0"))
        self.assertEqual(r.defaults_for_tab("Into mesh"), ("iridium_0", "mesh_0"))
        self.assertEqual(r.defaults_for_tab("Between links"), ("iridium_0", "sms_0"))
        fields = r.editor_fields(None, "Into mesh")
        self.assertEqual((fields["interface_id"], fields["forward_to"], fields["action"], fields["enabled"], fields["qos_level"], fields["priority"]), ("iridium_0", "mesh_0", "forward", True, 1, "10"))
        fields = r.editor_fields(rule(filters='{"keyword":"SOS"}', qos_level=0, priority=0, rate_limit_per_min=5, rate_limit_window=60), "From mesh")
        self.assertEqual((fields["keyword"], fields["qos_level"], fields["priority"], fields["rate_limit_per_min"], fields["rate_limit_window"]), ("SOS", 0, "0", "5", "60"))

    def test_the_checks_before_a_save(self):
        fields = r.editor_fields(None, "From mesh")
        fields["name"] = "  "
        self.assertEqual(r.errors(fields), (r.NAME_ERROR, None))
        fields["name"] = "x"
        fields["forward_to"] = "mesh_0"
        self.assertEqual(r.errors(fields), (None, r.TARGET_ERROR))
        fields["action"] = "drop"
        self.assertEqual(r.errors(fields), (None, None))

    def test_the_helpers(self):
        self.assertEqual(r.urgency_helper("0"), "Critical. Lower numbers go first and are checked first; 0 never expires.")
        self.assertEqual(r.urgency_helper("x"), "Low. Lower numbers go first and are checked first; 0 never expires.")
        self.assertEqual(r.limit_helper("5", "60"), "At most 5 messages per minute. Leave either box at 0 for no limit.")
        self.assertEqual(r.limit_helper("0", "60"), r.NO_LIMIT)
        self.assertEqual(r.interface_label(rule(direction="egress")), "When a message leaves by")
        self.assertEqual(r.interface_label(None), "When a message arrives by")

    def test_a_new_rule_is_androids_record(self):
        fields = r.editor_fields(None, "From mesh")
        fields.update(name=" e2e rule ", interface_id="iridium_0", forward_to="hub_0", priority="0", qos_level=0, rate_limit_per_min="5", rate_limit_window="60", keyword="SOS")
        self.assertEqual(r.save_body(None, fields), {
            "interface_id": "iridium_0", "direction": "ingress", "priority": 0, "name": "e2e rule", "enabled": True, "action": "forward", "forward_to": "hub_0",
            "filters": '{"keyword":"SOS"}', "filter_node_group": None, "filter_sender_group": None, "filter_portnum_group": None, "schedule_type": "none", "schedule_config": "",
            "forward_options": "{}", "qos_level": 0, "rate_limit_per_min": 5, "rate_limit_window": 60})

    def test_a_saved_rule_keeps_every_column_the_editor_does_not_show(self):
        old = rule(filters='{"channels":"[0]","keyword":"old"}', filter_portnum_group="texts", forward_options='{"ttl_seconds":600,"to":"+31612345678"}', direction="egress",
                   schedule_type="window", schedule_config='{"from":"08:00"}', match_count=9)
        fields = r.editor_fields(old, "From mesh")
        fields["name"] = "renamed"
        fields["action"] = "drop"
        body = r.save_body(old, fields)
        self.assertEqual(body["filters"], '{"channels":"[0]","keyword":"old"}')
        self.assertEqual(body["filter_portnum_group"], "texts")
        self.assertEqual(body["forward_options"], '{"ttl_seconds":600,"to":"+31612345678"}')
        self.assertEqual(body["direction"], "egress")
        self.assertEqual((body["schedule_type"], body["schedule_config"]), ("window", '{"from":"08:00"}'))
        self.assertEqual((body["name"], body["action"], body["forward_to"]), ("renamed", "drop", ""))
        self.assertNotIn("match_count", body)
        self.assertNotIn("id", body)


if __name__ == "__main__":
    unittest.main()
