# SPDX-License-Identifier: GPL-3.0-or-later
"""Map, as ui/screens/MapScreen.kt and ui/components/MapChrome.kt: OpenStreetMap's tiles drawn
through the Android app's dark-tile matrix, the round buttons (centre on me, show everyone,
zoom), the OpenStreetMap credit, this phone as an orange dot, the nodes as diamonds with
their name, and the "Layers and nodes" panel under the map. The markers sit in a layer of
their own above the filtered tiles, so they keep their exact colours, as on Android."""
import time

import gi

from gi.repository import Gdk, Gtk

from . import api, theme
from .widgets import Filtered, ago, clear, icon, icon_button, page, scroller, spacer, text

try:
    gi.require_version("Shumate", "1.0")
    from gi.repository import Shumate
except (ValueError, ImportError):
    Shumate = None

# The tiles every MeshSat app shows (osmdroid's MAPNIK source on Android).
OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
WORLD = (20.0, 0.0, 3.0)  # where the map opens without a position, as on Android
HERE_ZOOM = 14.0
STALE_AFTER = 15 * 60


class Diamond(Gtk.DrawingArea):
    """A node on the map: a 14 dp diamond in the mesh colour, muted once the node is stale."""

    def __init__(self, stale: bool):
        super().__init__()
        size = theme.dp(14)
        self.set_content_width(size)
        self.set_content_height(size)
        self.colour = theme.TEXT_MUTED if stale else theme.MESH
        self.set_draw_func(self.draw)

    def draw(self, area, cr, width, height):
        rgba = Gdk.RGBA()
        rgba.parse(self.colour)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1.0)
        cr.move_to(width / 2, 0)
        cr.line_to(width, height / 2)
        cr.line_to(width / 2, height)
        cr.line_to(0, height / 2)
        cr.close_path()
        cr.fill_preserve()
        ink = Gdk.RGBA()
        ink.parse(theme.SPACE_BLACK)
        cr.set_source_rgba(ink.red, ink.green, ink.blue, 1.0)
        cr.set_line_width(1.5)
        cr.stroke()


