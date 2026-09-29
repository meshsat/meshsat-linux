# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Advanced > Diagnostics (SettingsScreen.kt's Diagnostics sections): the links' health
scores, and the background service: whether it starts after a restart, and a restart of it
after a question. Android's "Crash reports" card is its own local telemetry server, which this
edition does not have (the Bridge is a system service with its own journal): excluded.
This edition's own row, under the service's start: "Share the Bridge on this network"
(model/share.py), off unless the person switches it on after a question."""
from gi.repository import Gtk

from .. import api, system, theme
from ..model import share
from ..screen import SubScreen
from ..widgets import confirm, outlined_button, text

BRIDGE = "meshsat-bridge.service"
FORMULA = "Health = Signal(0.3) + SuccessRate(0.3) + Latency(0.2) + Cost(0.2). Scores update in real-time based on 24h delivery history."
NO_SCORER = "Health scorer not available. Connect a transport first."
BOOT_TITLE = "Start after a phone restart"
# Android's second sentence ("Android gives it your position only once you open the app") is
# about Android: the first is true here as it is there.
BOOT_NOTE = "The gateway starts by itself after the phone restarts or the app is updated, and reconnects to your node."
RESTART_TITLE = "Restart Gateway Service"
RESTART_NOTE = "Stop and restart all transports"
RESTART_DIALOG = ("Restart Service?", "This will disconnect all transports and restart the gateway service. It should take a few seconds.")
RESTARTING = "Service restarting..."


def score_tone(score) -> str:
    if score is None:
        return "muted"
    if score >= 70:
        return "green"
    if score >= 40:
        return "amber"
    return "red"


def score_text(score) -> str:
    return f"score: {score}/100" if score is not None else "score: --"


class DiagnosticsScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Diagnostics")
        self.route = "setup/diagnostics"
        self.scores = None
        self.health = self.card("Link health")
        # SettingsScreen.kt:1091-1122: each link a row of the card's Column, 8 dp apart.
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.health.append(self.rows)
        self.formula = text(FORMULA, "body-small", theme.TEXT_MUTED, wrap=True)
        self.health.append(self.formula)
        service = self.card("Background service")
        boot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        texts.append(text(BOOT_TITLE, "body-medium"))
        texts.append(text(BOOT_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        boot.append(texts)
        self.boot = Gtk.Switch()
        self.boot.set_valign(Gtk.Align.CENTER)
        from ..widgets import name_widget  # noqa: PLC0415

        name_widget(self.boot, BOOT_TITLE)
        self._quiet = False
        self.boot.connect("state-set", self.boot_changed)
        boot.append(self.boot)
        service.append(boot)
        # The Bridge answers without a password: only this phone reaches it until the person
        # shares it (meshsat-share). The switch shows the flag, never its own last position.
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        texts.append(text(share.TITLE, "body-medium", wrap=True))
        self.share_note = text(share.LOCAL, "body-small", theme.TEXT_MUTED, wrap=True)
        texts.append(self.share_note)
        row.append(texts)
        self.share_switch = Gtk.Switch()
        self.share_switch.set_valign(Gtk.Align.CENTER)
        name_widget(self.share_switch, share.TITLE)
        self._asking = False
        self.share_switch.connect("state-set", self.share_changed)
        row.append(self.share_switch)
        service.append(row)
        restart = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        texts.append(text(RESTART_TITLE, "body-medium"))
        texts.append(text(RESTART_NOTE, "body-small", theme.TEXT_MUTED))
        restart.append(texts)
        button = outlined_button("Restart", self.restart_asked)
        button.add_css_class("red-outline")
        button.set_valign(Gtk.Align.CENTER)
        restart.append(button)
        service.append(restart)

    def on_show(self) -> None:
        self.fetch("/api/interfaces/health", self.got_scores)
        self._quiet = True
        try:
            self.boot.set_active(system.unit_enabled(BRIDGE))
        finally:
            self._quiet = False
        self.show_share()

    def update(self, s: api.State) -> None:
        self.show_share()

    def got_scores(self, answer: api.Answer) -> None:
        from ..widgets import clear, paint, tone_colour  # noqa: PLC0415
        from ..model import words  # noqa: PLC0415

        clear(self.rows)
        if not answer.ok or not isinstance(answer.body, list):
            self.rows.append(text(NO_SCORER, "body-small", theme.TEXT_MUTED, wrap=True))
            self.formula.set_visible(False)
            return
        self.formula.set_visible(True)
        for hs in answer.body:
            ch = hs.get("interface_id", "")
            # background(MeshSatSurface, RoundedCornerShape(4.dp)).padding(8.dp): the card's own
            # colour, so the row lies flat on it (tonal-box's corners and padding, not its raise).
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            row.add_css_class("tonal-box")
            paint(row, theme.SURFACE, background=True)
            name = text(ch, "body-small", theme.lane_colour(words.channel_lane(ch)) if words.channel_lane(ch) != "none" else theme.TEXT_SECONDARY)
            name.set_hexpand(True)
            row.append(name)
            score = hs.get("score")
            row.append(text(score_text(score), "body-small", tone_colour(score_tone(score))))
            self.rows.append(row)

    def boot_changed(self, switch, on) -> bool:
        if self._quiet:
            return False
        system.privileged("systemctl", "enable" if on else "disable", BRIDGE)
        return False

    def show_share(self) -> None:
        """The switch and the line under it as the system has them: meshsat-share's flag, read
        on show and at every poll. While a change runs the switch waits, insensitive, and while
        the question is open it keeps the position the person gave it."""
        busy = system.share_changing()
        self.share_switch.set_sensitive(not busy)
        if busy or self._asking:
            return
        on = system.shared_on_network()
        self._quiet = True
        try:
            self.share_switch.set_active(on)
        finally:
            self._quiet = False
        self.share_note.set_text(share.subtitle(on, system.lan_addresses() if on else [], system.bridge_port()))

    def share_changed(self, switch, on) -> bool:
        if self._quiet or bool(on) == system.shared_on_network():
            return False
        if on:
            # Opening the Bridge to the network asks first; closing it does not.
            self._asking = True
            confirm(self.app, share.QUESTION, share.QUESTION_BODY, share.SHARE, lambda: self.share_run(True),
                    cancel=share.NOT_NOW, danger=True, on_cancel=self.share_kept)
        else:
            self.share_run(False)
        return False

    def share_kept(self) -> None:
        self._asking = False
        self.show_share()

    def share_run(self, on: bool) -> None:
        self._asking = False

        def done(ok: bool) -> None:
            if not ok:
                self.app.toast(share.not_changed(on))
            self.show_share()

        system.share_on_network(on, done)
        self.show_share()

    def restart_asked(self) -> None:
        title, body = RESTART_DIALOG

        def restart() -> None:
            system.privileged("systemctl", "restart", BRIDGE)
            self.app.toast(RESTARTING)

        confirm(self.app, title, body, "Restart", restart, cancel="Cancel", danger=True)
