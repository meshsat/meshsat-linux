# SPDX-License-Identifier: GPL-3.0-or-later
"""The node's own satellite modem (SettingsScreen.kt:528-629, Bridge change B9): the card's status
in Android's words, "Use the node's modem" handing the modem to the node and back, the modem's
rows, Node health from the node's STATS re-read every 10 s while on view and not after."""
import time

SCENARIO = "bluetooth-node-modem"
HARDWARE = {"node": "bluetooth", "why": "no LoRa back cover on the pogo bus", "model": "PinePhone Pro"}
STATUS = "GET /api/mesh/ble/status"


def satellite(ctx) -> None:
    ctx.bridge.scenario("bluetooth-node-modem")
    ctx.app.open("setup/satellite")
    ctx.app.refresh()


def ble_status(**changes) -> dict:
    out = {"mode": "ready", "address": "E0:72:A1:B3:C2:ED", "name": "MSPA_c2ec", "connected": True, "pairing_pending": False,
           "satellite_pipe": True, "satellite_enabled": True, "satellite_owner": "phone", "satellite_link_broken": False, "adapter_powered": True}
    out.update(changes)
    return out


def case_a_the_node_card_and_its_switch(ctx):
    satellite(ctx)
    ctx.tree.wait_text("Satellite modem on the node", timeout=10)
    ctx.tree.wait_text("Connected (Signal: 4/5)", timeout=10)
    for words in ("Manufacturer", "Iridium", "Model", "RockBLOCK 9603", "IMEI", "300434065000001"):
        assert ctx.tree.has_text(words), f"missing: {words!r}"
    assert not ctx.tree.has_text("Satellite modem on USB-C"), "the USB card shows beside the node's"
    ctx.tree.find("button", name="Check Mailbox")
    ctx.shot("node-modem")
    before = ctx.bridge.count()
    ctx.tree.toggle("Use the node's modem")
    put = ctx.bridge.wait_request("PUT", "/api/mesh/ble/satellite", since=before, timeout=8)
    assert put["body"] == {"enabled": False}, put["body"]
    ctx.app.refresh()
    ctx.tree.wait_text("Off: the node keeps its modem", timeout=10)
    ctx.tree.toggle("Use the node's modem")
    put = ctx.bridge.wait_request("PUT", "/api/mesh/ble/satellite", since=before + 1, timeout=8)
    ctx.app.refresh()
    ctx.tree.wait_text("Connected (Signal: 4/5)", timeout=10)


def case_b_the_status_words(ctx):
    satellite(ctx)
    ctx.tree.wait_text("Satellite modem on the node", timeout=10)
    for status, modem, words in (
            (ble_status(satellite_owner="node"), {"connected": False, "port": "", "type": "sbd"}, "The node is using its modem"),
            (ble_status(satellite_owner="none"), {"connected": False, "port": "", "type": "sbd"}, "Waiting for the node"),
            (ble_status(), {"connected": False, "port": "ble", "type": "sbd", "silent": True}, "The node's modem does not answer (still trying)"),
            (ble_status(), {"connected": False, "port": "ble", "type": "sbd"}, "Checking the modem...")):
        ctx.bridge.set(STATUS, status)
        ctx.bridge.set("GET /api/iridium/modem", modem)
        ctx.app.refresh()
        ctx.tree.wait_text(words, timeout=12)
    ctx.bridge.set(STATUS, ble_status(satellite_pipe=False, satellite_owner=""))
    ctx.bridge.set("GET /api/iridium/modem", {"connected": False, "port": "", "type": "sbd"})
    ctx.app.refresh()
    ctx.tree.wait_text("Satellite modem on USB-C", timeout=12)  # a node without the pipe: the USB card


def case_c_node_health(ctx):
    satellite(ctx)
    ctx.tree.wait_text("Node health", timeout=12)
    for words in ("Held by this phone, answers", "3 of 5, 12 s ago", "Sessions since boot", "MO 32, no network service, MOMSN 250, 4 min ago",
                  "0 of 10 sessions today, sent 0, received 0", "2 h 14 min",
                  "What the node reports about its own modem, whoever holds it. The signal here is information, never a reason to hold a send."):
        ctx.tree.wait_text(words, timeout=8)
    ctx.shot("node-health")
    mark = ctx.bridge.count()
    time.sleep(12)
    reads = [r for r in ctx.bridge.requests(mark) if r["path"] == "/api/mesh/ble/satellite/stats"]
    assert reads, "the node's report is not read again while on view"
    ctx.app.open("home")
    time.sleep(2)
    mark = ctx.bridge.count()
    time.sleep(12)
    assert not [r for r in ctx.bridge.requests(mark) if r["path"] == "/api/mesh/ble/satellite/stats"], "the report is still read with the page gone"
