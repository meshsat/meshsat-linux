# SPDX-License-Identifier: GPL-3.0-or-later
"""Node log (ui/screens/NodeLogScreen.kt): the node's own log, newest at the bottom, 2000 lines
kept, Pause/Resume, Clear, Share. With the LoRa back cover the node is meshtasticd on this
phone and its log is the service's journal, followed while the page is open. A node adopted
over Bluetooth streams its log over the link (MeshSat Android's switch) once the Bridge relays
it, which comes with the Bridge's node settings (the plan's B11 with B1)."""
import threading

from gi.repository import GLib, Gtk

from .. import files, system, theme
from ..model import nodelog as model
from ..screen import SubScreen
from ..widgets import clear, outlined_button, text, tone_colour

UNIT = "meshtasticd.service"
NOT_READABLE = ("This phone's account cannot read the node's service log yet: the package adds it to the journal's readers, which takes effect at the next "
                "login.")
BLUETOOTH = "This node is over Bluetooth, and the Bridge does not relay its log yet."


class NodeLogScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Node log", spacing=8, padded=False)
        self.route = "nodelog"
        self.buffer = model.Buffer()
        self.cursor = None
        self.reading = False
        self._shown = 0
        self.column.set_margin_start(theme.dp(16))
        self.column.set_margin_end(theme.dp(16))
        self.note = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        self.note.set_margin_top(theme.dp(8))
        self.column.append(self.note)
        # The lines in their own scroller, so the page's buttons stay under the thumb.
        scroll = self.get_last_child()
        self.remove(scroll)
        self.append(scroll)
        scroll.set_vexpand(False)
        self.lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.lines.add_css_class("log-view")
        self.lines_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.lines_scroll.set_child(self.lines)
        self.lines_scroll.set_vexpand(True)
        self.lines_scroll.set_margin_start(theme.dp(16))
        self.lines_scroll.set_margin_end(theme.dp(16))
        self.append(self.lines_scroll)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        row.set_margin_start(theme.dp(16))
        row.set_margin_end(theme.dp(16))
        row.set_margin_top(theme.dp(8))
        row.set_margin_bottom(theme.dp(8))
        self.pause_button = outlined_button("Pause", self.toggle_pause)
        row.append(self.pause_button)
        row.append(outlined_button("Clear", self.clear))
        row.append(outlined_button("Share", self.share))
        self.append(row)

    def on_show(self) -> None:
        self.every(3, self.read)

    def update(self, s) -> None:
        self.note.set_text(model.COVER_NOTE if s.node_mode() == "cover" else BLUETOOTH)

    def read(self) -> None:
        if self.app.state.node_mode() != "cover" or self.reading:
            self.update(self.app.state)
            return
        self.reading = True

        def run() -> None:
            lines, cursor, why = system.journal_follow(UNIT, self.cursor)
            GLib.idle_add(lambda: self.got(lines, cursor, why) or False)

        threading.Thread(target=run, daemon=True).start()

    def got(self, lines: list, cursor, why) -> None:
        self.reading = False
        if not self.alive:
            return
        self.cursor = cursor
        if why:
            self.note.set_text(NOT_READABLE)
            return
        self.update(self.app.state)
        import time  # noqa: PLC0415

        now = time.time()
        parsed = [p for p in (model.parse_daemon(l, now) for l in lines) if p]
        if parsed:
            self.buffer.add(parsed)
            self.render()

    def render(self) -> None:
        kept = self.buffer.kept
        if len(kept) < self._shown or len(kept) - self._shown > 400 or self._shown > len(kept):
            clear(self.lines)
            self._shown = 0
            start = max(0, len(kept) - 400)  # a screenful and more; the rest is in the copy
        else:
            start = self._shown
        for line in kept[start:]:
            label = text(model.format_line(line), "log-line", tone_colour(model.tone(line)), wrap=True)
            label.set_selectable(True)
            self.lines.append(label)
        while self.lines.observe_children().get_n_items() > 400:
            self.lines.remove(self.lines.get_first_child())
        self._shown = len(kept)
        if not self.buffer.paused:
            adjustment = self.lines_scroll.get_vadjustment()
            GLib.idle_add(lambda: adjustment.set_value(adjustment.get_upper()) or False)

    def toggle_pause(self) -> None:
        if self.buffer.paused:
            self.buffer.resume()
            self.pause_button.set_label("Pause")
            self.render()
        else:
            self.buffer.pause()
            self.pause_button.set_label("Resume")

    def clear(self) -> None:
        self.buffer.clear()
        clear(self.lines)
        self._shown = 0

    def share(self) -> None:
        value = self.buffer.text()
        if not value.strip():
            self.app.toast(model.SHARE_EMPTY)
            return
        self.app.window.get_clipboard().set(value)
        files.save(self.app, model.share_name(), value + "\n", lambda ok: self.app.toast("Node log saved" if ok else "Could not save the node log. Try another place.") if ok is not None else None)
