# SPDX-License-Identifier: GPL-3.0-or-later
"""The SOS and the alarm test against the scripted Bridge: what goes out on which route, and
what the record says afterwards."""
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request

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


def poll_sos(fake, flow, s) -> dict:
    """The app's poll of GET /api/sos/status, then the flow follows it."""
    with urllib.request.urlopen(fake.url + "/api/sos/status", timeout=5) as answer:
        s.sos = json.loads(answer.read())
    flow._followed = 0.0
    flow.follow(s)
    return s.sos


def deliver(fake, flow, s, key: str, status: str = "sent", cancel: bool = False, **more) -> None:
    """The Bridge's queue moves a leg on; the next poll reads it."""
    route = flow.run.route(key)
    assert wait(lambda: (route.cancel_ref if cancel else route.ref) is not None), f"{key} has no delivery"
    fake.control("POST", "/__fake__/delivery", dict({"ref": route.cancel_ref if cancel else route.ref, "status": status}, **more))
    flow._followed = 0.0
    flow.follow(s)


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

    def test_an_sos_starts_the_bridge_legs_with_the_words_and_texts_the_contacts(self):
        s = state(bridge=CONNECTED, cellular=SIM, contacts=[{"name": "Anna", "phone": "+31600000000"}], sos_name="Kyriakos")
        run = self.flow.start(s, test=False, trigger="hold")
        self.assertFalse(run.test)
        self.assertEqual([r.key for r in run.routes], ["mesh", "sms:+31600000000"])
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))
        activate = next(r for r in self.fake.requests if r["path"] == "/api/sos/activate")
        self.assertEqual(activate["body"]["trigger"], "hold")
        self.assertEqual(activate["body"]["routes"], ["mesh"], "the Bridge is asked for the routes this run planned")
        self.assertNotIn("latitude", activate["body"], "no position to give")
        self.assertTrue(activate["body"]["message"].startswith("SOS: Kyriakos needs help. Position unknown."))
        self.assertTrue(wait(lambda: any(s_.get("gateway") == "cellular" for s_ in self.fake.sent)))
        sms = next(s_ for s_ in self.fake.sent if s_.get("gateway") == "cellular")
        self.assertEqual(sms["to"], "+31600000000")
        self.assertTrue(sms["text"].startswith("SOS: Kyriakos needs help."))
        self.assertIs(sms.get("plain"), True, "an SOS text must go out as its words, never sealed (MESHSAT-1424)")
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").state == sosrun.WAITING))
        deliver(self.fake, self.flow, s, "sms:+31600000000", "sent")
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").state == sosrun.SENT))
        deliver(self.fake, self.flow, s, "sms:+31600000000", "sent", ack_status="acked")
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").detail == "Delivered to their phone"))
        # The mesh leg waits in the Bridge's queue, then goes: the app reads it from the Bridge's legs.
        poll_sos(self.fake, self.flow, s)
        self.assertEqual((self.flow.run.route("mesh").state, self.flow.run.route("mesh").detail), (sosrun.WAITING, "Waiting to send"))
        self.assertTrue(self.flow.run.route("mesh").ref.endswith("-mesh"))
        deliver(self.fake, self.flow, s, "mesh", "sent")
        poll_sos(self.fake, self.flow, s)
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
        wait(lambda: self.flow.run.route("sms:+31600000000").state == sosrun.WAITING)
        deliver(self.fake, self.flow, s, "sms:+31600000000", "sent")
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").state == sosrun.SENT))
        poll_sos(self.fake, self.flow, s)
        deliver(self.fake, self.flow, s, "mesh", "sent")
        poll_sos(self.fake, self.flow, s)
        self.assertEqual(self.flow.run.route("mesh").state, sosrun.SENT)
        self.flow.cancel(s)
        self.assertIsNotNone(self.flow.run.cancelled_at)
        self.assertFalse(self.flow.run.active)
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/cancel" for r in self.fake.requests)))
        cancel = next(r for r in self.fake.requests if r["path"] == "/api/sos/cancel")
        self.assertEqual(cancel["body"], {"message": "Alarm cancelled: Kyriakos is safe and needs no help now."})
        self.assertTrue(wait(lambda: any("Alarm cancelled: Kyriakos is safe" in s_.get("text", "") and s_.get("gateway") == "cellular" and s_.get("plain") is True for s_ in self.fake.sent)))
        # The Bridge tells the mesh (its mesh leg went out): a leg of its own, which the app follows.
        self.assertTrue(wait(lambda: self.flow.run.route("mesh").cancel == sosrun.WAITING))
        self.assertTrue(self.flow.run.route("mesh").cancel_ref.endswith("-cancel:mesh"))
        self.assertFalse(any("Alarm cancelled" in s_.get("text", "") and "gateway" not in s_ for s_ in self.fake.sent), "the app told the mesh as well")
        deliver(self.fake, self.flow, s, "mesh", "sent", cancel=True)
        self.assertTrue(wait(lambda: self.flow.run.route("mesh").cancel == sosrun.SENT))
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").cancel == sosrun.WAITING))
        deliver(self.fake, self.flow, s, "sms:+31600000000", "sent", cancel=True)
        self.assertTrue(wait(lambda: self.flow.run.route("sms:+31600000000").cancel == sosrun.SENT))

    def test_an_sos_takes_every_route_set_up_and_a_leg_waits_for_its_link(self):
        # MESHSAT-1446: a modem this phone has had (not connected now) and the Hub (its link down)
        # are routes too; their legs wait at the Bridge and go when the link is back.
        self.prefs.set(last_modem_imei="300434065000000")
        self.fake.control("POST", "/__fake__/set", {"key": "GET /api/iridium/modem", "body": {"connected": False}})
        now = time.time()
        s = state(bridge=CONNECTED, modem={"connected": False, "port": "", "imei": ""}, hub={"url": "mqtts://hub", "link": "down"}, sos_name="Kyriakos",
                  phone=(52.1601, 4.497, 8.0, now))
        run = self.flow.start(s, test=False, trigger="hold")
        self.assertEqual([r.key for r in run.routes], ["sat", "mesh", "hub"])
        self.assertEqual(run.skipped, ["SMS: this device cannot send SMS."])
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))
        activate = next(r for r in self.fake.requests if r["path"] == "/api/sos/activate")["body"]
        self.assertEqual(activate["routes"], ["satellite", "mesh", "hub"])
        self.assertEqual((activate["latitude"], activate["longitude"]), (52.1601, 4.497))
        poll_sos(self.fake, self.flow, s)
        self.assertEqual([(r.key, r.state, r.detail) for r in self.flow.run.routes],
                         [("sat", sosrun.WAITING, "Waiting to send"), ("mesh", sosrun.WAITING, "Waiting to send"),
                          ("hub", sosrun.WAITING, "Waiting for the Hub connection")])
        self.assertIsNone(self.flow.run.route("sat").ref, "no delivery before the modem is there")
        # The modem comes back and its frame goes, the Hub confirms it; the Hub link comes back
        self.fake.control("POST", "/__fake__/sos", {"route": "satellite", "status": "sent", "ack_status": "acked", "interface": "iridium_0", "msg_ref": "sos-1-satellite"})
        self.fake.control("POST", "/__fake__/sos", {"route": "hub", "status": "sent", "sent_at": "2026-09-30T00:10:00Z"})
        poll_sos(self.fake, self.flow, s)
        self.assertEqual((self.flow.run.route("sat").state, self.flow.run.route("sat").detail), (sosrun.SENT, "Sent, and the Hub has it"))
        self.assertEqual(self.flow.run.route("sat").ref, "sos-1-satellite")
        self.assertEqual((self.flow.run.route("hub").state, self.flow.run.route("hub").detail), (sosrun.SENT, "Sent"))
        self.assertIn("Sent by satellite and the Hub online. Still trying mesh.", sosrun.summary(self.flow.run.routes))

    def test_a_route_the_bridge_does_not_carry_says_why(self):
        s = state(bridge=CONNECTED, hub={"url": "mqtts://hub"}, sos_name="Kyriakos")
        self.flow.start(s, test=False, trigger="hold")
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))
        self.fake.control("POST", "/__fake__/sos", {"drop": "hub", "skipped": ["Hub: not set up on this Bridge."]})
        poll_sos(self.fake, self.flow, s)
        self.assertEqual((self.flow.run.route("hub").state, self.flow.run.route("hub").detail), (sosrun.FAILED, "Not set up on this Bridge."))
        self.assertEqual(self.flow.run.route("mesh").state, sosrun.WAITING)

    def test_a_blank_name_takes_the_hub_callsign(self):
        s = state(bridge=CONNECTED, hub={"url": "", "callsign": "PA3XYZ"}, sos_name="")
        run = self.flow.start(s, test=False, trigger="hold")
        self.assertEqual(run.name, "PA3XYZ")
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))
        activate = next(r for r in self.fake.requests if r["path"] == "/api/sos/activate")["body"]
        self.assertTrue(activate["message"].startswith("SOS: PA3XYZ needs help."), activate["message"])

    def test_an_older_bridge_without_legs_is_still_followed(self):
        # A Bridge before MESHSAT-1447 counts its burst's sends and cancels only the burst: the
        # app marks the routes from the count and tells the mesh itself.
        s = state(bridge=CONNECTED, sos_name="Kyriakos")
        self.fake.control("POST", "/__fake__/set", {"key": "POST /api/sos/cancel", "status": 200, "body": {"status": "cancelled"}})
        # the next cases get the Bridge's own cancel again (a set answer outlives the reset)
        self.addCleanup(self.fake.control, "POST", "/__fake__/set", {"key": "POST /api/sos/cancel", "body": {}})
        self.flow.start(s, test=False, trigger="hold")
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/activate" for r in self.fake.requests)))
        s.sos = {"active": True, "sends": 1}
        self.flow.follow(s)
        self.assertEqual(self.flow.run.route("mesh").state, sosrun.SENT)
        self.flow.cancel(s)
        self.assertTrue(wait(lambda: any("Alarm cancelled" in s_.get("text", "") and "gateway" not in s_ for s_ in self.fake.sent)), "no cancellation on the mesh")
        self.assertTrue(wait(lambda: self.flow.run.route("mesh").cancel == sosrun.SENT))

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
        self.assertTrue(all(s_.get("plain") is True for s_ in self.fake.sent if s_.get("gateway") == "cellular"))
        self.assertFalse(any(r["path"] == "/api/sos/activate" for r in self.fake.requests), "a test started a real SOS")
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/test" for r in self.fake.requests)))
        self.assertTrue(self.flow.run.active, "a test settled with its SMS leg still queued")
        deliver(self.fake, self.flow, s, "sms:+31600000000", "sent")
        self.assertTrue(wait(lambda: self.flow.run is not None and not self.flow.run.active), "the test never settled")
        self.assertEqual([r.state for r in self.flow.run.routes], [sosrun.SENT] * 3)
        self.assertEqual(sosrun.summary(self.flow.run.routes), "Sent by mesh, SMS to Anna and the Hub online.")

    def test_a_test_with_a_fix_sends_a_position_report_by_satellite(self):
        # MESHSAT-1430: with a modem and the phone's fix, the satellite leg is Android's position
        # report, queued by the Bridge and followed to the Hub's receipt; the text does not go too.
        self.fake.control("POST", "/__fake__/set", {"key": "GET /api/iridium/modem", "body": {"connected": True}})
        self.fake.control("POST", "/__fake__/set", {"key": "POST /api/sos/test", "body": {"status": "sent"}})
        now = time.time()
        s = state(bridge=CONNECTED, modem={"connected": True}, phone=(52.1601, 4.497, 8.0, now), sos_name="Kyriakos",
                  fix={"latitude": 52.1601, "longitude": 4.497, "accuracy": 8.0, "altitude": 3.9, "speed": None, "heading": None, "at": now})
        run = self.flow.start(s, test=True, trigger="hold")
        self.assertIn("sat", [r.key for r in run.routes])
        self.assertTrue(wait(lambda: any(r["path"] == "/api/sos/test" and (r["body"] or {}).get("satellite") for r in self.fake.requests)))
        report = next(r["body"] for r in self.fake.requests if r["path"] == "/api/sos/test" and (r["body"] or {}).get("satellite"))
        self.assertEqual(report, {"satellite": True, "latitude": 52.1601, "longitude": 4.497, "altitude": 3.9})
        self.assertFalse(any(s_.get("gateway") == "iridium" and "text" in s_ for s_ in self.fake.sent), "the test text went by satellite as well")
        self.assertTrue(wait(lambda: self.flow.run.route("sat").state == sosrun.WAITING))
        self.assertTrue(wait(lambda: self.flow.run.route("mesh").state == sosrun.SENT))
        self.assertTrue(self.flow.run.active, "a test settled with its satellite leg still queued")
        deliver(self.fake, self.flow, s, "sat", "sent", ack_status="acked")
        self.assertTrue(wait(lambda: self.flow.run.route("sat").detail == "Sent, and the Hub has it"))
        self.assertTrue(wait(lambda: not self.flow.run.active), "the test never settled")

    def test_a_test_without_a_fix_sends_the_text_by_satellite(self):
        s = state(bridge=CONNECTED, modem={"connected": True}, sos_name="Kyriakos")
        self.flow.start(s, test=True, trigger="hold")
        self.assertTrue(wait(lambda: any(s_.get("gateway") == "iridium" for s_ in self.fake.sent)))
        self.assertEqual(next(s_ for s_ in self.fake.sent if s_.get("gateway") == "iridium")["text"],
                         "Test from Kyriakos: checking the MeshSat alarm routes. No help needed.")
        self.assertFalse(any((r["body"] or {}).get("satellite") for r in self.fake.requests if r["path"] == "/api/sos/test"))

    def test_a_position_report_the_bridge_cannot_queue_says_so(self):
        # The scripted Bridge has no modem: 503, as the Bridge without an Iridium gateway.
        self.fake.control("POST", "/__fake__/set", {"key": "GET /api/iridium/modem", "body": {"connected": False}})
        self.fake.control("POST", "/__fake__/set", {"key": "POST /api/sos/test", "body": {"status": "sent"}})
        s = state(bridge=CONNECTED, modem={"connected": True}, phone=(52.1601, 4.497, 8.0, time.time()), sos_name="")
        self.flow.start(s, test=True, trigger="hold")
        self.assertTrue(wait(lambda: self.flow.run.route("sat").state == sosrun.FAILED))
        self.assertEqual(self.flow.run.route("sat").detail, sosrun.NOT_QUEUED)

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
