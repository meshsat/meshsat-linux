# SPDX-License-Identifier: GPL-3.0-or-later
"""A T-Deck adopted over Bluetooth (RadioConfigScreen.kt, NodeLogScreen.kt): its Bluetooth and
WiFi tabs in Android's words, "Turn off Bluetooth?" before the link is cut, a fixed PIN of six
digits, the password hidden until shown, switching the node off; the node's log streamed over
the link while its switch is on, the switch writing only the debug-log flag."""

SCENARIO = "bluetooth-connected"
HARDWARE = {"node": "bluetooth", "why": "no LoRa back cover on the pogo bus", "model": "PinePhone Pro"}
OTHER_NUM = int("a1b3c2ec", 16)


def start(ctx, tab: str | None = None) -> None:
    ctx.bridge.scenario("bluetooth-connected")
    ctx.app.open("radio-config")
    ctx.tree.wait_text("!a1b3c2ec", timeout=10)
    if tab:
        ctx.tree.click(tab)


def entry(ctx, name: str, timeout: float = 5.0):
    """A text entry by name, hidden (a password or a PIN: role "password text") or shown."""
    import time  # noqa: PLC0415

    deadline = time.time() + timeout
    while True:
        found = ctx.tree.find_all("password text", name=name) or ctx.tree.find_all("text", name=name)
        if found or time.time() > deadline:
            assert found, f"no entry named {name!r}"
            return found[0]
        time.sleep(0.2)


def posts(ctx, before: int, path: str) -> list:
    return [r for r in ctx.bridge.requests(before) if r["method"] == "POST" and r["path"] == path]


def case_name_tab_of_a_tdeck(ctx):
    start(ctx)
    for words in ("LilyGO T-Deck", "2.7.26.a1b2c3d", "WiFi, Bluetooth, Power off"):
        ctx.tree.wait_text(words)
    assert ctx.tree.entry_text("Long name") == "MSPA"


def case_turning_bluetooth_off_asks_first(ctx):
    start(ctx, "Bluetooth")
    for words in ("This is how your phone talks to the node.", "Applying restarts the node. The phone reconnects by itself."):
        ctx.tree.wait_text(words)
    assert ctx.tree.switch("Bluetooth on").checked
    ctx.tree.find("button", name="PIN shown on the node's screen")
    before = ctx.bridge.count()
    ctx.tree.toggle("Bluetooth on")
    ctx.tree.click("Apply")
    ctx.tree.wait_text("Turn off Bluetooth?")
    ctx.tree.wait_text("You will lose the connection to this node from the phone, and with it the satellite modem. Turning it back on then needs the node itself "
                       "or a USB cable.")
    ctx.shot("bluetooth-off")
    ctx.tree.click_in_dialog("Cancel")
    assert not posts(ctx, before, "/api/config/radio"), "Bluetooth went off without the answer"
    ctx.tree.toggle("Bluetooth on")
    ctx.tree.click("PIN shown on the node's screen")
    ctx.tree.click_in_dialog("Fixed PIN")
    pin = entry(ctx, "PIN")
    assert pin.text() == "123456", pin.text()
    pin.set_text("12345")
    ctx.tree.wait_text("Enter 6 digits.")
    assert not ctx.tree.find("button", name="Apply").sensitive
    pin.set_text("654321")
    ctx.tree.wait_gone("Enter 6 digits.")
    ctx.app.mark()
    ctx.tree.click("Apply")
    ctx.app.wait_toast("Sent to the radio. It restarts to apply the change.")
    sent = posts(ctx, before, "/api/config/radio")
    assert sent and sent[0]["body"] == {"section": "bluetooth", "config": {"mode": 1, "fixed_pin": 654321}}, sent


