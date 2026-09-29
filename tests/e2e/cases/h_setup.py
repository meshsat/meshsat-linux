# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup (SetupScreen.kt:60-160) and Your MeshSat node (SettingsScreen.kt:384-525 and this
edition's cover and device cards): Android's three groups and every row's words, the state lines
following the Bridge, the cover card's states and its button, the device card, the watchdog's
banner when the cover's radio stops answering."""
import json
import os

SCENARIO = "mesh-only"
ROWS = ("Get connected", "Your MeshSat node", "Satellite", "Hub", "SMS", "Using MeshSat", "Safety", "SOS, check-in timer, zones", "Messaging",
        "Encryption, compression, quick messages", "Maps", "Offline maps for when there is no internet", "Ham radio, TAK and Reticulum",
        "Other networks MeshSat can bridge", "Mesh radio settings", "Region, channels, transmit power", "For experts", "Advanced",
        "Routing, links, queue, logs, diagnostics", "About")


def setup(ctx, scenario: str) -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("setup")
    ctx.app.refresh()
    ctx.tree.wait_text("Get connected", timeout=10)


def case_a_the_rows_in_androids_words(ctx):
    setup(ctx, "mesh-only")
    texts = ctx.tree.texts()
    at = -1
    for words in ROWS:
        assert words in texts[at + 1:], f"{words!r} missing or out of Android's order"
        at = texts.index(words, at + 1)
    assert any(t.startswith("MeshSat Linux ") for t in texts), "About's version line"
    for words in ("Connected", "No modem on this radio", "Not set up. Scan the Hub's QR code."):
        ctx.tree.wait_text(words, timeout=8)
    ctx.shot("setup")


def case_b_the_state_lines_follow_the_bridge(ctx):
    setup(ctx, "all-four")
    for words in ("Modem ready, signal 3 of 5", "Allowed"):
        ctx.tree.wait_text(words, timeout=10)
    assert ctx.tree.count_text("Connected") >= 2, "the node and the Hub rows both connected"
    setup(ctx, "hub-set-up")
    ctx.tree.wait_text("Connecting", timeout=10)


def case_c_the_cover_card(ctx):
    ctx.bridge.scenario("mesh-only")
    ctx.app.open("setup/node")
    ctx.app.refresh()
    ctx.tree.wait_text("The LoRa back cover", timeout=10)
    for words in ("Status", "Connected", "Firmware", "Node ID", "!52cb81e7", "This device", "A node over Bluetooth"):
        if words == "A node over Bluetooth":
            assert not ctx.tree.has_text(words), "cover mode says Bluetooth"
            continue
        ctx.tree.wait_text(words, timeout=8)
    ctx.tree.find("button", name="Restart the node")
    ctx.tree.find("button", name="Look for a LoRa back cover again")
    ctx.app.mark()
    ctx.tree.click("Restart the node")
    ctx.app.wait_toast("Starting the node", timeout=5)
    assert ["pkexec", "systemctl", "restart", "meshtasticd.service", "meshsat-bridge.service"] in ctx.app.commands(), ctx.app.commands()
    ctx.shot("node-cover")


def case_d_the_watchdog_banner(ctx):
    """This edition's own banner: the cover's radio stopped answering; a tap opens the node's page."""
    ctx.bridge.scenario("mesh-only")
    status = os.path.join(ctx.app.work, "status.json")
    with open(status, "w", encoding="utf-8") as handle:
        json.dump({"radio": "radio-not-answering", "message": "The radio in the back cover stopped answering. Re-seat the cover."}, handle)
    try:
        ctx.app.open("home")
        ctx.app.refresh()
        banner = ctx.tree.find("button", contains="The radio in the back cover stopped answering.", timeout=12)
        ctx.shot("watchdog-banner")
        banner.do("click")
        ctx.tree.wait_text("The LoRa back cover", timeout=8)
    finally:
        with open(status, "w", encoding="utf-8") as handle:
            json.dump({"radio": "ok", "message": "The radio answers."}, handle)
        ctx.app.refresh()
