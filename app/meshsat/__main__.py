# SPDX-License-Identifier: GPL-3.0-or-later
"""The app: the window every MeshSat app has (the status strip, the banners, the five tabs
with their own stacks, the navigation bar), night mode as the colour matrix Android applies,
and the few things the screens ask of it: push, pop, toast, copy, open a route, pick a tab."""
import json
import os
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import __version__, api, routes, sosflow, store, theme, trace  # noqa: E402
from .home import HomeScreen  # noqa: E402
from .mapview import MapScreen  # noqa: E402
from .messages import ChatScreen, MessagesScreen, name_of  # noqa: E402
from .model import words  # noqa: E402
from .people import PeopleScreen  # noqa: E402
from .setup import SetupScreen  # noqa: E402
from .widgets import Banner, Filtered, KeyValue, NavBar, StatusStrip, ago, filled_button, outlined_button, text  # noqa: E402

# The application id is the package's; a test instance takes its own so the two never meet.
APP_ID = os.environ.get("MESHSAT_APP_ID", "net.meshsat.Bridge")
TEST = os.environ.get("MESHSAT_APP_TEST") == "1"
TABS = (("home", "Home", HomeScreen), ("messages", "Messages", MessagesScreen), ("map", "Map", MapScreen), ("people", "People", PeopleScreen), ("setup", "Setup", SetupScreen))
TABS_BY_KEY = {key for key, _title, _cls in TABS}

GLib.set_prgname("net.meshsat.Bridge")
GLib.set_application_name("MeshSat")


class MeshSatApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        self.poller = api.Poller(self.on_state)
        self.state = self.poller.state
        self.prefs = store.Prefs()
        # The SOS in progress, or the last one (sos/SosController.kt): the banner, the Home
        # card and the result screen read it.
        self.sos = sosflow.Flow(self.prefs, lambda: GLib.idle_add(self.on_sos_change))
        self._test_notified = None
        self.night = False
        self.tabs = {}
        self.current = "home"
        for name, handler, accel in (("quit", lambda *_: self.quit(), "<Control>q"), ("night", lambda *_: self.toggle_night(), "<Control>n"), ("refresh", lambda *_: self.poller.poll_now(), "F5"),
                                     ("stop-test", lambda *_: self.stop_test(), None)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)
            if accel:
                self.set_accels_for_action(f"app.{name}", [accel])
        # With a string: pick a tab, or open a route (Android's route strings, routes.py).
        # Reachable over D-Bus, as any GApplication action (gapplication action net.meshsat.Bridge
        # open "'setup/node'"), which is how the parity captures and the tests drive the app.
        # `inspect "'/tmp/tree.json'"` writes every widget on view with its size, for the tests.
        for name, handler in (("tab", lambda _a, p: self.select_tab(p.get_string())), ("open", lambda _a, p: self.open_route(p.get_string())),
                              ("inspect", lambda _a, p: self.inspect(p.get_string()))):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", handler)
            self.add_action(action)
        open_sos = Gio.SimpleAction.new("open-sos", None)  # the alarm test's notification
        open_sos.connect("activate", lambda *_: (self.activate(), self.open_route("sos")))
        self.add_action(open_sos)

    # Lifecycle
    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        theme.apply()
        # MeshSat outside its window (notifications, the satellite signal) runs with the
        # session; a session older than the package gets it with the app's first start.
        if not TEST:
            try:
                subprocess.Popen(["systemctl", "--user", "start", "meshsat-notify.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
        self.night = bool(self.prefs.get("night", False))
        entered = self.prefs.get("position")
        if isinstance(entered, list) and len(entered) == 2:
            self.state.entered = (float(entered[0]), float(entered[1]))
        contacts = self.prefs.get("contacts")
        if isinstance(contacts, list):
            self.state.contacts = [c for c in contacts if isinstance(c, dict) and c.get("phone")]
        self.state.sos_name = str(self.prefs.get("sos_name", ""))
        self.locate()

    def set_contacts(self, contacts: list) -> None:
        self.state.contacts = contacts
        self.prefs.set(contacts=contacts)

    def set_sos_name(self, name: str) -> None:
        self.state.sos_name = name.strip()
        self.prefs.set(sos_name=self.state.sos_name)

    # The phone's own position, as Android asks the phone for its GPS: geoclue, which asks the
    # user once (Phosh's location dialog) and follows the Location switch in Settings.
    def locate(self) -> None:
        try:
            gi.require_version("Geoclue", "2.0")
            from gi.repository import Geoclue  # noqa: PLC0415
        except (ValueError, ImportError):
            self.state.location_hint = "Location needs geoclue (gir1.2-geoclue-2.0)."
            return
        self.geoclue = None
        Geoclue.Simple.new(APP_ID, Geoclue.AccuracyLevel.EXACT, None, self.on_located, Geoclue)

    def on_located(self, source, result, Geoclue) -> None:
        try:
            self.geoclue = Geoclue.Simple.new_finish(result)
        except GLib.Error as error:
            message = str(error.message)
            if "disabled" in message.lower():
                self.state.location_hint = "Location is off for this phone: Settings > Privacy > Location Services, then allow MeshSat."
            elif "denied" in message.lower() or "not allowed" in message.lower():
                self.state.location_hint = "Location was not allowed for MeshSat: Settings > Privacy > Location Services."
            else:
                self.state.location_hint = f"No location service: {message}"
            return
        self.geoclue.connect("notify::location", lambda *_: self.on_fix())
        self.on_fix()

    def on_fix(self) -> None:
        location = self.geoclue.get_location() if self.geoclue else None
        if location is None:
            return
        lat, lon = location.get_property("latitude"), location.get_property("longitude")
        if lat == 0 and lon == 0:
            return
        self.state.phone = (lat, lon, location.get_property("accuracy"), time.time())
        self.state.location_hint = ""
        if self.window is not None:
            self.on_state(self.state)

    def set_entered_position(self, lat: float, lon: float) -> None:
        self.state.entered = (lat, lon)
        self.prefs.set(position=[lat, lon])

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        # The first frame is a complete one: the window opens once the Bridge has answered
        # (or after a moment, if it does not), never on empty screens that fill a second later.
        self.build_window()
        self.poller.start()
        self.hold()
        self._opened = False
        GLib.timeout_add(1500, self.open_window)

    def open_window(self) -> bool:
        if not self._opened:
            self._opened = True
            self.window.present()
            self.release()
        return False

    def do_shutdown(self):
        self.poller.stop()
        self.prefs.flush()
        Adw.Application.do_shutdown(self)

    # The window: strip, banners, the tab stacks, the bar. The same on a 360 px phone and a desktop.
    def build_window(self) -> None:
        self.window = Adw.ApplicationWindow(application=self, title="MeshSat", default_width=360, default_height=720)
        self.window.set_size_request(320, 480)
        self.window.connect("notify::is-active", lambda *_: self.poller.set_pace(self.window.is_active()))
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.strip = StatusStrip()
        column.append(self.strip)
        self.sos_banner = Banner(self.on_banner)
        self.node_banner = Banner(self.on_banner)
        column.append(self.sos_banner)
        column.append(self.node_banner)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
        self.stack.set_vexpand(True)
        # Each tab is as wide as its own content: one wide row must never widen every tab
        # past the screen (a Gtk.Stack is homogeneous unless told otherwise).
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        for key, title, cls in TABS:
            nav = Adw.NavigationView()
            nav.add(Adw.NavigationPage.new(cls(self), title))
            self.tabs[key] = nav
            self.stack.add_named(nav, key)
        column.append(self.stack)
        self.navbar = NavBar(self.select_tab)
        column.append(self.navbar)
        # Night mode, as Android's: the red-only matrix over the whole screen, icons and images included.
        self.filter = Filtered(column, theme.NIGHT_MATRIX)
        self.filter.on = self.night
        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.filter)
        self.window.set_content(self.toasts)
        self.select_tab("home")
        if os.environ.get("MESHSAT_APP_DEBUG"):
            GLib.timeout_add_seconds(5, lambda: self.inspect("") or True)

    def inspect(self, path: str) -> bool:
        """Every widget on view, with its class, CSS classes, allocation and minimum width, as
        JSON to `path` (stderr when empty): what AT-SPI cannot tell, for the tests and for
        finding what widens the window."""
        if self.window is None:
            return False
        out = {"route": self.current, "window": [self.window.get_width(), self.window.get_height()], "scale": self.window.get_scale_factor(), "widgets": []}

        def walk(widget, depth, scrolls):
            if not widget.get_visible() or not widget.get_mapped():
                return
            minimum, natural, _b1, _b2 = widget.measure(Gtk.Orientation.HORIZONTAL, -1)
            label = widget.get_label() if isinstance(widget, Gtk.Label) else None
            # Inside a row that slides sideways (hscroll) a wide child is by design: it never widens the window.
            if isinstance(widget, Gtk.ScrolledWindow) and widget.get_policy()[0] != Gtk.PolicyType.NEVER:
                scrolls = True
            out["widgets"].append({"depth": depth, "type": type(widget).__name__, "css": widget.get_css_classes(), "width": widget.get_width(), "height": widget.get_height(),
                                   "min": minimum, "natural": natural, "text": label, "scrolls": scrolls})
            child = widget.get_first_child()
            while child is not None:
                walk(child, depth + 1, scrolls)
                child = child.get_next_sibling()

        walk(self.window, 0, False)
        try:
            if path:
                with open(path + ".tmp", "w", encoding="utf-8") as handle:
                    json.dump(out, handle)
                os.replace(path + ".tmp", path)
            else:
                limit = self.window.get_width() - 40
                for w in out["widgets"]:
                    if (w["min"] > limit and not w["scrolls"]) or w["depth"] < 3:
                        print(f"{'  ' * w['depth']}{w['type']} .{' .'.join(w['css']) or '-'} allocated {w['width']} min {w['min']} nat {w['natural']}", file=sys.stderr)
        except OSError:
            pass
        return False

    # What the screens ask of the app
    def visible_screen(self):
        page = self.tabs[self.current].get_visible_page()
        return page.get_child() if page else None

    def select_tab(self, key: str) -> None:
        if key not in self.tabs:
            return
        self.current = key
        self.stack.set_visible_child_name(key)
        self.navbar.set_active(key)
        trace.event("route", route=key)
        if self.state.polled_at:
            self.visible_screen().update(self.state)

    def push(self, screen: Gtk.Widget, title: str = "MeshSat") -> None:
        trace.event("route", route=getattr(screen, "route", title))
        self.tabs[self.current].push(Adw.NavigationPage.new(screen, title))

    def pop(self) -> None:
        self.tabs[self.current].pop()

    def pop_to_root(self) -> None:
        nav = self.tabs[self.current]
        stack = nav.get_navigation_stack()
        if stack.get_n_items() > 1:
            nav.pop_to_page(stack.get_item(0))

    def open_lane(self, lane: str) -> None:
        """A tap on a Home lane (HomeLanes.kt): the satellite lane opens the passes once the
        modem is there, the mesh lane the people once the node is up, else the setup page."""
        s = self.state
        if lane == "satellite" and s.modem_connected():
            self.open_route("passes")
        elif lane == "mesh" and s.mesh_connected():
            self.open_route("people")
        else:
            self.open_route(routes.LANES.get(lane, "setup"))

    def open_screen(self, name: str) -> None:
        self.open_route(name)

    def open_route(self, name: str) -> None:
        """Android's route strings: a tab, "chat/<peer>", or a page under the tab that owns it."""
        route = routes.resolve(name)
        if route in TABS_BY_KEY:
            self.select_tab(route)
            self.pop_to_root()
            return
        if route.startswith("chat/"):
            peer = route[5:]
            self.select_tab("messages")
            self.pop_to_root()
            if peer == api.EVERYONE:
                self.push(ChatScreen(self, api.EVERYONE, "Everyone on the mesh", "mesh"), "Everyone on the mesh")
            elif peer == "satellite":
                self.push(ChatScreen(self, "satellite", "Satellite", "satellite"), "Satellite")
            elif peer.startswith("sms:"):
                self.push(ChatScreen(self, peer, self.state.contact_name(peer[4:]), "sms"), "SMS")
            else:
                self.push(ChatScreen(self, peer, name_of(peer, self.state), "mesh"), name_of(peer, self.state))
            return
        screen = routes.screen_of(route)
        if screen is None:
            return
        self.select_tab(routes.tab_of(route))
        self.pop_to_root()
        page = screen(self)
        page.route = route
        self.push(page, getattr(page, "title", "MeshSat"))

    def toggle_night(self) -> None:
        self.night = not self.night
        self.filter.on = self.night
        self.filter.queue_draw()
        self.prefs.set(night=self.night)
        screen = self.visible_screen()
        if hasattr(screen, "night_changed"):
            screen.night_changed(self.night)

    def toast(self, message: str) -> None:
        trace.event("toast", text=message)
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.toasts.add_toast(toast)

    def copy(self, value: str) -> None:
        self.window.get_clipboard().set(value)
        self.toast("Copied")

    def node_sheet(self, node: dict) -> None:
        """A node's card, as the sheet the Android People screen opens: who, how well heard,
        where, and the two things to do with them."""
        # NodeDetailSheet.kt: the long name, or the id, and "(your node)" for the phone's own.
        node_id = node.get("user_id", "?")
        name = node.get("long_name") or node_id
        mine = node_id == (self.state.bridge or {}).get("node_id")
        dialog = Adw.Dialog(title=name, content_width=360)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        box.add_css_class("sheet")
        box.append(text(name + (" (your node)" if mine else ""), "title-large"))
        box.append(text(node.get("user_id", ""), "body-medium", theme.TEXT_SECONDARY, mono=True))
        battery = node.get("battery_level") or 0
        position = f"{node['latitude']:.5f}, {node['longitude']:.5f}" if node.get("latitude") else "Unknown"
        for k, v in (("Hardware", node.get("hw_model_name") or "-"), ("Signal", signal_words(node)),
                     ("Battery", "USB" if battery > 100 else f"{battery}%" if battery else "-"), ("Position", position), ("Last heard", ago(node.get("last_heard")))):
            box.append(KeyValue(k, v, mono=k in ("Position",)))
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        buttons.set_margin_top(theme.dp(8))

        def message() -> None:
            dialog.close()
            self.open_route("chat/" + node.get("user_id", ""))

        def show() -> None:
            dialog.close()
            self.select_tab("map")
            screen = self.visible_screen()
            if hasattr(screen, "map") and node.get("latitude"):
                screen.map.center_on(node["latitude"], node["longitude"])
            elif not node.get("latitude"):
                self.toast(f"{name} has not shared a position.")

        buttons.append(outlined_button("Show on map", show))
        buttons.append(filled_button("Message", message))
        box.append(buttons)
        dialog.set_child(box)
        dialog.present(self.window)

    def on_banner(self, kind: str) -> None:
        """The SOS banner opens the SOS screen, the node banner the node's page (NodeLinkBanner.kt)."""
        self.open_route("sos" if kind == "sos" else "setup/node")

    # The SOS and the alarm test (SosController): the app's own record, and the Bridge's status.
    def stop_test(self) -> None:
        self.sos.cancel(self.state)

    def on_sos_change(self) -> bool:
        """The run changed (a route answered, a test settled): the banner, the screen on view,
        and the alarm test's notification (a real SOS is the notifier's, from the Bridge)."""
        run = self.sos.run
        if self.window is not None:
            self.show_sos_banner(self.state)
            screen = self.visible_screen()
            if screen is not None:
                screen.update(self.state)
        if run is not None and run.test:
            if run.active:
                from .model import sosrun  # noqa: PLC0415

                note = Gio.Notification.new("Alarm test running")
                note.set_body(sosrun.summary(run.routes))
                note.set_default_action("app.open-sos")
                note.add_button("Stop test", "app.stop-test")
                note.set_priority(Gio.NotificationPriority.HIGH)
                if not TEST:
                    self.send_notification("alarm-test", note)
                self._test_notified = run.id
            elif self._test_notified == run.id:
                self.withdraw_notification("alarm-test")
                self._test_notified = None
        return False

    def show_sos_banner(self, s: api.State) -> None:
        """SosBanner: a strip on every screen while an SOS or a test is on."""
        run = self.sos.active()
        bridge_sos = bool((s.sos or {}).get("active"))
        if run is not None and run.test:
            self.sos_banner.show("sos", "Alarm test running. Tap to see it.")
            self.sos_banner.add_css_class("test")
        elif bridge_sos or (run is not None and not run.test):
            self.sos_banner.remove_css_class("test")
            self.sos_banner.show("sos", "SOS is on. Tap to see where it went, or to cancel.")
        else:
            self.sos_banner.show(None)

    # Every poll: the strip, the banners, the screen on view
    def on_state(self, s: api.State) -> bool:
        self.state = s
        # While this window is the one in front, the notifier keeps quiet about new texts.
        if not TEST:
            flag = os.path.join(GLib.get_user_runtime_dir(), "meshsat-app-active")
            try:
                if self.window is not None and self.window.is_active():
                    with open(flag, "w", encoding="utf-8"):
                        pass
                elif os.path.exists(flag):
                    os.remove(flag)
            except OSError:
                pass
        bars = (s.signal or {}).get("bars", 0)
        if s.modem_connected():
            self.strip.set_lane("satellite", "working", f"{bars}/5", f"Satellite signal {bars} of 5")
        elif s.modem and s.modem.get("port") not in ("", "supervisor", None):
            self.strip.set_lane("satellite", "trying", "", "Satellite not connected")
        else:
            self.strip.set_lane("satellite", "off", "", "Satellite not connected")
        if s.mesh_connected():
            self.strip.set_lane("mesh", "working", str(len(s.others())), f"Mesh {words.count(len(s.others()), 'node')}")
        elif s.node_service or s.bridge_service:
            self.strip.set_lane("mesh", "trying", "", "Mesh not connected")
        else:
            self.strip.set_lane("mesh", "off", "", "Mesh not connected")
        hub_state, _detail = hub_lane(s)
        self.strip.set_lane("hub", hub_state)
        self.strip.set_lane("sms", "working" if s.sms_ready() else "off")
        self.strip.set_lane("location", "working" if s.position() else "off")

        self.sos.follow(s)
        self.show_sos_banner(s)
        verdict = s.watchdog.get("radio")
        if s.bridge is None and not s.bridge_service:
            self.node_banner.show("node", "The Bridge is not running on this phone. Tap to start it.")
        elif verdict in ("radio-not-answering", "cover-unreachable"):
            self.node_banner.show("node", s.watchdog.get("message") or "The radio in the back cover stopped answering. Re-seat the cover.")
        elif not s.mesh_connected() and s.unreachable_since and s.polled_at - s.unreachable_since > 12 and (s.node_mode() != "bluetooth" or (s.ble or {}).get("address")):
            # NodeLinkBanner.kt: "Cannot reach your MeshSat node[ since HH:mm][ (N min)]. Nothing
            # goes out by mesh or satellite. Tap to see." (shown once a node has ever been chosen)
            since = time.strftime("%H:%M", time.localtime(s.unreachable_since))
            minutes = int((s.polled_at - s.unreachable_since) // 60)
            self.node_banner.show("node", f"Cannot reach your MeshSat node since {since}" + (f" ({minutes} min)" if minutes >= 1 else "") + ". Nothing goes out by mesh or satellite. Tap to see.")
        else:
            self.node_banner.show(None)

        screen = self.visible_screen()
        if screen is not None:
            screen.update(s)
        if not getattr(self, "_opened", True):
            GLib.idle_add(self.open_window)
        return False


def hub_lane(s: api.State) -> tuple:
    """The Hub lane's state and words (HomeLanes.kt:217-222). The Bridge tells the app its Hub
    settings, not yet whether the link is up (MESHSAT Bridge change B12): with settings and no
    word on the link it is "trying", never "working" on a guess."""
    hub = s.hub or {}
    if not s.bridge or not hub.get("url"):
        return "off", "Scan the Hub's QR code to connect this phone."
    link = hub.get("link") or hub.get("state") or ""
    if link == "connected":
        return "working", f"Connected as {hub.get('bridge_id') or ''}."
    if link == "error":
        return "failed", "Cannot reach the Hub. It keeps trying by itself."
    if link == "disconnected":
        return "trying", "Not connected. It keeps trying by itself."
    return "trying", "Connecting to the Hub."


def signal_words(node: dict) -> str:
    """A node's signal as NodeDetailSheet shows it: the RSSI in dBm, with the SNR beside it."""
    rssi, snr = node.get("rssi"), node.get("snr")
    if rssi:
        return f"{rssi} dBm" + (f", SNR {snr:.1f} dB" if snr else "")
    if snr:
        return f"SNR {snr:.1f} dB"
    return "-"


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"meshsat-app {__version__}")
        return 0
    return MeshSatApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
