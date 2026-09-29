# SPDX-License-Identifier: GPL-3.0-or-later
"""The welcome (Onboarding.kt:64-126): at the first start it is the window's only content, says
what the app asks for and why, and "Continue" leads to Home; only then is the position asked
for; the next start goes straight to Home."""
import time

SCENARIO = "mesh-only"
PREFS = {"welcome_done": False}

WORDS = ("Keeping people connected when the network is not.",
         "This phone becomes a gateway. With a MeshSat node it sends and receives over the mesh radio and by satellite, and by SMS while there is a mobile signal.",
         "What the app asks for, and why", "Bluetooth", "To find your MeshSat node and talk to it over Bluetooth.", "Location",
         "Your position for an SOS and the map.", "Notifications", "Incoming messages, the satellite signal in the status bar, and an SOS in progress.",
         "You can change any of these later in the phone's settings for MeshSat.")


def restart(ctx) -> None:
    ctx.app.stop()
    ctx.app.start()
    ctx.tree = ctx.app.tree
    ctx.app.mark()


def case_shown_at_the_first_start_only(ctx):
    ctx.tree.wait_text(WORDS[0], timeout=15)
    texts = ctx.tree.texts()
    for words in WORDS:
        assert any(words == t or words in t for t in texts), f"missing on the welcome: {words!r}"
    ctx.tree.find("button", name="Continue")
    # Nothing else: no tab bar, no strip, no Home
    assert not ctx.tree.find_all("button", name="Home"), "the tab bar shows under the welcome"
    assert not ctx.tree.has_text("Messages can go out by mesh."), "Home shows under the welcome"
    assert not any(e.get("kind") == "locate" for e in ctx.app.trace()), "the position was asked for before Continue"
    ctx.shot("welcome")
    ctx.app.mark()
    ctx.tree.click("Continue")
    ctx.tree.wait_text("Messages can go out by mesh.", timeout=10)
    ctx.tree.find("button", name="Home")
    assert any(e.get("kind") == "locate" for e in ctx.app.trace_since_mark()), "Continue did not ask for the position"
    ctx.shot("after-continue")
    time.sleep(1.5)  # the preferences are written a second after the change
    restart(ctx)
    ctx.tree.wait_text("Messages can go out by mesh.", timeout=15)
    assert not ctx.tree.has_text(WORDS[0]), "the welcome came back at the second start"
