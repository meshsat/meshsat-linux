# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Hub (SettingsScreen.kt:1625-1900) against the scripted Bridge, which reports the link
as the Bridge does since MESHSAT-1417: the card in Android's words, each state of the link with
its dot, the Setup row and the Home lane, "Why: …" only when switched on and failed, the switch
that writes the setting and restarts nothing, the connection test, the connection details filled
from the Bridge and saved (the Bridge restarted, dry under test), and a provisioning claim still
waiting shown on the card once its dialog is hidden."""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from driver.qr import write_png  # noqa: E402

SCENARIO = "mesh-only"
ENV = {"MESHSAT_APP_SCAN_SOURCE": 'filesrc location="{work}/scan.png" ! pngdec ! imagefreeze', "MESHSAT_APP_HUB_SCHEME": "http"}
LINKED = {"url": "wss://mqtt-hub.meshsat.net/mqtt", "bridge_id": "", "username": "meshsat-pinephone-pro", "has_password": True, "has_cert": True,
          "enabled": True, "state": "connected", "running_as": "meshsat-pinephone-pro", "link": "connected"}
CLOSING = ("The Hub is the control room: with it, this phone shows in the fleet and on the map, "
           "and SOS alerts reach it over the internet as well as by satellite.")
NONCE = "fedcba9876543210fedcba9876543210"


def hub(ctx, **fields) -> dict:
    body = dict(LINKED, **fields)
    ctx.bridge.set("GET /api/routing/hub", body)
    return body


def start(ctx, **fields) -> None:
    ctx.bridge.scenario("mesh-only")
    hub(ctx, **fields)
    ctx.app.refresh()
    ctx.app.open("setup/hub")
    ctx.tree.wait_text("Hub connection", timeout=10)


def show(ctx, words: str, **fields) -> None:
    hub(ctx, **fields)
    ctx.app.refresh()
    ctx.tree.wait_text(words, timeout=12)


def case_a_the_card_in_androids_words(ctx):
    start(ctx)
    ctx.tree.wait_text("Connected as meshsat-pinephone-pro", timeout=12)
    texts = ctx.tree.texts()
    for words in ("On the Hub, open Fleet and add a bridge for this phone: the QR code it shows fills in everything, certificates included.", CLOSING):
        assert words in texts, (words, texts)
    for name in ("Scan the Hub's QR code", "Test the connection", "Connection details"):
        ctx.tree.find("button", name=name)
    assert ctx.tree.switch("Use the Hub").checked
    assert not ctx.tree.has_text("Why:")
    ctx.shot("setup-hub")


def case_b_each_state_of_the_link(ctx):
    start(ctx)
    show(ctx, "Connecting", state="connecting")
    show(ctx, "Cannot reach the Hub", state="error", last_error="network Error : dial tcp 1.2.3.4:443: connect: connection refused")
    ctx.tree.wait_text("Why: network Error : dial tcp 1.2.3.4:443: connect: connection refused")
    ctx.shot("setup-hub-error")
    show(ctx, "Not connected", state="disconnected")
    assert not ctx.tree.has_text("Why:")
    show(ctx, "Not set up: scan the Hub's QR code", state="", link="", running_as="")
    show(ctx, "Switched off", enabled=False, state="error", last_error="tls: bad certificate")
    assert not ctx.tree.has_text("Why:"), "the reason shows only with the switch on"
    assert not ctx.tree.switch("Use the Hub").checked


def case_c_the_setup_row_and_the_home_lane(ctx):
    start(ctx, state="error", last_error="tls: bad certificate")
    ctx.app.open("setup")
    ctx.tree.wait_text("Cannot reach the Hub", timeout=12)
    ctx.app.tab("home")
    ctx.tree.wait_text("Cannot reach the Hub. It keeps trying by itself.", timeout=12)
    show(ctx, "Connected as meshsat-pinephone-pro.", state="connected")
    show(ctx, "Scan the Hub's QR code to connect this phone.", state="", link="")
    ctx.app.open("setup")
    ctx.tree.wait_text("Not set up. Scan the Hub's QR code.", timeout=12)


def case_d_the_switch_writes_the_setting_and_restarts_nothing(ctx):
    start(ctx)
    ctx.tree.wait_text("Connected as meshsat-pinephone-pro", timeout=12)
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.toggle("Use the Hub")
    put = ctx.bridge.wait_request("PUT", "/api/routing/hub", since=before)["body"]
    assert put == {"enabled": False}, put
    ctx.tree.wait_text("Switched off", timeout=12)
    ctx.tree.toggle("Use the Hub")
    ctx.tree.wait_text("Connected as meshsat-pinephone-pro", timeout=12)
    puts = [r["body"] for r in ctx.bridge.requests(before) if r["method"] == "PUT" and r["path"] == "/api/routing/hub"]
    assert puts == [{"enabled": False}, {"enabled": True}], puts
    assert not [c for c in ctx.app.commands() if "restart" in c], ctx.app.commands()


def case_e_the_connection_test(ctx):
    start(ctx)
    ctx.tree.wait_text("Connected as meshsat-pinephone-pro", timeout=12)
    before = ctx.bridge.count()
    ctx.tree.click("Test the connection")
    ctx.tree.wait_text("42ms", timeout=10)
    assert [r for r in ctx.bridge.requests(before) if r["method"] == "POST" and r["path"] == "/api/routing/hub/ping"]
    show(ctx, "Not connected", state="disconnected")
    before = ctx.bridge.count()
    ctx.tree.click("Test the connection")
    ctx.tree.wait_count("Not connected", 2, timeout=10)  # the status line and the result
    assert not [r for r in ctx.bridge.requests(before) if r["path"] == "/api/routing/hub/ping"], "tested with no link"


def case_f_the_connection_details_saved(ctx):
    start(ctx, callsign="", health_interval=0)
    ctx.tree.click("Connection details")
    ctx.tree.find("button", name="Hide connection details", timeout=10)
    assert ctx.tree.entry_text("Hub MQTT URL") == "wss://mqtt-hub.meshsat.net/mqtt"
    assert ctx.tree.entry_text("Username") == "meshsat-pinephone-pro"
    assert ctx.tree.entry_text("Health interval (seconds)") == "30"
    ctx.tree.set_text("Callsign", "Team Alpha")
    ctx.tree.set_text("Health interval (seconds)", "4x5")
    assert ctx.tree.entry_text("Health interval (seconds)") == "45", "digits only"
    # a hidden entry is "password text" on some GTK builds and "text" on others
    (ctx.tree.find_all("password text", name="Password") or ctx.tree.find_all("text", name="Password"))[0].set_text("new-secret")
    ctx.shot("setup-hub-details")
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click("Save")
    ctx.app.wait_toast("Saved. Restarting the Bridge to use them.", timeout=10)
    put = ctx.bridge.wait_request("PUT", "/api/routing/hub", since=before)["body"]
    assert put == {"url": "wss://mqtt-hub.meshsat.net/mqtt", "bridge_id": "", "callsign": "Team Alpha", "username": "meshsat-pinephone-pro",
                   "health_interval": 45, "password": "new-secret"}, put
    assert ["pkexec", "systemctl", "restart", "meshsat-bridge.service"] in ctx.app.commands(), ctx.app.commands()
    ctx.tree.click("Hide connection details")
    ctx.tree.find("button", name="Connection details", timeout=10)


def case_g_a_claim_still_waiting_shows_on_the_card(ctx):
    start(ctx, state="", link="", url="", username="", has_password=False, has_cert=False, running_as="")
    host = urllib.parse.urlparse(ctx.bridge.url).netloc
    ctx.bridge.claim("e2e-hub", NONCE, None, busy=100, retry_after=1)
    write_png(f"meshsat://provision/e2e-hub/{NONCE}?hub={host}", ctx.app.work + "/scan.png")
    ctx.tree.click("Scan the Hub's QR code")
    ctx.tree.wait_text("Waiting for the Hub", timeout=15)
    ctx.tree.click_in_dialog("Hide")
    ctx.tree.wait_text("Getting the Hub's settings, ", timeout=10)
    ctx.shot("setup-hub-waiting")
    # The Hub gives up on the code: the claim ends in Android's words, and the card's line goes.
    ctx.bridge.claim("e2e-hub", NONCE, None)
    ctx.tree.wait_text("No settings from the Hub", timeout=20)
    ctx.tree.click_in_dialog("OK")
    ctx.tree.wait_gone("Getting the Hub's settings, ", timeout=10)
