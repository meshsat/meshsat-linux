# SPDX-License-Identifier: GPL-3.0-or-later
"""Home's cards (DashboardScreen.kt), Getting started (Onboarding.kt:128-195) and Arrange Home:
the queue from the Bridge's delivery stats, the phone's position, the satellite sky and the
mobile signal, the mailbox check that asks first and says how it went, the lanes' pages and the
satellite lane's pass line, the order kept across a restart."""
import json
import os
import time

SCENARIO = "home-cards"
# The phone's fix: 52.1620671, 4.5097404 within 12.7 m, 3.9 m high, 1.5 m/s heading 271.8°, 2 s old
ENV = {"MESHSAT_APP_FIX": "52.1620671,4.5097404,12.7,3.9,1.5,271.8,2"}
TITLES = ("SOS", "Message queue", "Your position", "Satellite signal and passes", "Satellite mailbox", "Recent messages")


def restart(ctx) -> None:
    time.sleep(1.5)  # the preferences are written a second after the last change
    ctx.app.stop()
    ctx.app.start()
    ctx.tree = ctx.app.tree
    ctx.app.mark()


def prefs(ctx) -> dict:
    path = os.path.join(ctx.app.work, "xdg", "config", "meshsat", "app.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def home(ctx, scenario: str = "home-cards") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("messages")
    ctx.app.open("home")  # Home loads its own data each time it comes on view
    ctx.app.refresh()
    ctx.tree.wait_text("Message queue", timeout=10)


def order(ctx) -> list:
    texts = ctx.tree.texts()
    return sorted((texts.index(t), t) for t in TITLES if t in texts)


def case_a_getting_started_steps_hide_and_open_their_pages(ctx):
    home(ctx)
    ctx.tree.wait_text("Getting started", timeout=10)
    ctx.tree.wait_text("1 of 2 done")
    assert not ctx.tree.find_all("button", name="Start your MeshSat node"), "a step that is done opens nothing"
    ctx.tree.find(name="Done")
    ctx.tree.find(name="To do")
    ctx.shot("getting-started")
    ctx.tree.click("Scan the Hub's QR code")
    ctx.tree.wait_text("Hub connection", timeout=8)
    ctx.app.open("home")
    ctx.tree.wait_text("Getting started", timeout=8)
    ctx.tree.click("Hide")
    ctx.tree.wait_gone("Getting started", timeout=5)
    time.sleep(1.5)
    assert prefs(ctx).get("checklist_dismissed") is True


def case_b_cards_follow_the_bridge(ctx):
    home(ctx)
    # Message queue: the bars and the four counts from GET /api/deliveries/stats
    for name in ("Satellite: 3 waiting", "Mesh: 1 waiting", "SMS: 1 waiting", "Waiting: 4", "Sending: 1", "Failed: 3", "Gave up: 4"):
        ctx.tree.find(name=name, timeout=10)
    # Your position: the phone's own fix, in Android's words
    ctx.tree.wait_text("52.16207, 4.50974")
    assert any(t.startswith("within 12 m, ") for t in ctx.tree.texts()), [t for t in ctx.tree.texts() if "within" in t]
    ctx.tree.wait_text("Height 3 m. moving 5.4 km/h, heading 271°.")
    # The sky card, its legend, and the mobile signal
    ctx.tree.wait_text("Satellite signal and passes")
    for words in ("3 h back, 3 h ahead", " Pass", " Signal", " Session"):
        assert ctx.tree.has_text(words), f"the sky card's legend lacks {words!r}"
    ctx.tree.wait_text("Mobile signal, last 6 hours")
    texts = ctx.tree.texts()
    assert any(t.startswith("min: ") and t.endswith(" dBm") for t in texts) and any(t.startswith("avg: ") for t in texts) and any(t.startswith("max: ") for t in texts)
    assert not ctx.tree.has_text("Signal history"), "the old SNR chart is still there"
    # Recent messages: the newest first, the transport in words, the arrow of the direction
    ctx.tree.wait_text("mew")
    texts = ctx.tree.texts()
    assert texts.index("mew") < texts.index("hello from the phone") < texts.index("first light"), "not newest first"
    assert "↓" in texts and "↑" in texts and "Mesh" in texts
    ctx.shot("cards")
    ctx.tree.click("Satellite signal and passes")
    ctx.tree.wait_text("Satellite passes", timeout=8)
    ctx.app.open("home")
    ctx.tree.click("Open the queue")
    ctx.tree.wait_text("Waiting", timeout=8)
    # Without passes, readings or history the two charts go
    home(ctx, "mesh-only")
    ctx.tree.wait_gone("Satellite signal and passes", timeout=10)
    assert not ctx.tree.has_text("Mobile signal, last 6 hours")


def case_c_the_mailbox_check_asks_first_and_says_how_it_went(ctx):
    home(ctx)
    ctx.tree.wait_text("Satellite mailbox", timeout=10)
    checks = ctx.bridge.state()["mailbox_checks"]
    ctx.tree.click("Check Mailbox")
    ctx.tree.wait_text("Check the satellite mailbox?", timeout=15)
    ctx.tree.click_in_dialog("Cancel")
    time.sleep(1.5)
    assert ctx.bridge.state()["mailbox_checks"] == checks, "a check went out after Cancel"
    ctx.tree.click("Check Mailbox")
    ctx.tree.wait_text("Check the satellite mailbox?", timeout=15)
    ctx.tree.click_in_dialog("Check")
    ctx.tree.wait_text("No new messages.", timeout=15)
    assert ctx.bridge.state()["mailbox_checks"] == checks + 1
    ctx.shot("mailbox-checked")
    ctx.bridge.set("_mailbox_next", {"kind": "checked", "received": 1, "still_queued": 2})
    ctx.tree.click("Check Mailbox")
    ctx.tree.wait_text("Check the satellite mailbox?", timeout=15)
    ctx.tree.click_in_dialog("Check")
    ctx.tree.wait_text("1 message received. 2 more waiting.", timeout=15)
    # The Satellite page shows the same outcome: the Bridge keeps it
    ctx.app.open("setup/satellite")
    ctx.tree.wait_text("1 message received. 2 more waiting.", timeout=10)
    ctx.bridge.set("_mailbox_next", {"kind": "session_failed", "mo_status": 32})
    ctx.tree.click("Check Mailbox")
    ctx.tree.wait_text("Check the satellite mailbox?", timeout=15)
    ctx.tree.click_in_dialog("Check")
    ctx.tree.wait_text("No network: the modem sees no satellite. No credit used.", timeout=15)
    assert ctx.bridge.state()["mailbox_checks"] == checks + 3


def case_d_lanes_open_androids_pages(ctx):
    home(ctx)
    for lane, title in (("Satellite 3/5", "Satellite passes"), ("Mesh 1 node", "People"), ("SMS This phone cannot send SMS", "Text messages"), ("Hub Scan the Hub", "Hub connection")):
        ctx.app.open("home")
        ctx.tree.wait_text("Message queue", timeout=8)
        ctx.tree.click_containing(lane)
        ctx.tree.wait_text(title, timeout=8)
    home(ctx, "mesh-only")
    ctx.tree.click_containing("Satellite This radio has no satellite modem")
    ctx.tree.wait_text("Satellite modem on USB-C", timeout=8)


def case_e_the_satellite_lane_quotes_the_high_pass(ctx):
    home(ctx)
    ctx.tree.find("button", contains="3 messages waiting to go out. A satellite is high overhead now.", timeout=10)
    now = int(time.time())
    ctx.bridge.set("GET /api/iridium/passes", {"passes": [
        {"satellite": "IRIDIUM 112", "aos": now + 300, "los": now + 600, "duration_min": 5, "peak_elev_deg": 21.0, "peak_azimuth": 90, "is_active": False},
        {"satellite": "IRIDIUM 106", "aos": now + 755, "los": now + 1200, "duration_min": 7, "peak_elev_deg": 62.0, "peak_azimuth": 10, "is_active": False}]})
    ctx.app.open("messages")
    ctx.app.open("home")
    ctx.tree.find("button", contains="3 messages waiting to go out. Next high pass in 12 min.", timeout=10)
    ctx.bridge.set("GET /api/iridium/passes", {"passes": []})
    ctx.app.open("messages")
    ctx.app.open("home")
    ctx.tree.find("button", contains="Satellite 3/5 3 messages waiting to go out. Modem ready.", timeout=10)


def case_f_arranged_order_persists(ctx):
    home(ctx)
    ctx.tree.wait_text("Recent messages", timeout=10)
    assert [t for _i, t in order(ctx)] == list(TITLES), order(ctx)
    ctx.tree.click("Arrange Home")
    ctx.tree.wait_text("Move a card up or down. The lanes stay at the top.", timeout=15)
    assert not ctx.tree.find("button", name="Move SOS up").sensitive
    assert not ctx.tree.find("button", name="Move Recent messages down").sensitive
    for _ in range(5):
        ctx.tree.click("Move Recent messages up")
        time.sleep(0.3)
    ctx.shot("arrange")
    ctx.tree.click_in_dialog("Apply")
    ctx.tree.wait_gone("Move a card up or down.", timeout=8)
    time.sleep(0.5)
    got = [t for _i, t in order(ctx)]
    assert got[0] == "Recent messages", got
    # Cancel keeps the order as it was
    ctx.tree.click("Arrange Home")
    ctx.tree.wait_text("Move a card up or down. The lanes stay at the top.", timeout=15)
    ctx.tree.click("Move SOS down")
    ctx.tree.click_in_dialog("Cancel")
    ctx.tree.wait_gone("Move a card up or down.", timeout=8)
    assert [t for _i, t in order(ctx)] == got
    time.sleep(1.5)
    assert prefs(ctx).get("dashboard_card_order") == "activity,sos,queue,location,signals,mailbox", prefs(ctx)
    restart(ctx)
    ctx.tree.wait_text("Recent messages", timeout=15)
    ctx.tree.wait_text("Message queue", timeout=10)
    assert [t for _i, t in order(ctx)][0] == "Recent messages", order(ctx)
    assert not ctx.tree.has_text("Getting started"), "Hide did not last across a restart"
