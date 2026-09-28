# SPDX-License-Identifier: GPL-3.0-or-later
"""MeshSat outside its window: a user service (meshsat-notify.service) that runs with the
session, whether the app is open or not.

- Notifications, as MeshSat Android posts them: a text that arrived ("Mesh: !a1b3c2ec"), a
  message that did not go, an SOS in progress with its Cancel button, and the satellite signal
  ("Iridium signal 3/5") as one notification kept up to date in place, which is how Android
  puts its satellite icon in the status bar.
- net.meshsat.Status on the session bus: the two radios' state for whatever draws it outside
  the app (the Phosh quick-settings tile and lock-screen widget of this package).
- A tray icon (org.kde.StatusNotifierItem) wherever the shell has a tray: Plasma Mobile,
  desktops. Phosh has none.

GLib and Gio only: no window, no GTK."""
import glob
import os
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import api, events, outside  # noqa: E402

APP_ID = "net.meshsat.Bridge"
APP_PATH = "/net/meshsat/Bridge"
APP_NAME = "MeshSat"
STATUS_NAME = "net.meshsat.Status"
STATUS_PATH = "/net/meshsat/Status"
STATUS_IFACE = "net.meshsat.Status1"
WATCHER = "org.kde.StatusNotifierWatcher"
ACTIVE_FLAG = os.path.join(GLib.get_user_runtime_dir(), "meshsat-app-active")

STATUS_XML = """<node>
  <interface name="net.meshsat.Status1">
    <property name="SatelliteState" type="s" access="read"/>
    <property name="SatelliteBars" type="i" access="read"/>
    <property name="SatelliteDetail" type="s" access="read"/>
    <property name="MeshState" type="s" access="read"/>
    <property name="MeshNodes" type="i" access="read"/>
    <property name="MeshDetail" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="Summary" type="s" access="read"/>
    <property name="TileLabel" type="s" access="read"/>
    <method name="Open"><arg name="screen" type="s" direction="in"/></method>
  </interface>
</node>"""

SNI_XML = """<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
    <signal name="NewIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg name="status" type="s"/></signal>
  </interface>
</node>"""


def offer_phosh_plugins() -> None:
    """Once per person: MeshSat's tile among Phosh's quick settings and its widget on the lock
    screen. Phosh keeps the lists in the person's settings; whoever takes MeshSat out of them
    later is not overruled (the marker says the offer was made)."""
    marker = os.path.join(GLib.get_user_config_dir(), "meshsat", "phosh-plugins-offered")
    if os.path.exists(marker):
        return
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup("sm.puri.phosh.plugins", True) is None:
        return
    if not glob.glob("/usr/lib/*/phosh/plugins/meshsat-quick-setting.plugin"):
        return
    settings = Gio.Settings.new("sm.puri.phosh.plugins")
    for key, plugin in (("quick-settings", "meshsat-quick-setting"), ("lock-screen", "meshsat-lockscreen")):
        current = list(settings.get_strv(key))
        if plugin not in current:
            settings.set_strv(key, current + [plugin])
    Gio.Settings.sync()
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("MeshSat's Phosh plugins were offered once; Phosh's settings are the person's from here.\n")
    except OSError:
        pass


def app_in_front() -> bool:
    """The app writes a flag while its window is the active one; its notifications would
    only repeat what the person is looking at."""
    try:
        return time.time() - os.path.getmtime(ACTIVE_FLAG) < 15
    except OSError:
        return False


