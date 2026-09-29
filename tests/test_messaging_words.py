# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Messaging and the SMS page (0.9.1) against Android: the transform chains the switches
become on the Bridge's links (MESHSAT-1412), the brevity codebook (CannedCodebookTest, ported),
the SMS gateway body that keeps the gateway's switch and secrets, and the scripted Bridge's
transforms and gateway answers that the e2e cases lean on."""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
sys.path.insert(0, HERE)

from fakebridge import FakeBridge, load_scenario  # noqa: E402
from meshsat.model import messaging as model  # noqa: E402

KEY = "0123456789abcdef" * 4


class ChainTest(unittest.TestCase):
    def test_encryption_on_the_sms_link(self):
        out, back = model.sms_chains([], [], enabled=True, auto_decrypt=True, key=KEY, compress="off", msvqsc_stages="3")
        self.assertEqual(out, [{"type": "encrypt", "params": {"key": KEY}}, {"type": "base64"}])
        self.assertEqual(back, [{"type": "decrypt", "params": {"key": KEY, "optional": "true"}}, {"type": "base64"}])
        out, back = model.sms_chains(out, back, enabled=False, auto_decrypt=False, key=KEY, compress="off", msvqsc_stages="3")
        self.assertEqual((out, back), ([], []))

    def test_a_key_that_cannot_encrypt_writes_nothing(self):
        out, back = model.sms_chains([], [], enabled=True, auto_decrypt=True, key="0123", compress="off", msvqsc_stages="3")
        self.assertEqual((out, back), ([], []))
        self.assertTrue(model.valid_key(KEY))
        self.assertFalse(model.valid_key(KEY[:-1] + "z"))
        self.assertTrue(model.valid_key(model.generate_key()))

    def test_compression_comes_before_the_encryption(self):
        out, _ = model.sms_chains([], [], enabled=True, auto_decrypt=False, key=KEY, compress="msvqsc", msvqsc_stages="4")
        self.assertEqual([s["type"] for s in out], ["msvqsc", "encrypt", "base64"])
        self.assertEqual(out[0]["params"], {"stages": "4"})
        sbd = model.link_chain([], "msvqsc", "6", text_link=False)
        self.assertEqual(sbd, [{"type": "msvqsc", "params": {"stages": "6"}}])  # a satellite link carries bytes: no base64
        self.assertEqual(model.link_chain(sbd, "off", "6", text_link=False), [])

    def test_steps_this_page_does_not_manage_stay(self):
        chain = [{"type": "smaz2"}, {"type": "encrypt", "params": {"key": KEY}}, {"type": "fec", "params": {"profile": "lora"}}, {"type": "base64"}]
        out, _ = model.sms_chains(chain, [], enabled=True, auto_decrypt=False, key=KEY, compress="msvqsc", msvqsc_stages="3")
        self.assertEqual([s["type"] for s in out], ["smaz2", "msvqsc", "encrypt", "fec", "base64"])

    def test_reading_the_links(self):
        chain = model.steps(json.dumps([{"type": "msvqsc", "params": {"stages": "8"}}, {"type": "encrypt", "params": {"key": KEY}}, {"type": "base64"}]))
        self.assertEqual(model.inline_key(chain), KEY)
        self.assertTrue(model.encrypts(chain))
        self.assertEqual(model.compression(chain), "msvqsc")
        self.assertEqual(model.stages(chain), "8")
        self.assertEqual(model.steps("not json"), [])
        self.assertEqual(model.inline_key([{"type": "encrypt", "params": {"key_ref": "sms:+31"}}]), "")
        self.assertEqual(model.chain_text([{"type": "base64"}]), '[{"type":"base64"}]')


class CannedCodebookTest(unittest.TestCase):
    """CannedCodebookTest.kt, case for case."""

    def test_default_codebook_has_30_entries(self):
        self.assertEqual(len(model.CODEBOOK), 30)

    def test_encode_produces_2_byte_wire_format(self):
        self.assertEqual(model.encode_canned(1), bytes([0xCA, 1]))

    def test_decode_default_codebook_by_id(self):
        self.assertEqual(model.decode_canned(bytes([0xCA, 1])), "Copy.")

    def test_decode_all_30_messages(self):
        for code in range(1, 31):
            self.assertTrue(model.decode_canned(model.encode_canned(code)).strip())

    def test_known_messages_match_expected_text(self):
        self.assertEqual(model.CODEBOOK[1], "Copy.")
        self.assertEqual(model.CODEBOOK[2], "Roger.")
        self.assertEqual(model.CODEBOOK[3], "Negative.")
        self.assertEqual(model.CODEBOOK[25], "SOS — need immediate help.")

    def test_unknown_codes_are_refused(self):
        for data in (bytes([0xCA, 31]), bytes([0xCB, 1]), bytes([0xCA])):
            with self.assertRaises(ValueError):
                model.decode_canned(data)

    def test_the_card(self):
        self.assertEqual(model.loaded_line(), "30 brevity codes loaded")
        self.assertEqual(model.shown_codes()[0], ("Copy.", "#1"))
        self.assertEqual(len(model.shown_codes()), 10)
        self.assertEqual(model.more_line(), "... and 20 more")


class NoRecipientTest(unittest.TestCase):
    def test_the_gateway_keeps_its_switch_and_secrets(self):
        gateway = {"enabled": True, "config": {"destination_numbers": ["+31611111111"], "webhook_in_secret": "****", "allowed_senders": ["+316"]}}
        body = model.cellular_body(gateway, " +31 612345678 ")
        self.assertEqual(body, {"enabled": True, "config": {"destination_numbers": ["+31612345678"], "webhook_in_secret": "****", "allowed_senders": ["+316"]}})
        self.assertEqual(model.cellular_body(gateway, "")["config"]["destination_numbers"], [])
        self.assertEqual(model.cellular_body(None, "+31612345678"), {"enabled": False, "config": {"destination_numbers": ["+31612345678"]}})
        self.assertEqual(model.default_number(gateway["config"]), "+31611111111")
        self.assertEqual(model.default_number({}), "")

    def test_numbers(self):
        for good in ("", "+31612345678", "0612345678", "+1 (555) 010-0100"):
            self.assertTrue(model.number_ok(good), good)
        for bad in ("abc", "+", "12"):
            self.assertFalse(model.number_ok(bad), bad)


def call(url: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"} if data else {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


class ScriptedTransformsTest(unittest.TestCase):
    """The scripted Bridge refuses what the Bridge refuses, so the H cases prove the app."""

    def setUp(self):
        self.fake = FakeBridge(load_scenario("messaging")).start()

    def tearDown(self):
        self.fake.stop()

    def test_transforms_and_the_sms_gateway(self):
        url = self.fake.url
        good = json.dumps([{"type": "encrypt", "params": {"key": KEY}}, {"type": "base64"}])
        status, record = call(url, "PUT", "/api/interfaces/cellular_0/transforms", {"egress_transforms": good})
        self.assertEqual((status, record["egress_transforms"], record["ingress_transforms"]), (200, good, "[]"))
        self.assertEqual(call(url, "PUT", "/api/interfaces/cellular_0/transforms", {"egress_transforms": json.dumps([{"type": "encrypt", "params": {"key": KEY}}])})[0], 400)
        self.assertEqual(call(url, "PUT", "/api/interfaces/cellular_0/transforms", {"egress_transforms": json.dumps([{"type": "encrypt", "params": {"key": "01"}}, {"type": "base64"}])})[0], 400)
        self.assertEqual(call(url, "PUT", "/api/interfaces/iridium_0/transforms", {"egress_transforms": json.dumps([{"type": "msvqsc", "params": {"stages": "3"}}])})[0], 200)
        self.assertEqual(call(url, "PUT", "/api/interfaces/nope_0/transforms", {"egress_transforms": "[]"})[0], 404)
        self.assertFalse(call(url, "GET", "/api/transforms/capabilities")[1]["msvqsc_encode"])
        status, gw = call(url, "GET", "/api/gateways/cellular")
        self.assertEqual((status, gw["config"]["webhook_in_secret"]), (200, "****"))
        self.assertEqual(call(url, "PUT", "/api/gateways/cellular", model.cellular_body(gw, "+31612345678"))[0], 200)
        stored = call(url, "GET", "/__fake__/state")[1]["gateways"]["cellular"]
        self.assertEqual((stored["enabled"], stored["config"]["destination_numbers"], stored["config"]["webhook_in_secret"]), (True, ["+31612345678"], "****"))
