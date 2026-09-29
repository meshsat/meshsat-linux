# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Advanced > Diagnostics, "Share the Bridge on this network" (this edition's own, no
Android counterpart), against the scripted Bridge: off by default; switching it on asks first,
"Not now" runs nothing, "Share" runs exactly one pkexec command and the line under the switch
names the address to open; switching off asks nothing; the switch follows the flag, never its
own last position. Under test nothing privileged runs: the command goes to the trace and
meshsat-share's flag is a file of the module's own (the driver's MESHSAT_APP_SHARE_FLAG). The
addresses are MESHSAT_APP_ADDRESSES, the port the one written in this module's bridge.env."""
import os
import time

SCENARIO = "advanced"
ENV = {"MESHSAT_APP_ADDRESSES": "192.168.1.20,10.0.0.5", "MESHSAT_APP_BRIDGE_ENV": "{work}/bridge.env"}
TITLE = "Share the Bridge on this network"
LOCAL = "Only this phone can open the Bridge."
SHARED = "Open http://192.168.1.20:6051 or http://10.0.0.5:6051 in a browser on the same network."
QUESTION = "Share the Bridge on this network?"
BODY = ("Anyone on this network can then open the Bridge without a password: read and send messages, start an SOS, "
        "change every setting and spend satellite credit. Share it only on a network you trust, and switch it off when you are done.")
ON = ["pkexec", "/usr/lib/meshsat/bin/meshsat-share", "on"]
OFF = ["pkexec", "/usr/lib/meshsat/bin/meshsat-share", "off"]


def start(ctx, shared: bool) -> None:
    """The page on view with the Bridge shared or not, whatever the case before left."""
    with open(os.path.join(ctx.app.work, "bridge.env"), "w", encoding="utf-8") as handle:
        handle.write("MESHSAT_MODE=direct\nMESHSAT_PORT=6051\n")
    if shared:
        open(ctx.app.share_flag, "w", encoding="utf-8").close()
    elif os.path.exists(ctx.app.share_flag):
        os.remove(ctx.app.share_flag)
    ctx.bridge.scenario("advanced")
    ctx.app.refresh()
    ctx.app.open("setup/diagnostics")
    ctx.tree.wait_text(TITLE, timeout=10)
    ctx.tree.wait_switch(TITLE, shared)
    ctx.tree.wait_text(SHARED if shared else LOCAL, timeout=10)


def wait_commands(ctx, count: int, timeout: float = 5.0) -> list:
    deadline = time.time() + timeout
    while time.time() < deadline and len(ctx.app.commands()) < count:
        time.sleep(0.2)
    return ctx.app.commands()


def case_a_local_by_default_and_not_now_changes_nothing(ctx):
    start(ctx, shared=False)
    ctx.shot("local")
    ctx.app.mark()
    ctx.tree.toggle(TITLE)
    ctx.tree.wait_text(QUESTION)
    ctx.tree.wait_text(BODY)
    ctx.shot("question")
    ctx.tree.click_in_dialog("Not now")
    ctx.tree.wait_switch(TITLE, False)
    ctx.tree.wait_text(LOCAL)
    time.sleep(1.5)
    assert ctx.app.commands() == [], ctx.app.commands()
    assert not os.path.exists(ctx.app.share_flag), "Not now shared the Bridge"
    assert not ctx.tree.dialogs_open(), "the question is still open"


def case_b_share_runs_pkexec_once_and_names_the_address(ctx):
    start(ctx, shared=False)
    ctx.app.mark()
    ctx.tree.toggle(TITLE)
    ctx.tree.wait_text(QUESTION)
    ctx.tree.click_in_dialog("Share")
    assert wait_commands(ctx, 1) == [ON], ctx.app.commands()
    ctx.tree.wait_text(SHARED, timeout=10)
    ctx.tree.wait_switch(TITLE, True)
    assert os.path.exists(ctx.app.share_flag), "the flag was not written"
    ctx.shot("shared")
    time.sleep(1.5)
    assert ctx.app.commands() == [ON], f"more than the one command: {ctx.app.commands()}"


def case_c_off_asks_nothing_and_goes_back_to_local(ctx):
    start(ctx, shared=True)
    ctx.app.mark()
    ctx.tree.toggle(TITLE)
    assert wait_commands(ctx, 1) == [OFF], ctx.app.commands()
    ctx.tree.wait_text(LOCAL, timeout=10)
    ctx.tree.wait_switch(TITLE, False)
    assert not ctx.tree.dialogs_open(), "switching off asked a question"
    assert not os.path.exists(ctx.app.share_flag), "the flag is still there"
    time.sleep(1.5)
    assert ctx.app.commands() == [OFF], f"more than the one command: {ctx.app.commands()}"


def case_d_the_switch_follows_the_flag_not_itself(ctx):
    # meshsat-share run from a terminal, or a change the app did not see: the next poll shows it.
    start(ctx, shared=False)
    ctx.app.mark()
    open(ctx.app.share_flag, "w", encoding="utf-8").close()
    ctx.app.refresh()
    ctx.tree.wait_switch(TITLE, True)
    ctx.tree.wait_text(SHARED, timeout=10)
    os.remove(ctx.app.share_flag)
    ctx.app.refresh()
    ctx.tree.wait_switch(TITLE, False)
    ctx.tree.wait_text(LOCAL, timeout=10)
    assert ctx.app.commands() == [], ctx.app.commands()
    ctx.app.open("home")
