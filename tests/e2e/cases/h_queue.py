# SPDX-License-Identifier: GPL-3.0-or-later
"""The message queue (DeliveryScreen.kt): the counts by state as filters, the link chips, the
cards, the details dialog, and a cancel or a retry that is always confirmed first. Every case
starts from the scenario queue-busy afresh (the cases change the queue). The scripted Bridge
lists the queue newest first, as the Bridge's ORDER BY created_at DESC."""
SCENARIO = "queue-busy"


def start(ctx, scenario: str = "queue-busy") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("deliveries")
    ctx.tree.wait_text("Message queue", timeout=10)


def case_counts_chips_and_cards(ctx):
    start(ctx)
    ctx.tree.wait_text("Position report", timeout=10)
    # 3 waiting (queued, retry, held), 1 sending, 2 sent, 1 failed, 3 gave up (dead, dead, expired)
    for group in ("Waiting", "Sending", "Sent", "Failed", "Gave up"):
        ctx.tree.find("button", name=group)
    labels = ctx.tree.texts()
    for figure in ("3", "1", "2"):
        assert figure in labels, (figure, labels[:40])
    ctx.tree.wait_text("Waiting to retry")
    ctx.tree.wait_text("The satellite modem found no network. It is waiting for a satellite to come over.")
    ctx.tree.wait_text("Retried 2 of 10 times")
    ctx.tree.wait_text("On hold until the link is back")
    ctx.tree.wait_text("Cancelled")
    ctx.tree.wait_text("You cancelled it.")
    ctx.tree.wait_text("Stopped after too many tries.")
    ctx.tree.wait_text("It waited too long and expired.")
    ctx.tree.wait_text("Confirmed received")
    ctx.shot("queue")
    ctx.tree.click("Failed")
    ctx.tree.wait_text("The phone cannot reach the node's radio. It is waiting for the radio, not for a satellite.")
    ctx.tree.wait_gone("Position report")
    ctx.tree.click("Failed")  # tapped again: the filter is off
    ctx.tree.wait_text("Position report")
    ctx.tree.click("SMS")
    ctx.tree.wait_text("Back by six")
    ctx.tree.wait_gone("Position report")
    ctx.tree.click("All links")
    ctx.tree.wait_text("Position report")
    ctx.tree.click("Sending")
    ctx.tree.click("SMS")
    ctx.tree.wait_text("No messages match this filter.")
    ctx.shot("no-match")
    ctx.tree.click("Sending")
    ctx.tree.click("All links")
    ctx.tree.wait_text("Position report")


def case_details_dialog_shows_the_facts_and_the_raw_fields(ctx):
    start(ctx)
    ctx.tree.click_containing("Camp reached, all well", timeout=10)
    ctx.tree.wait_text("Message by Satellite")
    ctx.tree.wait_text("Waiting to retry")
    for fact in ("Urgency", "Normal", "Added", "Tries", "Retried 2 of 10 times", "Problem"):
        ctx.tree.wait_text(fact)
    assert not ctx.tree.has_text("Message ref"), "the raw fields showed before Show details"
    ctx.tree.click("Show details")
    for fact in ("Message ref", "msg-2", "QoS level", "1 (Keep trying)", "Stored status", "retry"):
        ctx.tree.wait_text(fact)
    ctx.shot("details")
    ctx.tree.click("Hide details")
    ctx.tree.wait_gone("Message ref")
    ctx.tree.click_in_dialog("Close")
    ctx.tree.wait_gone("Message by Satellite")


def case_cancel_and_retry_are_confirmed_and_reach_the_bridge(ctx):
    start(ctx)
    ctx.tree.wait_text("Position report", timeout=10)
    ctx.app.mark()
    before = ctx.bridge.count()
    # Cancel, from the details: asked first, and "Keep it" sends nothing.
    ctx.tree.click_containing("Position report")
    ctx.tree.wait_text("Message by Satellite")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.tree.wait_text("Cancel this message?")
    ctx.tree.wait_text("It will not be sent by Satellite. You can retry it later from the queue.")
    ctx.tree.click_in_dialog("Keep it")
    assert not [r for r in ctx.bridge.requests(before) if r["method"] == "POST"], "Keep it sent a request"
    ctx.tree.click_containing("Position report")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.tree.wait_text("Cancel this message?")
    ctx.shot("cancel-asked")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.bridge.wait_request("POST", "/api/deliveries/1/cancel", since=before)
    ctx.app.wait_toast("Cancelled. It will not be sent by Satellite.")
    stored = next(d for d in ctx.bridge.state()["deliveries"] if d["id"] == 1)
    assert (stored["status"], stored["last_error"]) == ("dead", "cancelled"), stored
    ctx.tree.wait_count("You cancelled it.", 2)  # the SMS cancelled before, and this one
    # Retry by satellite: the credit, then the Bridge is asked.
    count = ctx.bridge.count()
    ctx.tree.click_containing("Weather closing in")
    ctx.tree.wait_text("Message by Satellite")
    ctx.tree.click_in_dialog("Retry")
    ctx.tree.wait_text("Retry by satellite?")
    ctx.tree.wait_text("Each satellite attempt that gets through uses at least 1 credit. The message goes back in the queue and is sent at the next chance.")
    ctx.tree.click_in_dialog("Not now")
    assert not [r for r in ctx.bridge.requests(count) if r["method"] == "POST"], "Not now sent a request"
    ctx.tree.click_containing("Weather closing in")
    ctx.tree.click_in_dialog("Retry")
    ctx.tree.click_in_dialog("Retry")
    ctx.bridge.wait_request("POST", "/api/deliveries/8/retry", since=count)
    ctx.app.wait_toast("Back in the queue for Satellite")
    # Retry by SMS: the carrier.
    ctx.tree.click_containing("Running late")
    ctx.tree.wait_text("Message by SMS")
    ctx.tree.click_in_dialog("Retry")
    ctx.tree.wait_text("Send again by SMS?")
    ctx.tree.wait_text("Your carrier may charge for the text. The message goes back in the queue and is sent when SMS is working.")
    ctx.tree.click_in_dialog("Not now")
    # A message that can be neither cancelled nor retried offers only Close.
    ctx.tree.click_containing("hello from the phone")
    ctx.tree.wait_text("Message by Mesh")
    buttons = [n.name for n in ctx.tree.dialog() if n.role == "button"]
    assert "Retry" not in buttons and "Cancel message" not in buttons, buttons
    ctx.tree.click_in_dialog("Close")


def case_a_cancel_the_bridge_refuses_says_so(ctx):
    start(ctx)
    ctx.tree.wait_text("Position report", timeout=10)
    # The message went out between the list and the tap: the Bridge answers 500.
    ctx.bridge.set("POST /api/deliveries/1/cancel", {"error": "failed to cancel delivery"}, status=500)
    ctx.app.mark()
    ctx.tree.click_containing("Position report")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.app.wait_toast("Nothing to cancel: it has already been sent or stopped.")


def case_an_empty_queue_says_so(ctx):
    start(ctx, "mesh-only")
    ctx.tree.wait_text("No messages here yet. Messages you send, and messages your rules pass on, show up here.", timeout=10)
    ctx.shot("empty")
    ctx.app.open("home")
