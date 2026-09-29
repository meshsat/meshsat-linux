# SPDX-License-Identifier: GPL-3.0-or-later
"""The Map tab (MapScreen.kt, MapTracks.kt) and People's node sheet (NodeDetailSheet.kt) against
the scripted Bridge: the markers newest first with the stale ones faded, a track per node from
the positions of the last 24 hours (the row older than a day left out, an APRS station the
position log alone knows included), the "Layers and nodes" panel in Android's words, a node
hidden with its track, the layers off and on, a node row and "Show everyone" moving the camera,
the sheet's rows and its "Show on map" (disabled for a node that never sent a position), and the
bubbles on a marker and on a track."""
import time

SCENARIO = "zones"
ENV = {"MESHSAT_APP_OSM_URL": "{bridge}/tiles/{z}/{x}/{y}.png"}
OTHER, THIRD, APRS = "!a1b3c2ec", "!b1b3c2ed", "PA3XYZ-9"
HOME = (52.3731, 4.8932)
STATION = (52.0907, 5.1214)


def on_map(ctx, fresh: bool = False) -> None:
    """The Map tab; `fresh`: the scenario loaded again first, so "2 min ago" holds (its ages are
    counted from when it is loaded)."""
    if fresh:
        ctx.bridge.scenario("zones")
        ctx.app.refresh()
    ctx.app.tab("map")
    ctx.tree.wait_text("Layers and nodes", timeout=10)
    ctx.tree.wait_text("3 of 3 nodes shown", timeout=10)  # the APRS station comes with the positions


def open_panel(ctx) -> None:
    if ctx.tree.find_all("button", name="Open layers and nodes"):
        ctx.tree.click("Open layers and nodes")
    ctx.tree.find("button", name="Close layers and nodes")


def near(a: float, b: float, tolerance: float = 0.001) -> bool:
    return abs(a - b) < tolerance


def case_a_the_map_and_its_panel(ctx):
    on_map(ctx)
    for button in ("Centre on me", "Show everyone on the map", "Zoom in", "Zoom out", "Open layers and nodes"):
        ctx.tree.find("button", name=button)
    facts = ctx.app.wait_map(lambda f: len(f["tracks"]) == 3, what="three tracks")
    assert facts["nodes"] == ["MSPA", APRS, "Far Hill"] and facts["stale"] == [APRS, "Far Hill"], facts
    assert facts["tracks"] == {OTHER: 4, THIRD: 3, APRS: 2}, facts["tracks"]
    assert facts["track_titles"] == {OTHER: "Track of MSPA", THIRD: "Track of Far Hill", APRS: f"Track of {APRS}"}, facts["track_titles"]
    assert facts["phone"] is None and facts["note"] == "© OpenStreetMap contributors", facts
    ctx.shot("map")
    open_panel(ctx)
    for words in ("Layers", "Nodes", "Heard 2 min ago", "Last heard 20 min ago", "Last heard 30 min ago"):
        ctx.tree.wait_text(words)
    for layer in ("This phone", "Nodes", "Tracks from the last 24 hours", "Show MSPA on the map", f"Show {APRS} on the map", "Show Far Hill on the map"):
        assert ctx.tree.switch(layer).checked, layer
    for button in ("Show all", "Hide all", "Centre the map on MSPA", f"Centre the map on {APRS}", "Centre the map on Far Hill"):
        ctx.tree.find("button", name=button)
    assert not ctx.tree.has_text("Nodes appear here when they send a position.")
    ctx.shot("panel")


def case_b_a_hidden_node_loses_marker_and_track(ctx):
    on_map(ctx)
    open_panel(ctx)
    ctx.tree.toggle("Show MSPA on the map")
    ctx.tree.wait_text("2 of 3 nodes shown")
    facts = ctx.app.wait_map(lambda f: "MSPA" not in f["nodes"], what="MSPA hidden")
    assert OTHER not in facts["tracks"] and set(facts["tracks"]) == {THIRD, APRS}, facts["tracks"]
    ctx.tree.click("Show all")
    ctx.tree.wait_text("3 of 3 nodes shown")
    ctx.app.wait_map(lambda f: len(f["nodes"]) == 3 and len(f["tracks"]) == 3, what="everyone back")
    assert ctx.tree.switch("Show MSPA on the map").checked
    ctx.tree.click("Hide all")
    ctx.tree.wait_text("0 of 3 nodes shown")
    ctx.app.wait_map(lambda f: f["nodes"] == [] and f["tracks"] == {}, what="nobody")
    ctx.tree.click("Show all")
    ctx.tree.wait_text("3 of 3 nodes shown")


