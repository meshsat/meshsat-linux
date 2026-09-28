# SPDX-License-Identifier: GPL-3.0-or-later
"""The message queue's words (model/deliveries.py) held up against Android's DeliveryScreen.kt:
DeliveryProblemTextTest ported case for case, then the groups, the dialogs and the facts."""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from meshsat.model import deliveries as d  # noqa: E402
from meshsat.model import words  # noqa: E402

NOW = 1_800_000_000.0


def delivery(**more) -> dict:
    out = {"id": 7, "msg_ref": "m-7", "channel": "iridium_0", "status": "queued", "priority": 1, "text_preview": "Position report", "retries": 0, "max_retries": 10,
           "last_error": "", "ttl_seconds": 0, "qos_level": 1, "seq_num": 0, "created_at": "2027-01-15 10:00:00", "updated_at": "2027-01-15 10:00:00"}
    out.update(more)
    return out


class DeliveryProblemTextTest(unittest.TestCase):
    """What the queue tells a person about why a message has not gone (MESHSAT-615)."""

    def test_a_radio_out_of_reach_is_not_described_as_waiting_for_a_satellite(self):
        text = d.problem_text("Could not hand the message to the modem")
        self.assertIn("cannot reach the node's radio", text)
        self.assertIn("not for a satellite", text)

    def test_no_network_service_says_a_satellite_is_what_it_waits_for(self):
        text = d.problem_text("Not sent: status 32, no network service, MOMSN 233")
        self.assertIn("found no network", text)
        self.assertIn("satellite", text)

    def test_the_errors_the_app_did_not_write_are_passed_through_capitalised(self):
        self.assertTrue(d.problem_text("something odd happened").startswith("Something"))
        self.assertEqual(d.problem_text(""), "")
        self.assertIn("You cancelled", d.problem_text("cancelled"))

    def test_the_other_written_reasons(self):
        self.assertEqual(d.problem_text("cancelled: exceeded retry limit (10)"), "Stopped after too many tries.")
        self.assertEqual(d.problem_text("TTL expired at 10:00"), "It waited too long and expired.")
        self.assertEqual(d.problem_text("egress rules denied"), "A rule on this link blocked it.")
        self.assertEqual(d.problem_text("recovered after restart"), "The app restarted while sending it, so it is tried again.")


