# SPDX-License-Identifier: GPL-3.0-or-later
"""Your MeshSat node over Bluetooth (setup.node, setup.node.pin, setup.node.device): Android's
"Bluetooth connection" card word for word (SettingsScreen.kt:384-525 at v2.19.4: Status, Firmware,
Node ID, Battery, Reboots, Mesh Nodes, Disconnect; Scan for Meshtastic devices, Found devices:,
Connect), the scan and the connect through the Bridge, a node out of reach and "Forget this node",
the PIN dialog this edition shows when a node asks to pair (Android's system shows it there), and
the "This device" card with its look-again button, in both modes. The cover card and the watchdog
banner are h_setup.py's.

Needs wip-100/patch-100-node.py (the battery with its voltage, one row per mesh node)."""
import json
import os
import time

SCENARIO = "bluetooth-connected"
HARDWARE = {"node": "bluetooth", "why": "no LoRa back cover on the pogo bus", "model": "PinePhone Pro"}
COVER = {"node": "cover", "why": "the LoRa back cover answers on the pogo bus", "model": "PinePhone Pro"}
ADDRESS = "E0:72:A1:B3:C2:ED"
# The Bridge's GET /api/mesh/ble/status (transport.BLEStatus) with no node chosen yet
IDLE = {"mode": "idle", "paired": False, "connected": False, "pairing_pending": False, "satellite_pipe": False, "adapter_powered": True}
FOUND = {"devices": [{"address": ADDRESS, "name": "MSPA_c2ec", "rssi": -55, "paired": True, "connected": False},
                     {"address": "E0:72:A1:B3:C3:A5", "name": "MSPB_c3a4", "rssi": -70, "paired": False, "connected": False}], "count": 2}


def node_page(ctx) -> None:
    ctx.app.open("setup/node")
    ctx.app.refresh()
    ctx.tree.wait_text("Bluetooth connection", timeout=10)


def after(texts: list, key: str) -> str:
    """The label right after `key`: the value of a key-value row."""
    assert key in texts, f"no {key!r} on view: {texts}"
    at = texts.index(key)
    return texts[at + 1] if at + 1 < len(texts) else ""


def deletes(ctx, since: int) -> list:
    return [r["path"] for r in ctx.bridge.requests(since) if r["method"] == "DELETE"]


def pin_field(ctx):
    """The PIN dialog's entry: it has no name of its own, so the text field of the dialog in front."""
    for node in ctx.tree.dialog(timeout=5):
        if node.role in ("text", "password text"):
            return node
    raise AssertionError(f"no PIN field in the dialog: {[(n.role, n.name) for n in ctx.tree.dialog(1)]}")


def case_a_connected_in_androids_words(ctx):
    ctx.bridge.scenario("bluetooth-connected")
    status = dict(ctx.bridge.fake.routes["GET /api/status"])
    ctx.bridge.set("GET /api/status", dict(status, reboot_count=3))
    nodes = json.loads(json.dumps(ctx.bridge.fake.routes["GET /api/nodes"]["nodes"]))
    for n in nodes:
        if n["user_id"] == "!a1b3c2ec":
            n.update(battery_level=78, voltage=3.98)  # the node's own DeviceMetrics, as /api/nodes carries them
    ctx.bridge.set("GET /api/nodes", {"nodes": nodes})
    node_page(ctx)
    ctx.tree.wait_text("Firmware", timeout=10)
    ctx.tree.wait_text("78%, 3.98 V", timeout=10)
    texts = ctx.tree.texts()
    rows = {key: after(texts, key) for key in ("Status", "Firmware", "Node ID", "Battery", "Reboots")}
    assert rows == {"Status": "Connected", "Firmware": status["firmware_version"], "Node ID": "!a1b3c2ec", "Battery": "78%, 3.98 V", "Reboots": "3"}, rows
    # "Mesh Nodes (N)" over one row per node: the long name, the short name (SettingsScreen.kt:420-448)
    assert "Mesh Nodes (2)" in texts, texts
    assert after(texts, "meshsat-pinephone-pro") == "MSPP", texts
    assert texts.count("MSPA") >= 2, "T-Deck A's long and short names"
    assert not ctx.tree.has_text("The LoRa back cover"), "the cover card shows in Bluetooth mode"
    assert not ctx.tree.find_all("button", name="Scan for Meshtastic devices"), "a scan is offered while connected"
    ctx.shot("node-bluetooth-connected")
    # Disconnect: the link goes, the bond stays (Android's Disconnect)
    ctx.bridge.set("DELETE /api/mesh/ble", {"status": "forgotten"})
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click("Disconnect")
    ctx.app.wait_toast("Disconnected", timeout=8)
    assert deletes(ctx, before) == ["/api/mesh/ble"], deletes(ctx, before)


