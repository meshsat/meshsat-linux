# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh radio settings with the LoRa back cover (RadioConfigScreen.kt): the seven tabs in
Android's words over the node's settings as the Bridge names them; every Apply sends only what
changed, and the questions come first where Android asks them; the cover's transmit power is
capped with the reason beside it, and it has no WiFi or Bluetooth of its own. The phone is set
to the Netherlands, so the region check has a country to judge by."""
import json

SCENARIO = "mesh-only"
ENV = {"MESHSAT_APP_COUNTRY": "NL"}
ME_NUM = int("52cb81e7", 16)


def start(ctx, tab: str | None = None) -> None:
    ctx.bridge.scenario("mesh-only")
    ctx.app.open("radio-config")
    ctx.tree.wait_text("This node", timeout=10)
    ctx.tree.wait_text("!52cb81e7", timeout=10)
    if tab:
        ctx.tree.click(tab)


def posts(ctx, before: int, path: str) -> list:
    return [r for r in ctx.bridge.requests(before) if r["method"] == "POST" and r["path"] == path]


def case_name_tab_facts_and_save(ctx):
    start(ctx)
    for words in ("Node ID", "Hardware", "Portduino", "Firmware", "2.7.3.dev", "Has",
                  "The long name shows in other people's node lists. The short name, up to 4 characters, is used where space is tight."):
        ctx.tree.wait_text(words)
    for tab in ("Name", "Radio", "Channels", "Position", "Bluetooth", "WiFi", "Restart and reset"):
        ctx.tree.find("button", name=tab)
    assert ctx.tree.entry_text("Long name") == "meshsat-pinephone-pro"
    assert ctx.tree.entry_text("Short name") == "MSPP"
    assert not ctx.tree.find("button", name="Save name").sensitive, "Save name is on with nothing changed"
    ctx.shot("name")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.set_text("Short name", "MSP2")
    ctx.tree.click("Save name")
    ctx.app.wait_toast("Sent to the radio. It restarts to apply the change.")
    sent = posts(ctx, before, "/api/config/owner")
    assert sent and sent[0]["body"] == {"long_name": "meshsat-pinephone-pro", "short_name": "MSP2"}, sent


def case_radio_tab_sends_only_the_hop_limit(ctx):
    start(ctx, "Radio")
    for words in ("The radio band for the country you are in. Every node on your mesh uses the same one.",
                  "How far and how fast the radio talks. Every node on your mesh must use the same preset.", "0 dBm (1 mW), capped",
                  "The LoRa back cover sends at 0 dBm, the one power it is qualified at", "How many times other nodes pass your messages on, 1 to 7.",
                  "Off makes your node listen only: nothing you send leaves it."):
        ctx.tree.wait_text(words)
    ctx.tree.find("button", name="EU 868")
    ctx.tree.find("button", name="Long Fast")
    assert not ctx.tree.find_all("text", name="dBm"), "the cover's power is typed in, not capped"
    assert not ctx.tree.has_text("Your phone is set to"), "a region that fits the Netherlands was warned about"
    assert ctx.tree.switch("Transmit").checked
    apply = ctx.tree.find("button", name="Apply")
    assert not apply.sensitive, "Apply is on with nothing changed"
    ctx.tree.click("Details")
    ctx.tree.wait_text("Long Fast: spreading factor 11, bandwidth 250 kHz, coding rate 4/5. Radios on 2.4 GHz use wider bandwidths.")
    ctx.tree.click("Hide details")
    ctx.tree.set_text("Hops", "9")
    ctx.tree.wait_text("Enter a number from 1 to 7.")
    assert not ctx.tree.find("button", name="Apply").sensitive
    ctx.shot("radio")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.set_text("Hops", "5")
    ctx.tree.wait_gone("Enter a number from 1 to 7.")
    ctx.tree.click("Apply")
    ctx.app.wait_toast("Sent to the radio. It switches over in a few seconds; older firmware restarts to do it.")
    assert not ctx.tree.dialogs_open(), "a hop limit alone asked first"
    sent = posts(ctx, before, "/api/config/radio")
    assert sent and sent[0]["body"] == {"section": "lora", "config": {"hop_limit": 5}}, sent
    # Read back as Android does, 2.5 s later: the node is asked for the section again.
    ctx.bridge.wait_request("GET", "/api/config/lora", timeout=6, since=before)


def case_region_is_checked_and_asked_first(ctx):
    start(ctx, "Radio")
    ctx.tree.click("EU 868")
    ctx.tree.wait_text("Region")
    ctx.tree.click_in_dialog("US")
    ctx.tree.wait_text("Your phone is set to Netherlands, where radios use EU 868 or EU 433. Check the region matches where you are: the wrong one can be "
                       "illegal there, and you will not hear nearby nodes.")
    ctx.shot("region-warning")
    before = ctx.bridge.count()
    ctx.tree.click("Apply")
    ctx.tree.wait_text("Apply these radio settings?")
    ctx.tree.wait_text("Changing the region or preset can cut you off from other nodes until they change too.")
    ctx.shot("apply-radio")
    ctx.tree.click_in_dialog("Cancel")
    assert not posts(ctx, before, "/api/config/radio"), "a region change went out without the answer"
    ctx.tree.click("Apply")
    ctx.tree.click_in_dialog("Apply")
    ctx.bridge.wait_request("POST", "/api/config/radio", since=before)
    sent = posts(ctx, before, "/api/config/radio")
    assert sent[0]["body"] == {"section": "lora", "config": {"region": 1}}, sent


def case_channels_edit_never_sends_a_key(ctx):
    start(ctx, "Channels")
    for words in ("Nodes hear each other on a channel when they share its name and key.", "Channel 0", "msat-ttc-01", "Main channel. Every node on this mesh shares it.",
                  "Channel key: private", "Only nodes that have this key can read it.", "Channel 1", "i9603", "Extra channel. A group channel beside the main one.",
                  "Channel 7", "No name", "Off. Not in use."):
        ctx.tree.wait_text(words)
    ctx.shot("channels")
    ctx.tree.click_after("msat-ttc-01", "Edit")
    ctx.tree.wait_text("Channel 0 is always the main channel.")
    ctx.tree.click_in_dialog("Cancel")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click_after("i9603", "Edit")
    ctx.tree.wait_text("Copies this channel's messages to an internet server when the node has internet.")
    ctx.tree.set_text("Channel name", "e2e-team")
    ctx.shot("channel-edit")
    ctx.tree.click_in_dialog("Save")
    ctx.tree.wait_text("Change channel 1?")
    ctx.tree.wait_text("Changing a channel's name or role can cut you off from nodes that still use the old one until they change too.")
    ctx.tree.click_in_dialog("Change")
    ctx.app.wait_toast("Sent to the radio.")
    sent = posts(ctx, before, "/api/channels")
    assert sent and sent[0]["body"] == {"index": 1, "name": "e2e-team", "role": "SECONDARY", "uplink_enabled": False, "downlink_enabled": False}, sent


def case_position_tab(ctx):
    start(ctx, "Position")
    for words in ("Use a position set by hand instead of the GPS.", "How often the node shares its position, in seconds. 0 uses the default, 15 minutes.",
                  "Shares sooner when the node moves.", "Applying restarts the node. The phone reconnects by itself."):
        ctx.tree.wait_text(words)
    assert not ctx.tree.switch("GPS on").checked
    assert ctx.tree.switch("Smart sharing").checked
    assert ctx.tree.entry_text("Every (seconds)") == "900"
    ctx.tree.set_text("Every (seconds)", "")
    ctx.tree.wait_text("Enter a number of seconds.")
    ctx.tree.set_text("Every (seconds)", "900")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.toggle("Smart sharing")
    ctx.tree.click("Apply")
    ctx.app.wait_toast("Sent to the radio. It restarts to apply the change.")
    sent = posts(ctx, before, "/api/config/radio")
    assert sent and sent[0]["body"] == {"section": "position", "config": {"position_broadcast_smart_enabled": False}}, sent


def case_the_cover_has_no_wifi_or_bluetooth(ctx):
    start(ctx, "Bluetooth")
    ctx.tree.wait_text("The node runs on this phone, so it has no Bluetooth of its own: the app reaches it inside the phone.")
    ctx.tree.click("WiFi")
    ctx.tree.wait_text("The node runs on this phone and uses the phone's own network, so it has no WiFi of its own.")
    ctx.shot("wifi-cover")


def case_restart_and_reset_ask_first(ctx):
    start(ctx, "Restart and reset")
    for words in ("Sets the node's clock to the phone's time.", "Restarts the node after a delay. The phone reconnects by itself.", "This node cannot switch itself off.",
                  "Clears the node's list of the nodes it has heard. They come back as they transmit again.",
                  "Erases every setting on the node and restores the factory ones. This cannot be undone."):
        ctx.tree.wait_text(words)
    assert not ctx.tree.find("button", name="Switch off the node").sensitive, "the cover's node can be switched off"
    ctx.shot("restart")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click("Set the clock")
    ctx.app.wait_toast("Sent to the radio.")
    ctx.bridge.wait_request("POST", "/api/admin/set_clock", since=before)
    ctx.tree.click("Restart the node")
    ctx.tree.wait_text("Restart your node?")
    ctx.tree.wait_text("In 5 seconds the phone loses the node and the mesh until the node is back, usually within a minute. The phone reconnects by itself.")
    ctx.tree.click_in_dialog("Restart")
    ctx.app.wait_toast("Sent to the radio. It restarts in 5 seconds.")
    sent = posts(ctx, before, "/api/admin/reboot")
    assert sent and sent[0]["body"] == {"node_id": ME_NUM, "delay_secs": 5}, sent
    ctx.tree.click("Forget heard nodes")
    ctx.tree.wait_text("Your node clears its list of the nodes it has heard. They come back as they transmit again.")
    ctx.tree.click_in_dialog("Forget")
    ctx.bridge.wait_request("POST", "/api/admin/nodedb_reset", since=before)
    ctx.tree.click("Factory reset")
    ctx.tree.wait_text("Erase every setting on your node?")
    ctx.tree.wait_text("Its region, channels, keys and name go back to the factory ones and it restarts.")
    ctx.shot("erase")
    ctx.tree.click_in_dialog("Cancel")
    assert not posts(ctx, before, "/api/admin/factory_reset"), "a factory reset went out without the answer"


def case_a_refused_write_says_why(ctx):
    start(ctx, "Radio")
    ctx.bridge.set("POST /api/config/radio", {"error": "the node has not sent these settings yet: lora"}, status=409)
    ctx.app.mark()
    ctx.tree.set_text("Hops", "4")
    ctx.tree.click("Apply")
    ctx.app.wait_toast("The node has not sent these settings yet; try again in a moment.")
    ctx.bridge.set("POST /api/config/radio", {"error": 'unknown lora setting "hop_limit"'}, status=400)
    ctx.tree.click("Apply")
    ctx.app.wait_toast('unknown lora setting "hop_limit"')


def case_not_connected_offers_the_node_page(ctx):
    start(ctx)
    status = json.loads(json.dumps(ctx.bridge.fake.routes["GET /api/status"]))
    status["connected"] = False
    ctx.bridge.set("GET /api/status", status)
    ctx.app.refresh()
    ctx.tree.wait_text("Your phone is not connected to your node, so its settings cannot be read or changed.", timeout=10)
    assert not ctx.tree.find("text", name="Long name").sensitive, "the name can be typed with no node"
    ctx.shot("not-connected")
    ctx.tree.click("Connect your node")
    ctx.tree.wait_text("Your MeshSat node", timeout=10)
    ctx.app.open("home")
