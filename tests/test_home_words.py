# SPDX-License-Identifier: GPL-3.0-or-later
"""Home's lanes and sentences, held up against HomeLanes.kt and SosScreens.kt."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import api  # noqa: E402
from meshsat.model import home  # noqa: E402


def state(**fields) -> api.State:
    s = api.State()
    for key, value in fields.items():
        setattr(s, key, value)
    return s


NODE = {"user_id": "!52cb81e7", "long_name": "meshsat-pinephone-pro", "battery_level": 101, "rssi": -60}
OTHER = {"user_id": "!a1b3c2ec", "long_name": "MSPA", "last_heard": 1}
CONNECTED = {"connected": True, "node_id": "!52cb81e7", "node_name": "meshsat-pinephone-pro"}


class LanesTest(unittest.TestCase):
    def test_nothing_can_send_with_the_bridge_down(self):
        s = state(bridge=None)
        lanes = home.lanes(s)
        self.assertEqual(lanes["mesh"][0], "off")
        self.assertEqual(lanes["satellite"], ("off", "Connect a MeshSat node to use its satellite modem.", ""))
        self.assertEqual(lanes["hub"], ("off", "Scan the Hub's QR code to connect this phone.", ""))
        self.assertEqual(home.sentence(lanes, s), ("Nothing can send yet.", "Start with your MeshSat node, below."))

    def test_stale_modem_and_hub_never_count_with_the_bridge_down(self):
        s = state(bridge=None, modem={"connected": True}, hub={"url": "mqtts://hub", "bridge_id": "x"}, cellular={"connected": True, "sim_state": "READY", "registration": "registered"})
        lanes = home.lanes(s)
        self.assertEqual(lanes["satellite"][0], "off")
        self.assertEqual(lanes["hub"][0], "off")
        # api.poll_state clears these on a poll; the words never claim a link the Bridge cannot see
        self.assertEqual(home.sentence(lanes, s)[0], "Nothing can send yet.")

    def test_mesh_only(self):
        s = state(bridge=CONNECTED, nodes=[NODE, OTHER])
        lanes = home.lanes(s)
        self.assertEqual(lanes["mesh"], ("working", "Connected to meshsat-pinephone-pro, signal -60 dBm. On USB power.", "1 node"))
        self.assertEqual(lanes["satellite"], ("off", "This radio has no satellite modem. Plug a RockBLOCK into USB-C.", ""))
        self.assertEqual(home.sentence(lanes, s), ("Messages can go out by mesh.", None))

    def test_singular_and_plural_nodes(self):
        s = state(bridge=CONNECTED, nodes=[NODE, OTHER, dict(OTHER, user_id="!b")])
        self.assertEqual(home.mesh_lane(s)[2], "2 nodes")

    def test_all_four_ways(self):
        s = state(bridge=CONNECTED, nodes=[NODE], modem={"connected": True, "port": "/dev/ttyUSB4"}, signal={"bars": 3},
                  hub={"url": "mqtts://hub", "bridge_id": "msa-1", "link": "connected"}, cellular={"connected": True, "sim_state": "READY", "registration": "registered_home"})
        lanes = home.lanes(s)
        self.assertEqual(lanes["satellite"], ("working", "Modem ready.", "3/5"))
        self.assertEqual(lanes["sms"], ("working", "Ready.", "0 today"))
        self.assertEqual(lanes["hub"], ("working", "Connected as msa-1.", ""))
        self.assertEqual(home.sentence(lanes, s), ("Messages can go out by satellite, mesh, SMS and the Hub.", None))

    def test_hub_lane_follows_the_links_state(self):
        """HomeLanes.kt:217-223: no Hub link running is Off, whatever the settings say."""
        s = state(bridge=CONNECTED, hub={"url": "mqtts://hub", "bridge_id": "msa-1", "state": ""})
        self.assertEqual(home.hub_lane(s), ("off", "Scan the Hub's QR code to connect this phone.", ""))
        for link, want in (("connecting", ("trying", "Connecting to the Hub.", "")),
                           ("error", ("failed", "Cannot reach the Hub. It keeps trying by itself.", "")),
                           ("disconnected", ("trying", "Not connected. It keeps trying by itself.", "")),
                           ("connected", ("working", "Connected as msa-1.", ""))):
            s.hub["state"] = link
            self.assertEqual(home.hub_lane(s), want, link)
        s.hub["running_as"] = "kit-7"
        self.assertEqual(home.hub_lane(s), ("working", "Connected as kit-7.", ""))
        s.bridge = None
        self.assertEqual(home.hub_lane(s)[0], "off")

    def test_messages_on_the_way(self):
        s = state(bridge=CONNECTED, nodes=[NODE], messages=[{"delivery_status": "queued"}, {"delivery_status": "sending"}])
        self.assertEqual(home.sentence(home.lanes(s), s)[1], "2 messages on the way.")
        s.messages = [{"delivery_status": "queued"}]
        self.assertEqual(home.sentence(home.lanes(s), s)[1], "1 message on the way.")

    def test_bluetooth_mode_words(self):
        s = state(bridge=CONNECTED | {"connected": False}, hardware={"node": "bluetooth"}, ble={"mode": "connecting", "address": "E0:72"})
        self.assertEqual(home.mesh_lane(s), ("trying", "Connecting to your node.", ""))
        s.ble = {"mode": "lost", "address": "E0:72"}
        self.assertEqual(home.mesh_lane(s), ("trying", "Reconnecting to your node.", ""))
        self.assertEqual(home.satellite_lane(s), ("trying", "Reconnecting to your MeshSat node.", ""))
        s.ble = {"mode": "idle"}
        self.assertEqual(home.mesh_lane(s), ("off", "Connect a MeshSat node or a Meshtastic radio.", ""))


class SosWordsTest(unittest.TestCase):
    def test_reach_sentence(self):
        s = state(bridge=CONNECTED, nodes=[NODE])
        self.assertEqual(home.reach_sentence(s), "Sends your position by the mesh, and keeps trying until you cancel.")
        s.contacts = [{"name": "Anna", "phone": "+31"}]
        s.cellular = {"connected": True, "sim_state": "READY", "registration": "registered"}
        self.assertEqual(home.reach_sentence(s), "Sends your position by the mesh and SMS to Anna, and keeps trying until you cancel.")
        s.contacts.append({"name": "", "phone": "+32"})
        self.assertEqual(home.reach_sentence(s), "Sends your position by the mesh and SMS to 2 people, and keeps trying until you cancel.")

    def test_nowhere_to_go(self):
        s = state(bridge=None)
        self.assertEqual(home.reach_sentence(s), "An SOS has nowhere to go yet. Connect your MeshSat node, or set up the Hub.")
        s = state(bridge=CONNECTED | {"connected": False}, cellular={"connected": True, "sim_state": "READY", "registration": "registered"})
        self.assertEqual(home.reach_sentence(s), "An SOS has nowhere to go yet. Add emergency contacts, or connect your node.")

    def test_contacts_button(self):
        s = state(bridge=None)
        self.assertEqual(home.contacts_button(s), "Connect your node")
        s = state(bridge=CONNECTED, cellular={"connected": True, "sim_state": "READY", "registration": "registered"})
        self.assertEqual(home.contacts_button(s), "Add emergency contacts")
        s.contacts = [{"phone": "+31"}]
        self.assertEqual(home.contacts_button(s), "Emergency contacts")


if __name__ == "__main__":
    unittest.main()
