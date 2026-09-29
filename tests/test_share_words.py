# SPDX-License-Identifier: GPL-3.0-or-later
""""Share the Bridge on this network" (Setup > Advanced > Diagnostics): the words, the line under
the switch, the port and the addresses to open (model/share.py), and what system.py does for the
switch under test and for real (pkexec stood in for). meshsat-share itself: test_share_package."""
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import system, trace  # noqa: E402
from meshsat.model import share  # noqa: E402

TOOL = "/usr/lib/meshsat/bin/meshsat-share"
# `ip -4 -o addr show scope global` on a phone on its Wi-Fi and mobile data, with a desktop's
# container bridge, a second Wi-Fi address, a public one and an interface named with its parent.
IP = """2: wwan0    inet 10.64.12.7/30 scope global noprefixroute wwan0\\       valid_lft forever preferred_lft forever
3: wlan0    inet 192.168.1.20/24 brd 192.168.1.255 scope global dynamic noprefixroute wlan0\\       valid_lft 86124sec preferred_lft 86124sec
3: wlan0    inet 192.168.1.21/24 brd 192.168.1.255 scope global secondary wlan0:1\\       valid_lft forever preferred_lft forever
4: docker0    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0\\       valid_lft forever preferred_lft forever
5: eth0    inet 198.51.100.7/24 brd 198.51.100.255 scope global eth0\\       valid_lft forever preferred_lft forever
6: usb0    inet 10.42.0.1/24 brd 10.42.0.255 scope global noprefixroute usb0\\       valid_lft forever preferred_lft forever
7: rmnet_data0    inet 10.100.3.4/28 scope global rmnet_data0\\       valid_lft forever preferred_lft forever
8: eth1.10@eth1    inet 172.20.5.9/24 scope global eth1.10\\       valid_lft forever preferred_lft forever
"""


class ShareWordsTest(unittest.TestCase):
    def test_the_switch_and_its_question(self):
        self.assertEqual(share.TITLE, "Share the Bridge on this network")
        self.assertEqual(share.QUESTION, "Share the Bridge on this network?")
        self.assertEqual(share.QUESTION_BODY, "Anyone on this network can then open the Bridge without a password: read and send messages, start an SOS, "
                                              "change every setting and spend satellite credit. Share it only on a network you trust, and switch it off when you are done.")
        self.assertEqual((share.SHARE, share.NOT_NOW), ("Share", "Not now"))

    def test_the_line_under_the_switch_says_what_is_true(self):
        self.assertEqual(share.subtitle(False, [], 6050), "Only this phone can open the Bridge.")
        self.assertEqual(share.subtitle(False, ["192.168.1.20"], 6050), "Only this phone can open the Bridge.")
        self.assertEqual(share.subtitle(True, [], 6050), "Shared, but this phone is on no network right now.")
        self.assertEqual(share.subtitle(True, ["192.168.1.20"], 6050), "Open http://192.168.1.20:6050 in a browser on the same network.")
        self.assertEqual(share.subtitle(True, ["192.168.1.20", "10.42.0.1"], 7050),
                         "Open http://192.168.1.20:7050 or http://10.42.0.1:7050 in a browser on the same network.")

    def test_a_change_that_did_not_happen_says_what_is_true_now(self):
        self.assertEqual(share.not_changed(True), "The Bridge was not shared.")
        self.assertEqual(share.not_changed(False), "The Bridge is still shared.")

    def test_the_port_is_the_bridges_as_systemd_and_the_bridge_read_it(self):
        for text, port in (("MESHSAT_MODE=direct\nMESHSAT_PORT=6050\n", 6050), ("MESHSAT_PORT=7050\n", 7050), ('MESHSAT_PORT="7051"\n', 7051),
                           ("MESHSAT_PORT='7052'\n", 7052), ("MESHSAT_PORT=7053  \n", 7053), ("  MESHSAT_PORT = 7054\n", 7054),
                           ("MESHSAT_PORT=7055\nMESHSAT_PORT=7056\n", 7056), ("# MESHSAT_PORT=7057\n", 6050), ("MESHSAT_PORT=07058\n", 7058),
                           ("MESHSAT_PORT=+7063\n", 7063), ("MESHSAT_PORT=0\n", 6050), ("MESHSAT_PORT=65535\n", 65535), ("MESHSAT_PORT=65536\n", 6050),
                           ("MESHSAT_PORT=99999999999999999999\n", 6050), ("MESHSAT_PORT=abc\n", 6050), ("MESHSAT_PORT=\n", 6050),
                           ("MESHSAT_PORT=-7062\n", 6050), ('MESHSAT_PORT="7061\n', 6050), ("MESHSAT_PORTX=7059\n", 6050), ("", 6050)):
            self.assertEqual(share.bridge_port(text), port, text)

    def test_the_addresses_to_open_are_on_this_network(self):
        # Not the mobile data connection (wwan, rmnet), not a public address, not a container's
        # bridge the kernel calls virtual; a phone's hotspot or USB network counts.
        self.assertEqual(share.lan_addresses(IP, {"lo", "docker0"}), ["192.168.1.20", "192.168.1.21", "10.42.0.1", "172.20.5.9"])
        self.assertEqual(share.lan_addresses(IP), ["192.168.1.20", "192.168.1.21", "172.17.0.1", "10.42.0.1", "172.20.5.9"])
        self.assertEqual(share.lan_addresses(""), [])
        self.assertEqual(share.lan_addresses("garbage\n3: wlan0 inet\n3: wlan0 inet not-an-address x\n"), [])


