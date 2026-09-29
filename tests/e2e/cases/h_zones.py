# SPDX-License-Identifier: GPL-3.0-or-later
"""Zones (GeofenceScreen.kt) against the scripted Bridge, which holds the zones and checks every
position as the Bridge's monitor does (MESHSAT-1414): the list and the alerts in Android's words,
a zone placed by a long press and saved as Android's 32-vertex circle, the three errors at once,
the slider and the field in step, the delete dialog, a node crossing a zone listed within the
5 s refresh, the screen without the service, and the bubbles. The map's tiles come from the
scripted Bridge, never from OpenStreetMap."""
import time

SCENARIO = "zones"
ENV = {"MESHSAT_APP_OSM_URL": "{bridge}/tiles/{z}/{x}/{y}.png"}
OTHER = "!a1b3c2ec"
HOME = (52.3731, 4.8932)
STATION = (52.0907, 5.1214)
EXPLAINER = ("When a mesh node reports a position that crosses a zone's edge, the alert is listed here. It does not send a message or a "
             "notification, and zones are kept only until the MeshSat service restarts.")


def start(ctx, scenario: str = "zones") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("geofence")
    ctx.tree.wait_text(EXPLAINER, timeout=10)


def case_a_the_list_in_androids_words(ctx):
    start(ctx)
    ctx.tree.find("button", name="Add zone", timeout=10)
    for words in ("Home", "Alerts when a node enters. Radius about 200 m.", "Station", "Alerts when a node enters or leaves. Radius about 1 km.", "Pick-up point",
                  "Recent alerts", "MSPA entered Home, 4 min ago", "!0badf00d left Station, 2 h ago"):
        ctx.tree.wait_text(words)
    for button in ("Show Home on the map", "Delete zone Home", "Show Station on the map", "Delete zone Station", "Centre on me", "Zoom in", "Zoom out"):
        ctx.tree.find("button", name=button)
    # The first view: every zone vertex in view, at the zoom for their span (0.29 degrees: 9).
    facts = ctx.app.wait_map(lambda f: f["zones"] == ["Home", "Station"] and f["zoom"] == 9, what="both zones at zoom 9")
    assert abs(facts["centre"][0] - 52.2283) < 0.001 and abs(facts["centre"][1] - 5.0131) < 0.001, facts["centre"]
    assert facts["hint"] == "Long-press the map to place a zone.", facts["hint"]
    assert facts["nodes"] == ["MSPA", "Far Hill"] and facts["stale"] == ["Far Hill"], facts
    ctx.shot("zones")


def case_b_a_long_press_places_a_zone_and_save_sends_it(ctx):
    start(ctx)
    ctx.tree.find("button", name="Add zone", timeout=10)
    before = ctx.bridge.count()
    ctx.app.press("long", 52.1, 5.0)
    ctx.tree.wait_text("New zone")
    ctx.tree.wait_text("The orange circle is the zone. Long-press the map to move it.")
    facts = ctx.app.wait_map(lambda f: f["draft"] is not None, what="the orange circle")
    assert abs(facts["draft"][0] - 52.1) < 1e-6 and abs(facts["draft"][1] - 5.0) < 1e-6 and facts["draft"][2] == 200, facts["draft"]
    assert facts["hint"] == "Long-press the map to move the zone.", facts["hint"]
    ctx.tree.set_text("Name", "e2e Gate")
    ctx.tree.set_text("Radius in metres", "500")
    ctx.tree.wait_text("About 1 km across.")
    ctx.app.wait_map(lambda f: f["draft"] and f["draft"][2] == 500, what="the circle at 500 m")
    ctx.tree.click("Leaves the zone")
    ctx.app.mark()
    ctx.tree.click("Save zone")
    ctx.app.wait_toast("Zone added: e2e Gate")
    sent = ctx.bridge.wait_request("POST", "/api/geofences", since=before)["body"]
    assert sent["name"] == "e2e Gate" and sent["alert_on"] == "exit" and sent["message"] == "" and sent["id"].startswith("zone_"), sent
    assert len(sent["polygon"]) == 32 and list(sent) == ["id", "name", "polygon", "alert_on", "message"], sent
    north = sent["polygon"][0]  # due north of where the finger was (to a millionth of a degree: the press goes through the screen)
    assert abs(north["lat"] - (52.1 + 500 / 6371000 * 57.29577951308232)) < 1e-6 and abs(north["lon"] - 5.0) < 1e-6, north
    ctx.tree.wait_text("Alerts when a node leaves. Radius about 501 m.", timeout=8)
    ctx.tree.find("button", name="Add zone")
    ctx.app.wait_map(lambda f: "e2e Gate" in f["zones"] and f["draft"] is None, what="the saved zone in amber and no draft")
    ctx.shot("saved")


def case_c_save_shows_every_error_at_once(ctx):
    start(ctx)
    before = ctx.bridge.count()
    ctx.tree.click("Add zone", timeout=10)
    ctx.tree.wait_text("New zone")
    ctx.tree.wait_text("Long-press the map where the zone should be.")  # no position known: no centre
    ctx.tree.click("Save zone")
    ctx.tree.wait_text("Give the zone a name.")
    ctx.tree.set_text("Radius in metres", "5")
    ctx.tree.set_text("Name", "e2e Nowhere")
    ctx.tree.wait_gone("Give the zone a name.")
    ctx.tree.click("Save zone")
    ctx.tree.wait_text("Use a radius between 10 m and 50 km.")
    assert not [r for r in ctx.bridge.requests(before) if r["method"] == "POST" and r["path"] == "/api/geofences"], "saved with errors"
    ctx.shot("errors")
    ctx.tree.click("Cancel")
    ctx.tree.find("button", name="Add zone")
    assert ctx.app.map_facts()["draft"] is None


