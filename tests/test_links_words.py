# SPDX-License-Identifier: GPL-3.0-or-later
"""Links' words (model/links.py) against Android's InterfacesScreen.kt: the state of each link,
the questions and toasts, the capabilities, groups, backup links and health."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from meshsat.model import links as l  # noqa: E402, E741
from meshsat.model import words  # noqa: E402


def iface(**more) -> dict:
    out = {"id": "mesh_0", "channel_type": "mesh", "label": "Meshtastic LoRa", "enabled": True, "state": "online", "last_activity": "0001-01-01T00:00:00Z"}
    out.update(more)
    return out


class StateTest(unittest.TestCase):
    def test_the_bridges_states_read_as_androids(self):
        self.assertEqual(l.state_of(iface(state="online")), "online")
        self.assertEqual(l.state_of(iface(state="binding")), "connecting")
        self.assertEqual(l.state_of(iface(state="error")), "error")
        self.assertEqual(l.state_of(iface(state="offline")), "offline")
        self.assertEqual(l.state_of(iface(enabled=False, state="online")), "disabled")
        self.assertEqual([l.state_text(s) for s in ("online", "connecting", "offline", "error", "disabled")], ["Working", "Connecting", "Off", "Not working", "Switched off"])

    def test_a_link_the_bridge_does_not_bind_follows_the_lane(self):
        self.assertEqual(l.state_of(iface(state="unbound"), {"mesh": True}), "online")
        self.assertEqual(l.state_of(iface(state="unbound"), {"mesh": False}), "offline")
        self.assertEqual(l.state_of(iface(id="iridium_imt_0", state="unbound"), {"satellite": True}), "online")
        self.assertEqual(l.state_of(iface(id="sms_0", state="unbound"), None), "offline")

    def test_tones_and_badges(self):
        self.assertEqual([l.state_tone(s) for s in ("online", "connecting", "offline", "error", "disabled")], ["green", "amber", "muted", "red", "muted"])
        links = [iface(state="online"), iface(id="iridium_0", state="offline"), iface(id="sms_0", state="unbound")]
        scores = [{"interface_id": "mesh_0", "score": 70, "available": True}, {"interface_id": "sms_0", "score": 20, "available": True}, {"interface_id": "iridium_0", "score": 10, "available": False}]
        self.assertEqual(l.badges(links, scores, {"sms": True}), {"Links": 2, "Health": 1})

    def test_the_order_and_the_lines(self):
        ids = [i["id"] for i in l.sorted_interfaces([iface(id="sms_0"), iface(id="hub_0"), iface(id="iridium_0"), iface(id="mesh_0")])]
        self.assertEqual(ids, ["mesh_0", "iridium_0", "sms_0", "hub_0"])
        now = words.stamp_epoch("2027-01-15T10:00:00Z")
        self.assertEqual(l.times_line(iface(), now), "")
        self.assertEqual(l.times_line(iface(last_activity="2027-01-15T09:56:00Z"), now), "last message 4 min ago")
        self.assertEqual(l.times_line(iface(last_online="2027-01-15T09:00:00Z", last_activity="2027-01-15T09:56:00Z"), now), "Last working 1 h ago · last message 4 min ago")
        self.assertEqual(l.reconnect_line(iface(reconnect_attempts=3)), "Tried to reconnect 3 times")
        self.assertEqual(l.reconnect_line(iface()), "")
        self.assertTrue(l.can_reconnect("offline") and l.can_reconnect("error"))
        self.assertFalse(l.can_reconnect("online") or l.can_reconnect("disabled"))
        self.assertEqual(l.bind_target(iface(device_id="/dev/ttyUSB4")), "/dev/ttyUSB4")
        self.assertEqual(l.bind_target(iface()), "")

    def test_the_switch_off_question_and_the_toasts(self):
        mesh = l.switch_off_dialog("mesh_0")
        self.assertEqual(mesh["title"], "Switch off Mesh?")
        self.assertEqual(mesh["body"], "Messages stop going out by Mesh until you switch it back on. Messages waiting for it stay in the queue.")
        self.assertEqual((mesh["ok"], mesh["cancel"]), ("Switch off", "Keep it on"))
        # The Bridge keeps a switched-off modem connected: the satellite gets the sentence that is true of it.
        sat = l.switch_off_dialog("iridium_0")
        self.assertEqual(sat["body"], "Messages stop going out by Satellite until you switch it back on. Messages waiting for it stay in the queue.")
        self.assertEqual(l.switch_off_dialog("iridium_imt_0")["title"], "Switch off Satellite (RockBLOCK 9704)?")
        self.assertEqual(l.toast_on("mesh_0"), "Mesh switched on")
        self.assertEqual(l.toast_off("sms_0"), "SMS switched off")
        self.assertEqual(l.toast_reconnect("iridium_0"), "Trying to connect Satellite now")
        self.assertEqual(l.switch_name("hub_0"), "Use Hub")


class TabsTest(unittest.TestCase):
    def test_capabilities_in_androids_rows(self):
        self.assertEqual(l.capability_rows("mesh"), [("Largest message", "237 bytes"), ("Sends", "Yes"), ("Receives", "Yes"), ("Carries data, not only text", "Yes"), ("Cost", "Free")])
        self.assertEqual(l.capability_rows("mqtt")[0], ("Largest message", "No limit"))
        self.assertEqual(l.capability_rows("cellular")[3:], [("Carries data, not only text", "No"), ("Cost", "Paid")])
        self.assertEqual(l.capability_rows("nothing"), [])
        self.assertEqual(l.retries_text("iridium"), "Retries: waits for the next satellite pass, at most 10 times.")
        self.assertEqual(l.retries_text("cellular"), "Retries: first after 30 s, then up to 300 s apart, at most 3 times.")
        self.assertEqual(l.retries_text("mesh"), "")
        self.assertEqual(l.channel_label(iface(label="")), "Meshtastic LoRa")

    def test_groups_and_backup_links(self):
        self.assertEqual([l.group_type_label(t) for t in ("node_group", "sender_group", "portnum_group", "contact_group", "odd_thing")], ["Nodes", "Senders", "Message types", "Contacts", "Odd thing"])
        self.assertEqual(l.member_count('["a","b"]'), 2)
        self.assertEqual(l.member_count("garbage"), 0)
        self.assertEqual(l.member_count(["a"]), 1)
        self.assertEqual(l.group_title({"id": "g1", "label": ""}), "g1")
        self.assertEqual(l.failover_mode("failover"), "Uses the first link that works")
        self.assertEqual(l.failover_mode("broadcast"), "Sends on every link")
        self.assertEqual(l.failover_mode("weird"), "Weird")

    def test_health(self):
        self.assertEqual([l.score_tone(s) for s in (100, 80, 79, 50, 49, 1, 0)], ["green", "green", "amber", "amber", "red", "red", "muted"])
        self.assertEqual(l.speed_score(0), 0)
        self.assertEqual(l.speed_score(2500), 98)
        self.assertEqual(l.speed_score(500_000), 0)
        parts = l.score_parts({"signal": 40, "success_rate": 0.75, "latency_ms": 2500, "cost_score": 100})
        self.assertEqual(parts, [("Signal", 40), ("Got through", 75), ("Speed", 98), ("Low cost", 100)])

    def test_the_read_only_rules_tab(self):
        self.assertEqual(l.rule_line({"action": "forward", "interface_id": "mesh_0", "forward_to": "iridium_0"}), "Forward: Mesh to Satellite")
        self.assertEqual(l.rule_line({"action": "drop", "interface_id": "sms_0", "forward_to": ""}), "Drop: Messages from SMS")
        self.assertEqual(l.rule_line({"action": "log", "direction": "egress", "interface_id": "iridium_0"}), "Log only: Messages leaving by Satellite")


if __name__ == "__main__":
    unittest.main()