class MapScreen(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.positions = []
        self.panel_open = False
        column = page(spacing=theme.dp(12))
        column.append(text("Map", "headline-medium"))

        frame = Gtk.Box()
        frame.add_css_class("map-frame")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_vexpand(True)
        frame.set_size_request(-1, theme.dp(360))
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        self.markers = None
        if Shumate is not None:
            self.map = Shumate.Map()
            self.map.set_hexpand(True)
            self.map.set_vexpand(True)
            source = Shumate.RasterRenderer.new_from_url(OSM_TILES)
            source.set_id("osm")
            source.set_name("OpenStreetMap")
            source.set_license("© OpenStreetMap contributors")
            self.map.set_map_source(source)
            self.map.add_layer(Shumate.MapLayer.new(source, self.map.get_viewport()))
            self.map.get_viewport().set_zoom_level(WORLD[2])
            self.map.center_on(WORLD[0], WORLD[1])
            overlay.set_child(Filtered(self.map, theme.DARK_TILES_MATRIX))
            # The markers: a layer on the same viewport, outside the filter, and never in the
            # way of a finger (touches go to the map underneath).
            self.markers = Shumate.MarkerLayer.new(self.map.get_viewport())
            self.markers.set_can_target(False)
            overlay.add_overlay(self.markers)
        else:
            missing = text("The map needs libshumate (gir1.2-shumate-1.0).", "body-medium", theme.TEXT_SECONDARY, xalign=0.5)
            missing.set_vexpand(True)
            overlay.set_child(missing)
        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        top.set_halign(Gtk.Align.END)
        top.set_valign(Gtk.Align.START)
        top.set_margin_top(theme.dp(12))
        top.set_margin_end(theme.dp(12))
        top.append(self.round("outlined-my-location", self.centre_on_me, "Centre on me"))
        top.append(self.round("outlined-zoom-out-map", self.show_everyone, "Show everyone on the map"))
        overlay.add_overlay(top)
        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        bottom.set_halign(Gtk.Align.END)
        bottom.set_valign(Gtk.Align.END)
        bottom.set_margin_bottom(theme.dp(12))
        bottom.set_margin_end(theme.dp(12))
        bottom.append(self.round("outlined-add", lambda: self.zoom(1), "Zoom in"))
        bottom.append(self.round("outlined-remove", lambda: self.zoom(-1), "Zoom out"))
        overlay.add_overlay(bottom)
        credit = Gtk.Label(label="© OpenStreetMap contributors")
        credit.add_css_class("map-credit")
        credit.set_halign(Gtk.Align.START)
        credit.set_valign(Gtk.Align.END)
        credit.set_margin_start(theme.dp(8))
        credit.set_margin_bottom(theme.dp(8))
        overlay.add_overlay(credit)
        frame.append(overlay)
        column.append(frame)

        # The panel under the map: a 56 dp bar that opens to the layers and the node list.
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.add_css_class("card")
        bar = Gtk.Button()
        bar.add_css_class("flat")
        bar.connect("clicked", lambda *_: self.toggle_panel())
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        row.add_css_class("panel-bar")
        layers = icon("outlined-layers", 24, theme.TEXT_SECONDARY)
        layers.set_valign(Gtk.Align.CENTER)
        row.append(layers)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text("Layers and nodes", "title-small"))
        self.summary = text("No node positions yet", "body-small", theme.TEXT_MUTED, ellipsize=True)
        texts.append(self.summary)
        row.append(texts)
        self.expand_icon = icon("outlined-expand-less", 24, theme.TEXT_SECONDARY)
        self.expand_icon.set_valign(Gtk.Align.CENTER)
        row.append(self.expand_icon)
        bar.set_child(row)
        panel.append(bar)
        self.panel_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(6))
        self.panel_body.set_margin_start(theme.dp(12))
        self.panel_body.set_margin_end(theme.dp(12))
        self.panel_body.set_margin_bottom(theme.dp(12))
        self.panel_body.set_visible(False)
        panel.append(self.panel_body)
        column.append(panel)
        self.append(scroller(column))

    def round(self, name: str, on_click, tooltip: str) -> Gtk.Button:
        button = icon_button(name, on_click, 24, theme.TEXT_PRIMARY, tooltip)
        button.remove_css_class("icon-button")
        button.add_css_class("round")
        return button

    def toggle_panel(self) -> None:
        self.panel_open = not self.panel_open
        self.panel_body.set_visible(self.panel_open)
        self.expand_icon.set_from_icon_name(f"meshsat-outlined-{'expand-more' if self.panel_open else 'expand-less'}-symbolic")

    def zoom(self, step: int) -> None:
        if Shumate is None:
            return
        viewport = self.map.get_viewport()
        viewport.set_zoom_level(max(viewport.get_min_zoom_level(), min(viewport.get_max_zoom_level(), viewport.get_zoom_level() + step)))

    def go_to(self, latitude: float, longitude: float, zoom: float) -> None:
        if Shumate is None:
            return
        viewport = self.map.get_viewport()
        viewport.set_zoom_level(max(viewport.get_zoom_level(), zoom))
        self.map.go_to(latitude, longitude)

    def centre_on_me(self) -> None:
        position = self.app.state.position()
        if Shumate is None or not position:
            self.app.toast("Waiting for a position. Allow location, or enter one under Satellite passes.")
            return
        self.go_to(position[0], position[1], HERE_ZOOM)

    def show_everyone(self) -> None:
        if Shumate is None or not self.positions:
            self.app.toast("No node with a position yet.")
            return
        lats = [p[0] for p in self.positions]
        lons = [p[1] for p in self.positions]
        if len(self.positions) == 1:
            self.go_to(lats[0], lons[0], HERE_ZOOM)
            return
        self.map.get_viewport().set_zoom_level(10)
        self.map.go_to((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)

    def update(self, s: api.State) -> None:
        me = (s.bridge or {}).get("node_id")
        nodes = [n for n in s.nodes if n.get("latitude") and n.get("longitude") and n.get("user_id") != me]
        phone = s.position()  # this phone: its own fix, the node's position, or the one typed in
        positioned = [(n["latitude"], n["longitude"]) for n in nodes] + ([(phone[0], phone[1])] if phone else [])
        first_fix = positioned and not self.positions
        self.positions = positioned
        others = nodes
        self.summary.set_text("No node positions yet" if not positioned else f"{len(others)} of {len(others)} node{'s' if len(others) != 1 else ''} shown" if others else "This phone only")
        if Shumate is not None and self.markers is not None:
            self.markers.remove_all()
            now = time.time()
            for n in ([{"latitude": phone[0], "longitude": phone[1], "mine": True}] if phone else []) + nodes:
                mine = n.get("mine", False)
                marker = Shumate.Marker()
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
                box.set_halign(Gtk.Align.CENTER)
                if mine:
                    dot = Gtk.Box()
                    dot.add_css_class("marker-me")
                    dot.set_halign(Gtk.Align.CENTER)
                    box.append(dot)
                else:
                    shape = Diamond(stale=(n.get("last_heard") or 0) < now - STALE_AFTER)
                    shape.set_halign(Gtk.Align.CENTER)
                    box.append(shape)
                    name = Gtk.Label(label=n.get("long_name") or n.get("short_name") or n.get("user_id", ""))
                    name.add_css_class("marker-label")
                    box.append(name)
                marker.set_child(box)
                marker.set_location(n["latitude"], n["longitude"])
                self.markers.add_marker(marker)
            if first_fix and phone:
                self.go_to(phone[0], phone[1], HERE_ZOOM)
        clear(self.panel_body)
        self.panel_body.append(text("Layers", "label-medium", theme.TEXT_SECONDARY))
        for title, on in (("This phone", bool(phone)), ("Nodes", True), ("Tracks from the last 24 hours", False)):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            check = Gtk.CheckButton(active=on)
            row.append(check)
            row.append(text(title, "body-large"))
            self.panel_body.append(row)
        self.panel_body.append(text("Nodes", "label-medium", theme.TEXT_SECONDARY))
        if not others:
            self.panel_body.append(text("No node has shared a position yet.", "body-medium", theme.TEXT_MUTED, wrap=True))
        for n in others:
            row = Gtk.Button()
            row.add_css_class("flat")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            inner.append(Gtk.CheckButton(active=True))
            inner.append(text(n.get("long_name") or n.get("user_id", ""), "body-large", ellipsize=True))
            inner.append(spacer())
            inner.append(text("Heard " + ago(n.get("last_heard")), "body-medium", theme.TEXT_SECONDARY))
            row.set_child(inner)
            row.connect("clicked", lambda _b, lat=n["latitude"], lon=n["longitude"]: self.go_to(lat, lon, HERE_ZOOM))
            self.panel_body.append(row)
