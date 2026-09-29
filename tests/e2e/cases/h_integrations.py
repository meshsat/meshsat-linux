# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > "Ham radio, TAK and Reticulum" (SettingsScreen.kt:1180-1623) against the scripted
Bridge, which validates and fills the gateways as the Bridge does: the three cards in Android's
words; every APRS write carries `enabled` and the stored config, KISS always with an external
Direwolf; the chips and the beacon write at once; Auto fills the passcode; APRS-IS carries the
server, passcode, radius, interval and the phone's position; the status rows follow the Bridge;
without a callsign the switch waits in the app; the Bridge's refusal is said; TAK's switches and
Save; Reticulum's interface made, switched and saved. Nothing reaches a radio or a real server:
the scripted Bridge only records the requests."""
import time

SCENARIO = "integrations"
ENV = {"MESHSAT_APP_POSITION": "52.3676,4.9041"}


def start(ctx, scenario: str = "integrations") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("setup/integrations")
    ctx.tree.wait_text("Ham radio (APRS)", timeout=15)


def puts(ctx, before: int, path: str, method: str = "PUT") -> list:
    return [r["body"] for r in ctx.bridge.requests(before) if r["method"] == method and r["path"] == path]


def save(ctx, index: int) -> None:
    """The index-th Save: APRS, TAK, Reticulum."""
    ctx.tree.find_all("button", name="Save")[index].do("click")


def entry(ctx, name: str, index: int = 0):
    found = ctx.tree.find_all("text", name=name)
    assert len(found) > index, (name, [n.name for n in ctx.tree.find_all("text")])
    return found[index]


def case_a_the_three_cards_in_androids_words(ctx):
    start(ctx)
    ctx.tree.wait_text("Connected", timeout=10)
    texts = ctx.tree.texts()
    for words in ("Ham radio (APRS)", "TAK", "Reticulum", "KISS TNC", "The frequency is set on the radio itself: 144.800 MHz in Europe, 144.390 MHz in North America.",
                  "Connect to Direwolf's KISS TCP server for local RF APRS via AIOC + handheld radio. SSID 7 = handheld, 10 = igate. EU: 144.800 MHz, NA: 144.390 MHz.",
                  "Generates CoT (Cursor on Target) events for positions, SOS, telemetry, and chat. ATAK Broadcast sends locally to ATAK if installed. "
                  "MQTT Export sends to Hub for relay to a TAK server. Callsign format: PREFIX-XXXX (last 4 hex of device ID).",
                  "Connect to a stock Reticulum (Python RNS) node over TCP/IP. Enable TLS for public endpoints (e.g. port 443 via HAProxy/stunnel). "
                  "Default port 4242. Uses HDLC framing for wire compatibility."):
        assert words in texts, words
    for name in ("Enable APRS", "Enable TAK", "ATAK Broadcast", "MQTT Export to Hub", "Enable RNS TCP", "TLS"):
        ctx.tree.switch(name)
    ctx.shot("setup-integrations")
    ctx.tree.click("APRS-IS Direct")
    ctx.tree.wait_text("Connect directly to APRS-IS (rotate.aprs2.net) over the internet. No Direwolf or radio needed.", timeout=10)
    for name in ("APRS-IS Server", "Passcode", "Filter radius (km)"):
        entry(ctx, name)
    ctx.shot("setup-integrations-is")


def case_b_aprs_save_always_sends_enabled(ctx):
    start(ctx)
    entry(ctx, "Callsign").set_text("n0call")
    time.sleep(0.5)
    assert entry(ctx, "Callsign").text() == "N0CALL", entry(ctx, "Callsign").text()
    entry(ctx, "SSID (0-15)").set_text("7")
    entry(ctx, "KISS Host").set_text("127.0.0.1")
    before = ctx.bridge.count()
    ctx.app.mark()
    save(ctx, 0)
    ctx.app.wait_toast("APRS settings saved", timeout=15)
    body = puts(ctx, before, "/api/gateways/aprs")[-1]
    c = body["config"]
    assert body["enabled"] is True and c["callsign"] == "N0CALL" and c["ssid"] == 7 and c["kiss_port"] == 8001 and c["external_direwolf"] is True, body
    assert c["tx_delay"] == 300 and "kiss_device" not in c, c


def case_c_the_switch_writes_the_stored_config_only(ctx):
    start(ctx)
    entry(ctx, "Callsign").set_text("PA3XYZ")  # typed, not saved
    before = ctx.bridge.count()
    ctx.tree.toggle("Enable APRS")
    ctx.tree.wait_switch("Enable APRS", False, timeout=10)
    body = puts(ctx, before, "/api/gateways/aprs")[-1]
    assert body["enabled"] is False and body["config"]["callsign"] == "N0CALL", body


def case_d_the_chips_and_the_beacon_write_at_once(ctx):
    start(ctx)
    before = ctx.bridge.count()
    ctx.tree.click("APRS-IS Direct")
    ctx.tree.toggle("Position beacon")
    deadline = time.time() + 10
    while len(puts(ctx, before, "/api/gateways/aprs")) < 2 and time.time() < deadline:
        time.sleep(0.3)
    bodies = puts(ctx, before, "/api/gateways/aprs")
    assert bodies[0]["config"]["mode"] == "is" and bodies[0]["enabled"] is True, bodies
    assert bodies[-1]["config"]["position_beacon"] is True, bodies
    entry(ctx, "Beacon interval (min)")


def case_e_auto_fills_the_passcode(ctx):
    start(ctx)
    ctx.tree.click("APRS-IS Direct")
    entry(ctx, "Callsign").set_text("N0CALL")
    before = ctx.bridge.count()
    ctx.tree.click("Auto")
    time.sleep(0.5)
    assert entry(ctx, "Passcode").text() == "13023", entry(ctx, "Passcode").text()
    assert not [r for r in ctx.bridge.requests(before) if r["method"] != "GET"], "Auto wrote something"


def case_f_aprs_is_save_carries_the_position(ctx):
    start(ctx)
    ctx.tree.click("APRS-IS Direct")
    entry(ctx, "Passcode").set_text("13023")
    entry(ctx, "Filter radius (km)").set_text("50")
    before = ctx.bridge.count()
    ctx.app.mark()
    save(ctx, 0)
    ctx.app.wait_toast("APRS settings saved", timeout=15)
    c = puts(ctx, before, "/api/gateways/aprs")[-1]["config"]
    assert (c["aprs_is_server"], c["aprs_is_passcode"], c["aprs_is_filter_km"], c["aprs_is_filter_lat"], c["aprs_is_filter_lon"]) == \
        ("rotate.aprs2.net:14580", "13023", 50, 52.3676, 4.9041), c


def case_g_the_status_rows_follow_the_bridge(ctx):
    start(ctx)
    ctx.tree.wait_text("Connected", timeout=10)
    for state, words in (("connecting", "Connecting..."), ("error", "Error"), ("disconnected", "Disconnected")):
        ctx.bridge.set("GET /api/aprs/status", {"connected": False, "state": state})
        ctx.tree.wait_text(words, timeout=12)


def case_h_no_callsign_keeps_the_switch_in_the_app(ctx):
    start(ctx, "integrations-empty")
    before = ctx.bridge.count()
    ctx.tree.toggle("Enable APRS")
    time.sleep(2)
    assert not puts(ctx, before, "/api/gateways/aprs"), "a gateway without a callsign was written"
    assert ctx.tree.switch("Enable APRS").checked
    entry(ctx, "Callsign").set_text("N0CALL")
    ctx.app.mark()
    save(ctx, 0)
    ctx.app.wait_toast("APRS settings saved", timeout=15)
    assert puts(ctx, before, "/api/gateways/aprs")[-1]["enabled"] is True


def case_i_the_bridges_refusal_is_said(ctx):
    start(ctx)
    entry(ctx, "Callsign").set_text("")
    ctx.app.mark()
    save(ctx, 0)
    ctx.app.wait_toast("invalid config: callsign is required for APRS", timeout=15)
    assert "APRS settings saved" not in ctx.app.toasts(since_mark=True)


def case_j_tak_switches_and_save(ctx):
    start(ctx)
    before = ctx.bridge.count()
    ctx.tree.toggle("Enable TAK")
    ctx.bridge.wait_request("PUT", "/api/gateways/tak", since=before, timeout=10)
    first = puts(ctx, before, "/api/gateways/tak")[0]
    assert first == {"enabled": True, "config": {"callsign_prefix": "MESHSAT", "multicast": True, "hub_export": True}}, first
    ctx.tree.toggle("ATAK Broadcast")
    deadline = time.time() + 10
    while len(puts(ctx, before, "/api/gateways/tak")) < 2 and time.time() < deadline:
        time.sleep(0.3)
    assert puts(ctx, before, "/api/gateways/tak")[-1]["config"]["multicast"] is False
    entry(ctx, "Callsign Prefix").set_text("team1")
    ctx.app.mark()
    save(ctx, 1)
    ctx.app.wait_toast("TAK settings saved", timeout=15)
    assert puts(ctx, before, "/api/gateways/tak")[-1]["config"]["callsign_prefix"] == "TEAM1"


def case_k_reticulum_made_switched_and_saved(ctx):
    start(ctx)
    ctx.tree.toggle("Enable RNS TCP")
    entry(ctx, "Host").set_text("127.0.0.1")
    before = ctx.bridge.count()
    ctx.app.mark()
    save(ctx, 2)
    ctx.app.wait_toast("RNS TCP settings saved", timeout=15)
    made = puts(ctx, before, "/api/routing/ifaces", "POST")[-1]
    assert made == {"type": "tcp_rns", "enabled": True, "config": {"host": "127.0.0.1", "port": 4242, "tls": False}}, made
    ctx.tree.wait_text("RNS TCP", timeout=10)
    ctx.tree.toggle("TLS")
    ctx.bridge.wait_request("PUT", "/api/routing/ifaces/tcp_rns_0", since=before, timeout=10)
    assert puts(ctx, before, "/api/routing/ifaces/tcp_rns_0")[-1] == {"config": {"host": "127.0.0.1", "port": 4242, "tls": True}}
    ctx.tree.toggle("Enable RNS TCP")
    deadline = time.time() + 10
    while {"enabled": False} not in puts(ctx, before, "/api/routing/ifaces/tcp_rns_0") and time.time() < deadline:
        time.sleep(0.3)
    assert {"enabled": False} in puts(ctx, before, "/api/routing/ifaces/tcp_rns_0")
