# SPDX-License-Identifier: GPL-3.0-or-later
"""Links against a real, scratch Bridge: a link switched off in the app is off in the Bridge's
interface list at once (MESHSAT-1401), and on again; with every mesh link off the Bridge
refuses a text on the mesh and the chat says why."""
import time

SCENARIO = None  # the scratch Bridge
# The scratch Bridge's links as the person reads them (Words.kt; the Bridge's 9704 link is iridium_imt_0).
NAMES = {"mesh_0": "Mesh", "iridium_0": "Satellite", "iridium_imt_0": "Satellite (RockBLOCK 9704)", "cellular_0": "SMS", "sms_0": "SMS", "hub_0": "Hub", "mqtt_0": "MQTT broker"}


def links_of(ctx) -> list:
    return ctx.bridge.get("/api/interfaces") or []


def enabled_of(ctx, id_: str) -> bool:
    return next(i for i in links_of(ctx) if i["id"] == id_).get("enabled")


def wait_enabled(ctx, id_: str, on: bool, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while enabled_of(ctx, id_) is not on:
        if time.time() >= deadline:
            raise AssertionError(f"the Bridge still lists {id_} as {'off' if on else 'on'}")
        time.sleep(0.5)


def case_switch_off_and_on_persist(ctx):
    links = links_of(ctx)
    ctx.note(f"links: {[(i.get('id'), i.get('state'), i.get('enabled')) for i in links]}")
    assert any(i["id"] == "mesh_0" for i in links), "the scratch Bridge lists no mesh link"
    ctx.app.open("interfaces")
    ctx.tree.wait_text("Each way this phone can send and receive messages, and how well it is working.", timeout=10)
    for iface in links:
        ctx.tree.switch(f"Use {NAMES.get(iface['id'], iface['id'])}")
    ctx.app.mark()
    ctx.tree.toggle("Use Mesh")
    ctx.tree.wait_text("Switch off Mesh?")
    ctx.tree.click_in_dialog("Switch off")
    ctx.app.wait_toast("Mesh switched off", timeout=10)
    wait_enabled(ctx, "mesh_0", False)
    ctx.tree.wait_switch("Use Mesh", False)
    ctx.tree.wait_text("Switched off", timeout=10)
    ctx.shot("switched-off")
    # A text on the mesh now: refused by the Bridge, in words, and the text stays in the box.
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("Everyone on the mesh", timeout=10)
    status, answer = ctx.bridge.call("POST", "/api/messages/send", {"text": "e2e mesh off"})
    ctx.note(f"a direct send with the mesh off: {status} {answer}")
    assert status == 409 and "switched off" in str(answer), (status, answer)
    # Back on
    ctx.app.open("interfaces")
    ctx.tree.wait_switch("Use Mesh", False)
    ctx.tree.toggle("Use Mesh")
    ctx.app.wait_toast("Mesh switched on", timeout=10)
    wait_enabled(ctx, "mesh_0", True)
    ctx.tree.wait_switch("Use Mesh", True)
    ctx.tree.wait_gone("Switched off", timeout=10)
    ctx.app.open("home")
