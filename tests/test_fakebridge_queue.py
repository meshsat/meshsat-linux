# SPDX-License-Identifier: GPL-3.0-or-later
"""The scripted Bridge's queue and rules behave as the Bridge's own handlers: what the app
relies on when the e2e cases run against it."""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakebridge import FakeBridge, load_scenario  # noqa: E402


def call(url: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"} if data else {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


class QueueAndRulesTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeBridge(load_scenario("queue-busy")).start()

    def tearDown(self):
        self.fake.stop()

    def test_cancel_and_retry_follow_the_bridges_rules(self):
        status, rows = call(self.fake.url, "GET", "/api/deliveries?limit=200")
        self.assertEqual(status, 200)
        self.assertEqual(len(rows), 10)
        self.assertEqual(call(self.fake.url, "POST", "/api/deliveries/1/cancel", {}), (200, {"status": "cancelled"}))
        self.assertEqual(call(self.fake.url, "POST", "/api/deliveries/1/cancel", {})[0], 500)  # already dead
        self.assertEqual(call(self.fake.url, "POST", "/api/deliveries/4/cancel", {})[0], 500)  # sending
        self.assertEqual(call(self.fake.url, "POST", "/api/deliveries/1/retry", {}), (200, {"status": "requeued"}))
        self.assertEqual(call(self.fake.url, "POST", "/api/deliveries/5/retry", {})[0], 500)  # sent
        row = next(d for d in call(self.fake.url, "GET", "/api/deliveries")[1] if d["id"] == 1)
        self.assertEqual((row["status"], row["last_error"]), ("queued", "cancelled"))

    def test_rules_are_created_replaced_switched_and_deleted(self):
        status, rules = call(self.fake.url, "GET", "/api/access-rules")
        self.assertEqual((status, len(rules)), (200, 3))
        status, made = call(self.fake.url, "POST", "/api/access-rules", {"interface_id": "mesh_0", "direction": "ingress", "action": "log", "name": "x"})
        self.assertEqual(status, 201)
        self.assertEqual((made["id"], made["qos_level"], made["match_count"]), (4, 1, 0))
        self.assertEqual(call(self.fake.url, "POST", "/api/access-rules", {"direction": "ingress", "action": "log"})[0], 400)
        status, saved = call(self.fake.url, "PUT", "/api/access-rules/4", {"interface_id": "mesh_0", "direction": "ingress", "action": "drop", "name": "y", "forward_options": "{}"})
        self.assertEqual((status, saved["name"], saved["action"], saved["id"]), (200, "y", "drop", 4))
        self.assertEqual(call(self.fake.url, "POST", "/api/access-rules/4/disable", {}), (200, {"status": "disabled"}))
        self.assertFalse(next(r for r in call(self.fake.url, "GET", "/api/access-rules")[1] if r["id"] == 4)["enabled"])
        self.assertEqual(call(self.fake.url, "DELETE", "/api/access-rules/4"), (204, None))
        self.assertEqual(len(call(self.fake.url, "GET", "/api/access-rules")[1]), 3)

    def test_a_link_switched_off_stays_off_in_the_list(self):
        self.assertEqual(call(self.fake.url, "POST", "/api/interfaces/mesh_0/disable", {}), (200, {"status": "disabled"}))
        mesh = next(i for i in call(self.fake.url, "GET", "/api/interfaces")[1] if i["id"] == "mesh_0")
        self.assertFalse(mesh["enabled"])
        self.assertEqual(call(self.fake.url, "POST", "/api/interfaces/iridium_0/bind", {"device_id": "/dev/ttyUSB4"}), (200, {"status": "bound"}))
        self.assertEqual(call(self.fake.url, "POST", "/api/interfaces/iridium_0/bind", {})[0], 400)


if __name__ == "__main__":
    unittest.main()
