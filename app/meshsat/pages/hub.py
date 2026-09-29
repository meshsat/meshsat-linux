# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Hub (ui/screens/SettingsScreen.kt:1625-1900): one card, "Hub connection". The link's
state with its dot and "Use the Hub", the provisioning claim still waiting, "Why: …" when the link
failed, "Scan the Hub's QR code", "Test the connection", the connection details for setting it up
by hand, and the closing paragraph, in MeshSat Android's words (model/hub.py).

The Bridge holds the link (MESHSAT-1417): its state and reason, the switch, the test and the
settings the form saves. As on Android the switch writes the setting and takes effect when the
link next starts; Save writes the settings and restarts the Bridge, which is what "Restart the
app to use them" amounts to here. "Reach a kit through the Hub" is not on this page: the Bridge
has no relay client to a kit (docs/PARITY.md, setup.hub.relay)."""
from gi.repository import Gtk

from .. import api, flows, system, theme
from ..layout import body_text
from ..model import hub as model
from ..model import messaging as messaging_words
from ..scan import Scanner
from ..screen import SubScreen
from ..widgets import Field, filled_button, icon, icon_button, name_widget, outlined_button, paint, text, text_button, tone_colour


class HubScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, model.TITLE)
        self.route = "setup/hub"
        self.hub = {}
        self.pinging = False
        card = self.card(model.CARD)

        # Where the link stands, and the switch for it
        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.dot = Gtk.Box()
        self.dot.add_css_class("lane-dot")
        self.dot.set_size_request(theme.dp(10), theme.dp(10))
        self.dot.set_valign(Gtk.Align.CENTER)
        status.append(self.dot)
        self.status = text("", "body-medium", wrap=True)
        self.status.set_hexpand(True)
        status.append(self.status)
        self.switch = Gtk.Switch()
        self.switch.set_valign(Gtk.Align.CENTER)
        name_widget(self.switch, model.USE)
        self._quiet = False
        self.switch.connect("state-set", self.switched)
        status.append(self.switch)
        card.append(status)

        # A provisioning claim still waiting, for when its dialog was hidden
        self.waiting = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        spinner = Gtk.Spinner(spinning=True)
        spinner.set_size_request(theme.dp(14), theme.dp(14))
        paint(spinner, theme.SIGNAL_ORANGE)
        self.waiting.append(spinner)
        self.waited = text("", "body-small", theme.TEXT_MUTED)
        self.waiting.append(self.waited)
        self.waiting.set_visible(False)
        card.append(self.waiting)

        self.why = text("", "body-small", theme.RED, wrap=True)
        self.why.set_visible(False)
        card.append(self.why)

        # The way to set it up: the Hub's QR code
        scan = filled_button(model.SCAN, self.scan)
        scan.add_css_class("tall")
        card.append(scan)
        card.append(text(model.SCAN_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))

        # Test the connection
        test_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.test_button = outlined_button(model.TEST, self.test)
        test_row.append(self.test_button)
        self.result = text("", "body-medium")
        self.result.set_valign(Gtk.Align.CENTER)
        test_row.append(self.result)
        card.append(test_row)

        # Everything the QR code fills in, for people who set it up by hand
        self.details_button = text_button(model.DETAILS, self.toggle_details)
        self.details_button.set_halign(Gtk.Align.START)
        self.details_button.add_css_class("off-white")  # Android: TextButton with OffWhite text
        card.append(self.details_button)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.details.set_visible(False)
        self.url = Field(model.URL_LABEL, model.URL_HINT)
        self.details.append(self.url)
        self.bridge_id = Field(model.BRIDGE_LABEL, model.BRIDGE_HINT)
        self.callsign = Field(model.CALLSIGN_LABEL, model.CALLSIGN_HINT)
        self.details.append(pair(self.bridge_id, self.callsign))
        self.username = Field(model.USERNAME_LABEL)
        self.password = Field(model.PASSWORD_LABEL, purpose=Gtk.InputPurpose.PASSWORD)
        self.password.entry.set_visibility(False)
        # The eye is the field's trailingIcon: a 48 dp IconButton inside the outline at its end,
        # centred on the box under the floating label's room; the typed text stops 4 dp before it
        # (the entry's own 16 dp end padding plus these 36).
        self.eye = icon_button("filled-visibility", self.toggle_password, colour=theme.TEXT_SECONDARY, tooltip=model.SHOW_PASSWORD)
        self.eye.set_halign(Gtk.Align.END)
        self.eye.set_valign(Gtk.Align.CENTER)
        self.eye.set_margin_top(self.password.entry.get_margin_top())
        self.password.box.add_overlay(self.eye)
        self.password.entry.set_margin_end(theme.dp(36))
        self.details.append(pair(self.username, self.password))
        self.interval = Field(model.INTERVAL_LABEL, purpose=Gtk.InputPurpose.DIGITS)
        self.interval.entry.connect("changed", self.only_digits)
        self.details.append(self.interval)
        # Each typed in bodyMedium, 14 sp (SettingsScreen.kt:1762-1835): Field(size=14), theme.py's
        # .field-input.text-14.
        for field in (self.url, self.bridge_id, self.callsign, self.username, self.password, self.interval):
            field.entry.add_css_class("text-14")
        save = body_text(filled_button(model.SAVE, self.save, expand=False))
        save.set_halign(Gtk.Align.START)
        self.details.append(save)
        card.append(self.details)

        card.append(text(model.CLOSING, "body-small", theme.TEXT_MUTED, wrap=True))
        self.app.provisioning.listen(self.show_claim)
        self.update(app.state)

    # The link, from every poll of the Bridge
    def update(self, s: api.State) -> None:
        self.hub = dict(s.hub or {}) if s.bridge else {}
        paint(self.dot, tone_colour(model.dot(self.hub)), background=True)
        self.status.set_text(model.status(self.hub))
        # The switch shows the Bridge's setting: until the Bridge has said it, it is not offered.
        self.switch.set_sensitive(bool(s.bridge) and isinstance(s.hub, dict))
        if self.switch.get_active() != model.enabled(self.hub):
            self._quiet = True
            try:
                self.switch.set_active(model.enabled(self.hub))
            finally:
                self._quiet = False
        why = model.why(self.hub)
        self.why.set_text(why)
        self.why.set_visible(bool(why))
        self.show_claim()

    def show_claim(self) -> None:
        claim = self.app.provisioning
        waiting = claim.state == "Waiting"
        self.waiting.set_visible(waiting)
        if waiting:
            self.waited.set_text(model.card_waited(claim.seconds()))

    def on_hide(self) -> None:
        super().on_hide()
        # Closed each time the page opens, as Android's remember{} is.
        self.details.set_visible(False)
        self.details_button.set_label(model.DETAILS)

    # "Use the Hub": the setting only, as Android's; the link follows at its next start
    def switched(self, _switch, on) -> bool:
        if self._quiet:
            return False

        def saved(answer: api.Answer) -> None:
            if not answer.ok:
                self.app.toast(answer.error or model.NOT_SAVED)
            self.app.poller.poll_now()

        self.call("/api/routing/hub", saved, body={"enabled": bool(on)}, method="PUT")
        return False

    def scan(self) -> None:
        def got(value, _how) -> None:
            flows.route_setup_code(self.app, value, self.hex_key)

        # Android's Hub scanner has no failure words (its camera activity is always there): Messaging's
        Scanner(self.app, model.SCAN, got, on_error=lambda reason: self.app.toast(messaging_words.scanner_missing(reason))).present()

    def hex_key(self, key: str) -> None:
        """A 64-hex key read here becomes the encryption key, as on Android (Setup's router)."""
        from .messaging import use_scanned_key  # noqa: PLC0415

        use_scanned_key(self.app, key)

    # Test the connection
    def test(self) -> None:
        if model.state(self.hub) != "connected":
            self.show_result(model.NOT_CONNECTED)
            return
        self.pinging = True
        self.test_button.set_sensitive(False)
        self.show_result(model.TESTING)

        def done(answer: api.Answer) -> None:
            self.pinging = False
            self.test_button.set_sensitive(True)
            self.show_result(model.ping_result(answer.status, answer.body, answer.error))

        self.call("/api/routing/hub/ping", done, method="POST", body={}, timeout=15.0)

    def show_result(self, value: str) -> None:
        self.result.set_text(value)
        paint(self.result, theme.GREEN if model.ping_green(value) else theme.TEXT_MUTED)

    # The connection details
    def toggle_details(self) -> None:
        showing = not self.details.get_visible()
        if showing:
            self.fill_form()
        self.details.set_visible(showing)
        self.details_button.set_label(model.HIDE_DETAILS if showing else model.DETAILS)

    def fill_form(self) -> None:
        values = model.form(self.hub)
        self.url.set_text(values["url"])
        self.bridge_id.set_text(values["bridge_id"])
        self.callsign.set_text(values["callsign"])
        self.username.set_text(values["username"])
        self.password.set_text("")
        self.password.entry.set_placeholder_text(model.PASSWORD_KEPT if values["has_password"] else "")
        self.interval.set_text(values["interval"])

    def toggle_password(self) -> None:
        shown = not self.password.entry.get_visibility()
        self.password.entry.set_visibility(shown)
        label = model.HIDE_PASSWORD if shown else model.SHOW_PASSWORD
        self.eye.set_child(icon("filled-visibility-off" if shown else "filled-visibility", 24, theme.TEXT_SECONDARY))
        self.eye.set_tooltip_text(label)
        name_widget(self.eye, label)

    def only_digits(self, entry) -> None:
        cleaned = model.interval_digits(entry.get_text())
        if cleaned != entry.get_text():
            entry.set_text(cleaned)
            entry.set_position(-1)

    def save(self) -> None:
        body = model.save_body(self.url.text, self.bridge_id.text, self.callsign.text, self.username.text, self.password.text, self.interval.text)

        def saved(answer: api.Answer) -> None:
            if not answer.ok:
                self.app.toast(answer.error or model.NOT_SAVED)
                return
            self.password.set_text("")
            system.privileged("systemctl", "restart", "meshsat-bridge.service")
            self.app.toast(model.SAVED)
            self.app.poller.poll_now()

        self.call("/api/routing/hub", saved, body=body, method="PUT")


def pair(left: Gtk.Widget, right: Gtk.Widget) -> Gtk.Box:
    """Two fields in one row, 8 dp apart, equal widths (Android's Row with weight(1f) each)."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
    row.append(left)
    row.append(right)
    return row

