# SPDX-License-Identifier: GPL-3.0-or-later
"""The words of an SOS, held up against sos/SosMessagesTest.kt and SosRunTest.kt."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import api, sos  # noqa: E402
from meshsat.model import home, sosrun  # noqa: E402


def state(**fields) -> api.State:
    s = api.State()
    for key, value in fields.items():
        setattr(s, key, value)
    return s


CONNECTED = {"connected": True, "node_id": "!52cb81e7", "node_name": "meshsat-pinephone-pro"}
SIM = {"connected": True, "sim_state": "READY", "registration": "registered"}


class SosMessagesTest(unittest.TestCase):
    def test_a_test_and_a_cancellation_never_raise_an_alarm_whatever_the_name(self):
        for name in ("flaneur", "Sosimos", "Emergency team", "MAYDAY", ""):
            self.assertFalse(sos.contains_alarm_word(sos.test_text(name)), name)
            self.assertFalse(sos.contains_alarm_word(sos.cancel_text(name)), name)

    def test_an_sos_does_raise_the_alarm_on_every_route(self):
        fix = (52.16207, 4.50974, "GPS", 8.0, 1000.0)
        self.assertTrue(sos.contains_alarm_word(sos.mesh_text("flaneur", fix)))
        self.assertTrue(sos.contains_alarm_word(sos.sms_text("flaneur", fix)))

    def test_coordinates_use_a_point(self):
        fix = (52.1620671, 4.5097402, "GPS", 12.4, 0.0)
        self.assertIn("mlat=52.16207&mlon=4.50974", sos.sms_text("flaneur", fix))

    def test_an_sms_with_the_longest_name_fits_one_part(self):
        fix = (-33.86882, -151.20929, "GPS", 12345.0, 0.0)
        text = sos.sms_text("A" * 40, fix, now=10 * 60)
        self.assertLessEqual(len(text), 160, text)
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in text))

    def test_an_old_fix_is_called_the_last_position(self):
        self.assertEqual(sos.where_text((52.0, 4.0, "GPS", None, 0.0), now=3 * 60), "Last position 52.00000, 4.00000 at 00:00 UTC.")
        self.assertEqual(sos.where_text(None), "Position unknown.")

    def test_the_name_is_short_and_clean(self):
        self.assertEqual(sos.clean_name("  Kyriakos\tP  "), "KyriakosP")  # control characters go, as Android's filter drops them
        self.assertEqual(sos.clean_name(""), "A MeshSat user")
        self.assertEqual(len(sos.clean_name("A" * 60)), 24)


class SosRunTest(unittest.TestCase):
    def test_the_plan_names_every_route_and_what_is_skipped(self):
        s = state(bridge=CONNECTED, cellular=SIM, contacts=[{"name": "Anna", "phone": "+31600000000"}], hub={"url": "mqtts://hub", "bridge_id": "x"})
        routes, skipped = sosrun.plan(s, test=False, contacts_reach=True)
        self.assertEqual([r.key for r in routes], ["mesh", "sms:+31600000000", "hub"])
        self.assertEqual([r.label for r in routes], ["Mesh, everyone in range", "SMS to Anna", "Hub, over the internet"])
        self.assertEqual(skipped, ["Satellite: no satellite modem has been connected to this phone yet."])

    def test_without_the_bridge_nothing_can_be_queued(self):
        routes, skipped = sosrun.plan(state(bridge=None), False, False)
        self.assertEqual(routes, [])
        self.assertIn("The Bridge is not running", skipped[0])

    def test_the_summary_says_what_went_and_what_is_still_trying(self):
        routes = [sosrun.Route("sat", "Satellite, to the Hub", sosrun.WAITING, "Trying again: no network"),
                  sosrun.Route("sms:+31600000000", "SMS to Anna", sosrun.SENT, "Sent"),
                  sosrun.Route("hub", sosrun.HUB_LABEL, sosrun.SENT, "Sent")]
        self.assertEqual(sosrun.summary(routes), "Sent by SMS to Anna and the Hub online. Still trying satellite.")
        self.assertEqual(sosrun.summary([]), "No way to send it: add emergency contacts or connect your node.")
        self.assertEqual(sosrun.summary([sosrun.Route("mesh", "Mesh", sosrun.FAILED, "Not sent")]), "Nothing could be sent.")

    def test_a_test_is_settled_only_when_every_route_is_done(self):
        routes = [sosrun.Route("mesh", "Mesh", sosrun.SENT), sosrun.Route("hub", sosrun.HUB_LABEL, sosrun.WAITING)]
        self.assertFalse(sosrun.all_settled(routes))
        routes[1].state = sosrun.SENT
        self.assertTrue(sosrun.all_settled(routes))

    def test_a_run_survives_its_own_storage(self):
        run = sosrun.Run(1_000.0, False, "hold", "flaneur", (52.0, 4.0, 12.0, 990.0), [sosrun.Route("mesh", "Mesh, everyone in range", sosrun.SENT, "Sent")], ["Hub: not set up on this phone."])
        again = sosrun.Run.from_json(run.to_json())
        self.assertEqual(again.id, 1_000.0)
        self.assertEqual(again.routes[0].state, sosrun.SENT)
        self.assertEqual(again.fix, (52.0, 4.0, 12.0, 990.0))
        self.assertTrue(again.active)
        self.assertIsNone(sosrun.Run.from_json({"broken": True}))
        self.assertIsNone(sosrun.Run.from_json("no"))

    def test_the_titles_and_the_started_line(self):
        run = sosrun.Run(0.0, False, "checkin", "flaneur", None, [], [])
        self.assertEqual(sosrun.titles(run), ("SOS is on", "red"))
        self.assertTrue(sosrun.started_line(run).endswith("by the check-in timer. Position unknown."))
        run.cancelled_at = 60.0
        self.assertTrue(sosrun.titles(run)[0].startswith("SOS cancelled at "))
        test = sosrun.Run(0.0, True, "hold", "flaneur", (52.0, 4.0, 12.4, 0.0), [], [])
        self.assertEqual(sosrun.titles(test), ("Alarm test running", "amber"))
        self.assertTrue(sosrun.started_line(test).endswith("from this phone. Position 52.00000, 4.00000, within 12 m."))
        test.finished_at = 5.0
        self.assertEqual(sosrun.titles(test), ("Alarm test finished", "muted"))

    def test_the_test_dialog_lists_every_leg(self):
        s = state(bridge=CONNECTED, cellular=SIM, contacts=[{"name": "Anna", "phone": "+316"}, {"name": "", "phone": "+317"}], hub={"url": "mqtts://hub"}, modem={"connected": True, "port": "/dev/ttyUSB4"})
        parts = sosrun.test_parts(s)
        self.assertEqual(parts, ["a position report to the Hub by satellite, 1 credit", "the text on the mesh", "the text by SMS to 2 contacts, at your carrier's rate", "a test event to the Hub online"])
        text = sosrun.test_dialog_text(sos.test_text("flaneur"), parts)
        self.assertTrue(text.startswith('The test text is "Test from flaneur: checking the MeshSat alarm routes. No help needed.". It goes as a position report'))
        self.assertTrue(text.endswith("; and a test event to the Hub online. Nobody is alarmed, and the Hub does not raise an SOS."))
        one = sosrun.test_dialog_text("t", ["the text on the mesh"])
        self.assertIn("It goes as the text on the mesh.", one)

    def test_the_test_dialog_takes_every_route_set_up(self):
        """TestAlarmDialog lists SosReach's routes (SosScreens.kt:423-428), as Home and Safety count
        them: a modem this phone has had, a node paired while it reconnects; not only what is up
        this minute. One contact is named, a blank name is "1 contact" (ifBlank)."""
        imei = "300434065000000"
        s = state(bridge=CONNECTED | {"connected": False}, hardware={"node": "bluetooth"}, ble={"mode": "lost", "address": "E0:72"},
                  modem={"connected": False, "port": "", "imei": ""}, cellular=SIM, contacts=[{"name": "  ", "phone": "+316"}], hub={"url": "mqtts://hub"})
        self.assertEqual(sosrun.test_parts(s, imei), ["a position report to the Hub by satellite, 1 credit", "the text on the mesh",
                                                      "the text by SMS to 1 contact, at your carrier's rate", "a test event to the Hub online"])
        # No modem ever seen: no satellite leg; the Bridge's own word on a modem it knows counts too
        self.assertNotIn("a position report to the Hub by satellite, 1 credit", sosrun.test_parts(s))
        s.modem = {"connected": False, "port": "/dev/ttyUSB4", "imei": imei, "silent": True}
        self.assertIn("a position report to the Hub by satellite, 1 credit", sosrun.test_parts(s))
        s.contacts = [{"name": "Anna", "phone": "+316"}]
        self.assertIn("the text by SMS to Anna, at your carrier's rate", sosrun.test_parts(s))
        # The cover: the node started is the mesh route, connected yet or not
        cover = state(bridge=CONNECTED | {"connected": False}, node_service=True)
        self.assertEqual(sosrun.test_parts(cover), ["the text on the mesh"])
        # Without the Bridge nothing goes, whatever was set up
        s.bridge = None
        self.assertEqual(sosrun.test_parts(s, imei), [])

    def test_the_test_dialog_and_the_reach_rule_agree(self):
        """One rule (model/home.reach) for the SOS card, Safety and the test's dialog: a leg for each
        route it counts, and none when an SOS would have nowhere to go."""
        imei = "300434065000000"
        states = [state(bridge=None), state(bridge=CONNECTED | {"connected": False}), state(bridge=CONNECTED | {"connected": False}, node_service=True),
                  state(bridge=CONNECTED, cellular=SIM), state(bridge=CONNECTED, cellular=SIM, contacts=[{"name": "Anna", "phone": "+316"}], hub={"url": "mqtts://hub"}),
                  state(bridge=CONNECTED | {"connected": False}, hardware={"node": "bluetooth"}, ble={"mode": "idle"}, cellular={"connected": True, "sim_state": "PIN_REQUIRED"},
                        contacts=[{"name": "Anna", "phone": "+316"}])]
        for s in states:
            for seen in ("", imei):
                routes = home.reach(s, seen)
                parts = sosrun.test_parts(s, seen)
                self.assertEqual(len(parts), sum(routes[k] for k in ("satellite", "mesh", "sms", "hub")), (vars(s), seen))
                self.assertEqual(bool(parts), routes["anywhere"], (vars(s), seen))


if __name__ == "__main__":
    unittest.main()
