# SPDX-License-Identifier: GPL-3.0-or-later
"""The names of mesh nodes: the cache that outlives the Bridge, and the asks for a node the
phone has no NodeInfo from. Runs without GTK: python3 -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import api  # noqa: E402

TDECK = {"user_id": "!a1b3c2ec", "num": 2712912620, "long_name": "", "short_name": "", "hw_model": 0, "last_heard": 1000}
ME = "!52cb81e7"


class NameCacheTest(unittest.TestCase):
    def test_a_name_heard_once_outlives_the_bridge(self):
        names = {}
        heard = [dict(TDECK, long_name="t-deck-pro-a", short_name="TDPA", hw_model=48, hw_model_name="T_DECK")]
        self.assertTrue(api.remember_names(heard, names, now=1000))
        self.assertFalse(api.remember_names(heard, names, now=1001), "the same name is not a change")
        after_restart = [dict(TDECK)]
        filled = api.name_nodes(after_restart, names)
        self.assertEqual(filled[0]["long_name"], "t-deck-pro-a")
        self.assertEqual(filled[0]["hw_model_name"], "T_DECK")
        self.assertTrue(filled[0]["name_cached"])
        self.assertFalse(api.remember_names(filled, names), "a name that came from the cache is not remembered as new")

    def test_a_renamed_node_is_remembered_again(self):
        names = {"!a1b3c2ec": {"num": 2712912620, "long_name": "old", "short_name": "OLD", "hw_model": 0, "hw_model_name": "", "seen": 1}}
        self.assertTrue(api.remember_names([dict(TDECK, long_name="new")], names))
        self.assertEqual(names["!a1b3c2ec"]["long_name"], "new")

    def test_the_bridge_name_wins_over_the_cache(self):
        names = {"!a1b3c2ec": {"num": 2712912620, "long_name": "old", "short_name": "OLD", "hw_model": 0, "hw_model_name": "", "seen": 1}}
        filled = api.name_nodes([dict(TDECK, long_name="t-deck-pro-a")], names)
        self.assertEqual(filled[0]["long_name"], "t-deck-pro-a")
        self.assertNotIn("name_cached", filled[0])


class NameAskerTest(unittest.TestCase):
    def test_cadence(self):
        calls = []
        asker = api.NameAsker(post_fn=lambda path, body: calls.append((path, body)) or {"status": "nodeinfo request sent"})
        # Heard at 1000: nothing before six minutes have passed, then the ask.
        self.assertEqual(asker.ask([TDECK], ME, 0, now=1359), [])
        self.assertEqual(asker.ask([TDECK], ME, 0, now=1360), [("!a1b3c2ec", "nodeinfo request sent")])
        self.assertEqual(calls, [("/api/nodes/request-info", {"node_num": 2712912620})])
        # Then once per twelve hours (the firmware answers a requester it has not heard for that long).
        late = 1360 + 12 * 3600
        self.assertEqual(asker.ask([dict(TDECK, last_heard=late - 100)], ME, 0, now=late - 1), [])
        self.assertEqual(len(asker.ask([dict(TDECK, last_heard=late - 100)], ME, 0, now=late)), 1)
        # Never within 30 s of this phone's own transmission.
        later = late + 12 * 3600
        self.assertEqual(asker.ask([dict(TDECK, last_heard=later - 100)], ME, later - 10, now=later), [])
        self.assertEqual(len(asker.ask([dict(TDECK, last_heard=later - 100)], ME, later - 31, now=later)), 1)
        self.assertEqual(len(asker.log), 3)

    def test_who_is_left_alone(self):
        asker = api.NameAsker(post_fn=lambda path, body: {"status": "nodeinfo request sent"})
        self.assertEqual(asker.ask([dict(TDECK, long_name="t-deck-pro-a")], ME, 0, now=5000), [], "a named node")
        self.assertEqual(asker.ask([dict(TDECK, short_name="TDPA")], ME, 0, now=5000), [], "a node with a short name")
        self.assertEqual(asker.ask([dict(TDECK, user_id=ME)], ME, 0, now=5000), [], "the phone itself")
        self.assertEqual(asker.ask([dict(TDECK, last_heard=100)], ME, 0, now=5000), [], "a node heard over an hour ago")
        self.assertEqual(asker.ask([dict(TDECK, num=0)], ME, 0, now=5000), [], "a node without a number")

    def test_a_node_that_keeps_talking_is_not_asked_again_soon(self):
        asker = api.NameAsker(post_fn=lambda path, body: {"status": "nodeinfo request sent"})
        self.assertEqual(len(asker.ask([TDECK], ME, 0, now=1360)), 1)
        t, asked = 1360, 0
        for _ in range(20):  # heard every six minutes for two hours: no further ask
            t += 360
            asked += len(asker.ask([dict(TDECK, last_heard=t - 10)], ME, 0, now=t))
        self.assertEqual(asked, 0)

    def test_an_error_is_logged_and_tried_again_soon(self):
        answers = [{"error": "request nodeinfo failed: not connected"}] * 2 + [{"status": "nodeinfo request sent"}] * 2
        asker = api.NameAsker(post_fn=lambda path, body: answers.pop(0))
        self.assertEqual(asker.ask([TDECK], ME, 0, now=1360), [("!a1b3c2ec", "request nodeinfo failed: not connected")])
        self.assertEqual(asker.log[-1]["outcome"], "request nodeinfo failed: not connected")
        # Tried again 30 s later, not six minutes later, and the failed try does not count.
        self.assertEqual(asker.ask([TDECK], ME, 0, now=1389), [])
        self.assertEqual(len(asker.ask([TDECK], ME, 0, now=1390)), 1)
        self.assertEqual(len(asker.ask([TDECK], ME, 0, now=1420)), 1)
        self.assertEqual(asker.seen["!a1b3c2ec"]["asked"], 1)
        self.assertEqual(asker.ask([TDECK], ME, 0, now=1450), [], "sent: back to the cadence")
        late = 1420 + 12 * 3600
        self.assertEqual(len(asker.ask([dict(TDECK, last_heard=late - 100)], ME, 0, now=late)), 1)

    def test_errors_do_not_retry_forever(self):
        asker = api.NameAsker(post_fn=lambda path, body: {"error": "mesh transport unavailable"})
        t, tries = 1360, 0
        for _ in range(12):
            tries += len(asker.ask([TDECK], ME, 0, now=t))
            t += 30
        self.assertEqual(tries, api.NameAsker.RETRIES + 1, "the retries, then one that counts as an ask")
        self.assertEqual(asker.seen["!a1b3c2ec"]["asked"], 1)


class RecentSendersTest(unittest.TestCase):
    def test_a_sender_the_bridge_forgot_is_a_candidate(self):
        messages = [{"direction": "rx", "transport": "radio", "from_node": "!a1b3c2ec", "rx_time": 5000, "decoded_text": "hi"},
                    {"direction": "rx", "transport": "radio", "from_node": "!a1b3c2ec", "rx_time": 4000, "decoded_text": "again"},
                    {"direction": "rx", "transport": "radio", "from_node": "!ffffffff", "rx_time": 5000},
                    {"direction": "rx", "transport": "radio", "from_node": "!8b04a69e", "rx_time": 5000},
                    {"direction": "rx", "transport": "radio", "from_node": "!00000001", "rx_time": 100},
                    {"direction": "rx", "transport": "sms", "from_node": "+31612345678", "rx_time": 5000},
                    {"direction": "tx", "transport": "radio", "from_node": ME, "rx_time": 5000}]
        nodes = [{"user_id": "!8b04a69e", "long_name": "MeshSat flaneur"}]
        got = api.recent_senders(messages, nodes, {}, now=5100)
        self.assertEqual(got, [{"user_id": "!a1b3c2ec", "num": 2712912620, "long_name": "", "short_name": "", "last_heard": 5000, "unlisted": True}])
        self.assertEqual(api.recent_senders(messages, nodes, {"!a1b3c2ec": {"long_name": "t-deck-pro-a"}}, now=5100), [], "a cached name is enough")

    def test_the_asker_takes_such_a_sender(self):
        asker = api.NameAsker(post_fn=lambda path, body: {"status": "nodeinfo request sent"})
        sender = api.recent_senders([{"direction": "rx", "transport": "radio", "from_node": "!a1b3c2ec", "rx_time": 1000}], [], {}, now=1400)
        self.assertEqual(asker.ask(sender, ME, 0, now=1400), [("!a1b3c2ec", "nodeinfo request sent")])


class LastTransmissionTest(unittest.TestCase):
    def test_feed_and_sent_log(self):
        # The feed's tx entry (13:33:42Z = 1790602422) is later than the logged mesh send; the SMS does not count.
        packets = [{"dir": "rx", "time": "2026-09-28T15:33:56.806558016+02:00"}, {"dir": "tx", "time": "2026-09-28T15:33:42+02:00"}]
        sent = [{"transport": "radio", "rx_time": 1790602000}, {"transport": "sms", "rx_time": 1790609999}]
        self.assertEqual(api.last_transmission(packets, sent), 1790602422)
        self.assertEqual(api.last_transmission([], sent), 1790602000)
        self.assertEqual(api.last_transmission([], []), 0.0)
        self.assertEqual(api.packet_time({"time": "junk"}), 0.0)


if __name__ == "__main__":
    unittest.main()