class StatesAndGroupsTest(unittest.TestCase):
    def test_the_five_groups_count_androids_statuses(self):
        rows = [delivery(id=i, status=s) for i, s in enumerate(("queued", "retry", "held", "sending", "sent", "delivered", "failed", "dead", "expired", "denied", "cancelled"))]
        self.assertEqual(d.group_counts(rows), {"queued": 3, "sending": 1, "sent": 2, "failed": 1, "dead": 4})
        self.assertEqual([d.group_label(k) for k, _ in d.GROUPS], ["Waiting", "Sending", "Sent", "Failed", "Gave up"])

    def test_a_cancelled_message_says_so_instead_of_gave_up(self):
        row = delivery(status="dead", last_error="cancelled")
        self.assertEqual(d.state_text(row), "Cancelled")
        self.assertEqual(d.state_tone(row), "muted")
        self.assertEqual(d.state_text(delivery(status="dead", last_error="cancelled: exceeded retry limit")), "Gave up")
        self.assertEqual(d.state_text(delivery(status="retry")), "Waiting to retry")
        self.assertEqual(d.state_text(delivery(status="held")), "On hold until the link is back")

    def test_cancel_and_retry_follow_the_status(self):
        for status in ("queued", "retry", "held"):
            self.assertTrue(d.can_cancel(delivery(status=status)), status)
            self.assertFalse(d.can_retry(delivery(status=status)), status)
        self.assertFalse(d.can_cancel(delivery(status="sending")))
        for status in ("failed", "dead"):
            self.assertTrue(d.can_retry(delivery(status=status)), status)
        self.assertFalse(d.can_retry(delivery(status="expired")))

    def test_filters_by_group_and_link(self):
        rows = [delivery(id=1, status="queued", channel="iridium_0"), delivery(id=2, status="failed", channel="sms_0"), delivery(id=3, status="sent", channel="mesh_0")]
        self.assertEqual([r["id"] for r in d.filtered(rows, "failed", None)], [2])
        self.assertEqual([r["id"] for r in d.filtered(rows, None, "mesh_0")], [3])
        self.assertEqual([r["id"] for r in d.filtered(rows, "queued", "sms_0")], [])
        self.assertEqual(d.channels(rows), ["iridium_0", "mesh_0", "sms_0"])
        self.assertEqual(d.empty_text([]), "No messages here yet. Messages you send, and messages your rules pass on, show up here.")
        self.assertEqual(d.empty_text(rows), "No messages match this filter.")

    def test_urgency_and_guarantee_words(self):
        self.assertEqual([d.urgency_label(p) for p in (0, 1, 2, 10)], ["Critical", "Normal", "Low", "Low"])
        self.assertEqual([d.guarantee_label(q) for q in (0, 1, 2)], ["Try once", "Keep trying", "Keep trying (high)"])
        self.assertEqual(d.ack_text("pending"), "Waiting for confirmation")
        self.assertEqual(d.ack_text("acked"), "Confirmed received")
        self.assertEqual(d.ack_text("nacked"), "Refused by the other end")
        self.assertEqual(d.ack_text("timeout"), "No confirmation came back")

    def test_tries_text(self):
        self.assertIsNone(d.tries_text(delivery(retries=0)))
        self.assertEqual(d.tries_text(delivery(retries=2, max_retries=3)), "Retried 2 of 3 times")
        self.assertEqual(d.tries_text(delivery(retries=1, max_retries=0)), "Retried 1 time")


