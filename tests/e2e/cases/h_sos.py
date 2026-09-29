# SPDX-License-Identifier: GPL-3.0-or-later
"""Safety (SosScreens.kt): the alarm test route by route, the SOS screen, and Setup > Safety
with the emergency contacts and the check-in timer."""
import time

SCENARIO = "mesh-only"


def settle(ctx, scenario: str = "mesh-only") -> None:
    for name in ("Keep it on", "Don't send", "Not now", "Cancel"):
        while ctx.tree.dialogs_open() and any(n.role == "button" and n.name == name for n in ctx.tree.dialog(0.5)):
            ctx.tree.click_in_dialog(name)
    ctx.bridge.scenario(scenario)
    ctx.app.open("home")
    ctx.app.refresh()
    ctx.tree.wait_text("Messages can go out by", timeout=10)


def case_alarm_test_goes_route_by_route_and_settles(ctx):
    settle(ctx, "all-four")
    ctx.tree.wait_text("Messages can go out by satellite, mesh, SMS and the Hub.")
    before = ctx.bridge.count()
    ctx.tree.click("Test the alarm")
    ctx.tree.wait_text("Test the alarm?")
    body = next(t for t in ctx.tree.texts() if t.startswith("The test text is"))
    assert 'The test text is "Test from A MeshSat user: checking the MeshSat alarm routes. No help needed."' in body, body
    assert "a position report to the Hub by satellite, 1 credit; the text on the mesh; and a test event to the Hub online" in body, body
    assert body.endswith("Nobody is alarmed, and the Hub does not raise an SOS."), body
    ctx.shot("test-dialog")
    ctx.tree.click_in_dialog("Send the test")
    ctx.bridge.wait_request("POST", "/api/sos/test", since=before, timeout=10)
    # The satellite leg waits in the Bridge's queue until its session; then the Hub's receipt comes
    queued = ctx.bridge.state()["queued"]
    assert queued, "the satellite leg was not queued"
    ctx.app.open("sos")
    ctx.tree.wait_text("Waiting to send", timeout=10)
    for ref, row in queued.items():
        ctx.bridge.delivery(ref, status="sent", ack_status="acked" if str(row.get("channel", "")).startswith("iridium") else None)
    sends = [r for r in ctx.bridge.requests(before) if r["path"] == "/api/messages/send"]
    texts = {r["body"].get("gateway", "mesh"): r["body"]["text"] for r in sends}
    assert texts.get("mesh") == "Test from A MeshSat user: checking the MeshSat alarm routes. No help needed.", texts
    assert texts.get("iridium") == texts["mesh"], texts
    assert not [r for r in ctx.bridge.requests(before) if r["path"] == "/api/sos/activate"], "a test started a real SOS"
    ctx.app.open("sos")
    ctx.tree.wait_text("Alarm test", timeout=10)
    ctx.tree.wait_text("Satellite, to the Hub")
    ctx.tree.wait_text("Mesh, everyone in range")
    ctx.tree.wait_text("Hub, over the internet")
    ctx.tree.wait_text("Alarm test finished", timeout=15)
    ctx.tree.wait_text("Sent, and the Hub has it", timeout=15)
    ctx.tree.wait_text("SMS: you have no emergency contacts. Add them in Setup, Safety.")
    labels = ctx.tree.texts()
    # The satellite route confirmed by the Hub says so (SosRun.detailOf); the mesh and the Hub each "Sent"
    assert "Sent, and the Hub has it" in labels and labels.count("Sent") >= 2, labels
    ctx.shot("test-finished")
    ctx.app.open("home")
    ctx.tree.find("button", name="Hold 3 seconds for SOS", timeout=10)


