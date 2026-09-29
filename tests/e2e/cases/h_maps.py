# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Maps and the map offline (SettingsScreen.kt:1984-2223, MapTiles.kt, MapChrome.kt): the
card with only the world overview, a detailed map added from a file and put in use, a vector
file kept but never used, a file that is no map refused in Android's words, "Use my detailed
map" keeping its file, the map offline serving the detailed map (the tile server unreachable:
three failed downloads), the Map tab zooming out to 5 when offline with only the world overview,
and the delete dialog. The tiles come from the scripted Bridge, never from OpenStreetMap; the
maps live in the case's own data folder."""
import os
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fakebridge import solid_png  # noqa: E402

SCENARIO = "mesh-only"
ENV = {"MESHSAT_APP_OSM_URL": "{bridge}/tiles/{z}/{x}/{y}.png", "MESHSAT_APP_OFFLINE_RETRY": "3"}
INTRO = "The map downloads its detail from the internet. Without internet it shows what is installed here."
WORLD_TEXT = "Built in and always installed. Countries and coastlines at a zoomed-out scale, shown when there is no internet."
HINT = "Use an MBTiles file with PNG or JPEG tiles, for example one exported from OpenStreetMap for your area. Files with vector tiles cannot be shown."
ONLINE = "© OpenStreetMap contributors"


def mbtiles(name: str, fmt: str = "png", zooms=range(0, 4)) -> bytes:
    """An MBTiles file with every tile of these zooms in one colour."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "m.mbtiles")
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
        db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
        db.executemany("INSERT INTO metadata VALUES (?, ?)", [("name", name), ("format", fmt), ("minzoom", str(min(zooms))), ("maxzoom", str(max(zooms)))])
        tile = solid_png((70, 110, 170), 256) if fmt == "png" else b"\x1a\x00vector"
        for z in zooms:
            for x in range(1 << z):
                for y in range(1 << z):
                    db.execute("INSERT INTO tiles VALUES (?, ?, ?, ?)", (z, x, y, tile))
        db.commit()
        db.close()
        with open(path, "rb") as handle:
            return handle.read()


def open_maps(ctx) -> None:
    ctx.app.open("setup/maps")
    ctx.tree.wait_text(INTRO, timeout=10)


def zoom_to(ctx, level: float) -> dict:
    """Zoom in or out with the map's buttons until the map is at `level`."""
    for _ in range(20):
        facts = ctx.app.map_facts()
        if round(facts["zoom"]) == level:
            return facts
        ctx.tree.click("Zoom in" if facts["zoom"] < level else "Zoom out")
        time.sleep(0.8)
    return ctx.app.wait_map(lambda f: round(f["zoom"]) == level, what=f"zoom {level}")


def case_a_the_card_with_only_the_world(ctx):
    open_maps(ctx)
    for words in ("Offline maps", "Installed", "World overview", WORLD_TEXT, HINT):
        ctx.tree.wait_text(words)
    ctx.tree.find("button", name="Add a detailed map")
    assert not ctx.tree.switches("Use my detailed map"), "the switch shows with no detailed map"
    ctx.shot("world-only")


def case_b_a_map_added_is_in_use(ctx):
    open_maps(ctx)
    ctx.app.pick(mbtiles("e2e Utrecht"), name="utrecht.mbtiles")
    ctx.app.mark()
    ctx.tree.click("Add a detailed map")
    ctx.app.wait_toast("Map added: e2e Utrecht", timeout=15)
    ctx.tree.wait_text("In use")
    ctx.tree.wait_text(" MB, zoom 0 to 3")
    ctx.tree.find("button", name="Use e2e Utrecht")
    ctx.tree.find("button", name="Delete e2e Utrecht")
    ctx.tree.wait_switch("Use my detailed map", True)
    folder = os.path.join(ctx.app.work, "xdg", "data", "meshsat", "mbtiles")
    assert sorted(os.listdir(folder)) == ["utrecht.mbtiles"], os.listdir(folder)
    ctx.shot("added")


def case_c_vector_file_is_kept_but_not_used(ctx):
    open_maps(ctx)
    ctx.app.pick(mbtiles("e2e Zeeland", fmt="pbf", zooms=range(0, 2)), name="zeeland.mbtiles")
    ctx.app.mark()
    ctx.tree.click("Add a detailed map")
    ctx.app.wait_toast("Added, but this file has vector tiles, which the map cannot show.", timeout=15)
    ctx.tree.wait_text("Vector tiles: the map cannot show this file.")
    ctx.tree.wait_text("e2e Zeeland")
    assert not ctx.tree.find("button", name="Use e2e Zeeland").sensitive, "a vector map can be chosen"
    assert ctx.tree.count_text("In use") == 1  # Utrecht is still the one


