# SPDX-License-Identifier: GPL-3.0-or-later
"""The Map tab (ui/screens/MapScreen.kt, map/MapTracks.kt, ui/components/MapChrome.kt): the
nodes as diamonds with their names, this phone as an orange dot with its accuracy circle, the
tracks of the last 24 hours as dashed sand lines, the round buttons, the note in the corner,
and the "Layers and nodes" panel under the map. Built once and kept for the app's life, as on
Android: its layers, hidden nodes and camera last until the app closes. Tracks are read from
the Bridge (GET /api/positions) when the tab comes on view and every 30 s while it stays."""
import time
import urllib.parse

from gi.repository import GLib, Gtk

from . import api, theme
from .mapwidget import MeshMap
from .model import tracks
from .screen import Screen
from .widgets import CheckRow, clear, icon, name_widget, paint, scroller, text, text_button

FOCUS_ZOOM = 14.0  # a node from the panel or from People: zoom max(current, 14)
ME_ZOOM = 15.0  # Centre on me: zoom max(current, 15)
FIRST_FIX_ZOOM = 14.0


class MapScreen(Screen):
    route = "map"

    def __init__(self, app):
        super().__init__(app)
        # The layers, all on at first; the nodes hidden one by one (the hidden ones are kept, so a
        # node heard later is on the map by itself).
        self.show_phone = True
        self.show_nodes = True
        self.show_tracks = True
        self.hidden = set()
        self.rows = []  # the positions of the last 24 hours, newest first
        self.markers = []
        self.labels = {}
        self.fitted = False  # the first view with node positions, once in the app's life
        self.fixed = False  # before that, the first fix of the phone, once
        self.focus_id = None  # MapFocus: a node People asked to be shown
        self.panel_open = False
        self._panel_key = None
        self._limit = 0

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        column.add_css_class("map-page")
        column.set_vexpand(True)
        column.append(text(tracks.MAP, "headline-medium"))
        self.area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.area.set_vexpand(True)
        frame = Gtk.Box()
        frame.add_css_class("map-frame")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_vexpand(True)
        self.map = MeshMap(app)
        self.map.add_button("outlined-my-location", self.centre_on_me, tracks.CENTRE_ON_ME)
        self.map.add_button("outlined-zoom-out-map", self.show_everyone, tracks.SHOW_EVERYONE)
        frame.append(self.map)
        self.area.append(frame)
        self.area.append(self.build_panel())
        column.append(self.area)
        self.append(column)

    # The panel (MapScreen.kt:418-620)
    def build_panel(self) -> Gtk.Widget:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.add_css_class("card")
        self.bar = Gtk.Button()
        self.bar.add_css_class("flat")
        self.bar.connect("clicked", lambda *_: self.toggle_panel())
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        row.add_css_class("panel-bar")
        layers = icon("outlined-layers", 24, theme.TEXT_SECONDARY)
        layers.set_valign(Gtk.Align.CENTER)
        row.append(layers)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text(tracks.PANEL, "title-small"))
        self.summary = text(tracks.NO_NODE_POSITIONS, "body-small", theme.TEXT_MUTED, ellipsize=True)
        texts.append(self.summary)
        row.append(texts)
        self.chevron = icon("outlined-expand-less", 24, theme.TEXT_SECONDARY)
        self.chevron.set_valign(Gtk.Align.CENTER)
        row.append(self.chevron)
        self.bar.set_child(row)
        name_widget(self.bar, tracks.OPEN_PANEL)
        panel.append(self.bar)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        divider = Gtk.Box()
        divider.add_css_class("divider")
        self.body.append(divider)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.list.set_margin_bottom(theme.dp(8))
        self.scroll = scroller(self.list)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_vexpand(False)
        self.body.append(self.scroll)
        self.body.set_visible(False)
        panel.append(self.body)
        # The layer rows are made once: a tap never rebuilds the row under the finger.
        self.layer_rows = {}
        for key, title, dot in (("show_phone", tracks.THIS_PHONE, theme.SIGNAL_ORANGE), ("show_nodes", tracks.NODES, theme.MESH),
                                ("show_tracks", tracks.TRACKS, theme.MESH)):
            self.layer_rows[key] = CheckRow(title, lambda on, k=key: self.set_layer(k, on), active=True, dot=dot, style="body-medium")
        return panel

    def toggle_panel(self) -> None:
        self.panel_open = not self.panel_open
        self.body.set_visible(self.panel_open)
        self.chevron.set_from_icon_name(f"meshsat-outlined-{'expand-more' if self.panel_open else 'expand-less'}-symbolic")
        name_widget(self.bar, tracks.CLOSE_PANEL if self.panel_open else tracks.OPEN_PANEL)
        self.limit_list()
        self.fill_panel(force=True)

    def limit_list(self) -> None:
        """The list is at most half the map area's height (MapScreen.kt:353), and never so tall
        that the map's two columns of round buttons meet (a 360 px phone's map area is short)."""
        height = self.area.get_height()
        limit = max(theme.dp(120), min(height // 2, height - theme.dp(56 + 8 + 250)))
        if limit != self._limit:
            self._limit = limit
            self.scroll.set_max_content_height(limit)

    def fill_panel(self, force: bool = False) -> None:
        s = self.app.state
        phone = s.position()
        # The rows are made again only when the nodes or their names change; the heard lines and
        # the stale colour change in place, so a row under a finger stays where it is.
        key = (tuple((m["id"], m["label"]) for m in self.markers), tracks.phone_line(phone[0], phone[1], self.accuracy()) if phone else None)
        if not force and key == self._panel_key:
            self.sync_checks()
            self.refresh_rows()
            return
        self._panel_key = key
        if not self.panel_open:
            return
        for row in self.layer_rows.values():
            if row.get_parent() is not None:
                row.get_parent().remove(row)
        clear(self.list)
        heading = text(tracks.LAYERS, "title-small", theme.TEXT_SECONDARY)
        heading.add_css_class("panel-heading")
        self.list.append(heading)
        for row in self.layer_rows.values():
            row.add_css_class("layer-row")
            self.list.append(row)
        if phone:
            me = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
            me.add_css_class("panel-item")
            me.append(text(tracks.THIS_PHONE, "body-medium"))
            me.append(text(tracks.phone_line(phone[0], phone[1], self.accuracy()), "body-small", theme.TEXT_MUTED, wrap=True))
            self.list.append(me)
        nodes_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        nodes_row.add_css_class("panel-heading-row")
        nodes_heading = text(tracks.NODES, "title-small", theme.TEXT_SECONDARY)
        nodes_heading.set_hexpand(True)
        nodes_heading.set_valign(Gtk.Align.CENTER)
        nodes_row.append(nodes_heading)
        if self.markers:
            nodes_row.append(text_button(tracks.SHOW_ALL, self.show_all))
            nodes_row.append(text_button(tracks.HIDE_ALL, self.hide_all))
        self.list.append(nodes_row)
        if not self.markers:
            empty = text(tracks.EMPTY_NODES, "body-medium", theme.TEXT_SECONDARY, wrap=True)
            empty.add_css_class("panel-item")
            self.list.append(empty)
        now = time.time()
        self.node_checks = {}
        self.node_lines = {}
        for m in self.markers:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            row.add_css_class("node-row")
            check = CheckRow("", lambda on, i=m["id"]: self.set_hidden(i, not on), active=m["id"] not in self.hidden)
            name_widget(check, tracks.show_label(m["label"]))
            check.set_valign(Gtk.Align.CENTER)
            self.node_checks[m["id"]] = check
            row.append(check)
            go = Gtk.Button()
            go.add_css_class("flat")
            go.set_hexpand(True)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
            inner.set_valign(Gtk.Align.CENTER)
            name = text(m["label"], "body-medium", theme.TEXT_SECONDARY if m["stale"] else theme.TEXT_PRIMARY, ellipsize=True)
            inner.append(name)
            heard = text(tracks.heard(m["heard"], now), "body-small", theme.TEXT_MUTED, ellipsize=True)
            inner.append(heard)
            self.node_lines[m["id"]] = (name, heard)
            go.set_child(inner)
            name_widget(go, tracks.centre_label(m["label"]))
            go.connect("clicked", lambda _b, i=m["id"]: self.centre_on(i))
            row.append(go)
            self.list.append(row)

    def refresh_rows(self) -> None:
        now = time.time()
        for m in self.markers:
            lines = getattr(self, "node_lines", {}).get(m["id"])
            if lines is not None:
                paint(lines[0], theme.TEXT_SECONDARY if m["stale"] else theme.TEXT_PRIMARY)
                words = tracks.heard(m["heard"], now)
                if lines[1].get_text() != words:
                    lines[1].set_text(words)

    def sync_checks(self) -> None:
        for key, row in self.layer_rows.items():
            row.set_checked(getattr(self, key))
        for node_id, check in getattr(self, "node_checks", {}).items():
            check.set_checked(node_id not in self.hidden)

    # What the panel and the buttons do
    def set_layer(self, key: str, on: bool) -> None:
        setattr(self, key, on)
        self.layer_rows[key].set_checked(on)
        self.redraw()

    def set_hidden(self, node_id: str, hidden: bool) -> None:
        (self.hidden.add if hidden else self.hidden.discard)(node_id)
        self.redraw()

    def show_all(self) -> None:
        self.hidden.clear()
        self.sync_checks()
        self.redraw()

    def hide_all(self) -> None:
        self.hidden = {m["id"] for m in self.markers}
        self.sync_checks()
        self.redraw()

    def centre_on(self, node_id: str) -> None:
        """A node row, or People's "Show on map": the node back on the map, the Nodes layer on,
        and the map on it at zoom max(current, 14)."""
        marker = next((m for m in self.markers if m["id"] == node_id), None)
        if marker is None:
            self.app.toast(tracks.NO_NODE_POSITION)
            return
        self.hidden.discard(node_id)
        self.show_nodes = True
        self.sync_checks()
        self.redraw()
        self.map.go_to(marker["lat"], marker["lon"], max(self.map.zoom_level(), FOCUS_ZOOM))

    def centre_on_me(self) -> None:
        phone = self.app.state.position()
        if not phone:
            self.app.toast(tracks.NO_POSITION)
            return
        self.set_layer("show_phone", True)
        self.map.go_to(phone[0], phone[1], max(self.map.zoom_level(), ME_ZOOM))

    def show_everyone(self) -> None:
        phone = self.app.state.position()
        points = [(m["lat"], m["lon"]) for m in self.shown()] + ([(phone[0], phone[1])] if phone and self.show_phone else [])
        if not points:
            self.app.toast(tracks.NO_POSITIONS)
            return
        self.map.show_points(points, animate=True)

    def focus(self, node_id: str) -> None:
        """MapFocus.show: centre on the node once the positions are in (they are: the poll has
        the node list), then forget the request."""
        self.focus_id = node_id
        GLib.idle_add(self.apply_focus)

    def apply_focus(self) -> bool:
        node_id, self.focus_id = self.focus_id, None
        if node_id is not None:
            self.update(self.app.state)
            self.centre_on(node_id)
        return False

    # The data
    def on_show(self) -> None:
        self.map.reload_tiles()  # the detailed map may have changed in Setup > Maps
        self.map.refresh_note()
        self.every(tracks.RELOAD_S, self.load_tracks)
        self.update(self.app.state)

    def load_tracks(self) -> None:
        path = f"/api/positions?since={urllib.parse.quote(tracks.since_param())}&limit={tracks.LIMIT}"
        self.fetch(path, self.got_tracks)

    def got_tracks(self, answer) -> None:
        if not answer.ok or not isinstance(answer.body, dict):
            return  # MapTracks: an error keeps the tracks there are
        self.rows = [r for r in (answer.body.get("positions") or []) if isinstance(r, dict) and r.get("latitude") is not None]
        self.update(self.app.state)

    def skip(self, s: api.State) -> set:
        """The node that is this phone: in cover mode the node is the phone's own radio, and the
        phone is drawn as the orange dot already. A node over Bluetooth is a device of its own."""
        me = (s.bridge or {}).get("node_id")
        return {me} if me and s.node_mode() == "cover" else set()

    def accuracy(self):
        s = self.app.state
        position = s.position()
        if position and s.phone and position[2] in ("GPS", "Network"):
            return s.phone[2]
        return None

    def shown(self) -> list:
        return [m for m in self.markers if m["id"] not in self.hidden] if self.show_nodes else []

    def update(self, s: api.State) -> None:
        now = time.time()
        skip = self.skip(s)
        self.markers = tracks.markers(s.nodes, self.rows, skip, now)
        self.labels = {m["id"]: m["label"] for m in self.markers}
        phone = s.position()
        # The camera (MapScreen.kt:285-304): the first node positions fit everyone, once; before
        # them, the phone's first fix, once.
        if not self.fitted and self.markers:
            self.fitted = self.fixed = True
            self.map.show_points([(m["lat"], m["lon"]) for m in self.markers] + ([(phone[0], phone[1])] if phone else []), animate=False)
        elif not self.fixed and phone:
            self.fixed = True
            self.map.go_to(phone[0], phone[1], FIRST_FIX_ZOOM, animate=False)
        self.redraw()
        if self.panel_open:
            self.limit_list()
        self.fill_panel()

    def redraw(self) -> None:
        s = self.app.state
        now = time.time()
        shown = self.shown()
        self.map.set_nodes([{**m, "snippet": tracks.marker_snippet(m, now)} for m in shown])
        latest = {m["id"]: (m["lat"], m["lon"]) for m in shown}
        skip = self.skip(s)
        paths = tracks.group([r for r in self.rows if r.get("node_id") not in skip], self.hidden, latest) if self.show_tracks else {}
        self.map.set_tracks(paths, {k: tracks.track_title(self.labels.get(k, k)) for k in paths})
        phone = s.position() if self.show_phone else None
        accuracy = self.accuracy()
        self.map.set_phone(phone, accuracy, tracks.accuracy(accuracy))
        total = len(self.markers)
        self.summary.set_text(tracks.summary(len(shown), total))