def case_sos_screen_shows_where_it_went_and_the_cancellation(ctx):
    settle(ctx, "mesh-only")
    before = ctx.bridge.count()
    ctx.tree.click("Hold 3 seconds for SOS")
    ctx.tree.click_in_dialog("Send SOS")
    ctx.bridge.wait_request("POST", "/api/sos/activate", since=before)
    ctx.tree.wait_text("SOS is on since", timeout=10)
    ctx.tree.wait_text("SOS is on. Tap to see where it went, or to cancel.")
    ctx.tree.click("See where it went")
    ctx.tree.wait_text("SOS is on")
    started = next(t for t in ctx.tree.texts() if t.startswith("Started at "))
    assert started.endswith(" from this phone. Position unknown."), started
    ctx.tree.wait_text("Mesh, everyone in range")
    ctx.app.refresh()
    ctx.tree.wait_text("Not used")
    ctx.tree.wait_text("Satellite: no satellite modem has been connected to this phone yet.")
    ctx.tree.wait_text("Hub: not set up on this phone.")
    ctx.shot("sos-on")
    ctx.tree.click("Cancel SOS: I am safe")
    ctx.tree.wait_text("Cancel the SOS?")
    ctx.tree.click_in_dialog("Cancel SOS")
    ctx.bridge.wait_request("POST", "/api/sos/cancel", since=before)
    ctx.tree.wait_text("SOS cancelled at", timeout=10)
    ctx.tree.wait_text('Every route that carried the SOS is sending "Alarm cancelled: A MeshSat user is safe and needs no help now."')
    cancels = [r for r in ctx.bridge.requests(before) if r["path"] == "/api/messages/send" and "Alarm cancelled" in r["body"].get("text", "")]
    assert cancels, "no cancellation went out on the mesh"
    ctx.tree.wait_text("Cancellation: sent", timeout=10)
    ctx.shot("sos-cancelled")
    ctx.tree.click("Emergency contacts and alarm test")
    ctx.tree.wait_text("Test the alarm")
    ctx.app.open("home")


def case_safety_page_contacts_and_check_in_timer(ctx):
    settle(ctx, "sim-ready")
    ctx.app.open("setup/safety")
    ctx.tree.wait_text("Emergency contacts")
    ctx.tree.wait_text("Each one gets an SMS with your position and a map link from this phone's SIM, whenever it has a signal.")
    ctx.tree.click("Or type a number")
    ctx.tree.set_text("Name", "Anna")
    ctx.tree.set_text("Phone number, with country code", "+31 6 1234 5678")
    ctx.tree.click("Add this number")
    ctx.tree.find("button", name="Remove Anna")
    ctx.tree.wait_text("+31612345678")
    ctx.tree.click("Or type a number")  # the fields folded away after the number was added
    ctx.tree.set_text("Name", "")
    ctx.tree.set_text("Phone number, with country code", "+31 6 1234 5678")
    ctx.tree.click("Add this number")
    ctx.tree.wait_text("That number is already on the list.")
    ctx.shot("contacts")
    before = ctx.bridge.count()
    ctx.tree.toggle("Enabled")
    on = ctx.bridge.wait_request("POST", "/api/deadman", since=before)
    assert on["body"]["enabled"] is True, on
    ctx.tree.wait_text("Timeout (triggers SOS if no activity)", timeout=10)
    after_enable = ctx.bridge.count()
    ctx.tree.click("1 hour")
    hour = ctx.bridge.wait_request("POST", "/api/deadman", since=after_enable)
    assert hour["body"] == {"enabled": True, "timeout_min": 60}, hour
    ctx.app.refresh()
    ctx.tree.wait_text("selected", timeout=10)
    # Opening the page again writes nothing: a poll must never count as a check-in.
    count = ctx.bridge.count()
    ctx.app.open("home")
    ctx.app.open("setup/safety")
    ctx.app.refresh()
    time.sleep(3)
    posts = [r for r in ctx.bridge.requests(count) if r["method"] == "POST" and r["path"] == "/api/deadman"]
    assert not posts, f"opening Safety posted to the timer: {posts}"
    # The timer ran out: TRIGGERED, and a tap resets it.
    ctx.bridge.fake.deadman["triggered"] = True
    import json
    import urllib.request

    with urllib.request.urlopen(ctx.bridge.url + "/api/deadman", timeout=5) as answer:
        served = json.load(answer)
    ctx.note(f"the fake serves {served}")
    assert served.get("triggered") is True, served
    ctx.app.refresh()
    ctx.tree.find("button", name="TRIGGERED — SOS was sent. Tap to reset.", timeout=10)
    ctx.shot("triggered")
    count = ctx.bridge.count()
    ctx.tree.click("TRIGGERED — SOS was sent. Tap to reset.")
    reset = ctx.bridge.wait_request("POST", "/api/deadman", since=count)
    assert reset["body"] == {"enabled": True, "timeout_min": 60}, reset
    ctx.tree.wait_gone("TRIGGERED — SOS was sent. Tap to reset.", timeout=10)
    ctx.tree.click("Remove Anna")
    ctx.app.open("home")
