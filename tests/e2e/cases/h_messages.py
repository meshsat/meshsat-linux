# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages and the New message dialog (MessagesScreen.kt)."""
SCENARIO = "mesh-only"


def case_new_message_to_a_node_opens_that_node(ctx):
    ctx.app.open("messages")
    ctx.tree.wait_text("Everyone on the mesh")
    ctx.tree.click("New message")
    ctx.tree.wait_text("New message")
    ctx.tree.click_containing("On the mesh, !a1b3c2ec")  # the node heard most recently, by its row
    ctx.tree.wait_text("By mesh, from your node.")
    labels = ctx.tree.texts()
    assert "MSPA" in labels, f"the chat is not the node's: {labels[:12]}"
    assert "Satellite" not in labels[:6], f"the chat opened is the Satellite one: {labels[:12]}"
    ctx.shot("chat-with-node")
    before = ctx.bridge.count()
    ctx.tree.set_text("Message", "hello node")
    ctx.tree.click("Send")
    sent = ctx.bridge.wait_request("POST", "/api/messages/send", since=before)
    assert sent["body"] == {"text": "hello node", "to": "!a1b3c2ec"}, sent["body"]
    ctx.app.open("messages")


def case_new_message_to_everyone_and_by_satellite(ctx):
    ctx.app.open("messages")
    ctx.tree.click("New message")
    ctx.tree.click_containing("Every node on your channel")
    ctx.tree.wait_text("The mesh channel")
    ctx.app.open("messages")
    ctx.tree.click("New message")
    ctx.tree.click_containing("Through Rock7 to the Hub, from anywhere")
    ctx.tree.wait_text("By satellite, through Rock7 to the Hub.")
    ctx.app.open("messages")


def case_counts_have_a_singular(ctx):
    ctx.app.open("messages")
    ctx.tree.wait_text("1 node")
    ctx.tree.wait_text("2 today")
