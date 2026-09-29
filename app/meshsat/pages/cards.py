# SPDX-License-Identifier: GPL-3.0-or-later
"""People you carry (ui/screens/ContactCards.kt): the section on the People tab with My card, Scan a
card and Paste a card instead, the cards kept, and their dialogs. This phone's card comes from
the Bridge, signed by its routing identity (GET /api/contacts/card, MESHSAT-1416); the cards of
others are checked here and kept in cards.json, on this phone only, as Android keeps them."""
import os
import time

from gi.repository import Gtk

from .. import api, store, theme
from ..model import cards
from ..qrview import QRView
from ..scan import CAMERA, Scanner
from ..widgets import Card, Field, Sheet, clear, outlined_button, text, text_button


def cards_path() -> str:
    return os.path.join(store.config_dir(), "meshsat", "cards.json")


def load() -> list:
    rows = store.read_json(cards_path(), [])
    return [r for r in rows if isinstance(r, dict) and r.get("fingerprint")] if isinstance(rows, list) else []


def save(rows: list) -> None:
    store.write_json(cards_path(), rows)


class CardsSection(Card):
    """The card of ContactCards.kt:84-152, a Column with no spacing of its own: the title, the
    description 4 dp under it and 12 dp over the buttons, My card and Scan a card side by side,
    Paste a card instead right under them, then "No cards yet." 12 dp lower or the cards, each
    12 dp under the one before (theme.py's .card-row), nothing under an empty list. Material
    keeps a 48 dp touch height round its 40 dp buttons: the row of outlined buttons takes 4 dp
    above and below, the text buttons are 48 dp tall with their words in the middle."""

    def __init__(self, app):
        super().__init__(spacing=0)
        self.app = app
        self.add_css_class("cards-section")
        self.append(text(cards.TITLE, "title-medium"))
        description = text(cards.DESCRIPTION, "body-small", theme.TEXT_MUTED, wrap=True)
        description.set_margin_top(theme.dp(4))
        description.set_margin_bottom(theme.dp(12))
        self.append(description)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        buttons.set_margin_top(theme.dp(4))
        buttons.set_margin_bottom(theme.dp(4))
        buttons.append(outlined_button(cards.MY_CARD, self.my_card))
        buttons.append(outlined_button(cards.SCAN, self.scan))
        self.append(buttons)
        paste = text_button(cards.PASTE, self.paste)
        paste.set_size_request(-1, theme.dp(48))
        paste.set_halign(Gtk.Align.START)
        self.append(paste)
        self.empty = text(cards.NO_CARDS, "body-small", theme.TEXT_MUTED)
        self.empty.set_margin_top(theme.dp(12))
        self.append(self.empty)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self.rows)
        self.fill()

    # The list (ContactCards.kt:122-150)
    def fill(self) -> None:
        rows = cards.ordered(load())
        self.empty.set_visible(not rows)
        self.rows.set_visible(bool(rows))
        clear(self.rows)
        for card in rows:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            box.add_css_class("card-row")
            box.append(text(card.get("name", ""), "body-large", wrap=True))
            box.append(text(card.get("fingerprint", ""), "body-small", theme.TEXT_MUTED, mono=True))
            box.append(text(cards.row_line(card), "body-small", theme.TEXT_MUTED, wrap=True))
            forget = text_button(cards.FORGET, lambda fp=card["fingerprint"]: self.forget(fp))
            forget.set_size_request(-1, theme.dp(48))
            forget.set_halign(Gtk.Align.START)
            box.append(forget)
            self.rows.append(box)

    def forget(self, fp: str) -> None:
        save(cards.forget(load(), fp))
        self.fill()

    # Reading a card: one function, three errors
    def read(self, value: str, trust: str) -> None:
        result, card = cards.decode(value or "")
        if result != "Ok":
            self.app.toast(cards.verdict(result))
            return
        AddDialog(self.app, card, trust, self.added).present()

    def added(self, card: dict, trust: str) -> None:
        save(cards.upsert(load(), cards.record(card, trust, int(time.time() * 1000))))
        self.fill()

    def scan(self) -> None:
        def got(value, how) -> None:
            if value and value.strip():
                self.read(value, cards.SCANNED if how == CAMERA else cards.IMPORTED)

        Scanner(self.app, cards.SCAN_PROMPT, got, on_error=lambda reason: self.app.toast(cards.no_scanner(reason))).present()

    def paste(self) -> None:
        PasteDialog(self.app, lambda value: self.read(value, cards.IMPORTED)).present()

    def my_card(self) -> None:
        MyCardDialog(self.app).present()


class PasteDialog(Sheet):
    """Paste a card (ContactCards.kt:157-187): its text starts empty every time."""

    def __init__(self, app, on_read):
        super().__init__(app, cards.PASTE_TITLE)
        self.body.append(text(cards.PASTE_TEXT, "body-small", theme.TEXT_MUTED, wrap=True))
        self.field = Field(cards.PASTE_LABEL)
        self.body.append(self.field)
        self.button(cards.CANCEL, self.close)
        self.button(cards.READ_IT, lambda: (self.close(), on_read(self.field.text)))


class AddDialog(Sheet):
    """Add {name}? (ContactCards.kt:189-237), for every card that reads, this phone's own and a
    key already kept included."""

    def __init__(self, app, card: dict, trust: str, on_add):
        super().__init__(app, cards.add_title(card["name"]))
        self.body.append(text(cards.ADD_CHECK, "body-small", theme.TEXT_MUTED, wrap=True))
        fp = text(cards.fingerprint(card["signing_pub"]), "title-medium", mono=True)
        fp.add_css_class("card-fingerprint")
        self.body.append(fp)
        if card["mesh_node_id"].strip():
            self.body.append(text(cards.mesh_line(card["mesh_node_id"]), "body-small", theme.TEXT_MUTED))
        if card["bridge_id"].strip():
            self.body.append(text(cards.hub_line(card["bridge_id"]), "body-small", theme.TEXT_MUTED))
        self.body.append(text(cards.ADD_SCANNED if trust == cards.SCANNED else cards.ADD_IMPORTED, "body-small", theme.TEXT_MUTED))
        self.button(cards.CANCEL, self.close)
        self.button(cards.ADD, lambda: (on_add(card, trust), self.close()), kind="filled")


class MyCardDialog(Sheet):
    """My card (ContactCards.kt:240-319): the card the Bridge signs, as a QR code with the
    fingerprint to read aloud; Copy puts the text on the clipboard."""

    def __init__(self, app):
        super().__init__(app, cards.MY_CARD)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.body.append(self.content)
        self.copy = self.button(cards.COPY, self.copy_card)
        self.copy.set_visible(False)
        self.button(cards.DONE, self.close, kind="filled")
        self.value = ""
        api.fetch("/api/contacts/card", self.got)

    def got(self, answer) -> None:
        body = answer.body if isinstance(answer.body, dict) else {}
        if not answer.ok or not body.get("text"):
            self.content.append(text(cards.NO_KEY, "body-medium", wrap=True))
            return
        self.value = body["text"]
        self.content.append(QRView(self.value, 260, cards.QR_NAME))
        fp = text(body.get("fingerprint", ""), "my-card-fingerprint", mono=True, xalign=0.5)
        self.content.append(fp)
        self.content.append(text(cards.READ_ALOUD, "body-small", theme.TEXT_MUTED, xalign=0.5, wrap=True))
        self.copy.set_visible(True)

    def copy_card(self) -> None:
        self.app.window.get_clipboard().set(self.value)
        self.app.toast(cards.COPIED)

