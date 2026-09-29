# SPDX-License-Identifier: GPL-3.0-or-later
"""Zones, offline maps and tracks (0.10.0) against MeshSat Android v2.19.4: the Zones screen's
numbers, words and geometry (GeofenceScreen.kt, GeofenceMonitorTest ported against the scripted
Bridge, which checks positions as the Bridge's monitor does), the MBTiles reader on Android's own
world.mbtiles, Setup > Maps' list and names, the Map tab's tracks and markers, and the node
sheet's words."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

from fakebridge import FakeBridge, load_scenario  # noqa: E402
from meshsat.model import geofence, maps, nodes, tracks  # noqa: E402
from meshsat.model.mbtiles import MBTiles, NotRaster, content_type  # noqa: E402

WORLD = os.path.join(APP, "meshsat", "maps", "world.mbtiles")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class RadiusTest(unittest.TestCase):
    def test_slider_to_radius(self):
        for t, radius in ((0, 50), (0.1, 80), (0.25, 160), (0.30103, 200), (0.5, 500), (0.6, 800), (0.75, 1600), (0.9, 3200), (1, 5000)):
            self.assertEqual(geofence.slider_to_radius(t), radius, t)

    def test_radius_to_slider(self):
        for radius, t in ((10, 0.0), (200, 0.30103), (1000, 0.650515), (50000, 1.0)):
            self.assertAlmostEqual(geofence.radius_to_slider(radius), t, places=5)

    def test_format_distance(self):
        for metres, words in ((20, "20 m"), (999.4, "999 m"), (999.6, "1000 m"), (1000, "1 km"), (1049, "1 km"), (1050, "1.1 km"), (1500, "1.5 km"),
                              (12340, "12.3 km"), (100000, "100 km")):
            self.assertEqual(geofence.format_distance(metres), words, metres)

    def test_zoom_for_radius(self):
        for radius, zoom in ((100, 17), (200, 16), (250, 16), (500, 15), (1000, 14), (2500, 13), (5000, 12), (15000, 11), (15001, 9)):
            self.assertEqual(geofence.zoom_for_radius(radius), zoom, radius)

    def test_zoom_for_span(self):
        for span, zoom in ((0.001, 16), (0.005, 15), (0.02, 13), (0.1, 11), (0.5, 9), (2, 7), (10, 5), (30, 3), (90, 3)):
            self.assertEqual(geofence.zoom_for_span(span), zoom, span)

    def test_radius_field(self):
        self.assertEqual(geofence.radius_ok("200"), 200)
        self.assertEqual(geofence.radius_ok("10"), 10)
        self.assertEqual(geofence.radius_ok("50000"), 50000)
        for bad in ("9", "50001", "", "2x0", "-5"):
            self.assertIsNone(geofence.radius_ok(bad), bad)


class GeometryTest(unittest.TestCase):
    def test_circle_polygon_vectors(self):
        poly = geofence.circle_polygon(52.0, 5.0, 200, 32)
        self.assertEqual(len(poly), 32)
        for i, lat, lon in ((0, 52.001798643211835, 5.0), (1, 52.00176408278687, 5.000569952640294), (8, 52.0, 5.002921480852584),
                            (16, 51.998201356788165, 5.0), (24, 52.0, 4.997078519147416)):
            self.assertAlmostEqual(poly[i]["lat"], lat, places=12)
            self.assertAlmostEqual(poly[i]["lon"], lon, places=12)

    def test_zone_radius_is_measured_on_the_ellipsoid(self):
        for lat, lon, r, shown in ((52, 5, 200, "200 m"), (52, 5, 1000, "1 km"), (0, 0, 1000, "998 m"), (52, 5, 50000, "50.1 km"), (64, 5, 200, "201 m")):
            self.assertEqual(geofence.format_distance(geofence.zone_radius(geofence.circle_polygon(lat, lon, r))), shown, (lat, r))

    def test_draft_circle_has_sixty_points_on_the_radius(self):
        ring = geofence.geodesic_circle(52.0, 5.0, 500, 60)
        self.assertEqual(len(ring), 60)
        for lat, lon in ring[::10]:
            self.assertAlmostEqual(haversine(52.0, 5.0, lat, lon), 500, delta=0.5)

    def test_point_in_polygon(self):
        square = [{"lat": 46.99, "lon": -122.01}, {"lat": 46.99, "lon": -121.99}, {"lat": 47.01, "lon": -121.99}, {"lat": 47.01, "lon": -122.01}]
        self.assertTrue(geofence.point_in_polygon(47.0, -122.0, square))  # GeofenceMonitorTest 1
        self.assertFalse(geofence.point_in_polygon(48.0, -122.0, square))  # 2
        self.assertFalse(geofence.point_in_polygon(47.0, -122.0, square[:2]))

    def test_show_points_is_the_box_middle_not_a_fit(self):
        lat, lon, zoom = geofence.show_points([(52.0, 5.0), (52.1, 5.2)])
        self.assertAlmostEqual(lat, 52.05)
        self.assertAlmostEqual(lon, 5.1)
        self.assertEqual(zoom, 9)  # a span of 0.2 degrees is not "< 0.2"
        self.assertEqual(geofence.show_points([(52.0, 5.0), (52.1, 5.1)])[2], 11)
        self.assertIsNone(geofence.show_points([]))
        self.assertEqual(geofence.show_points(geofence.zone_points({"polygon": geofence.circle_polygon(52, 5, 200)}))[2], 15)


class ZoneWordsTest(unittest.TestCase):
    def test_rows_and_bubbles(self):
        zone = {"name": "Home", "alert_on": "both", "polygon": geofence.circle_polygon(52, 5, 200)}
        self.assertEqual(geofence.zone_subtitle(zone), "Alerts when a node enters or leaves. Radius about 200 m.")
        self.assertEqual(geofence.zone_snippet({**zone, "alert_on": "enter"}), "Alerts when a node enters")
        self.assertEqual(geofence.alert_when("exit"), "leaves")
        self.assertEqual(geofence.alert_when("other"), "enters or leaves")
        self.assertEqual(geofence.delete_title("Home"), "Delete Home?")
        self.assertEqual(geofence.delete_name("Home"), "Delete zone Home")
        self.assertEqual(geofence.show_name("Home"), "Show Home on the map")
        self.assertEqual(geofence.added("Home"), "Zone added: Home")
        self.assertEqual(geofence.RADIUS_ERROR, "Use a radius between 10 m and 50 km.")

    def test_alert_lines(self):
        now = 1_790_000_000
        names = {"!a1b2c3d4": "Alice"}
        self.assertEqual(geofence.event_line({"zone_name": "Home", "node_id": "!a1b2c3d4", "event": "enter", "timestamp": (now - 240) * 1000}, names, now),
                         "Alice entered Home, 4 min ago")
        self.assertEqual(geofence.event_line({"zone_name": "Home", "node_id": "!00000001", "event": "exit", "timestamp": (now - 10) * 1000}, names, now),
                         "!00000001 left Home, just now")

    def test_save_checks_all_three_at_once(self):
        self.assertEqual(geofence.check(" ", None, "5"), {"name": True, "centre": True, "radius": True})
        self.assertEqual(geofence.check("Home", (52, 5), "200"), {"name": False, "centre": False, "radius": False})

    def test_new_zone(self):
        zone = geofence.new_zone("  Home ", (52.0, 5.0), 200, "exit", " gate ", now_ms=1759140000000)
        self.assertEqual(zone["id"], "zone_1759140000000")
        self.assertEqual((zone["name"], zone["alert_on"], zone["message"]), ("Home", "exit", "gate"))
        self.assertEqual(len(zone["polygon"]), 32)
        self.assertEqual(list(zone), ["id", "name", "polygon", "alert_on", "message"])


class MonitorTest(unittest.TestCase):
    """GeofenceMonitorTest, ported against the scripted Bridge's check (it mirrors the Bridge's
    GeofenceMonitor, whose own Go tests hold the same cases)."""

    SQUARE = [{"lat": 46.99, "lon": -122.01}, {"lat": 46.99, "lon": -121.99}, {"lat": 47.01, "lon": -121.99}, {"lat": 47.01, "lon": -122.01}]

    def monitor(self, *zones):
        fake = FakeBridge({"_zones": [dict(z) for z in zones]})
        self.addCleanup(fake.server.server_close)
        return fake

    def zone(self, **more):
        out = {"id": "test_zone", "name": "Test Zone", "polygon": self.SQUARE, "alert_on": "both", "message": ""}
        out.update(more)
        return out

    def test_enter_and_exit(self):
        fake = self.monitor(self.zone())
        self.assertEqual(fake.check_zones("node1", 48.0, -122.0), [])
        self.assertEqual([e["event"] for e in fake.check_zones("node1", 47.0, -122.0)], ["enter"])
        self.assertEqual([e["event"] for e in fake.check_zones("node1", 48.0, -122.0)], ["exit"])

    def test_no_event_while_inside(self):
        fake = self.monitor(self.zone())
        fake.check_zones("node1", 47.0, -122.0)
        self.assertEqual(fake.check_zones("node1", 47.001, -122.001), [])

    def test_enter_only_zone_does_not_alert_on_leaving(self):
        fake = self.monitor(self.zone(alert_on="enter"))
        fake.check_zones("node1", 47.0, -122.0)
        self.assertEqual(fake.check_zones("node1", 48.0, -122.0), [])

    def test_exit_only_zone_tracks_entering_quietly(self):
        fake = self.monitor(self.zone(alert_on="exit"))
        self.assertEqual(fake.check_zones("node1", 47.0, -122.0), [])
        self.assertEqual([e["event"] for e in fake.check_zones("node1", 48.0, -122.0)], ["exit"])

    def test_log_is_newest_first(self):
        fake = self.monitor(self.zone())
        fake.check_zones("node1", 47.0, -122.0)
        fake.check_zones("node1", 48.0, -122.0)
        self.assertEqual([e["event"] for e in fake.zone_events], ["exit", "enter"])

    def test_zones_tracked_independently(self):
        other = [{"lat": p["lat"] + 1, "lon": p["lon"]} for p in self.SQUARE]
        fake = self.monitor(self.zone(id="z1", name="Zone 1"), self.zone(id="z2", name="Zone 2", polygon=other))
        self.assertEqual([e["zone_name"] for e in fake.check_zones("node1", 47.0, -122.0)], ["Zone 1"])


class FakeZonesTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeBridge(load_scenario("zones")).start()
        self.addCleanup(self.fake.stop)

    def call(self, method: str, path: str, body=None):
        request = urllib.request.Request(self.fake.url + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as answer:
                raw = answer.read()
                return answer.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read()
            return error.code, json.loads(raw) if raw else None

    def test_zone_api_as_the_bridge(self):
        status, zones = self.call("GET", "/api/geofences")
        self.assertEqual((status, [z["name"] for z in zones]), (200, ["Home", "Station"]))
        zone = geofence.new_zone("e2e Gate", (52.0, 5.0), 300, "", "")
        status, saved = self.call("POST", "/api/geofences", zone)
        self.assertEqual((status, saved["alert_on"]), (201, "both"))
        self.assertEqual(self.call("POST", "/api/geofences", {"id": "x", "polygon": []})[0], 400)
        self.assertEqual(self.call("DELETE", f"/api/geofences/{zone['id']}")[0], 204)
        self.assertEqual(len(self.call("GET", "/api/geofences")[1]), 2)

    def test_a_node_moving_raises_the_zone_alerts(self):
        home = load_scenario("zones")["_zones"][1]  # Station: enters and leaves
        self.call("POST", "/__fake__/position", {"node_id": "!a1b3c2ec", "lat": 52.0907, "lon": 5.1214})
        self.call("POST", "/__fake__/position", {"node_id": "!a1b3c2ec", "lat": 52.3, "lon": 5.3})
        events = self.call("GET", "/api/geofences/events")[1]["events"]
        self.assertEqual([(e["zone_name"], e["event"]) for e in events[:2]], [(home["name"], "exit"), (home["name"], "enter")])
        rows = self.call("GET", "/api/positions?limit=5000")[1]["positions"]
        self.assertEqual((rows[0]["latitude"], rows[0]["longitude"]), (52.3, 5.3))

    def test_positions_since(self):
        status, body = self.call("GET", "/api/positions?since=" + urllib.request.quote(tracks.since_param()) + "&limit=5000")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["positions"]), 9)  # the row older than a day is left out

    def test_no_monitor_answers_503(self):
        fake = FakeBridge(load_scenario("zones-down")).start()
        self.addCleanup(fake.stop)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(fake.url + "/api/geofences", timeout=5)
        self.assertEqual(caught.exception.code, 503)


class MBTilesTest(unittest.TestCase):
    def test_world_overview(self):
        world = MBTiles(WORLD)
        self.addCleanup(world.close)
        self.assertEqual(world.name, "Natural Earth World")
        self.assertEqual(world.zoom_range(), (0, 3))
        self.assertEqual(world.bounds(), (-180.0, -85.05, 180.0, 85.05))
        self.assertEqual(os.path.getsize(WORLD), 249856)
        count = 0
        for z in range(4):
            for x in range(1 << z):
                for y in range(1 << z):
                    data = world.tile(z, x, y)
                    self.assertEqual(content_type(data), "image/png")
                    count += 1
        self.assertEqual(count, 85)
        self.assertIsNone(world.tile(4, 0, 0))
        self.assertIsNone(world.tile(1, 2, 0))

    def test_rows_are_flipped(self):
        """XYZ row 0 is the top; the file keeps TMS rows, counted from the bottom."""
        db = sqlite3.connect(WORLD)
        self.addCleanup(db.close)
        world = MBTiles(WORLD)
        self.addCleanup(world.close)
        for z, x, y in ((1, 0, 0), (2, 1, 3), (3, 5, 2)):
            raw = db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?", (z, x, (1 << z) - 1 - y)).fetchone()[0]
            self.assertEqual(world.tile(z, x, y), bytes(raw))

    def test_vector_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = make_mbtiles(folder, "v.mbtiles", "Vector", "pbf")
            with self.assertRaises(NotRaster):
                MBTiles(path)


class MapsTest(unittest.TestCase):
    def test_safe_names(self):
        self.assertEqual(maps.safe_name("My Map (1).mbtiles"), "My_Map__1_.mbtiles")
        self.assertEqual(maps.safe_name("utrecht"), "utrecht.mbtiles")
        self.assertEqual(maps.safe_name(""), "map.mbtiles")
        self.assertEqual(maps.safe_name("world.mbtiles"), "my_world.mbtiles")

    def test_listing(self):
        with tempfile.TemporaryDirectory() as folder:
            make_mbtiles(folder, "b.mbtiles", "Utrecht", "png", minzoom=0, maxzoom=14)
            make_mbtiles(folder, "a.mbtiles", "Zeeland", "pbf")
            make_mbtiles(folder, "c.mbtiles", "", "jpg")
            make_mbtiles(folder, "world.mbtiles", "World", "png")
            make_mbtiles(folder, ".adding-x.mbtiles", "Half", "png")
            with open(os.path.join(folder, "broken.mbtiles"), "wb") as handle:
                handle.write(b"not sqlite")
            with open(os.path.join(folder, "notes.txt"), "w") as handle:
                handle.write("x")
            entries = maps.listing(folder)
            self.assertEqual([e.name for e in entries], ["Utrecht", "Zeeland", "c"])
            utrecht, zeeland, c = entries
            self.assertTrue(zeeland.vector)
            self.assertFalse(utrecht.vector)
            self.assertRegex(utrecht.details(), r"^0\.0 MB, zoom 0 to 14$")
            self.assertEqual(c.details(), "0.0 MB")
            self.assertIsNone(maps.active(entries, True, "a.mbtiles"))  # vector: never in use
            self.assertEqual(maps.active(entries, True, "b.mbtiles").name, "Utrecht")
            self.assertIsNone(maps.active(entries, False, "b.mbtiles"))
            self.assertEqual(maps.turn_on(entries, "gone.mbtiles").filename, "b.mbtiles")
            self.assertEqual(maps.turn_on(entries, "c.mbtiles").filename, "c.mbtiles")

    def test_details(self):
        self.assertEqual(maps.Entry("x", "X", int(12.25 * 1048576), 0, 14, False).details(), "12.3 MB, zoom 0 to 14")

    def test_checked_open(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError) as caught:
                maps.open_checked(os.path.join(folder, "none.mbtiles"))
            self.assertTrue(str(caught.exception).startswith("MBTiles file not found: "))
            path = os.path.join(folder, "t.mbtiles")
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
            db.commit()
            db.close()
            with self.assertRaises(ValueError) as caught:
                maps.open_checked(path)
            self.assertEqual(str(caught.exception), "Not a valid MBTiles file: missing 'tiles' table")
            path = os.path.join(folder, "m.mbtiles")
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
            db.commit()
            db.close()
            with self.assertRaises(ValueError) as caught:
                maps.open_checked(path)
            self.assertEqual(str(caught.exception), "Not a valid MBTiles file: missing 'metadata' table")
            junk = os.path.join(folder, "j.mbtiles")
            with open(junk, "wb") as handle:
                handle.write(b"x" * 200)
            with self.assertRaises(ValueError):
                maps.open_checked(junk)
            self.assertEqual(maps.invalid("file is not a database"), "Invalid MBTiles file: file is not a database")
            self.assertEqual(maps.could_not_add(maps.invalid("x")), "Could not add this map: Invalid MBTiles file: x")

    def test_note(self):
        self.assertEqual(maps.note(False, "Utrecht"), ("© OpenStreetMap contributors", "credit"))
        self.assertEqual(maps.note(True, "Utrecht"), ("Offline map: Utrecht. Outside it, the world overview.", "note"))
        self.assertEqual(maps.note(True, None), ("Offline map: world overview, country level only. Add a detailed map in Setup > Maps.", "note"))
        self.assertEqual(maps.note(True, None, zones=True)[0],
                         "Offline, with no street detail here. Zones still work: place one around your position. For detail, add a map in Setup > Maps.")

    def test_offline_after_three_failures(self):
        online = maps.Online()
        online.failed()
        online.failed()
        self.assertFalse(online.offline)
        online.failed()
        self.assertTrue(online.offline)
        online.worked()
        self.assertFalse(online.offline)

    def test_dialog_words(self):
        self.assertEqual(maps.delete_body("Utrecht"), "Utrecht is removed from this phone. You can add it again from a file.")
        self.assertEqual((maps.added("Utrecht"), maps.deleted("Utrecht"), maps.use_name("Utrecht")), ("Map added: Utrecht", "Map deleted: Utrecht", "Use Utrecht"))


class TracksTest(unittest.TestCase):
    NOW = 1_790_000_000

    def test_since_is_sqlite_utc(self):
        self.assertEqual(tracks.since_param(1_790_086_400), "2026-09-21 14:13:20")

    def test_summary_and_heard(self):
        self.assertEqual(tracks.summary(0, 0), "No node positions yet")
        self.assertEqual(tracks.summary(2, 3), "2 of 3 nodes shown")
        self.assertEqual(tracks.summary(1, 1), "1 of 1 node shown")
        self.assertEqual(tracks.heard(self.NOW - 240, self.NOW), "Heard 4 min ago")
        self.assertEqual(tracks.heard(self.NOW - 900, self.NOW), "Heard 15 min ago")
        self.assertEqual(tracks.heard(self.NOW - 7200, self.NOW), "Last heard 2 h ago")
        self.assertEqual(tracks.node_snippet({"last_heard": self.NOW - 240, "altitude": 12}, self.NOW), "Heard 4 min ago, altitude 12 m")

    def test_phone_row(self):
        self.assertEqual(tracks.accuracy(12.9), "Within about 12 m")
        self.assertEqual(tracks.accuracy(None), "Accuracy unknown")
        self.assertEqual(tracks.phone_line(52.123455, 5.12345, 12), "52.12346, 5.12345, within about 12 m")
        self.assertEqual(tracks.phone_line(52.1, 5.1, None), "52.10000, 5.10000, accuracy unknown")

    def test_group(self):
        rows = [{"node_id": "!a", "latitude": 3, "longitude": 3}, {"node_id": "!b", "latitude": 9, "longitude": 9}, {"node_id": "!a", "latitude": 2, "longitude": 2},
                {"node_id": "!a", "latitude": 1, "longitude": 1}, {"node_id": "", "latitude": 5, "longitude": 5}, {"node_id": "!c", "latitude": 7, "longitude": 7},
                {"node_id": "!c", "latitude": 6, "longitude": 6}]
        self.assertEqual(tracks.group(rows, set()), {"!a": [(1, 1), (2, 2), (3, 3)], "!c": [(6, 6), (7, 7)]})
        self.assertEqual(tracks.group(rows, {"!a"}), {"!c": [(6, 6), (7, 7)]})
        joined = tracks.group(rows, set(), {"!a": (4.0, 4.0), "!b": (9.5, 9.5), "!c": (7, 7)})
        self.assertEqual(joined["!a"][-1], (4.0, 4.0))
        self.assertEqual(joined["!b"], [(9, 9), (9.5, 9.5)])  # one fix and the marker make a line
        self.assertEqual(joined["!c"], [(6, 6), (7, 7)])

    def test_markers(self):
        nodes_ = [{"user_id": "!me", "latitude": 52, "longitude": 5, "last_heard": self.NOW},
                  {"user_id": "!a", "long_name": "Alice", "latitude": 52.1, "longitude": 5.1, "last_heard": self.NOW - 60},
                  {"user_id": "!b", "short_name": "BB", "latitude": 52.2, "longitude": 5.2, "last_heard": self.NOW - 3600},
                  {"user_id": "!c", "latitude": 0, "longitude": 0, "last_heard": self.NOW}]
        rows = [{"node_id": "PA3XYZ-9", "latitude": 52.3, "longitude": 5.3, "created_at": "2026-09-21T13:00:00Z"},
                {"node_id": "!a", "latitude": 1, "longitude": 1, "created_at": "2026-09-21T12:00:00Z"}]
        out = tracks.markers(nodes_, rows, {"!me"}, self.NOW)
        self.assertEqual([(m["id"], m["label"], m["stale"]) for m in out], [("!a", "Alice", False), ("!b", "BB", True), ("PA3XYZ-9", "PA3XYZ-9", True)])
        self.assertEqual(tracks.marker_snippet(out[0], self.NOW, zones=True), "Heard 1 min ago")
        self.assertEqual(tracks.marker_snippet(out[1], self.NOW), "Last heard 1 h ago")


class NodeSheetTest(unittest.TestCase):
    NOW = 1_790_000_000

    def test_someone_elses_node(self):
        node = {"user_id": "!a1b3c2ec", "long_name": "MSPA", "short_name": "MSPA", "last_heard": self.NOW - 120, "battery_level": 78, "snr": 8.25,
                "hw_model": 50, "hw_model_name": "T_DECK", "latitude": 52.3731, "longitude": 4.8932}
        self.assertEqual(nodes.title(node, False), "MSPA")
        self.assertEqual(nodes.subtitle(node), "MSPA  !a1b3c2ec")
        self.assertEqual(nodes.rows(node, False, self.NOW), [
            ("Last heard", "2 min ago", False), ("Battery", "78%", True), ("Signal", "Heard directly. SNR 8.3 dB, as your node last measured it.", False),
            ("Hardware", "LilyGO T-Deck", False), ("Position", "52.37310, 4.89320, 2 min ago", True)])
        self.assertTrue(nodes.has_position(node))

    def test_own_node_and_the_unknowns(self):
        node = {"user_id": "!52cb81e7", "long_name": "", "battery_level": 101, "hw_model": 0}
        self.assertEqual(nodes.title(node, True), "!52cb81e7 (your node)")
        self.assertEqual(nodes.subtitle(node), "!52cb81e7")
        self.assertEqual(nodes.rows(node, True, self.NOW), [("Battery", "On USB power", False), ("Position", nodes.NOT_SHARED, False)])
        self.assertEqual(nodes.battery(0), None)
        self.assertEqual(nodes.signal({"hops_away": 2}), "Heard through other nodes, 2 hops away.")
        self.assertEqual(nodes.signal({}), nodes.NOT_MEASURED)
        self.assertFalse(nodes.has_position({"latitude": 0, "longitude": 0}))


def make_mbtiles(folder: str, filename: str, name: str, fmt: str, minzoom: int | None = None, maxzoom: int | None = None) -> str:
    path = os.path.join(folder, filename)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
    meta = {"name": name, "format": fmt}
    if minzoom is not None:
        meta["minzoom"] = str(minzoom)
    if maxzoom is not None:
        meta["maxzoom"] = str(maxzoom)
    db.executemany("INSERT INTO metadata VALUES (?, ?)", [(k, v) for k, v in meta.items() if v])
    db.execute("INSERT INTO tiles VALUES (0, 0, 0, ?)", (PNG,))
    db.commit()
    db.close()
    return path


def haversine(lat1, lon1, lat2, lon2) -> float:
    import math

    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


if __name__ == "__main__":
    unittest.main()
