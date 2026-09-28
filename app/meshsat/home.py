# SPDX-License-Identifier: GPL-3.0-or-later
"""Home, as ui/screens/DashboardScreen.kt and HomeLanes.kt: the wordmark with the night-mode
and arrange buttons, one sentence about what can go out and a second line, the lane card,
then the cards: Getting started (until it is done), SOS, Signal history, Recent messages."""
import os

from gi.repository import Gdk, Gtk

from . import api, sos, theme
from .model import home as words_of_home
from .model import words
from .screen import Screen
from .widgets import Card, HoldButton, LaneRow, Wordmark, clear, confirm, icon_button, name_widget, page, scroller, spacer, text, text_button, when

BRAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brand", "app-icon-1024.png")


class HomeScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        column = page(spacing=12)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        head.append(Wordmark(BRAND))
        head.append(spacer())
        self.night_button = icon_button("outlined-nights-stay", app.toggle_night, 24, tooltip="Night mode off" if app.night else "Night mode on")
        head.append(self.night_button)
        head.append(icon_button("outlined-swap-vert", self.arrange, 24, tooltip="Arrange Home"))
        column.append(head)

        self.sentence = text("Nothing can send yet.", "headline-small", wrap=True)
        column.append(self.sentence)
        self.second = text("Start with your MeshSat node, below.", "body-large", theme.TEXT_SECONDARY, wrap=True)
        column.append(self.second)

        lanes = Card(padded=False, spacing=0)
        self.lanes = {}
        for i, (lane, title) in enumerate((("satellite", "Satellite"), ("mesh", "Mesh"), ("sms", "SMS"), ("hub", "Hub"))):
            if i:
                sep = Gtk.Box()
                sep.add_css_class("lane-sep")
                lanes.append(sep)
            row = LaneRow(lane, title, lambda k=lane: app.open_lane(k))
            self.lanes[lane] = row
            lanes.append(row)
        column.append(lanes)

        # Onboarding.kt: the checklist, until the node and the Hub are done.
        self.started = Card()
        started_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        started_top.append(text("Getting started", "title-medium"))
        started_top.append(spacer())
        self.started_count = text("0 of 4 done", "body-medium", theme.TEXT_SECONDARY, mono=True)
        started_top.append(self.started_count)
        self.started.append(started_top)
        self.steps = []
        for _ in range(4):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
            dot = Gtk.Box()
            dot.add_css_class("dot")
            dot.add_css_class("dot-muted")
            dot.set_valign(Gtk.Align.CENTER)
            row.append(dot)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
            title_label = text("", "body-large")
            detail_label = text("", "body-medium", theme.TEXT_SECONDARY)
            texts.append(title_label)
            texts.append(detail_label)
            row.append(texts)
            self.started.append(row)
            self.steps.append((dot, title_label, detail_label))
        column.append(self.started)

        # SosCard: the reach sentence, the hold bar, the contacts button; while an SOS is on,
        # since when, and Cancel.
        sos_card = Card()
        sos_card.append(text("SOS", "title-medium"))
        self.sos_text = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        sos_card.append(self.sos_text)
        self.hold = HoldButton("Hold 3 seconds for SOS", self.sos_fire, self.sos_activate)
        self.hold.set_margin_top(theme.dp(4))
        sos_card.append(self.hold)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.contacts_button = text_button("Emergency contacts", lambda: app.open_route("setup/safety"))
        actions.append(self.contacts_button)
        actions.append(spacer())
        self.see = text_button("See where it went", lambda: app.open_route("sos"))
        actions.append(self.see)
        self.cancel = text_button("Cancel SOS", self.sos_cancel_asked)
        actions.append(self.cancel)
        sos_card.append(actions)
        column.append(sos_card)

        signal = Card()
        signal.append(text("Signal history", "title-medium"))
        self.chart = Gtk.DrawingArea()
        self.chart.set_content_height(theme.dp(72))
        self.chart.set_draw_func(self.draw_chart)
        name_widget(self.chart, "Signal history chart")
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
        self._recent_key = None

        self.append(scroller(column))
        self.samples = []

    def night_changed(self, on: bool) -> None:
        self.night_button.set_tooltip_text("Night mode off" if on else "Night mode on")
        name_widget(self.night_button, "Night mode off" if on else "Night mode on")

    def arrange(self) -> None:
        self.app.toast("Arranging Home comes with the next release.")

    # SOS: hold three seconds, as on Android; a screen reader or a test asks in a dialog.
    def sos_activate(self, how: str) -> None:
        if (self.app.state.sos or {}).get("active"):
            self.sos_cancel_asked()
            return
        if how == "tap":
            self.app.toast("Hold 3 seconds for SOS")
            return
        confirm(self.app, "Send an SOS?", "Your position goes out on every route this phone has, and the phone keeps trying until you cancel.",
                "Send SOS", self.sos_fire, cancel="Don't send", danger=True)

    def sos_cancel_asked(self) -> None:
        confirm(self.app, "Cancel the SOS?", "Nothing more goes out, and everyone who got the SOS is told you are safe.", "Cancel SOS", self.sos_cancel, cancel="Keep it on")

    def sos_fire(self) -> None:
        s = self.app.state
        if (s.sos or {}).get("active"):
            self.sos_cancel()
            return
        body = {"message": sos.mesh_text(s.sos_name, s.position()), "trigger": "hold"}
        self.app.toast("Sending the SOS")

        def sent(answer: api.Answer) -> None:
            if not answer.ok:
                self.app.toast(f"The SOS did not start: {answer.error}")
            self.app.poller.poll_now()

        api.fetch("/api/sos/activate", sent, method="POST", body=body)
        self.text_contacts(sos.sms_text(s.sos_name, s.position()))

    def sos_cancel(self) -> None:
        s = self.app.state
        api.fetch("/api/sos/cancel", lambda answer: self.app.poller.poll_now(), method="POST")
        self.text_contacts(sos.cancel_text(s.sos_name))

    def text_contacts(self, message: str) -> None:
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
            def sent(answer: api.Answer, contact=contact) -> None:
                if not answer.ok:
                    self.app.toast(f"SMS to {contact.get('name') or contact['phone']} failed: {answer.error}")
                else:
                    api.record_sent(message, contact["phone"], "sms", me)

            api.fetch("/api/messages/send", sent, method="POST", body={"text": message, "gateway": "cellular", "to": contact["phone"]})

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
        lanes = words_of_home.lanes(s)
        waiting = words_of_home.queued(s)
        for lane, (state, detail, figure) in lanes.items():
            self.lanes[lane].set_state(state, detail, figure, in_flight=(waiting > 0 and lane in ("mesh", "satellite") and state == "working"))
        first, second = words_of_home.sentence(lanes, s)
        self.sentence.set_text(first)
        self.second.set_text(second or "")
        self.second.set_visible(bool(second))

        steps = words_of_home.checklist(s, lanes)
        self.started_count.set_text(f"{sum(1 for _t, _d, done in steps if done)} of {len(steps)} done")
        for (dot, title_label, detail_label), (title, detail, done) in zip(self.steps, steps):
            title_label.set_text(title)
            detail_label.set_text(detail)
            for c in ("dot-green", "dot-muted"):
                dot.remove_css_class(c)
            dot.add_css_class("dot-green" if done else "dot-muted")
        self.started.set_visible(not (steps[0][2] and steps[1][2]))

        active = bool((s.sos or {}).get("active"))
        if active:
            self.sos_text.set_text(f"SOS is on since {when((s.sos or {}).get('started_at_unix')) or sos_clock(s.sos)}. Sent {(s.sos or {}).get('sends', 0)} times.")
        else:
            self.sos_text.set_text(words_of_home.reach_sentence(s, lanes))
        self.hold.set_visible(not active)
        self.cancel.set_visible(active)
        self.see.set_visible(active)
        self.contacts_button.set_visible(not active)
        self.contacts_button.set_label(words_of_home.contacts_button(s))

        self.samples = [m.get("rx_snr") for m in reversed(s.messages) if m.get("direction") == "rx" and m.get("rx_snr")]
        if self.samples:
            self.chart_min.set_text(f"min: {min(self.samples):.1f} dB")
            self.chart_avg.set_text(f"avg: {sum(self.samples) / len(self.samples):.1f} dB")
            self.chart_max.set_text(f"max: {max(self.samples):.1f} dB")
        self.chart.queue_draw()

        texts = [m for m in s.messages if m.get("portnum_name") == "TEXT_MESSAGE_APP" and m.get("decoded_text")][:20]
        key = tuple((m.get("id"), m.get("rx_time"), m.get("decoded_text")) for m in texts)
        if key == self._recent_key:
            return
        self._recent_key = key
        clear(self.recent)
        if not texts:
            self.recent.append(text("No messages yet.", "body-medium", theme.TEXT_SECONDARY))
        for m in texts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
            row.append(text(when(m.get("rx_time")), "body-medium", theme.TEXT_SECONDARY, mono=True))
            lane = words.transport_lane(m.get("transport") or "mesh")
            lane = lane if lane in ("satellite", "sms", "hub") else "mesh"
            tag = text(words.transport(m.get("transport") or "mesh"), "body-medium", theme.lane_colour(lane))
            tag.set_size_request(theme.dp(64), -1)
            row.append(tag)
            out = m.get("direction") == "tx"
            row.append(text("↑" if out else "↓", "body-medium", theme.GREEN if out else theme.SIGNAL_ORANGE))
            body = text(m.get("decoded_text", ""), "body-large", ellipsize=True)
            body.set_hexpand(True)
            row.append(body)
            self.recent.append(row)


def sos_clock(sos_state: dict | None) -> str:
    """HH:MM of the SOS start, from the Bridge's RFC 3339 stamp (local time, as Android's clock())."""
    stamp = (sos_state or {}).get("started_at") or ""
    if isinstance(stamp, str) and len(stamp) >= 16:
        return stamp[11:16] + " UTC"
    return "now"
