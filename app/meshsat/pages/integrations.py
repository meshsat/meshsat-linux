# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > "Ham radio, TAK and Reticulum" (ui/screens/SettingsScreen.kt:1180-1623): the three
cards of MeshSat Android, in its words (model/integrations.py). The Bridge holds each setting:
the `aprs` and `tak` gateways and the `tcp_rns_0` Reticulum interface. Until a record can exist
(APRS needs a callsign, Reticulum a host) the switches wait in the app's preferences, as the
Messaging page keeps what the Bridge cannot hold yet, and the first save carries them.

A field typed into is never overwritten by a poll (Android's remember); leaving the page drops
what was not saved. A toast says "saved" only once the Bridge took it, else the Bridge's words.
Nothing here transmits by itself: KISS mode always uses an external Direwolf, and the position
beacon (APRS-IS only) goes out over the internet, never over the radio."""
from gi.repository import Gtk

from .. import api, theme
from ..model import integrations as m
from ..screen import SubScreen
from ..widgets import Chip, Field, SwitchRow, filled_button, name_widget, outlined_button, paint, text

PREFS = ("integrations_aprs_enabled", "integrations_aprs_mode", "integrations_aprs_beacon", "integrations_aprs_passcode",
         "integrations_rns_enabled", "integrations_rns_tls")
SLOW = 45.0  # a KISS dial is tried for 30 s inside the Bridge's answer
NOT_TAKEN = "The Bridge did not take the change."


def status_row() -> tuple:
    """Android's ConnectionStatusRow: the label on the left, the status on the right."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
    label = text("", "body-medium")
    label.set_hexpand(True)
    row.append(label)
    status = text("", "body-medium", theme.TEXT_MUTED, xalign=1.0)
    row.append(status)
    row.set_visible(False)
    return row, label, status


def two_to_one(left: Gtk.Widget, right: Gtk.Widget) -> Gtk.Grid:
    """Android's Row with weight(2f) and weight(1f), 8 dp apart."""
    grid = Gtk.Grid(column_spacing=theme.dp(8), column_homogeneous=True)
    left.set_hexpand(True)
    right.set_hexpand(True)
    grid.attach(left, 0, 0, 2, 1)
    grid.attach(right, 2, 0, 1, 1)
    return grid


def small_switch_row(title: str, on_change) -> SwitchRow:
    """TAK's two output rows have their title in bodySmall."""
    row = SwitchRow(title, on_change)
    for child in _children(row):
        for label in _children(child):
            if isinstance(label, Gtk.Label) and label.get_label() == title:
                label.remove_css_class("body-large")
                label.add_css_class("body-small")
    return row


def _children(widget: Gtk.Widget) -> list:
    out, child = [], widget.get_first_child()
    while child is not None:
        out.append(child)
        child = child.get_next_sibling()
    return out


def save_button(on_click, card: str) -> Gtk.Button:
    button = filled_button(m.SAVE, on_click, expand=False)
    button.add_css_class("small-text")
    button.set_halign(Gtk.Align.START)
    name_widget(button, m.SAVE, card)  # three buttons named Save: the description tells them apart
    return button


class IntegrationsScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, m.TITLE)
        self.route = "setup/integrations"
        self.aprs_record = None  # the Bridge's `aprs` gateway; None while it answers 404
        self.aprs_state = {}
        self.tak_record = None
        self.rns_iface = None
        self.dirty = set()
        self._filling = False
        self.aprs_pending = False
        self.aprs_mode = "kiss"
        self.fields = {}

        # Ham radio (APRS)
        card = self.card(m.APRS_TITLE)
        self.aprs_switch = SwitchRow(m.ENABLE_APRS, self.toggle_aprs)
        card.append(self.aprs_switch)
        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.kiss_chip = Chip(m.KISS, lambda _c: self.set_mode("kiss"))
        self.is_chip = Chip(m.IS, lambda _c: self.set_mode("is"))
        for chip in (self.kiss_chip, self.is_chip):
            chip.add_css_class("filter-chip")  # Android's FilterChip: bodySmall, selected in orange at 20 %
            chips.append(chip)
        card.append(chips)
        self.aprs_row, self.aprs_label, self.aprs_status = status_row()
        card.append(self.aprs_row)
        card.append(self.field("callsign", m.CALLSIGN, m.callsign))
        card.append(self.field("ssid", m.SSID, m.ssid, Gtk.InputPurpose.DIGITS))
        self.kiss_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.kiss_box.append(two_to_one(self.field("kiss_host", m.KISS_HOST), self.field("kiss_port", m.PORT, m.port, Gtk.InputPurpose.DIGITS, "KISS")))
        self.kiss_box.append(text(m.FREQUENCY_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        card.append(self.kiss_box)
        self.is_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.is_box.append(two_to_one(self.field("is_host", m.IS_SERVER), self.field("is_port", m.PORT, m.port, Gtk.InputPurpose.DIGITS, "APRS-IS")))
        code = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        passcode = self.field("passcode", m.PASSCODE, m.passcode_input, Gtk.InputPurpose.NUMBER)
        passcode.set_hexpand(True)
        code.append(passcode)
        auto = outlined_button(m.AUTO, self.auto_passcode)
        auto.set_valign(Gtk.Align.CENTER)
        code.append(auto)
        self.is_box.append(code)
        self.is_box.append(self.field("radius", m.RADIUS, m.radius, Gtk.InputPurpose.DIGITS))
        self.beacon = SwitchRow(m.BEACON, self.toggle_beacon)
        self.is_box.append(self.beacon)
        self.interval_field = self.field("interval", m.BEACON_INTERVAL, m.interval, Gtk.InputPurpose.DIGITS)
        self.is_box.append(self.interval_field)
        card.append(self.is_box)
        card.append(save_button(self.save_aprs, "APRS"))
        self.aprs_note = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.aprs_note)

        # TAK
        card = self.card(m.TAK_TITLE)
        self.tak_switch = SwitchRow(m.ENABLE_TAK, lambda on: self.write_tak(enabled=on))
        card.append(self.tak_switch)
        card.append(self.field("prefix", m.PREFIX, m.prefix))
        self.atak = small_switch_row(m.ATAK, lambda on: self.write_tak(atak=on))
        card.append(self.atak)
        self.export = small_switch_row(m.MQTT_EXPORT, lambda on: self.write_tak(export=on))
        card.append(self.export)
        card.append(save_button(self.save_tak, "TAK"))
        card.append(text(m.TAK_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))

        # Reticulum
        card = self.card(m.RNS_TITLE)
        self.rns_switch = SwitchRow(m.ENABLE_RNS, self.toggle_rns)
        card.append(self.rns_switch)
        self.rns_row, self.rns_label, self.rns_status = status_row()
        card.append(self.rns_row)
        card.append(two_to_one(self.field("host", m.HOST), self.field("rns_port", m.PORT, m.port, Gtk.InputPurpose.DIGITS, "RNS TCP")))
        self.tls = SwitchRow(m.TLS, self.toggle_tls)
        card.append(self.tls)
        card.append(save_button(self.save_rns, "RNS TCP"))
        card.append(text(m.RNS_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))

        self.show_mode(self.pref("integrations_aprs_mode", "kiss"))
        self.fill_empty()

    # Fields: Android's filters, and a field typed into is the person's until Save
    def field(self, key: str, label: str, keep=None, purpose=None, description: str | None = None) -> Field:
        box = Field(label, purpose=purpose)
        if description:
            name_widget(box.entry, label, description)
        self.fields[key] = box

        def changed(entry) -> None:
            value = entry.get_text()
            if keep is not None and keep(value) != value:
                entry.set_text(keep(value))
                entry.set_position(-1)
                return
            if not self._filling:
                self.dirty.add(key)

        box.entry.connect("changed", changed)
        return box

    def value(self, key: str) -> str:
        return self.fields[key].text

    def put(self, key: str, value: str) -> None:
        if key in self.dirty:
            return
        self._filling = True
        try:
            self.fields[key].set_text(value)
        finally:
            self._filling = False

    def pref(self, name: str, default=None):
        return self.app.prefs.get(name, default)

    # Data
    def on_show(self) -> None:
        self.dirty.clear()
        self.every(5, self.load)

    def load(self) -> None:
        self.fetch("/api/gateways/aprs", self.got_aprs)
        self.fetch("/api/aprs/status", self.got_aprs_status)
        self.fetch("/api/gateways/tak", self.got_tak)
        self.fetch("/api/routing/ifaces", self.got_ifaces)

    def got_aprs(self, answer: api.Answer) -> None:
        if answer.status == 404:
            self.aprs_record = None
        elif answer.ok and isinstance(answer.body, dict):
            self.aprs_record = answer.body
        else:
            return
        form = m.aprs_form(self.aprs_record, self.pref("integrations_aprs_passcode"))
        if self.aprs_record is None:
            form.update(enabled=bool(self.pref("integrations_aprs_enabled", False)), mode=self.pref("integrations_aprs_mode", "kiss"),
                        beacon=bool(self.pref("integrations_aprs_beacon", False)))
        self.aprs_switch.set_active(form["enabled"])
        self.beacon.set_active(form["beacon"])
        self.show_mode(form["mode"])
        for key in ("callsign", "ssid", "kiss_host", "kiss_port", "is_host", "is_port", "passcode", "radius", "interval"):
            self.put(key, form[key])
        self.interval_field.set_visible(form["beacon"])
        self.render_aprs_row()

    def got_aprs_status(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.aprs_state = answer.body
            self.render_aprs_row()

    def got_tak(self, answer: api.Answer) -> None:
        if answer.status == 404:
            self.tak_record = None
        elif answer.ok and isinstance(answer.body, dict):
            self.tak_record = answer.body
        else:
            return
        form = m.tak_form(self.tak_record)
        self.tak_switch.set_active(form["enabled"])
        self.atak.set_active(form["atak"])
        self.export.set_active(form["export"])
        self.put("prefix", form["prefix"])

    def got_ifaces(self, answer: api.Answer) -> None:
        if not answer.ok:
            return
        listed = answer.body if isinstance(answer.body, list) else (answer.body or {}).get("interfaces") or []
        self.rns_iface = next((i for i in listed if isinstance(i, dict) and i.get("id") == m.RNS_ID), None)
        form = m.rns_form(self.rns_iface, {"enabled": self.pref("integrations_rns_enabled"), "tls": self.pref("integrations_rns_tls")})
        self.rns_switch.set_active(form["enabled"])
        self.tls.set_active(form["tls"])
        self.put("host", form["host"])
        self.put("rns_port", form["port"])
        row = m.rns_status(self.rns_iface)
        self.rns_row.set_visible(row is not None)
        if row is not None:
            self.rns_label.set_text(row[0])
            self.rns_status.set_text(row[1])
            paint(self.rns_status, theme.GREEN if row[2] else theme.TEXT_MUTED)
            name_widget(self.rns_status, row[1], (self.rns_iface or {}).get("last_error") or None)

    def fill_empty(self) -> None:
        """Android's defaults before the Bridge has answered."""
        form = m.aprs_form(None, self.pref("integrations_aprs_passcode"))
        for key in ("ssid", "kiss_host", "kiss_port", "is_host", "is_port", "passcode", "radius", "interval"):
            self.put(key, form[key])
        self.put("prefix", m.DEFAULT_PREFIX)
        self.put("rns_port", m.DEFAULT_RNS_PORT)
        self.atak.set_active(True)
        self.export.set_active(True)
        self.interval_field.set_visible(False)

    # APRS
    def show_mode(self, mode: str) -> None:
        self.aprs_mode = mode if mode in ("kiss", "is") else "kiss"
        self.kiss_chip.set_selected(self.aprs_mode == "kiss")
        self.is_chip.set_selected(self.aprs_mode == "is")
        self.kiss_box.set_visible(self.aprs_mode == "kiss")
        self.is_box.set_visible(self.aprs_mode == "is")
        self.aprs_note.set_text(m.KISS_NOTE if self.aprs_mode == "kiss" else m.IS_NOTE)

    def render_aprs_row(self) -> None:
        row = m.aprs_status(self.aprs_record, self.aprs_state, self.aprs_pending)
        self.aprs_row.set_visible(row is not None)
        if row is not None:
            self.aprs_label.set_text(row[0])
            self.aprs_status.set_text(row[1])
            paint(self.aprs_status, theme.GREEN if row[2] else theme.TEXT_MUTED)

    def write_aprs(self, body: dict, done=None) -> None:
        self.aprs_pending = bool(body.get("enabled"))
        self.render_aprs_row()

        def answered(answer: api.Answer) -> None:
            self.aprs_pending = False
            if not answer.ok:
                self.app.toast(answer.error or NOT_TAKEN)
            elif done is not None:
                done()
            self.load()

        self.call("/api/gateways/aprs", answered, body=body, method="PUT", timeout=SLOW)

    def toggle_aprs(self, on: bool) -> None:
        if self.aprs_record is None:
            self.app.prefs.set(integrations_aprs_enabled=on)
            return
        self.write_aprs(m.aprs_flag_body(self.aprs_record, enabled=on))

    def set_mode(self, mode: str) -> None:
        self.show_mode(mode)
        if self.aprs_record is None:
            self.app.prefs.set(integrations_aprs_mode=mode)
            return
        self.write_aprs(m.aprs_flag_body(self.aprs_record, mode=mode))

    def toggle_beacon(self, on: bool) -> None:
        self.interval_field.set_visible(on)
        if self.aprs_record is None:
            self.app.prefs.set(integrations_aprs_beacon=on)
            return
        self.write_aprs(m.aprs_flag_body(self.aprs_record, position_beacon=on))

    def auto_passcode(self) -> None:
        """Android's Auto: the passcode field from the callsign field; nothing is saved."""
        call = self.value("callsign")
        if call.strip():
            self.fields["passcode"].set_text(m.passcode(call))

    def save_aprs(self) -> None:
        enabled = bool(self.aprs_record.get("enabled")) if self.aprs_record else bool(self.pref("integrations_aprs_enabled", False))
        fields = {key: self.value(key) for key in ("callsign", "ssid", "kiss_host", "kiss_port", "is_host", "is_port", "passcode", "radius", "interval")}
        fields["beacon"] = self.beacon.active
        position = self.app.state.position()
        body = m.aprs_save_body(self.aprs_record, enabled, self.aprs_mode, fields, position[:2] if position else None)

        def saved() -> None:
            self.app.toast(m.APRS_SAVED)
            typed = fields["passcode"]
            self.app.prefs.set(integrations_aprs_enabled=None, integrations_aprs_mode=None, integrations_aprs_beacon=None,
                               integrations_aprs_passcode=typed or self.pref("integrations_aprs_passcode"))
            self.dirty -= {"callsign", "ssid", "kiss_host", "kiss_port", "is_host", "is_port", "passcode", "radius", "interval"}

        self.write_aprs(body, saved)

    # TAK
    def write_tak(self, done=None, **changed) -> None:
        body = m.tak_body(self.tak_record, **changed)

        def answered(answer: api.Answer) -> None:
            if not answer.ok:
                self.app.toast(answer.error or NOT_TAKEN)
            elif done is not None:
                done()
            self.load()

        self.call("/api/gateways/tak", answered, body=body, method="PUT", timeout=SLOW)

    def save_tak(self) -> None:
        def saved() -> None:
            self.app.toast(m.TAK_SAVED)
            self.dirty.discard("prefix")

        self.write_tak(saved, prefix=self.value("prefix"))

    # Reticulum
    def write_rns(self, body: dict, done=None, create: bool = False) -> None:
        def answered(answer: api.Answer) -> None:
            if not answer.ok:
                self.app.toast(answer.error or NOT_TAKEN)
            elif done is not None:
                done()
            self.load()

        if create:
            self.call("/api/routing/ifaces", answered, body=body, method="POST", timeout=20.0)
        else:
            self.call(f"/api/routing/ifaces/{m.RNS_ID}", answered, body=body, method="PUT", timeout=20.0)

    def toggle_rns(self, on: bool) -> None:
        if self.rns_iface is None:
            self.app.prefs.set(integrations_rns_enabled=on)
            return
        self.write_rns({"enabled": on})

    def toggle_tls(self, on: bool) -> None:
        if self.rns_iface is None:
            self.app.prefs.set(integrations_rns_tls=on)
            return
        stored = self.rns_iface.get("config") or {}
        self.write_rns({"config": m.rns_config(stored.get("host") or "", str(stored.get("port") or ""), on)})

    def save_rns(self) -> None:
        config = m.rns_config(self.value("host"), self.value("rns_port"), self.tls.active)

        def saved() -> None:
            self.app.toast(m.RNS_SAVED)
            self.app.prefs.set(integrations_rns_enabled=None, integrations_rns_tls=None)
            self.dirty -= {"host", "rns_port"}

        if self.rns_iface is not None:
            self.write_rns({"config": config}, saved)
        elif config["host"]:
            self.write_rns({"type": "tcp_rns", "enabled": bool(self.pref("integrations_rns_enabled", False)), "config": config}, saved, create=True)
        else:
            self.app.toast(m.RNS_SAVED)

