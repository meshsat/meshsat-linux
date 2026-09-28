# SPDX-License-Identifier: GPL-3.0-or-later
"""MeshSat outside its window: the event stream's parsing and the words of the notifications
and of the status, against events recorded on the bench phone (28 Sep 2026)."""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import events, outside  # noqa: E402

PACKET = b'data: {"type":"packet","message":"lora rx mesh_0 !a1b3c2ec -\\u003e broadcast TEXT_MESSAGE_APP 26 B rssi -62 snr 6.5","data":{"time":"2026-09-28T17:31:23.801831455+02:00","bearer":"lora","dir":"rx","iface":"mesh_0","from":"!a1b3c2ec","to":"broadcast","bytes":26,"rssi":-62,"snr":6.5,"hops":0,"channel":0,"portnum":1,"portnum_name":"TEXT_MESSAGE_APP","text":"Event sample 1 at 17:31:18","raw":"","path":"","msg_ref":""},"time":"2026-09-28T15:31:23.801831455Z"}\n'
MESSAGE = b'data: {"type":"message","message":"from !a1b3c2ec portnum=TEXT_MESSAGE_APP","data":{"from":2712912620,"to":4294967295,"channel":0,"id":3848726775,"portnum":1,"portnum_name":"TEXT_MESSAGE_APP","decoded_text":"Event sample 1 at 17:31:18","rx_time":1790609482},"time":"2026-09-28T15:31:22Z"}\n'
HELLO = b'data: {"type":"connected_to_stream","message":"subscribed to MeshSat event stream"}\n'


class StreamTest(unittest.TestCase):
    def test_lines(self):
        self.assertEqual(events.parse_line(HELLO)["type"], "connected_to_stream")
        self.assertIsNone(events.parse_line(b"\n"))
        self.assertIsNone(events.parse_line(b": keepalive\n"))
        self.assertIsNone(events.parse_line(b"data: not json\n"))
        self.assertIsNone(events.parse_line(b'data: {"no":"type"}\n'))

    def test_a_mesh_text_is_told_once(self):
        got = []
        stream = events.EventStream(got.append, url="http://nowhere.invalid/", opener=None)
        stream.read(io.BytesIO(HELLO + b"\n" + PACKET + b"\n" + MESSAGE + b"\n"))
        self.assertEqual([e["type"] for e in got], ["packet", "message"], "the greeting is not an event")
        texts = [events.inbound_text(e) for e in got]
        self.assertEqual(texts[0], {"lane": "mesh", "from": "!a1b3c2ec", "text": "Event sample 1 at 17:31:18"})
        self.assertIsNone(texts[1], "the message event repeats the packet event")

    def test_not_every_packet_is_a_text(self):
        tx = {"type": "packet", "data": {"dir": "tx", "portnum_name": "TEXT_MESSAGE_APP", "text": "mine", "from": "!52cb81e7"}}
        telemetry = {"type": "packet", "data": {"dir": "rx", "portnum_name": "TELEMETRY_APP", "text": "", "from": "!a1b3c2ec"}}
        self.assertIsNone(events.inbound_text(tx))
        self.assertIsNone(events.inbound_text(telemetry))
        self.assertIsNone(events.inbound_text({"type": "node_update", "data": {}}))

    def test_sms_and_satellite(self):
        sms = events.inbound_text({"type": "sms_received", "message": "hello", "data": {"phone": "+31612345678", "text": "hello"}})
        self.assertEqual(sms, {"lane": "sms", "from": "+31612345678", "text": "hello"})
        sat = events.inbound_text({"type": "inbound", "data": {"source": "iridium_0", "imei": "300434061234560", "text": "from the hub"}})
        self.assertEqual(sat["lane"], "satellite")

    def test_seen(self):
        seen = events.Seen()
        self.assertTrue(seen.new("!a1b3c2ec", "hi", now=1000))
        self.assertFalse(seen.new("!a1b3c2ec", "hi", now=1060), "heard again through a relay")
        self.assertTrue(seen.new("!a1b3c2ec", "hi", now=1200), "the same words two minutes later are a new text")
        self.assertTrue(seen.new("!8b04a69e", "hi", now=1200))


