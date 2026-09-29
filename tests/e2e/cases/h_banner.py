# SPDX-License-Identifier: GPL-3.0-or-later
"""The node banner (NodeLinkBanner.kt): with the phone's Bluetooth off it says so first and a
tap switches it on; with the link lost it says which link and since when, and a tap opens Setup;
an SOS or an alarm test outranks it."""
import time

SCENARIO = "bluetooth-off"
HARDWARE = {"node": "bluetooth", "why": "no LoRa back cover on the pogo bus", "model": "PinePhone Pro"}
TAIL_OFF = ", so the phone cannot reach your MeshSat node. Nothing goes out by mesh or satellite. Tap to switch it on."
TAIL_LOST = ". Nothing goes out by mesh or satellite. Tap to see."


def banner(ctx, contains: str, timeout: float = 10.0) -> str:
    button = ctx.tree.find("button", contains=contains, timeout=timeout)
    return button.name


def case_bluetooth_off_is_said_first_and_a_tap_switches_it_on(ctx):
    ctx.bridge.scenario("bluetooth-off")
    ctx.app.open("home")
    ctx.app.refresh()
    name = banner(ctx, "Bluetooth is off since ")
    assert name.endswith(TAIL_OFF), name
    assert "Cannot reach" not in name, name
    ctx.tree.find("button", contains="Bluetooth is off on this phone. Switch it on to reach your node.")
    ctx.shot("bluetooth-off")
    ctx.app.mark()
    ctx.tree.click_containing("Bluetooth is off since ")
    deadline = time.time() + 5
    while time.time() < deadline and ["bluetooth", "on"] not in ctx.app.commands():
        time.sleep(0.2)
    assert ["bluetooth", "on"] in ctx.app.commands(), ctx.app.commands()


def case_a_lost_link_says_since_when_and_opens_setup(ctx):
    ctx.bridge.scenario("bluetooth-off")
    ctx.bridge.set("GET /api/mesh/ble/status", {"mode": "ready", "address": "E0:72:A1:B3:C2:ED", "name": "MSPA_c2ec", "connected": False, "pairing_pending": False,
                                                "satellite_pipe": False, "adapter_powered": True})
    ctx.app.open("people")
    ctx.app.refresh()
    name = banner(ctx, "Cannot reach your MeshSat node since ")
    assert name.endswith(TAIL_LOST), name
    ctx.tree.click_containing("Cannot reach your MeshSat node since ")
    ctx.tree.wait_text("Get connected", timeout=8)


def case_the_nodes_modem_when_the_mesh_is_up(ctx):
    ctx.bridge.scenario("bluetooth-connected")
    ctx.bridge.set("GET /api/mesh/ble/status", {"mode": "ready", "address": "E0:72:A1:B3:C2:ED", "name": "MSPA_c2ec", "connected": True, "pairing_pending": False,
                                                "satellite_pipe": True, "satellite_link_broken": True, "adapter_powered": True})
    ctx.app.open("home")
    ctx.app.refresh()
    name = banner(ctx, "Cannot reach the node's modem since ")
    assert name.endswith(TAIL_LOST), name


def case_an_sos_outranks_it(ctx):
    ctx.bridge.scenario("bluetooth-off")
    ctx.app.open("home")
    ctx.app.refresh()
    banner(ctx, "Bluetooth is off since ")
    ctx.bridge.scenario("bluetooth-off-sos")
    ctx.app.refresh()
    ctx.tree.find("button", contains="SOS is on. Tap to see where it went, or to cancel.", timeout=10)
    ctx.tree.wait_gone("Bluetooth is off since ", timeout=10)
    ctx.bridge.scenario("bluetooth-off")
    ctx.app.refresh()
    banner(ctx, "Bluetooth is off since ")
