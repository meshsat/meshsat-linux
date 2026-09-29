# SPDX-License-Identifier: GPL-3.0-or-later
"""MeshSat's two Phosh plugins as Phosh loads them, each in a GTK 3 process of its own on the
test session: this tier's session runs a headless phoc and no Phosh (and Phosh scans its plugins
only at its own start). The host registers the plugin's extension point, loads the installed GIO
module from Phosh's plugin directory (/usr/lib/<triplet>/phosh/plugins) as Phosh's plugin loader
does, makes the plugin's widget and shows it in a window of its own.

The lock-screen widget needs nothing of Phosh. The quick-settings tile subclasses Phosh's
PhoshQuickSetting and makes a PhoshStatusIcon, both looked up by name when the module loads: the
host gives it stand-ins with the properties and the signal of Phosh 0.46's own (src/quick-setting.c:
a GtkBox with "active", "status-icon" and "clicked"; src/status-icon.c: a GtkBin with "icon-name",
"icon-size" and "info"), or, with types "libphosh", Phosh's own types from libphosh-0.45.so.0
(Debian 13's libphosh-0.45-0, built from the same phosh source as the shell). The plugins read
net.meshsat.Status from the notifier on the same session bus, as they do inside Phosh.

The case side, PluginHost, starts `python3 phosh_host.py <lockscreen|quick-setting> <module>
<stand-in|libphosh>` and asks one JSON line at a time on stdin/stdout: "state", "click" (a tap on
the tile), "quit".

Installed as tests/e2e/driver/phosh_host.py by wip-100/patch-100-outside.py."""
import glob
import json
import os
import select
import subprocess
import sys
import time

# kind -> (Phosh's extension point, the plugin's id: its .plugin file and its extension's name)
KINDS = {"lockscreen": ("phosh-lockscreen-widget", "meshsat-lockscreen"),
         "quick-setting": ("phosh-quick-setting-widget", "meshsat-quick-setting")}
PLUGIN_DIRS = "/usr/lib/*/phosh/plugins"
LIBPHOSH = "libphosh-0.45.so.0"


def plugin_dir() -> str | None:
    """Where Phosh finds the installed plugins; MESHSAT_E2E_PHOSH_PLUGINS names a folder of
    freshly built ones instead (phosh-plugins/build.sh's output)."""
    override = os.environ.get("MESHSAT_E2E_PHOSH_PLUGINS", "")
    if override:
        return override
    for folder in sorted(glob.glob(PLUGIN_DIRS)):
        if glob.glob(os.path.join(folder, "libphosh-plugin-meshsat-*.so")):
            return folder
    return None


def module_path(kind: str) -> str | None:
    folder = plugin_dir()
    return os.path.join(folder, f"libphosh-plugin-meshsat-{kind}.so") if folder else None


