# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup and its pages, as ui/screens/SetupScreen.kt and SettingsScreen.kt: the flat list
in three groups, and one page of cards per row. This edition: the node is the LoRa back
cover driven by meshtasticd on this phone, the satellite modem is a RockBLOCK on USB-C, and
there is no SMS row (the phone's own modem is not the app's)."""
import threading
import time
import urllib.parse

from gi.repository import Adw, GLib, Gtk

from . import __version__ as VERSION
from . import api, system, theme
from .layout import body_text
from .model import hub as hub_model
from .model import nodes as nodes_model
from .model import satellite as satellite_model
from .pages.safety import SafetyScreen  # noqa: F401  (the Setup row and the route table use it)
from .passes import PassesScreen
from .screen import Screen, SubScreen
from .mailbox import MailboxButton
from .widgets import KeyValue, NavRow, SwitchRow, clear, divider, fact_row, filled_button, group_title, name_widget, outlined_button, page, paint, scroller, text, text_button, when

# Meshtastic's LoRa config, as the Bridge relays it: protobuf field numbers of Config.LoRaConfig.


class SetupScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        column = page(spacing=0, padded=False)
        title = text("Setup", "headline-medium")
        title.set_margin_start(theme.dp(16))
        title.set_margin_top(theme.dp(16))
        column.append(title)
        column.append(group_title("Get connected"))
        self.node = NavRow("outlined-bluetooth", "Your MeshSat node", lambda: app.push(NodeScreen(app)), theme.MESH)
        self.satellite = NavRow("transport-satellite", "Satellite", lambda: app.push(SatelliteScreen(app)), theme.IRIDIUM)
        self.hub = NavRow("outlined-cloud", "Hub", lambda: app.open_route("setup/hub"), theme.HUB)
        self.sms = NavRow("outlined-sms", "SMS", lambda: app.push(SmsScreen(app)), theme.SMS)
        for row in (self.node, self.satellite, self.hub, self.sms):
            column.append(row)
        column.append(group_title("Using MeshSat"))
        rows = (
            ("outlined-health-and-safety", "Safety", "SOS, check-in timer, zones", lambda: app.push(SafetyScreen(app))),
            ("outlined-lock", "Messaging", "Encryption, compression, quick messages", lambda: app.open_route("setup/messaging")),
            ("outlined-map", "Maps", "Offline maps for when there is no internet", lambda: app.open_route("setup/maps")),
            ("outlined-radio", "Ham radio, TAK and Reticulum", "Other networks MeshSat can bridge", lambda: app.open_route("setup/integrations")),
            ("outlined-tune", "Mesh radio settings", "Region, channels, transmit power", lambda: app.open_route("radio-config")),
        )
        for name, title_text, detail, action in rows:
            row = NavRow(name, title_text, action)
            row.set_detail(detail)
            column.append(row)
        column.append(group_title("For experts"))
        advanced = NavRow("outlined-build", "Advanced", lambda: app.push(AdvancedScreen(app)))
        advanced.set_detail("Routing, links, queue, logs, diagnostics")
        column.append(advanced)
        about = NavRow("outlined-info", "About", lambda: app.open_route("about"))
        about.set_detail(f"MeshSat Linux {VERSION}")
        column.append(about)
        self.append(scroller(column))

    def update(self, s: api.State) -> None:
        ble = s.ble or {}
        if s.mesh_connected():
            self.node.set_detail("Connected", "green")
        elif s.node_mode() == "bluetooth":
            # SetupScreen.kt: "Connecting" while scanning or connecting, else "Not connected. Pair it here."
            if ble.get("mode") in ("scanning", "pairing", "connecting"):
                self.node.set_detail("Connecting", "amber")
            else:
                self.node.set_detail("Not connected. Pair it here.", "muted")
        elif s.node_service:
            self.node.set_detail("Connecting", "amber")
        else:
            self.node.set_detail("Not connected. Start it here.", "muted")
        if s.modem_connected():
            self.satellite.set_detail(f"Modem ready, signal {(s.signal or {}).get('bars', 0)} of 5", "green")
        elif not s.mesh_connected():
            self.satellite.set_detail("Connect your node first", "muted")
        elif s.modem and s.modem.get("port") not in ("", "supervisor"):
            self.satellite.set_detail("Checking the modem", "amber")
        else:
            self.satellite.set_detail("No modem on this radio", "muted")
        self.hub.set_detail(*hub_model.setup_row(s.hub if s.bridge else None))
        if s.sms_ready():
            self.sms.set_detail("Allowed", "green")
        else:
            self.sms.set_detail(s.sms_reason() or "Not allowed yet", "muted")


# A sub-screen: the '<- Title' row and a column of cards 16 px apart (screen.SubScreen).
Page = SubScreen


class NodeScreen(Page):
    """Your MeshSat node: the LoRa back cover this phone carries, or a node over Bluetooth
    (the "Bluetooth connection" card of SettingsScreen.kt, word for word). Which of the two,
    the package's meshsat-hardware decided when the phone booted; the last card asks it again."""

    def __init__(self, app):
        super().__init__(app, "Your MeshSat node")
        self.devices = None
        self.scanning = False
        self.pin_asked_for = None
        self.battery_readings = []  # (at, level) of the node's last three hours (GET /api/telemetry)
        # The LoRa back cover, when this phone has one: drawn as Android's Bluetooth card is (its
        # ConnectionStatusRow, InfoRows 8 dp apart, the node rows and a bodySmall button).
        self.cover = self.card("The LoRa back cover")
        row, self.status = status_row("Status")
        self.cover.append(row)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.cover.append(self.details)
        self.action = body_text(filled_button("Start the node", self.start))
        self.cover.append(self.action)
        self.note = text("The node is meshtasticd on this phone, driving the Pine64 LoRa back cover through its pogo pins. It starts with the phone.", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.cover.append(self.note)
        # A node over Bluetooth, as on the other apps.
        self.bt = self.card("Bluetooth connection")
        row, self.bt_status = status_row("Status")
        self.bt.append(row)
        self.bt_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.bt.append(self.bt_body)
        # Which of the two this device has.
        self.device = self.card("This device")
        self.device_node = KeyValue("Node", "")
        self.device.append(self.device_node)
        self.device_why = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.device.append(self.device_why)
        self.device.append(outlined_button("Look for a LoRa back cover again", self.check_hardware))
        self.update(app.state)

    def start(self) -> None:
        system.privileged("systemctl", "restart", "meshtasticd.service", "meshsat-bridge.service")
        self.app.toast("Starting the node")

    def check_hardware(self) -> None:
        self.app.toast("Looking for the cover")

        def run() -> None:
            error = api.check_hardware()
            found = api.hardware().get("node", "")
            GLib.idle_add(lambda: self.app.toast(error or {"cover": "The LoRa back cover is this phone's node.", "bluetooth": "No LoRa back cover: connect a node over Bluetooth."}.get(found, "Checked.")) or False)

        threading.Thread(target=run, daemon=True).start()

    def update(self, s: api.State) -> None:
        mode = s.node_mode()
        self.cover.set_visible(mode == "cover")
        self.bt.set_visible(mode == "bluetooth")
        hw = s.hardware
        self.device_node.value.set_text("The LoRa back cover" if mode == "cover" else "A node over Bluetooth")
        why = hw.get("why", "")
        why = why[:1].upper() + why[1:]
        if hw.get("model"):
            why = f"{why} ({hw['model']})" if why else hw["model"]
        self.device_why.set_text(why)
        self.device_why.set_visible(bool(why))
        if mode == "cover":
            self.update_cover(s)
        else:
            self.update_bluetooth(s)

    def on_show(self) -> None:
        super().on_show()
        self.every(60, self.load_battery)

    def load_battery(self) -> None:
        """The node's battery readings of the last three hours, which the Bridge keeps: the time
        left comes from them, as Android's NodeBattery estimates it from its own."""
        s = self.app.state
        node = (s.own_node() or {}).get("user_id") or (s.bridge or {}).get("node_id")
        if not node:
            return
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - nodes_model.WINDOW_S))
        self.fetch(f"/api/telemetry?node={urllib.parse.quote(node)}&since={since}&limit=1000", self.battery_loaded)

    def battery_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.battery_readings = nodes_model.readings_of(answer.body.get("telemetry") or [])
            self.update(self.app.state)

    def hours_left(self) -> float | None:
        return nodes_model.hours_left(self.battery_readings, time.time())

    def update_cover(self, s: api.State) -> None:
        clear(self.details)
        if s.mesh_connected():
            self.show_status(self.status, "Connected")
            b = s.bridge or {}
            own = s.own_node() or {}
            for k, v in (("Firmware", b.get("firmware_version", "")), ("Node ID", b.get("node_id", "")), ("Name", b.get("node_name") or own.get("long_name", "")),
                         ("Hardware", b.get("hw_model_name", "")), ("Reboots", str(b.get("reboot_count", 0)))):
                self.details.append(fact_row(k, v))
            mesh_node_rows(self.details, s.nodes)
            self.action.set_label("Restart the node")
        elif s.node_service:
            self.show_status(self.status, "Connecting...")
            self.action.set_label("Restart the node")
        else:
            self.show_status(self.status, "Disconnected")
            self.action.set_label("Start the node")
        radio = s.watchdog.get("radio")
        if radio in ("radio-not-answering", "cover-unreachable"):
            self.details.append(text(s.watchdog.get("message", ""), "body-medium", theme.AMBER, wrap=True))
        self.details.set_visible(self.details.get_first_child() is not None)

    @staticmethod
    def show_status(label: Gtk.Label, value: str) -> None:
        """ConnectionStatusRow's value: Green when connected, else TextMuted."""
        label.set_text(value)
        paint(label, theme.GREEN if value == "Connected" else theme.TEXT_MUTED)

    # SettingsScreen.kt:384-525: Status; while disconnected "Scan for Meshtastic devices" and
    # "Found devices:" with a row per device (its name, its address, Connect); when connected
    # Firmware, Node ID, Battery, Reboots, Mesh Nodes and Disconnect. What is not happening says
    # the Status row alone (the node banner says a lost link). This edition's own: the PIN (Android's
    # system asks for it there) and "Forget this node" (the system keeps the bonds there).
    def update_bluetooth(self, s: api.State) -> None:
        ble = s.ble or {}
        b = s.bridge or {}
        state = ble.get("mode", "idle")
        if s.mesh_connected():
            status = "Connected"
        elif self.scanning:
            status = "Scanning..."
        elif state in ("scanning", "pairing", "connecting") or (state == "ready" and not ble.get("connected")):
            status = "Connecting..."
        else:
            status = "Disconnected"
        self.show_status(self.bt_status, status)
        if ble.get("pairing_pending") and self.pin_asked_for != ble.get("pairing_since"):
            self.pin_asked_for = ble.get("pairing_since")
            self.ask_pin(ble)
        # Rebuilt only when what it shows changes: a poll that brings the same state must not
        # replace the buttons under a person's finger (or a test's click).
        own = s.own_node() or {}
        key = (status, b.get("firmware_version"), b.get("node_id"), b.get("reboot_count"),
               nodes_model.describe(own.get("battery_level"), own.get("voltage"), self.hours_left()),
               tuple(((n.get("long_name") or "").strip() or n.get("user_id", ""), (n.get("short_name") or "").strip()) for n in (s.nodes or [])),
               state == "pairing" or bool(ble.get("pairing_pending")), ble.get("name"), ble.get("address"),
               None if self.devices is None else tuple((d.get("name"), d.get("address")) for d in self.devices))
        if key == getattr(self, "_bt_key", None):
            return
        self._bt_key = key
        clear(self.bt_body)
        self.bt_body.set_visible(True)
        if s.mesh_connected():
            own = s.own_node() or {}
            rows = [("Firmware", b.get("firmware_version", "")), ("Node ID", b.get("node_id", ""))]
            battery = nodes_model.describe(own.get("battery_level"), own.get("voltage"), self.hours_left())
            if battery:
                rows.append(("Battery", battery))
            if b.get("reboot_count"):
                rows.append(("Reboots", str(b["reboot_count"])))
            for k, v in rows:
                if v:
                    self.bt_body.append(fact_row(k, v))
            mesh_node_rows(self.bt_body, s.nodes)
            # Button(containerColor = MeshSatRed, fillMaxWidth) with bodySmall ink text, as the
            # 9704's Disconnect on the Satellite page.
            disconnect = body_text(filled_button("Disconnect", self.disconnect))
            disconnect.add_css_class("red-fill")
            self.bt_body.append(disconnect)
            return
        if state == "pairing" or ble.get("pairing_pending"):
            self.bt_body.append(text(f"Pairing with {ble.get('name') or ble.get('address') or 'the node'}: enter the PIN shown on its screen.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
            self.bt_body.append(outlined_button("Enter the PIN", lambda: self.ask_pin(ble)))
        if status == "Disconnected":
            self.bt_body.append(body_text(filled_button("Scan for Meshtastic devices", self.scan)))
            if self.devices:
                self.bt_body.append(text("Found devices:", "body-small", theme.TEXT_MUTED))
                for dev in self.devices:
                    self.bt_body.append(self.device_row(dev))
        if ble.get("address"):
            forget = text_button("Forget this node", self.forget)
            self.bt_body.append(forget)
        self.bt_body.set_visible(self.bt_body.get_first_child() is not None)

    def device_row(self, dev: dict) -> Gtk.Widget:
        """DeviceRow: the name in bodyMedium over the address in bodySmall TextMuted, "Connect" in
        bodySmall Signal Orange at the right, 8 dp inside a strip of the card's own colour (so only
        its inset shows); a tap anywhere on it connects. "Connect" is also a button of its own, so a
        screen reader and the tests find one per device after the device's name."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        for side in ("start", "end", "top", "bottom"):
            getattr(row, f"set_margin_{side}")(theme.dp(8))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        names.set_hexpand(True)
        names.set_valign(Gtk.Align.CENTER)
        names.append(text(dev.get("name") or "Unknown", "body-medium", ellipsize=True))
        names.append(text(dev.get("address", ""), "body-small", theme.TEXT_MUTED))
        row.append(names)
        connect = Gtk.Button()
        connect.add_css_class("flat")
        connect.set_child(text("Connect", "body-small", theme.SIGNAL_ORANGE))
        name_widget(connect, "Connect")
        connect.set_valign(Gtk.Align.CENTER)
        connect.connect("clicked", lambda *_: self.connect_node(dev))
        row.append(connect)

        def tapped(_gesture, _n, x: float, y: float) -> None:
            target = row.pick(x, y, Gtk.PickFlags.DEFAULT)
            if target is not None and (target is connect or target.is_ancestor(connect)):
                return  # the button's own click
            self.connect_node(dev)

        tap = Gtk.GestureClick()
        tap.connect("released", tapped)
        row.add_controller(tap)
        return row

    def scan(self) -> None:
        if self.scanning:
            return
        self.scanning = True
        self.update(self.app.state)

        def run() -> None:
            result = api.ble_scan(8)

            def done() -> bool:
                self.scanning = False
                if result is None or result.get("error"):
                    self.devices = []
                    self.app.toast((result or {}).get("error") or "The Bridge is not answering.")
                else:
                    self.devices = result.get("devices") or []
                self.update(self.app.state)
                return False

            GLib.idle_add(done)

        threading.Thread(target=run, daemon=True).start()

    def connect_node(self, dev: dict) -> None:  # not `connect`: that is the widget's own signal method
        self.devices = None
        self.app.toast(f"Connecting to {dev.get('name') or dev.get('address')}")
        self.update(self.app.state)

        def done(answer: api.Answer) -> None:
            if not answer.ok:
                self.app.toast(answer.error or "The node could not be connected.")
            self.app.poller.poll_now()

        # The Bridge answers once the link is up or given up: up to 45 s, off the main loop.
        self.call("/api/mesh/ble/connect", done, body={"address": dev.get("address", "")}, timeout=45.0)

    def disconnect(self) -> None:
        self.call("/api/mesh/ble", lambda answer: (self.app.toast(answer.error if not answer.ok else "Disconnected"), self.app.poller.poll_now()), method="DELETE", timeout=15.0)

    def forget(self) -> None:
        self.devices = None
        self.call("/api/mesh/ble?bond=1", lambda answer: (self.app.toast(answer.error if not answer.ok else "The node is forgotten"), self.app.poller.poll_now()), method="DELETE", timeout=15.0)

    def ask_pin(self, ble: dict) -> None:
        """The node shows a six-digit PIN ("Enter this code" on its screen); the Bridge's
        pairing waits for it."""
        who = ble.get("name") or ble.get("address") or "the node"
        dialog = Adw.Dialog(title=f"Pair with {who}", content_width=340)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        box.add_css_class("sheet")
        box.append(text(f"Pair with {who}", "dialog-title"))
        box.append(text("Enter the PIN shown on the node's screen.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        entry = Gtk.Entry(placeholder_text="6 digits", input_purpose=Gtk.InputPurpose.DIGITS, max_length=6)
        entry.add_css_class("field")
        box.append(entry)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        buttons.set_halign(Gtk.Align.END)
        cancel = text_button("Cancel", dialog.close)
        buttons.append(cancel)

        def pair() -> None:
            pin = "".join(ch for ch in entry.get_text() if ch.isdigit())
            if len(pin) != 6:
                self.app.toast("Enter 6 digits.")
                return
            dialog.close()
            self.app.toast("Pairing")

            def done(answer: api.Answer) -> None:
                if not answer.ok:
                    self.app.toast(answer.error or "Pairing failed.")
                self.app.poller.poll_now()

            self.call("/api/mesh/ble/pair", done, body={"pin": pin}, timeout=10.0)

        buttons.append(text_button("Pair", pair))
        entry.connect("activate", lambda *_: pair())
        box.append(buttons)
        dialog.set_child(box)
        dialog.present(self.app.window)


class SatelliteScreen(Page):
    """Setup > Satellite (SettingsScreen.kt:528-733): the passes row, the modem's card with its
    status, what it said about itself, Poll Signal and Check Mailbox, then the 9704's card,
    folded away until a 9704 is there. The modem here is a RockBLOCK 9603 on USB-C."""

    SIGNAL_TIMEOUT = 65.0  # a fresh reading (AT+CSQ) can take up to a minute

    def __init__(self, app):
        super().__init__(app, "Satellite")
        # SetupPageLinks (MeshSatUI.kt:250): the row full width under the '<- Satellite' row, and
        # fixed there while the cards scroll under it.
        passes = NavRow("outlined-schedule", "Satellite passes", lambda: app.push(PassesScreen(app)))
        passes.set_detail("When satellites are high overhead")
        self.insert_child_after(passes, self.header)
        self.sbd, self.sbd_bars, self.imt, self.imt_bars = None, 0, None, 0
        self.show_imt = False

        # A node over Bluetooth with its modem pipe (B9): Android's two cards; else the USB card
        self.node_card = self.card(satellite_model.NODE_TITLE)
        self.node_status, self.node_status_text = status_row(satellite_model.STATUS)
        self.node_card.append(self.node_status)
        self.use_node = SwitchRow(satellite_model.USE_NODE_MODEM, self.set_use_node)
        self.node_card.append(self.use_node)
        self.node_details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.node_card.append(self.node_details)
        self.node_poll = filled_button(satellite_model.POLL_SIGNAL, self.poll_signal)
        self.node_poll.add_css_class("small-text")
        self.node_card.append(self.node_poll)
        self.node_mailbox = MailboxButton(self)
        self.node_card.append(self.node_mailbox)
        self.node_note = text(satellite_model.NO_NODE_NOTE, "body-small", theme.TEXT_MUTED, wrap=True)
        self.node_card.append(self.node_note)
        self.health_card = self.card(satellite_model.HEALTH_TITLE)
        self.health_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.health_card.append(self.health_rows)
        self.health_warning = text("", "body-small", theme.AMBER, wrap=True)
        self.health_card.append(self.health_warning)
        self.health_card.append(text(satellite_model.HEALTH_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        self.stats, self.has_stats = None, False

        card = self.card(satellite_model.USB_TITLE)
        self.usb_card = card
        self.status, self.status_text = status_row(satellite_model.STATUS)
        card.append(self.status)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        card.append(self.details)
        self.poll = body_text(filled_button(satellite_model.POLL_SIGNAL, self.poll_signal))
        card.append(self.poll)
        self.mailbox = MailboxButton(self)
        card.append(self.mailbox)
        self.note = text(satellite_model.USB_NOTE, "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.note)

        self.imt_fold = text_button(satellite_model.IMT_FOLD, self.unfold_imt)
        self.imt_fold.add_css_class("off-white")
        self.imt_fold.set_halign(Gtk.Align.START)
        self.column.append(self.imt_fold)
        self.imt_card = self.card(satellite_model.IMT_TITLE)
        self.imt_status, self.imt_status_text = status_row(satellite_model.STATUS)
        self.imt_card.append(self.imt_status)
        self.imt_details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.imt_card.append(self.imt_details)
        self.imt_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        poll = body_text(filled_button(satellite_model.POLL_SIGNAL, self.poll_imt_signal))
        self.imt_buttons.append(poll)
        off = body_text(filled_button(satellite_model.DISCONNECT, self.disconnect_imt))
        off.add_css_class("red-fill")
        self.imt_buttons.append(off)
        self.imt_card.append(self.imt_buttons)
        self.imt_note = text(satellite_model.IMT_PLUG, "body-small", theme.TEXT_MUTED, wrap=True)
        self.imt_card.append(self.imt_note)
        self.render()

    def on_show(self) -> None:
        self.every(5, self.load)
        self.every(10, self.load_stats)
        self.mailbox.load()
        self.node_mailbox.load()

    def load_stats(self) -> None:
        if self.app.state.node_mode() == "bluetooth" and (self.app.state.ble or {}).get("satellite_pipe"):
            self.fetch("/api/mesh/ble/satellite/stats", self.stats_loaded)

    def stats_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.stats, self.has_stats = answer.body, True
        elif answer.status == 404:
            self.stats, self.has_stats = None, False
        self.render()

    def set_use_node(self, on: bool) -> None:
        """Use the node's modem: off hands it to the node at once, on takes it (GatewayService.kt:2863-2903)."""
        self.call("/api/mesh/ble/satellite", lambda a: None if a.ok else self.app.toast(a.error or "The Bridge did not take it."),
                  body={"enabled": on}, method="PUT")

    def load(self) -> None:
        self.fetch("/api/iridium/modem?type=sbd", lambda a: self.loaded("sbd", a))
        self.fetch("/api/iridium/signal/fast?type=sbd", lambda a: self.signal_loaded("sbd", a))
        self.fetch("/api/iridium/modem?type=imt", lambda a: self.loaded("imt", a))
        self.fetch("/api/iridium/signal/fast?type=imt", lambda a: self.signal_loaded("imt", a))

    def loaded(self, kind: str, answer: api.Answer) -> None:
        # 503: no gateway of that kind runs, which is "no modem" here
        value = answer.body if answer.ok and isinstance(answer.body, dict) else None
        setattr(self, kind, value)
        self.render()

    def signal_loaded(self, kind: str, answer: api.Answer) -> None:
        bars = answer.body.get("bars") if answer.ok and isinstance(answer.body, dict) else None
        setattr(self, f"{kind}_bars", int(bars or 0))
        self.render()

    def poll_signal(self) -> None:
        """A fresh reading of the 9603, then "Signal: N/5" (Android's Poll Signal)."""
        self.call("/api/iridium/signal?type=sbd", lambda a: self.app.toast(satellite_model.signal_toast(a.body) if a.ok else (a.error or "No modem")),
                  method="GET", timeout=self.SIGNAL_TIMEOUT)

    def poll_imt_signal(self) -> None:
        self.call("/api/iridium/signal?type=imt", lambda a: self.app.toast(satellite_model.signal_toast(a.body, "9704 ") if a.ok else (a.error or "No modem")),
                  method="GET", timeout=self.SIGNAL_TIMEOUT)

    def disconnect_imt(self) -> None:
        self.call("/api/interfaces/iridium_imt_0/unbind", lambda a: None if a.ok else self.app.toast(a.error or "The Bridge did not take it."))

    def unfold_imt(self) -> None:
        self.show_imt = True
        self.render()

    def update(self, s: api.State) -> None:
        self.render()

    def render(self) -> None:
        s = self.app.state
        # The poll's modem until the page's own read is in
        sbd = self.sbd if self.sbd is not None else (s.modem if (s.modem or {}).get("type") in (None, "", "sbd") else None)
        ble = s.ble or {}
        node = s.node_mode() == "bluetooth" and (bool(ble.get("satellite_pipe")) or (sbd or {}).get("port") == "ble")
        self.node_card.set_visible(node)
        self.usb_card.set_visible(not node)
        self.health_card.set_visible(node and self.has_stats)
        if node:
            words, connected = satellite_model.node_status(ble, sbd, self.sbd_bars or (s.signal or {}).get("bars", 0))
            self.node_status_text.set_text(words)
            paint(self.node_status_text, theme.GREEN if connected else theme.TEXT_MUTED)
            self.use_node.set_active(ble.get("satellite_enabled") is not False)
            clear(self.node_details)
            for label, value in satellite_model.usb_rows(sbd):
                self.node_details.append(fact_row(label, value))
            for w in (self.node_details, self.node_poll, self.node_mailbox):
                w.set_visible(connected)
            self.node_mailbox.set_connected(connected)
            self.node_note.set_visible(not connected and not ble.get("satellite_pipe"))
            clear(self.health_rows)
            if self.stats is None:
                self.health_rows.append(text(satellite_model.HEALTH_WAITING, "body-small", theme.TEXT_MUTED))
                self.health_warning.set_visible(False)
            else:
                for label, value in satellite_model.node_stats_rows(self.stats):
                    self.health_rows.append(fact_row(label, value))
                warning = satellite_model.node_stats_warning(self.stats)
                self.health_warning.set_text(warning or "")
                self.health_warning.set_visible(bool(warning))
        words, connected = satellite_model.usb_status(bool(s.bridge), sbd, self.sbd_bars or (s.signal or {}).get("bars", 0))
        self.status_text.set_text(words)
        paint(self.status_text, theme.GREEN if connected else theme.TEXT_MUTED)
        clear(self.details)
        for label, value in satellite_model.usb_rows(sbd):
            self.details.append(fact_row(label, value))
        self.details.set_visible(connected)
        self.poll.set_visible(connected)
        self.mailbox.set_visible(connected)
        self.mailbox.set_connected(connected)
        self.note.set_visible(not connected)
        used = satellite_model.imt_used(self.imt)
        self.imt_fold.set_visible(not used and not self.show_imt)
        self.imt_card.set_visible(used or self.show_imt)
        words, ready = satellite_model.imt_status(self.imt, self.imt_bars)
        self.imt_status_text.set_text(words)
        paint(self.imt_status_text, theme.GREEN if ready else theme.TEXT_MUTED)
        clear(self.imt_details)
        for label, value in satellite_model.imt_rows(self.imt):
            self.imt_details.append(fact_row(label, value))
        self.imt_details.set_visible(ready)
        self.imt_buttons.set_visible(ready)
        self.imt_note.set_visible(not ready and not satellite_model.imt_used(self.imt))


def status_row(label: str) -> tuple:
    """ConnectionStatusRow: the label in bodyMedium on the left, the status on the right (Green
    when connected, else TextMuted)."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
    name = text(label, "body-medium")
    name.set_hexpand(True)
    row.append(name)
    status = text("", "body-medium", theme.TEXT_MUTED, xalign=1.0, wrap=True)
    status.set_justify(Gtk.Justification.RIGHT)
    row.append(status)
    return row, status


def mesh_node_rows(box: Gtk.Box, nodes: list) -> None:
    """SettingsScreen.kt:420-448: "Mesh Nodes (N)" in bodySmall TextMuted, 4 dp more above it,
    then one row per node, the long name (or the id) at the left and the short name at the right
    in the mesh colour, both bodySmall, 6 dp inside a strip of the card's own colour (so only its
    inset shows); nothing while the node has sent no list."""
    if not nodes:
        return
    caption = text(f"Mesh Nodes ({len(nodes)})", "body-small", theme.TEXT_MUTED)
    caption.set_margin_top(theme.dp(4))
    box.append(caption)
    for n in nodes:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        for side in ("start", "end", "top", "bottom"):
            getattr(row, f"set_margin_{side}")(theme.dp(6))
        name = text((n.get("long_name") or "").strip() or n.get("user_id", ""), "body-small", ellipsize=True)
        name.set_hexpand(True)
        row.append(name)
        row.append(text((n.get("short_name") or "").strip(), "body-small", theme.MESH, xalign=1.0))
        box.append(row)


class SmsScreen(Page):
    """Setup > SMS, as the Android SMS section: the phone's SIM as a way out, and its state."""

    def __init__(self, app):
        super().__init__(app, "SMS")
        card = self.card("Text messages")
        # SettingsScreen.kt:1915-1942: ConnectionStatusRow "SMS", then the sentence; no rows of
        # modem facts. The value is Android's "Allowed" once the SIM can send, else why it cannot
        # (the Setup row's words: the modem and the SIM stand where Android asks a permission).
        row, self.status = status_row("SMS")
        card.append(row)
        card.append(text("MeshSat sends and receives texts through this phone's SIM when the network works. Your carrier's normal rates apply.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        # SettingsScreen.kt:1945-1981: the one number a text with no recipient goes to (the
        # Bridge's SMS gateway's default number, MESHSAT-1412).
        from .model import messaging  # noqa: PLC0415
        from .widgets import Field  # noqa: PLC0415

        self.words = messaging
        self.gateway = None
        fallback = self.card(messaging.NO_RECIPIENT_TITLE)
        self.number = Field(messaging.NUMBER_LABEL, purpose=Gtk.InputPurpose.PHONE)
        self.number.entry.add_css_class("text-14")  # textStyle = bodyMedium: Field(size=14), theme.py's .field-input.text-14
        fallback.append(self.number)
        save = body_text(filled_button("Save", self.save_number, expand=False))
        save.set_halign(Gtk.Align.START)
        fallback.append(save)
        fallback.append(text(messaging.NO_RECIPIENT_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        self.update(app.state)

    def on_show(self) -> None:
        self.fetch("/api/gateways/cellular", self.got_gateway)

    def got_gateway(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.gateway = answer.body
        elif answer.status == 404:
            self.gateway = {}  # no SMS gateway set up yet: a save sets one up, switched off
        else:
            return
        if not self.number.text:
            self.number.set_text(self.words.default_number(self.gateway.get("config") or {}))

    def save_number(self) -> None:
        if self.gateway is None:
            # Not read yet: a PUT without the gateway's own switch would switch it off.
            self.fetch("/api/gateways/cellular", lambda a: (self.got_gateway(a), self.gateway is not None and self.save_number()))
            return
        number = self.number.text.strip()
        if not self.words.number_ok(number):
            self.number.set_error(self.words.BAD_NUMBER)
            return
        self.number.set_error(None)

        def done(answer: api.Answer) -> None:
            if answer.ok:
                self.app.toast(self.words.SAVED)
                self.fetch("/api/gateways/cellular", self.got_gateway)
            else:
                self.app.toast(answer.error or "The Bridge did not take the number.")

        self.call("/api/gateways/cellular", done, body=self.words.cellular_body(self.gateway, number), method="PUT")

    def update(self, s: api.State) -> None:
        ready = s.sms_ready()
        self.status.set_text("Allowed" if ready else (s.sms_reason() or "Not allowed yet"))
        paint(self.status, theme.GREEN if ready else theme.TEXT_MUTED)


class AdvancedScreen(Page):
    """Setup > Advanced (SetupScreen.kt's AdvancedSection): every row a native page, opened by
    Android's route over this one."""

    ROWS = (
        ("outlined-alt-route", "Routing rules", "Which messages go where, automatically", "rules"),
        ("outlined-link", "Links", "Every way out, its state and its health", "interfaces"),
        ("outlined-outbox", "Message queue", "Everything waiting, sent or given up", "deliveries"),
        ("outlined-hub", "Mesh topology", "How the nodes you hear are linked", "topology"),
        ("outlined-history", "Audit log", "A signed record of what the gateway did", "audit"),
        ("outlined-key", "Certificates and keys", "The Hub certificate and imported keys", "credentials"),
        ("outlined-lock-open", "Encrypt or decrypt text", "By hand, with a conversation key", "decrypt"),
        # Android's row says "Link health, batch queue, crash reports, service": this edition's
        # page has the link health and the service (no batch queue, no local crash telemetry).
        ("outlined-monitor-heart", "Diagnostics", "Link health, service", "setup/diagnostics"),
        ("outlined-terminal", "Node log", "The node's live log, on demand", "nodelog"),
    )

    def __init__(self, app):
        # AdvancedScreen: the rows one under the other, with no padding and no spacing of the
        # page's own, and a divider under the last one.
        super().__init__(app, "Advanced", spacing=0, padded=False)
        for name, title_text, detail, route in self.ROWS:
            if route == "nodelog" and app.state.node_mode() == "bluetooth":
                detail = "The node's live log over Bluetooth, on demand"  # Android's words, where they hold
            row = NavRow(name, title_text, lambda t=title_text, r=route: self.open(t, r))
            row.set_detail(detail)
            self.column.append(row)
        self.column.append(divider())

    def open(self, title_text: str, route: str) -> None:
        # The native pages, pushed over this one as Android's navigation does.
        from .routes import screen_of  # noqa: PLC0415

        page = screen_of(route)(self.app)
        page.route = route
        self.app.push(page, title_text)


def utc_clock(stamp) -> str:
    """The Bridge's RFC 3339 times as the apps show them: HH:MM UTC."""
    if isinstance(stamp, str) and len(stamp) >= 16:
        return stamp[11:16] + " UTC"
    return when(stamp) if stamp else "now"


def read_provenance() -> dict:
    out = {}
    try:
        with open("/usr/share/doc/meshsat/PROVENANCE", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("meshsat ") and "built" in line:
                    out["build"] = line.split("built", 1)[1].strip()[:16]
                elif line.startswith("meshtasticd:"):
                    out["meshtasticd"] = line.split(":", 1)[1].strip().split(",")[0]
                elif line.startswith("bridge:"):
                    out["bridge"] = line.split(":", 1)[1].strip()
    except OSError:
        pass
    return out
