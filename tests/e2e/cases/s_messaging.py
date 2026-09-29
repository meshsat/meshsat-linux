# SPDX-License-Identifier: GPL-3.0-or-later
"""What Messaging and the SMS page write, against a real, scratch Bridge (MESHSAT-1412): a link's
chains set on their own keep everything else about the link, a key that cannot encrypt is
refused when saved, an optional decrypt is taken; the SMS gateway may have no default number,
and its secret survives a write of the masked config the Bridge answered."""
import json

SCENARIO = None  # the scratch Bridge
KEY = "0123456789abcdef" * 4


def link_record(ctx, link: str) -> dict:
    _s, listed = ctx.bridge.call("GET", "/api/interfaces")
    return next((i for i in listed or [] if i.get("id") == link), {})


def case_chains_set_on_their_own_keep_the_link(ctx):
    link = "iridium_imt_0"  # a link the scratch Bridge always has
    before = link_record(ctx, link)
    ctx.note(f"{link} before: enabled {before.get('enabled')}, egress {before.get('egress_transforms')!r}")
    assert before, "the scratch Bridge has no iridium_imt_0"
    bad = json.dumps([{"type": "encrypt", "params": {"key": "0123"}}])
    status, answer = ctx.bridge.call("PUT", f"/api/interfaces/{link}/transforms", {"egress_transforms": bad})
    assert status == 400 and "64 hex" in json.dumps(answer), (status, answer)
    chain = json.dumps([{"type": "msvqsc", "params": {"stages": "4"}}, {"type": "encrypt", "params": {"key": KEY}}])
    back = json.dumps([{"type": "decrypt", "params": {"key": KEY, "optional": "true"}}])
    status, answer = ctx.bridge.call("PUT", f"/api/interfaces/{link}/transforms", {"egress_transforms": chain, "ingress_transforms": back})
    assert status == 200, (status, answer)
    after = link_record(ctx, link)
    assert after.get("egress_transforms") == chain and after.get("ingress_transforms") == back, after
    assert after.get("enabled") == before.get("enabled") and after.get("label") == before.get("label"), (before, after)
    status, caps = ctx.bridge.call("GET", "/api/transforms/capabilities")
    ctx.note(f"capabilities: {caps}")
    assert status == 200 and caps.get("msvqsc_encode") is False, caps
    ctx.bridge.call("PUT", f"/api/interfaces/{link}/transforms", {"egress_transforms": "[]", "ingress_transforms": "[]"})


def case_the_sms_gateway_without_a_default_number(ctx):
    config = {"destination_numbers": [], "allowed_senders": ["+31600000001"], "webhook_in_enabled": False, "webhook_in_secret": "s3cret-e2e", "max_sms_segments": 1}
    status, answer = ctx.bridge.call("PUT", "/api/gateways/cellular", {"enabled": False, "config": config})
    assert status == 200, f"no default number refused: {status} {answer}"
    status, gateway = ctx.bridge.call("GET", "/api/gateways/cellular")
    ctx.note(f"cellular gateway: {gateway}")
    assert status == 200 and gateway["config"].get("webhook_in_secret") == "****", gateway
    # The page's own write: the masked config back, with one number.
    status, answer = ctx.bridge.call("PUT", "/api/gateways/cellular", {"enabled": False, "config": dict(gateway["config"], destination_numbers=["+31612345678"])})
    assert status == 200, (status, answer)
    ctx.app.open("setup/sms")
    ctx.tree.wait_text("Where a text goes with no recipient", timeout=10)
    assert ctx.tree.entry_text("Optional number, e.g. +31612345678") == "+31612345678"
    ctx.app.mark()
    ctx.tree.set_text("Optional number, e.g. +31612345678", "")
    ctx.tree.click("Save")
    ctx.app.wait_toast("Saved")
    status, gateway = ctx.bridge.call("GET", "/api/gateways/cellular")
    assert gateway["config"].get("destination_numbers") in ([], None), gateway
    ctx.app.open("home")
