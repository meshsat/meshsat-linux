# SPDX-License-Identifier: GPL-3.0-or-later
"""The message queue against a real, scratch Bridge. The scratch Bridge's 9704 link has a port
that does not exist, so a message for it can never leave: its IMT gateway is switched on
through the API, a text is queued for it, and the app cancels it (the Bridge marks it dead,
"cancelled") and puts it back in the queue with Retry."""
import time

from driver import BridgeError

SCENARIO = None  # the scratch Bridge
LINK = "Satellite (RockBLOCK 9704)"


def delivery_of(ctx, text: str):
    return next((d for d in (ctx.bridge.get("/api/deliveries?limit=50") or []) if d.get("text_preview") == text), None)


def case_cancel_and_retry_follow_the_bridges_state(ctx):
    status, answer = ctx.bridge.call("PUT", "/api/gateways/iridium_imt", {"enabled": True, "config": {}})
    ctx.note(f"IMT gateway: {status} {answer}")
    if status != 200:
        raise BridgeError(f"the scratch Bridge would not run an IMT gateway ({status} {answer})")
    status, answer = ctx.bridge.call("POST", "/api/messages/send", {"text": "e2e queue", "gateway": "iridium_imt"})
    ctx.note(f"send: {status} {answer}")
    if status != 200:
        raise BridgeError(f"the scratch Bridge refused the satellite send ({status} {answer}): nothing to queue")
    # Past the first try (it fails at once: no modem), a retry waits 30 s: time to act without a race.
    row = None
    deadline = time.time() + 25
    while time.time() < deadline:
        row = delivery_of(ctx, "e2e queue")
        if row and row["status"] in ("retry", "held"):
            break
        time.sleep(0.5)
    ctx.note(f"delivery: {row}")
    if row is None:
        raise BridgeError("the scratch Bridge stored no delivery for the satellite send")
    if row["status"] not in ("queued", "retry", "held"):
        raise BridgeError(f"the delivery is {row['status']}, so there is nothing to cancel")
    ctx.app.open("deliveries")
    ctx.tree.wait_text("e2e queue", timeout=15)
    ctx.shot("queued")
    ctx.app.mark()
    ctx.tree.click_containing("e2e queue")
    ctx.tree.wait_text(f"Message by {LINK}")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.tree.wait_text("Cancel this message?")
    ctx.tree.wait_text(f"It will not be sent by {LINK}. You can retry it later from the queue.")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.app.wait_toast(f"Cancelled. It will not be sent by {LINK}.", timeout=10)
    stored = delivery_of(ctx, "e2e queue")
    assert (stored["status"], stored.get("last_error")) == ("dead", "cancelled"), stored
    ctx.tree.wait_text("You cancelled it.", timeout=10)
    ctx.tree.wait_text("Cancelled")
    ctx.shot("cancelled")
    ctx.tree.click_containing("e2e queue")
    ctx.tree.wait_text(f"Message by {LINK}")
    ctx.tree.click_in_dialog("Retry")
    ctx.tree.wait_text("Retry by satellite?")
    ctx.tree.click_in_dialog("Retry")
    ctx.app.wait_toast(f"Back in the queue for {LINK}", timeout=10)
    stored = delivery_of(ctx, "e2e queue")
    assert stored["status"] in ("queued", "retry", "sending"), stored
    ctx.note(f"after the retry: {stored['status']}")
    ctx.shot("retried")
    ctx.app.open("home")
