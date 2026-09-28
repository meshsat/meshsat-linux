# SPDX-License-Identifier: GPL-3.0-or-later
"""The scripted Bridge answers as told, records what it is asked, and refuses what the scenario
did not give it."""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import fakebridge  # noqa: E402
from meshsat import api  # noqa: E402


def call(url: str, method: str = "GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


class FakeBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = fakebridge.FakeBridge(fakebridge.load_scenario("mesh-only")).start()

    @classmethod
    def tearDownClass(cls):
        cls.fake.stop()

    def setUp(self):
        self.fake.control("POST", "/__fake__/reset", {})

    def test_answers_the_scenario_and_records_the_request(self):
        status, body = call(self.fake.url + "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(body["connected"])
        self.assertEqual(self.fake.requests[-1]["path"], "/api/status")

    def test_an_unknown_path_is_404_and_counted(self):
        status, body = call(self.fake.url + "/api/nothing")
        self.assertEqual(status, 404)
        self.assertIn("scenario has no answer", body["error"])
        self.assertEqual(self.fake.unexpected[-1]["path"], "/api/nothing")

    def test_sos_reducer(self):
        self.assertFalse(call(self.fake.url + "/api/sos/status")[1]["active"])
        status, body = call(self.fake.url + "/api/sos/activate", "POST", {"message": "SOS: Kyriakos needs help.", "trigger": "hold"})
        self.assertEqual(status, 200)
        self.assertTrue(call(self.fake.url + "/api/sos/status")[1]["active"])
        self.assertEqual(self.fake.sos["message"], "SOS: Kyriakos needs help.")
        self.assertEqual(call(self.fake.url + "/api/sos/activate", "POST", {})[0], 409)
        call(self.fake.url + "/api/sos/cancel", "POST", {})
        self.assertFalse(call(self.fake.url + "/api/sos/status")[1]["active"])

    def test_a_sent_text_appears_in_the_packet_feed(self):
        status, body = call(self.fake.url + "/api/messages/send", "POST", {"text": "hi", "to": "!a1b3c2ec"})
        self.assertEqual(status, 200)
        feed = call(self.fake.url + "/api/packets?limit=200")[1]["packets"]
        self.assertEqual(feed[0]["text"], "hi")
        self.assertEqual(feed[0]["to"], "!a1b3c2ec")
        self.assertEqual(self.fake.sent[-1]["to"], "!a1b3c2ec")

    def test_orders_set_and_scenario(self):
        self.fake.control("POST", "/__fake__/set", {"key": "GET /api/iridium/signal", "body": {"bars": 5}})
        self.assertEqual(call(self.fake.url + "/api/iridium/signal")[1]["bars"], 5)
        self.fake.control("POST", "/__fake__/scenario", {"name": "satellite-3-bars"})
        self.assertEqual(call(self.fake.url + "/api/iridium/signal")[1]["bars"], 3)
        self.fake.control("POST", "/__fake__/set", {"key": "GET /api/status", "status": 503, "body": {"error": "mesh transport unavailable"}})
        self.assertEqual(call(self.fake.url + "/api/status")[0], 503)
        self.fake.control("POST", "/__fake__/scenario", {"name": "mesh-only"})

    def test_the_app_client_reads_it(self):
        api.BRIDGE = self.fake.url
        answer = api.request("GET", "/api/status")
        self.assertTrue(answer.ok)
        self.assertEqual(answer.body["node_id"], "!52cb81e7")
        missing = api.request("GET", "/api/nothing")
        self.assertEqual(missing.status, 404)
        self.assertFalse(missing.ok)
        self.assertFalse(missing.down)

    def test_down_means_no_answer_at_all(self):
        api.BRIDGE = self.fake.url
        self.fake.control("POST", "/__fake__/down", {"down": True})
        answer = api.request("GET", "/api/status", timeout=3)
        self.assertTrue(answer.down)
        self.fake.control("POST", "/__fake__/down", {"down": False})
        self.assertTrue(api.request("GET", "/api/status").ok)

    def test_poll_state_against_the_scenario(self):
        api.BRIDGE = self.fake.url
        s = api.State()
        api.poll_state(s, {}, api.NameAsker(lambda *_: {"status": "nodeinfo request sent"}))
        self.assertTrue(s.mesh_connected())
        self.assertEqual(len(s.others()), 1)
        self.assertEqual(s.others()[0]["long_name"], "MSPA")
        self.assertEqual(s.sms, [])
        self.fake.control("POST", "/__fake__/down", {"down": True})
        api.poll_state(s, {}, api.NameAsker(lambda *_: {}))
        self.assertIsNone(s.bridge)
        self.assertIsNone(s.modem)
        self.assertFalse(s.mesh_connected())
        self.fake.control("POST", "/__fake__/down", {"down": False})

    def test_a_bridge_that_asks_for_a_pause_is_not_down(self):
        """A 429 (the Bridge's per-address limit, found by the live tests of 0.7.0) keeps what
        the screens show: it used to read as "Bridge down" and blanked every lane."""
        api.BRIDGE = self.fake.url
        s = api.State()
        api.poll_state(s, {}, api.NameAsker(lambda *_: {}))
        self.assertTrue(s.mesh_connected())
        modem = s.modem
        self.fake.control("POST", "/__fake__/set", {"key": "GET /api/status", "status": 429, "body": {"error": "rate limit exceeded"}})
        api.poll_state(s, {}, api.NameAsker(lambda *_: {}))
        self.assertTrue(s.mesh_connected(), "a 429 on the status read as the Bridge down")
        self.assertEqual(s.modem, modem)
        self.fake.control("POST", "/__fake__/scenario", {"name": "mesh-only"})
        self.fake.control("POST", "/__fake__/set", {"key": "GET /api/deadman", "status": 429, "body": {"error": "rate limit exceeded"}})
        s.deadman = {"enabled": True, "timeout_min": 60, "triggered": False}
        api.poll_state(s, {}, api.NameAsker(lambda *_: {}))
        self.assertEqual(s.deadman, {"enabled": True, "timeout_min": 60, "triggered": False}, "a 429 blanked the check-in timer")
        self.fake.control("POST", "/__fake__/scenario", {"name": "mesh-only"})

    def test_every_scenario_builds(self):
        for name in ("fresh", "mesh-only", "one-node", "nameless-node", "satellite-3-bars", "sim-ready", "all-four", "hub-set-up", "sos-active", "bluetooth-pairing", "bluetooth-connected",
                     "queue-busy"):
            routes = fakebridge.load_scenario(name)
            self.assertIn("GET /api/status", routes, name)
        fake = fakebridge.FakeBridge(fakebridge.load_scenario("sos-active"))
        self.assertTrue(fake.sos["active"])
        fake = fakebridge.FakeBridge(fakebridge.load_scenario("fresh"))
        self.assertTrue(fake.down)


if __name__ == "__main__":
    unittest.main()
