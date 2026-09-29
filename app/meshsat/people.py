# SPDX-License-Identifier: GPL-3.0-or-later
"""People, as ui/screens/PeersScreen.kt and ContactCards.kt: the heard line, the "People you
carry" card, then the empty state, or the sort chips and the node table with your own node in
it; a tap opens the node's sheet."""
import time

from gi.repository import Gtk

from . import api, theme
from .model import nodes as node_words
from .model import words
from .pages.cards import CardsSection
from .widgets import Chip, clear, filled_button, hscroll, name_widget, page, scroller, text

ACTIVE_S = 15 * 60
SORTS = (("last_heard", "Last heard"), ("name", "Name"), ("signal", "Signal"), ("battery", "Battery"))
WEIGHTS = (22, 9, 8, 11)  # the columns' weights 0.44, 0.18, 0.16, 0.22, in fiftieths


class PeopleScreen(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.sort = "last_heard"
        self._key = None
        column = page(spacing=0)
        title = text("People", "headline-medium")
        title.set_margin_bottom(theme.dp(4))
        column.append(title)
        self.heard = text("0 nodes heard, 0 in the last 15 min", "body-medium", theme.TEXT_SECONDARY)
        self.heard.set_margin_bottom(theme.dp(8))
        column.append(self.heard)

        # People you carry (ContactCards.kt): 16 dp at the sides and 8 dp above and below.
        carry = CardsSection(app)
        carry.set_margin_start(theme.dp(16))
        carry.set_margin_end(theme.dp(16))
        carry.set_margin_top(theme.dp(8))
        carry.set_margin_bottom(theme.dp(8))
        column.append(carry)

        # Silence is not evidence of an empty mesh: a node only shows up once it transmits.
        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.empty.set_margin_top(theme.dp(16))
        self.empty.set_margin_start(theme.dp(32))
        self.empty.set_margin_end(theme.dp(32))
        self.empty_title = text("Nobody heard yet.", "title-medium", xalign=0.5)
        self.empty.append(self.empty_title)
        self.empty_text = text("People appear here when your MeshSat node hears them on the mesh.", "body-medium", theme.TEXT_SECONDARY, xalign=0.5, wrap=True)
        self.empty_text.set_justify(Gtk.Justification.CENTER)
        self.empty.append(self.empty_text)
        self.connect_button = filled_button("Connect your node", lambda: app.open_route("setup/node"), expand=False)
        self.connect_button.set_halign(Gtk.Align.CENTER)
        self.empty.append(self.connect_button)
        column.append(self.empty)

        self.table_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sort_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        sort_row.set_margin_bottom(theme.dp(8))
        by = text("Sort by", "body-small", theme.TEXT_MUTED)
        by.set_valign(Gtk.Align.CENTER)
        sort_row.append(by)
        self.sort_chips = {}
        for key, label_text in SORTS:
            chip = Chip(label_text, lambda c, k=key: self.set_sort(k), selected=key == "last_heard")
            chip.add_css_class("people-chip")
            self.sort_chips[key] = chip
            sort_row.append(chip)
        self.table_box.append(hscroll(sort_row))
        header = table_row()
        header.add_css_class("people-head")
        for i, name in enumerate(("Node", "Signal", "Battery", "Last heard")):
            place(header, i, text(name, "label-small", theme.TEXT_MUTED, ellipsize=True))
        self.table_box.append(header)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.table_box.append(self.rows)
        column.append(self.table_box)
        self.append(scroller(column))

    def set_sort(self, key: str) -> None:
        self.sort = key
        for k, chip in self.sort_chips.items():
            chip.set_selected(k == key)
        self._key = None
        self.update(self.app.state)

    def update(self, s: api.State) -> None:
        now = time.time()
        me = (s.bridge or {}).get("node_id")
        others = s.others()
        active = sum(1 for n in others if (n.get("last_heard") or 0) > 0 and now - n["last_heard"] < ACTIVE_S)
        self.heard.set_text(f"{words.count(len(others), 'node')} heard, {active} in the last 15 min")
        if not s.nodes:
            self.empty.set_visible(True)
            self.table_box.set_visible(False)
            up = s.mesh_connected()
            self.empty_title.set_text("Your node is listening." if up else "Nobody heard yet.")
            self.empty_text.set_text("People appear here as soon as they transmit on the mesh." if up else "People appear here when your MeshSat node hears them on the mesh.")
            self.connect_button.set_visible(not up)
            self._key = None
            return
        self.empty.set_visible(False)
        self.table_box.set_visible(True)
        rows = [(n, node_words.node_signal(n, node_words.live_packet(s.packets, node_words.node_id(n)))) for n in s.nodes]
        if self.sort == "name":
            rows.sort(key=lambda r: node_words.name_order(r[0]))
        elif self.sort == "signal":
            rows.sort(key=lambda r: node_words.signal_order(r[1]))
        elif self.sort == "battery":
            rows.sort(key=lambda r: -(r[0].get("battery_level") or -1))
        else:
            rows.sort(key=lambda r: -(r[0].get("last_heard") or 0))
        # "Last heard" moves with the clock: the key holds it to the minute.
        key = tuple((node_words.node_id(n), n.get("long_name"), n.get("short_name"), n.get("battery_level"), sig["short"], sig["direct"],
                     words.ago(n.get("last_heard") or 0, now), node_words.node_id(n) == me) for n, sig in rows)
        if key == self._key:
            return
        self._key = key
        clear(self.rows)
        for n, sig in rows:
            self.rows.append(self.peer_row(n, sig, node_words.node_id(n) == me, now))

    def peer_row(self, node: dict, sig: dict, mine: bool, now: float) -> Gtk.Widget:
        """PeerRow: the dot and the name over the id, the signal, the battery, when last heard."""
        heard = node.get("last_heard") or 0
        status = theme.TEXT_PRIMARY if mine else theme.GREEN if heard and now - heard < ACTIVE_S else theme.TEXT_MUTED
        row = table_row()
        row.add_css_class("people-row")
        first = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        dot = Gtk.Box()
        dot.add_css_class("dot")
        dot.add_css_class({theme.TEXT_PRIMARY: "dot-primary", theme.GREEN: "dot-green"}.get(status, "dot-muted"))
        dot.set_valign(Gtk.Align.CENTER)
        first.append(dot)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        names.set_valign(Gtk.Align.CENTER)
        name = (node.get("long_name") or "").strip() or (node.get("short_name") or "").strip()
        if name or mine:
            names.append(text(f"{name or 'Your node'} (you)" if mine else name, "body-medium", ellipsize=True))
        names.append(text(node_words.node_id(node), "body-small", theme.TEXT_MUTED, mono=True, ellipsize=True))
        first.append(names)
        place(row, 0, first)
        direct = sig["direct"] and not mine
        place(row, 1, text("-" if mine else sig["short"], "body-small", theme.TEXT_PRIMARY if direct else theme.TEXT_MUTED, mono=direct, ellipsize=True))
        level = int(node.get("battery_level") or 0)
        colour = theme.TEXT_MUTED if level <= 0 else theme.GREEN if level > 100 else theme.AMBER if level <= 20 else theme.GREEN
        place(row, 2, text(node_words.battery_cell(level), "body-small", colour, mono=True, ellipsize=True))
        place(row, 3, text("-" if mine else words.ago(heard, now), "body-small", status, ellipsize=True))
        button = Gtk.Button()
        button.add_css_class("people-tap")
        button.set_child(row)
        label = f"{name or 'Your node'} (you)" if mine else (name or node_words.node_id(node))
        name_widget(button, label)
        button.connect("clicked", lambda *_: self.app.node_sheet(node))
        return button


def table_row() -> Gtk.Grid:
    """A row of the table: four columns by Android's weights (0.44, 0.18, 0.16, 0.22)."""
    grid = Gtk.Grid(column_homogeneous=True)
    grid.set_hexpand(True)
    return grid


def place(grid: Gtk.Grid, column: int, widget: Gtk.Widget) -> None:
    start = sum(WEIGHTS[:column])
    widget.set_hexpand(True)
    widget.set_halign(Gtk.Align.FILL)
    widget.set_valign(Gtk.Align.CENTER)
    if isinstance(widget, Gtk.Label):
        widget.set_xalign(0.0)
        widget.set_max_width_chars(1)
    grid.attach(widget, start, 0, WEIGHTS[column], 1)