def case_b_reboots_and_nodes_only_when_there_are_some(ctx):
    """Android shows Reboots only above 0 and the node list only once the node sent one."""
    ctx.bridge.scenario("bluetooth-connected")
    ctx.bridge.set("GET /api/status", dict(ctx.bridge.fake.routes["GET /api/status"], reboot_count=0))
    ctx.bridge.set("GET /api/nodes", {"nodes": []})
    node_page(ctx)
    ctx.tree.wait_text("Firmware", timeout=10)
    ctx.tree.wait_gone("Mesh Nodes", timeout=10)
    texts = ctx.tree.texts()
    for gone in ("Reboots", "Battery", "none yet"):
        assert gone not in texts, f"{gone!r} with nothing to show: {texts}"


def case_c_scan_found_devices_and_connect(ctx):
    ctx.bridge.scenario("bluetooth-pairing")
    ctx.bridge.set("GET /api/mesh/ble/status", IDLE)

    def slow_scan(method, path, body):  # the Bridge scans for the seconds asked; three are enough here
        time.sleep(3)
        return 200, FOUND

    with ctx.bridge.fake.lock:
        ctx.bridge.fake.routes["GET /api/mesh/ble/scan"] = slow_scan
    ctx.bridge.set("POST /api/mesh/ble/connect", {"status": "connecting", "address": ADDRESS}, status=202)
    node_page(ctx)
    ctx.tree.wait_text("Disconnected", timeout=10)
    before = ctx.bridge.count()
    ctx.tree.click("Scan for Meshtastic devices", timeout=8)
    ctx.tree.wait_text("Scanning...", timeout=3)
    assert not ctx.tree.find_all("button", name="Scan for Meshtastic devices"), "a second scan can start during the first"
    ctx.tree.wait_text("Found devices:", timeout=15)
    for words in ("MSPA_c2ec", "MSPB_c3a4"):
        ctx.tree.wait_text(words, timeout=5)
    texts = ctx.tree.texts()
    assert any(t.startswith(ADDRESS) for t in texts), f"the address under the name: {texts}"
    assert len(ctx.tree.find_all("button", name="Connect")) == 2, "one Connect per device"
    scans = [r["path"] for r in ctx.bridge.requests(before) if r["path"].startswith("/api/mesh/ble/scan")]
    assert scans == ["/api/mesh/ble/scan?seconds=8"], scans
    ctx.shot("found-devices")
    ctx.app.mark()
    ctx.tree.click_after("MSPA_c2ec", "Connect")
    ctx.app.wait_toast("Connecting to MSPA_c2ec", timeout=5)
    sent = ctx.bridge.wait_request("POST", "/api/mesh/ble/connect", since=before, timeout=8)
    assert sent["body"] == {"address": ADDRESS}, sent
    ctx.tree.wait_gone("Found devices:", timeout=5)
    # The Bridge brings the link up; the card follows its status
    ctx.bridge.set("GET /api/mesh/ble/status", dict(IDLE, mode="connecting", address=ADDRESS, name="MSPA_c2ec"))
    ctx.app.refresh()
    ctx.tree.wait_text("Connecting...", timeout=10)
    ctx.tree.wait_text("Connecting to MSPA_c2ec.", timeout=10)


def case_d_no_node_in_range(ctx):
    ctx.bridge.scenario("bluetooth-pairing")
    ctx.bridge.set("GET /api/mesh/ble/status", IDLE)
    ctx.bridge.set("GET /api/mesh/ble/scan", {"devices": [], "count": 0})
    node_page(ctx)
    ctx.tree.click("Scan for Meshtastic devices", timeout=10)
    ctx.tree.wait_text("No Meshtastic devices found. Is the node on, with Bluetooth enabled?", timeout=15)
    assert not ctx.tree.has_text("Found devices:")
    ctx.tree.find("button", name="Scan for Meshtastic devices", timeout=5)