class ShareSystemTest(unittest.TestCase):
    """system.py's side of the switch, with no main loop: done() comes straight back."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.trace = os.path.join(self.dir.name, "trace.jsonl")
        self.flag = os.path.join(self.dir.name, "share-on-network")
        for patch in (mock.patch.object(system, "GLib", None), mock.patch.object(trace, "PATH", self.trace),
                      mock.patch.dict(os.environ, {"MESHSAT_APP_SHARE_FLAG": self.flag})):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("MESHSAT_APP_ADDRESSES", None)
        os.environ.pop("MESHSAT_APP_BRIDGE_ENV", None)
        self.addCleanup(self.dir.cleanup)

    def commands(self) -> list:
        try:
            with open(self.trace, encoding="utf-8") as handle:
                return [e["command"] for e in map(json.loads, handle) if e.get("kind") == "command"]
        except OSError:
            return []

    def test_under_test_the_command_is_traced_and_the_flag_is_the_tests_own(self):
        answers = []
        with mock.patch.object(system, "TEST", True), mock.patch.object(system.subprocess, "run", side_effect=AssertionError("ran a command under test")):
            self.assertFalse(system.shared_on_network())
            system.share_on_network(True, answers.append)
            self.assertTrue(system.shared_on_network())
            self.assertTrue(os.path.exists(self.flag))
            system.share_on_network(False, answers.append)
            self.assertFalse(system.shared_on_network())
            self.assertFalse(system.share_changing())
        self.assertEqual(answers, [True, True])
        self.assertEqual(self.commands(), [["pkexec", TOOL, "on"], ["pkexec", TOOL, "off"]])

    def test_under_test_without_a_flag_file_nothing_of_the_systems_is_touched(self):
        os.environ.pop("MESHSAT_APP_SHARE_FLAG")
        system_flag = os.path.join(self.dir.name, "etc-share-on-network")
        answers = []
        with mock.patch.object(system, "TEST", True), mock.patch.object(system, "SHARE_FLAG", system_flag):
            system.share_on_network(True, answers.append)
        self.assertEqual(answers, [True])
        self.assertFalse(os.path.exists(system_flag))
        self.assertEqual(self.commands(), [["pkexec", TOOL, "on"]])

    def for_real(self, on: bool, code: int) -> tuple:
        """share_on_network with pkexec standing in, exiting `code`: (the answers, the commands
        run, whether the change was marked as running while pkexec ran)."""
        answered, answers, seen, running = threading.Event(), [], [], []

        def run(command, **_kwargs):
            seen.append(command)
            running.append(system.share_changing())
            return mock.Mock(returncode=code)

        def done(value):
            answers.append(value)
            answered.set()

        with mock.patch.object(system, "TEST", False), mock.patch.object(system.subprocess, "run", side_effect=run):
            system.share_on_network(on, done)
            self.assertTrue(answered.wait(5), "done() never came")
        return answers, seen, running

    def test_for_real_pkexec_runs_on_a_thread_and_its_exit_is_the_answer(self):
        for on, code, ok in ((True, 0, True), (False, 0, True), (True, 126, False), (False, 127, False), (True, 1, False)):
            answers, seen, running = self.for_real(on, code)
            self.assertEqual(answers, [ok], (on, code))
            self.assertEqual(seen, [["pkexec", TOOL, "on" if on else "off"]])
            self.assertEqual(running, [True], "the change was not marked as running while pkexec ran")
            self.assertFalse(system.share_changing())

    def test_for_real_no_pkexec_is_a_failure_not_a_crash(self):
        answered, answers = threading.Event(), []
        with mock.patch.object(system, "TEST", False), mock.patch.object(system.subprocess, "run", side_effect=FileNotFoundError("pkexec")):
            system.share_on_network(True, lambda value: (answers.append(value), answered.set()))
            self.assertTrue(answered.wait(5))
        self.assertEqual(answers, [False])

    def test_the_addresses_stand_in_under_test_and_are_none_without(self):
        with mock.patch.object(system, "TEST", True), mock.patch.object(system.subprocess, "run", side_effect=AssertionError("ran ip under test")):
            with mock.patch.dict(os.environ, {"MESHSAT_APP_ADDRESSES": "192.168.1.20, 10.0.0.5,"}):
                self.assertEqual(system.lan_addresses(), ["192.168.1.20", "10.0.0.5"])
            self.assertEqual(system.lan_addresses(), [])

    def test_for_real_the_addresses_come_from_ip(self):
        with mock.patch.object(system, "TEST", False), mock.patch.object(system.subprocess, "run", return_value=mock.Mock(stdout=IP)) as run:
            self.assertIn("192.168.1.20", system.lan_addresses())
        self.assertEqual(run.call_args[0][0], ["ip", "-4", "-o", "addr", "show", "scope", "global"])

    def test_the_port_comes_from_the_bridges_settings(self):
        env = os.path.join(self.dir.name, "bridge.env")
        with open(env, "w", encoding="utf-8") as handle:
            handle.write("MESHSAT_MODE=direct\nMESHSAT_PORT=6051\nHUB_API_KEY=\n")
        with mock.patch.dict(os.environ, {"MESHSAT_APP_BRIDGE_ENV": env}):
            self.assertEqual(system.bridge_port(), 6051)
        with mock.patch.dict(os.environ, {"MESHSAT_APP_BRIDGE_ENV": os.path.join(self.dir.name, "none.env")}):
            self.assertEqual(system.bridge_port(), 6050)


if __name__ == "__main__":
    unittest.main()