def case_d_not_a_map_is_refused(ctx):
    open_maps(ctx)
    ctx.app.pick(b"this is not a database at all, " * 20, name="notes.mbtiles")
    ctx.app.mark()
    ctx.tree.click("Add a detailed map")
    toast = ctx.app.wait_toast("Could not add this map: Invalid MBTiles file: ", timeout=15)
    assert "not a database" in toast, toast
    folder = os.path.join(ctx.app.work, "xdg", "data", "meshsat", "mbtiles")
    assert sorted(os.listdir(folder)) == ["utrecht.mbtiles", "zeeland.mbtiles"], os.listdir(folder)


def case_e_the_switch_keeps_the_file(ctx):
    open_maps(ctx)
    ctx.tree.wait_switch("Use my detailed map", True)
    ctx.tree.toggle("Use my detailed map")
    ctx.tree.wait_switch("Use my detailed map", False)
    ctx.tree.wait_gone("In use")
    ctx.tree.toggle("Use my detailed map")
    ctx.tree.wait_switch("Use my detailed map", True)
    ctx.tree.wait_text("In use")


def case_f_offline_the_detailed_map_serves(ctx):
    # No node with a position: the map stays where it opens (zoom 3), where the file has tiles.
    # The Map tab is opened only once the app has polled the new scenario.
    ctx.bridge.scenario("one-node")
    ctx.app.refresh()
    ctx.app.tab("people")
    ctx.tree.wait_text("0 nodes heard, 0 in the last 15 min", timeout=10)
    ctx.app.tab("map")
    facts = ctx.app.wait_map(lambda f: f["detailed"] == "e2e Utrecht" and round(f["zoom"]) == 3, what="the detailed map chosen, at zoom 3")
    assert facts["note"] == ONLINE and not facts["offline"], facts
    ctx.app.wait_map(lambda f: f["served"]["detailed"] > 0, what="tiles from the detailed map")
    ctx.bridge.tiles(down=True)
    zoom_to(ctx, 5)  # past the file's zoom 3, where nothing was seen yet: downloads, which fail
    facts = ctx.app.wait_map(lambda f: f["offline"], timeout=20, what="the map offline")
    assert facts["note"] == "Offline map: e2e Utrecht. Outside it, the world overview.", facts["note"]
    assert facts["served"]["scaled"] > 0, facts["served"]  # the detailed map, scaled up
    assert round(facts["zoom"]) == 5, "zoomed out although a detailed map is there"
    ctx.shot("offline-detailed")
    ctx.bridge.tiles(down=False)
    time.sleep(3.5)  # the next download tried offline
    zoom_to(ctx, 6)
    facts = ctx.app.wait_map(lambda f: not f["offline"], timeout=20, what="the map back online")
    assert facts["note"] == ONLINE, facts["note"]


def case_g_offline_with_only_the_world_zooms_out(ctx):
    open_maps(ctx)
    ctx.tree.toggle("Use my detailed map")
    ctx.tree.wait_switch("Use my detailed map", False)
    ctx.app.tab("map")
    ctx.app.wait_map(lambda f: f["detailed"] is None, what="no detailed map")
    zoom_to(ctx, 8)
    ctx.bridge.tiles(down=True)
    ctx.tree.click("Zoom in")  # one step, to 9, where nothing was seen yet: the downloads fail
    facts = ctx.app.wait_map(lambda f: f["offline"] and round(f["zoom"]) == 5, timeout=20, what="offline, zoomed out to 5")
    assert facts["note"] == "Offline map: world overview, country level only. Add a detailed map in Setup > Maps.", facts["note"]
    ctx.shot("offline-world")
    ctx.bridge.tiles(down=False)
    time.sleep(3.5)
    zoom_to(ctx, 9)  # the zoom whose downloads failed: tried again, and they work
    ctx.app.wait_map(lambda f: not f["offline"], timeout=20, what="the map back online")


def case_h_delete_asks_first(ctx):
    open_maps(ctx)
    ctx.tree.click("Delete e2e Utrecht")
    names = [n.name for n in ctx.tree.dialog()]
    assert "Delete this map?" in names and "e2e Utrecht is removed from this phone. You can add it again from a file." in names, names
    ctx.tree.click_in_dialog("Keep it")
    time.sleep(0.8)
    ctx.tree.find("button", name="Use e2e Utrecht")
    ctx.app.mark()
    ctx.tree.click("Delete e2e Utrecht")
    ctx.tree.click_in_dialog("Delete")
    ctx.app.wait_toast("Map deleted: e2e Utrecht")
    ctx.tree.click("Delete e2e Zeeland")
    ctx.tree.click_in_dialog("Delete")
    ctx.app.wait_toast("Map deleted: e2e Zeeland")
    ctx.tree.wait_gone("e2e Zeeland")
    assert not ctx.tree.switches("Use my detailed map")
    folder = os.path.join(ctx.app.work, "xdg", "data", "meshsat", "mbtiles")
    assert os.listdir(folder) == [], os.listdir(folder)