def case_d_the_slider_and_the_field_agree(ctx):
    start(ctx)
    ctx.tree.click("Add zone", timeout=10)
    ctx.tree.wait_text("New zone")
    assert ctx.tree.entry_text("Radius in metres") == "200"
    slider = ctx.tree.find("slider", name="Radius")
    assert abs(slider.value() - 0.30103) < 0.001, slider.value()
    slider.set_value(0.5)
    deadline = time.time() + 5
    while ctx.tree.entry_text("Radius in metres") != "500" and time.time() < deadline:
        time.sleep(0.2)
    assert ctx.tree.entry_text("Radius in metres") == "500"
    ctx.tree.wait_text("About 1 km across.")
    ctx.tree.set_text("Radius in metres", "20000")
    ctx.tree.wait_text("About 40 km across.")
    assert abs(ctx.tree.find("slider", name="Radius").value() - 1.0) < 0.001  # past 5 km the thumb sits at the end
    ctx.tree.set_text("Radius in metres", "12a3")
    deadline = time.time() + 5
    while ctx.tree.entry_text("Radius in metres") != "123" and time.time() < deadline:
        time.sleep(0.2)
    assert ctx.tree.entry_text("Radius in metres") == "123", "only digits are kept"
    ctx.tree.click("Cancel")


def case_e_delete_asks_first(ctx):
    start(ctx)
    ctx.tree.wait_text("Alerts when a node enters. Radius about 200 m.", timeout=10)
    before = ctx.bridge.count()
    ctx.tree.click("Delete zone Home")
    names = [n.name for n in ctx.tree.dialog()]
    assert "Delete Home?" in names and "MeshSat stops watching this zone. Alerts it already raised stay in the list." in names, names
    ctx.tree.click_in_dialog("Keep it")
    time.sleep(1)
    assert not [r for r in ctx.bridge.requests(before) if r["method"] == "DELETE"], "deleted without the answer"
    ctx.tree.click("Delete zone Home")
    ctx.tree.click_in_dialog("Delete zone")
    ctx.bridge.wait_request("DELETE", "/api/geofences/zone_1", since=before)
    ctx.tree.wait_gone("Alerts when a node enters. Radius about 200 m.", timeout=8)
    ctx.tree.wait_text("MSPA entered Home, 4 min ago")  # the alerts it raised stay
    assert [z["name"] for z in ctx.bridge.state()["zones"]] == ["Station"]


def case_f_a_node_crossing_is_listed(ctx):
    start(ctx)
    ctx.tree.wait_text("Station", timeout=10)
    assert ctx.bridge.position(OTHER, *STATION) == [{"zone_name": "Station", "node_id": OTHER, "event": "enter", "timestamp": ctx.bridge.state()["zone_events"][0]["timestamp"]}]
    ctx.tree.wait_text("MSPA entered Station, just now", timeout=10)
    ctx.bridge.position(OTHER, 52.2, 5.3)
    ctx.tree.wait_text("MSPA left Station, just now", timeout=10)
    ctx.shot("alerts")


def case_g_without_the_service(ctx):
    start(ctx, "zones-down")
    ctx.tree.wait_text("Zones are not available until the MeshSat service is running.", timeout=10)
    assert not ctx.tree.find_all("button", name="Add zone"), "Add zone offered without the service"
    ctx.app.press("long", 52.1, 5.0)
    time.sleep(1.5)
    assert not ctx.tree.has_text("New zone"), "a long press placed a zone without the service"
    assert ctx.app.map_facts()["hint"] == ""
    ctx.shot("no-service")


def case_h_bubbles(ctx):
    start(ctx)
    ctx.tree.click("Show Home on the map", timeout=10)
    ctx.app.wait_map(lambda f: f["zoom"] == 15, what="Home at zoom 15")
    time.sleep(1)  # the camera's 600 ms move
    ctx.app.mark()
    ctx.app.press("tap", HOME[0] + 0.0010, HOME[1])  # inside Home, clear of MSPA's diamond at its centre
    deadline = time.time() + 5
    while not ctx.app.bubbles() and time.time() < deadline:
        time.sleep(0.2)
    assert ctx.app.bubbles() == [("Home", "Alerts when a node enters")], ctx.app.bubbles()
    ctx.app.mark()
    ctx.app.press("tap", *HOME)
    deadline = time.time() + 5
    while not ctx.app.bubbles() and time.time() < deadline:
        time.sleep(0.2)
    assert ctx.app.bubbles() == [("MSPA", "Heard 2 min ago")], ctx.app.bubbles()
    time.sleep(1)  # the bubble's first frame
    ctx.shot("bubble")


def served(facts: dict) -> int:
    return sum(facts.get("served", {}).values())


def case_i_the_first_view_draws_its_tiles(ctx):
    """libshumate holds tiles back while the view "moves fast", and reads the speed once per frame:
    the first view's jump (not animated, as Android's) must still end with the tiles asked for,
    with no finger on the map to make the next frame."""
    ctx.bridge.scenario("zones")
    ctx.app.tab("map")
    ctx.tree.wait_text("Layers and nodes", timeout=10)
    time.sleep(3)
    before = served(ctx.app.map_facts())
    ctx.app.open("geofence")
    ctx.app.wait_map(lambda f: f["zoom"] == 9 and f["zones"], what="the first view: both zones at zoom 9")
    facts = ctx.app.wait_map(lambda f: served(f) >= before + 4, timeout=8, what="the tiles of the first view asked for")
    ctx.note(f"tiles served: {before} before, {served(facts)} after the first view ({facts['served']})")
    time.sleep(1)
    ctx.shot("first-view-tiles")
