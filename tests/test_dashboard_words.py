# SPDX-License-Identifier: GPL-3.0-or-later
"""Home's cards and the node banner (model/dashboard.py): Android's NodeLinkBannerTextTest ported,
and the rules written from DashboardScreen.kt, CheckMailboxButton.kt and HomeLanes.kt."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import dashboard as d  # noqa: E402

NOW = 1_790_000_000


class ArrangeTest(unittest.TestCase):
    def test_home_order(self):
        default = ["sos", "queue", "location", "signals", "mailbox", "activity"]
        self.assertEqual(d.home_order(""), default)
        self.assertEqual(d.home_order(d.OLD_DEFAULT), default)
        self.assertEqual(d.home_order("reticulum"), default)
        self.assertEqual(d.home_order("activity,burst,sos"), ["activity", "sos", "queue", "location", "signals", "mailbox"])
        self.assertEqual(d.home_order("signals, signals ,mailbox"), ["signals", "mailbox", "sos", "queue", "location", "activity"])

    def test_moving_stops_at_the_ends(self):
        order = list(d.HOME_CARDS)
        self.assertEqual(d.moved(order, 0, up=True), order)
        self.assertEqual(d.moved(order, 5, up=False), order)
        self.assertEqual(d.moved(order, 5, up=True)[4:], ["activity", "mailbox"])


class MailboxTest(unittest.TestCase):
    def test_every_outcome(self):
        cases = [({"kind": "not_connected"}, "The modem is not connected."),
                 ({"kind": "held", "seconds": 42}, "Held after a failed session: try again in 42 s."),
                 ({"kind": "session_failed", "mo_status": 32}, "No network: the modem sees no satellite. No credit used."),
                 ({"kind": "session_failed", "mo_status": 18}, "The session failed (status 18)."),
                 ({"kind": "no_answer"}, "The modem did not answer."),
                 ({"kind": "link_lost"}, "The link to the node dropped during the session; what it fetched is unknown."),
                 ({"kind": "checked", "received": 0, "still_queued": 0}, "No new messages."),
                 ({"kind": "checked", "received": 1, "still_queued": 0}, "1 message received."),
                 ({"kind": "checked", "received": 3, "still_queued": 2}, "3 messages received. 2 more waiting."),
                 ({"kind": "checked", "received": 0, "still_queued": 4}, "No new messages. 4 more waiting.")]
        for result, words in cases:
            self.assertEqual(d.mailbox_text(result), words, result)
        self.assertIsNone(d.mailbox_text(None))


class PositionTest(unittest.TestCase):
    def test_fix_age(self):
        self.assertEqual([d.fix_age(s) for s in (0, 4, 5, 59, 60, 125)], ["just now", "just now", "5 s ago", "59 s ago", "1 min ago", "2 min ago"])

    def test_lines(self):
        fix = {"latitude": 52.1620671, "longitude": 4.5097404, "accuracy": 12.7, "at": NOW}
        self.assertEqual(d.position_lines(fix, NOW), ["52.16207, 4.50974", "within 12 m, just now"])
        moving = dict(fix, altitude=3.9, speed=1.5, heading=271.8)
        self.assertEqual(d.position_lines(moving, NOW)[2], "Height 3 m. moving 5.4 km/h, heading 271°.")
        self.assertEqual(d.position_lines(dict(fix, altitude=-2.5, speed=0.4), NOW)[2], "Height -2 m.")
        self.assertEqual(d.position_lines(None, NOW), [d.WAITING_FOR_FIX])

    def test_half_up_as_kotlin(self):
        self.assertEqual(d.half_up(0.125, 2), "0.13")
        self.assertEqual(d.half_up(-0.125, 2), "-0.13")


class QueueTest(unittest.TestCase):
    def test_counts(self):
        stats = [{"channel": "iridium_0", "status": "queued", "count": 2}, {"channel": "iridium_0", "status": "retry", "count": 1},
                 {"channel": "mesh_0", "status": "sending", "count": 1}, {"channel": "cellular_0", "status": "failed", "count": 3},
                 {"channel": "mesh_0", "status": "dead", "count": 4}, {"channel": "cellular_0", "status": "held", "count": 1}]
        got = d.queue_counts(stats)
        self.assertEqual([(l, n) for l, n, _ in got["lanes"]], [("Satellite", 3), ("Mesh", 1), ("SMS", 1)])
        self.assertAlmostEqual(got["lanes"][0][2], 0.15)
        self.assertEqual([(l, n) for l, n, _ in got["badges"]], [("Waiting", 4), ("Sending", 1), ("Failed", 3), ("Gave up", 4)])
        self.assertEqual(d.queue_counts([])["lanes"][0][2], 0.0)
        # The Bridge answers null for an empty queue: nothing waits.
        self.assertEqual([n for _, n, _ in d.queue_counts(None)["badges"]], [0, 0, 0, 0])
        self.assertEqual(d.lane_depth(stats, "satellite"), 3)


class ChartTest(unittest.TestCase):
    def test_buckets_and_labels(self):
        t0 = 1_800_000 * 1000
        records = [{"timestamp": t0, "value": -80}, {"timestamp": t0 + 600_000, "value": -84}, {"timestamp": t0 + 2_400_000, "value": -90}]
        self.assertEqual(d.chart_points(records), [-82.0, -90.0])
        self.assertEqual(d.chart_summary(records), {"latest": "-90 dBm", "min": "min: -90 dBm", "avg": "avg: -86 dBm", "max": "max: -82 dBm"})
        self.assertIsNone(d.chart_summary([]))


class PassLineTest(unittest.TestCase):
    def test_pass_line(self):
        self.assertEqual(d.pass_line([{"aos": NOW - 100, "los": NOW + 300, "peak_elev_deg": 55, "is_active": True}], NOW), "A satellite is high overhead now.")
        passes = [{"aos": NOW - 100, "los": NOW + 300, "peak_elev_deg": 35, "is_active": True}, {"aos": NOW + 725, "los": NOW + 1300, "peak_elev_deg": 62}]
        self.assertEqual(d.pass_line(passes, NOW), "Next high pass in 12 min.")
        self.assertEqual(d.pass_line([{"aos": NOW + 3900, "los": NOW + 4500, "peak_elev_deg": 45}], NOW), "Next high pass in 1 h 5 min.")
        self.assertIsNone(d.pass_line([{"aos": NOW + 900, "los": NOW + 1500, "peak_elev_deg": 30}], NOW))
        self.assertEqual(d.queue_prefix(2), "2 messages waiting to go out. ")
        self.assertEqual(d.queue_prefix(0), "")


class NodeLinkBannerTextTest(unittest.TestCase):
    """NodeLinkBannerTextTest.kt, case for case."""

    def test_bluetooth_off_is_said_first(self):
        text = d.node_link_banner_text(True, False, "02:27", 1)
        self.assertTrue(text.startswith("Bluetooth is off since 02:27 (1 min)"))
        self.assertTrue(text.endswith("Tap to switch it on."))
        self.assertNotIn("Cannot reach", text)

    def test_with_bluetooth_on_it_says_which_link_is_down(self):
        self.assertEqual(d.node_link_banner_text(False, False, "02:27", 0),
                         "Cannot reach your MeshSat node since 02:27. Nothing goes out by mesh or satellite. Tap to see.")
        self.assertTrue(d.node_link_banner_text(False, True, "02:27", 3).startswith("Cannot reach the node's modem since 02:27 (3 min)."))

    def test_no_time_yet_no_since(self):
        self.assertEqual(d.node_link_banner_text(False, False, None, 0), "Cannot reach your MeshSat node. Nothing goes out by mesh or satellite. Tap to see.")


class ChecklistTest(unittest.TestCase):
    def test_count_and_shown(self):
        steps = [("a", "", True), ("b", "", False)]
        self.assertEqual(d.checklist_count(steps), "1 of 2 done")
        self.assertTrue(d.checklist_shown(steps, False))
        self.assertFalse(d.checklist_shown(steps, True))
        self.assertFalse(d.checklist_shown([("a", "", True)], False))
        self.assertEqual(d.recent_text("a\nb" + "x" * 100), ("a b" + "x" * 100)[:80])



class RecentTest(unittest.TestCase):
    def test_twenty_newest_of_every_transport(self):
        mesh = [{"portnum_name": "TEXT_MESSAGE_APP", "decoded_text": f"m{i}", "rx_time": NOW - i * 60, "transport": "mesh"} for i in range(15)]
        mesh.append({"portnum_name": "POSITION_APP", "decoded_text": "", "rx_time": NOW})
        mesh.append({"portnum_name": "TEXT_MESSAGE_APP", "decoded_text": "local sms", "rx_time": NOW, "transport": "sms", "local": True})
        sms = [{"decoded_text": f"s{i}", "rx_time": NOW - 30 - i * 60, "transport": "sms", "direction": "rx"} for i in range(10)]
        out = d.recent(mesh, sms)
        self.assertEqual(len(out), 20)
        self.assertEqual([m["decoded_text"] for m in out[:4]], ["m0", "s0", "m1", "s1"])
        self.assertNotIn("local sms", [m["decoded_text"] for m in out], "SMS come from the SIM's store, once")

    def test_colours_and_text(self):
        self.assertEqual([d.recent_lane(t) for t in ("mesh", "iridium", "sms", "mqtt", None)], ["mesh", "satellite", "sms", None, "mesh"])
        self.assertEqual(d.recent_text("a\nb" + "x" * 100), "a b" + "x" * 77)


if __name__ == "__main__":
    unittest.main()
