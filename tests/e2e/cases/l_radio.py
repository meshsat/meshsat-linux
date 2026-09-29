# SPDX-License-Identifier: GPL-3.0-or-later
"""The radio settings live, on a T-Deck adopted over Bluetooth by a scratch Bridge (the phone's
own node and the live Bridge are never touched): the hop limit set in the app reaches the node,
whose own answer the Bridge reads back; the laptop then reads it over USB and puts it back
(tools/e2e-farend.py config). The node's log streams while its debug-log switch is on, and the
switch is turned off again before the case ends. Only harmless keys, each put back."""
import time

from driver import BenchError

BLE_NODE = "E0:72:A1:B3:C2:ED"  # T-Deck A (MSPA_c2ec), bonded with the phone
HARDWARE = {"node": "bluetooth", "why": "a T-Deck adopted over Bluetooth for the live radio case", "model": "PinePhone Pro"}
POLL = 2.0
HOPS = 4  # the node's own is 3; the laptop puts it back after the run


def named(ctx) -> dict:
    status, body = ctx.bridge.call("GET", "/api/config?format=names")
    return body if status == 200 and isinstance(body, dict) else {}


def wait_node(ctx, timeout: float = 150.0) -> dict:
    """The scratch Bridge up on the T-Deck: the link ready and the node's settings in."""
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        _s, ble = ctx.bridge.call("GET", "/api/mesh/ble/status")
        last = named(ctx)
        if (ble or {}).get("connected") and last.get("loaded") and (last.get("config") or {}).get("lora") and (last.get("config") or {}).get("security"):
            return last
        time.sleep(3)
    raise BenchError(f"the T-Deck never came up over Bluetooth on the scratch Bridge: ble {ble}, loaded {last.get('loaded')}; {ctx.bridge.log_tail()}")


def case_a_hop_limit_set_in_the_app_reaches_the_tdeck(ctx):
    settings = wait_node(ctx)
    lora = settings["config"]["lora"]
    ctx.note(f"T-Deck {settings.get('node_id')} firmware {settings.get('firmware_version')}: region {lora.get('region')}, hops {lora.get('hop_limit')}, "
             f"channels {[(c['index'], c['name'], c['key']) for c in settings.get('channels', []) if c.get('role')]}")
    assert settings.get("node_id") == "!a1b3c2ec", settings.get("node_id")
    region = lora.get("region")
    ctx.app.open("radio-config")
    ctx.tree.wait_text("!a1b3c2ec", timeout=20)
    ctx.tree.click("Radio")
    ctx.tree.wait_text("Hops", timeout=10)
    ctx.shot("radio-live")
    ctx.app.mark()
    ctx.tree.set_text("Hops", str(HOPS))
    ctx.tree.click("Apply")
    ctx.app.wait_toast("Sent to the radio. It switches over in a few seconds; older firmware restarts to do it.", timeout=10)
    # The node's own answer: the page asks for the section again 2.5 s later; its reply replaces the Bridge's copy.
    deadline = time.time() + 30
    lora = {}
    while time.time() < deadline:
        lora = (named(ctx).get("config") or {}).get("lora") or {}
        if lora.get("hop_limit") == HOPS:
            break
        time.sleep(1)
    assert lora.get("hop_limit") == HOPS, f"the node holds hop_limit {lora.get('hop_limit')}"
    assert lora.get("region") == region, f"the region changed from {region} to {lora.get('region')}"
    ctx.tree.wait_text("Hops", timeout=5)
    ctx.note(f"hop_limit {HOPS} set in the app and held by the node (read back through the Bridge); region still {region}")
    ctx.app.open("home")


def case_b_the_tdecks_log_streams_while_its_switch_is_on(ctx):
    wait_node(ctx)
    ctx.app.open("nodelog")
    ctx.tree.wait_text("Sets the node's debug log over Bluetooth", timeout=20)
    ctx.app.mark()
    ctx.tree.toggle("Stream the node's log")
    ctx.tree.wait_text("The node sends every log line while this switch is on", timeout=10)
    # A security set makes the node restart once; the Bridge takes the link up again by itself.
    ctx.note("debug log on: the T-Deck restarts, the link comes back")
    time.sleep(8)
    wait_node(ctx, timeout=180)
    deadline = time.time() + 120
    lines = []
    while time.time() < deadline:
        _s, log = ctx.bridge.call("GET", "/api/mesh/radio-log?after=0")
        lines = [l for l in (log or {}).get("lines") or [] if l.get("level") != "CONSOLE"]
        if lines:
            break
        time.sleep(2)
    ctx.note(f"{len(lines)} lines from the node; following: {(log or {}).get('following')}, available: {(log or {}).get('available')}")
    assert lines, f"no line of the node's log arrived; {ctx.bridge.log_tail()}"
    ctx.tree.wait_text(lines[-1]["message"][:40], timeout=20)
    ctx.shot("nodelog-live")
    ctx.tree.toggle("Stream the node's log")
    ctx.tree.wait_text("Sets the node's debug log over Bluetooth", timeout=10)
    time.sleep(8)
    settings = wait_node(ctx, timeout=180)
    assert settings["config"]["security"].get("debug_log_api_enabled") is False, settings["config"]["security"]
    ctx.note("debug log off again")
    ctx.app.open("home")
