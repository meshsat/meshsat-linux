# SPDX-License-Identifier: GPL-3.0-or-later
"""The rest of Advanced (0.8.0) against Android: the topology built from what was heard
(TopologyScreen.kt), the audit log's words and copy (AuditScreen.kt), the credentials' cards
(CredentialsScreen.kt), AES-256-GCM (AesGcmWireFormatTest, and a vector made with the Bridge's
own construction), the node log (NodeLog.kt)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from meshsat.model import audit, credentials, nodelog, topology, words  # noqa: E402

try:
    from meshsat.model import crypto  # noqa: E402

    import cryptography  # noqa: F401,E402
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

NOW = 1_800_000_000.0
ME = "!52cb81e7"


def node(user_id, long_name="", short_name="", last_heard=NOW - 60, **more):
    out = {"user_id": user_id, "num": int(user_id[1:], 16), "long_name": long_name, "short_name": short_name, "last_heard": last_heard, "snr": 5.5, "hw_model": 50}
    out.update(more)
    return out


class TopologyTest(unittest.TestCase):
    def test_a_link_is_what_was_heard_never_inferred(self):
        nodes = [node(ME, "meshsat-pinephone-pro", "MSPP", NOW - 5), node("!a1b3c2ec", "MSPA", "MSPA", NOW - 120), node("!8b04a69e", "", "", 0)]
        t = topology.build(nodes, ME, {"neighbors": None, "source": "database"}, NOW)
        self.assertEqual([n["num"] for n in t["nodes"]][0], 0x52CB81E7, "your node comes first")
        self.assertEqual(len(t["links"]), 1, t["links"])  # the node never heard has no link
        self.assertTrue(t["links"][0]["fresh"])
        self.assertFalse(t["reports"])
        self.assertEqual(topology.stats(t, NOW), [("Heard in 15 min", "1 of 2"), ("Links", "1"), ("Average SNR, heard directly", "5.5 dB")])
        lines = topology.hearing_lines(t, NOW)
        self.assertEqual(lines[0], ("Your node hears MSPA", "SNR 5.5 dB, 2 min ago", True))
        self.assertFalse(topology.empty(t))

    def test_a_node_further_away_is_not_heard_directly(self):
        nodes = [node(ME), node("!a1b3c2ec", "Far", hops_away=2)]
        t = topology.build(nodes, ME, {}, NOW)
        self.assertEqual(t["links"], [])
        rows = topology.node_rows(t, NOW)
        far = next(r for r in rows if r["num"] == 0xA1B3C2EC)
        self.assertIn("2 hops away", far["detail"])

    def test_neighbor_reports_live_and_stored(self):
        live = {"neighbors": [{"node_id": 0xA1B3C2EC, "neighbors": [{"node_id": 0x8B04A69E, "snr": -3.25}], "node_broadcast_interval_secs": 3600,
                               "last_updated": "2027-01-15T08:00:00Z"}], "source": "live"}
        now = words.stamp_epoch("2027-01-15T09:30:00Z")
        t = topology.build([node(ME, last_heard=0)], ME, live, now)
        self.assertTrue(t["reports"])
        h = t["hearings"][0]
        self.assertEqual((h["hearer"], h["heard"], h["by_our_radio"]), (0xA1B3C2EC, 0x8B04A69E, False))
        self.assertTrue(h["fresh"], "a report within twice its broadcast interval is recent")
        self.assertEqual(topology.hearing_lines(t, now)[0][1], "SNR -3.3 dB, 1 h ago, as it reported")
        stored = {"neighbors": [{"node_id": 0xA1B3C2EC, "neighbor_node_id": 0x8B04A69E, "snr": 1.0, "last_rx_time": 0, "broadcast_interval": 900,
                                 "created_at": "2027-01-15 09:00:00"}], "source": "database"}
        t = topology.build([node(ME, last_heard=0)], ME, stored, now)
        self.assertFalse(t["hearings"][0]["fresh"], "older than twice a 15 min interval")
        self.assertEqual([n["label"] for n in t["nodes"]], ["81e7", "a69e", "c2ec"])

    def test_the_empty_mesh_and_the_rows(self):
        t = topology.build([node(ME, "me", "ME", NOW - 5)], ME, {}, NOW)
        self.assertTrue(topology.empty(t))
        nodes = [node(ME, "me", "ME", NOW - 5, battery_level=101), node("!a1b3c2ec", "MSPA", "MSPA", NOW - 3600, battery_level=78, rssi=-60)]
        rows = topology.node_rows(topology.build(nodes, ME, {}, NOW), NOW)
        self.assertEqual(rows[0]["title"], "me (your node)")
        self.assertEqual(rows[0]["detail"], "On USB power")
        self.assertEqual(rows[0]["id_line"], "!52cb81e7  LilyGO T-Deck")
        self.assertEqual(rows[1]["detail"], "Heard directly, SNR 5.5 dB, RSSI -60 dBm, Battery 78%")
        self.assertEqual((rows[1]["ago"], rows[1]["tone"]), ("1 h ago", "muted"))

    def test_the_layout_settles_on_screen(self):
        positions = topology.start_positions(4)
        edges = [(0, 1, True), (0, 2, False)]
        for step in range(topology.STEPS):
            topology.simulate(positions, edges, topology.temperature(step))
        for x, y in positions:
            self.assertTrue(-300 <= x <= 300 and -300 <= y <= 300)
        scale, _mx, _my = topology.fit(positions, 360, 260, 32)
        self.assertTrue(0.2 <= scale <= 3.0)

    def test_numbers_are_rounded_as_kotlin_writes_them(self):
        self.assertEqual(words.fixed(-3.25), "-3.3")
        self.assertEqual(words.fixed(5.5), "5.5")
        self.assertEqual(words.fixed(0.05), "0.1")
        self.assertEqual(words.fixed(5.55), "5.5")  # the double is 5.54999..., as Java rounds it
        self.assertEqual(words.fixed(7), "7.0")

    def test_hardware_names(self):
        self.assertEqual(words.hardware_name(50), "LilyGO T-Deck")
        self.assertEqual(words.hardware_name(0), "Unknown model")
        self.assertEqual(words.hardware_name(255, "PORTDUINO"), "Custom hardware")
        self.assertEqual(words.hardware_name(37, "PORTDUINO"), "Portduino")
        self.assertEqual(words.hardware_name(9999), "Unknown model (code 9999)")
        self.assertEqual(words.hardware_name(62, "HELTEC_WIRELESS_PAPER_V1_0"), "Heltec Wireless Paper V1 0")


class AuditTest(unittest.TestCase):
    def test_event_words(self):
        self.assertEqual(audit.event_label("dispatch"), "Queued")
        self.assertEqual(audit.event_label("oob_reject"), "Remote command refused")
        self.assertEqual(audit.event_label("rule.matched:x"), "Rule matched x")
        self.assertEqual(audit.event_label(""), "Event")
        self.assertEqual([audit.event_tone(t) for t in ("forward", "delivered", "deny", "rejected", "bind", "connect", "dispatch")],
                         ["green", "green", "red", "red", "blue", "blue", "muted"])
        self.assertEqual(audit.direction_label("egress"), "sent")
        self.assertEqual(audit.direction_label("RX"), "received")
        self.assertIsNone(audit.direction_label("sideways"))
        self.assertEqual(audit.where_line({"interface_id": "iridium_0", "direction": "inbound"}), "Satellite, received")
        self.assertEqual(audit.refs_line({"delivery_id": 12, "rule_id": 3}, {3: "SOS to satellite"}), "Message #12 · Rule “SOS to satellite”")
        self.assertEqual(audit.refs_line({"rule_id": 9}, {}), "Rule #9")
        self.assertEqual(audit.count_text(1), "1 entry")
        self.assertEqual(audit.signer_short("082d35bc64aa838a5cb8dd18"), "082d35bc64aa…")

    def test_the_check_in_words(self):
        self.assertEqual(audit.check_words({"verified": True, "valid": 0, "broken_at": -1}), [("Nothing to check yet.", "body-medium", "secondary")])
        self.assertEqual(audit.check_words({"verified": True, "valid": 57, "broken_at": -1})[0][0], "The last 57 entries are as they were written.")
        broken = audit.check_words({"verified": False, "valid": 3, "broken_at": 3}, [{"id": 10}, {"id": 11}, {"id": 12}, {"id": 13}])
        self.assertEqual([l[0] for l in broken], ["The log was changed after it was written.", "Save a copy and keep it, then contact your MeshSat admin.",
                                                  "The first changed entry is number 13."])
        self.assertEqual(audit.check_words({"broken_at": 5})[2][0], "The first changed entry is 6 from the oldest of the last 1000.")

    def test_the_copy_is_oldest_first_with_its_hashes(self):
        newest_first = [{"id": 2, "timestamp": "2027-01-15T10:00:01Z", "interface_id": "mesh_0", "direction": "egress", "event_type": "deliver", "delivery_id": 5,
                         "rule_id": None, "detail": "a\tb\nc", "prev_hash": "h1", "hash": "h2"},
                        {"id": 1, "timestamp": "2027-01-15T10:00:00Z", "event_type": "dispatch", "detail": "", "prev_hash": "", "hash": "h1"}]
        text = audit.export_text(newest_first, "abc", now=0)
        lines = text.splitlines()
        self.assertEqual(lines[:4], ["MeshSat audit log", "Saved: 1970-01-01T00:00:00Z", "Signing key: abc", "Entries: 2"])
        self.assertEqual(lines[5], "id\ttimestamp_utc\tinterface\tdirection\tevent\tdelivery_id\trule_id\tdetail\tprev_hash\thash")
        self.assertEqual(lines[6], "1\t2027-01-15T10:00:00Z\t\t\tdispatch\t\t\t\t\th1")
        self.assertEqual(lines[7], "2\t2027-01-15T10:00:01Z\tmesh_0\tegress\tdeliver\t5\t\ta b c\th1\th2")
        self.assertTrue(audit.export_name(0).startswith("meshsat-audit-19"))


class CredentialsTest(unittest.TestCase):
    def test_the_card(self):
        cred = {"id": "x", "provider": "local", "name": "hub.pem", "cred_type": "x509_cert", "cert_not_after": "2027-03-01T12:00:00Z", "cert_subject": "CN=hub.meshsat.net",
                "cert_fingerprint": "0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9", "version": 2, "source": "local"}
        self.assertEqual(credentials.fingerprint_text(cred["cert_fingerprint"]), "0A:1B:2C:3D:4E:5F:60:71")
        self.assertEqual(credentials.badges(cred), ["local", "x509_cert", "local"])
        self.assertEqual(credentials.lines(cred), [("SHA-256: 0A:1B:2C:3D:4E:5F:60:71", "mono"), ("Subject: CN=hub.meshsat.net", "plain"), ("Expires: 2027-03-01", "expiry"),
                                                   ("v2", "plain")])
        self.assertEqual(credentials.delete_dialog(cred)["body"], "Remove 'hub.pem' (local)? This cannot be undone.")

    def test_the_expiry_colours(self):
        now = words.stamp_epoch("2027-01-15T12:00:00Z")
        self.assertEqual(credentials.expiry_tone("2027-01-10", now), "red")
        self.assertEqual(credentials.expiry_tone("2027-02-01", now), "amber")
        self.assertEqual(credentials.expiry_tone("2027-06-01", now), "green")
        self.assertEqual(credentials.expiry_tone("", now), "muted")
        self.assertEqual(credentials.expiry_tone("sometime", now), "muted")

    def test_the_upload_body(self):
        body = credentials.multipart({"provider": "local", "name": "hub.pem"}, "file", "hub.pem", b"-----BEGIN CERTIFICATE-----\n", "B")
        self.assertIn(b'Content-Disposition: form-data; name="provider"\r\n\r\nlocal\r\n', body)
        self.assertIn(b'name="file"; filename="hub.pem"', body)
        self.assertTrue(body.endswith(b"--B--\r\n"))


@unittest.skipUnless(HAVE_CRYPTO, "python3-cryptography is not installed")
class AesGcmWireFormatTest(unittest.TestCase):
    """AesGcmWireFormatTest ported, and one vector the Bridge's own construction made."""

    KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    def test_encrypted_output_has_a_12_byte_nonce_and_a_16_byte_tag(self):
        wire = crypto.encrypt(b"test", self.KEY)
        self.assertEqual(len(wire), 12 + 4 + 16)
        self.assertEqual(len(crypto.encrypt(bytes(range(100)), self.KEY)), 128)

    def test_round_trip_and_random_nonces(self):
        text = "MAYDAY MAYDAY requesting evacuation at checkpoint bravo"
        self.assertEqual(crypto.decrypt_from_base64(crypto.encrypt_to_base64(text, self.KEY), self.KEY), text)
        self.assertNotEqual(crypto.encrypt(b"x", self.KEY)[:12], crypto.encrypt(b"x", self.KEY)[:12])

    def test_a_text_the_bridge_encrypted_opens(self):
        # internal/engine/transform.go encryptAESGCM with the nonce 000102...0b (a Go program, 29 Sep 2026)
        self.assertEqual(crypto.decrypt_from_base64("AAECAwQFBgcICQoL0kvJPXaIUWHuoqZ9V4uV7nuCNI/pwgQo/xPd5EsnPE4TdHqtVdeUmU0=", self.KEY), "SOS position 47.3N 122.5W")
        self.assertEqual(crypto.encrypt(b"SOS position 47.3N 122.5W", self.KEY, nonce=bytes(range(12))),
                         __import__("base64").b64decode("AAECAwQFBgcICQoL0kvJPXaIUWHuoqZ9V4uV7nuCNI/pwgQo/xPd5EsnPE4TdHqtVdeUmU0="))

    def test_the_failures_say_why(self):
        with self.assertRaises(crypto.CryptoError):
            crypto.decrypt_from_base64("not base64 !!", self.KEY)
        with self.assertRaises(crypto.CryptoError):
            crypto.decrypt_from_base64(crypto.encrypt_to_base64("x", self.KEY), "00" * 32)
        with self.assertRaises(crypto.CryptoError):
            crypto.encrypt_to_base64("x", "abc")

    def test_the_key_comes_from_the_bridges_links(self):
        links = [{"id": "mesh_0", "egress_transforms": "[]"}, {"id": "sms_0", "egress_transforms": '[{"type":"encrypt","params":{"key":"' + self.KEY + '"}},{"type":"base64"}]'}]
        self.assertEqual(crypto.key_from_links(links), self.KEY)
        self.assertEqual(crypto.key_from_links([{"egress_transforms": '[{"type":"encrypt","params":{"key_ref":"k1"}}]'}]), "")
        self.assertEqual(crypto.key_from_links([{"egress_transforms": "garbage"}]), "")


