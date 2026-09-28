# SPDX-License-Identifier: GPL-3.0-or-later
"""Routing rules against a real, scratch Bridge: a rule made in the editor is the record the
Bridge stores, column for column; a save keeps every column; the switch and the delete reach
the database."""
import json

SCENARIO = None  # the scratch Bridge


def rules_of(ctx) -> list:
    return ctx.bridge.get("/api/access-rules") or []


def case_create_edit_switch_and_delete_reach_the_database(ctx):
    assert rules_of(ctx) == [], f"the scratch Bridge starts with rules: {rules_of(ctx)}"
    ctx.app.open("rules")
    ctx.tree.wait_text("Rules decide which messages are passed from one link to another.", timeout=10)
    ctx.tree.wait_text("No rules for mesh messages yet, so they stay on the mesh. Tap + to add one.", timeout=10)
    ctx.app.mark()
    ctx.tree.click("Add rule")
    ctx.tree.wait_text("New rule")
    ctx.tree.set_text("Rule name", "e2e-rule")
    ctx.tree.set_text("Urgency", "0")
    ctx.tree.click("Delivery guarantee")
    ctx.tree.click_containing("Try once")
    ctx.tree.set_text("At most (messages)", "5")
    ctx.tree.set_text("Every (seconds)", "60")
    ctx.tree.set_text("Contains the text (optional)", "SOS")
    ctx.tree.set_text("From a node group (group id, optional)", "north")
    ctx.tree.click_in_dialog("Add")
    ctx.app.wait_toast("Rule added", timeout=10)
    ctx.tree.wait_text("e2e-rule", timeout=10)
    stored = rules_of(ctx)
    assert len(stored) == 1, stored
    rule = stored[0]
    ctx.note(f"stored: {json.dumps(rule)}")
    assert rule["name"] == "e2e-rule" and rule["direction"] == "ingress" and rule["action"] == "forward", rule
    assert rule["interface_id"].startswith("mesh"), rule
    assert (rule["priority"], rule["qos_level"], rule["rate_limit_per_min"], rule["rate_limit_window"]) == (0, 0, 5, 60), rule
    assert json.loads(rule["filters"]) == {"keyword": "SOS"}, rule["filters"]
    assert rule.get("filter_node_group") == "north", rule
    assert rule["enabled"] is True, rule
    ctx.tree.wait_text("Forward: ")  # the route line
    ctx.tree.wait_text("No matches yet · At most 5 messages per minute · Try once · Critical")
    ctx.tree.wait_text("Contains “SOS” · Node group north")
    ctx.shot("stored")
    # Edit: the name changes, nothing else does.
    ctx.tree.click("Edit rule e2e-rule")
    ctx.tree.wait_text("Edit rule")
    assert ctx.tree.entry_text("From a node group (group id, optional)") == "north"
    ctx.tree.set_text("Rule name", "e2e-rule renamed")
    ctx.tree.click_in_dialog("Save")
    ctx.app.wait_toast("Rule saved", timeout=10)
    ctx.tree.wait_text("e2e-rule renamed", timeout=10)
    saved = rules_of(ctx)[0]
    for key in ("interface_id", "direction", "action", "forward_to", "filters", "filter_node_group", "qos_level", "rate_limit_per_min", "rate_limit_window", "priority", "schedule_type"):
        assert saved.get(key) == rule.get(key), (key, saved.get(key), rule.get(key))
    assert saved["name"] == "e2e-rule renamed"
    # The switch
    ctx.tree.toggle("Rule e2e-rule renamed is on")
    ctx.tree.wait_switch("Rule e2e-rule renamed is off", False)
    assert rules_of(ctx)[0]["enabled"] is False, rules_of(ctx)
    ctx.tree.toggle("Rule e2e-rule renamed is off")
    ctx.tree.wait_switch("Rule e2e-rule renamed is on", True)
    assert rules_of(ctx)[0]["enabled"] is True, rules_of(ctx)
    # Delete
    ctx.tree.click("Delete rule e2e-rule renamed")
    ctx.tree.wait_text("Delete this rule?")
    ctx.tree.click_in_dialog("Delete")
    ctx.app.wait_toast("Rule deleted", timeout=10)
    ctx.tree.wait_gone("e2e-rule renamed", timeout=10)
    assert rules_of(ctx) == [], rules_of(ctx)
    ctx.shot("deleted")
    ctx.app.open("home")
