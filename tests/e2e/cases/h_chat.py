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


def case_the_composer_says_how_the_message_goes(ctx):
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("To everyone on the mesh channel.")
    assert not ctx.tree.find("button", name="Send").sensitive, "Send is live with nothing typed"
    ctx.tree.set_text("Message", "x")
    assert ctx.tree.find("button", name="Send").sensitive
    ctx.tree.set_text("Message", "")
    ctx.app.open("chat/satellite")
    ctx.tree.wait_text("By satellite, when the modem is back.")
    ctx.tree.set_text("Message", "hello")
    ctx.tree.wait_text("By satellite, when the modem is back. 5 bytes, 1 credit.")
    ctx.tree.set_text("Message", "x" * 341)
    ctx.tree.wait_text("Too long for a satellite message: 341 bytes, 340 at most. Shorten it or send it in two.")
    assert not ctx.tree.find("button", name="Send").sensitive, "a message too long for one frame can be sent"
    ctx.shot("too-long")
    ctx.tree.set_text("Message", "x" * 340)
    ctx.tree.wait_text("By satellite, when the modem is back. 340 bytes, 7 credits.")
    assert ctx.tree.find("button", name="Send").sensitive
    ctx.tree.set_text("Message", "")
    ctx.app.open("messages")


def case_own_bubbles_carry_a_delivery_mark(ctx):
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("hello from the phone")
    ctx.tree.find("image", name="Sent")
    marks = [n.name for n in ctx.tree.find_all("image") if n.name in ("Sent", "Queued", "Failed", "Delivered", "May have been sent")]
    assert marks == ["Sent"], f"marks on the bubbles: {marks} (only the phone's own message carries one)"
    ctx.tree.wait_text("MESH")
    ctx.shot("bubbles")
    ctx.app.open("messages")


def case_the_mesh_down_refuses_the_send(ctx):
    ctx.bridge.scenario("bluetooth-pairing")
    ctx.app.refresh()
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("On the mesh, when your node is connected.", timeout=10)
    ctx.app.mark()
    before = ctx.bridge.count()
    ctx.tree.set_text("Message", "into the void")
    ctx.tree.click("Send")
    ctx.app.wait_toast("Not sent: your MeshSat node is not connected. Connect it in Setup.")
    assert not [r for r in ctx.bridge.requests(before) if r["path"] == "/api/messages/send"], "the text was sent with the node down"
    assert ctx.tree.entry_text("Message") == "into the void"
    ctx.tree.set_text("Message", "")
    ctx.bridge.scenario("mesh-only")
    ctx.app.refresh()
    ctx.app.open("messages")
