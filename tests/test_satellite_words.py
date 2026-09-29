# SPDX-License-Identifier: GPL-3.0-or-later
"""The Satellite page's words (model/satellite.py), from SettingsScreen.kt:528-733 for the
RockBLOCK 9603 on USB-C and the 9704 on USB."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import satellite as sat  # noqa: E402

MODEM = {"connected": True, "port": "/dev/ttyUSB4", "model": "RockBLOCK 9603", "imei": "300434065000000", "type": "sbd"}


class UsbModemTest(unittest.TestCase):
    def test_status_words(self):
        self.assertEqual(sat.usb_status(True, MODEM, 3), ("Connected (Signal: 3/5)", True))
        self.assertEqual(sat.usb_status(True, {"connected": False, "port": "/dev/ttyUSB4"}, 0), ("Checking the modem...", False))
        self.assertEqual(sat.usb_status(True, {"connected": False, "port": "/dev/ttyUSB4", "silent": True}, 0), ("The modem does not answer (still trying)", False))
        self.assertEqual(sat.usb_status(True, {"connected": False, "port": ""}, 0), ("No modem on this radio. Plug a RockBLOCK into USB-C.", False))
        self.assertEqual(sat.usb_status(True, {"connected": False, "port": "supervisor"}, 0)[0], "No modem on this radio. Plug a RockBLOCK into USB-C.")
        self.assertEqual(sat.usb_status(True, None, 0)[0], "No modem on this radio. Plug a RockBLOCK into USB-C.")
        self.assertEqual(sat.usb_status(False, MODEM, 3), ("Connect your node first.", False))

    def test_rows_only_what_the_modem_said(self):
        """InfoRows: Manufacturer, Model, IMEI, each when not blank; no Port (Android has none)."""
        self.assertEqual(sat.usb_rows(MODEM), [("Model", "RockBLOCK 9603"), ("IMEI", "300434065000000")])
        self.assertEqual(sat.usb_rows({**MODEM, "manufacturer": "Iridium"})[0], ("Manufacturer", "Iridium"))
        self.assertEqual(sat.usb_rows({**MODEM, "connected": False}), [])

    def test_signal_toast(self):
        self.assertEqual(sat.signal_toast({"bars": 4}), "Signal: 4/5")
        self.assertEqual(sat.signal_toast({"bars": 0}, "9704 "), "9704 Signal: 0/5")
        self.assertIsNone(sat.signal_toast({"error": "no modem"}))
        self.assertIsNone(sat.signal_toast(None))


class ImtModemTest(unittest.TestCase):
    def test_status_and_rows(self):
        imt = {"connected": True, "port": "/dev/ttyUSB5", "imei": "300534061111110", "firmware": "1.2.3", "type": "imt"}
        self.assertEqual(sat.imt_status(imt, 2), ("Ready (Signal: 2/5)", True))
        self.assertEqual(sat.imt_rows(imt), [("IMEI", "300534061111110"), ("Firmware", "1.2.3")])
        self.assertEqual(sat.imt_status({"connected": False, "port": "/dev/ttyUSB5"}, 0), ("Connecting...", False))
        self.assertEqual(sat.imt_status(None, 0), ("Disconnected", False))

    def test_the_card_unfolds_once_a_9704_is_there(self):
        self.assertFalse(sat.imt_used(None))
        self.assertFalse(sat.imt_used({"connected": False, "port": ""}))
        self.assertTrue(sat.imt_used({"connected": False, "port": "/dev/ttyUSB5"}))
        self.assertTrue(sat.imt_used({"connected": True}))


class MailboxDialogTest(unittest.TestCase):
    def test_androids_words(self):
        self.assertEqual(sat.CONFIRM_TITLE, "Check the satellite mailbox?")
        self.assertTrue(sat.CONFIRM_TEXT.startswith("This opens an Iridium session, which can take up to 90 seconds."))
        self.assertEqual((sat.CHECK_MAILBOX, sat.CHECKING, sat.CHECK, sat.CANCEL), ("Check Mailbox", "Checking mailbox...", "Check", "Cancel"))



class NodeStatsTextTest(unittest.TestCase):
    """IridiumPipeStreamsTest's "the node health card's wording", with the Bridge's field names."""

    QUIET = {"owner": "phone", "flags": {"modem_answers": True}, "csq": 3, "csq_age_s": 12, "sessions": 7, "last_mo_status": 32, "last_momsn": 250,
             "last_mt_status": 2, "last_mt_queued": 0, "last_session_age_s": 240, "uptime_s": 8040, "watchdog_reboots": 0, "client_bytes_dropped": 0,
             "node_sessions": 0, "node_sent": 0, "node_received": 0, "day_sessions_used": 0, "day_sessions_cap": 10}

    def test_a_quiet_node(self):
        self.assertEqual(sat.node_stats_rows(self.QUIET), [
            ("Modem", "Held by this phone, answers"), ("Signal", "3 of 5, 12 s ago"), ("Sessions since boot", "7"),
            ("Last session", "MO 32, no network service, MOMSN 250, 4 min ago"), ("Node's own routing", "0 of 10 sessions today, sent 0, received 0"),
            ("Node uptime", "2 h 14 min")])
        self.assertIsNone(sat.node_stats_warning(self.QUIET))

    def test_a_busy_node(self):
        busy = dict(self.QUIET, owner="node", flags={"session_in_flight": True, "message_waiting": True, "modem_answers": True, "buffer_congested": True},
                    csq=None, csq_age_s=None, last_mo_status=None, last_session_age_s=None, last_mt_queued=2, watchdog_reboots=3, client_bytes_dropped=17,
                    day_sessions_cap=0, node_sessions=0)
        self.assertEqual(sat.node_stats_rows(busy), [
            ("Modem", "Used by the node, answers"), ("Session", "In flight now"), ("Signal", "Never read"), ("Sessions since boot", "7"),
            ("Last session", "None yet"), ("Gateway", "2 waiting at the gateway"), ("Node uptime", "2 h 14 min"),
            ("Bluetooth watchdog reboots", "3"), ("Bytes the node could not take", "17")])
        self.assertEqual(sat.node_stats_warning(busy), "The node's incoming buffer is nearly full: the phone writes faster than the modem takes.")
        self.assertEqual(sat.node_stats_warning(dict(self.QUIET, flags={})), "The node's modem is not answering AT commands.")

    def test_words_and_times(self):
        self.assertEqual([sat.mo_status_text(c) for c in (-1, 0, 4, 13, 32, 36, 99)],
                         ["the link to the node dropped during the session", "sent", "sent", "the session did not complete", "no network service",
                          "the gateway asked to try again later", "failed"])
        self.assertEqual([sat.stats_ago(s) for s in (4, 5, 59, 60, 3599, 3600, 86_400)], ["just now", "5 s ago", "59 s ago", "1 min ago", "59 min ago", "1 h ago", "1 d ago"])
        self.assertEqual([sat.stats_duration(s) for s in (30, 2700, 8040, 266_400)], ["30 s", "45 min", "2 h 14 min", "3 d 2 h"])

    def test_the_node_cards_status(self):
        self.assertEqual(sat.node_status({}, {"connected": True, "port": "ble"}, 4), ("Connected (Signal: 4/5)", True))
        self.assertEqual(sat.node_status({}, {"port": "ble", "silent": True}, 0)[0], "The node's modem does not answer (still trying)")
        self.assertEqual(sat.node_status({}, {"port": "ble"}, 0)[0], "Checking the modem...")
        self.assertEqual(sat.node_status({"satellite_enabled": False, "satellite_pipe": True}, {}, 0)[0], "Off: the node keeps its modem")
        self.assertEqual(sat.node_status({"satellite_pipe": False}, {}, 0)[0], "No MeshSat node connected")
        self.assertEqual(sat.node_status({"satellite_pipe": True, "satellite_owner": "node"}, {}, 0)[0], "The node is using its modem")
        self.assertEqual(sat.node_status({"satellite_pipe": True, "satellite_owner": "none"}, {}, 0)[0], "Waiting for the node")


if __name__ == "__main__":
    unittest.main()
