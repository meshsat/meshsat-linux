# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup and its pages, as ui/screens/SetupScreen.kt and SettingsScreen.kt: the flat list
in three groups, and one page of cards per row. This edition: the node is the LoRa back
cover driven by meshtasticd on this phone, the satellite modem is a RockBLOCK on USB-C, and
there is no SMS row (the phone's own modem is not the app's)."""
import subprocess
import threading

from gi.repository import Adw, GLib, Gtk

from . import __version__ as VERSION
from . import api, theme
from . import sos as sos_words
from .passes import PassesScreen
from .widgets import Card, Chip, KeyValue, NavRow, SubHeader, clear, filled_button, group_title, hscroll, outlined_button, page, scroller, spacer, text, text_button, when

# Meshtastic's LoRa config, as the Bridge relays it: protobuf field numbers of Config.LoRaConfig.
REGIONS = {0: "Unset", 1: "US", 2: "EU_433", 3: "EU_868", 4: "CN", 5: "JP", 6: "ANZ", 7: "KR", 8: "TW", 9: "RU", 10: "IN", 11: "NZ_865", 12: "TH", 13: "LORA_24", 14: "UA_433", 15: "UA_868", 16: "MY_433", 17: "MY_919", 18: "SG_923"}
PRESETS = {0: "LongFast", 1: "LongSlow", 2: "VeryLongSlow", 3: "MediumSlow", 4: "MediumFast", 5: "ShortSlow", 6: "ShortFast", 7: "LongModerate", 8: "ShortTurbo"}


class SetupScreen(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        column = page(spacing=0, padded=False)
        title = text("Setup", "headline-medium")
        title.set_margin_start(theme.dp(16))
        title.set_margin_top(theme.dp(16))
        column.append(title)
        column.append(group_title("Get connected"))
        self.node = NavRow("outlined-bluetooth", "Your MeshSat node", lambda: app.push(NodeScreen(app)), theme.MESH)
        self.satellite = NavRow("transport-satellite", "Satellite", lambda: app.push(SatelliteScreen(app)), theme.IRIDIUM)
        self.hub = NavRow("outlined-cloud", "Hub", lambda: app.push(HubScreen(app)), theme.HUB)
        self.sms = NavRow("outlined-sms", "SMS", lambda: app.push(SmsScreen(app)), theme.SMS)
        for row in (self.node, self.satellite, self.hub, self.sms):
            column.append(row)
        column.append(group_title("Using MeshSat"))
        rows = (
            ("outlined-health-and-safety", "Safety", "SOS, check-in timer, zones", lambda: app.push(SafetyScreen(app))),
            ("outlined-lock", "Messaging", "Encryption, compression, quick messages", lambda: app.push(MessagingScreen(app))),
            ("outlined-map", "Maps", "Offline maps for when there is no internet", lambda: app.push(MapsScreen(app))),
            ("outlined-radio", "Ham radio, TAK and Reticulum", "Other networks MeshSat can bridge", lambda: app.push(IntegrationsScreen(app))),
            ("outlined-tune", "Mesh radio settings", "Region, channels, transmit power", lambda: app.push(RadioScreen(app))),
        )
        for name, title_text, detail, action in rows:
            row = NavRow(name, title_text, action)
            row.set_detail(detail)
            column.append(row)
        column.append(group_title("For experts"))
        advanced = NavRow("outlined-build", "Advanced", lambda: app.push(AdvancedScreen(app)))
        advanced.set_detail("Routing, links, queue, logs, diagnostics")
        column.append(advanced)
        about = NavRow("outlined-info", "About", lambda: app.push(AboutScreen(app)))
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
        if s.hub_configured():
            self.hub.set_detail("Connected" if (s.hub or {}).get("bridge_id") else "Connecting", "green" if (s.hub or {}).get("bridge_id") else "amber")
        else:
            self.hub.set_detail("Not set up. Paste the Hub's QR code.", "muted")
        if s.sms_ready():
            self.sms.set_detail("Allowed", "green")
        else:
            self.sms.set_detail(s.sms_reason() or "Not allowed yet", "muted")


class Page(Gtk.Box):
    """A sub-screen: the '<- Title' row and a column of cards 16 px apart."""

    def __init__(self, app, title: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.append(SubHeader(title, app.pop))
        self.column = page(spacing=16)
        self.append(scroller(self.column))

    def card(self, title: str | None = None) -> Card:
        card = Card(spacing=8)
        if title:
            card.append(text(title, "title-medium"))
        self.column.append(card)
        return card

    def update(self, s: api.State) -> None:
        pass


class NodeScreen(Page):
    """Your MeshSat node: the LoRa back cover this phone carries, or a node over Bluetooth
    (the "Bluetooth connection" card of SettingsScreen.kt, word for word). Which of the two,
    the package's meshsat-hardware decided when the phone booted; the last card asks it again."""

    def __init__(self, app):
        super().__init__(app, "Your MeshSat node")
        self.devices = None
        self.scanning = False
        self.pin_asked_for = None
        # The LoRa back cover, when this phone has one.
        self.cover = self.card("The LoRa back cover")
        self.status = KeyValue("Status", "Disconnected")
        self.cover.append(self.status)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        self.cover.append(self.details)
        self.action = filled_button("Start the node", self.start)
        self.cover.append(self.action)
        self.note = text("The node is meshtasticd on this phone, driving the Pine64 LoRa back cover through its pogo pins. It starts with the phone.", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.cover.append(self.note)
        # A node over Bluetooth, as on the other apps.
        self.bt = self.card("Bluetooth connection")
        self.bt_status = KeyValue("Status", "Disconnected")
        self.bt.append(self.bt_status)
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
        subprocess.Popen(["pkexec", "systemctl", "restart", "meshtasticd.service", "meshsat-bridge.service"])
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

    def update_cover(self, s: api.State) -> None:
        clear(self.details)
        if s.mesh_connected():
            self.status.value.set_text("Connected")
            b = s.bridge or {}
            own = s.own_node() or {}
            for k, v in (("Firmware", b.get("firmware_version", "")), ("Node ID", b.get("node_id", "")), ("Name", b.get("node_name") or own.get("long_name", "")),
                         ("Hardware", b.get("hw_model_name", "")), ("Reboots", str(b.get("reboot_count", 0))), (f"Mesh Nodes ({len(s.others())})", ", ".join((n.get("short_name") or n.get("user_id", "")) for n in s.others()[:6]) or "none yet")):
                self.details.append(KeyValue(k, v, mono=k in ("Node ID", "Firmware")))
            self.action.set_label("Restart the node")
        elif s.node_service:
            self.status.value.set_text("Connecting...")
            self.action.set_label("Restart the node")
        else:
            self.status.value.set_text("Disconnected")
            self.action.set_label("Start the node")
        radio = s.watchdog.get("radio")
        if radio in ("radio-not-answering", "cover-unreachable"):
            self.details.append(text(s.watchdog.get("message", ""), "body-medium", theme.AMBER, wrap=True))

    # SettingsScreen.kt:384-525: Status; "Scan for Meshtastic devices"; "Found devices:" with
    # name, address and Connect; when connected Firmware, Node ID, Battery, Reboots, Mesh Nodes
    # and Disconnect. The PIN dialog is this app's: Android's system shows it there.
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
        self.bt_status.value.set_text(status)
        if ble.get("pairing_pending") and self.pin_asked_for != ble.get("pairing_since"):
            self.pin_asked_for = ble.get("pairing_since")
            self.ask_pin(ble)
        clear(self.bt_body)
        if s.mesh_connected():
            own = s.own_node() or {}
            battery = own.get("battery_level") or 0
            rows = [("Firmware", b.get("firmware_version", "")), ("Node ID", b.get("node_id", ""))]
            if battery:
                rows.append(("Battery", "On USB power" if battery > 100 else f"{battery}%"))
            if b.get("reboot_count"):
                rows.append(("Reboots", str(b["reboot_count"])))
            names = [(n.get("long_name") or n.get("user_id", "")) + (f" ({n['short_name']})" if n.get("short_name") else "") for n in s.nodes[:8]]
            rows.append((f"Mesh Nodes ({len(s.nodes)})", ", ".join(names) or "none yet"))
            for k, v in rows:
                if v:
                    self.bt_body.append(KeyValue(k, v, mono=k in ("Node ID", "Firmware")))
            disconnect = outlined_button("Disconnect", self.disconnect)
            disconnect.add_css_class("danger")
            self.bt_body.append(disconnect)
            return
        if state == "pairing" or ble.get("pairing_pending"):
            self.bt_body.append(text(f"Pairing with {ble.get('name') or ble.get('address') or 'the node'}: enter the PIN shown on its screen.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
            self.bt_body.append(outlined_button("Enter the PIN", lambda: self.ask_pin(ble)))
        elif ble.get("address"):
            who = ble.get("name") or ble["address"]
            if state in ("scanning", "connecting"):
                self.bt_body.append(text(f"Connecting to {who}.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
            else:
                self.bt_body.append(text(f"{who} cannot be reached." + (f" {ble['error'].capitalize()}." if ble.get("error") else ""), "body-medium", theme.AMBER, wrap=True))
        if not self.scanning:
            self.bt_body.append(filled_button("Scan for Meshtastic devices", self.scan))
        if self.devices is not None and not self.scanning:
            if self.devices:
                self.bt_body.append(text("Found devices:", "title-medium"))
                for dev in self.devices:
                    self.bt_body.append(self.device_row(dev))
            else:
                self.bt_body.append(text("No Meshtastic devices found. Is the node on, with Bluetooth enabled?", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        if ble.get("address"):
            forget = text_button("Forget this node", self.forget)
            self.bt_body.append(forget)

    def device_row(self, dev: dict) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        names.set_hexpand(True)
        names.append(text(dev.get("name") or "Unknown", "title-medium", ellipsize=True))
        detail = dev.get("address", "")
        if dev.get("rssi"):
            detail += f"  {dev['rssi']} dBm"
        if dev.get("chosen"):
            detail += "  (your node)"
        names.append(text(detail, "body-medium", theme.TEXT_SECONDARY, mono=True))
        row.append(names)
        row.append(text_button("Connect", lambda: self.connect(dev)))
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

    def connect(self, dev: dict) -> None:
        result = api.ble_connect(dev.get("address", ""))
        if result and result.get("error"):
            self.app.toast(result["error"])
            return
        self.devices = None
        self.app.toast(f"Connecting to {dev.get('name') or dev.get('address')}")
        self.app.poller.poll_now()

    def disconnect(self) -> None:
        result = api.ble_forget(bond=False)
        self.app.toast(result.get("error") if result and result.get("error") else "Disconnected")
        self.app.poller.poll_now()

    def forget(self) -> None:
        result = api.ble_forget(bond=True)
        self.app.toast(result.get("error") if result and result.get("error") else "The node is forgotten")
        self.devices = None
        self.app.poller.poll_now()

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
            result = api.ble_pair(pin)
            if result and result.get("error"):
                self.app.toast(result["error"])
                return
            dialog.close()
            self.app.toast("Pairing")
            self.app.poller.poll_now()

        buttons.append(text_button("Pair", pair))
        entry.connect("activate", lambda *_: pair())
        box.append(buttons)
        dialog.set_child(box)
        dialog.present(self.app.window)


class SatelliteScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Satellite")
        passes = NavRow("outlined-schedule", "Satellite passes", lambda: app.push(PassesScreen(app)))
        passes.set_detail("When satellites are high overhead")
        self.column.append(passes)
        card = self.card("Satellite modem on USB-C")
        self.status = text("Checking the modem.", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        card.append(self.status)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        card.append(self.details)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        self.poll = outlined_button("Poll Signal", self.poll_signal)
        self.check = filled_button("Check Mailbox", self.check_mailbox, expand=False)
        buttons.append(self.poll)
        buttons.append(self.check)
        card.append(buttons)
        card.append(text("A RockBLOCK 9603 on the phone's USB-C port, through a USB adapter. The Bridge finds it by itself.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        health = self.card("Node health")
        self.health = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        health.append(self.health)
        self.update(app.state)

    def poll_signal(self) -> None:
        result = api.get("/api/iridium/signal/fast") or {}
        self.app.toast(f"Signal {result.get('bars', 0)} of 5" if "bars" in result else "No modem")

    def check_mailbox(self) -> None:
        result = api.post("/api/iridium/mailbox/check")
        self.app.toast(result.get("error") or "Checking the satellite mailbox")

    def update(self, s: api.State) -> None:
        clear(self.details)
        clear(self.health)
        modem = s.modem or {}
        if modem.get("connected"):
            self.status.set_text(f"Modem ready, signal {(s.signal or {}).get('bars', 0)} of 5.")
            for k, v in (("Model", modem.get("model", "")), ("IMEI", modem.get("imei", "") or "-"), ("Port", modem.get("port", ""))):
                self.details.append(KeyValue(k, v, mono=k != "Model"))
        elif not s.bridge:
            self.status.set_text("Connect your node first.")
        elif modem.get("port") in ("", "supervisor", None):
            self.status.set_text("No modem on this radio. Plug a RockBLOCK into USB-C.")
        else:
            self.status.set_text("Checking the modem.")
        for w in (self.poll, self.check):
            w.set_sensitive(bool(modem.get("connected")))
        b = s.bridge or {}
        for k, v in (("Node", "Connected" if s.mesh_connected() else "Not connected"), ("Modem", "Ready" if modem.get("connected") else "None"),
                     ("Radio", s.watchdog.get("message", "no word yet")), ("Last reset", b.get("radio_last_reset_reason") or "-")):
            self.health.append(KeyValue(k, v))


class HubScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Hub")
        card = self.card("Hub connection")
        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.dot = Gtk.Box()
        self.dot.add_css_class("dot")
        self.dot.add_css_class("dot-muted")
        self.dot.set_valign(Gtk.Align.CENTER)
        status.append(self.dot)
        self.status = text("Not set up", "body-large")
        status.append(self.status)
        status.append(spacer())
        self.switch = Gtk.Switch()
        self.switch.set_valign(Gtk.Align.CENTER)
        status.append(self.switch)
        card.append(status)
        card.append(text("Paste the Hub's QR code", "body-medium", theme.TEXT_SECONDARY))
        self.paste = Gtk.Entry(placeholder_text="The text behind the Hub's QR code, from the Fleet page")
        self.paste.add_css_class("field")
        card.append(self.paste)
        card.append(filled_button("Use these Hub settings", self.apply))
        card.append(outlined_button("Test the connection", self.test))
        self.details_button = text_button("Connection details", self.toggle_details)
        card.append(self.details_button)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        self.details.set_visible(False)
        card.append(self.details)
        self.update(app.state)

    def toggle_details(self) -> None:
        self.details.set_visible(not self.details.get_visible())

    def apply(self) -> None:
        raw = self.paste.get_text().strip()
        if not raw:
            self.app.toast("Paste the Hub's QR code first")
            return
        import json
        body = None
        try:
            data = json.loads(raw)
            body = {"url": data.get("url") or data.get("mqtt_url") or data.get("hub_url", ""), "username": data.get("username") or data.get("bridge_id", ""),
                    "password": data.get("password", ""), "bridge_id": data.get("bridge_id", "")}
        except ValueError:
            if raw.startswith("http") or raw.startswith("mqtt"):
                body = {"url": raw}
        if not body or not body.get("url"):
            self.app.toast("That is not a Hub QR code")
            return
        result = api.put("/api/routing/hub", body)
        self.app.toast(result.get("error") or "Hub settings saved. Restarting the Bridge.")
        subprocess.Popen(["pkexec", "systemctl", "restart", "meshsat-bridge.service"])

    def test(self) -> None:
        hub = api.get("/api/routing/hub") or {}
        self.app.toast(f"Connected as {hub['bridge_id']}" if hub.get("bridge_id") else "Not connected")

    def update(self, s: api.State) -> None:
        hub = s.hub or {}
        for c in ("dot-green", "dot-amber", "dot-muted"):
            self.dot.remove_css_class(c)
        if hub.get("url"):
            ok = bool(hub.get("bridge_id"))
            self.dot.add_css_class("dot-green" if ok else "dot-amber")
            self.status.set_text("Connected" if ok else "Connecting")
            self.switch.set_active(True)
        else:
            self.dot.add_css_class("dot-muted")
            self.status.set_text("Not set up")
            self.switch.set_active(False)
        clear(self.details)
        for k, v in (("Hub MQTT URL", hub.get("url") or "-"), ("Bridge ID", hub.get("bridge_id") or "-"), ("Username", hub.get("username") or "-"),
                     ("Password", "set" if hub.get("has_password") else "-"), ("Certificate", "set" if hub.get("has_cert") else "-")):
            self.details.append(KeyValue(k, v, mono=k in ("Bridge ID",)))


class SmsScreen(Page):
    """Setup > SMS, as the Android SMS section: the phone's SIM as a way out, and its state."""

    def __init__(self, app):
        super().__init__(app, "SMS")
        card = self.card("Text messages")
        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.dot = Gtk.Box()
        self.dot.add_css_class("dot")
        self.dot.set_valign(Gtk.Align.CENTER)
        status.append(self.dot)
        self.status = text("Not allowed yet", "body-large")
        status.append(self.status)
        card.append(status)
        card.append(text("MeshSat sends and receives texts through this phone's SIM when the network works. Your carrier's normal rates apply.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.append(self.details)
        card.append(text("SOS texts go to your emergency contacts under Safety. A text you write carries its own number.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.update(app.state)

    def update(self, s: api.State) -> None:
        for c in ("dot-green", "dot-amber", "dot-muted"):
            self.dot.remove_css_class(c)
        c = s.cellular or {}
        if s.sms_ready():
            self.dot.add_css_class("dot-green")
            self.status.set_text("Allowed")
        else:
            self.dot.add_css_class("dot-amber" if c.get("connected") else "dot-muted")
            self.status.set_text(s.sms_reason() or "Not allowed yet")
        clear(self.details)
        for k, v in (("Modem", c.get("model") or "-"), ("SIM", {"READY": "Ready", "NOT_INSERTED": "None", "PIN_REQUIRED": "Locked", "SIM_ERROR": "Faulty"}.get(c.get("sim_state", ""), c.get("sim_state") or "-")),
                     ("Network", (c.get("operator") or "-") + (f", {c['network_type']}" if c.get("network_type") else "")), ("Number", c.get("phone_number") or "-"),
                     ("Sent, received", f"{c.get('sms_sent', 0)}, {c.get('sms_received', 0)}")):
            self.details.append(KeyValue(k, v, mono=k == "Number"))


class SafetyScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Safety")
        zones = NavRow("outlined-fence", "Zones", lambda: app.toast("Zones are not on this device yet."))
        zones.set_detail("Not on this device yet")
        self.column.append(zones)
        sos = self.card("SOS")
        self.sos_status = text("No SOS has been sent from this phone.", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        sos.append(self.sos_status)
        self.sos_reach = text("An SOS goes out by satellite, the mesh and the Hub, with your position, and keeps trying until you cancel.", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        sos.append(self.sos_reach)
        sos.append(text("Your name in an SOS", "label-medium", theme.TEXT_SECONDARY))
        self.name = Gtk.Entry(placeholder_text="A MeshSat user")
        self.name.add_css_class("field")
        self.name.set_text(app.state.sos_name)
        self.name.connect("changed", lambda e: app.set_sos_name(e.get_text()))
        sos.append(self.name)
        self.cancel = outlined_button("Cancel SOS: I am safe", self.cancel_sos)
        sos.append(self.cancel)

        contacts = self.card("Emergency contacts")
        contacts.append(text("Who an SOS goes to by SMS, from this phone's own SIM, with your position and a map link.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.sms_note = text("", "body-small", theme.AMBER, wrap=True)
        contacts.append(self.sms_note)
        self.contact_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        contacts.append(self.contact_rows)
        self.contact_name = Gtk.Entry(placeholder_text="Name")
        self.contact_name.add_css_class("field")
        contacts.append(self.contact_name)
        self.contact_phone = Gtk.Entry(placeholder_text="Phone number, with country code: +31 6 1234 5678", input_purpose=Gtk.InputPurpose.PHONE)
        self.contact_phone.add_css_class("field")
        contacts.append(self.contact_phone)
        self.add_contact = filled_button("Add this contact", self.add_a_contact)
        contacts.append(self.add_contact)
        timer = self.card("Check-in timer (dead man's switch)")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        row.append(text("Enabled", "body-large"))
        row.append(spacer())
        self.enabled = Gtk.Switch()
        self.enabled.set_valign(Gtk.Align.CENTER)
        self.enabled.connect("state-set", self.set_enabled)
        row.append(self.enabled)
        timer.append(row)
        choices = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.timeouts = {}
        for minutes, label_text in ((30, "30 min"), (60, "1 hour"), (120, "2 hours"), (240, "4 hours"), (480, "8 hours")):
            chip = Chip(label_text, lambda c, m=minutes: self.set_timeout(m))
            self.timeouts[minutes] = chip
            choices.append(chip)
        timer.append(hscroll(choices))
        timer.append(text("If you do not touch the phone within the time, an SOS goes out by itself.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.update(app.state)

    def cancel_sos(self) -> None:
        api.post("/api/sos/cancel")
        self.app.poller.poll_now()

    MAX_CONTACTS = 10  # as Android's EmergencyContact.MAX

    def add_a_contact(self) -> None:
        name = self.contact_name.get_text().strip()
        phone = "".join(ch for ch in self.contact_phone.get_text() if ch.isdigit() or ch == "+")
        if not phone.startswith("+") or len(phone) < 8:
            self.app.toast("A phone number with its country code, like +31612345678.")
            return
        contacts = [c for c in self.app.state.contacts if c.get("phone") != phone]
        if len(contacts) >= self.MAX_CONTACTS:
            self.app.toast(f"Up to {self.MAX_CONTACTS} contacts.")
            return
        contacts.append({"name": name, "phone": phone})
        self.app.set_contacts(contacts)
        self.contact_name.set_text("")
        self.contact_phone.set_text("")
        self.update(self.app.state)

    def remove_contact(self, phone: str) -> None:
        self.app.set_contacts([c for c in self.app.state.contacts if c.get("phone") != phone])
        self.update(self.app.state)

    def set_enabled(self, switch, state) -> bool:
        current = self.app.state.deadman or {}
        api.post("/api/deadman", {"enabled": bool(state), "timeout_min": current.get("timeout_min", 240)})
        self.app.poller.poll_now()
        return False

    def set_timeout(self, minutes: int) -> None:
        current = self.app.state.deadman or {}
        api.post("/api/deadman", {"enabled": current.get("enabled", False), "timeout_min": minutes})
        self.app.poller.poll_now()

    def update(self, s: api.State) -> None:
        sos = s.sos or {}
        if sos.get("active"):
            self.sos_status.set_text(f"SOS is on since {utc_clock(sos.get('started_at'))}, sent {sos.get('sends', 0)} times. Tap Cancel when you are safe.")
            self.cancel.set_visible(True)
        else:
            self.sos_status.set_text("No SOS has been sent from this phone.")
            self.cancel.set_visible(False)
        d = s.deadman or {}
        self.enabled.set_active(bool(d.get("enabled")))
        for minutes, chip in self.timeouts.items():
            chip.set_selected(d.get("timeout_min") == minutes)
        names = [c.get("name") or c["phone"] for c in s.contacts]
        ways = "satellite, the mesh" + (f", SMS to {sos_words.join_and(names)}" if names else "") + " and the Hub"
        self.sos_reach.set_text(f"An SOS goes out by {ways}, with your position, and keeps trying until you cancel.")
        reason = s.sms_reason()
        self.sms_note.set_text(f"SMS is not available: {reason[0].lower() + reason[1:]}" if reason and names else "")
        self.sms_note.set_visible(bool(reason and names))
        clear(self.contact_rows)
        if not s.contacts:
            self.contact_rows.append(text("No contacts yet.", "body-medium", theme.TEXT_MUTED))
        for c in s.contacts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            texts.set_hexpand(True)
            texts.append(text(c.get("name") or c["phone"], "body-medium"))
            if c.get("name"):
                texts.append(text(c["phone"], "body-small", theme.TEXT_SECONDARY, mono=True))
            row.append(texts)
            from .widgets import icon_button
            row.append(icon_button("outlined-delete", lambda phone=c["phone"]: self.remove_contact(phone), 20, theme.TEXT_SECONDARY, "Remove"))
            self.contact_rows.append(row)
        self.add_contact.set_sensitive(len(s.contacts) < self.MAX_CONTACTS)


class MessagingScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Messaging")
        enc = self.card("Encryption")
        self.keys = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        enc.append(self.keys)
        enc.append(text("Keys are kept by the Bridge and used on every way out. Manage them under Advanced > Certificates and keys.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        comp = self.card("Message compression")
        comp.append(text("The Bridge compresses satellite messages with MSVQ-SC when a sidecar is configured, and sends them plain otherwise.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        quick = self.card("Quick messages")
        quick.append(text("The node's canned messages, as on every MeshSat node. Sent from a chat as any other message.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.update(app.state)

    def update(self, s: api.State) -> None:
        k = s.keys or {}
        self.keys.set_text(f"{k.get('active', 0)} active keys, {k.get('retired', 0)} retired, {k.get('revoked', 0)} revoked. Encryption {'on' if k.get('enabled') else 'off'}.")


class MapsScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Maps")
        card = self.card("Offline maps")
        card.append(text("World overview", "body-large"))
        card.append(text("Built in, always installed. The map uses OpenStreetMap when there is internet.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        card.append(outlined_button("Add a detailed map", lambda: app.toast("Detailed offline maps are not on this device yet.")))


class IntegrationsScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Ham radio, TAK and Reticulum")
        self.aprs = self.card("Ham radio (APRS)")
        self.aprs_text = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.aprs.append(self.aprs_text)
        self.tak = self.card("TAK")
        self.tak_text = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.tak.append(self.tak_text)
        self.rns = self.card("Reticulum")
        self.rns_text = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.rns.append(self.rns_text)
        self.column.append(text("The Bridge on this phone carries these links; their settings live in its interface under Advanced.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.update(app.state)

    def update(self, s: api.State) -> None:
        aprs = api.get("/api/aprs/status") or {}
        self.aprs_text.set_text("Working" if aprs.get("connected") else "Off: no radio or TNC on this phone")
        tak = api.get("/api/tak/enroll/status") or {}
        self.tak_text.set_text("Enrolled" if tak.get("success") or tak.get("enrolled") else "Not set up")
        rns = api.get("/api/rns/status") or {}
        self.rns_text.set_text(f"Working, {rns.get('links', 0)} links" if rns.get("enabled") else "Off")


class RadioScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Mesh radio settings")
        self.card_box = self.card("Radio")
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        self.card_box.append(self.rows)
        self.card_box.append(text("Transmit power is capped at 0 dBm on this radio: the back cover's crystal drifts above that and long frames are lost. Change region and channels with meshsat-node-channels.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.update(app.state)

    def update(self, s: api.State) -> None:
        clear(self.rows)
        if not s.mesh_connected():
            self.rows.append(text("Your phone is not connected to your node, so its settings cannot be read or changed.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
            return
        lora = (api.get("/api/config") or {}).get("config_6") or {}
        if not isinstance(lora, dict):
            lora = {}
        b = s.bridge or {}
        channel = ((api.get("/api/config") or {}).get("channel_0") or {}).get("2", {})
        name = channel.get("3", "") if isinstance(channel, dict) else ""
        for k, v in (("Node", b.get("node_name") or "-"), ("Region", REGIONS.get(lora.get("7", 0), str(lora.get("7", "-")))), ("Preset", PRESETS.get(lora.get("2", 0), str(lora.get("2", "-")))),
                     ("Primary channel", name or "default"), ("Transmit power", f"0 dBm (capped; the node asks for {lora.get('10', '-')})"), ("Hops", str(lora.get("8", 3))), ("Firmware", b.get("firmware_version", ""))):
            self.rows.append(KeyValue(k, v))


class AdvancedScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Advanced")
        rows = (
            ("outlined-alt-route", "Routing rules", "Which messages go where, automatically", "/rules"),
            ("outlined-link", "Links", "Every way out, its state and its health", "/interfaces"),
            ("outlined-outbox", "Message queue", "Everything waiting, sent or given up", "/deliveries"),
            ("outlined-hub", "Mesh topology", "How the nodes you hear are linked", "/topology"),
            ("outlined-history", "Audit log", "A signed record of what the gateway did", "/audit"),
            ("outlined-key", "Certificates and keys", "The Hub certificate and imported keys", "/credentials"),
            ("outlined-lock-open", "Encrypt or decrypt text", "By hand, with a conversation key", "/decrypt"),
            ("outlined-monitor-heart", "Diagnostics", "Link health, crash reports, service", "/diagnostics"),
            ("outlined-terminal", "Node log", "The node's live log, on demand", "/nodelog"),
        )
        self.column.set_margin_start(theme.dp(0))
        self.column.set_margin_end(theme.dp(0))
        self.column.set_margin_top(theme.dp(0))
        for name, title_text, detail, route in rows:
            row = NavRow(name, title_text, lambda t=title_text, r=route: self.open(t, r))
            row.set_detail(detail)
            self.column.append(row)

    def open(self, title_text: str, route: str) -> None:
        if route == "/nodelog":
            self.app.push(NodeLogScreen(self.app))
        else:
            self.app.push(BridgePage(self.app, title_text, route))


class BridgePage(Gtk.Box):
    """An expert page of the Bridge's own interface, inside the app. The Bridge's dashboard is
    the operator console of a MeshSat kit; here it serves the expert screens only."""

    def __init__(self, app, title: str, route: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.append(SubHeader(title, app.pop))
        try:
            import gi
            gi.require_version("WebKit", "6.0")
            from gi.repository import WebKit
            web = WebKit.WebView()
            web.set_vexpand(True)
            web.load_uri(api.BRIDGE + "/" + ("#" + route if route else ""))
            self.append(web)
        except (ValueError, ImportError):
            self.append(text("The Bridge's interface needs WebKitGTK.", "body-medium", theme.TEXT_SECONDARY))

    def update(self, s: api.State) -> None:
        pass


class NodeLogScreen(Page):
    def __init__(self, app):
        super().__init__(app, "Node log")
        self.column.set_margin_start(theme.dp(8))
        self.column.set_margin_end(theme.dp(8))
        self.log = text("", "body-small", mono=True, wrap=True)
        self.log.set_selectable(True)
        self.column.append(self.log)
        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)

    def refresh(self) -> bool:
        try:
            out = subprocess.run(["journalctl", "-u", "meshtasticd", "-n", "80", "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            out = "Cannot read the node's log."
        # The app's own asks for the name of a node the phone has no NodeInfo from.
        asks = self.app.state.name_requests
        if asks:
            lines = [f"{when(a['time'])} asked {a['node']} for its name: {a['outcome']}" for a in asks[-20:]]
            out = (out or "").rstrip() + "\n\n" + "\n".join(lines)
        self.log.set_text(out or "No lines yet.")
        return self.get_root() is not None


class AboutScreen(Page):
    def __init__(self, app):
        super().__init__(app, "About")
        title = text("MeshSat Linux", "headline-large", xalign=0.5)
        self.column.append(title)
        provenance = read_provenance()
        version = text(f"v{VERSION} ({provenance.get('build', 'source')})", "title-large", theme.SIGNAL_ORANGE, xalign=0.5)
        self.column.append(version)
        self.column.append(text("Pocket gateway for the LoRa back cover mesh + Iridium satellite", "body-large", theme.TEXT_SECONDARY, wrap=True))
        transports = self.card("Transports")
        for k, v in (("Meshtastic", "The LoRa back cover over I2C"), ("Iridium 9603N", "RockBLOCK on USB-C"), ("RockBLOCK 9704", "USB serial (JSPR)"), ("Hub", "Wi-Fi or the phone's data")):
            transports.append(KeyValue(k, v))
        enc = self.card("Encryption")
        for k, v in (("Algorithm", "AES-256-GCM"), ("Wire format", "[12B nonce][ciphertext+tag]"), ("Compatible with", "MeshSat Pi transform pipeline")):
            enc.append(KeyValue(k, v))
        build = self.card("Build")
        for k, v in (("Package", "meshsat (net.meshsat.Bridge)"), ("Edition", "Debian package, Mobian"), ("Bridge", provenance.get("bridge", "-")), ("Node firmware", provenance.get("meshtasticd", "-")), ("Toolkit", "GTK 4, libadwaita")):
            build.append(KeyValue(k, v))
        lic = self.card("License")
        lic.append(text("GPL-3.0-or-later. MeshSat is free software. Meshtastic is a registered trademark of Meshtastic LLC; this app is not affiliated with it.", "body-medium", theme.TEXT_SECONDARY, wrap=True))


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
