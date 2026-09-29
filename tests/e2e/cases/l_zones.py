# SPDX-License-Identifier: GPL-3.0-or-later
"""Zones against the live Bridge (MESHSAT-1414: the geofence monitor the Bridge now creates): a
zone placed on the Zones map (the app's test press: no finger reaches a headless session) and
saved reaches the Bridge as Android's 32-vertex circle, shows in the list with its measured
radius, and goes through the app's own delete dialog. The zone is named e2e-..., lies far out
at sea where no node crosses it, and any e2e zone left over is removed at the end whatever
happened. The Bridge's crossings answer in their shape."""
import time
import urllib.parse

SCENARIO = None  # the live Bridge
SEA = (54.0, 3.0)  # the North Sea


def remove_leftovers(ctx) -> None:
    for zone in ctx.bridge.get("/api/geofences") or []:
        if str(zone.get("name", "")).startswith("e2e-"):
            ctx.bridge.call("DELETE", "/api/geofences/" + urllib.parse.quote(str(zone.get("id", "")), safe=""))


def case_a_zone_saved_and_deleted_on_the_live_bridge(ctx):
    name = f"e2e-zone {time.strftime('%H%M%S')}"
    try:
        ctx.app.open("geofence")
        ctx.tree.find("button", name="Add zone", timeout=20)
        ctx.app.press("long", *SEA)
        ctx.tree.wait_text("New zone")
        ctx.tree.set_text("Name", name)
        ctx.tree.set_text("Radius in metres", "300")
        ctx.tree.wait_text("About 600 m across.")
        ctx.app.mark()
        ctx.tree.click("Save zone")
        ctx.app.wait_toast(f"Zone added: {name}", timeout=10)
        mine = [z for z in ctx.bridge.get("/api/geofences") if z.get("name") == name]
        assert len(mine) == 1 and len(mine[0]["polygon"]) == 32 and mine[0]["alert_on"] == "enter" and mine[0]["id"].startswith("zone_"), mine
        ctx.tree.wait_text("Alerts when a node enters. Radius about 301 m.", timeout=10)
        ctx.shot("live-zone")
        ctx.tree.click(f"Delete zone {name}")
        ctx.tree.click_in_dialog("Delete zone")
        deadline = time.time() + 10
        while any(z.get("name") == name for z in ctx.bridge.get("/api/geofences")) and time.time() < deadline:
            time.sleep(0.5)
        assert not any(z.get("name") == name for z in ctx.bridge.get("/api/geofences")), "the zone is still in the Bridge"
        events = ctx.bridge.get("/api/geofences/events")
        assert isinstance(events, dict) and isinstance(events.get("events"), list), events
        ctx.note(f"live zone {mine[0]['id']} saved and deleted; the Bridge holds {len(events['events'])} crossings")
    finally:
        remove_leftovers(ctx)
