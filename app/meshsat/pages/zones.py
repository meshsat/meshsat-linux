# SPDX-License-Identifier: GPL-3.0-or-later
"""Zones (ui/screens/GeofenceScreen.kt): a map over the top half, where a long press places a
zone or moves the one being placed, and under it either the list (the explainer, "Add zone", the
zones, the recent alerts) or the editor of a new zone. The zones live in the Bridge
(/api/geofences, MESHSAT-1414), which checks every mesh position against them and keeps the
crossings in memory, as Android's service does; this screen reads both every 5 s."""
import time
import urllib.parse

from gi.repository import Gtk, Pango

from .. import theme
from ..mapwidget import MeshMap
from ..model import geofence, tracks
from ..screen import Screen
from ..widgets import Field, SubHeader, clear, confirm, filled_button, icon, icon_button, name_widget, page, paint, scroller, text, text_button

REFRESH_S = 5
ME_ZOOM = 15.0


class ZonesScreen(Screen):
    route = "geofence"
    title = geofence.TITLE

    def __init__(self, app):
        super().__init__(app)
        self.service = None  # None until the Bridge first answers; then whether zones work
        self.zones = []
        self.events = []
        self.first_view = False
        self.reset_draft()
        self.append(SubHeader(geofence.TITLE, app.pop))
        halves = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, homogeneous=True)
        halves.set_vexpand(True)
        box = Gtk.Box()
        box.add_css_class("map-frame")
        box.add_css_class("zones-map")
        box.set_overflow(Gtk.Overflow.HIDDEN)
        self.map = MeshMap(app, zones=True)
        self.map.on_long_press = self.long_pressed
        self.map.add_button("outlined-my-location", self.centre_on_me, geofence.CENTRE_ON_ME)
        box.append(self.map)
        halves.append(box)
        self.content = page(spacing=12)
        self.list_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.content.append(self.list_view)
        self.editor = self.build_editor()
        self.editor.set_visible(False)
        self.content.append(self.editor)
        halves.append(scroller(self.content))
        self.append(halves)
        self.build_list()
        self.fill_list()

    # The draft (GeofenceScreen.kt:154-175)
    def reset_draft(self) -> None:
        self.placing = False
        self.centre = None
        self.radius = float(geofence.DEFAULT_RADIUS)
        self.alert_on = "enter"
        self.errors = {"name": False, "centre": False, "radius": False}

    # The list: its fixed parts made once and shown or hidden; the zone rows made again when the
    # zones change; the alert lines when the alerts change, their times updated in place.
    def build_list(self) -> None:
        self.list_view.append(text(geofence.EXPLAINER, "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.no_service = text(geofence.NO_SERVICE, "body-medium", theme.AMBER, wrap=True)
        self.list_view.append(self.no_service)
        self.add_button = Gtk.Button()
        self.add_button.add_css_class("filled")
        self.add_button.add_css_class("tall")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        inner.set_halign(Gtk.Align.CENTER)
        inner.append(icon("outlined-add", 18, theme.ON_PRIMARY))
        inner.append(text(geofence.ADD, "label-large"))
        self.add_button.set_child(inner)
        name_widget(self.add_button, geofence.ADD)
        self.add_button.connect("clicked", lambda *_: self.add_zone())
        self.list_view.append(self.add_button)
        self.no_zones = text(geofence.NO_ZONES, "body-medium", theme.TEXT_MUTED)
        self.list_view.append(self.no_zones)
        self.zone_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.list_view.append(self.zone_box)
        self.alerts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        heading = text(geofence.RECENT, "title-small", theme.TEXT_SECONDARY)
        heading.set_margin_top(theme.dp(8))
        self.alerts_box.append(heading)
        self.no_alerts = text(geofence.NO_ALERTS, "body-medium", theme.TEXT_MUTED)
        self.alerts_box.append(self.no_alerts)
        self.alert_lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.alerts_box.append(self.alert_lines)
        self.list_view.append(self.alerts_box)
        self._zones_key = None
        self._events_key = None
        self.lines = []

    def fill_list(self) -> None:
        running = self.service is True
        self.no_service.set_visible(self.service is False)
        self.add_button.set_visible(running)
        self.no_zones.set_visible(running and not self.zones)
        key = tuple((z.get("id"), z.get("name"), z.get("alert_on"), z.get("message"), tuple((p.get("lat"), p.get("lon")) for p in z.get("polygon") or [])) for z in self.zones)
        if key != self._zones_key:
            self._zones_key = key
            clear(self.zone_box)
            for zone in self.zones:
                self.zone_box.append(self.zone_row(zone))
        self.zone_box.set_visible(running and bool(self.zones))
        self.alerts_box.set_visible(running and bool(self.zones or self.events))
        self.no_alerts.set_visible(not self.events)
        shown = self.events[:geofence.ALERTS_SHOWN]
        names, now = self.names(), time.time()
        key = tuple((e.get("zone_name"), e.get("node_id"), e.get("event"), e.get("timestamp")) for e in shown)
        if key != self._events_key:
            self._events_key = key
            clear(self.alert_lines)
            self.lines = []
            for record in shown:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(10))
                row.add_css_class("alert-row")
                dot = Gtk.Box()
                dot.add_css_class("dot")
                paint(dot, theme.AMBER, background=True)
                dot.set_valign(Gtk.Align.CENTER)
                row.append(dot)
                line = text(geofence.event_line(record, names, now), "body-medium", wrap=True)
                line.set_hexpand(True)
                row.append(line)
                self.lines.append((record, line))
                self.alert_lines.append(row)
        else:
            for record, line in self.lines:
                words = geofence.event_line(record, names, now)
                if line.get_text() != words:
                    line.set_text(words)

    def zone_row(self, zone: dict) -> Gtk.Widget:
        """ZoneRow: the amber dot, the name, what it alerts on and its measured radius, the note,
        and the bin; a tap shows the zone on the map."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("card")
        row.add_css_class("zone-row")
        show = Gtk.Button()
        show.add_css_class("flat")
        show.set_hexpand(True)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        dot = Gtk.Box()
        dot.add_css_class("layer-dot")
        paint(dot, theme.AMBER, background=True)
        dot.set_valign(Gtk.Align.CENTER)
        inner.append(dot)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.add_css_class("zone-texts")
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text(zone.get("name", ""), "title-small", ellipsize=True))
        texts.append(text(geofence.zone_subtitle(zone), "body-small", theme.TEXT_SECONDARY, wrap=True))
        if (zone.get("message") or "").strip():
            note = text(zone["message"].strip(), "body-small", theme.TEXT_MUTED, wrap=True)
            note.set_lines(2)
            note.set_ellipsize(Pango.EllipsizeMode.END)
            texts.append(note)
        inner.append(texts)
        show.set_child(inner)
        name_widget(show, geofence.show_name(zone.get("name", "")))
        show.connect("clicked", lambda *_: self.map.show_points(geofence.zone_points(zone), animate=True))
        row.append(show)
        bin_ = icon_button("outlined-delete", lambda: self.ask_delete(zone), 24, theme.TEXT_SECONDARY, geofence.delete_name(zone.get("name", "")))
        bin_.set_valign(Gtk.Align.CENTER)
        row.append(bin_)
        return row

    def ask_delete(self, zone: dict) -> None:
        name = zone.get("name", "")

        def delete() -> None:
            self.call(f"/api/geofences/{urllib.parse.quote(str(zone.get('id', '')), safe='')}", lambda _a: self.load(), method="DELETE")

        confirm(self.app, geofence.delete_title(name), geofence.DELETE_BODY, geofence.DELETE_CONFIRM, delete, cancel=geofence.DELETE_KEEP, danger=True)

    # The editor (ZoneEditor, GeofenceScreen.kt:557-668)
    def build_editor(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        box.append(text(geofence.NEW_ZONE, "title-medium"))
        self.centre_line = text(geofence.HINT_NO_CENTRE, "body-medium", theme.TEXT_SECONDARY, wrap=True)
        box.append(self.centre_line)
        self.name_field = Field(geofence.NAME)
        self.name_field.on_change = self.name_changed
        box.append(self.name_field)
        box.append(text(geofence.RADIUS, "title-small", theme.TEXT_SECONDARY))
        self.slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.001)
        self.slider.set_draw_value(False)
        self.slider.set_hexpand(True)
        name_widget(self.slider, geofence.RADIUS)
        self._quiet = False
        self.slider.connect("value-changed", self.slider_moved)
        box.append(self.slider)
        self.radius_field = Field(geofence.RADIUS_FIELD, purpose=Gtk.InputPurpose.DIGITS)
        self.radius_field.on_change = self.radius_typed
        box.append(self.radius_field)
        box.append(text(geofence.ALERT_WHEN, "title-small", theme.TEXT_SECONDARY))
        self.alert_rows = {}
        for key, label in geofence.ALERT_CHOICES:
            row = Gtk.Button()
            row.add_css_class("flat")
            row.add_css_class("radio-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
            dot = Gtk.Box()
            dot.add_css_class("radio")
            dot.set_valign(Gtk.Align.CENTER)
            inner.append(dot)
            inner.append(text(label, "body-large"))
            row.set_child(inner)
            name_widget(row, label)
            row.connect("clicked", lambda _b, k=key: self.set_alert(k))
            self.alert_rows[key] = (row, dot)
            box.append(row)
        self.note_field = Field(geofence.NOTE)
        box.append(self.note_field)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        save = filled_button(geofence.SAVE, self.save, expand=False)
        save.add_css_class("tall")
        buttons.append(save)
        cancel = text_button(geofence.CANCEL, self.cancel)
        cancel.add_css_class("tall")
        buttons.append(cancel)
        box.append(buttons)
        return box

    def open_editor(self) -> None:
        """The editor as a fresh draft shows it: the name and note empty, 200 m, "enters"."""
        self._quiet = True
        try:
            self.name_field.set_text("")
            self.note_field.set_text("")
            self.radius_field.set_text(str(int(self.radius)))
            self.slider.set_value(geofence.radius_to_slider(self.radius))
        finally:
            self._quiet = False
        self.set_alert(self.alert_on)
        self.show_errors()
        self.editor.set_visible(True)
        self.list_view.set_visible(False)

    def show_errors(self) -> None:
        self.name_field.set_error(geofence.NAME_ERROR if self.errors["name"] else None)
        if self.errors["radius"]:
            self.radius_field.set_error(geofence.RADIUS_ERROR)
        else:
            self.radius_field.set_helper(f"About {geofence.format_distance(self.radius * 2)} across.")
        if self.centre is not None:
            self.centre_line.set_text(geofence.CENTRE_SET)
            paint(self.centre_line, theme.TEXT_SECONDARY)
        else:
            self.centre_line.set_text(geofence.HINT_NO_CENTRE)
            paint(self.centre_line, theme.RED if self.errors["centre"] else theme.TEXT_SECONDARY)

    def name_changed(self, value: str) -> None:
        if self._quiet:
            return
        if value.strip() and self.errors["name"]:
            self.errors["name"] = False
            self.show_errors()

    def slider_moved(self, scale) -> None:
        if self._quiet:
            return
        self.radius = float(geofence.slider_to_radius(scale.get_value()))
        self.errors["radius"] = False
        self._quiet = True
        try:
            self.radius_field.set_text(str(int(self.radius)))
        finally:
            self._quiet = False
        self.show_errors()
        self.draw_draft()

    def radius_typed(self, value: str) -> None:
        if self._quiet:
            return
        digits = "".join(ch for ch in value if ch.isdigit())[:5]
        if digits != value:
            self._quiet = True
            try:
                self.radius_field.set_text(digits)
            finally:
                self._quiet = False
        good = geofence.radius_ok(digits)
        if good is not None:
            self.radius = float(good)
            self.errors["radius"] = False
            self._quiet = True
            try:
                self.slider.set_value(geofence.radius_to_slider(self.radius))
            finally:
                self._quiet = False
            self.show_errors()
            self.draw_draft()

    def set_alert(self, key: str) -> None:
        self.alert_on = key
        for k, (_row, dot) in self.alert_rows.items():
            (dot.add_css_class if k == key else dot.remove_css_class)("on")

    def start_placing(self) -> None:
        if not self.placing:
            self.placing = True
            self.open_editor()

    def add_zone(self) -> None:
        """"Add zone": placing; with the phone's position known and no centre yet, the centre is
        the phone and the map goes there at the zoom for the radius."""
        self.start_placing()
        phone = self.app.state.position()
        if phone and self.centre is None:
            self.centre = (phone[0], phone[1])
            self.map.go_to(phone[0], phone[1], geofence.zoom_for_radius(self.radius))
        self.show_errors()
        self.draw_draft()
        self.show_hint()

    def long_pressed(self, lat: float, lon: float) -> None:
        """A long press places the zone there, or moves it; only while zones work. The camera
        stays."""
        if not self.service:
            return
        self.start_placing()
        self.centre = (lat, lon)
        self.errors["centre"] = False
        self.show_errors()
        self.draw_draft()
        self.show_hint()

    def cancel(self) -> None:
        self.reset_draft()
        self.editor.set_visible(False)
        self.list_view.set_visible(True)
        self.draw_draft()
        self.show_hint()

    def save(self) -> None:
        self.errors = geofence.check(self.name_field.text, self.centre, self.radius_field.text)
        self.show_errors()
        if any(self.errors.values()) or not self.service:
            return
        zone = geofence.new_zone(self.name_field.text, self.centre, geofence.radius_ok(self.radius_field.text), self.alert_on, self.note_field.text)

        def saved(answer) -> None:
            if answer.ok:
                self.app.toast(geofence.added(zone["name"]))
                self.cancel()
                self.load()
            elif answer.status in (0, 503):
                self.service = False
                self.load()
            elif answer.error:
                self.app.toast(answer.error)

        self.call("/api/geofences", saved, body=zone)

    def draw_draft(self) -> None:
        self.map.set_draft(self.centre if self.placing else None, self.radius)

    def show_hint(self) -> None:
        if not self.service:
            self.map.set_hint(None)
        elif self.placing:
            self.map.set_hint(geofence.HINT_MOVE if self.centre is not None else geofence.HINT_NO_CENTRE)
        else:
            self.map.set_hint(geofence.HINT_IDLE)

    def centre_on_me(self) -> None:
        phone = self.app.state.position()
        if not phone:
            self.app.toast(geofence.NO_POSITION)
            return
        self.map.go_to(phone[0], phone[1], max(self.map.zoom_level(), ME_ZOOM))

    # The data: zones and alerts every 5 s, the markers at every poll
    def on_show(self) -> None:
        self.map.reload_tiles()
        self.map.refresh_note()
        self.every(REFRESH_S, self.load)
        self.update(self.app.state)

    def load(self) -> None:
        self.fetch("/api/geofences", self.got_zones)
        self.fetch("/api/geofences/events", self.got_events)

    def got_zones(self, answer) -> None:
        if answer.status == 429:
            return  # the Bridge asks to slow down: it is up, keep what is shown
        if answer.ok and isinstance(answer.body, list):
            self.service = True
            self.zones = [z for z in answer.body if isinstance(z, dict)]
        else:
            self.service = False
            self.zones = []
            if self.placing:
                self.cancel()
        self.map.set_zones(self.zones)
        if not self.first_view:
            # Once per visit: every zone in view, else the phone at zoom 15 (GeofenceScreen.kt:303-318).
            self.first_view = True
            phone = self.app.state.position()
            if self.zones:
                self.map.show_points([p for z in self.zones for p in geofence.zone_points(z)], animate=False)
            elif phone:
                self.map.go_to(phone[0], phone[1], ME_ZOOM, animate=False)
        self.show_hint()
        self.fill_list()

    def got_events(self, answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.events = [e for e in (answer.body.get("events") or []) if isinstance(e, dict)]
        elif answer.status != 429:
            self.events = []
        self.fill_list()

    def names(self) -> dict:
        out = {}
        for node in self.app.state.nodes:
            name = (node.get("long_name") or "").strip() or (node.get("short_name") or "").strip()
            if name and node.get("user_id"):
                out[node["user_id"]] = name
        return out

    def update(self, s) -> None:
        now = time.time()
        me = (s.bridge or {}).get("node_id")
        skip = {me} if me and s.node_mode() == "cover" else set()
        markers = tracks.markers(s.nodes, [], skip, now)
        self.map.set_nodes([{**m, "snippet": tracks.marker_snippet(m, now, zones=True)} for m in markers])
        self.map.set_phone(s.position(), None, None)
