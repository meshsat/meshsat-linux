# SPDX-License-Identifier: GPL-3.0-or-later
"""Routing rules (RulesScreen.kt): the five tabs with their badges, subtitles and empty texts;
the cards; the editor writing Android's record; a save that keeps every column; the switch;
the delete that says what it changes; the queue tab's Cancel and Retry. Every case starts
from the scenario queue-busy afresh (the cases change the rules and the queue)."""
import json

SCENARIO = "queue-busy"


def start(ctx) -> None:
    ctx.bridge.scenario("queue-busy")
    ctx.app.open("rules")
    ctx.tree.wait_text("Rules decide which messages are passed from one link to another.", timeout=10)
    ctx.tree.wait_text("SOS to satellite", timeout=10)


def pick(ctx, field: str, option: str) -> None:
    """A choice in one of the editor's lists: the field's button, then the row in the list."""
    ctx.tree.click(field)
    ctx.tree.click_in_dialog(option)


def case_tabs_badges_and_cards(ctx):
    start(ctx)
    for tab in ("From mesh", "Into mesh", "Between links", "Deliveries", "Queue"):
        ctx.tree.find("button", name=tab)
    for words in ("What happens to messages heard on the mesh.", "Forward: Mesh to Satellite", "No matches yet · At most 5 messages per minute · Critical",
                  "Contains “SOS” · Mesh channels 0"):
        ctx.tree.wait_text(words)
    assert ctx.tree.switch("Rule SOS to satellite is on").checked
    ctx.tree.find("button", name="Edit rule SOS to satellite")
    ctx.tree.find("button", name="Delete rule SOS to satellite")
    ctx.tree.find("button", name="Add rule")
    ctx.shot("from-mesh")
    ctx.tree.click("Into mesh")
    for words in ("Messages from satellite, SMS or the Hub that are passed into the mesh.", "Satellite into the mesh", "Forward: Satellite to Mesh", "3 matches · last 2 min ago"):
        ctx.tree.wait_text(words)
    ctx.tree.click("Between links")
    for words in ("Messages from satellite, SMS or the Hub that go to another link, or are stopped or only logged.", "Stop spam", "Drop: messages from SMS",
                  "1 match · Try once", "Sender group spammers"):
        ctx.tree.wait_text(words)
    assert not ctx.tree.switch("Rule Stop spam is off").checked
    ctx.tree.click("Deliveries")
    ctx.tree.wait_text("Position report", timeout=10)
    ctx.tree.find("button", name="Waiting")
    assert not ctx.tree.find_all("button", name="Add rule"), "the add button showed on the Deliveries tab"
    ctx.tree.click("Queue")
    for words in ("Messages still waiting to go out, and messages that did not. Cancel one that is waiting, or retry one that gave up.",
                  "Waiting to go out (4)", "Did not go out (4)"):
        ctx.tree.wait_text(words)
    ctx.shot("queue-tab")
    ctx.tree.click("From mesh")


def case_a_new_rule_writes_androids_record(ctx):
    start(ctx)
    ctx.app.mark()
    before = ctx.bridge.count()
    ctx.tree.click("Add rule")
    ctx.tree.wait_text("New rule")
    ctx.tree.click_in_dialog("Add")
    ctx.tree.wait_text("Give the rule a name so you can find it later.")
    assert not [r for r in ctx.bridge.requests(before) if r["method"] == "POST"], "a rule without a name was sent"
    ctx.tree.set_text("Rule name", "e2e rule")
    pick(ctx, "Then", "Drop")
    ctx.tree.wait_text("Stop it. It is not passed on, whatever other rules say.")
    assert not ctx.tree.find_all("button", name="Pass it on by"), "the target showed for a Drop rule"
    pick(ctx, "Then", "Forward")
    ctx.tree.wait_text("Pass it on to another link.")
    pick(ctx, "When a message arrives by", "Satellite")
    pick(ctx, "Pass it on by", "Hub")
    ctx.tree.wait_text("The Hub already receives satellite messages straight from the provider. This rule sends a second copy, so anything the Hub does with them - alerts, TAK, webhooks - happens twice.")
    ctx.tree.set_text("Urgency", "0")
    ctx.tree.wait_text("Critical. Lower numbers go first and are checked first; 0 never expires.")
    pick(ctx, "Delivery guarantee", "Try once")
    ctx.tree.wait_text("Try once gives up after one failed attempt. Keep trying retries until it goes out.")
    ctx.tree.set_text("At most (messages)", "5")
    ctx.tree.set_text("Every (seconds)", "60")
    ctx.tree.wait_text("At most 5 messages per minute. Leave either box at 0 for no limit.")
    ctx.tree.set_text("Contains the text (optional)", "SOS")
    ctx.shot("editor")
    ctx.tree.click_in_dialog("Add")
    posted = ctx.bridge.wait_request("POST", "/api/access-rules", since=before)
    assert posted["body"] == {"interface_id": "iridium_0", "direction": "ingress", "priority": 0, "name": "e2e rule", "enabled": True, "action": "forward", "forward_to": "hub_0",
                              "filters": '{"keyword":"SOS"}', "filter_node_group": None, "filter_sender_group": None, "filter_portnum_group": None, "schedule_type": "none",
                              "schedule_config": "", "forward_options": "{}", "qos_level": 0, "rate_limit_per_min": 5, "rate_limit_window": 60}, posted["body"]
    ctx.app.wait_toast("Rule added")
    # The tab the rule is listed under is shown, so it never seems to disappear.
    ctx.tree.wait_text("e2e rule", timeout=10)
    ctx.tree.wait_text("Forward: Satellite to Hub")
    ctx.tree.wait_text("Contains “SOS”")
    ctx.shot("added")


