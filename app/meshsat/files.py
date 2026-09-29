# SPDX-License-Identifier: GPL-3.0-or-later
"""A file the person picks, and a copy saved where they choose: GTK's file dialog (the
portal's on a phone), with the person choosing the place, as Android's document pickers.
Under MESHSAT_APP_TEST=1 no dialog opens: the file picked is MESHSAT_APP_PICK and a copy goes
into MESHSAT_APP_SAVE_DIR, each written to the trace, so a test drives both without a portal."""
import os

from gi.repository import Gio, GLib, Gtk

from . import system, trace


def pick(app, title: str, on_picked, patterns=("*.pem", "*.crt", "*.cer", "*.key", "*.zip")) -> None:
    """`on_picked(path, data)` with the file's bytes, or `on_picked(None, None)` when the
    person picked nothing."""
    if system.TEST:
        path = os.environ.get("MESHSAT_APP_PICK", "")
        trace.event("pick", title=title, path=path)
        if not path:
            on_picked(None, None)
            return
        try:
            with open(path, "rb") as handle:
                on_picked(path, handle.read())
        except OSError:
            on_picked(None, None)
        return
    dialog = Gtk.FileDialog(title=title, modal=True)
    if patterns:
        filters = Gio.ListStore.new(Gtk.FileFilter)
        wanted = Gtk.FileFilter(name=title)
        for pattern in patterns:
            wanted.add_pattern(pattern)
        filters.append(wanted)
        anything = Gtk.FileFilter(name="All files")
        anything.add_pattern("*")
        filters.append(anything)
        dialog.set_filters(filters)

    def done(d, result) -> None:
        try:
            file = d.open_finish(result)
        except GLib.Error:
            on_picked(None, None)
            return
        try:
            ok, data, _etag = file.load_contents(None)
        except GLib.Error:
            on_picked(None, None)
            return
        on_picked(file.get_path() or file.get_basename(), bytes(data) if ok else None)

    dialog.open(app.window, None, done)


def pick_file(app, title: str, on_picked, patterns=()) -> None:
    """`on_picked(Gio.File)` for a file the person picks, or `on_picked(None)`: the file itself,
    not its bytes (an offline map can be hundreds of megabytes; the caller copies it off the
    main loop)."""
    if system.TEST:
        # MESHSAT_APP_PICK, or the file it links to: the tests pick files by their own names.
        path = os.path.realpath(os.environ.get("MESHSAT_APP_PICK", "")) if os.environ.get("MESHSAT_APP_PICK") else ""
        trace.event("pick", title=title, path=path)
        on_picked(Gio.File.new_for_path(path) if path and os.path.exists(path) else None)
        return
    dialog = Gtk.FileDialog(title=title, modal=True)
    if patterns:
        filters = Gio.ListStore.new(Gtk.FileFilter)
        wanted = Gtk.FileFilter(name=title)
        for pattern in patterns:
            wanted.add_pattern(pattern)
        filters.append(wanted)
        anything = Gtk.FileFilter(name="All files")
        anything.add_pattern("*")
        filters.append(anything)
        dialog.set_filters(filters)

    def done(d, result) -> None:
        try:
            on_picked(d.open_finish(result))
        except GLib.Error:
            on_picked(None)

    dialog.open(app.window, None, done)


def save(app, name: str, text: str, on_saved) -> None:
    """A copy of `text` where the person chooses, first named `name`; `on_saved(True)` once
    written, `on_saved(False)` when it could not be, `on_saved(None)` when they chose nothing."""
    data = text.encode("utf-8")
    if system.TEST:
        folder = os.environ.get("MESHSAT_APP_SAVE_DIR", "")
        path = os.path.join(folder, name) if folder else ""
        trace.event("save", name=name, path=path, bytes=len(data))
        if not path:
            on_saved(None)
            return
        try:
            with open(path, "wb") as handle:
                handle.write(data)
            on_saved(True)
        except OSError:
            on_saved(False)
        return
    dialog = Gtk.FileDialog(title=name, modal=True, initial_name=name)

    def done(d, result) -> None:
        try:
            file = d.save_finish(result)
        except GLib.Error:
            on_saved(None)
            return
        try:
            file.replace_contents(data, None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
            on_saved(True)
        except GLib.Error:
            on_saved(False)

    dialog.save(app.window, None, done)