def case_wifi_with_the_password_hidden(ctx):
    start(ctx, "WiFi")
    ctx.tree.wait_text("Lets the node reach the internet, for MQTT, when a network is in range.")
    assert not ctx.tree.switch("WiFi on").checked
    assert not ctx.tree.find_all("text", name="Network name"), "the WiFi fields show with WiFi off"
    ctx.tree.toggle("WiFi on")
    ctx.tree.set_text("Network name", "e2e-net")
    entry(ctx, "Password").set_text("e2e-secret")
    ctx.tree.click("Show password")
    ctx.tree.find("button", name="Hide password")
    ctx.tree.click("Hide password")
    ctx.tree.find("button", name="Show password")
    ctx.shot("wifi")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click("Apply")
    ctx.app.wait_toast("Sent to the radio. It restarts to apply the change.")
    sent = posts(ctx, before, "/api/config/radio")
    assert sent and sent[0]["body"] == {"section": "network", "config": {"wifi_enabled": True, "wifi_ssid": "e2e-net", "wifi_psk": "e2e-secret"}}, sent


def case_switching_the_node_off_asks_first(ctx):
    start(ctx, "Restart and reset")
    ctx.tree.wait_text("Switches the node off. Someone has to switch it on again at the node.")
    ctx.tree.click("Restart the node")
    ctx.tree.wait_text("In 5 seconds the phone loses the node, the mesh and the satellite modem until the node is back, usually within a minute.")
    ctx.tree.click_in_dialog("Cancel")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click("Switch off the node")
    ctx.tree.wait_text("Switch off your node?")
    ctx.tree.wait_text("The phone loses the connection to it, and with it the mesh and the satellite modem, until someone switches it on again at the node.")
    ctx.tree.click_in_dialog("Switch off")
    ctx.app.wait_toast("Sent to the radio. It switches off in 5 seconds.")
    sent = posts(ctx, before, "/api/admin/shutdown")
    assert sent and sent[0]["body"] == {"delay_secs": 5}, sent


def case_the_node_log_streams_over_the_link(ctx):
    ctx.bridge.scenario("bluetooth-connected")
    ctx.app.open("nodelog")
    ctx.tree.wait_text("Sets the node's debug log over Bluetooth (security.debug_log_api_enabled); a setting the node keeps.", timeout=10)
    assert not ctx.tree.switch("Stream the node's log").checked
    ctx.tree.wait_text("[Router] Received text msg from=0x52cb81e7", timeout=10)
    ctx.tree.wait_text("WARN [IridiumPipe] modem did not answer")
    before = ctx.bridge.count()
    assert ctx.bridge.state()["follows"] == 0, "the log was followed with the switch off"
    ctx.tree.toggle("Stream the node's log")
    ctx.bridge.wait_request("POST", "/api/config/radio", since=before)
    sent = posts(ctx, before, "/api/config/radio")
    assert sent[0]["body"] == {"section": "security", "config": {"debug_log_api_enabled": True}}, sent
    ctx.tree.wait_text("The node sends every log line while this switch is on; it may drop lines in a burst. Newest at the bottom.", timeout=10)
    ctx.bridge.wait_request("GET", "/api/mesh/radio-log?after=2&follow=1", timeout=8, since=before)
    ctx.bridge.log([{"received_at": "2026-09-29T00:11:00Z", "radio_time": 0, "level": "DEBUG", "source": "BleWatchdog", "message": "e2e line 3"}])
    ctx.tree.wait_text("DEBUG [BleWatchdog] e2e line 3", timeout=8)
    ctx.shot("nodelog-bluetooth")
    ctx.tree.toggle("Stream the node's log")
    ctx.tree.wait_text("Sets the node's debug log over Bluetooth", timeout=10)
    last = [r for r in ctx.bridge.requests(before) if r["method"] == "POST" and r["path"] == "/api/config/radio"][-1]
    assert last["body"] == {"section": "security", "config": {"debug_log_api_enabled": False}}, last
    ctx.app.open("home")


def case_the_switch_says_why_it_cannot(ctx):
    ctx.bridge.scenario("bluetooth-connected")
    ctx.bridge.set("POST /api/config/radio", {"error": "the node has not sent these settings yet: the node has not sent its private key"}, status=409)
    ctx.app.open("nodelog")
    ctx.tree.wait_text("Sets the node's debug log over Bluetooth", timeout=10)
    ctx.app.mark()
    ctx.tree.toggle("Stream the node's log")
    ctx.app.wait_toast("The node has not sent its security settings yet; try again in a moment.")
    ctx.tree.wait_switch("Stream the node's log", False)
    ctx.app.open("home")