class CardAndDialogWordsTest(unittest.TestCase):
    def test_the_card_meta_line(self):
        row = delivery(priority=0, retries=2, max_retries=10, ack_status="pending", created_at="2027-01-15 09:56:00")
        now = words.stamp_epoch("2027-01-15 10:00:00")
        self.assertEqual(d.card_meta(row, now), "4 min ago · Critical · Retried 2 of 10 times · Waiting for confirmation")

    def test_a_problem_is_red_only_when_the_message_gave_up_by_itself(self):
        self.assertEqual(d.problem_line(delivery(status="sent", last_error="anything")), ("", "muted"))
        self.assertEqual(d.problem_line(delivery(status="failed", last_error="Could not hand the message to the modem"))[1], "red")
        self.assertEqual(d.problem_line(delivery(status="dead", last_error="cancelled")), ("You cancelled it.", "muted"))
        self.assertEqual(d.problem_line(delivery(status="retry", last_error="Not sent: no network service"))[1], "muted")

    def test_the_retry_and_cancel_questions(self):
        sat = d.request_dialog(delivery(channel="iridium_0"), True)
        self.assertEqual(sat["title"], "Retry by satellite?")
        self.assertEqual(sat["body"], "Each satellite attempt that gets through uses at least 1 credit. The message goes back in the queue and is sent at the next chance.")
        self.assertEqual((sat["ok"], sat["cancel"]), ("Retry", "Not now"))
        sms = d.request_dialog(delivery(channel="sms_0"), True)
        self.assertEqual(sms["title"], "Send again by SMS?")
        self.assertEqual(sms["body"], "Your carrier may charge for the text. The message goes back in the queue and is sent when SMS is working.")
        mesh = d.request_dialog(delivery(channel="mesh_0"), True)
        self.assertEqual((mesh["title"], mesh["body"]), ("Send again by Mesh?", "The message goes back in the queue and is sent when Mesh is working."))
        cancel = d.request_dialog(delivery(channel="iridium_0"), False)
        self.assertEqual(cancel, {"title": "Cancel this message?", "body": "It will not be sent by Satellite. You can retry it later from the queue.", "ok": "Cancel message", "cancel": "Keep it"})

    def test_what_the_user_is_told_afterwards(self):
        row = delivery(channel="iridium_0")
        self.assertEqual(d.applied_text(row, True), "Back in the queue for Satellite")
        self.assertEqual(d.applied_text(row, False), "Cancelled. It will not be sent by Satellite.")
        self.assertEqual(d.applied_text(row, False, changed=False), "Nothing to cancel: it has already been sent or stopped.")
        self.assertEqual(d.failed_text("boom"), "That did not work: boom")
        self.assertEqual(d.failed_text(None), "That did not work: unknown error")

    def test_the_details_facts_and_hidden_rows(self):
        now = words.stamp_epoch("2027-01-15T10:00:00Z")
        row = delivery(retries=1, max_retries=3, last_error="cancelled", ack_status="acked", expires_at="2027-01-15T11:30:00Z", rule_id=4, seq_num=12, ttl_seconds=600, custody_id="abc")
        facts = d.facts(row, now)
        self.assertEqual(facts[0], ("Status", "Waiting", "amber"))
        self.assertEqual(facts[1], ("Urgency", "Normal", None))
        self.assertTrue(facts[2][1].startswith("4 min ago, ") or facts[2][1].startswith("just now, ") or "min ago" in facts[2][1], facts[2])
        self.assertIn(("Tries", "Retried 1 of 3 times", None), facts)
        self.assertIn(("Problem", "You cancelled it.", None), facts)
        self.assertIn(("Confirmation", "Confirmed received", None), facts)
        self.assertIn(("Gives up", "in 1 h 30 min", None), facts)
        labels = [label for label, _ in d.details(row)]
        self.assertEqual(labels, ["Delivery", "Link id", "Stored status", "Priority", "Message ref", "Rule", "QoS level", "Sequence", "TTL", "ACK", "Custody", "Error"])
        self.assertIn(("QoS level", "1 (Keep trying)"), d.details(row))
        self.assertIn(("TTL", "600 s"), d.details(row))
        self.assertEqual(d.details_title(row), "Message by Satellite")

    def test_the_queue_sections(self):
        rows = [delivery(id=1, status="queued"), delivery(id=2, status="sending"), delivery(id=3, status="dead"), delivery(id=4, status="sent")]
        waiting, gave_up = d.queue_sections(rows)
        self.assertEqual([r["id"] for r in waiting], [1, 2])
        self.assertEqual([r["id"] for r in gave_up], [3])
        self.assertEqual(d.queue_count(rows), 3)
        self.assertEqual(d.section_title(True, 2), "Waiting to go out (2)")
        self.assertEqual(d.section_title(False, 1), "Did not go out (1)")


class StampTest(unittest.TestCase):
    def test_the_bridges_stamps_are_read(self):
        self.assertEqual(words.stamp_epoch("2027-01-15 10:00:00"), words.stamp_epoch("2027-01-15T10:00:00Z"))
        self.assertEqual(words.stamp_epoch("2027-01-15T10:00:00.123456789Z"), words.stamp_epoch("2027-01-15T10:00:00.123456Z"))
        self.assertIsNone(words.stamp_epoch("0001-01-01T00:00:00Z"))
        self.assertIsNone(words.stamp_epoch(""))
        self.assertIsNone(words.stamp_epoch("not a time"))
        self.assertEqual(words.stamp_epoch(1234.0), 1234.0)

    def test_local_stamp(self):
        at = words.stamp_epoch("2027-01-15T10:04:09Z")
        self.assertRegex(words.local_stamp(at, at), r"^\d\d:\d\d:09$")
        self.assertRegex(words.local_stamp(at, at + 3 * 86400), r"^1[45] Jan \d\d:\d\d:09$")


if __name__ == "__main__":
    unittest.main()
