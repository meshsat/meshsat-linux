# SPDX-License-Identifier: GPL-3.0-or-later
"""The satellite mailbox check opens a billed Iridium session, so it is asked about first
(CheckMailboxButton.kt): Cancel sends nothing, Check sends one request; with no modem it is not
offered."""
import time

SCENARIO = "satellite-3-bars"
ASKED = ("This opens an Iridium session, which can take up to 90 seconds. It uses at least 1 credit, even when no message is waiting. "
         "A message waiting to be sent goes out in the same session.")


def checks(ctx, since: int) -> list:
    return [r for r in ctx.bridge.requests(since) if r["method"] == "POST" and r["path"] == "/api/iridium/mailbox/check"]


def case_the_mailbox_check_asks_first(ctx):
    ctx.bridge.scenario("satellite-3-bars")
    ctx.app.refresh()
    ctx.app.open("setup/satellite")
    ctx.tree.wait_text("Connected (Signal: 3/5)", timeout=15)
    before = ctx.bridge.count()
    ctx.tree.click("Check Mailbox")
    ctx.tree.wait_text("Check the satellite mailbox?", timeout=10)
    names = [n.name for n in ctx.tree.dialog()]
    assert any(ASKED in n for n in names), names
    ctx.shot("mailbox-asks")
    ctx.tree.click_in_dialog("Cancel")
    time.sleep(1.5)
    assert not checks(ctx, before), "a check went out after Cancel"
    ctx.tree.click("Check Mailbox")
    ctx.tree.wait_text("Check the satellite mailbox?", timeout=10)
    ctx.tree.click_in_dialog("Check")
    ctx.bridge.wait_request("POST", "/api/iridium/mailbox/check", since=before, timeout=10)
    assert len(checks(ctx, before)) == 1


def case_no_modem_no_check(ctx):
    ctx.bridge.scenario("mesh-only")
    ctx.app.refresh()
    ctx.app.open("setup/satellite")
    ctx.tree.wait_text("No modem on this radio", timeout=15)
    assert not ctx.tree.find_all("button", name="Check Mailbox"), "the check is offered without a modem"
