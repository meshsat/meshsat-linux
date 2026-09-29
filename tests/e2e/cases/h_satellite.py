# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Satellite (SettingsScreen.kt:528-733) for the RockBLOCK 9603 on USB-C: the status in
Android's words, the modem's own rows without a port, Poll Signal's "Signal: N/5", the mailbox
button; the 9704 folded away until one is there, then its card, its signal and Disconnect."""
SCENARIO = "satellite-3-bars"
IMT = {"connected": True, "port": "/dev/ttyUSB5", "model": "RockBLOCK 9704", "imei": "300534061111110", "type": "imt", "firmware": "1.2.3"}


def satellite(ctx, scenario: str = "satellite-3-bars") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("setup/satellite")
    ctx.app.refresh()


def case_the_usb_modem_in_androids_words(ctx):
    satellite(ctx)
    ctx.tree.wait_text("Satellite modem on USB-C", timeout=10)
    ctx.tree.wait_text("Connected (Signal: 3/5)", timeout=10)
    for words in ("Status", "Model", "RockBLOCK 9603", "IMEI", "300434065000000"):
        assert ctx.tree.has_text(words), f"missing: {words!r}"
    assert not ctx.tree.has_text("Port"), "Android has no Port row"
    assert not ctx.tree.has_text("Node health"), "the invented Node health card is back"
    ctx.tree.find("button", name="Check Mailbox")
    ctx.shot("satellite-connected")
    ctx.app.mark()
    ctx.tree.click("Poll Signal")
    ctx.app.wait_toast("Signal: 3/5", timeout=10)
    satellite(ctx, "mesh-only")
    ctx.tree.wait_text("No modem on this radio. Plug a RockBLOCK into USB-C.", timeout=10)
    assert not ctx.tree.find_all("button", name="Check Mailbox"), "the mailbox is offered without a modem"
    assert not ctx.tree.find_all("button", name="Poll Signal")


def case_the_9704_folds_away_until_there(ctx):
    satellite(ctx)
    ctx.tree.wait_text("Connected (Signal: 3/5)", timeout=10)
    assert not ctx.tree.has_text("RockBLOCK 9704 (separate modem)")
    ctx.tree.click("Using a RockBLOCK 9704 instead? Set it up")
    ctx.tree.wait_text("RockBLOCK 9704 (separate modem)", timeout=8)
    ctx.tree.wait_text("Disconnected")
    ctx.tree.wait_text("Plug a RockBLOCK 9704 into USB-C. The Bridge finds it by itself.")
    ctx.bridge.set("GET /api/iridium/modem?type=imt", IMT)
    ctx.bridge.set("GET /api/iridium/signal/fast?type=imt", {"bars": 2})
    ctx.bridge.set("GET /api/iridium/signal?type=imt", {"bars": 2})
    ctx.bridge.set("POST /api/interfaces/iridium_imt_0/unbind", {"status": "unbound"})
    ctx.tree.wait_text("Ready (Signal: 2/5)", timeout=15)
    for words in ("300534061111110", "Firmware", "1.2.3"):
        assert ctx.tree.has_text(words), f"missing: {words!r}"
    assert not ctx.tree.has_text("Using a RockBLOCK 9704 instead? Set it up")
    ctx.shot("satellite-9704")
    ctx.app.mark()
    buttons = ctx.tree.find_all("button", name="Poll Signal")
    assert len(buttons) == 2, "each modem has its own Poll Signal"
    buttons[1].do()
    ctx.app.wait_toast("9704 Signal: 2/5", timeout=10)
    before = ctx.bridge.count()
    ctx.tree.click("Disconnect")
    ctx.bridge.wait_request("POST", "/api/interfaces/iridium_imt_0/unbind", since=before, timeout=8)
