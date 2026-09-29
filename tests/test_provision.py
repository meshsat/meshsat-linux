# SPDX-License-Identifier: GPL-3.0-or-later
"""Hub provisioning (0.11.0) against MeshSat Android v2.19.4: ProvisionLinkTest and
ProvisionClaimRetryTest ported, and the claim's answers (the Hub's 404, 410, 429, 503 with
Retry-After, a 200 that is not JSON, no connection) against a scripted Hub."""
import base64
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))

from meshsat.model import provision as pv  # noqa: E402

NONCE = "0123456789abcdef0123456789abcdef"
LINK = f"meshsat://provision/msa-flaneur/{NONCE}?hub=hub.meshsat.net"
BUNDLE = {"v": "1", "bid": "msa-flaneur", "mqtt": "wss://mqtt-hub.meshsat.net/mqtt", "user": "msa-flaneur", "pass": "s3cret", "cert": "CERT", "key": "KEY",
          "ca": "CA", "cert_exp": "2027-09-29T00:00:00Z", "ret_tcp": "rns.meshsat.net:4242", "mqtt_topic_prefix": "meshsat", "dir_sign_pub": "ab"}


class ProvisionLinkTest(unittest.TestCase):
    """app/src/test/java/net/meshsat/android/ProvisionLinkTest.kt"""

    def test_nonce_link_yields_bridge_nonce_and_claim_host(self):
        self.assertEqual(pv.parse_link(LINK), {"bridge_id": "msa-flaneur", "nonce": NONCE, "hub_host": "hub.meshsat.net"})

    def test_inline_bundle_link_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            pv.parse_link("meshsat://provision/eyJicmlkZ2VfaWQiOiJ4In0")
        self.assertEqual(str(caught.exception), "Inline provisioning codes must be scanned in Settings")

    def test_link_without_a_claim_host_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            pv.parse_link(f"meshsat://provision/msa-flaneur/{NONCE}?hub=")
        self.assertEqual(str(caught.exception), "Missing hub host")

    def test_malformed_nonce_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            pv.parse_link("meshsat://provision/msa-flaneur/not-a-nonce?hub=hub.meshsat.net")
        self.assertEqual(str(caught.exception), "Invalid nonce: must be 32 hex chars")

    def test_other_schemes_are_refused(self):
        with self.assertRaises(ValueError) as caught:
            pv.parse_link(f"https://hub.meshsat.net/api/bridges/msa-flaneur/provision/{NONCE}")
        self.assertEqual(str(caught.exception), "Not a MeshSat provisioning link")

    def test_the_other_parse_errors(self):
        for link, message in ((f"meshsat://provision/msa-flaneur/{NONCE}/?hub=h", "Expected {bid}/{nonce}"), (f"meshsat://provision/ /{NONCE}?hub=h", "Empty bridge ID"),
                              (f"meshsat://provision/msa-flaneur/{NONCE.upper()}?hub=h", "Invalid nonce: must be 32 hex chars")):
            with self.assertRaises(ValueError) as caught:
                pv.parse_link(link)
            self.assertEqual(str(caught.exception), message, link)
        with self.assertRaises(ValueError) as caught:
            pv.parse_nonce("meshsat://provision/?hub=x")
        self.assertEqual(str(caught.exception), "Missing ?hub= parameter")
        self.assertEqual(pv.parse_link(f"meshsat://provision/b/{NONCE}?hub=a.net&x=1&hub=b.net:8443")["hub_host"], "b.net:8443")  # the last hub wins
        with self.assertRaises(ValueError):  # Android tells the forms apart by the text "?hub="
            pv.parse_link(f"meshsat://provision/b/{NONCE}?x=1&hub=a.net")


class ProvisionClaimRetryTest(unittest.TestCase):
    """app/src/test/java/net/meshsat/android/ProvisionClaimRetryTest.kt"""

    def test_the_hubs_retry_after_is_honoured_within_sane_bounds(self):
        self.assertEqual(pv.retry_delay_ms(5), 5000)
        self.assertEqual(pv.retry_delay_ms(None), 5000)
        self.assertEqual(pv.retry_delay_ms(0), 1000)
        self.assertEqual(pv.retry_delay_ms(600), 15000)
        self.assertEqual(pv.retry_delay_ms("Wed, 21 Oct 2026 07:28:00 GMT"), 5000)

    def test_a_scan_waits_long_enough_for_the_slowest_broker_measured(self):
        self.assertGreaterEqual(pv.CLAIM_WAIT_MAX_MS, 106000)


