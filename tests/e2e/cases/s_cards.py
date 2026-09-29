# SPDX-License-Identifier: GPL-3.0-or-later
"""My card against a real, scratch Bridge (MESHSAT-1416): the card the Bridge signs is shown with
the fingerprint of the Bridge's own routing key, reads as a card Android accepts, and carries that
key; a name the Bridge is asked for goes on the card."""
import sys

SCENARIO = None  # the scratch Bridge


def case_my_card_is_signed_by_the_bridges_routing_key(ctx):
    sys.path.insert(0, ctx.app.app_dir)
    from meshsat.model import cards  # noqa: PLC0415

    identity = ctx.bridge.get("/api/routing/identity")
    pub = bytes.fromhex(identity["signing_pub"])
    status, card = ctx.bridge.call("GET", "/api/contacts/card")
    assert status == 200, (status, card)
    result, decoded = cards.decode(card["text"])
    assert result == "Ok" and decoded["signing_pub"] == pub and decoded["bridge_id"] == "", (result, decoded)
    assert card["fingerprint"] == cards.fingerprint(pub), card
    ctx.note(f"card for {decoded['name']!r}, fingerprint {card['fingerprint']}, {len(card['text'])} characters")
    ctx.app.tab("people")
    ctx.tree.click("My card", timeout=15)
    ctx.tree.wait_text(card["fingerprint"], timeout=10)
    ctx.tree.find(name="This phone's contact card as a QR code")
    ctx.shot("my-card-real")
    ctx.tree.click_in_dialog("Done")
    status, named = ctx.bridge.call("GET", "/api/contacts/card?name=Kyriakos")
    assert status == 200 and cards.decode(named["text"])[1]["name"] == "Kyriakos", named
    status, refused = ctx.bridge.call("GET", "/api/contacts/card?name=" + "x" * 49)
    assert status == 400 and "name over 48 characters" in (refused or {}).get("error", ""), (status, refused)
