# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup and its pages, as ui/screens/SetupScreen.kt and SettingsScreen.kt: the flat list
in three groups, and one page of cards per row. This edition: the node is the LoRa back
cover driven by meshtasticd on this phone, the satellite modem is a RockBLOCK on USB-C, and
there is no SMS row (the phone's own modem is not the app's)."""
import threading

from gi.repository import Adw, GLib, Gtk

from . import __version__ as VERSION
from . import api, system, theme
from .model import hub as hub_model
from .model import satellite as satellite_model
from .pages.safety import SafetyScreen  # noqa: F401  (the Setup row and the route table use it)
from .passes import PassesScreen
from .screen import Screen, SubScreen
from .mailbox import MailboxButton
from .widgets import KeyValue, NavRow, clear, fact_row, filled_button, group_title, outlined_button, page, paint, scroller, text, text_button, when

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
        row.append(text_button("Connect", lambda: self.connect_node(dev)))
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
        passes = NavRow("outlined-schedule", "Satellite passes", lambda: app.push(PassesScreen(app)))
        passes.set_detail("When satellites are high overhead")
        self.column.append(passes)
        self.sbd, self.sbd_bars, self.imt, self.imt_bars = None, 0, None, 0
        self.show_imt = False

        card = self.card(satellite_model.USB_TITLE)
        self.status, self.status_text = status_row(satellite_model.STATUS)
        card.append(self.status)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        card.append(self.details)
        self.poll = filled_button(satellite_model.POLL_SIGNAL, self.poll_signal)
        self.poll.add_css_class("small-text")
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
        poll = filled_button(satellite_model.POLL_SIGNAL, self.poll_imt_signal)
        poll.add_css_class("small-text")
        self.imt_buttons.append(poll)
        off = filled_button(satellite_model.DISCONNECT, self.disconnect_imt)
        off.add_css_class("small-text")
        off.add_css_class("red-fill")
        self.imt_buttons.append(off)
        self.imt_card.append(self.imt_buttons)
        self.imt_note = text(satellite_model.IMT_PLUG, "body-small", theme.TEXT_MUTED, wrap=True)
        self.imt_card.append(self.imt_note)
        self.render()

    def on_show(self) -> None:
        self.every(5, self.load)
        self.mailbox.load()

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
        # SettingsScreen.kt:1945-1981: the one number a text with no recipient goes to (the
        # Bridge's SMS gateway's default number, MESHSAT-1412).
        from .model import messaging  # noqa: PLC0415
        from .widgets import Field  # noqa: PLC0415

        self.words = messaging
        self.gateway = None
        fallback = self.card(messaging.NO_RECIPIENT_TITLE)
        self.number = Field(messaging.NUMBER_LABEL, purpose=Gtk.InputPurpose.PHONE)
        fallback.append(self.number)
        save = filled_button("Save", self.save_number, expand=False)
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
        super().__init__(app, "Advanced")
        self.column.set_margin_start(theme.dp(0))
        self.column.set_margin_end(theme.dp(0))
        self.column.set_margin_top(theme.dp(0))
        for name, title_text, detail, route in self.ROWS:
            if route == "nodelog" and app.state.node_mode() == "bluetooth":
                detail = "The node's live log over Bluetooth, on demand"  # Android's words, where they hold
            row = NavRow(name, title_text, lambda t=title_text, r=route: self.open(t, r))
            row.set_detail(detail)
            self.column.append(row)

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