def case_e_the_pin_dialog_when_a_node_asks_to_pair(ctx):
    ctx.bridge.scenario("bluetooth-pairing")
    ctx.bridge.set("POST /api/mesh/ble/pair", {"status": "pin entered"})
    pairing = dict(ctx.bridge.fake.routes["GET /api/mesh/ble/status"])
    node_page(ctx)
    # The node shows a six-digit PIN and the Bridge's pairing waits for it: the dialog opens by itself
    ctx.tree.wait_text("Enter the PIN shown on the node's screen.", timeout=10)
    dialog = ctx.tree.dialog()
    assert "Pair with MSPA_c2ec" in [n.name for n in dialog if n.role == "label"], [n.name for n in dialog]
    assert {"Cancel", "Pair"} <= {n.name for n in dialog if n.role == "button"}, [n.name for n in dialog if n.role == "button"]
    ctx.shot("pin-dialog")
    before = ctx.bridge.count()
    pin_field(ctx).set_text("12345")
    ctx.app.mark()
    ctx.tree.click_in_dialog("Pair")
    ctx.app.wait_toast("Enter 6 digits.", timeout=5)
    assert not [r for r in ctx.bridge.requests(before) if r["path"] == "/api/mesh/ble/pair"], "five digits went to the Bridge"
    pin_field(ctx).set_text("123456")
    ctx.app.mark()
    ctx.tree.click_in_dialog("Pair")
    ctx.app.wait_toast("Pairing", timeout=5)
    sent = ctx.bridge.wait_request("POST", "/api/mesh/ble/pair", since=before, timeout=8)
    assert sent["body"] == {"pin": "123456"}, sent
    deadline = time.time() + 5
    while time.time() < deadline and ctx.tree.dialogs_open():
        time.sleep(0.3)
    assert not ctx.tree.dialogs_open(), "the PIN dialog stayed after Pair"
    # The same pairing does not ask again by itself; the card says what waits
    ctx.app.refresh()
    time.sleep(4)
    assert not ctx.tree.dialogs_open(), "the PIN dialog came back for the same pairing"
    ctx.tree.wait_text("Pairing with MSPA_c2ec: enter the PIN shown on its screen.", timeout=8)
    ctx.tree.click("Enter the PIN")
    ctx.tree.wait_text("Enter the PIN shown on the node's screen.", timeout=5)
    count = ctx.bridge.count()
    ctx.tree.click_in_dialog("Cancel")
    ctx.tree.wait_gone("Enter the PIN shown on the node's screen.", timeout=5)
    assert not [r for r in ctx.bridge.requests(count) if r["path"] == "/api/mesh/ble/pair"], "Cancel sent a PIN"
    # A PIN the Bridge refuses: its own words
    ctx.bridge.set("POST /api/mesh/ble/pair", {"error": "no pairing is waiting for a PIN"}, status=409)
    ctx.tree.click("Enter the PIN")
    pin_field(ctx).set_text("654321")
    ctx.app.mark()
    ctx.tree.click_in_dialog("Pair")
    ctx.app.wait_toast("no pairing is waiting for a PIN", timeout=8)
    # A new pairing (the node shows a new PIN): the dialog opens by itself again
    ctx.bridge.set("GET /api/mesh/ble/status", dict(pairing, pairing_since="2026-09-28T17:05:00Z"))
    ctx.app.refresh()
    ctx.tree.wait_text("Enter the PIN shown on the node's screen.", timeout=10)
    ctx.tree.click_in_dialog("Cancel")
    # Paired and connected: the card turns to the node's own rows
    ctx.bridge.scenario("bluetooth-connected")
    ctx.app.refresh()
    ctx.tree.wait_text("Connected", timeout=10)
    ctx.tree.wait_gone("Pairing with MSPA_c2ec", timeout=10)


def case_f_a_node_out_of_reach_and_forget_this_node(ctx):
    ctx.bridge.scenario("bluetooth-pairing")
    ctx.bridge.set("GET /api/mesh/ble/status", dict(IDLE, mode="lost", address=ADDRESS, name="MSPA_c2ec", paired=True, error="bluetooth link to the node lost"))
    ctx.bridge.set("DELETE /api/mesh/ble?bond=1", {"status": "forgotten"})
    node_page(ctx)
    ctx.tree.wait_text("MSPA_c2ec cannot be reached. Bluetooth link to the node lost.", timeout=10)
    assert after(ctx.tree.texts(), "Status") == "Disconnected"
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click("Forget this node")
    ctx.app.wait_toast("The node is forgotten", timeout=8)
    assert deletes(ctx, before) == ["/api/mesh/ble?bond=1"], deletes(ctx, before)


def case_g_this_device_in_both_modes_and_looking_again(ctx):
    path = os.path.join(ctx.app.work, "hardware.json")
    ctx.bridge.scenario("bluetooth-connected")
    try:
        node_page(ctx)
        ctx.tree.wait_text("This device", timeout=10)
        ctx.tree.wait_text("No LoRa back cover on the pogo bus (PinePhone Pro)", timeout=5)
        assert after(ctx.tree.texts(), "Node") == "A node over Bluetooth"
        ctx.app.mark()
        ctx.tree.click("Look for a LoRa back cover again")
        ctx.app.wait_toast("Looking for the cover", timeout=5)
        ctx.app.wait_toast("No LoRa back cover: connect a node over Bluetooth.", timeout=8)
        assert ["systemctl", "start", "meshsat-hardware.service"] in ctx.app.commands(), ctx.app.commands()
        # The cover put on: meshsat-hardware finds it, and the page turns to the cover
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(COVER, handle)
        ctx.app.mark()
        ctx.tree.click("Look for a LoRa back cover again")
        ctx.app.wait_toast("The LoRa back cover is this phone's node.", timeout=8)
        ctx.app.refresh()
        ctx.tree.wait_gone("Bluetooth connection", timeout=10)
        ctx.tree.wait_text("The LoRa back cover answers on the pogo bus (PinePhone Pro)", timeout=8)
        texts = ctx.tree.texts()
        assert after(texts, "Node") == "The LoRa back cover", texts
        assert texts.count("The LoRa back cover") >= 2, "the cover card's title and the device's node"
        ctx.tree.find("button", name="Restart the node", timeout=5)
        ctx.shot("device-cover")
    finally:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(HARDWARE, handle)
        ctx.app.refresh()