def case_a_save_keeps_every_column_and_delete_asks_first(ctx):
    start(ctx)
    ctx.app.mark()
    before = ctx.bridge.count()
    ctx.tree.click("Edit rule SOS to satellite")
    ctx.tree.wait_text("Edit rule")
    ctx.tree.wait_text("This rule also has settings this screen does not show (mesh channels, forwarding options). Saving keeps them.")
    for field, value in (("Rule name", "SOS to satellite"), ("Contains the text (optional)", "SOS"), ("At most (messages)", "5"), ("Every (seconds)", "60"), ("Urgency", "0")):
        shown = ctx.tree.entry_text(field)
        assert shown == value, (field, shown, value)
    ctx.tree.set_text("Rule name", "SOS to satellite now")
    ctx.tree.set_text("Contains the text (optional)", "HELP")
    ctx.tree.click_in_dialog("Save")
    put = ctx.bridge.wait_request("PUT", "/api/access-rules/1", since=before)
    body = put["body"]
    assert body["name"] == "SOS to satellite now", body
    assert json.loads(body["filters"]) == {"keyword": "HELP", "channels": "[0]"}, body["filters"]
    assert body["forward_options"] == '{"ttl_seconds":600}', body
    assert body["direction"] == "ingress" and body["schedule_type"] == "none", body
    assert (body["qos_level"], body["rate_limit_per_min"], body["rate_limit_window"], body["priority"]) == (1, 5, 60, 0), body
    ctx.app.wait_toast("Rule saved")
    ctx.tree.wait_text("SOS to satellite now", timeout=10)
    # The switch
    count = ctx.bridge.count()
    ctx.tree.toggle("Rule SOS to satellite now is on")
    ctx.bridge.wait_request("POST", "/api/access-rules/1/disable", since=count)
    ctx.tree.wait_switch("Rule SOS to satellite now is off", False)
    # Delete: what it changes, then "Keep it" changes nothing
    count = ctx.bridge.count()
    ctx.tree.click("Delete rule SOS to satellite now")
    ctx.tree.wait_text("Delete this rule?")
    ctx.tree.wait_text("Messages that matched it will no longer be forwarded to Satellite. You cannot undo this.")
    ctx.shot("delete-asked")
    ctx.tree.click_in_dialog("Keep it")
    assert not [r for r in ctx.bridge.requests(count) if r["method"] == "DELETE"], "Keep it deleted"
    ctx.tree.click("Delete rule SOS to satellite now")
    ctx.tree.click_in_dialog("Delete")
    ctx.bridge.wait_request("DELETE", "/api/access-rules/1", since=count)
    ctx.app.wait_toast("Rule deleted")
    ctx.tree.wait_gone("SOS to satellite now", timeout=10)
    ctx.tree.wait_text("No rules for mesh messages yet, so they stay on the mesh. Tap + to add one.")
    ctx.shot("empty-tab")


def case_the_queue_tab_cancels_and_retries(ctx):
    start(ctx)
    ctx.tree.click("Queue")
    ctx.tree.wait_text("Waiting to go out (4)", timeout=10)
    ctx.app.mark()
    before = ctx.bridge.count()
    ctx.tree.click_after("Position report", "Cancel")
    ctx.tree.wait_text("Cancel this message?")
    ctx.tree.click_in_dialog("Cancel message")
    ctx.bridge.wait_request("POST", "/api/deliveries/1/cancel", since=before)
    ctx.app.wait_toast("Cancelled. It will not be sent by Satellite.")
    ctx.tree.wait_text("Waiting to go out (3)", timeout=10)
    ctx.tree.wait_text("Did not go out (5)")
    count = ctx.bridge.count()
    ctx.tree.click_after("are you there", "Retry")
    ctx.tree.wait_text("Send again by Mesh?")
    ctx.tree.wait_text("The message goes back in the queue and is sent when Mesh is working.")
    ctx.tree.click_in_dialog("Retry")
    ctx.bridge.wait_request("POST", "/api/deliveries/7/retry", since=count)
    ctx.app.wait_toast("Back in the queue for Mesh")
    ctx.tree.wait_text("Waiting to go out (4)", timeout=10)
    ctx.shot("queue-after")
    ctx.app.open("home")
