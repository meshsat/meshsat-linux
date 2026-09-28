# SPDX-License-Identifier: GPL-3.0-or-later
"""People, as ui/screens/PeersScreen.kt and ContactCards.kt: the heard line, the "People you
carry" card, the sort chips, the node table, the empty states, and the node sheet."""
import time

from gi.repository import Gtk

from . import api, theme
from .widgets import Card, Chip, ago, clear, filled_button, hscroll, outlined_button, page, scroller, text, text_button


class PeopleScreen(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.sort = "last_heard"
        column = page(spacing=12)
        column.append(text("People", "headline-medium"))
        self.heard = text("0 nodes heard, 0 in the last 15 min", "body-large", theme.TEXT_SECONDARY)
        column.append(self.heard)

        carry = Card(spacing=8)
        carry.set_margin_start(theme.dp(16))
        carry.set_margin_end(theme.dp(16))
        carry.append(text("People you carry", "title-medium"))
        carry.append(text("Cards swapped face to face by QR code. Read the fingerprint aloud to each other: it is what says the card is theirs.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        buttons.append(outlined_button("My card", lambda: app.toast("Your card is the Bridge's key bundle: Setup > Advanced > Certificates and keys.")))
        buttons.append(outlined_button("Scan a card", lambda: app.toast("This device has no card scanner yet. Paste a card instead.")))
        carry.append(buttons)
        carry.append(text_button("Paste a card instead", lambda: app.toast("Paste a card: not on this device yet.")))
        self.cards_empty = text("No cards yet.", "body-medium", theme.TEXT_SECONDARY)
        carry.append(self.cards_empty)
        column.append(carry)

        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.empty.set_margin_top(theme.dp(48))
        self.empty_title = text("Nobody heard yet.", "title-large", xalign=0.5)
        self.empty.append(self.empty_title)
        self.empty_text = text("People appear here when your MeshSat node hears them on the mesh.", "body-large", theme.TEXT_SECONDARY, xalign=0.5, wrap=True)
        self.empty_text.set_justify(Gtk.Justification.CENTER)
        self.empty.append(self.empty_text)
        self.connect_button = filled_button("Connect your node", lambda: app.open_lane("mesh"), expand=False)
        self.connect_button.set_halign(Gtk.Align.CENTER)
        self.connect_button.set_margin_top(theme.dp(12))
        self.empty.append(self.connect_button)
        column.append(self.empty)

        self.table_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        sort_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        sort_row.append(text("Sort by", "body-medium", theme.TEXT_SECONDARY))
        self.sort_chips = {}
        for key, label_text in (("last_heard", "Last heard"), ("name", "Name"), ("signal", "Signal"), ("battery", "Battery")):
            chip = Chip(label_text, lambda c, k=key: self.set_sort(k), selected=key == "last_heard")
            self.sort_chips[key] = chip
            sort_row.append(chip)
        self.table_box.append(hscroll(sort_row))
        header = self.row(("Node", "Signal", "Battery", "Last heard"), header=True)
        self.table_box.append(header)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.table_box.append(self.rows)
        column.append(self.table_box)
        self.append(scroller(column))

    def set_sort(self, key: str) -> None:
        self.sort = key
        for k, chip in self.sort_chips.items():
            chip.set_selected(k == key)
        self.update(self.app.state)

    def row(self, cells, header: bool = False, dot: str | None = None, node: dict | None = None) -> Gtk.Widget:
        grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        if not header:
            grid.add_css_class("card")
            grid.set_margin_top(theme.dp(0))
        grid.set_size_request(-1, theme.dp(56) if not header else theme.dp(28))
        widths = (None, theme.dp(54), theme.dp(52), theme.dp(76))
        for i, (cell, width) in enumerate(zip(cells, widths)):
            if i == 0:
                first = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
                first.set_hexpand(True)
                first.set_margin_start(theme.dp(12))
                if dot:
                    d = Gtk.Box()
                    d.add_css_class("dot")
                    d.add_css_class(f"dot-{dot}")
                    d.set_valign(Gtk.Align.CENTER)
                    first.append(d)
                names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
                names.set_valign(Gtk.Align.CENTER)
                names.append(text(cell, "title-small" if header else "body-large", theme.TEXT_SECONDARY if header else None, ellipsize=True))
                if node:
                    names.append(text(node.get("user_id", ""), "label-medium", theme.TEXT_SECONDARY, mono=True))
                first.append(names)
                grid.append(first)
            else:
                colour = theme.TEXT_SECONDARY if header else None
                if i == 2 and node:
                    level = node.get("battery_level") or 0
                    colour = theme.AMBER if 0 < level <= 20 else theme.GREEN if level else None
                label = text(cell, "title-small" if header else "body-medium", colour, mono=not header)
                label.set_size_request(width, -1)
                label.set_valign(Gtk.Align.CENTER)
                if i == 3:
                    label.set_margin_end(theme.dp(12))
                grid.append(label)
        if node:
            button = Gtk.Button()
            button.add_css_class("flat")
            button.set_child(grid)
            button.connect("clicked", lambda *_: self.app.node_sheet(node))
            return button
        return grid

    def update(self, s: api.State) -> None:
        others = s.others()
        recent = s.heard_recently(15)
        self.heard.set_text(f"{len(others)} nodes heard, {recent} in the last 15 min")
        if not others:
            self.empty.set_visible(True)
            self.table_box.set_visible(False)
            if s.mesh_connected():
                self.empty_title.set_text("Your node is listening.")
                self.connect_button.set_visible(False)
            else:
                self.empty_title.set_text("Nobody heard yet.")
                self.connect_button.set_visible(True)
            return
        self.empty.set_visible(False)
        self.table_box.set_visible(True)
        key = {"last_heard": lambda n: -(n.get("last_heard") or 0), "name": lambda n: (n.get("long_name") or "").lower(),
               "signal": lambda n: -(n.get("snr") or -999), "battery": lambda n: -(n.get("battery_level") or 0)}[self.sort]
        clear(self.rows)
        now = time.time()
        for n in sorted(others, key=key):
            heard = n.get("last_heard") or 0
            dot = "green" if heard >= now - 900 else "muted"
            signal = f"{n.get('snr'):.1f} dB" if n.get("snr") else "-"
            battery = "USB" if (n.get("battery_level") or 0) > 100 else f"{n.get('battery_level')}%" if n.get("battery_level") else "-"
            self.rows.append(self.row((n.get("long_name") or n.get("short_name") or n.get("user_id", "?"), signal, battery, ago(heard)), dot=dot, node=n))
