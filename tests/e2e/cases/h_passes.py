# SPDX-License-Identifier: GPL-3.0-or-later
"""Satellite passes (PassPredictorScreen.kt, SkyChart.kt): the page with the Bridge's predictions for
the phone's position, the window and the surroundings asked again from the Bridge, the chart and its
legend, every pass in the window behind "Show the passes", the bookkeeping; and a position typed in
for a phone without a fix, kept and given to the node."""
import time

SCENARIO = "home-cards"
ENV = {"MESHSAT_APP_POSITION": "52.3676,4.9041"}


def passes(ctx) -> None:
    ctx.bridge.scenario("home-cards")
    ctx.app.open("passes")
    ctx.app.refresh()
    ctx.tree.wait_text("Your surroundings", timeout=10)


def asked(ctx, since: int) -> list:
    return [r["path"] for r in ctx.bridge.requests(since) if r["path"].startswith("/api/iridium/passes")]


def case_a_the_page_and_its_chart(ctx):
    passes(ctx)
    # The chart and its legend are drawn again when the passes arrive: wait for each word, a walk
    # taken during that redraw sees only part of the page
    for words in ("6 h", "12 h", "24 h", "48 h", "Open", "Trees", "City", "Canyon", " Pass", " Signal", " Session sent", " Session failed"):
        ctx.tree.wait_text(words, timeout=10)
    ctx.tree.wait_text("Every pass in the window (3)", timeout=12)
    assert any(t.startswith("Position from MESHSAT_APP_POSITION") for t in ctx.tree.texts()), "the position line"
    ctx.shot("passes")
    ctx.tree.click_containing("Every pass in the window")
    ctx.tree.wait_text("IRIDIUM 106", timeout=8)
    ctx.tree.find(name="Hide the passes")


def case_b_the_window_and_surroundings_ask_the_bridge_again(ctx):
    passes(ctx)
    before = ctx.bridge.count()
    ctx.tree.click("24 h")
    deadline = time.time() + 10
    while time.time() < deadline and not [p for p in asked(ctx, before) if "hours=24" in p]:
        time.sleep(0.5)
    assert [p for p in asked(ctx, before) if "hours=24" in p], asked(ctx, before)
    before = ctx.bridge.count()
    ctx.tree.click_containing("Trees")
    deadline = time.time() + 10
    while time.time() < deadline and not [p for p in asked(ctx, before) if "min_elev=20" in p]:
        time.sleep(0.5)
    assert [p for p in asked(ctx, before) if "min_elev=20" in p], asked(ctx, before)


def case_c_a_position_typed_in(ctx):
    passes(ctx)
    ctx.bridge.set("POST /api/position/fixed", {"status": "ok"})
    ctx.tree.click("Enter a position")
    ctx.tree.wait_text("Decimal degrees, as a map shows them.", timeout=10)
    ctx.tree.set_text("Latitude", "91")
    ctx.tree.set_text("Longitude", "4.4970")
    ctx.app.mark()
    ctx.tree.click_in_dialog("Use this position")
    ctx.app.wait_toast("That is not a position: latitude -90 to 90, longitude -180 to 180.", timeout=5)
    ctx.tree.set_text("Latitude", "52.1601")
    before = ctx.bridge.count()
    ctx.tree.click_in_dialog("Use this position")
    sent = ctx.bridge.wait_request("POST", "/api/position/fixed", since=before, timeout=8)
    assert sent["body"] == {"latitude": 52.1601, "longitude": 4.497, "altitude": 0}, sent["body"]
    ctx.app.wait_toast("The node carries this position now.", timeout=8)