class ClaimTest(unittest.TestCase):
    def run_claim(self, answers, start_ms=0):
        clock = {"t": start_ms}
        asked, slept, waits = [], [], []

        def get(url):
            asked.append(url)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        def sleep(seconds):
            slept.append(seconds)
            clock["t"] += int(seconds * 1000)

        request = pv.parse_link(LINK)
        result = pv.claim(request, get, sleep=sleep, now_ms=lambda: clock["t"], on_wait=waits.append)
        return result, asked, slept, waits

    def test_two_503s_then_the_settings(self):
        ok = (200, {}, json.dumps(BUNDLE))
        result, asked, slept, waits = self.run_claim([(503, {"Retry-After": "5"}, ""), (503, {"retry-after": " 5 "}, ""), ok])
        self.assertEqual(asked[0], f"https://hub.meshsat.net/api/bridges/msa-flaneur/provision/{NONCE}")
        self.assertEqual((slept, waits), ([5.0, 5.0], [1, 2]))
        self.assertEqual(result["bid"], "msa-flaneur")
        self.assertNotIn("dir_sign_pub", result)

    def test_the_hubs_refusals_in_androids_words(self):
        for answer, message in (((404, {}, ""), pv.EXPIRED_404), ((410, {}, ""), pv.EXPIRED_410), ((429, {}, ""), "Hub returned HTTP 429. Try again or generate a new QR."),
                                ((200, {}, "not json"), "Cannot reach Hub at hub.meshsat.net. Check network connectivity."),
                                (ConnectionRefusedError("refused"), "Cannot reach Hub at hub.meshsat.net. Check network connectivity.")):
            with self.assertRaises(pv.ProvisionError) as caught:
                self.run_claim([answer])
            self.assertEqual(str(caught.exception), message)

    def test_it_gives_up_before_the_deadline(self):
        answers = [(503, {"Retry-After": "15"}, "")] * 20
        with self.assertRaises(pv.ProvisionError) as caught:
            self.run_claim(answers)
        self.assertEqual(str(caught.exception), pv.STILL_WAITING)

    def test_inline_bundle_and_the_bridges_body(self):
        code = pv.PREFIX + base64.urlsafe_b64encode(json.dumps(BUNDLE).encode()).decode().rstrip("=")
        self.assertTrue(pv.is_inline(code))
        bundle = pv.inline_bundle(code)
        self.assertEqual(pv.hub_body(bundle), {"url": "wss://mqtt-hub.meshsat.net/mqtt", "bridge_id": "msa-flaneur", "username": "msa-flaneur", "password": "s3cret",
                                               "tls_cert_pem": "CERT", "tls_key_pem": "KEY", "tls_ca_pem": "CA"})
        self.assertEqual(pv.ready_lines(bundle), ["Hub: wss://mqtt-hub.meshsat.net/mqtt", "Certificate expires: 2027-09-29T00:00:00Z", "Reticulum: rns.meshsat.net:4242"])
        self.assertEqual(pv.bundle_from_json('{"bid": null, "mqtt": 5}')["bid"], "null")

    def test_words(self):
        self.assertEqual(pv.waited(-3), "Waiting for the Hub, 0 s")
        self.assertEqual(pv.card_wait(12), "Getting the Hub's settings, 12 s")
        self.assertEqual(pv.ready_text("msa-flaneur"), 'This phone becomes bridge "msa-flaneur" on the Hub. Its current Hub settings are replaced.')
        self.assertEqual(pv.applied("msa-flaneur"), "Hub provisioned: msa-flaneur. Connecting to the Hub.")
        self.assertEqual(pv.rejected("x"), "Provisioning link rejected: x")
        self.assertIn("\n\nThis will overwrite existing Hub settings.", pv.link_text("b", "h"))
        self.assertEqual(pv.failed("Invalid nonce: must be 32 hex chars"), "Provisioning failed: Invalid nonce: must be 32 hex chars")


if __name__ == "__main__":
    unittest.main()
