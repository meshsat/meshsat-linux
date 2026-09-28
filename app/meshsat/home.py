# SPDX-License-Identifier: GPL-3.0-or-later
"""Home, as ui/screens/HomeScreen.kt and HomeLanes.kt: the wordmark with the night-mode and
refresh buttons, one sentence about what can go out and a second line, the lane card, then
the cards: Getting started (until it is done), SOS, Signal history, Recent messages. This
edition has no SMS lane: the phone's own modem is not the app's."""
import os

from gi.repository import Gdk, GLib, Gtk

from . import api, sos, theme
from .widgets import Card, LaneRow, Wordmark, clear, icon_button, page, scroller, spacer, text, when

BRAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brand", "app-icon-1024.png")


class HomeScreen(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        column = page(spacing=12)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        head.append(Wordmark(BRAND))
        head.append(spacer())
        head.append(icon_button("outlined-nights-stay", app.toggle_night, 24, tooltip="Night mode"))
        head.append(icon_button("outlined-swap-vert", app.poller.poll_now, 24, tooltip="Refresh"))
        column.append(head)

        self.sentence = text("Nothing can send yet.", "headline-small", wrap=True)
        column.append(self.sentence)
        self.second = text("Start with your MeshSat node, below.", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        column.append(self.second)

        lanes = Card(padded=False, spacing=0)
        self.satellite = LaneRow("satellite", "Satellite", lambda: app.open_lane("satellite"))
        self.mesh = LaneRow("mesh", "Mesh", lambda: app.open_lane("mesh"))
        self.sms = LaneRow("sms", "SMS", lambda: app.open_lane("sms"))
        self.hub = LaneRow("hub", "Hub", lambda: app.open_lane("hub"))
        for i, row in enumerate((self.satellite, self.mesh, self.sms, self.hub)):
            if i:
                sep = Gtk.Box()
                sep.add_css_class("lane-sep")
                lanes.append(sep)
            lanes.append(row)
        column.append(lanes)

        self.started = Card()
        started_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        started_top.append(text("Getting started", "title-medium"))
        started_top.append(spacer())
        self.started_count = text("0 of 3 done", "body-medium", theme.TEXT_SECONDARY, mono=True)
        started_top.append(self.started_count)
        self.started.append(started_top)
        self.steps = []
        for title, detail in (("Start your MeshSat node", "The radio: the LoRa back cover"),
                              ("Paste the Hub's key", "Optional: the control room"),
                              ("Plug the satellite modem", "A RockBLOCK on USB-C")):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
            dot = Gtk.Box()
            dot.add_css_class("dot")
            dot.add_css_class("dot-muted")
            dot.set_valign(Gtk.Align.CENTER)
            row.append(dot)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
            texts.append(text(title, "body-large"))
            texts.append(text(detail, "body-medium", theme.TEXT_SECONDARY))
            row.append(texts)
            self.started.append(row)
            self.steps.append(dot)
        column.append(self.started)

        sos = Card()
        sos.append(text("SOS", "title-medium"))
        self.sos_text = text("Sends your position by satellite, the mesh and the Hub, and keeps trying until you cancel.", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        sos.append(self.sos_text)
        self.sos_button = Gtk.Button(label="Hold 3 seconds for SOS")
        self.sos_button.add_css_class("outlined")
        self.sos_button.add_css_class("danger")
        self.sos_button.set_margin_top(theme.dp(4))
        self._hold = None
        press = Gtk.GestureClick()
        press.connect("pressed", self._sos_pressed)
        press.connect("released", self._sos_released)
        press.connect("cancel", lambda *_: self._sos_released(None, 0, 0, 0))
        self.sos_button.add_controller(press)
        sos.append(self.sos_button)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        see = Gtk.Button(label="See where it went")
        see.add_css_class("textbutton")
        see.connect("clicked", lambda *_: app.select_tab("messages"))
        actions.append(see)
        sos.append(actions)
        column.append(sos)

        signal = Card()
        signal.append(text("Signal history", "title-medium"))
        self.chart = Gtk.DrawingArea()
        self.chart.set_content_height(theme.dp(72))
        self.chart.set_draw_func(self.draw_chart)
        signal.append(self.chart)
        legend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        self.chart_min = text("min: –", "body-medium", theme.TEXT_SECONDARY)
        self.chart_avg = text("avg: –", "body-medium", theme.TEXT_SECONDARY, xalign=0.5)
        self.chart_max = text("max: –", "body-medium", theme.TEXT_SECONDARY, xalign=1.0)
        for w in (self.chart_min, self.chart_avg, self.chart_max):
            legend.append(w)
        signal.append(legend)
        column.append(signal)

        column.append(text("Recent messages", "title-large"))
        self.recent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        column.append(self.recent)

        self.append(scroller(column))
        self.samples = []

    # SOS: hold three seconds, as on Android.
    def _sos_pressed(self, gesture, n, x, y):
        self._hold = GLib.timeout_add(3000, self._sos_fire)
        self.sos_button.set_label("Keep holding")

    def _sos_released(self, gesture, n, x, y):
        if self._hold:
            GLib.source_remove(self._hold)
            self._hold = None
        self.sos_button.set_label("Cancel SOS" if (self.app.state.sos or {}).get("active") else "Hold 3 seconds for SOS")

    def _sos_fire(self):
        self._hold = None
        s = self.app.state
        if (s.sos or {}).get("active"):
            api.post("/api/sos/cancel")
            self.text_contacts(sos.cancel_text(s.sos_name))
        else:
            api.post("/api/sos/activate", {"message": sos.mesh_text(s.sos_name, s.position())})
            self.text_contacts(sos.sms_text(s.sos_name, s.position()))
        self.app.poller.poll_now()
        return False

    def text_contacts(self, text: str) -> None:
        """The SOS by SMS to every emergency contact, from the phone's own SIM, as Android
        sends it; through the Bridge's SMS gateway, each logged as a sent text."""
        s = self.app.state
        if not s.contacts:
            return
        if not s.sms_ready():
            self.app.toast(f"SMS to your contacts did not go: {s.sms_reason()}")
            return
        me = (s.bridge or {}).get("node_id")
        for contact in s.contacts:
            result = api.post("/api/messages/send", {"text": text, "gateway": "cellular", "to": contact["phone"]})
            if result and result.get("error"):
                self.app.toast(f"SMS to {contact.get('name') or contact['phone']} failed: {result['error']}")
            else:
                api.record_sent(text, contact["phone"], "sms", me)

    def draw_chart(self, area, cr, width, height):
        rgba = Gdk.RGBA()
        rgba.parse(theme.MESH)
        pts = self.samples[-24:]
        cr.set_line_width(2)
        if len(pts) < 2:
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 0.35)
            cr.move_to(4, height / 2)
            cr.line_to(width - 4, height / 2)
            cr.stroke()
            return
        lo, hi = min(pts), max(pts)
        span = (hi - lo) or 1.0
        step = (width - 8) / (len(pts) - 1)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 0.25)
        cr.move_to(4, height - 4)
        for i, v in enumerate(pts):
            cr.line_to(4 + i * step, height - 8 - (v - lo) / span * (height - 16))
        cr.line_to(4 + (len(pts) - 1) * step, height - 4)
        cr.close_path()
        cr.fill()
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1.0)
        for i, v in enumerate(pts):
            x, y = 4 + i * step, height - 8 - (v - lo) / span * (height - 16)
            cr.line_to(x, y) if i else cr.move_to(x, y)
        cr.stroke()
        for i, v in enumerate(pts):
            cr.arc(4 + i * step, height - 8 - (v - lo) / span * (height - 16), 2.5, 0, 6.2832)
            cr.fill()

    def update(self, s: api.State) -> None:
        mesh_up, modem, hub, sms_up = s.mesh_connected(), s.modem_connected(), s.hub_configured(), s.sms_ready()
        lanes = [name for name, up in (("satellite", modem), ("mesh", mesh_up), ("SMS", sms_up), ("the Hub", hub)) if up]
        queued = sum(1 for m in s.messages if m.get("delivery_status") in ("queued", "pending", "sending"))
        if sms_up:
            self.sms.set_state("working", "Ready.", f"{s.sms_today()} today")
        else:
            self.sms.set_state("off", s.sms_reason() or "Allow SMS to send and receive texts.")
        names = [c.get("name") or c["phone"] for c in s.contacts]
        who = f"SMS to {sos.join_and(names)}, " if names else ""
        self.sos_text.set_text(f"Sends your position by satellite, the mesh, {who}and the Hub, and keeps trying until you cancel." if who else "Sends your position by satellite, the mesh and the Hub, and keeps trying until you cancel.")
        if not lanes:
            self.sentence.set_text("Nothing can send yet.")
            self.second.set_text("Start with your MeshSat node, below.")
        else:
            self.sentence.set_text("Messages can go out by " + (lanes[0] if len(lanes) == 1 else ", ".join(lanes[:-1]) + " and " + lanes[-1]) + ".")
            self.second.set_text(f"{queued} messages on the way." if queued else "")
        self.second.set_visible(bool(self.second.get_text()))

        own = s.own_node()
        if mesh_up:
            name = (s.bridge or {}).get("node_name") or (own or {}).get("long_name") or "your node"
            detail = f"Connected to {name}."
            if own and own.get("snr"):
                detail = f"Connected to {name}, signal {own.get('snr')} dB."
            if own and own.get("battery_level"):
                detail += " On USB power." if own["battery_level"] > 100 else f" Battery {own['battery_level']}%."
            self.mesh.set_state("working", detail, f"{len(s.others())} nodes", in_flight=queued > 0)
        elif s.node_service:
            self.mesh.set_state("trying", "Connecting to your node." if not s.bridge else "Reconnecting to your node.")
        else:
            self.mesh.set_state("off", "Connect a MeshSat node or a Meshtastic radio.")

        if modem:
            bars = (s.signal or {}).get("bars", 0)
            self.satellite.set_state("working", "Modem ready." if bars else "Modem ready, waiting for a satellite.", f"{bars}/5")
        elif not s.bridge:
            self.satellite.set_state("off", "Connect a MeshSat node to use its satellite modem.")
        elif s.modem and s.modem.get("port") not in ("", "supervisor"):
            self.satellite.set_state("trying", "Checking the modem.")
        else:
            self.satellite.set_state("off", "This radio has no satellite modem. Plug a RockBLOCK into USB-C.")

        if hub:
            bridge_id = (s.hub or {}).get("bridge_id") or ""
            self.hub.set_state("working", f"Connected as {bridge_id}." if bridge_id else "Connecting to the Hub.")
        else:
            self.hub.set_state("off", "Not set up. Paste the Hub's key to connect this device.")

        done = [mesh_up, hub, modem]
        self.started_count.set_text(f"{sum(done)} of 3 done")
        for dot, ok in zip(self.steps, done):
            for c in ("dot-green", "dot-muted"):
                dot.remove_css_class(c)
            dot.add_css_class("dot-green" if ok else "dot-muted")
        self.started.set_visible(not all(done[:2]))

        active = bool((s.sos or {}).get("active"))
        self.sos_button.set_label("Cancel SOS" if active else "Hold 3 seconds for SOS")

        self.samples = [m.get("rx_snr") for m in reversed(s.messages) if m.get("direction") == "rx" and m.get("rx_snr")]
        if self.samples:
            self.chart_min.set_text(f"min: {min(self.samples):.1f} dB")
            self.chart_avg.set_text(f"avg: {sum(self.samples) / len(self.samples):.1f} dB")
            self.chart_max.set_text(f"max: {max(self.samples):.1f} dB")
        self.chart.queue_draw()

        clear(self.recent)
        texts = [m for m in s.messages if m.get("portnum_name") == "TEXT_MESSAGE_APP" and m.get("decoded_text")][:20]
        if not texts:
            self.recent.append(text("No messages yet.", "body-medium", theme.TEXT_SECONDARY))
        for m in texts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
            row.append(text(when(m.get("rx_time")), "body-medium", theme.TEXT_SECONDARY, mono=True))
            lane = "satellite" if m.get("transport") in ("iridium", "iridium_imt") else "mesh"
            tag = text({"satellite": "Satellite", "mesh": "Mesh"}[lane], "body-medium", theme.lane_colour(lane))
            tag.set_size_request(theme.dp(64), -1)
            row.append(tag)
            out = m.get("direction") == "tx"
            row.append(text("↑" if out else "↓", "body-medium", theme.GREEN if out else theme.SIGNAL_ORANGE))
            body = text(m.get("decoded_text", ""), "body-large", ellipsize=True)
            body.set_hexpand(True)
            row.append(body)
            self.recent.append(row)
