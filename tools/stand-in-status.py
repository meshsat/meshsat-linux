# SPDX-License-Identifier: GPL-3.0-or-later
# What the notifier says with a satellite modem at N bars, for screenshots on a phone that has
# no modem plugged in: the same words and icons, from the app's own functions.
import sys
sys.path.insert(0, "/usr/lib/meshsat/app")
from gi.repository import Gio, GLib
from meshsat import notify, outside

bars = int(sys.argv[1]) if len(sys.argv) > 1 else 3
seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 30
modem = {"connected": True, "imei": "300434061234560", "port": "/dev/ttyUSB4"}
nodes = [{"user_id": "!52cb81e7"}, {"user_id": "!a1b3c2ec"}, {"user_id": "!8b04a69e"}]
s = outside.status({"connected": True, "node_id": "!52cb81e7", "node_name": "meshsat-pinephone-pro"}, modem, {"bars": bars}, nodes)
props = {"SatelliteState": GLib.Variant("s", s["satellite"]["state"]), "SatelliteBars": GLib.Variant("i", s["satellite"]["bars"]),
         "SatelliteDetail": GLib.Variant("s", s["satellite"]["detail"]), "MeshState": GLib.Variant("s", s["mesh"]["state"]),
         "MeshNodes": GLib.Variant("i", s["mesh"]["nodes"]), "MeshDetail": GLib.Variant("s", s["mesh"]["detail"]),
         "IconName": GLib.Variant("s", s["icon"]), "Summary": GLib.Variant("s", s["summary"]), "TileLabel": GLib.Variant("s", s["tile"])}
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
info = Gio.DBusNodeInfo.new_for_xml(notify.STATUS_XML).interfaces[0]
bus.register_object(notify.STATUS_PATH, info, lambda c, sender, path, iface, method, params, invocation: invocation.return_value(None),
                    lambda c, sender, path, iface, name: props.get(name), None)
Gio.bus_own_name_on_connection(bus, notify.STATUS_NAME, Gio.BusNameOwnerFlags.REPLACE, None, None)
title, text, icon = outside.signal_notification(modem, {"bars": bars})
hints = {"desktop-entry": GLib.Variant("s", "net.meshsat.Bridge"), "urgency": GLib.Variant("y", 0), "resident": GLib.Variant("b", True)}
number = bus.call_sync("org.freedesktop.Notifications", "/org/freedesktop/Notifications", "org.freedesktop.Notifications", "Notify",
                       GLib.Variant("(susssasa{sv}i)", ("MeshSat", 0, icon, title, text, ["default", "Open"], hints, 0)), None, Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
print("serving", s["tile"], "|", s["summary"], "| notification", number, flush=True)
loop = GLib.MainLoop()
GLib.timeout_add_seconds(seconds, loop.quit)
loop.run()
bus.call_sync("org.freedesktop.Notifications", "/org/freedesktop/Notifications", "org.freedesktop.Notifications", "CloseNotification", GLib.Variant("(u)", (number,)), None, Gio.DBusCallFlags.NONE, 5000, None)
