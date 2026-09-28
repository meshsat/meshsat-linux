# SPDX-License-Identifier: GPL-3.0-or-later
"""The SOS and the alarm test against the scripted Bridge: what goes out on which route, and
what the record says afterwards."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import fakebridge  # noqa: E402
from meshsat import api, sosflow, store  # noqa: E402
from meshsat.model import sosrun  # noqa: E402


def state(**fields) -> api.State:
    s = api.State()
    for key, value in fields.items():
        setattr(s, key, value)
    return s


CONNECTED = {"connected": True, "node_id": "!52cb81e7", "node_name": "meshsat-pinephone-pro"}
SIM = {"connected": True, "sim_state": "READY", "registration": "registered"}


def wait(predicate, seconds: float = 5.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class FlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = fakebridge.FakeBridge(fakebridge.load_scenario("mesh-only")).start()
        api.BRIDGE = cls.fake.url

    @classmethod
    def tearDownClass(cls):
        cls.fake.stop()

    def setUp(self):
        self.fake.control("POST", "/__fake__/reset", {})
        self.dir = tempfile.TemporaryDirectory()
        self.prefs = store.Prefs(os.path.join(self.dir.name, "app.json"))
        self.changes = 0

        def changed():
            self.changes += 1

        self.flow = sosflow.Flow(self.prefs, changed)

    def tearDown(self):
        self.dir.cleanup()

    def test_an_sos_starts_the_bridge_burst_with_the_words_and_texts_the_contacts(self):
        s = state(bridge=CONNECTED, cellular=SIM, contacts=[{"name": "Anna", "phone": "+31600000000"}], sos_name="Kyriakos")
        run = self.flow.start(s, test=False, trigger="hold")
        self.assertFalse(run.test)
        self.assertEqual([r.key for r in run.routes], ["mesh", "sms:+31600000000"])
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))
        activate = next(r for r in self.fake.requests if r["path"] == "/api/sos/activate")
        self.assertEqual(activate["body"]["trigger"], "hold")
        self.assertTrue(activate["body"]["message"].startswith("SOS: Kyriakos needs help. Position unknown."))
        self.assertTrue(wait(lambda: any(s_.get("gateway") == "cellular" for s_ in self.fake.sent)))
        sms = next(s_ for s_ in self.fake.sent if s_.get("gateway") == "cellular")
        self.assertEqual(sms["to"], "+31600000000")
        self.assertTrue(sms["text"].startswith("SOS: Kyriakos needs help."))
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").state == sosrun.SENT))
        # The Bridge's burst counts the sends: the mesh route is sent once the status says so.
        s.sos = {"active": True, "sends": 1}
        self.flow.follow(s)
        self.assertEqual(self.flow.run.route("mesh").state, sosrun.SENT)
        self.assertIn("Sent by mesh and SMS to Anna.", sosrun.summary(self.flow.run.routes))
        # Kept on disk for the banner and the result screen after a restart.
        self.prefs.flush()
        again = sosflow.Flow(store.Prefs(self.prefs.path))
        self.assertIsNotNone(again.run)
        self.assertEqual(again.run.route("mesh").state, sosrun.SENT)

    def test_cancelling_tells_the_bridge_and_every_route_that_carried_it(self):
        s = state(bridge=CONNECTED, cellular=SIM, contacts=[{"name": "Anna", "phone": "+31600000000"}], sos_name="Kyriakos")
        self.flow.start(s, test=False, trigger="hold")
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))
        wait(lambda: self.flow.run.route("sms:+31600000000").state == sosrun.SENT)
        s.sos = {"active": True, "sends": 1}
        self.flow.follow(s)
        self.flow.cancel(s)
        self.assertIsNotNone(self.flow.run.cancelled_at)
        self.assertFalse(self.flow.run.active)
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/cancel" for r in self.fake.requests)))
        self.assertTrue(wait(lambda: any("Alarm cancelled: Kyriakos is safe" in s_.get("text", "") and s_.get("gateway") == "cellular" for s_ in self.fake.sent)))
        self.assertTrue(wait(lambda: any("Alarm cancelled" in s_.get("text", "") and "gateway" not in s_ for s_ in self.fake.sent)), "no cancellation on the mesh")
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").cancel == sosrun.SENT))

    def test_a_test_goes_route_by_route_and_tells_the_hub(self):
        s = state(bridge=CONNECTED, cellular=SIM, contacts=[{"name": "Anna", "phone": "+31600000000"}], hub={"url": "mqtts://hub", "link": "connected"}, sos_name="Kyriakos")
        self.fake.control("POST", "/__fake__/set", {"key": "POST /api/sos/test", "body": {"status": "sent"}})
        run = self.flow.start(s, test=True, trigger="hold")
        self.assertTrue(run.test)
        self.assertEqual([r.key for r in run.routes], ["mesh", "sms:+31600000000", "hub"])
        self.assertTrue(wait(lambda: len(self.fake.sent) >= 2))
        texts = {s_.get("gateway", "mesh"): s_["text"] for s_ in self.fake.sent}
        self.assertEqual(texts["mesh"], "Test from Kyriakos: checking the MeshSat alarm routes. No help needed.")
        self.assertEqual(texts["cellular"], texts["mesh"])
        self.assertFalse(any(r["path"] == "/api/sos/activate" for r in self.fake.requests), "a test started a real SOS")
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/test" for r in self.fake.requests)))
        self.assertTrue(wait(lambda: self.flow.run is not None and not self.flow.run.active), "the test never settled")
        self.assertEqual([r.state for r in self.flow.run.routes], [sosrun.SENT] * 3)
        self.assertEqual(sosrun.summary(self.flow.run.routes), "Sent by mesh, SMS to Anna and the Hub online.")

    def test_a_test_waits_for_the_hub_and_can_be_stopped(self):
        s = state(bridge=CONNECTED, hub={"url": "mqtts://hub"}, sos_name="")
        self.fake.control("POST", "/__fake__/set", {"key": "POST /api/sos/test", "status": 503, "body": {"error": "the Hub is not connected"}})
        self.flow.start(s, test=True, trigger="hold")
        self.assertTrue(wait(lambda: self.flow.run.route("hub").state == sosrun.WAITING and self.flow.run.route("mesh").state == sosrun.SENT))
        self.assertTrue(self.flow.run.active)
        self.flow.cancel(s)
        self.assertFalse(self.flow.run.active)
        self.assertEqual(self.flow.run.route("hub").state, sosrun.STOPPED)
        self.assertFalse(any(r["path"] == "/api/sos/cancel" for r in self.fake.requests), "stopping a test cancelled at the Bridge")

    def test_a_real_sos_replaces_a_running_test(self):
        s = state(bridge=CONNECTED, hub={"url": "mqtts://hub"})
        self.fake.control("POST", "/__fake__/set", {"key": "POST /api/sos/test", "status": 503, "body": {"error": "no"}})
        test = self.flow.start(s, test=True, trigger="hold")
        real = self.flow.start(s, test=False, trigger="hold")
        self.assertIsNot(test, real)
        self.assertFalse(test.active)
        self.assertTrue(real.active and not real.test)
        self.assertIs(self.flow.start(s, test=True, trigger="hold"), real, "a test must not replace a real SOS")
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))


if __name__ == "__main__":
    unittest.main()
