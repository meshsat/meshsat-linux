# SPDX-License-Identifier: GPL-3.0-or-later
"""Home follows the Bridge: the sentence, the lanes and their words (HomeLanes.kt), the SOS card."""
SCENARIO = "mesh-only"


def switch(ctx, scenario: str, expect: str, timeout: float = 8.0) -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.refresh()
    ctx.tree.wait_text(expect, timeout=timeout)


def settle(ctx) -> None:
    """Every case starts from the same place: mesh only, no SOS, no dialog left by the case before."""
    for name in ("Keep it on", "Don't send", "Cancel"):
        while any(n.role == "button" and n.name == name for n in (ctx.tree.dialog(0.5) if ctx.tree.dialogs_open() else [])):
            ctx.tree.click_in_dialog(name)
    ctx.bridge.scenario("mesh-only")
    ctx.app.open("home")
    ctx.app.refresh()
    ctx.tree.wait_text("Messages can go out by mesh.", timeout=10)


def case_sentence_and_lanes_follow_the_bridge(ctx):
    settle(ctx)
    ctx.tree.find("button", contains="Mesh 1 node Connected to meshsat-pinephone-pro. On USB power.")
    ctx.tree.find("button", contains="This radio has no satellite modem. Plug a RockBLOCK into USB-C.")
    ctx.tree.find("button", contains="Hub Scan the Hub's QR code to connect this phone.")
    ctx.shot("mesh-only")

    switch(ctx, "all-four", "Messages can go out by satellite, mesh, SMS and the Hub.")
    ctx.tree.find("button", contains="Satellite 3/5 Modem ready.")
    ctx.tree.find("button", contains="SMS 2 today Ready.")
    ctx.tree.find("button", contains="Hub Connected as msa-pinephone.")
    ctx.shot("all-four")

    switch(ctx, "hub-set-up", "Connecting to the Hub.")
    assert ctx.tree.has_text("Messages can go out by mesh."), "a Hub with settings but no word on the link must not count as a way out"

    switch(ctx, "one-node", "Messages can go out by mesh.")
    ctx.tree.find("button", contains="Mesh 0 nodes")
    ctx.bridge.scenario("mesh-only")


def case_bridge_down_shows_nothing_as_working(ctx):
    settle(ctx)
    switch(ctx, "fresh", "Nothing can send yet.", timeout=12)
    ctx.tree.wait_text("Start with your MeshSat node, below.")
    for lane in ("Satellite", "SMS", "Hub"):
        button = ctx.tree.find("button", contains=lane)
        assert "Ready" not in button.name and "Connected as" not in button.name and "Modem ready" not in button.name, f"stale lane: {button.name}"
    ctx.tree.find("button", contains="Connect a MeshSat node to use its satellite modem.")
    ctx.shot("bridge-down")
    switch(ctx, "mesh-only", "Messages can go out by mesh.", timeout=12)


def case_sos_hold_bar_asks_before_sending_when_activated_by_name(ctx):
    """A screen reader's or a test's activation never sends: it asks first (HoldToSend.kt)."""
    settle(ctx)
    ctx.tree.find("button", name="Hold 3 seconds for SOS")
    before = ctx.bridge.count()
    ctx.tree.click("Hold 3 seconds for SOS")
    ctx.tree.wait_text("Send an SOS?")
    ctx.tree.wait_text("Your position goes out on every route this phone has, and the phone keeps trying until you cancel.")
    ctx.shot("send-an-sos")
    ctx.tree.click_in_dialog("Don't send")
    ctx.tree.wait_gone("Send an SOS?")
    assert not [r for r in ctx.bridge.requests(before) if r["path"].startswith("/api/sos/activate")], "an SOS went out on a dismissed dialog"


def case_sos_confirmed_activates_and_can_be_cancelled(ctx):
    settle(ctx)
    ctx.tree.find("button", name="Hold 3 seconds for SOS")
    before = ctx.bridge.count()
    ctx.tree.click("Hold 3 seconds for SOS")
    ctx.tree.click_in_dialog("Send SOS")
    sent = ctx.bridge.wait_request("POST", "/api/sos/activate", since=before)
    assert sent["body"]["trigger"] == "hold", sent
    assert sent["body"]["message"].startswith("SOS: A MeshSat user needs help."), sent["body"]["message"]
    ctx.tree.wait_text("SOS is on since", timeout=10)
    ctx.tree.wait_text("SOS is on. Tap to see where it went, or to cancel.")
    ctx.shot("sos-on")
    ctx.tree.click("Cancel SOS")  # the card's button opens the question
    ctx.tree.wait_text("Cancel the SOS?")
    ctx.tree.click_in_dialog("Cancel SOS")
    ctx.bridge.wait_request("POST", "/api/sos/cancel", since=before)
    ctx.tree.wait_gone("SOS is on since", timeout=10)
    ctx.tree.find("button", name="Hold 3 seconds for SOS", timeout=10)
