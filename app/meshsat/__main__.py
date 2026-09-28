# SPDX-License-Identifier: GPL-3.0-or-later
"""The app: the window every MeshSat app has (the status strip, the banners, the five tabs
with their own stacks, the navigation bar), night mode as the colour matrix Android applies,
and the few things the screens ask of it: push, pop, toast, copy, open a lane, pick a tab."""
import json
import os
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import __version__, api, theme  # noqa: E402
from .home import HomeScreen  # noqa: E402
from .mapview import MapScreen  # noqa: E402
from .messages import ChatScreen, MessagesScreen  # noqa: E402
from .people import PeopleScreen  # noqa: E402
from .passes import PassesScreen  # noqa: E402
from .setup import (AboutScreen, AdvancedScreen, HubScreen, IntegrationsScreen, MapsScreen, MessagingScreen, NodeScreen, RadioScreen,  # noqa: E402
                    SafetyScreen, SatelliteScreen, SetupScreen, SmsScreen, utc_clock)
from .widgets import Banner, Filtered, KeyValue, NavBar, StatusStrip, ago, filled_button, outlined_button, text  # noqa: E402

APP_ID = "net.meshsat.Bridge"
PREFS = os.path.join(GLib.get_user_config_dir(), "meshsat", "app.json")
TABS = (("home", "Home", HomeScreen), ("messages", "Messages", MessagesScreen), ("map", "Map", MapScreen), ("people", "People", PeopleScreen), ("setup", "Setup", SetupScreen))
# The Setup pages by name, for the `open` action (gapplication action net.meshsat.Bridge open "'node'").
SCREENS = {"node": NodeScreen, "satellite": SatelliteScreen, "passes": PassesScreen, "hub": HubScreen, "sms": SmsScreen, "safety": SafetyScreen, "messaging": MessagingScreen,
           "maps": MapsScreen, "integrations": IntegrationsScreen, "radio": RadioScreen, "advanced": AdvancedScreen, "about": AboutScreen}
TABS_BY_KEY = {key for key, _title, _cls in TABS}


class MeshSatApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        self.poller = api.Poller(self.on_state)
        self.state = self.poller.state
        self.night = False
        self.tabs = {}
        self.current = "home"
        for name, handler, accel in (("quit", lambda *_: self.quit(), "<Control>q"), ("night", lambda *_: self.toggle_night(), "<Control>n"), ("refresh", lambda *_: self.poller.poll_now(), "F5")):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)
            self.set_accels_for_action(f"app.{name}", [accel])
        # With a string: pick a tab, or open a Setup page. Reachable over D-Bus, as any GApplication
        # action (gapplication action net.meshsat.Bridge tab "'messages'"), which is how the parity
        # captures are taken.
        for name, handler in (("tab", lambda _a, p: self.select_tab(p.get_string())), ("open", lambda _a, p: self.open_screen(p.get_string()))):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", handler)
            self.add_action(action)

    # Lifecycle
    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        theme.apply()
        prefs = self.prefs()
        self.night = bool(prefs.get("night", False))
        entered = prefs.get("position")
        if isinstance(entered, list) and len(entered) == 2:
            self.state.entered = (float(entered[0]), float(entered[1]))
        contacts = prefs.get("contacts")
        if isinstance(contacts, list):
            self.state.contacts = [c for c in contacts if isinstance(c, dict) and c.get("phone")]
        self.state.sos_name = str(prefs.get("sos_name", ""))
        self.locate()

    def set_contacts(self, contacts: list) -> None:
        self.state.contacts = contacts
        self.save_prefs(contacts=contacts)

    def set_sos_name(self, name: str) -> None:
        self.state.sos_name = name.strip()
        self.save_prefs(sos_name=self.state.sos_name)

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
        self.save_prefs(position=[lat, lon])

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
        Adw.Application.do_shutdown(self)

    def prefs(self) -> dict:
        try:
            with open(PREFS, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    def save_prefs(self, **values) -> None:
        prefs = self.prefs()
        prefs.update(values)
        try:
            os.makedirs(os.path.dirname(PREFS), exist_ok=True)
            with open(PREFS, "w", encoding="utf-8") as handle:
                json.dump(prefs, handle)
        except OSError:
            pass

    # The window: strip, banners, the tab stacks, the bar. The same on a 360 px phone and a desktop.
    def build_window(self) -> None:
        self.window = Adw.ApplicationWindow(application=self, title="MeshSat", default_width=360, default_height=720)
        self.window.set_size_request(320, 480)
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
            GLib.timeout_add_seconds(5, self.debug_sizes)

    def debug_sizes(self) -> bool:
        """MESHSAT_APP_DEBUG=1: every 5 s, the window's size and each widget on view whose
        minimum width is more than the screen affords, on stderr: what widens the window."""
        surface = self.window.get_surface()
        print(f"-- {self.current}: window {self.window.get_width()}x{self.window.get_height()}, scale {self.window.get_scale_factor()}, "
              f"surface {surface.get_width() if surface else 0}x{surface.get_height() if surface else 0}", file=sys.stderr)
        limit = self.window.get_width() - 40

        def walk(widget, depth):
            if not widget.get_visible():
                return
            minimum, natural, _b1, _b2 = widget.measure(Gtk.Orientation.HORIZONTAL, -1)
            if minimum > limit or depth < 3:
                print(f"{'  ' * depth}{type(widget).__name__} .{' .'.join(widget.get_css_classes()) or '-'} allocated {widget.get_width()} min {minimum} nat {natural}", file=sys.stderr)
            child = widget.get_first_child()
            while child is not None:
                walk(child, depth + 1)
                child = child.get_next_sibling()

        walk(self.window, 0)
        screen = self.visible_screen()
        if hasattr(screen, "map"):  # the map and everything around it, whatever their size
            def walk_all(widget, depth):
                minimum, natural, _b1, _b2 = widget.measure(Gtk.Orientation.HORIZONTAL, -1)
                print(f"{'  ' * depth}{type(widget).__name__} .{' .'.join(widget.get_css_classes()) or '-'} allocated {widget.get_width()}x{widget.get_height()} min {minimum} nat {natural} visible {widget.get_visible()} hexpand {widget.get_hexpand()}", file=sys.stderr)
                child = widget.get_first_child()
                while child is not None and depth < 8:
                    walk_all(child, depth + 1)
                    child = child.get_next_sibling()
            walk_all(screen, 0)
        return True

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
        if self.state.polled_at:
            self.visible_screen().update(self.state)

    def push(self, screen: Gtk.Widget, title: str = "MeshSat") -> None:
        self.tabs[self.current].push(Adw.NavigationPage.new(screen, title))

    def pop(self) -> None:
        self.tabs[self.current].pop()

    def pop_to_root(self) -> None:
        nav = self.tabs[self.current]
        stack = nav.get_navigation_stack()
        if stack.get_n_items() > 1:
            nav.pop_to_page(stack.get_item(0))

    def open_lane(self, lane: str) -> None:
        self.open_screen({"mesh": "node", "satellite": "satellite", "hub": "hub", "sms": "sms"}.get(lane, ""))

    def open_screen(self, name: str) -> None:
        if name in TABS_BY_KEY:
            self.select_tab(name)
            self.pop_to_root()
            return
        if name == "everyone":  # the mesh's broadcast chat
            self.select_tab("messages")
            self.pop_to_root()
            self.push(ChatScreen(self, "!ffffffff", "Everyone on the mesh", "mesh"))
            return
        screen = SCREENS.get(name)
        if screen is None:
            return
        self.select_tab("setup")
        self.pop_to_root()
        self.push(screen(self))

    def toggle_night(self) -> None:
        self.night = not self.night
        self.filter.on = self.night
        self.filter.queue_draw()
        self.save_prefs(night=self.night)

    def toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.toasts.add_toast(toast)

    def copy(self, value: str) -> None:
        self.window.get_clipboard().set(value)
        self.toast("Copied")

    def node_sheet(self, node: dict) -> None:
        """A node's card, as the sheet the Android People screen opens: who, how well heard,
        where, and the two things to do with them."""
        name = node.get("long_name") or node.get("short_name") or node.get("user_id", "?")
        dialog = Adw.Dialog(title=name, content_width=360)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        box.add_css_class("sheet")
        box.append(text(name, "title-large"))
        box.append(text(node.get("user_id", ""), "body-medium", theme.TEXT_SECONDARY, mono=True))
        battery = node.get("battery_level") or 0
        position = f"{node['latitude']:.5f}, {node['longitude']:.5f}" if node.get("latitude") else "Unknown"
        for k, v in (("Hardware", node.get("hw_model_name") or "-"), ("Signal", f"{node['snr']:.1f} dB" if node.get("snr") else "-"),
                     ("Battery", "USB" if battery > 100 else f"{battery}%" if battery else "-"), ("Position", position), ("Last heard", ago(node.get("last_heard")))):
            box.append(KeyValue(k, v, mono=k in ("Position",)))
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        buttons.set_margin_top(theme.dp(8))

        def message() -> None:
            dialog.close()
            self.select_tab("messages")
            self.pop_to_root()
            self.push(ChatScreen(self, node.get("user_id"), name, "mesh"))

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
        if kind == "sos":
            self.select_tab("setup")
            self.pop_to_root()
            self.push(SafetyScreen(self))
        else:
            self.open_lane("mesh")

    # Every poll: the strip, the banners, the screen on view
    def on_state(self, s: api.State) -> bool:
        self.state = s
        own = s.own_node() or {}
        if s.modem_connected():
            self.strip.set_lane("satellite", "working", f"{(s.signal or {}).get('bars', 0)}/5")
        elif s.modem and s.modem.get("port") not in ("", "supervisor", None):
            self.strip.set_lane("satellite", "trying")
        else:
            self.strip.set_lane("satellite", "off")
        if s.mesh_connected():
            self.strip.set_lane("mesh", "working", str(len(s.others())))
        elif s.node_service or s.bridge_service:
            self.strip.set_lane("mesh", "trying")
        else:
            self.strip.set_lane("mesh", "off")
        hub = s.hub or {}
        self.strip.set_lane("hub", "working" if hub.get("bridge_id") else "trying" if hub.get("url") else "off")
        self.strip.set_lane("sms", "working" if s.sms_ready() else "off")
        self.strip.set_lane("location", "working" if s.position() else "off")

        sos = s.sos or {}
        if sos.get("active"):
            self.sos_banner.show("sos", f"SOS is on since {utc_clock(sos.get('started_at'))}. Tap to cancel when you are safe.")
        else:
            self.sos_banner.show(None)
        verdict = s.watchdog.get("radio")
        if s.bridge is None and not s.bridge_service:
            self.node_banner.show("node", "The Bridge is not running on this phone. Tap to start it.")
        elif verdict in ("radio-not-answering", "cover-unreachable"):
            self.node_banner.show("node", s.watchdog.get("message") or "The radio in the back cover stopped answering. Re-seat the cover.")
        elif not s.mesh_connected() and s.unreachable_since and s.polled_at - s.unreachable_since > 12:
            self.node_banner.show("node", "Your MeshSat node cannot be reached. Tap to see why.")
        else:
            self.node_banner.show(None)

        screen = self.visible_screen()
        if screen is not None:
            screen.update(s)
        if not getattr(self, "_opened", True):
            GLib.idle_add(self.open_window)
        return False


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"meshsat-app {__version__}")
        return 0
    return MeshSatApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
