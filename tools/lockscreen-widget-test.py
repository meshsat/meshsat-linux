# SPDX-License-Identifier: GPL-3.0-or-later
# The lock-screen widget in a window of its own: the module is loaded the way Phosh loads it (a
# GIO module implementing the extension point), but in this process, so a fault ends this test
# and nothing else.
import sys
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, GObject, Gtk

POINT = "phosh-lockscreen-widget"
Gio.IOExtensionPoint.register(POINT)
module = Gio.IOModule.new("/usr/lib/aarch64-linux-gnu/phosh/plugins/libphosh-plugin-meshsat-lockscreen.so")
if not GObject.TypeModule.use(module):
    print("the module did not load"); sys.exit(2)
extension = Gio.IOExtensionPoint.lookup(POINT).get_extension_by_name("meshsat-lockscreen")
if extension is None:
    print("the module implements nothing"); sys.exit(3)
widget = GObject.new(extension.get_type())
print("widget:", type(widget).__name__, GObject.type_name(extension.get_type()))
window = Gtk.Window(title="MeshSat lock-screen widget (test)")
window.set_default_size(340, 120)
window.add(widget)
window.show_all()
def report():
    labels = []
    def walk(w):
        if isinstance(w, Gtk.Label): labels.append(w.get_text())
        if isinstance(w, Gtk.Container): w.foreach(walk)
    walk(widget)
    print("labels:", labels)
    return False
GLib.timeout_add_seconds(3, report)
GLib.timeout_add_seconds(7, Gtk.main_quit)
Gtk.main()
print("ok")
