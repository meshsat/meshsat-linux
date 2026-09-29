# SPDX-License-Identifier: GPL-3.0-or-later
"""The map MeshSat Android's two map screens share (map/MapTiles.kt, ui/components/MapChrome.kt,
map/MapMarkers.kt): the tiles drawn through the dark matrix, and above them, unfiltered, what a
screen puts on it, bottom to top: saved zones, tracks, node diamonds with their names, this
phone's accuracy circle and dot, and the zone being placed. The round buttons, the note in the
bottom left corner, a hint in the top left, and the bubble a tap on a marker, a track or a zone
opens (osmdroid's info window: its title and snippet) sit on top.

Taps and long presses are read on the map itself before its own gestures (so dragging and
pinching stay the map's), and everything drawn above it lets touches through."""
import math
import time

import gi

from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from . import maptiles, theme, trace
from .model import geofence, maps, tracks
from .widgets import Filtered, icon_button, text

try:
    gi.require_version("Shumate", "1.0")
    from gi.repository import Shumate
except (ValueError, ImportError):
    Shumate = None

START = (20.0, 0.0, 3.0)  # both screens open here (MapTiles.kt:117-128)
MIN_ZOOM = 2.0
MOVE_MS = 600  # animateTo(point, zoom, 600L)
ZOOM_MS = 300


def rgba(colour: str, alpha: float = 1.0) -> tuple:
    c = Gdk.RGBA()
    c.parse(colour)
    return c.red, c.green, c.blue, alpha


