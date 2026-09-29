# SPDX-License-Identifier: GPL-3.0-or-later
"""The SOS screen (SosScreens.kt SosScreen): where an SOS went, what was not used, and the
cancellation. A module of its own, so its app has never seen a satellite modem: a modem this
phone has had is an SOS route (MESHSAT-1446), and h_sos's alarm test shows one."""
SCENARIO = "mesh-only"


def settle(ctx, scenario: str = "mesh-only") -> None:
    for name in ("Keep it on", "Don't send", "Not now", "Cancel"):
        while ctx.tree.dialogs_open() and any(n.role == "button" and n.name == name for n in ctx.tree.dialog(0.5)):
            ctx.tree.click_in_dialog(name)
    ctx.bridge.scenario(scenario)
    ctx.app.open("home")
    ctx.app.refresh()
    ctx.tree.wait_text("Messages can go out by", timeout=10)


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
    # The mesh leg waits in the Bridge's queue, then goes (MESHSAT-1447)
    ctx.tree.wait_text("Waiting to send", timeout=10)
    activate = next(r for r in ctx.bridge.requests(before) if r["path"] == "/api/sos/activate")
    assert activate["body"]["routes"] == ["mesh"], activate["body"]
    mesh_ref = next(ref for ref in ctx.bridge.state()["queued"] if ref.endswith("-mesh"))
    ctx.bridge.delivery(mesh_ref, status="sent")
    ctx.app.refresh()
    ctx.tree.wait_text("Sent", timeout=10)
    ctx.shot("sos-on")
    ctx.tree.click("Cancel SOS: I am safe")
    ctx.tree.wait_text("Cancel the SOS?")
    ctx.tree.click_in_dialog("Cancel SOS")
    cancel = ctx.bridge.wait_request("POST", "/api/sos/cancel", since=before)
    assert cancel["body"] == {"message": "Alarm cancelled: A MeshSat user is safe and needs no help now."}, cancel["body"]
    ctx.tree.wait_text("SOS cancelled at", timeout=10)
    ctx.tree.wait_text('Every route that carried the SOS is sending "Alarm cancelled: A MeshSat user is safe and needs no help now."')
    # The Bridge tells the mesh (its leg went out): a leg of its own, which the screen follows
    cancel_ref = next((ref for ref in ctx.bridge.state()["queued"] if ref.endswith("-cancel:mesh")), None)
    assert cancel_ref, "the Bridge queued no cancellation on the mesh"
    assert not [r for r in ctx.bridge.requests(before) if r["path"] == "/api/messages/send" and "Alarm cancelled" in r["body"].get("text", "")], \
        "the app told the mesh as well"
    ctx.tree.wait_text("Cancellation: waiting to send", timeout=10)
    ctx.bridge.delivery(cancel_ref, status="sent")
    ctx.tree.wait_text("Cancellation: sent", timeout=15)
    ctx.shot("sos-cancelled")
    ctx.tree.click("Emergency contacts and alarm test")
    ctx.tree.wait_text("Test the alarm")
    ctx.app.open("home")
