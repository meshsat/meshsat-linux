# SPDX-License-Identifier: GPL-3.0-or-later
"""A chat's own key against a real, scratch Bridge (B21, the per-chat keys batch): Save puts the
key in the Bridge's keystore under that number, the Bridge gives the same key back for that chat
and no other, Remove takes it away."""
import time

SCENARIO = None  # the scratch Bridge
NUMBER = "+31600000077"
PATH = "/api/keys/sms/%2B31600000077"
FIELD = "Hex key (64 chars)"


def field(ctx):
    deadline = time.time() + 5
    while True:
        found = ctx.tree.find_all("password text", name=FIELD) or ctx.tree.find_all("text", name=FIELD)
        if found or time.time() > deadline:
            assert found, "no key entry"
            return found[0]
        time.sleep(0.2)


def case_a_chat_key_is_kept_by_the_bridge(ctx):
    status, _body = ctx.bridge.call("GET", PATH)
    assert status == 404, status
    ctx.app.open("messages")
    ctx.app.open("chat/sms:" + NUMBER)
    ctx.tree.click("Encryption key", timeout=10)
    ctx.tree.wait_text("Conversation Encryption Key", timeout=8)
    ctx.tree.click("Show")
    ctx.tree.click("Generate")
    time.sleep(0.5)
    key = field(ctx).text()
    assert len(key) == 64, key
    ctx.app.mark()
    ctx.tree.click("Save")
    ctx.app.wait_toast("Key saved", timeout=10)
    status, body = ctx.bridge.call("GET", PATH)
    assert status == 200 and body.get("key") == key, (status, body)
    status, _body = ctx.bridge.call("GET", "/api/keys/sms/%2B31600000078")
    assert status == 404, "the key reached another number"
    ctx.tree.click("Remove")
    ctx.app.wait_toast("Key removed — messages will show encrypted", timeout=10)
    status, _body = ctx.bridge.call("GET", PATH)
    assert status == 404, status
