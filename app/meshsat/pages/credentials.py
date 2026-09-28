# SPDX-License-Identifier: GPL-3.0-or-later
"""Certificates and keys (ui/screens/CredentialsScreen.kt): the certificates and keys the Bridge
keeps (its credential store, /api/credentials), imported from a PEM file here or received
through the Hub; each with its badges, fingerprint, subject, expiry and version; deleted after a
question."""
import os

from gi.repository import Gtk

from .. import api, files, theme
from ..model import credentials as model
from ..screen import SubScreen
from ..widgets import Card, clear, confirm, icon, icon_button, text, tone_colour


class CredentialsScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Certificates and keys", spacing=12)
        self.route = "credentials"
        self.credentials = []
        self._key = None
        # A button made without a label, so its accessible name is the one given here (a button
        # made with a label and given another child kept an empty name on the bus).
        self.import_button = Gtk.Button()
        self.import_button.add_css_class("filled")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        inner.append(icon("outlined-add", 16, theme.ON_PRIMARY))
        inner.append(text(model.IMPORT, "label-large"))
        self.import_button.set_child(inner)
        self.import_button.set_halign(Gtk.Align.START)
        self.import_button.connect("clicked", lambda *_: self.import_pem())
        from ..widgets import name_widget  # noqa: PLC0415

        name_widget(self.import_button, model.IMPORT)
        self.column.append(self.import_button)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.column.append(self.list)

    def on_show(self) -> None:
        self.every(15, self.load)

    def load(self) -> None:
        self.fetch("/api/credentials", self.got)

    def got(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.credentials = answer.body.get("credentials") or []
            self.render()

    def render(self) -> None:
        key = tuple((c.get("id"), c.get("name"), c.get("version"), c.get("cert_not_after")) for c in self.credentials)
        if key == self._key:
            return
        self._key = key
        clear(self.list)
        if not self.credentials:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
            empty.set_margin_top(theme.dp(48))
            empty.append(text(model.EMPTY[0], "title-medium", theme.TEXT_MUTED, xalign=0.5))
            empty.append(text(model.EMPTY[1], "body-small", theme.TEXT_MUTED, xalign=0.5))
            self.list.append(empty)
            return
        for cred in self.credentials:
            self.list.append(self.card(cred))

    def card(self, cred: dict) -> Card:
        card = Card(spacing=4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        texts.set_hexpand(True)
        texts.append(text(cred.get("name", ""), "body-medium", wrap=True))
        badges = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        for badge in model.badges(cred):
            label = text(badge, "label-medium", theme.SIGNAL_ORANGE)
            label.add_css_class("state-tag")
            label.add_css_class("tint-teal")
            badges.append(label)
        texts.append(badges)
        top.append(texts)
        top.append(icon_button("outlined-delete", lambda c=cred: self.delete_asked(c), 18, theme.RED, tooltip="Delete"))
        card.append(top)
        tone = model.expiry_tone(cred.get("cert_not_after", ""))
        for line, kind in model.lines(cred):
            if kind == "expiry":
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
                if tone in ("red", "amber"):
                    warning = icon("outlined-error-outline", 14, tone_colour(tone))
                    warning.set_valign(Gtk.Align.CENTER)
                    row.append(warning)
                row.append(text(line, "body-small", tone_colour(tone)))
                card.append(row)
            else:
                label = text(line, "body-small", theme.TEXT_MUTED, ellipsize=kind == "plain", mono=kind == "mono", wrap=kind == "mono")
                card.append(label)
        return card

    def import_pem(self) -> None:
        def picked(path, data) -> None:
            if not path or data is None:
                return
            name = os.path.basename(path) or "imported.pem"

            def uploaded(answer: api.Answer) -> None:
                if answer.ok:
                    self.app.toast(model.IMPORTED)
                    self._key = None
                    self.load()
                else:
                    self.app.toast(model.import_failed(answer.error))

            api.upload("/api/credentials/upload", {"provider": model.PROVIDER, "name": name}, "file", name, data, uploaded)

        files.pick(self.app, model.IMPORT, picked)

    def delete_asked(self, cred: dict) -> None:
        question = model.delete_dialog(cred)

        def delete() -> None:
            self.call(f"/api/credentials/{cred.get('id')}", lambda a: (self.app.toast(f"That did not work: {a.error}") if not a.ok else None, self.load()), method="DELETE")

        confirm(self.app, question["title"], question["body"], question["ok"], delete, cancel=question["cancel"], danger=True)