class WordsTest(unittest.TestCase):
    def test_messages(self):
        self.assertEqual(outside.message_notification({"lane": "mesh", "from": "!a1b3c2ec", "text": "hi"}), ("Mesh: !a1b3c2ec", "hi"))
        self.assertEqual(outside.message_notification({"lane": "satellite", "from": "300434061234560", "text": "x"})[0], "Iridium: 300434061234560")
        self.assertEqual(outside.message_notification({"lane": "sms", "from": "+31612345678", "text": "x"})[0], "SMS: +31612345678")

    def test_signal(self):
        self.assertIsNone(outside.signal_notification(None, None))
        self.assertIsNone(outside.signal_notification({"connected": False}, {"bars": 3}))
        self.assertEqual(outside.signal_notification({"connected": True, "imei": "300434061234560", "port": "/dev/ttyUSB4"}, {"bars": 3}),
                         ("Iridium signal 3/5", "RockBLOCK 234560 on this device", "meshsat-iridium-3-symbolic"))
        self.assertEqual(outside.signal_notification({"connected": True, "imei": "300434061234560", "port": "ble:E0:72:A1:B3:C2:ED"}, {"bars": 9})[:2],
                         ("Iridium signal 5/5", "RockBLOCK 234560 via the MeshSat node"))
        self.assertEqual(outside.signal_notification({"connected": True}, None), ("Iridium signal 0/5", "Iridium modem connected", "meshsat-iridium-0-symbolic"))

    def test_sos(self):
        self.assertIsNone(outside.sos_notification({"active": False}, False))
        self.assertEqual(outside.sos_notification({"active": True}, False)[0], "SOS is on")
        self.assertEqual(outside.sos_notification({"active": False}, True), ("SOS cancelled", "Telling everyone who got it that you are safe.", False))

    def test_failures(self):
        self.assertIsNone(outside.failure_notification({"type": "packet"}))
        self.assertEqual(outside.failure_notification({"type": "delivery_dead", "data": {"channel": "iridium_0", "last_error": "no network"}}), ("Iridium send failed", "no network"))
        self.assertEqual(outside.failure_notification({"type": "forward_error", "message": "mesh_0: queue full"})[0], "Not sent by mesh")

    def test_status(self):
        nothing = outside.status(None, None, None, [])
        self.assertEqual(nothing["summary"], "Nothing can send yet.")
        self.assertEqual(nothing["mesh"]["state"], "off")
        self.assertEqual(nothing["tile"], "MeshSat: no node")
        nodes = [{"user_id": "!52cb81e7"}, {"user_id": "!a1b3c2ec"}, {"user_id": "!8b04a69e"}]
        up = outside.status({"connected": True, "node_id": "!52cb81e7", "node_name": "meshsat-pinephone-pro"}, {"connected": True, "imei": "1"}, {"bars": 4}, nodes)
        self.assertEqual(up["summary"], "Satellite: 4/5, Mesh: 2 nodes")
        self.assertEqual(up["tile"], "Satellite: 4/5")
        self.assertEqual(up["icon"], "meshsat-iridium-4-symbolic")
        self.assertEqual(up["mesh"]["detail"], "Connected to meshsat-pinephone-pro.")
        mesh_only = outside.status({"connected": True, "node_id": "!52cb81e7"}, {"connected": False, "port": ""}, None, nodes)
        self.assertEqual(mesh_only["summary"], "Mesh: 2 nodes")
        self.assertEqual(mesh_only["tile"], "Mesh: 2 nodes")
        self.assertEqual(outside.mesh_words(1), "Mesh: 1 node")
        self.assertEqual(outside.mesh_words(0), "Mesh: 0 nodes")
        self.assertEqual(mesh_only["icon"], "meshsat-transport-mesh-symbolic")
        waiting = outside.status({"connected": False}, None, None, [], {"node": "bluetooth"}, {"address": ""})
        self.assertEqual(waiting["mesh"]["detail"], "Connect a MeshSat node or a Meshtastic radio.")
        reconnecting = outside.status({"connected": False}, None, None, [], {"node": "cover"}, None)
        self.assertEqual(reconnecting["tile"], "Mesh: connecting")


if __name__ == "__main__":
    unittest.main()