class PluginHost:
    """One plugin in its GTK 3 host, for a case: `state()`, `wait(check)`, `click()`, `stop()`."""

    def __init__(self, kind: str, work: str, types: str = "stand-in", timeout: float = 40.0):
        from . import HarnessError  # noqa: PLC0415

        self.kind = kind
        so = module_path(kind)
        if not so or not os.path.exists(so):
            raise AssertionError(f"no {kind} plugin installed where Phosh looks for it ({PLUGIN_DIRS})")
        env = dict(os.environ)
        # Nothing of the person's settings is read or written; the host is a Wayland client of
        # the test session's phoc.
        env.update({"GSETTINGS_BACKEND": "memory", "GDK_BACKEND": "wayland"})
        self.stderr_path = os.path.join(work, f"phosh-host-{kind}.stderr")
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), kind, so, types], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(self.stderr_path, "w", encoding="utf-8"), env=env, bufsize=0, cwd=work)
        self._buffer = b""
        try:
            hello = self._read(timeout)
        except HarnessError:
            self.stop()
            raise
        if hello.get("error"):
            self.stop()
            raise (HarnessError if hello.get("class") == "harness" else AssertionError)(f"the {kind} plugin: {hello['error']}")
        self.hello = hello

    def _read(self, timeout: float) -> dict:
        from . import HarnessError  # noqa: PLC0415

        deadline = time.time() + timeout
        fd = self.proc.stdout.fileno()
        while b"\n" not in self._buffer:
            left = deadline - time.time()
            if left <= 0:
                raise HarnessError(f"the {self.kind} host said nothing for {timeout:.0f} s; its stderr: {self.stderr()[-800:]}")
            ready, _, _ = select.select([fd], [], [], left)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    raise HarnessError(f"the {self.kind} host ended; its stderr: {self.stderr()[-800:]}")
                self._buffer += chunk
        line, self._buffer = self._buffer.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def ask(self, command: str, timeout: float = 10.0) -> dict:
        self.proc.stdin.write((command + "\n").encode())
        return self._read(timeout)

    def state(self) -> dict:
        return self.ask("state")

    def wait(self, check, timeout: float = 20.0, what: str = "") -> dict:
        """Until `check(state)` holds; the state. The notifier polls the Bridge every 5 s."""
        deadline = time.time() + timeout
        state = {}
        while time.time() < deadline:
            state = self.state()
            if check(state):
                return state
            time.sleep(0.4)
        raise AssertionError(f"the {self.kind} never showed {what or 'what was asked'}; it shows {json.dumps(state)[:700]}")

    def click(self) -> dict:
        return self.ask("click")

    def stderr(self) -> str:
        try:
            with open(self.stderr_path, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return ""

    def stop(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"quit\n")
            except OSError:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


# ── The host itself: run as a script, in GTK 3 ──────────────────────────────────────────────────
def say(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


STAND_INS = []  # the stand-in classes, kept for the life of the host


def stand_ins(GObject, Gtk) -> None:
    """Phosh 0.46's PhoshStatusIcon and PhoshQuickSetting as far as the tile uses them (their
    property names and types, the "clicked" signal), drawn plainly so a capture shows what the
    tile says: the icon and the info beside it."""

    class StatusIcon(Gtk.Bin):
        __gtype_name__ = "PhoshStatusIcon"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._icon_name, self._info, self._size = "", "", 3
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            self._image, self._label = Gtk.Image(), Gtk.Label()
            box.pack_start(self._image, False, False, 0)
            box.pack_start(self._label, False, False, 0)
            box.show_all()
            self.add(box)

        @GObject.Property(type=str, default="")
        def icon_name(self):
            return getattr(self, "_icon_name", "")

        @icon_name.setter
        def icon_name(self, value):
            self._icon_name = value or ""
            if hasattr(self, "_image"):
                self._image.set_from_icon_name(self._icon_name, Gtk.IconSize.LARGE_TOOLBAR)

        @GObject.Property(type=str, default="")
        def info(self):
            return getattr(self, "_info", "")

        @info.setter
        def info(self, value):
            self._info = value or ""
            if hasattr(self, "_label"):
                self._label.set_text(self._info)

        # Phosh's is an enum of GtkIconSize; g_object_new collects an enum as an int.
        @GObject.Property(type=int, default=3)
        def icon_size(self):
            return getattr(self, "_size", 3)

        @icon_size.setter
        def icon_size(self, value):
            self._size = value

    class QuickSetting(Gtk.Box):
        __gtype_name__ = "PhoshQuickSetting"
        __gsignals__ = {"clicked": (GObject.SignalFlags.RUN_LAST, None, ())}
        active = GObject.Property(type=bool, default=False)

        @GObject.Property(type=StatusIcon)
        def status_icon(self):
            return getattr(self, "_status_icon", None)

        @status_icon.setter
        def status_icon(self, icon):
            old = getattr(self, "_status_icon", None)
            if old is not None and old.get_parent() is self:
                self.remove(old)
            self._status_icon = icon
            if icon is not None:
                self.pack_start(icon, True, True, 0)  # Phosh packs it into the tile's button

    STAND_INS.extend([StatusIcon, QuickSetting])


def serve(kind: str, so: str, types: str) -> int:
    point, name = KINDS[kind]
    try:
        import gi  # noqa: PLC0415

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gio, GLib, GObject, Gtk  # noqa: PLC0415
    except (ImportError, ValueError) as error:
        say({"error": f"GTK 3 for Python is not on this device: {error}", "class": "harness"})
        return 2
    if not Gtk.init_check(sys.argv)[0]:
        say({"error": "GTK 3 found no display", "class": "harness"})
        return 2
    used = ""
    if kind == "quick-setting":
        if types == "libphosh":
            import ctypes  # noqa: PLC0415

            try:
                library = ctypes.CDLL(LIBPHOSH, mode=ctypes.RTLD_GLOBAL)
                for symbol in ("phosh_status_icon_get_type", "phosh_quick_setting_get_type"):
                    getattr(library, symbol).restype = ctypes.c_size_t
                    getattr(library, symbol)()
            except (OSError, AttributeError) as error:
                say({"error": f"Phosh's own types ({LIBPHOSH}, package libphosh-0.45-0): {error}", "class": "harness"})
                return 2
            used = "libphosh"
        else:
            stand_ins(GObject, Gtk)
            used = "stand-in"
    # As Phosh's plugin loader (src/plugin-loader.c): the point wants widgets, the extension is
    # found by the plugin's name and made with g_object_new. Phosh scans the whole directory
    # (g_io_modules_scan_all_in_directory, lazily through giomodule.cache); the host loads only
    # this module, so Phosh's own plugins, which need the shell's symbols, stay out of it.
    Gio.IOExtensionPoint.register(point).set_required_type(Gtk.Widget.__gtype__)
    module = Gio.IOModule.new(so)
    if not GObject.TypeModule.use(module):
        say({"error": f"{os.path.basename(so)} did not load", "class": "app"})
        return 3
    extension = Gio.IOExtensionPoint.lookup(point).get_extension_by_name(name)
    if extension is None:
        say({"error": f"{os.path.basename(so)} implements nothing at {point} under the name {name}", "class": "app"})
        return 3
    widget = GObject.new(extension.get_type())
    window = Gtk.Window(title=f"MeshSat {kind} (e2e host)")
    window.set_default_size(360, 160)
    window.add(widget)
    widget.show()  # never show_all: the widget decides which of its own children show
    window.show()
    gtype = widget.__gtype__

    def state() -> dict:
        out = {"type": gtype.name}
        if kind == "lockscreen":
            icons, labels = [], []

            def walk(w) -> None:
                if isinstance(w, Gtk.Image):
                    icons.append(w.get_icon_name()[0])
                elif isinstance(w, Gtk.Label):
                    labels.append({"text": w.get_text(), "visible": w.get_visible()})
                if isinstance(w, Gtk.Container):
                    w.foreach(walk)

            widget.foreach(walk)
            out.update(icons=icons, labels=labels, shown=[label["text"] for label in labels if label["visible"] and label["text"]])
        else:
            icon = widget.get_property("status-icon")
            out.update(info=icon.get_property("info") if icon is not None else None, icon=icon.get_property("icon-name") if icon is not None else None,
                       active=widget.get_property("active"))
        return out

    pending = [b""]

    def on_input(_channel, _condition) -> bool:
        try:
            chunk = os.read(0, 4096)
        except OSError:
            chunk = b""
        if not chunk:
            Gtk.main_quit()
            return False
        pending[0] += chunk
        while b"\n" in pending[0]:
            line, pending[0] = pending[0].split(b"\n", 1)
            command = line.decode("utf-8", "replace").strip()
            if command == "state":
                say(state())
            elif command == "click":
                if kind != "quick-setting":
                    say({"error": "only the tile takes a tap"})
                else:
                    widget.emit("clicked")
                    say({"clicked": True})
            elif command == "quit":
                say({"bye": True})
                Gtk.main_quit()
                return False
            else:
                say({"error": f"no such question: {command!r}"})
        return True

    GLib.io_add_watch(GLib.IOChannel.unix_new(0), GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN | GLib.IOCondition.HUP, on_input)
    GLib.timeout_add_seconds(900, Gtk.main_quit)  # never outlives a run
    parent = GObject.type_parent(gtype)
    say({"ready": True, "type": gtype.name, "parent": parent.name if parent else "", "types": used, "module": so})
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(serve(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "stand-in"))