class Notifier:
    def __init__(self):
        self.loop = GLib.MainLoop()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.ids = {}       # our key -> the notification daemon's id
        self.keys = {}      # and back, for the actions
        self.counter = 0
        self.seen = events.Seen()
        self.status = outside.status(None, None, None, [])
        self.sos_active = False
        self.signal_shown = None
        self.tray_registered = False
        self.notifications = Gio.DBusProxy.new_sync(self.bus, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, None, "org.freedesktop.Notifications",
                                                    "/org/freedesktop/Notifications", "org.freedesktop.Notifications", None)
        self.notifications.connect("g-signal", self.on_notification_signal)
        self.status_info = Gio.DBusNodeInfo.new_for_xml(STATUS_XML).interfaces[0]
        self.sni_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        Gio.bus_own_name_on_connection(self.bus, STATUS_NAME, Gio.BusNameOwnerFlags.NONE, None, None)
        self.bus.register_object(STATUS_PATH, self.status_info, self.on_status_call, self.on_status_get, None)
        self.bus.register_object("/StatusNotifierItem", self.sni_info, self.on_tray_call, self.on_tray_get, None)
        Gio.bus_watch_name_on_connection(self.bus, WATCHER, Gio.BusNameWatcherFlags.NONE, self.on_tray_appeared, self.on_tray_vanished)
        self.stream = events.EventStream(lambda event: GLib.idle_add(self.on_event, event))

    # Notifications
    def post(self, key: str, title: str, text: str, icon: str = outside.ICON_APP, actions=(), urgency: int = 1, ongoing: bool = False, quiet: bool = False) -> None:
        hints = {"desktop-entry": GLib.Variant("s", APP_ID), "urgency": GLib.Variant("y", urgency)}
        if ongoing:
            hints["resident"] = GLib.Variant("b", True)
        if quiet:
            hints["suppress-sound"] = GLib.Variant("b", True)
            hints["transient"] = GLib.Variant("b", False)
        flat = []
        for action_key, label in actions:
            flat += [action_key, label]
        try:
            result = self.notifications.call_sync("Notify", GLib.Variant("(susssasa{sv}i)", (APP_NAME, self.ids.get(key, 0), icon, title, text, flat, hints, 0 if ongoing else -1)),
                                                  Gio.DBusCallFlags.NONE, 5000, None)
        except GLib.Error as error:
            print(f"meshsat-notify: no notification daemon: {error.message}", file=sys.stderr)
            return
        number = result.unpack()[0]
        self.ids[key] = number
        self.keys[number] = key

    def withdraw(self, key: str) -> None:
        number = self.ids.pop(key, None)
        if number is None:
            return
        self.keys.pop(number, None)
        try:
            self.notifications.call_sync("CloseNotification", GLib.Variant("(u)", (number,)), Gio.DBusCallFlags.NONE, 5000, None)
        except GLib.Error:
            pass

    def on_notification_signal(self, _proxy, _sender, signal: str, parameters) -> None:
        if signal == "NotificationClosed":
            number = parameters.unpack()[0]
            key = self.keys.pop(number, None)
            if key and self.ids.get(key) == number:
                del self.ids[key]
                if key == "signal":
                    self.signal_shown = None  # swiped away: it comes back with the next change
        elif signal == "ActionInvoked":
            number, action = parameters.unpack()
            key = self.keys.get(number, "")
            if action == "cancel-sos":
                threading.Thread(target=lambda: api.post("/api/sos/cancel"), daemon=True).start()
            elif key == "sos":
                self.open_app("open", "safety")
            elif key == "signal":
                self.open_app("open", "satellite")
            else:
                self.open_app("tab", "messages")

    # The app
    def open_app(self, action: str, target: str) -> None:
        def act() -> bool:
            try:
                self.bus.call_sync(APP_ID, APP_PATH, "org.freedesktop.Application", "Activate", GLib.Variant("(a{sv})", ({},)), None, Gio.DBusCallFlags.NONE, 5000, None)
                Gio.DBusActionGroup.get(self.bus, APP_ID, APP_PATH).activate_action(action, GLib.Variant("s", target))
            except GLib.Error as error:
                print(f"meshsat-notify: cannot open the app: {error.message}", file=sys.stderr)
            return False

        try:
            running = self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner", GLib.Variant("(s)", (APP_ID,)),
                                         None, Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        except GLib.Error:
            running = False
        if running:
            act()
            return
        try:
            subprocess.Popen(["meshsat-app"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            print(f"meshsat-notify: cannot start the app: {error}", file=sys.stderr)
            return
        GLib.timeout_add_seconds(4, act)

    # The event stream: what cannot wait for the next poll
    def on_event(self, event: dict) -> bool:
        item = events.inbound_text(event)
        if item is not None:
            if self.seen.new(item["from"], item["text"]) and not app_in_front():
                self.counter += 1
                title, text = outside.message_notification(item)
                self.post(f"message-{self.counter}", title, text, actions=(("default", "Open"),))
            return False
        failure = outside.failure_notification(event)
        if failure is not None:
            self.counter += 1
            self.post(f"failure-{self.counter}", failure[0], failure[1], actions=(("default", "Open"),))
        return False

    # The polls: the state of the radios and of an SOS
    def poll(self) -> bool:
        threading.Thread(target=self.poll_once, daemon=True).start()
        return True

    def poll_once(self) -> None:
        bridge = api.get("/api/status")
        modem = signal = sos = None
        nodes = []
        ble = None
        if bridge is not None:
            modem = api.get("/api/iridium/modem")
            signal = api.get("/api/iridium/signal")
            sos = api.get("/api/sos/status")
            nodes = (api.get("/api/nodes") or {}).get("nodes") or []
        hardware = api.hardware()
        if bridge is not None and hardware.get("node") == "bluetooth":
            ble = api.ble_status()
        GLib.idle_add(self.apply, bridge, modem, signal, sos, nodes, hardware, ble)

    def apply(self, bridge, modem, signal, sos, nodes, hardware, ble) -> bool:
        shown = outside.signal_notification(modem, signal)
        if shown is None:
            if self.signal_shown is not None or "signal" in self.ids:
                self.withdraw("signal")
            self.signal_shown = None
        elif shown != self.signal_shown:
            self.post("signal", shown[0], shown[1], icon=shown[2], actions=(("default", "Open"),), urgency=0, ongoing=True, quiet=True)
            self.signal_shown = shown

        alarm = outside.sos_notification(sos, self.sos_active)
        active = bool((sos or {}).get("active"))
        if alarm is not None and (active != self.sos_active or active):
            title, text, ongoing = alarm
            actions = (("default", "Open"), ("cancel-sos", "Cancel SOS")) if ongoing else (("default", "Open"),)
            if active != self.sos_active or self.ids.get("sos") is None:
                self.post("sos", title, text, actions=actions, urgency=2 if ongoing else 1, ongoing=ongoing)
        self.sos_active = active

        new = outside.status(bridge, modem, signal, nodes, hardware, ble)
        if new != self.status:
            self.status = new
            self.announce()
        return False

    # net.meshsat.Status
    def status_properties(self) -> dict:
        s = self.status
        return {"SatelliteState": GLib.Variant("s", s["satellite"]["state"]), "SatelliteBars": GLib.Variant("i", s["satellite"]["bars"]),
                "SatelliteDetail": GLib.Variant("s", s["satellite"]["detail"]), "MeshState": GLib.Variant("s", s["mesh"]["state"]),
                "MeshNodes": GLib.Variant("i", s["mesh"]["nodes"]), "MeshDetail": GLib.Variant("s", s["mesh"]["detail"]),
                "IconName": GLib.Variant("s", s["icon"]), "Summary": GLib.Variant("s", s["summary"]), "TileLabel": GLib.Variant("s", s["tile"])}

    def on_status_get(self, _connection, _sender, _path, _interface, name: str):
        return self.status_properties().get(name)

    def on_status_call(self, _connection, _sender, _path, _interface, method: str, parameters, invocation) -> None:
        if method == "Open":
            screen = parameters.unpack()[0]
            if screen in ("home", "messages", "map", "people", "setup"):
                self.open_app("tab", screen)
            else:
                self.open_app("open", screen or "satellite")
        invocation.return_value(None)

    def announce(self) -> None:
        try:
            self.bus.emit_signal(None, STATUS_PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged", GLib.Variant("(sa{sv}as)", (STATUS_IFACE, self.status_properties(), [])))
            if self.tray_registered:
                self.bus.emit_signal(None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewIcon", None)
                self.bus.emit_signal(None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewToolTip", None)
        except GLib.Error:
            pass

    # The tray, where there is one
    def on_tray_appeared(self, _connection, _name, _owner) -> None:
        try:
            self.bus.call_sync(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem", GLib.Variant("(s)", (self.bus.get_unique_name(),)),
                               None, Gio.DBusCallFlags.NONE, 5000, None)
            self.tray_registered = True
        except GLib.Error as error:
            print(f"meshsat-notify: the tray refused the icon: {error.message}", file=sys.stderr)

    def on_tray_vanished(self, _connection, _name) -> None:
        self.tray_registered = False

    def on_tray_get(self, _connection, _sender, _path, _interface, name: str):
        return {"Category": GLib.Variant("s", "Communications"), "Id": GLib.Variant("s", "meshsat"), "Title": GLib.Variant("s", APP_NAME),
                "Status": GLib.Variant("s", "Active"), "IconName": GLib.Variant("s", self.status["icon"]),
                "ToolTip": GLib.Variant("(sa(iiay)ss)", (self.status["icon"], [], APP_NAME, self.status["summary"])),
                "ItemIsMenu": GLib.Variant("b", False), "Menu": GLib.Variant("o", "/NO_DBUSMENU")}.get(name)

    def on_tray_call(self, _connection, _sender, _path, _interface, method: str, _parameters, invocation) -> None:
        if method in ("Activate", "SecondaryActivate"):
            self.open_app("tab", "home")
        invocation.return_value(None)

    def run(self) -> int:
        try:
            offer_phosh_plugins()
        except GLib.Error as error:
            print(f"meshsat-notify: Phosh's plugin settings: {error.message}", file=sys.stderr)
        self.stream.start()
        self.poll()
        GLib.timeout_add_seconds(5, self.poll)
        try:
            self.loop.run()
        except KeyboardInterrupt:
            pass
        self.stream.stop()
        for key in list(self.ids):
            if key in ("signal",):
                self.withdraw(key)
        return 0


def main() -> int:
    return Notifier().run()


if __name__ == "__main__":
    sys.exit(main())
