# SPDX-License-Identifier: GPL-3.0-or-later
"""People (PeersScreen.kt, NodeDetailSheet.kt): your own node is in the table as "(you)" with
"-" for signal and last heard; a node heard directly shows its SNR, one heard through others its
hops; the empty texts only with no node at all; the sheet says how a node was heard."""
import time

SCENARIO = "mesh-only"
ME, OTHER = "!52cb81e7", "!a1b3c2ec"


def stamp(seconds_ago: float = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.123456789Z", time.gmtime(time.time() - seconds_ago))


def packets(*rows) -> dict:
    return {"packets": [{"time": stamp(ago), "bearer": "lora", "dir": "rx", "iface": "mesh_0", "from": OTHER, "to": "broadcast", "bytes": 40, "rssi": rssi, "snr": snr,
                         "hops": hops, "hop_start": hop_start, "channel": 0, "portnum": 1, "portnum_name": "TEXT_MESSAGE_APP", "text": "", "raw": "", "path": "", "msg_ref": ""}
                        for ago, snr, rssi, hops, hop_start in rows]}


def people(ctx, scenario: str = "mesh-only") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("people")
    ctx.app.refresh()


def case_your_node_is_in_the_table(ctx):
    people(ctx)
    ctx.tree.wait_text("meshsat-pinephone-pro (you)", timeout=10)
    ctx.tree.wait_text("1 node heard, 1 in the last 15 min")
    ctx.tree.find("button", contains="meshsat-pinephone-pro (you)")
    # The other node, heard directly as the node list says (SNR 8.5, no hop count)
    ctx.tree.find("button", contains="MSPA")
    assert ctx.tree.has_text("8.5 dB")
    ctx.shot("people")
    ctx.tree.click_containing("meshsat-pinephone-pro (you)")
    ctx.tree.wait_text("meshsat-pinephone-pro (your node)", timeout=10)
    names = [n.name for n in ctx.tree.dialog()]
    assert "Message" not in names, "your own node's sheet offers Message"
    ctx.app.action("close-dialog", "")
    # Only your own node: the table, not the empty texts
    people(ctx, "one-node")
    ctx.tree.wait_text("0 nodes heard, 0 in the last 15 min", timeout=10)
    ctx.tree.wait_text("meshsat-pinephone-pro (you)")
    assert not ctx.tree.has_text("Your node is listening."), "the empty text shows beside your own node"


def case_no_node_at_all_says_so(ctx):
    people(ctx)
    ctx.bridge.set("GET /api/nodes", {"nodes": []})
    ctx.app.refresh()
    ctx.tree.wait_text("Your node is listening.", timeout=10)
    ctx.tree.wait_text("People appear here as soon as they transmit on the mesh.")
    assert not ctx.tree.find_all("button", name="Connect your node")
    ctx.bridge.set("GET /api/status", {"connected": False, "node_id": "", "node_name": "", "address": "tcp://127.0.0.1:4403", "transport": "tcp"})
    ctx.app.refresh()
    ctx.tree.wait_text("Nobody heard yet.", timeout=10)
    ctx.tree.wait_text("People appear here when your MeshSat node hears them on the mesh.")
    ctx.tree.find("button", name="Connect your node")
    ctx.shot("people-empty")  # Android's capture state: the block centred under the cards


def case_the_signal_says_how_the_node_was_heard(ctx):
    people(ctx)
    ctx.bridge.set("GET /api/packets?limit=200", packets((30, 2.0, -110, 2, 3)))
    ctx.app.refresh()
    ctx.tree.wait_text("2 hops", timeout=10)
    ctx.tree.click_containing("MSPA")
    ctx.tree.wait_text("Heard through other nodes, 2 hops away.", timeout=10)
    ctx.app.action("close-dialog", "")
    ctx.bridge.set("GET /api/packets?limit=200", packets((60, 2.0, -110, 2, 3), (5, 6.46, -71, 0, 3)))
    ctx.app.refresh()
    ctx.tree.wait_text("6.5 dB", timeout=10)
    ctx.tree.click_containing("MSPA")
    ctx.tree.wait_text("Heard directly. SNR 6.5 dB, RSSI -71 dBm.", timeout=10)
    ctx.app.action("close-dialog", "")
    # A packet without a hop count says nothing about the path: the node list's word stands
    ctx.bridge.set("GET /api/packets?limit=200", packets((5, 1.0, -90, 0, 0)))
    ctx.app.refresh()
    ctx.tree.wait_text("8.5 dB", timeout=10)
    ctx.tree.click_containing("MSPA")
    ctx.tree.wait_text("Heard directly. SNR 8.5 dB, as your node last measured it.", timeout=10)
    ctx.app.action("close-dialog", "")
