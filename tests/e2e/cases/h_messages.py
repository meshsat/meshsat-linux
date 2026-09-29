# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages and the New message dialog (MessagesScreen.kt)."""
SCENARIO = "mesh-only"


def case_new_message_to_a_node_opens_that_node(ctx):
    ctx.app.open("messages")
    ctx.tree.wait_text("Everyone on the mesh")
    ctx.tree.click("New message")
    ctx.tree.wait_text("New message")
    ctx.tree.click_containing("On the mesh, !a1b3c2ec")  # the node heard most recently, by its row
    ctx.tree.wait_text("Directly to this node on the mesh.")
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
    ctx.tree.wait_text("By satellite, when the modem is back.")
    ctx.app.open("messages")


def case_counts_have_a_singular(ctx):
    ctx.app.open("messages")
    ctx.tree.wait_text("1 node")
    ctx.tree.wait_text("2 today")


def case_search_filters_all_messages(ctx):
    ctx.app.open("messages")
    ctx.tree.wait_text("Everyone on the mesh")
    assert not ctx.tree.find_all("text", name="Search messages"), "the search bar showed on Chats"
    ctx.tree.click("All Messages")
    ctx.tree.wait_text("first light")
    ctx.tree.wait_text("MESH")
    ctx.tree.wait_text("RX")
    ctx.tree.wait_text("TX")
    ctx.tree.set_text("Search messages", "FIRST")
    ctx.tree.wait_text("first light")
    ctx.tree.wait_gone("mew")
    ctx.shot("search")
    ctx.tree.click("Clear")
    ctx.tree.wait_text("mew")
    ctx.tree.set_text("Search messages", "nothing like this")
    ctx.tree.wait_text("No messages yet")
    ctx.tree.click("Clear")
    ctx.tree.click("Chats")
    ctx.tree.wait_text("Everyone on the mesh")


def case_new_message_to_a_typed_number(ctx):
    """A phone number in the same dialog: "Text this number" only for a number, then its SMS chat."""
    ctx.app.open("messages")
    ctx.tree.click("New message")
    ctx.tree.wait_text("Or a phone number, e.g. +31612345678")
    assert not ctx.tree.find("button", name="Text this number").sensitive, "offered with no number"
    ctx.tree.set_text("Or a phone number, e.g. +31612345678", "12345")
    assert not ctx.tree.find("button", name="Text this number").sensitive, "offered for five digits"
    ctx.tree.set_text("Or a phone number, e.g. +31612345678", "+31 6 1234 5678")
    ctx.shot("new-message-number")
    ctx.tree.click_in_dialog("Text this number")
    ctx.tree.wait_text("+31612345678", timeout=8)
    ctx.app.open("messages")