def case_c_layers_off_and_on(ctx):
    on_map(ctx)
    open_panel(ctx)
    ctx.tree.toggle("Tracks from the last 24 hours")
    ctx.app.wait_map(lambda f: f["tracks"] == {} and len(f["nodes"]) == 3, what="no tracks, every node")
    ctx.tree.toggle("Tracks from the last 24 hours")
    ctx.app.wait_map(lambda f: len(f["tracks"]) == 3, what="the tracks back")
    ctx.tree.toggle("Nodes")
    ctx.tree.wait_text("0 of 3 nodes shown")
    facts = ctx.app.wait_map(lambda f: f["nodes"] == [], what="no nodes")
    assert set(facts["tracks"]) == {OTHER, THIRD, APRS}, "the tracks go with the Tracks layer, not the Nodes layer"
    ctx.tree.toggle("Nodes")
    ctx.tree.wait_text("3 of 3 nodes shown")


def case_d_a_node_row_centres_the_map(ctx):
    on_map(ctx)
    open_panel(ctx)
    ctx.tree.click("Centre the map on Far Hill")
    ctx.app.wait_map(lambda f: near(f["centre"][0], STATION[0]) and near(f["centre"][1], STATION[1]) and f["zoom"] >= 14, what="Far Hill at zoom 14 or more")


def case_e_show_everyone(ctx):
    on_map(ctx)
    ctx.tree.click("Show everyone on the map")
    ctx.app.wait_map(lambda f: near(f["centre"][0], 52.2319) and near(f["centre"][1], 5.0073) and round(f["zoom"]) == 9, what="the box's middle at zoom 9")


def case_f_centre_on_me_without_a_position(ctx):
    on_map(ctx)
    ctx.app.mark()
    ctx.tree.click("Centre on me")
    ctx.app.wait_toast("Your position is not known yet.")


def case_g_the_node_sheet_and_show_on_map(ctx):
    on_map(ctx, fresh=True)
    ctx.tree.click("Show everyone on the map")
    ctx.app.wait_map(lambda f: round(f["zoom"]) == 9, what="zoom 9")
    ctx.app.tab("people")
    ctx.tree.click_containing("MSPA", timeout=10)
    names = [n.name for n in ctx.tree.dialog()]
    for words in ("MSPA", "MSPA  !a1b3c2ec", "Last heard", "2 min ago", "Battery", "78%", "Signal", "Heard directly. SNR 8.5 dB, as your node last measured it.",
                  "Hardware", "LilyGO T-Deck", "Position", "52.37310, 4.89320, 2 min ago", "Message", "Show on map"):
        assert words in names, (words, names)
    ctx.shot("sheet")
    ctx.tree.click_in_dialog("Show on map")
    ctx.tree.wait_text("Layers and nodes", timeout=10)
    ctx.app.wait_map(lambda f: near(f["centre"][0], HOME[0]) and near(f["centre"][1], HOME[1]) and round(f["zoom"]) == 14, what="MSPA at zoom 14")


def case_h_no_position_no_show_on_map(ctx):
    ctx.bridge.scenario("zones")
    ctx.app.refresh()
    ctx.app.tab("people")
    ctx.tree.click_containing("Quiet One", timeout=10)
    names = [n.name for n in ctx.tree.dialog()]
    for words in ("Quiet One", "Not reported", "Not shared yet. It appears once the node sends its position."):
        assert words in names, (words, names)
    show = [n for n in ctx.tree.dialog() if n.role == "button" and n.name == "Show on map"]
    assert show and not show[0].sensitive, "Show on map offered for a node with no position"
    ctx.app.action("close-dialog", "")
    deadline = time.time() + 5
    while ctx.tree.dialogs_open() and time.time() < deadline:
        time.sleep(0.2)
    assert not ctx.tree.dialogs_open()


def case_i_bubbles_on_a_marker_and_a_track(ctx):
    on_map(ctx, fresh=True)
    open_panel(ctx)
    ctx.tree.click("Centre the map on MSPA")
    ctx.app.wait_map(lambda f: near(f["centre"][0], HOME[0]) and f["zoom"] >= 14, what="MSPA in the middle")
    time.sleep(1)
    ctx.app.mark()
    ctx.app.press("tap", *HOME)
    deadline = time.time() + 5
    while not ctx.app.bubbles() and time.time() < deadline:
        time.sleep(0.2)
    assert ctx.app.bubbles() == [("MSPA", "Heard 2 min ago, altitude 12 m")], ctx.app.bubbles()
    time.sleep(1)  # the bubble's first frame
    ctx.shot("marker-bubble")
    ctx.app.mark()
    ctx.app.press("tap", 52.3675, 4.8875)  # between two of MSPA's fixes, clear of its diamond
    deadline = time.time() + 5
    while not ctx.app.bubbles() and time.time() < deadline:
        time.sleep(0.2)
    assert ctx.app.bubbles() == [("Track of MSPA", "")], ctx.app.bubbles()
