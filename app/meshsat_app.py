#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""MeshSat for Linux phones and desktops.

The MeshSat Bridge runs on this machine as a service and serves its interface on
127.0.0.1:6050; the Meshtastic daemon that drives the LoRa radio serves its API on 4403.
This app is that interface in a window of its own, sized for a phone and fine on a
desktop, with a status page while a service is not running: which one, what the radio
watchdog says (a back cover whose radio stopped answering must be re-seated by hand), and
a button to start the services.
"""
import json
import os
import subprocess
import sys
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gio, GLib, Gtk, WebKit  # noqa: E402

APP_ID = "net.meshsat.Bridge"
VERSION = "0.1.1"
BRIDGE_URL = os.environ.get("MESHSAT_APP_URL", "http://127.0.0.1:6050/")
STATUS_PATH = os.environ.get("MESHSAT_APP_STATUS", "/run/meshsat-node/status")
SERVICES = ("meshtasticd.service", "meshsat-bridge.service")

# The daemon's API port (4403) is never touched from here: meshtasticd keeps one TCP client
# at a time and drops the previous one for every new connection, so a mere "is the port open"
# probe would throw the Bridge off its session every few seconds (seen on 28 Sep 2026). The
# node's state comes from systemd and from the Bridge's own status page instead.


def bridge_status() -> dict | None:
    """The Bridge's /api/status, or None when the Bridge does not answer."""
    try:
        with urllib.request.urlopen(BRIDGE_URL.rstrip("/") + "/api/status", timeout=1.5) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def unit_active(unit: str) -> bool:
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def read_status() -> dict:
    """What the radio watchdog last wrote, or nothing."""
    try:
        with open(STATUS_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="MeshSat", default_width=390, default_height=780)
        self.set_size_request(320, 480)
        self.showing = ""

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu = Gio.Menu()
        menu.append("Reload", "app.reload")
        menu.append("Open in browser", "app.browser")
        menu.append("Start services", "app.start")
        menu.append("About MeshSat", "app.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu"))
        view.add_top_bar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        view.set_content(self.stack)

        self.web = WebKit.WebView()
        settings = self.web.get_settings()
        settings.set_enable_javascript(True)
        settings.set_javascript_can_access_clipboard(True)
        settings.set_enable_developer_extras(False)
        self.stack.add_named(self.web, "web")

        self.status = Adw.StatusPage(icon_name="network-wireless-symbolic", title="MeshSat")
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_start=16, margin_end=16)
        self.node_row = Gtk.Label(xalign=0, wrap=True)
        self.bridge_row = Gtk.Label(xalign=0, wrap=True)
        self.radio_row = Gtk.Label(xalign=0, wrap=True)
        self.radio_row.add_css_class("dim-label")
        for row in (self.node_row, self.bridge_row, self.radio_row):
            rows.append(row)
        start = Gtk.Button(label="Start services", halign=Gtk.Align.CENTER)
        start.add_css_class("suggested-action")
        start.add_css_class("pill")
        start.set_action_name("app.start")
        rows.append(start)
        self.status.set_child(rows)
        self.stack.add_named(self.status, "status")

        self.set_content(view)
        self.refresh()
        GLib.timeout_add_seconds(3, self.refresh)

    def refresh(self) -> bool:
        bridge = bridge_status()
        if bridge is not None:
            if self.showing != "web":
                self.web.load_uri(BRIDGE_URL)
                self.stack.set_visible_child_name("web")
                self.showing = "web"
            return True
        status = read_status()
        daemon = unit_active("meshtasticd.service")
        self.node_row.set_markup(
            "<b>Node (meshtasticd):</b> " + ("running" if daemon else "not running")
        )
        self.bridge_row.set_markup("<b>Bridge:</b> not running")
        radio = status.get("radio", "")
        message = status.get("message", "")
        if radio in ("radio-not-answering", "cover-unreachable"):
            self.radio_row.set_markup("<b>Radio:</b> " + GLib.markup_escape_text(message))
        elif message:
            self.radio_row.set_text("Radio: " + message)
        else:
            self.radio_row.set_text("Radio: no word from the watchdog yet")
        self.status.set_description("The Bridge's interface appears here as soon as its service is up.")
        if self.showing != "status":
            self.stack.set_visible_child_name("status")
            self.showing = "status"
        return True


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        for name, handler in (("reload", self.on_reload), ("browser", self.on_browser), ("start", self.on_start), ("about", self.on_about)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

    def do_activate(self):
        win = self.props.active_window or Window(self)
        win.present()

    def on_reload(self, *_):
        win = self.props.active_window
        if win and win.showing == "web":
            win.web.reload()
        elif win:
            win.refresh()

    def on_browser(self, *_):
        Gio.AppInfo.launch_default_for_uri(BRIDGE_URL, None)

    def on_start(self, *_):
        # polkit asks the user for the password through the shell's agent.
        try:
            subprocess.Popen(["pkexec", "systemctl", "start", *SERVICES])
        except OSError as error:
            win = self.props.active_window
            if win:
                win.radio_row.set_text(f"Could not start the services: {error}. Run: sudo systemctl start {' '.join(SERVICES)}")

    def on_about(self, *_):
        about = Adw.AboutDialog(
            application_name="MeshSat",
            application_icon=APP_ID,
            developer_name="MeshSat",
            version=VERSION,
            website="https://meshsat.net",
            issue_url="https://github.com/meshsat/meshsat-linux/issues",
            license_type=Gtk.License.GPL_3_0,
            comments="The MeshSat Bridge on this device: a router between the LoRa mesh and the satellite, "
            "with the LoRa back cover as a Meshtastic node. Keeping people connected when the network is not.",
        )
        about.present(self.props.active_window)


def main() -> int:
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
