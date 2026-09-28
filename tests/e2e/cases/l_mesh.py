# SPDX-License-Identifier: GPL-3.0-or-later
"""A text both ways with a radio on the mesh (a T-Deck on the laptop, tools/e2e-farend.py):
a text the far end sent before this run shows in the chat; a text typed in the composer
leaves through the Bridge and is heard at the far end (the runner checks the far end's log
after the run). Needs MESHSAT_E2E_INBOUND (the text the far end sent) and writes the text
it sent to MESHSAT_E2E_EXPECT_FILE for the runner."""
import os
import time

from driver import BenchError

SCENARIO = None  # the live Bridge


def case_text_both_ways_with_a_tdeck(ctx):
    inbound = os.environ.get("MESHSAT_E2E_INBOUND", "")
    if not inbound:
        raise BenchError("no MESHSAT_E2E_INBOUND: the runner did not send a text from the far end")
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("Everyone on the mesh")
    # The far end's text: heard by the node, stored by the Bridge, shown in the chat.
    try:
        ctx.tree.wait_text(inbound, timeout=90)
    except AssertionError as error:
        stored = ctx.bridge.get("/api/messages?limit=50").get("messages", [])
        if not any(inbound in (m.get("decoded_text") or "") for m in stored):
            raise BenchError(f"the Bridge never received {inbound!r}: the radio did not hear the far end (its last texts: {[m.get('decoded_text') for m in stored[:5]]})") from error
        raise
    ctx.shot("inbound")
    # Our own text, out through the Bridge.
    nonce = f"e2e {int(time.time()) % 100000:05d}"
    ctx.app.mark()
    ctx.tree.set_text("Message", nonce)
    ctx.tree.click("Send")
    ctx.tree.wait_text(nonce, timeout=20)
    sends = ctx.app.http_since_mark("POST", "/api/messages/send")
    assert len(sends) == 1 and sends[0].get("status") == 200, sends
    deadline = time.time() + 30
    while time.time() < deadline:
        packets = ctx.bridge.get("/api/packets?limit=50").get("packets", [])
        if any(p.get("dir") == "tx" and (p.get("text") or "") == nonce for p in packets):
            break
        time.sleep(2)
    else:
        raise AssertionError(f"the Bridge's packet feed never showed {nonce!r} going out")
    expect = os.environ.get("MESHSAT_E2E_EXPECT_FILE", "")
    if expect:
        with open(expect, "a", encoding="utf-8") as handle:
            handle.write(nonce + "\n")
    ctx.note(f"inbound {inbound!r} shown; outbound {nonce!r} left through the Bridge")
    ctx.shot("outbound")
