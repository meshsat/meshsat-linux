# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in notification daemon (org.freedesktop.Notifications) on the test session's bus:
it takes what the notifier posts and keeps it for the cases to read, the way Phosh would show
it. Nothing is drawn."""
import threading

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

INTROSPECTION = """
<node>
  <interface name="org.freedesktop.Notifications">
    <method name="Notify">
      <arg type="s" direction="in" name="app_name"/>
      <arg type="u" direction="in" name="replaces_id"/>
      <arg type="s" direction="in" name="app_icon"/>
      <arg type="s" direction="in" name="summary"/>
      <arg type="s" direction="in" name="body"/>
      <arg type="as" direction="in" name="actions"/>
      <arg type="a{sv}" direction="in" name="hints"/>
      <arg type="i" direction="in" name="expire_timeout"/>
      <arg type="u" direction="out" name="id"/>
    </method>
    <method name="CloseNotification"><arg type="u" direction="in" name="id"/></method>
    <method name="GetCapabilities"><arg type="as" direction="out" name="caps"/></method>
    <method name="GetServerInformation">
      <arg type="s" direction="out" name="name"/><arg type="s" direction="out" name="vendor"/>
      <arg type="s" direction="out" name="version"/><arg type="s" direction="out" name="spec_version"/>
    </method>
    <signal name="NotificationClosed"><arg type="u" name="id"/><arg type="u" name="reason"/></signal>
    <signal name="ActionInvoked"><arg type="u" name="id"/><arg type="s" name="action_key"/></signal>
  </interface>
</node>
"""


class NotificationDaemon:
    """Owns org.freedesktop.Notifications on the session bus, on its own main loop thread."""

    def __init__(self):
        self.posted = []  # every Notify call, in order: {id, app, summary, body, actions, hints, replaces}
        self.closed = []
        self.next_id = 1
        self.lock = threading.Lock()
        # Its own main context and its own bus connection: the runner's shared session connection
        # and default context belong to its main thread (AT-SPI), and a second daemon in the same
        # run could not register on a shared connection the first one never let go of.
        self.context = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(self.context, False)
        self.bus = None
        self.registration = None
        self.owner = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "NotificationDaemon":
        self.thread.start()
        if not self.ready.wait(10):
            raise RuntimeError("the notification daemon did not come up on the bus")
        return self

    def _run(self) -> None:
        self.context.push_thread_default()
        try:
            address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            self.bus = Gio.DBusConnection.new_for_address_sync(
                address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
            node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
            self.registration = self.bus.register_object("/org/freedesktop/Notifications", node.interfaces[0], self._call, None, None)
            self.owner = Gio.bus_own_name_on_connection(self.bus, "org.freedesktop.Notifications",
                                                        Gio.BusNameOwnerFlags.REPLACE | Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT, lambda *_: self.ready.set(), None)
            self.loop.run()
        finally:
            # Let the name and the object go, so the next module's daemon gets them
            if self.owner is not None:
                Gio.bus_unown_name(self.owner)
            if self.bus is not None:
                if self.registration:
                    self.bus.unregister_object(self.registration)
                self.bus.close_sync(None)
            self.context.pop_thread_default()

    def _call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
        if method == "Notify":
            app, replaces, icon, summary, body, actions, hints, timeout = parameters.unpack()
            with self.lock:
                number = replaces or self.next_id
                if not replaces:
                    self.next_id += 1
                self.posted.append({"id": number, "app": app, "icon": icon, "summary": summary, "body": body, "actions": list(actions), "hints": dict(hints), "replaces": replaces})
            invocation.return_value(GLib.Variant("(u)", (number,)))
        elif method == "CloseNotification":
            with self.lock:
                self.closed.append(parameters.unpack()[0])
            invocation.return_value(None)
        elif method == "GetCapabilities":
            invocation.return_value(GLib.Variant("(as)", (["body", "actions", "persistence"],)))
        elif method == "GetServerInformation":
            invocation.return_value(GLib.Variant("(ssss)", ("meshsat-e2e", "MeshSat", "1", "1.2")))
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)

    def invoke(self, number: int, action: str) -> None:
        """As a tap on the notification's action."""
        self.bus.emit_signal(None, "/org/freedesktop/Notifications", "org.freedesktop.Notifications", "ActionInvoked", GLib.Variant("(us)", (number, action)))

    def since(self, index: int) -> list:
        with self.lock:
            return list(self.posted[index:])

    def count(self) -> int:
        with self.lock:
            return len(self.posted)

    def stop(self) -> None:
        self.loop.quit()
        self.thread.join(5)