class NodeLogTest(unittest.TestCase):
    def test_a_daemon_line(self):
        line = nodelog.parse_daemon("INFO  | 23:56:38 1890.659 [DeviceTelemetry] Sending local stats: uptime=1890", 0)
        self.assertEqual(nodelog.format_line(line), "23:56:38 INFO [DeviceTelemetry] Sending local stats: uptime=1890")
        plain = nodelog.parse_daemon("WARN  | 00:00:13 2105.671 Tell client new packets 63", 0)
        self.assertEqual(nodelog.format_line(plain), "00:00:13 WARN Tell client new packets 63")
        self.assertEqual(nodelog.tone(plain), "amber")
        self.assertIsNone(nodelog.parse_daemon("   ", 0))
        odd = nodelog.parse_daemon("something else", 0)
        self.assertEqual(odd["message"], "something else")

    def test_a_record_from_the_bridge(self):
        line = nodelog.parse_record({"time": 0, "level": "ERROR", "source": "IridiumPipe", "message": "no answer\r\n"}, 0)
        self.assertTrue(nodelog.format_line(line).endswith(" ERROR [IridiumPipe] no answer"))
        self.assertEqual(nodelog.tone(line), "red")

    def test_the_buffer_holds_while_paused_and_keeps_2000(self):
        buffer = nodelog.Buffer(capacity=3)
        buffer.add([nodelog.parse_daemon(f"INFO  | 00:00:0{i} 1.0 m{i}", 0) for i in range(2)])
        buffer.pause()
        buffer.add([nodelog.parse_daemon("INFO  | 00:00:05 1.0 held", 0)])
        self.assertEqual(len(buffer.kept), 2)
        buffer.resume()
        self.assertEqual([l["message"] for l in buffer.kept], ["m0", "m1", "held"])
        buffer.add([nodelog.parse_daemon("INFO  | 00:00:06 1.0 last", 0)])
        self.assertEqual([l["message"] for l in buffer.kept], ["m1", "held", "last"])
        self.assertIn("00:00:06 INFO last", buffer.text())
        buffer.clear()
        self.assertEqual(buffer.text(), "")
        self.assertEqual(nodelog.CAPACITY, 2000)


if __name__ == "__main__":
    unittest.main()
