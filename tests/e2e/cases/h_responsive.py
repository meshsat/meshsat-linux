# SPDX-License-Identifier: GPL-3.0-or-later
"""The interface answers while the Bridge is slow: no call to it on the main loop."""
import time

SCENARIO = "mesh-only"


def case_ui_answers_while_the_bridge_is_slow(ctx):
    ctx.app.open("home")
    ctx.tree.wait_text("Messages can go out by mesh.")
    # 1.5 s per answer: a poll of fourteen calls takes twenty seconds, yet no call may hold
    # the screen (a longer delay would pass the client's own 2 s timeout and read as "down").
    ctx.bridge.delay(1.5)
    ctx.app.mark()
    try:
        for route, title in (("setup/integrations", "Ham radio (APRS)"), ("radio-config", "Mesh radio settings"), ("setup/satellite", "Satellite passes"), ("setup/hub", "Hub connection"), ("home", "Messages can go out by")):
            ctx.app.open(route)
            started = time.time()
            ctx.tree.wait_text(title, timeout=6)
            took = time.time() - started
            # a walk of the tree is a few hundred bus calls: about a second on the phone, never more
            assert took < 3.0, f"{route} took {took:.1f} s to answer while the Bridge was slow"
        slow = [e for e in ctx.app.http_since_mark() if e.get("ms", 0) >= 1400]
        assert slow, "no call took the Bridge's delay: the case proved nothing"
    finally:
        ctx.bridge.delay(0)
