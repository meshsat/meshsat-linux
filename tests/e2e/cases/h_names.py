# SPDX-License-Identifier: GPL-3.0-or-later
"""Node names: kept once heard, "Node !id" until then (Peers.displayName)."""
SCENARIO = "mesh-only"


def case_a_name_heard_once_survives_a_bridge_restart(ctx):
    ctx.app.open("people")
    ctx.tree.wait_text("MSPA")
    # The Bridge restarts: its node table comes back without the name, and a new node appears.
    ctx.bridge.scenario("nameless-node")
    ctx.app.refresh()
    ctx.tree.wait_text("Node !b1b3c2ed", timeout=10)
    assert ctx.tree.has_text("MSPA"), "the name heard before the restart is gone"
    ctx.tree.wait_text("2 nodes heard")
    ctx.shot("people-after-restart")
    ctx.bridge.scenario("mesh-only")
    ctx.app.refresh()
    ctx.tree.wait_text("1 node heard", timeout=10)
