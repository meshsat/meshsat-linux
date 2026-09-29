# SPDX-License-Identifier: GPL-3.0-or-later
"""A chat's own key (MessagesScreen.kt:465-548, 854-969): the lock opens the section, Generate
fills the field and saves nothing, Save keeps the key in the Bridge for that chat only (B21) and
closes the lock, the key comes back when the chat is opened again, Copy and Paste, an invalid key
refused in Android's words, Remove."""
import time

SCENARIO = "sim-ready"
CHAT = "sms:+31611111111"
PATH = "/api/keys/sms/%2B31611111111"
FIELD = "Hex key (64 chars)"


def field(ctx):
    """The key's entry, hidden ("password text") or shown ("text")."""
    deadline = time.time() + 5
    while True:
        found = ctx.tree.find_all("password text", name=FIELD) or ctx.tree.find_all("text", name=FIELD)
        if found or time.time() > deadline:
            assert found, "no key entry"
            return found[0]
        time.sleep(0.2)


def keys(ctx, since: int, method: str) -> list:
    return [r for r in ctx.bridge.requests(since) if r["method"] == method and r["path"].startswith("/api/keys/")]


def amber_lock(ctx) -> bool:
    return any(w["type"] == "Image" and "fg-amber" in w["css"] for w in ctx.app.inspect()["widgets"])


def open_chat(ctx, chat: str = CHAT) -> None:
    ctx.app.open("messages")
    ctx.app.open("chat/" + chat)
    ctx.tree.click("Encryption key", timeout=10)
    ctx.tree.wait_text("Conversation Encryption Key", timeout=8)


def case_a_generate_save_and_the_lock(ctx):
    ctx.bridge.scenario("sim-ready")
    ctx.app.refresh()
    open_chat(ctx)
    ctx.tree.wait_text("AES-256-GCM key for this conversation. Messages are encrypted/decrypted with this key.")
    assert not amber_lock(ctx), "the lock is closed with no key anywhere"
    assert not ctx.tree.find_all("button", name="Remove"), "Remove without a key"
    ctx.tree.click("Show")
    ctx.tree.find("button", name="Hide")
    before = ctx.bridge.count()
    ctx.tree.click("Generate")
    time.sleep(0.5)
    generated = field(ctx).text()
    assert len(generated) == 64 and all(c in "0123456789abcdef" for c in generated), generated
    assert not keys(ctx, before, "PUT"), "Generate saved the key"
    ctx.app.mark()
    ctx.tree.click("Save")
    ctx.app.wait_toast("Key saved", timeout=8)
    puts = keys(ctx, before, "PUT")
    assert len(puts) == 1 and puts[0]["path"] == PATH and puts[0]["body"] == {"key": generated}, puts
    assert ctx.bridge.state()["chat_keys"] == {"sms:+31611111111": generated}
    ctx.tree.find("button", name="Remove", timeout=5)
    time.sleep(0.5)
    assert amber_lock(ctx), "the lock stayed open after Save"
    ctx.shot("chat-key")
    # Another chat keeps no key of its own
    open_chat(ctx, "!ffffffff")
    assert field(ctx).text() == ""
    assert not ctx.tree.find_all("button", name="Remove")
    # Back in the first chat the Bridge's key is there
    open_chat(ctx)
    deadline = time.time() + 8
    while time.time() < deadline and field(ctx).text() != generated:
        time.sleep(0.3)
    assert field(ctx).text() == generated
    ctx.tree.find("button", name="Remove")


def case_b_copy_paste_invalid_and_remove(ctx):
    open_chat(ctx)
    ctx.app.mark()
    ctx.tree.click("Copy")
    ctx.app.wait_toast("Key copied", timeout=5)
    kept = field(ctx).text()
    field(ctx).set_text("")
    ctx.tree.click("Paste")
    ctx.app.wait_toast("Key pasted", timeout=5)
    assert field(ctx).text() == kept
    before = ctx.bridge.count()
    field(ctx).set_text("abc")
    ctx.tree.click("Save")
    ctx.app.wait_toast("Invalid key — 64 hex chars required", timeout=5)
    assert not keys(ctx, before, "PUT"), "an invalid key went to the Bridge"
    ctx.tree.click("Remove")
    ctx.app.wait_toast("Key removed — messages will show encrypted", timeout=8)
    assert [r["path"] for r in keys(ctx, before, "DELETE")] == [PATH]
    assert ctx.bridge.state()["chat_keys"] == {}
    assert field(ctx).text() == ""
    assert not ctx.tree.find_all("button", name="Remove")


def case_c_a_sealed_sms_carries_the_lock(ctx):
    """A bubble of an SMS that went or came sealed, opened by the Bridge: Android's amber lock, "Decrypted"."""
    now = int(time.time())
    ctx.bridge.scenario("sim-ready")
    ctx.bridge.set("GET /api/cellular/sms?limit=200", [
        {"id": 1, "direction": "rx", "phone": "+31611111111", "text": "Sealed and opened", "timestamp": now - 120, "status": "received", "encrypted": True},
        {"id": 2, "direction": "tx", "phone": "+31611111111", "text": "In the clear", "timestamp": now - 60, "status": "sent", "encrypted": False}])
    ctx.app.refresh()
    ctx.app.open("messages")
    ctx.app.open("chat/" + CHAT)
    ctx.tree.wait_text("Sealed and opened", timeout=10)
    assert len(ctx.tree.find_all(name="Decrypted")) == 1, "one lock, on the sealed SMS only"
    ctx.shot("sealed-bubble")
