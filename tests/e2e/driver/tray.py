# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in tray (org.kde.StatusNotifierWatcher) on the test session's bus, as a desktop's tray
host runs one (Plasma, a desktop panel; Phosh has none): items register with it, and it reads
them the way a tray does, over their org.kde.StatusNotifierItem properties and signals. Nothing
is drawn. It has its own connection and its own main loop, so it can come and go like a tray
host that restarts, without touching the stand-in notification daemon's connection.

Installed as tests/e2e/driver/tray.py by wip-100/patch-100-outside.py."""
import threading
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import HarnessError  # noqa: E402

WATCHER = "org.kde.StatusNotifierWatcher"
ITEM = "org.kde.StatusNotifierItem"
XML = """<node>
  <interface name="org.kde.StatusNotifierWatcher">
    <method name="RegisterStatusNotifierItem"><arg type="s" direction="in" name="service"/></method>
    <method name="RegisterStatusNotifierHost"><arg type="s" direction="in" name="service"/></method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered"><arg type="s" name="service"/></signal>
    <signal name="StatusNotifierItemUnregistered"><arg type="s" name="service"/></signal>
    <signal name="StatusNotifierHostRegistered"/>
  </interface>
</node>"""


class Tray:
    """Owns org.kde.StatusNotifierWatcher on the session bus until stopped."""

    def __init__(self):
        self.items = []  # every RegisterStatusNotifierItem: {"sender", "service", "t"}
        self.signals = []  # every item signal seen: {"sender", "path", "member", "t"}
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.failed = ""
        self.bus = None
        self.loop = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self, timeout: float = 10.0) -> "Tray":
        self.thread.start()
        if not self.ready.wait(timeout):
            raise HarnessError(f"the stand-in tray did not come up on the bus {self.failed}".strip())
        return self

    def alive(self) -> bool:
        return self.thread.is_alive() and self.ready.is_set()

    def _run(self) -> None:
        context = GLib.MainContext()
        context.push_thread_default()
        try:
            self.loop = GLib.MainLoop(context)
            address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
            self.bus = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
            info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
            registration = self.bus.register_object("/StatusNotifierWatcher", info, self._call, self._get, None)
            subscription = self.bus.signal_subscribe(None, ITEM, None, None, None, Gio.DBusSignalFlags.NONE, self._signal)
            owner = Gio.bus_own_name_on_connection(self.bus, WATCHER, Gio.BusNameOwnerFlags.NONE, lambda *_: self.ready.set(), None)
            self.loop.run()
            Gio.bus_unown_name(owner)
            self.bus.signal_unsubscribe(subscription)
            self.bus.unregister_object(registration)
            self.bus.close_sync(None)
        except GLib.Error as error:
            self.failed = f"({error.message})"
        finally:
            context.pop_thread_default()

    # The watcher, as a tray host answers it
    def _call(self, connection, sender, _path, _interface, method, parameters, invocation) -> None:
        if method == "RegisterStatusNotifierItem":
            service = parameters.unpack()[0]
            with self.lock:
                self.items.append({"sender": sender, "service": service, "t": time.time()})
            connection.emit_signal(None, "/StatusNotifierWatcher", WATCHER, "StatusNotifierItemRegistered", GLib.Variant("(s)", (service,)))
            invocation.return_value(None)
        elif method == "RegisterStatusNotifierHost":
            invocation.return_value(None)
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)

    def _get(self, _connection, _sender, _path, _interface, name: str):
        with self.lock:
            services = [i["service"] for i in self.items]
        return {"RegisteredStatusNotifierItems": GLib.Variant("as", services), "IsStatusNotifierHostRegistered": GLib.Variant("b", True),
                "ProtocolVersion": GLib.Variant("i", 0)}.get(name)

    def _signal(self, _connection, sender, path, _interface, member, _parameters, *_):
        with self.lock:
            self.signals.append({"sender": sender, "path": path, "member": member, "t": time.time()})

    # What a case asks, as a tray would
    def wait_item(self, timeout: float = 10.0, since: int = 0) -> dict:
        """The latest item registered (after the first `since` registrations)."""
        deadline = time.time() + timeout
        while True:
            with self.lock:
                found = list(self.items[since:])
            if found:
                return found[-1]
            if time.time() >= deadline:
                raise AssertionError(f"no item registered with the tray in {timeout:.0f} s")
            time.sleep(0.2)

    @staticmethod
    def where(item: dict) -> tuple:
        """The item's bus name and object path, as the StatusNotifierItem spec reads `service`:
        a bus name (the item at /StatusNotifierItem), or an object path on the sender."""
        service = item["service"]
        if service.startswith("/"):
            return item["sender"], service
        return service, "/StatusNotifierItem"

    def properties(self, item: dict) -> dict:
        name, path = self.where(item)
        reply = self.bus.call_sync(name, path, "org.freedesktop.DBus.Properties", "GetAll", GLib.Variant("(s)", (ITEM,)), GLib.VariantType.new("(a{sv})"),
                                   Gio.DBusCallFlags.NONE, 5000, None)
        return reply.unpack()[0]

    def call(self, item: dict, method: str, x: int = 0, y: int = 0) -> None:
        """Activate, SecondaryActivate or ContextMenu at a place, as a click on the icon."""
        name, path = self.where(item)
        self.bus.call_sync(name, path, ITEM, method, GLib.Variant("(ii)", (x, y)), None, Gio.DBusCallFlags.NONE, 5000, None)

    def signals_since(self, t: float) -> list:
        with self.lock:
            return [s for s in self.signals if s["t"] >= t]

    def stop(self) -> None:
        if self.loop is not None:
            self.loop.quit()
        self.thread.join(10)
