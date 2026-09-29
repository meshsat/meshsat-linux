# SPDX-License-Identifier: GPL-3.0-or-later
"""The radio settings against a real, scratch Bridge with no node at all (MESHSAT-1405): the
named settings say nothing is loaded, a write is refused with its reason instead of the old
silent 200, and the page offers the node page instead of fields."""

SCENARIO = None  # the scratch Bridge


def case_without_a_node_nothing_is_written(ctx):
    status, named = ctx.bridge.call("GET", "/api/config?format=names")
    ctx.note(f"named: {status} {named}")
    assert status == 200 and named.get("loaded") is False and named.get("channels") == [] and named.get("config") == {}, (status, named)
    status, answer = ctx.bridge.call("POST", "/api/config/radio", {"section": "lora", "config": {"hop_limit": 4}})
    assert status == 409 and "has not sent" in str(answer), (status, answer)
    status, answer = ctx.bridge.call("POST", "/api/config/radio", {"section": "radio", "config": {"hop_limit": 4}})
    assert status == 400 and "unknown config section" in str(answer), (status, answer)
    status, answer = ctx.bridge.call("POST", "/api/channels", {"index": 0, "name": "x"})
    assert status == 409, (status, answer)
    status, answer = ctx.bridge.call("POST", "/api/admin/set_clock", {})
    assert status == 503, (status, answer)
    status, log = ctx.bridge.call("GET", "/api/mesh/radio-log?after=0&follow=1")
    assert status == 200 and log.get("available") is False and log.get("following") is False and log.get("debug_log_api_enabled") is None, (status, log)
    ctx.app.open("radio-config")
    ctx.tree.wait_text("Your phone is not connected to your node, so its settings cannot be read or changed.", timeout=15)
    ctx.tree.click("Radio")
    ctx.tree.wait_text("Connect your node to read its settings.")
    ctx.shot("no-node")
    ctx.app.open("home")
