# SPDX-License-Identifier: GPL-3.0-or-later
"""The chat: one send is one request, the bubble shows, the entry clears."""
SCENARIO = "mesh-only"


def case_send_posts_once_and_shows_the_bubble(ctx):
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("Everyone on the mesh")
    ctx.tree.wait_text("mew")
    before = ctx.bridge.count()
    ctx.tree.set_text("Message", "test one two")
    ctx.tree.click("Send")
    ctx.bridge.wait_request("POST", "/api/messages/send", since=before)
    sends = [r for r in ctx.bridge.requests(before) if r["path"] == "/api/messages/send"]
    assert len(sends) == 1, f"{len(sends)} sends for one tap"
    assert sends[0]["body"] == {"text": "test one two"}, sends[0]["body"]
    ctx.tree.wait_text("test one two", timeout=10)
    assert ctx.tree.entry_text("Message") == "", "the entry kept the text after sending"
    ctx.shot("sent")
    # The bubble stays across polls and the chat is not rebuilt for nothing.
    ctx.app.refresh()
    ctx.tree.wait_text("test one two")


def case_a_failed_send_keeps_the_text_and_says_why(ctx):
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("Everyone on the mesh")
    ctx.bridge.set("POST /api/messages/send", {"error": "mesh transport unavailable"}, status=503)
    ctx.app.mark()
    ctx.tree.set_text("Message", "will not go")
    ctx.tree.click("Send")
    ctx.app.wait_toast("mesh transport unavailable")
    assert ctx.tree.entry_text("Message") == "will not go", "the text was lost on a failed send"
    ctx.bridge.scenario("mesh-only", reset_log=False)
