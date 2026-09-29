# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Maps (ui/screens/SettingsScreen.kt:1984-2223, map/MBTilesManager.kt): the one card
"Offline maps": the world overview that is always there, the detailed maps added from files
(one of them in use), "Use my detailed map", "Add a detailed map" and the delete dialog. The
files live in the app's data folder; the settings are Android's two keys."""
import os
import threading

from gi.repository import GLib, Gtk

from .. import files, maptiles, theme
from ..layout import material_icon_button
from ..model import maps
from ..model.mbtiles import NotRaster
from ..screen import SubScreen
from ..widgets import SwitchRow, clear, confirm, name_widget, outlined_button, paint, text

CHUNK = 1 << 20


class MapsScreen(SubScreen):
    route = "setup/maps"

    def __init__(self, app):
        super().__init__(app, maps.TITLE)
        self.busy = False
        card = self.card(maps.CARD)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        card.append(self.body)
        self.fill()

    def on_show(self) -> None:
        self.fill()

    def settings(self) -> tuple:
        return bool(self.app.prefs.get("offline_map_enabled", True)), str(self.app.prefs.get("offline_map_file", "") or "")

    def fill(self) -> None:
        folder = maptiles.data_dir()
        entries = maps.listing(folder)
        enabled, chosen = self.settings()
        active = maps.active(entries, enabled, chosen)
        clear(self.body)
        self.body.append(text(maps.INTRO, "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.body.append(text(maps.INSTALLED, "title-small", theme.TEXT_SECONDARY))
        world = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        world.add_css_class("world-box")
        world.append(text(maps.WORLD, "body-medium"))
        world.append(text(maps.WORLD_TEXT, "body-small", theme.TEXT_MUTED, wrap=True))
        self.body.append(world)
        for entry in entries:
            self.body.append(self.map_row(entry, active is not None and entry.filename == active.filename))
        if any(not e.vector for e in entries):
            switch = SwitchRow(maps.USE_DETAILED, lambda on: self.use_detailed(on, entries), detail=maps.USE_DETAILED_HINT, active=active is not None)
            switch.detail.remove_css_class("body-medium")
            switch.detail.add_css_class("body-small")
            paint(switch.detail, theme.TEXT_MUTED)
            self.body.append(switch)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        add = outlined_button(maps.ADD, self.add)
        add.set_sensitive(not self.busy)
        row.append(add)
        if self.busy:
            spinner = Gtk.Spinner(spinning=True)
            spinner.set_size_request(theme.dp(20), theme.dp(20))
            row.append(spinner)
            adding = text(maps.ADDING, "body-small", theme.TEXT_MUTED)
            adding.set_valign(Gtk.Align.CENTER)
            row.append(adding)
        self.body.append(row)
        self.body.append(text(maps.ADD_HINT, "body-small", theme.TEXT_MUTED, wrap=True))

    def map_row(self, entry, in_use: bool) -> Gtk.Widget:
        """One detailed map: its radio, name, size and zooms, "In use" or the vector line, and
        the bin. A raster row makes its map the one in use; a vector row cannot be chosen."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("map-row")
        if in_use:
            row.add_css_class("active")
        use = Gtk.Button()
        use.add_css_class("flat")
        use.set_hexpand(True)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        radio = Gtk.Box()
        radio.add_css_class("radio")
        if in_use:
            radio.add_css_class("on")
        if entry.vector:
            radio.add_css_class("dimmed")
        radio.set_valign(Gtk.Align.CENTER)
        inner.append(radio)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        texts.append(text(entry.name, "body-medium", ellipsize=True))
        texts.append(text(entry.details(), "body-small", theme.TEXT_MUTED))
        if entry.vector:
            texts.append(text(maps.VECTOR, "body-small", theme.AMBER, wrap=True))
        elif in_use:
            texts.append(text(maps.IN_USE, "body-small", theme.SIGNAL_ORANGE))
        inner.append(texts)
        use.set_child(inner)
        name_widget(use, maps.use_name(entry.name))
        if entry.vector:
            use.set_sensitive(False)
        else:
            use.connect("clicked", lambda *_: self.choose(entry.filename))
        row.append(use)
        # Icons.Default.Delete, the filled bin, in TextMuted (SettingsScreen.kt:2126-2128)
        bin_ = material_icon_button("delete", lambda: self.ask_delete(entry), 24, theme.TEXT_MUTED, maps.delete_name(entry.name))
        bin_.set_valign(Gtk.Align.CENTER)
        row.append(bin_)
        return row

    def choose(self, filename: str) -> None:
        self.app.prefs.set(offline_map_file=filename, offline_map_enabled=True)
        self.fill()

    def use_detailed(self, on: bool, entries: list) -> None:
        """On: the saved file when it is still a map that shows, else the first by name. Off: the
        file is kept, so on again brings the same map back."""
        if on:
            entry = maps.turn_on(entries, self.settings()[1])
            if entry is not None:
                self.app.prefs.set(offline_map_file=entry.filename, offline_map_enabled=True)
        else:
            self.app.prefs.set(offline_map_enabled=False)
        GLib.idle_add(lambda: self.fill() or False)

    # Adding (MBTilesManager.importFile), off the main loop
    def add(self) -> None:
        files.pick_file(self.app, maps.ADD, self.picked, patterns=("*.mbtiles",))

    def picked(self, gfile) -> None:
        if gfile is None:
            return  # nothing picked: nothing happens
        self.busy = True
        self.fill()
        threading.Thread(target=self.copy, args=(gfile,), daemon=True).start()

    def copy(self, gfile) -> None:
        """The copy goes to a name of its own first and replaces a map of the same name only once
        it opens as MBTiles (Android overwrote first, so a broken file cost the map it replaced)."""
        folder = maptiles.data_dir()
        name = maps.safe_name(gfile.get_basename() or "")
        final = os.path.join(folder, name)
        partial = os.path.join(folder, f".adding-{name}")
        result = None
        try:
            os.makedirs(folder, exist_ok=True)
            stream = gfile.read(None)
            try:
                with open(partial, "wb") as out:
                    while True:
                        chunk = stream.read_bytes(CHUNK, None).get_data()
                        if not chunk:
                            break
                        out.write(chunk)
            finally:
                stream.close(None)
            vector = False
            try:
                maps.open_checked(partial).close()
            except NotRaster:
                vector = True
            except ValueError as error:
                raise ValueError(maps.invalid(str(error))) from error
            self.app.tiles.forget(final)
            os.replace(partial, final)
            result = ("vector" if vector else "added", name, None)
        except (OSError, ValueError, GLib.Error) as error:
            message = error.message if isinstance(error, GLib.Error) else str(error)
            result = ("failed", name, message)
        finally:
            if os.path.exists(partial):
                try:
                    os.remove(partial)
                except OSError:
                    pass
        GLib.idle_add(self.added, result)

    def added(self, result) -> bool:
        kind, name, message = result
        self.busy = False
        if kind == "failed":
            self.app.toast(maps.could_not_add(message))
        elif kind == "vector":
            self.app.toast(maps.ADDED_VECTOR)
        else:
            entry = next((e for e in maps.listing(maptiles.data_dir()) if e.filename == name), None)
            self.app.prefs.set(offline_map_file=name, offline_map_enabled=True)
            self.app.toast(maps.added(entry.name if entry else name))
        if self.get_mapped():
            self.fill()
        return False

    # Deleting
    def ask_delete(self, entry) -> None:
        def delete() -> None:
            path = os.path.join(maptiles.data_dir(), entry.filename)
            self.app.tiles.forget(path)
            try:
                os.remove(path)
            except OSError:
                pass
            if self.settings()[1] == entry.filename:
                self.app.prefs.set(offline_map_file="", offline_map_enabled=False)
            self.fill()
            self.app.toast(maps.deleted(entry.name))

        confirm(self.app, maps.DELETE_TITLE, maps.delete_body(entry.name), maps.DELETE_CONFIRM, delete, cancel=maps.DELETE_KEEP, danger=True)
