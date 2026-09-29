# SPDX-License-Identifier: GPL-3.0-or-later
"""The SOS on every route that is set up (MESHSAT-1446, the owner's decision): a satellite modem
this phone has had is a route even while it is not connected; its leg waits at the Bridge and the
SOS screen says so until it goes. A blank SOS name takes the Hub callsign, as Android's
SosController, in the test text, the SOS text and the cancellation."""
SCENARIO = "mesh-only"
PREFS = {"last_modem_imei": "300434065000000"}


def settle(ctx) -> None:
    for name in ("Keep it on", "Don't send", "Not now", "Cancel"):
        while ctx.tree.dialogs_open() and any(n.role == "button" and n.name == name for n in ctx.tree.dialog(0.5)):
            ctx.tree.click_in_dialog(name)
    ctx.bridge.scenario("mesh-only")
    ctx.bridge.set("GET /api/routing/hub", {"url": "", "bridge_id": "", "callsign": "PA3XYZ", "username": "", "has_password": False, "has_cert": False,
                                            "enabled": True, "state": ""})
    ctx.bridge.set("GET /api/iridium/modem", {"connected": False, "port": "", "imei": ""})
    ctx.app.open("home")
    ctx.app.refresh()
    ctx.tree.wait_text("Messages can go out by", timeout=10)


def case_a_blank_name_takes_the_hub_callsign(ctx):
    settle(ctx)
    ctx.tree.wait_text("Sends your position by satellite and the mesh, and keeps trying until you cancel.", timeout=10)
    ctx.tree.click("Test the alarm")
    ctx.tree.wait_text("Test the alarm?")
    body = next(t for t in ctx.tree.texts() if t.startswith("The test text is"))
    assert 'The test text is "Test from PA3XYZ: checking the MeshSat alarm routes. No help needed."' in body, body
    ctx.shot("test-dialog-callsign")
    ctx.tree.click_in_dialog("Not now")
    ctx.tree.wait_gone("Test the alarm?")


def case_b_an_sos_takes_the_modem_this_phone_has_had(ctx):
    settle(ctx)
    before = ctx.bridge.count()
    ctx.tree.click("Hold 3 seconds for SOS")
    ctx.tree.click_in_dialog("Send SOS")
    sent = ctx.bridge.wait_request("POST", "/api/sos/activate", since=before)
    assert sent["body"]["routes"] == ["satellite", "mesh"], sent["body"]
    assert sent["body"]["message"].startswith("SOS: PA3XYZ needs help."), sent["body"]["message"]
    ctx.tree.wait_text("SOS is on since", timeout=10)
    ctx.tree.click("See where it went")
    ctx.tree.wait_text("Satellite, to the Hub", timeout=10)
    ctx.tree.wait_text("Mesh, everyone in range")
    ctx.app.refresh()
    ctx.tree.wait_text("Waiting to send", timeout=10)
    labels = ctx.tree.texts()
    assert labels.count("Waiting to send") >= 2, labels  # the satellite leg waits for its modem, the mesh leg in the queue
    assert "Satellite: no satellite modem has been connected to this phone yet." not in labels, labels
    ctx.shot("sos-waiting-for-the-modem")
    # The modem is back: the frame goes and the Hub confirms it
    ctx.bridge.fake.control("POST", "/__fake__/sos", {"route": "satellite", "status": "sent", "ack_status": "acked", "interface": "iridium_0",
                                                      "msg_ref": "sos-e2e-satellite"})
    ctx.app.refresh()
    ctx.tree.wait_text("Sent, and the Hub has it", timeout=15)
    ctx.shot("sos-satellite-sent")
    ctx.tree.click("Cancel SOS: I am safe")
    ctx.tree.wait_text("Cancel the SOS?")
    ctx.tree.click_in_dialog("Cancel SOS")
    cancel = ctx.bridge.wait_request("POST", "/api/sos/cancel", since=before)
    assert cancel["body"] == {"message": "Alarm cancelled: PA3XYZ is safe and needs no help now."}, cancel["body"]
    ctx.tree.wait_text("SOS cancelled at", timeout=10)
    ctx.app.open("home")
