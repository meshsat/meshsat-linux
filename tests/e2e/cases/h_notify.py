# SPDX-License-Identifier: GPL-3.0-or-later
"""MeshSat outside its window: one notification per text in Android's words, none while the
app is in front, and the SOS notification's Cancel."""
import os
import time

SCENARIO = "mesh-only"
NOTIFIER = True


def wait_posted(ctx, since: int, timeout: float = 12.0) -> list:
    deadline = time.time() + timeout
    while time.time() < deadline:
        posted = ctx.notifications.since(since)
        if posted:
            return posted
        time.sleep(0.3)
    raise AssertionError("no notification was posted")


def case_one_notification_per_text_in_android_words(ctx):
    before = ctx.notifications.count()
    # A text arrives on the mesh: the Bridge's event ({"type", "data": {...}}, events.go).
    packet = {"dir": "rx", "portnum_name": "TEXT_MESSAGE_APP", "text": "kettle is on", "from": "!a1b3c2ec", "bearer": "lora", "time": "2026-09-28T18:00:00Z"}
    ctx.bridge.event({"type": "packet", "data": packet})
    posted = wait_posted(ctx, before)
    assert len(posted) == 1, f"{len(posted)} notifications for one text: {posted}"
    assert posted[0]["summary"] in ("Mesh: MSPA", "Mesh: !a1b3c2ec"), posted[0]
    assert posted[0]["body"] == "kettle is on", posted[0]
    # The same text again (the Bridge repeats a packet on every bearer): nothing more.
    ctx.bridge.event({"type": "packet", "data": dict(packet, bearer="mesh")})
    time.sleep(3)
    assert ctx.notifications.count() == before + 1, "a repeated packet made a second notification"


def case_no_notification_while_the_app_is_in_front(ctx):
    flag = os.path.join(os.environ["XDG_RUNTIME_DIR"], "meshsat-app-active")
    with open(flag, "w", encoding="utf-8"):
        pass
    try:
        before = ctx.notifications.count()
        ctx.bridge.event({"type": "packet", "data": {"dir": "rx", "portnum_name": "TEXT_MESSAGE_APP", "text": "seen on screen", "from": "!a1b3c2ec", "bearer": "lora", "time": "2026-09-28T18:01:00Z"}})
        time.sleep(4)
        assert ctx.notifications.count() == before, f"a notification was posted while the app is in front: {ctx.notifications.since(before)}"
    finally:
        os.remove(flag)


def case_sos_notification_offers_cancel(ctx):
    before = ctx.notifications.count()
    ctx.bridge.scenario("sos-active", reset_log=False)
    posted = wait_posted(ctx, before, timeout=15)
    sos = [p for p in posted if "SOS" in p["summary"] or "SOS" in p["body"]]
    assert sos, f"no SOS notification: {posted}"
    assert "cancel-sos" in sos[0]["actions"], sos[0]["actions"]
    count = ctx.bridge.count()
    ctx.notifications.invoke(sos[0]["id"], "cancel-sos")
    ctx.bridge.wait_request("POST", "/api/sos/cancel", since=count, timeout=10)
    ctx.bridge.scenario("mesh-only", reset_log=False)
