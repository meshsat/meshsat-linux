# SPDX-License-Identifier: GPL-3.0-or-later
"""A routing rule on the live Bridge: made in the app, found in /api/access-rules, deleted from
the app. The rule only counts its matches (Log only), is named e2e-rule-<nonce>, and is removed
in the teardown whatever happened."""
import time

SCENARIO = None  # the live Bridge


def case_a_rule_made_in_the_app_is_in_the_bridge_and_removed_again(ctx):
    nonce = f"{int(time.time()) % 100000:05d}"
    name = f"e2e-rule-{nonce}"
    try:
        ctx.app.open("rules")
        ctx.tree.wait_text("Rules decide which messages are passed from one link to another.", timeout=10)
        ctx.app.mark()
        ctx.tree.click("Add rule")
        ctx.tree.wait_text("New rule")
        ctx.tree.set_text("Rule name", name)
        ctx.tree.click("Then")
        ctx.tree.click_containing("Log only")
        ctx.tree.wait_text("Only count the match. Other rules still decide what happens.")
        ctx.tree.click_in_dialog("Add")
        ctx.app.wait_toast("Rule added", timeout=10)
        ctx.tree.wait_text(name, timeout=10)
        stored = [r for r in (ctx.bridge.get("/api/access-rules") or []) if r.get("name") == name]
        assert len(stored) == 1, stored
        assert stored[0]["action"] == "log" and stored[0]["direction"] == "ingress", stored[0]
        ctx.note(f"stored: {stored[0]}")
        ctx.shot("stored")
        ctx.tree.click(f"Delete rule {name}")
        ctx.tree.wait_text("Its matches will no longer be counted. Messages are not affected. You cannot undo this.")
        ctx.tree.click_in_dialog("Delete")
        ctx.app.wait_toast("Rule deleted", timeout=10)
        ctx.tree.wait_gone(name, timeout=10)
        assert not [r for r in (ctx.bridge.get("/api/access-rules") or []) if r.get("name") == name]
    finally:
        for rule in [r for r in (ctx.bridge.get("/api/access-rules") or []) if str(r.get("name", "")).startswith("e2e-rule-")]:
            ctx.bridge.call("DELETE", f"/api/access-rules/{rule['id']}")
            ctx.note(f"teardown removed rule {rule['id']}")
        ctx.app.open("home")
