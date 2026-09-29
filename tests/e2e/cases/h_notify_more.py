# SPDX-License-Identifier: GPL-3.0-or-later
"""The notifications of a message that did not go and of the satellite signal (GatewayService's):
one per failure in Android's words for its lane, and the signal as one notification kept up to date
in place, withdrawn when the modem goes."""
import time

SCENARIO = "mesh-only"
NOTIFIER = True


def wait_posted(ctx, since: int, check, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for posted in ctx.notifications.since(since):
            if check(posted):
                return posted
        time.sleep(0.3)
    raise AssertionError(f"no such notification; posted: {ctx.notifications.since(since)}")


def case_a_a_message_that_did_not_go(ctx):
    for channel, title in (("iridium_0", "Iridium send failed"), ("cellular_0", "SMS not sent"), ("mesh_0", "Not sent by mesh")):
        before = ctx.notifications.count()
        ctx.bridge.event({"type": "delivery_dead", "data": {"channel": channel, "last_error": "cancelled: exceeded retry limit (10)"}})
        posted = wait_posted(ctx, before, lambda p, t=title: p["summary"] == t)
        assert posted["body"] == "cancelled: exceeded retry limit (10)", posted


def case_b_the_satellite_signal_in_place(ctx):
    before = ctx.notifications.count()
    ctx.bridge.scenario("satellite-3-bars", reset_log=False)
    first = wait_posted(ctx, before, lambda p: p["summary"] == "Iridium signal 3/5")
    assert first["body"] == "RockBLOCK 000000 on this device", first  # the last six digits of the scenario's IMEI
    ctx.bridge.set("GET /api/iridium/signal", {"bars": 4, "timestamp": "2026-09-29T12:00:00Z"})
    second = wait_posted(ctx, before + 1, lambda p: p["summary"] == "Iridium signal 4/5", timeout=20)
    assert second["replaces"] == first["id"], "the signal came as a second notification, not in place"
    ctx.bridge.scenario("mesh-only", reset_log=False)
    deadline = time.time() + 20
    while time.time() < deadline and first["id"] not in ctx.notifications.closed:
        time.sleep(0.5)
    assert first["id"] in ctx.notifications.closed, "the signal stayed with the modem gone"
