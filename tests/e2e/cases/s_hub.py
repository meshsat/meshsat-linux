# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hub page against a real, scratch Bridge (MESHSAT-1417): with no Hub set up the Bridge says
so and the page says Android's words for it; the test sends nothing without a link; the switch
and the connection details are kept by the Bridge as the page wrote them, and read back."""
import time

SCENARIO = None  # the scratch Bridge


def wait_for(ctx, check, what: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while True:
        got = ctx.bridge.get("/api/routing/hub")
        if check(got):
            return got
        if time.time() > deadline:
            raise AssertionError(f"{what}: {got}")
        time.sleep(0.5)


def case_the_hub_page_against_the_bridge(ctx):
    got = ctx.bridge.get("/api/routing/hub")
    assert got.get("state") == "" and got.get("enabled") is True and "running_as" not in got, got
    status, answer = ctx.bridge.call("POST", "/api/routing/hub/ping")
    assert status == 409 and "not connected" in (answer or {}).get("error", ""), (status, answer)
    ctx.app.open("setup/hub")
    ctx.tree.wait_text("Not set up: scan the Hub's QR code", timeout=15)
    ctx.tree.click("Test the connection")
    ctx.tree.wait_text("Not connected", timeout=10)

    ctx.tree.toggle("Use the Hub")
    wait_for(ctx, lambda h: h.get("enabled") is False, "the switch never reached the Bridge")
    ctx.app.refresh()
    ctx.tree.wait_text("Switched off", timeout=15)
    ctx.tree.toggle("Use the Hub")
    wait_for(ctx, lambda h: h.get("enabled") is True, "switched back on")

    ctx.tree.click("Connection details")
    ctx.tree.find("button", name="Hide connection details", timeout=10)
    ctx.tree.set_text("Callsign", "e2e-callsign")
    ctx.tree.set_text("Health interval (seconds)", "45")
    ctx.app.mark()
    ctx.tree.click("Save")
    ctx.app.wait_toast("Saved. Restarting the Bridge to use them.", timeout=10)
    got = wait_for(ctx, lambda h: h.get("callsign") == "e2e-callsign", "the details never reached the Bridge")
    assert got.get("health_interval") == 45 and got.get("url") == "" and got.get("has_password") is False, got
    assert ["pkexec", "systemctl", "restart", "meshsat-bridge.service"] in ctx.app.commands(), ctx.app.commands()
    status, _ = ctx.bridge.call("PUT", "/api/routing/hub", {"callsign": "", "health_interval": 0})
    assert status == 200
