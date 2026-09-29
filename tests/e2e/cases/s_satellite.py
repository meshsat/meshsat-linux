# SPDX-License-Identifier: GPL-3.0-or-later
"""The mailbox check and Home's queue against a real, scratch Bridge with no modem (Bridge change
B22, MESHSAT-1423): the check answers 503 and keeps "not connected" as its outcome, writes no
satellite session into the signal history, and the Satellite page shows no check to make; the
delivery stats are the list Home reads."""
import time

SCENARIO = None  # the scratch Bridge
# The modems found by the Bridge's own device search, as the phone's Bridge has them (bridge.env sets
# no port): with every serial port present on the skip list it finds none, and says so.
BRIDGE_ENV = {"MESHSAT_IRIDIUM_PORT": "auto", "MESHSAT_IMT_PORT": "auto"}


def case_the_mailbox_without_a_modem(ctx):
    got = ctx.bridge.get("/api/iridium/mailbox")
    assert got.get("running") is False and got.get("result") is None and got.get("finished_at") is None, got
    now = int(time.time())
    status, answer = ctx.bridge.call("POST", "/api/iridium/mailbox/check")
    assert status == 503, (status, answer)
    got = ctx.bridge.get("/api/iridium/mailbox")
    assert got.get("running") is False and (got.get("result") or {}).get("kind") == "not_connected" and got.get("finished_at"), got
    sessions = ctx.bridge.get(f"/api/iridium/signal/history?source=gss&from={now - 60}&to={now + 60}")
    assert not sessions, f"a satellite session was written without one: {sessions}"
    ctx.app.open("setup/satellite")
    ctx.tree.wait_text("No modem on this radio. Plug a RockBLOCK into USB-C.", timeout=15)
    assert not ctx.tree.find_all("button", name="Check Mailbox")


def case_delivery_stats_are_the_list_home_reads(ctx):
    stats = ctx.bridge.get("/api/deliveries/stats")
    # An empty queue is null (the Bridge's Go nil slice), a list of rows otherwise.
    assert stats is None or isinstance(stats, list), stats
    for row in stats or []:
        assert set(row) >= {"channel", "status", "count"} and isinstance(row["count"], int), row
    ctx.app.open("home")
    ctx.tree.wait_text("Message queue", timeout=15)
    ctx.tree.find(name="Waiting: 0", timeout=10)
