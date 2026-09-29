# SPDX-License-Identifier: GPL-3.0-or-later
"""This phone on both maps, its position given to the app (MESHSAT_APP_POSITION, as a fix from
the phone would give it): the orange dot and the panel's row on the Map tab, "Centre on me",
the phone's bubble; on Zones, "Add zone" starting the zone at the phone at the zoom for its
radius, and the first view going to the phone when there is no zone."""
import time

SCENARIO = "zones"
PHONE = (52.0907, 5.1214)
ENV = {"MESHSAT_APP_OSM_URL": "{bridge}/tiles/{z}/{x}/{y}.png", "MESHSAT_APP_POSITION": f"{PHONE[0]},{PHONE[1]}"}


def near(a: float, b: float, tolerance: float = 0.001) -> bool:
    return abs(a - b) < tolerance


def case_a_this_phone_on_the_map(ctx):
    ctx.app.tab("map")
    ctx.tree.wait_text("Layers and nodes", timeout=10)
    facts = ctx.app.wait_map(lambda f: f["phone"] is not None, what="this phone")
    assert near(facts["phone"][0], PHONE[0]) and near(facts["phone"][1], PHONE[1]) and facts["accuracy"] is None, facts
    ctx.tree.click("Open layers and nodes")
    ctx.tree.wait_text("52.09070, 5.12140, accuracy unknown")
    ctx.tree.click("Show everyone on the map")
    ctx.app.wait_map(lambda f: round(f["zoom"]) == 9, what="everyone in view")
    ctx.tree.click("Centre on me")
    ctx.app.wait_map(lambda f: near(f["centre"][0], PHONE[0]) and near(f["centre"][1], PHONE[1]) and round(f["zoom"]) == 15, what="the phone at zoom 15")
    time.sleep(1)
    ctx.app.mark()
    ctx.app.press("tap", *PHONE)  # the dot is drawn over Far Hill's diamond, and answers first
    deadline = time.time() + 5
    while not ctx.app.bubbles() and time.time() < deadline:
        time.sleep(0.2)
    assert ctx.app.bubbles() == [("This phone", "Accuracy unknown")], ctx.app.bubbles()
    ctx.tree.toggle("This phone")
    ctx.app.wait_map(lambda f: f["phone"] is None, what="the phone layer off")
    ctx.tree.toggle("This phone")
    ctx.app.wait_map(lambda f: f["phone"] is not None, what="the phone layer on")
    ctx.shot("phone")


def case_b_add_zone_starts_at_the_phone(ctx):
    ctx.app.open("geofence")
    ctx.tree.click("Add zone", timeout=10)
    ctx.tree.wait_text("The orange circle is the zone. Long-press the map to move it.")
    ctx.app.wait_map(lambda f: f["draft"] and near(f["draft"][0], PHONE[0]) and near(f["draft"][1], PHONE[1]) and f["draft"][2] == 200 and round(f["zoom"]) == 16,
                     what="the draft at the phone, zoom 16")
    ctx.tree.click("Cancel")
    ctx.tree.find("button", name="Add zone")


def case_c_first_view_without_zones_is_the_phone(ctx):
    ctx.bridge.scenario("mesh-only")
    ctx.app.open("geofence")
    ctx.tree.find("button", name="Add zone", timeout=10)
    ctx.tree.wait_text("No zones yet.")
    ctx.app.wait_map(lambda f: near(f["centre"][0], PHONE[0]) and near(f["centre"][1], PHONE[1]) and round(f["zoom"]) == 15, what="the phone at zoom 15")
    ctx.bridge.scenario("zones")
