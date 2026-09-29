# SPDX-License-Identifier: GPL-3.0-or-later
"""An SOS leg read from its delivery (model/sosrun.py), Android's SosRunTest cases ported."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import sosrun  # noqa: E402


def delivery(status: str, last_error: str = "", retries: int = 0, channel: str = "x", ack=None) -> dict:
    return {"status": status, "last_error": last_error, "retries": retries, "channel": channel, "ack_status": ack}


class SosDeliveryTest(unittest.TestCase):
    def test_each_route_reads_its_own_delivery(self):
        sat = delivery("retry", "Not sent: status 32, no network", 1)
        self.assertEqual(sosrun.state_of_delivery(sat), sosrun.WAITING)
        self.assertIn("status 32", sosrun.detail_of_delivery(sat))
        self.assertEqual(sosrun.detail_of_delivery(sat), "Trying again: Not sent: status 32, no network")
        self.assertEqual(sosrun.state_of_delivery(delivery("sent")), sosrun.SENT)
        self.assertEqual(sosrun.detail_of_delivery(delivery("queued")), "Waiting to send")
        self.assertEqual(sosrun.detail_of_delivery(delivery("sending")), "Sending now")

    def test_a_cancelled_delivery_is_stopped_not_failed(self):
        self.assertEqual(sosrun.state_of_delivery(delivery("dead", "cancelled")), sosrun.STOPPED)
        self.assertEqual(sosrun.detail_of_delivery(delivery("dead", "cancelled")), "Stopped")
        self.assertEqual(sosrun.state_of_delivery(delivery("dead", "SMS failed")), sosrun.FAILED)
        self.assertEqual(sosrun.detail_of_delivery(delivery("dead", "SMS failed")), "SMS failed")
        self.assertEqual(sosrun.detail_of_delivery(delivery("failed")), "Not sent")

    def test_a_confirmed_route_says_who_confirmed_it(self):
        sat = delivery("sent", channel="iridium_0", ack="acked")
        sms = delivery("sent", channel="cellular_0", ack="acked")
        self.assertEqual([sosrun.detail_of_delivery(d) for d in (sat, sms)], ["Sent, and the Hub has it", "Delivered to their phone"])
        self.assertEqual(sosrun.detail_of_delivery(dict(sms, channel="sms_0")), "Delivered to their phone")
        self.assertEqual([sosrun.detail_of_delivery(dict(sat, ack_status="pending")), sosrun.detail_of_delivery(dict(sms, ack_status=None))], ["Sent", "Sent"])


if __name__ == "__main__":
    unittest.main()