class MeshMap(Gtk.Overlay):
    def __init__(self, app, zones: bool = False):
        super().__init__()
        self.app = app
        self.zones_screen = zones  # Zones' own offline sentence, and no zoom-out when offline
        self.add_css_class("map-box")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.zones = []
        self.tracks = {}  # node id -> [(lat, lon)], oldest first
        self.track_titles = {}
        self.nodes = []  # [{"id", "lat", "lon", "label", "stale", "snippet"}]
        self.phone = None  # (lat, lon)
        self.accuracy = None
        self.phone_snippet = None
        self.draft = None  # (lat, lon, radius in metres)
        self.on_long_press = None  # (lat, lon) -> None
        self.bubble = None  # (popover, key, lat, lon)
        self._held = 0.0
        self._label_boxes = []  # (x0, y0, x1, y1, node) of the names drawn, for taps
        self.map = None
        if Shumate is None:
            missing = text("The map needs libshumate (gir1.2-shumate-1.0).", "body-medium", theme.TEXT_SECONDARY, xalign=0.5, wrap=True)
            missing.set_vexpand(True)
            self.set_child(missing)
            return
        self.tiles = app.tiles
        self.map = Shumate.Map()
        self.map.set_hexpand(True)
        self.map.set_vexpand(True)
        self.map.set_go_to_duration(MOVE_MS)
        # The camera first and the tiles after it: libshumate holds back loading while the view
        # moves fast, and a camera set after the tile layer reads as a fast move.
        viewport = self.map.get_viewport()
        viewport.set_zoom_level(START[2])
        self.map.center_on(START[0], START[1])
        self.layer = None
        self._resolved = False
        self.reload_tiles()
        self.set_child(Filtered(self.map, theme.DARK_TILES_MATRIX))

        self.drawing = Gtk.DrawingArea()
        self.drawing.set_can_target(False)
        self.drawing.set_draw_func(self.draw)
        self.add_overlay(self.drawing)
        for prop in ("latitude", "longitude", "zoom-level", "rotation"):
            viewport.connect(f"notify::{prop}", self._moved)

        tap = Gtk.GestureClick()
        tap.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        tap.connect("released", self._tapped)
        self.map.add_controller(tap)
        hold = Gtk.GestureLongPress()
        hold.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        hold.connect("pressed", self._held_down)
        self.map.add_controller(hold)

        # Top left, the hint (Zones); top right, the screen's own buttons; bottom right, the
        # zoom; bottom left, the note: each 8 dp in, the left ones 64 dp clear of the right.
        self.hint = text("", "body-small", wrap=True)
        self.hint.add_css_class("map-note")
        self.hint.set_max_width_chars(40)
        self.hint.set_halign(Gtk.Align.START)
        self.hint.set_valign(Gtk.Align.START)
        self.hint.set_margin_top(theme.dp(8))
        self.hint.set_margin_start(theme.dp(8))
        self.hint.set_margin_end(theme.dp(64))
        self.hint.set_visible(False)
        self.add_overlay(self.hint)
        self.buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.buttons.set_halign(Gtk.Align.END)
        self.buttons.set_valign(Gtk.Align.START)
        self.buttons.set_margin_top(theme.dp(8))
        self.buttons.set_margin_end(theme.dp(8))
        self.add_overlay(self.buttons)
        zoom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        zoom.set_halign(Gtk.Align.END)
        zoom.set_valign(Gtk.Align.END)
        zoom.set_margin_bottom(theme.dp(8))
        zoom.set_margin_end(theme.dp(8))
        zoom.append(self.round("outlined-add", lambda: self.zoom_step(1), "Zoom in"))
        zoom.append(self.round("outlined-remove", lambda: self.zoom_step(-1), "Zoom out"))
        self.add_overlay(zoom)
        self.note = text("", "body-small", wrap=True)
        self.note.set_max_width_chars(44)
        self.note.set_halign(Gtk.Align.START)
        self.note.set_valign(Gtk.Align.END)
        self.note.set_margin_start(theme.dp(8))
        self.note.set_margin_bottom(theme.dp(8))
        self.note.set_margin_end(theme.dp(64))
        self.add_overlay(self.note)
        self.refresh_note()
        self.tiles.listen(self._offline_changed)
        self.connect("unmap", lambda *_: self.close_bubble())

    # The chrome
    def round(self, name: str, on_click, description: str) -> Gtk.Button:
        """MapButton (MapChrome.kt:107-117): a 48 dp circle on Surface with a 1 dp ring; its
        description is its accessible name."""
        button = icon_button(name, on_click, 24, theme.TEXT_PRIMARY, description)
        button.remove_css_class("icon-button")
        button.add_css_class("round")
        return button

    def add_button(self, name: str, on_click, description: str) -> Gtk.Button:
        button = self.round(name, on_click, description)
        self.buttons.append(button)
        return button

    def set_hint(self, value: str | None) -> None:
        self.hint.set_text(value or "")
        self.hint.set_visible(bool(value))

    def refresh_note(self) -> None:
        """MapStatusNote (MapChrome.kt:119-152): the credit online; offline, which map is shown."""
        if self.map is None:
            return
        value, kind = maps.note(self.tiles.offline, self.tiles.detailed_name(), zones=self.zones_screen)
        self.note.set_text(value)
        for c in ("map-credit", "map-note"):
            self.note.remove_css_class(c)
        self.note.add_css_class("map-credit" if kind == "credit" else "map-note")

    def _offline_changed(self, offline: bool) -> None:
        if not offline:
            self.reload_tiles(force=True)  # the tiles scaled up offline give way to real ones
        self.refresh_note()
        self.zoom_out_offline()

    def zoom_out_offline(self) -> None:
        """MapScreen.kt:297-304: offline with no detailed map, the Map tab zooms out from beyond 6
        to 5, where the world overview still reads. Zones keeps its zoom."""
        if self.map is None or self.zones_screen:
            return
        if self.tiles.offline and self.tiles.detailed_name() is None and self.zoom_level() > 6:
            viewport = self.map.get_viewport()
            self.go_to(viewport.get_latitude(), viewport.get_longitude(), 5.0, animate=False)

    def reload_tiles(self, force: bool = False) -> None:
        """A new tile layer when the detailed map the settings choose has changed (or when forced),
        as MapTilesEffect rebuilds its tile source; otherwise nothing."""
        if self.map is None:
            return
        resolved = self.tiles.resolved()
        if not force and resolved == self._resolved:
            return
        self._resolved = resolved
        renderer = self.tiles.renderer()
        viewport = self.map.get_viewport()
        if self.layer is not None:
            self.map.remove_layer(self.layer)
        self.map.set_map_source(renderer)
        viewport.set_min_zoom_level(MIN_ZOOM)
        viewport.set_max_zoom_level(maptiles.MAX_ZOOM)
        self.layer = Shumate.MapLayer.new(renderer, viewport)
        self.map.add_layer(self.layer)
        if hasattr(self, "note"):
            self.refresh_note()
            self.zoom_out_offline()

    # The camera
    def zoom_level(self) -> float:
        return self.map.get_viewport().get_zoom_level() if self.map is not None else START[2]

    def centre(self) -> tuple:
        viewport = self.map.get_viewport()
        return viewport.get_latitude(), viewport.get_longitude()

    def go_to(self, lat: float, lon: float, zoom: float | None = None, animate: bool = True) -> None:
        if self.map is None:
            return
        viewport = self.map.get_viewport()
        zoom = viewport.get_zoom_level() if zoom is None else max(MIN_ZOOM, min(float(maptiles.MAX_ZOOM), zoom))
        if animate:
            self.map.go_to_full_with_duration(lat, lon, zoom, MOVE_MS)
        else:
            self.map.stop_go_to()
            viewport.set_zoom_level(zoom)
            self.map.center_on(lat, lon)
            self._settle(int(zoom))

    def _settle(self, zoom: int) -> None:
        """After a jump that is not animated: libshumate holds tiles back while the view "moves
        fast", and looks at the speed again only on a later frame. New frames are asked for; if the
        new zoom still has no tile asked for a moment later, the tile layer is made again."""
        asked = self.tiles.asked.get(zoom, 0)

        def redraw() -> bool:
            if self.map is not None and self.get_mapped():
                self.map.queue_draw()
                if self.layer is not None:
                    self.layer.queue_allocate()
            return False

        def check() -> bool:
            if self.get_mapped() and int(self.zoom_level()) == zoom and self.tiles.asked.get(zoom, 0) == asked:
                self.reload_tiles(force=True)
            return False

        GLib.timeout_add(60, redraw)
        GLib.timeout_add(500, redraw)
        GLib.timeout_add(1200, check)

    def zoom_step(self, step: int) -> None:
        if self.map is None:
            return
        lat, lon = self.centre()
        zoom = max(MIN_ZOOM, min(float(maptiles.MAX_ZOOM), round(self.zoom_level()) + step))
        self.map.go_to_full_with_duration(lat, lon, zoom, ZOOM_MS)

    def show_points(self, points: list, animate: bool = True) -> None:
        """MapChrome.showPoints: the middle of the points' box at the zoom for its larger span
        (deliberately not a fit); nothing for no points."""
        view = geofence.show_points(points)
        if view is not None:
            self.go_to(view[0], view[1], view[2], animate)

    # What the screen puts on the map
    def set_zones(self, zones: list) -> None:
        self.zones = [z for z in zones if len(z.get("polygon") or []) >= 3]
        self._keep_bubble("zone", {z.get("id") for z in self.zones})
        self._redraw()

    def set_tracks(self, tracks: dict, titles: dict) -> None:
        self.tracks = tracks
        self.track_titles = titles
        self._keep_bubble("track", set(tracks))
        self._redraw()

    def set_nodes(self, nodes: list) -> None:
        self.nodes = nodes
        self._keep_bubble("node", {n["id"] for n in nodes})
        if self.bubble is not None and self.bubble[1][0] == "node":
            for n in nodes:  # an open bubble stays with its node when the node moves
                if n["id"] == self.bubble[1][1]:
                    self.bubble = (self.bubble[0], self.bubble[1], n["lat"], n["lon"])
        self._redraw()
        self._place_bubble()

    def set_phone(self, position, accuracy=None, snippet: str | None = None) -> None:
        self.phone = (position[0], position[1]) if position else None
        self.accuracy = accuracy if position and accuracy and accuracy >= 1 else None
        self.phone_snippet = snippet
        self._keep_bubble("phone", {""} if self.phone else set())
        self._redraw()

    def set_draft(self, centre, radius: float) -> None:
        self.draft = (centre[0], centre[1], float(radius)) if centre else None
        self._redraw()

    # Drawing
    def _redraw(self) -> None:
        if self.map is not None:
            self.drawing.queue_draw()

    def _moved(self, *_args) -> None:
        self.drawing.queue_draw()
        self._place_bubble()

    def xy(self, lat: float, lon: float) -> tuple:
        return self.map.get_viewport().location_to_widget_coords(self.map, lat, lon)

    def draw(self, _area, cr, width, height) -> None:
        if self.map is None or self.map.get_width() <= 0:
            return
        cr.set_line_join(1)  # round
        for zone in self.zones:
            self._polygon(cr, [(p["lat"], p["lon"]) for p in zone["polygon"]], theme.AMBER, 0.12, theme.AMBER, 1.0, theme.dp(2))
        cr.set_line_cap(1)  # round
        cr.set_dash([theme.dp(8), theme.dp(5)])
        cr.set_line_width(theme.dp(3))
        cr.set_source_rgba(*rgba(theme.MESH, 0.75))
        for points in self.tracks.values():
            if len(points) < 2:
                continue
            for i, (lat, lon) in enumerate(points):
                x, y = self.xy(lat, lon)
                (cr.move_to if i == 0 else cr.line_to)(x, y)
            cr.stroke()
        cr.set_dash([])
        self._label_boxes = []
        for node in self.nodes:
            self._diamond(cr, node)
        if self.phone is not None:
            if self.accuracy:
                self._polygon(cr, geofence.geodesic_circle(self.phone[0], self.phone[1], self.accuracy, 60), theme.SIGNAL_ORANGE, 0.12, theme.SIGNAL_ORANGE, 0.5, theme.dp(1.5))
            self._dot(cr, self.phone, theme.dp(18))
        if self.draft is not None:
            lat, lon, radius = self.draft
            self._polygon(cr, geofence.geodesic_circle(lat, lon, radius, 60), theme.SIGNAL_ORANGE, 0.15, theme.SIGNAL_ORANGE, 1.0, theme.dp(2))
            self._dot(cr, (lat, lon), theme.dp(14))

    def _polygon(self, cr, points: list, fill: str, fill_alpha: float, stroke: str, stroke_alpha: float, width: float) -> None:
        for i, (lat, lon) in enumerate(points):
            x, y = self.xy(lat, lon)
            (cr.move_to if i == 0 else cr.line_to)(x, y)
        cr.close_path()
        cr.set_source_rgba(*rgba(fill, fill_alpha))
        cr.fill_preserve()
        cr.set_source_rgba(*rgba(stroke, stroke_alpha))
        cr.set_line_width(width)
        cr.stroke()

    def _dot(self, cr, at: tuple, size: float) -> None:
        """MarkerPainter.dot: a disc with a 3 dp ring of the page's black, orange inside."""
        x, y = self.xy(at[0], at[1])
        cr.set_source_rgba(*rgba(theme.SPACE_BLACK))
        cr.arc(x, y, size / 2, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(*rgba(theme.SIGNAL_ORANGE))
        cr.arc(x, y, max(1.0, size / 2 - theme.dp(3)), 0, 2 * math.pi)
        cr.fill()

    def _diamond(self, cr, node: dict) -> None:
        """MarkerPainter.node: a 22 dp diamond in the mesh colour (faded when stale) with a 2 dp
        outline, and the name 2 dp under it on a pill of the page's black at 80 %."""
        x, y = self.xy(node["lat"], node["lon"])
        half = theme.dp(11)
        cr.move_to(x, y - half)
        cr.line_to(x + half, y)
        cr.line_to(x, y + half)
        cr.line_to(x - half, y)
        cr.close_path()
        cr.set_source_rgba(*rgba(theme.MESH, 115 / 255 if node.get("stale") else 1.0))
        cr.fill_preserve()
        cr.set_source_rgba(*rgba(theme.SPACE_BLACK))
        cr.set_line_width(theme.dp(2))
        cr.stroke()
        label = node.get("label") or ""
        if not label:
            return
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription.from_string(theme.FONT)
        font.set_absolute_size(theme.dp(12) * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text(label, -1)
        layout.set_width(theme.dp(144) * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_single_paragraph_mode(True)
        w, h = layout.get_pixel_size()
        pad_x, pad_y = theme.dp(6), theme.dp(3)
        left, top = x - w / 2 - pad_x, y + half + theme.dp(2)
        right, bottom = x + w / 2 + pad_x, top + h + 2 * pad_y
        radius = theme.dp(4)
        cr.new_sub_path()
        cr.arc(right - radius, top + radius, radius, -math.pi / 2, 0)
        cr.arc(right - radius, bottom - radius, radius, 0, math.pi / 2)
        cr.arc(left + radius, bottom - radius, radius, math.pi / 2, math.pi)
        cr.arc(left + radius, top + radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(*rgba(theme.SPACE_BLACK, 0.8))
        cr.fill()
        cr.set_source_rgba(*rgba(theme.TEXT_MUTED if node.get("stale") else theme.TEXT_PRIMARY))
        cr.move_to(left + pad_x, top + pad_y)
        PangoCairo.show_layout(cr, layout)
        self._label_boxes.append((left, top, right, bottom, node))

    # Taps: the bubble (osmdroid's info window), and the long press
    def _tapped(self, _gesture, n_press, x, y) -> None:
        if n_press != 1 or time.monotonic() - self._held < 0.6:
            return
        self.tap_at(x, y)

    def _held_down(self, gesture, x, y) -> None:
        if self.on_long_press is None:
            return  # a long press means nothing here: the finger stays the map's
        self._held = time.monotonic()
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.long_press_at(x, y)

    def long_press_at(self, x: float, y: float) -> None:
        if self.on_long_press is None:
            return
        lat, lon = self.map.get_viewport().widget_coords_to_location(self.map, x, y)
        self.on_long_press(lat, lon)

    def tap_at(self, x: float, y: float) -> None:
        """The item under a tap, topmost first: this phone, a node (its diamond or its name), a
        track, a saved zone. The draft and the accuracy circle never answer."""
        hit = None
        if self.phone is not None:
            px, py = self.xy(*self.phone)
            if math.hypot(x - px, y - py) <= theme.dp(14):
                hit = (("phone", ""), self.phone, tracks.THIS_PHONE, self.phone_snippet)
        if hit is None:
            for node in reversed(self.nodes):
                nx, ny = self.xy(node["lat"], node["lon"])
                inside_label = any(b[4] is node and b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in self._label_boxes)
                if math.hypot(x - nx, y - ny) <= theme.dp(16) or inside_label:
                    hit = (("node", node["id"]), (node["lat"], node["lon"]), node.get("label") or node["id"], node.get("snippet"))
                    break
        if hit is None:
            for node_id, points in self.tracks.items():
                if len(points) >= 2 and self._near_line(x, y, points, theme.dp(12)):
                    lat, lon = self.map.get_viewport().widget_coords_to_location(self.map, x, y)
                    hit = (("track", node_id), (lat, lon), self.track_titles.get(node_id, ""), None)
                    break
        if hit is None:
            lat, lon = self.map.get_viewport().widget_coords_to_location(self.map, x, y)
            for zone in reversed(self.zones):
                if geofence.point_in_polygon(lat, lon, zone["polygon"]):
                    hit = (("zone", zone.get("id")), (lat, lon), zone.get("name", ""), geofence.zone_snippet(zone))
                    break
        if hit is None:
            self.close_bubble()
            return
        key, at, title, snippet = hit
        self.open_bubble(key, at, title, snippet)
        if key[0] in ("node", "phone"):
            self.go_to(at[0], at[1])  # a marker tap also pans to the marker

    def _near_line(self, x: float, y: float, points: list, limit: float) -> bool:
        previous = None
        for lat, lon in points:
            here = self.xy(lat, lon)
            if previous is not None and segment_distance(x, y, previous, here) <= limit:
                return True
            previous = here
        return False

    def open_bubble(self, key: tuple, at: tuple, title: str, snippet: str | None) -> None:
        self.close_bubble()
        popover = Gtk.Popover()
        # No grab: the bubble stays until a tap elsewhere on the map closes it (osmdroid's info
        # window), and it shows whether or not a finger opened it.
        popover.set_autohide(False)
        popover.set_position(Gtk.PositionType.TOP)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        box.add_css_class("map-bubble")
        box.append(text(title, "title-small", wrap=True))
        if snippet:
            box.append(text(snippet, "body-small", theme.TEXT_SECONDARY, wrap=True))
        popover.set_child(box)
        popover.set_parent(self)
        popover.connect("closed", lambda p: GLib.idle_add(self._forget_bubble, p))
        self.bubble = (popover, key, at[0], at[1])
        self._place_bubble()
        popover.popup()
        trace.event("bubble", title=title, snippet=snippet or "")

    def _place_bubble(self) -> None:
        if self.bubble is None or self.map is None:
            return
        popover, _key, lat, lon = self.bubble
        x, y = self.xy(lat, lon)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y) - theme.dp(10), 1, 1
        popover.set_pointing_to(rect)

    def _keep_bubble(self, kind: str, keys: set) -> None:
        """An open bubble closes when its item is no longer on the map (a layer switched off, a
        node hidden, a zone deleted)."""
        if self.bubble is not None and self.bubble[1][0] == kind and self.bubble[1][1] not in keys:
            self.close_bubble()

    def close_bubble(self) -> None:
        if self.bubble is None:
            return
        popover = self.bubble[0]
        self.bubble = None
        popover.popdown()
        self._forget_bubble(popover)

    def _forget_bubble(self, popover) -> bool:
        if self.bubble is not None and self.bubble[0] is popover:
            self.bubble = None
        if popover.get_parent() is not None:
            popover.unparent()
        return False

    # For the tests: what is drawn, and a finger at a place
    def press(self, kind: str, lat: float, lon: float) -> None:
        x, y = self.xy(lat, lon)
        (self.long_press_at if kind == "long" else self.tap_at)(x, y)

    def facts(self) -> dict:
        if self.map is None:
            return {}
        lat, lon = self.centre()
        return {"zoom": round(self.zoom_level(), 2), "centre": [round(lat, 5), round(lon, 5)], "zones": [z.get("name", "") for z in self.zones],
                "tracks": {k: len(v) for k, v in self.tracks.items()}, "track_titles": dict(self.track_titles), "nodes": [n.get("label") for n in self.nodes],
                "stale": [n.get("label") for n in self.nodes if n.get("stale")], "phone": list(self.phone) if self.phone else None, "accuracy": self.accuracy,
                "draft": list(self.draft) if self.draft else None, "note": self.note.get_text(), "hint": self.hint.get_text() if self.hint.get_visible() else "",
                "offline": self.tiles.offline, "detailed": self.tiles.detailed_name(), "bubble": self.bubble[1][0] if self.bubble else None,
                "served": dict(self.tiles.served), "asked": {str(k): v for k, v in sorted(self.tiles.asked.items())}}


def segment_distance(x: float, y: float, a: tuple, b: tuple) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(x - ax, y - ay)
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))


def find_maps(widget) -> list:
    """Every map on view under a widget (the inspection, the tests' finger)."""
    out = []

    def walk(w) -> None:
        if not w.get_visible() or not w.get_mapped():
            return
        if isinstance(w, MeshMap):
            out.append(w)
        child = w.get_first_child()
        while child is not None:
            walk(child)
            child = child.get_next_sibling()

    walk(widget)
    return out

