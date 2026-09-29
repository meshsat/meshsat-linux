# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Messaging and the SMS page (SettingsScreen.kt): the Encryption card writing the SMS
link's two chains (the key, the optional decrypt of "Auto-decrypt incoming SMS"), a key that
cannot encrypt refused before it goes, compression per link only where the Bridge can encode,
the brevity codes; the number a text with no recipient goes to, saved over the SMS gateway
with its switch and secrets kept. Every case starts from the scenario afresh."""
import json
import time

SCENARIO = "messaging"
KEY = "0123456789abcdef" * 4
KEY_LABEL = "AES-256-GCM Key (hex)"


def start(ctx, scenario: str = "messaging") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("setup/messaging")
    ctx.tree.wait_text("Fallback key — used when no per-conversation key is set.", timeout=10)
    ctx.tree.find("button", name="SMS Off", timeout=10)


def key_entry(ctx):
    deadline = time.time() + 5
    while True:
        found = ctx.tree.find_all("password text", name=KEY_LABEL) or ctx.tree.find_all("text", name=KEY_LABEL)
        if found or time.time() > deadline:
            assert found, "no key entry"
            return found[0]
        time.sleep(0.2)


def puts(ctx, before: int, link: str) -> list:
    return [r["body"] for r in ctx.bridge.requests(before) if r["method"] == "PUT" and r["path"] == f"/api/interfaces/{link}/transforms"]


def case_the_three_cards_in_androids_words(ctx):
    start(ctx)
    for words in ("Encryption", "Encryption enabled", "Auto-decrypt incoming SMS", KEY_LABEL, "Message compression",
                  "Only for links where the other end is MeshSat too: anyone else sees a line of letters.", "Iridium SBD",
                  "MSVQ-SC needs its encoder beside the Bridge, and this phone has none, so messages go out as typed.",
                  "Quick messages", "30 brevity codes loaded", "Copy.", "#1", "Mission complete.", "#10", "... and 20 more",
                  "Wire format: 2 bytes (0xCA + message ID). Auto-detected on receive."):
        ctx.tree.wait_text(words)
    for button in ("Show", "Generate", "Save", "Copy", "Paste", "Share"):
        ctx.tree.find("button", name=button)
    ctx.tree.switch("Encryption enabled")  # on or off as an earlier case left the app's settings
    assert not ctx.tree.find("button", name="SMS MSVQ-SC").sensitive, "MSVQ-SC offered without an encoder"
    ctx.shot("messaging")


def case_a_generated_key_becomes_the_sms_chains(ctx):
    start(ctx)
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.tree.click("Generate")
    ctx.app.wait_toast("Key generated")
    key = key_entry(ctx).text()
    assert len(key) == 64, key
    # Encryption is off; "Auto-decrypt incoming SMS" is on (Android's default): only the receive chain.
    ctx.bridge.wait_request("PUT", "/api/interfaces/cellular_0/transforms", since=before)
    body = puts(ctx, before, "cellular_0")[-1]
    assert json.loads(body["egress_transforms"]) == [] and json.loads(body["ingress_transforms"]) == [
        {"type": "decrypt", "params": {"key": key, "optional": "true"}}, {"type": "base64"}], body
    mark = ctx.bridge.count()
    ctx.tree.toggle("Encryption enabled")
    ctx.bridge.wait_request("PUT", "/api/interfaces/cellular_0/transforms", since=mark)
    body = puts(ctx, mark, "cellular_0")[-1]
    assert json.loads(body["egress_transforms"]) == [{"type": "encrypt", "params": {"key": key}}, {"type": "base64"}], body
    ctx.tree.wait_switch("Encryption enabled", True)
    mark = ctx.bridge.count()
    ctx.tree.toggle("Auto-decrypt incoming SMS")
    ctx.bridge.wait_request("PUT", "/api/interfaces/cellular_0/transforms", since=mark)
    assert json.loads(puts(ctx, mark, "cellular_0")[-1]["ingress_transforms"]) == []


def case_a_key_that_cannot_encrypt_is_refused(ctx):
    start(ctx)
    if not ctx.tree.switch("Auto-decrypt incoming SMS").checked:  # as an earlier case left it
        ctx.tree.toggle("Auto-decrypt incoming SMS")
        ctx.tree.wait_switch("Auto-decrypt incoming SMS", True)
    before = ctx.bridge.count()
    ctx.app.mark()
    key_entry(ctx).set_text("1234")
    ctx.tree.click("Save")
    ctx.app.wait_toast("A key is 64 hexadecimal characters (0-9, a-f).")
    assert all("1234" not in json.dumps(b) for b in puts(ctx, before, "cellular_0")), "a key that cannot encrypt was sent"
    mark = ctx.bridge.count()
    key_entry(ctx).set_text(KEY.upper())
    ctx.tree.click("Save")
    ctx.app.wait_toast("Key saved")
    body = puts(ctx, mark, "cellular_0")[-1]
    assert json.loads(body["ingress_transforms"]) == [{"type": "decrypt", "params": {"key": KEY, "optional": "true"}}, {"type": "base64"}], body


def case_show_copy_and_paste(ctx):
    start(ctx)
    key_entry(ctx).set_text(KEY)
    ctx.tree.click("Show")
    ctx.tree.find("button", name="Hide")
    ctx.app.mark()
    ctx.tree.click("Copy")
    ctx.app.wait_toast("Key copied to clipboard")
    key_entry(ctx).set_text("")
    ctx.tree.click("Paste")
    ctx.app.wait_toast("Key imported from clipboard")
    assert key_entry(ctx).text() == KEY
    ctx.tree.click("Hide")


def case_compression_where_the_bridge_can_encode(ctx):
    start(ctx, "messaging-encoder")
    deadline = time.time() + 8  # the capabilities answer comes after the links
    while not ctx.tree.find("button", name="SMS MSVQ-SC").sensitive and time.time() < deadline:
        time.sleep(0.3)
    assert ctx.tree.find("button", name="SMS MSVQ-SC").sensitive, "MSVQ-SC not offered with an encoder"
    ctx.tree.wait_gone("MSVQ-SC needs its encoder")
    before = ctx.bridge.count()
    ctx.tree.click("Iridium SBD MSVQ-SC")
    ctx.bridge.wait_request("PUT", "/api/interfaces/iridium_0/transforms", since=before)
    assert json.loads(puts(ctx, before, "iridium_0")[-1]["egress_transforms"]) == [{"type": "msvqsc", "params": {"stages": "3"}}]
    ctx.tree.wait_text("MSVQ-SC stages (fewer = smaller, lower fidelity)")
    ctx.shot("compression")
    mark = ctx.bridge.count()
    ctx.tree.click("6 (13B)")
    ctx.bridge.wait_request("PUT", "/api/interfaces/iridium_0/transforms", since=mark)
    assert json.loads(puts(ctx, mark, "iridium_0")[-1]["egress_transforms"]) == [{"type": "msvqsc", "params": {"stages": "6"}}]
    mark = ctx.bridge.count()
    ctx.tree.click("SMS MSVQ-SC")
    ctx.bridge.wait_request("PUT", "/api/interfaces/cellular_0/transforms", since=mark)
    chain = json.loads(puts(ctx, mark, "cellular_0")[-1]["egress_transforms"])
    # Compression first, base64 last; the encryption between them when an earlier case left it on.
    assert chain[0] == {"type": "msvqsc", "params": {"stages": "6"}} and chain[-1] == {"type": "base64"} and len(chain) in (2, 3), chain


def case_a_refused_chain_says_why(ctx):
    start(ctx)
    ctx.bridge.set("PUT /api/interfaces/cellular_0/transforms",
                   {"error": "transform validation failed", "errors": ["egress: encrypt key must be 64 hex characters (AES-256; 32 or 48 for AES-128 or -192)"]}, status=400)
    ctx.app.mark()
    ctx.tree.click("Generate")
    ctx.app.wait_toast("egress: encrypt key must be 64 hex characters")


def case_no_recipient_number_goes_over_the_sms_gateway(ctx):
    ctx.bridge.scenario("messaging")
    ctx.app.open("setup/sms")
    for words in ("Where a text goes with no recipient", "Optional number, e.g. +31612345678",
                  "Only used when a message has no recipient of its own: a routing rule that forwards to SMS without naming a number."):
        ctx.tree.wait_text(words, timeout=10)
    # Text messages as Android's card (SettingsScreen.kt:1915-1942): "SMS" and its value in one
    # row (no SIM here, so why it cannot go), then the sentence; none of the modem's facts
    ctx.tree.wait_text("This phone cannot send SMS.", timeout=10)
    texts = ctx.tree.texts()
    at = texts.index("Text messages")
    assert texts[at + 1:at + 3] == ["SMS", "This phone cannot send SMS."], texts[at:at + 4]
    for gone in ("Modem", "SIM", "Network", "Number", "Sent, received"):
        assert gone not in texts, f"{gone!r} is on the SMS page: {texts}"
    before = ctx.bridge.count()
    ctx.tree.set_text("Optional number, e.g. +31612345678", "abc")
    ctx.tree.click("Save")
    ctx.tree.wait_text("Enter a phone number, e.g. +31612345678.")
    assert not [r for r in ctx.bridge.requests(before) if r["method"] == "PUT"], "a number that is not one was saved"
    ctx.app.mark()
    ctx.tree.set_text("Optional number, e.g. +31612345678", "+31612345678")
    ctx.tree.click("Save")
    ctx.app.wait_toast("Saved")
    sent = [r["body"] for r in ctx.bridge.requests(before) if r["method"] == "PUT" and r["path"] == "/api/gateways/cellular"]
    assert sent and sent[0] == {"enabled": True, "config": {"destination_numbers": ["+31612345678"], "allowed_senders": ["+31600000001"],
                                                            "webhook_in_secret": "****", "max_sms_segments": 1}}, sent
    ctx.shot("sms")
    ctx.app.open("home")
