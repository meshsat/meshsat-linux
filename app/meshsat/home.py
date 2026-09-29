# SPDX-License-Identifier: GPL-3.0-or-later
"""Home, as ui/screens/DashboardScreen.kt, HomeLanes.kt and Onboarding.kt: the wordmark with the
night-mode and arrange buttons, one sentence about what can go out and a second line, the lane
card, Getting started (until it is done or hidden), then the cards in the order Arrange Home
keeps: SOS, Message queue, Your position, the signals (the satellite sky, the mobile signal),
Satellite mailbox, Recent messages."""
import time

from gi.repository import Gdk, Gtk

from . import api, theme
from .mailbox import MailboxButton
from .messages import sms_as_messages
from .model import dashboard, sky
from .model import home as words_of_home
from .model import sosrun, words
from .pages.sos import ask_test
from .passes import SkyChart, sky_legend
from .screen import Screen
from .widgets import (Card, HoldButton, LaneRow, Sheet, Wordmark, clear, confirm, filled_button, icon, icon_button, name_widget, outlined_button, page, paint,
                      scroller, spacer, text, text_button, when)

SKY_TITLE = "Satellite signal and passes"
SKY_WINDOW = "3 h back, 3 h ahead"


def night_icon(on: bool) -> str:
    return "filled-nights-stay" if on else "outlined-nights-stay"


class HomeScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        column = page(spacing=12)
        self.stats = []  # GET /api/deliveries/stats, every 5 s while on view
        self.passes = []  # GET /api/iridium/passes, now-3 h to now+6 h, every 5 min
        self.sky_signals, self.sky_sessions = [], []  # the last 3 h of readings and sessions, every 10 min
        self.mobile = []  # GET /api/cellular/signal/history, the last 6 h

        # HomeHeader: the lockup, night mode, Arrange
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        head.set_margin_start(theme.dp(4))
        mark = Wordmark()
        name_widget(mark, "MeshSat")
        head.append(mark)
        head.append(spacer())
        self.night_button = icon_button(night_icon(app.night), app.toggle_night, 24, theme.TEXT_SECONDARY, tooltip="Night mode off" if app.night else "Night mode on")
        head.append(self.night_button)
        head.append(icon_button("outlined-swap-vert", self.arrange, 24, theme.TEXT_SECONDARY, tooltip=dashboard.ARRANGE_TITLE))
        column.append(head)

        # HomeLanes: the sentence and the line under it, 4 dp apart, then the lanes
        said = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        said.set_margin_start(theme.dp(4))
        said.set_margin_end(theme.dp(4))
        self.sentence = text("Nothing can send yet.", "headline-small", wrap=True)
        said.append(self.sentence)
        self.second = text("Start with your MeshSat node, below.", "body-large", theme.TEXT_SECONDARY, wrap=True)
        said.append(self.second)
        column.append(said)

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

        # SetupChecklistCard (Onboarding.kt:128-195)
        self.started = Card(padded=False, spacing=0)
        self.started.add_css_class("checklist")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        top.set_margin_start(theme.dp(12))
        top.set_margin_end(theme.dp(4))
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        titles.set_hexpand(True)
        titles.set_valign(Gtk.Align.CENTER)
        titles.append(text(dashboard.GETTING_STARTED, "title-medium"))
        self.started_count = text("", "body-small", theme.TEXT_SECONDARY)
        titles.append(self.started_count)
        top.append(titles)
        hide = text_button(dashboard.HIDE, self.hide_checklist)
        hide.add_css_class("off-white")
        hide.set_valign(Gtk.Align.CENTER)
        top.append(hide)
        self.started.append(top)
        self.step_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.started.append(self.step_rows)
        self._steps_key = None
        column.append(self.started)

        # The cards, in the order Arrange Home keeps
        self.cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        column.append(self.cards)
        self.show_checklist(False)
        self.build_sos_card()
        self.build_queue_card()
        self.build_position_card()
        self.build_signals()
        self.mailbox_card = Card(spacing=4)
        self.mailbox_card.append(text(dashboard.MAILBOX_TITLE, "title-medium"))
        self.mailbox = MailboxButton(self)
        self.mailbox_card.append(self.mailbox)
        self.mailbox_card.set_visible(False)
        self.activity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        heading = text(dashboard.RECENT_TITLE, "title-medium")
        heading.set_margin_top(theme.dp(4))
        self.activity.append(heading)
        self.recent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.activity.append(self.recent)
        self._recent_key = None
        self.card_widgets = {"sos": self.sos_card, "queue": self.queue_card, "location": self.position_card, "signals": self.signals,
                             "mailbox": self.mailbox_card, "activity": self.activity}
        self.order = dashboard.home_order(app.prefs.get("dashboard_card_order", ""))
        self.place_cards()

        self.append(scroller(column))

    # ── Building ──────────────────────────────────────────────────────────────────────────────
    def build_sos_card(self) -> None:
        """SosCard (SosScreens.kt): hold to send, or where the SOS or the alarm test in progress stands."""
        app = self.app
        self.sos_card = Card()
        self.sos_title = text("SOS", "title-medium")
        self.sos_card.append(self.sos_title)
        self.sos_text = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.sos_card.append(self.sos_text)
        # 8 dp under the text: the card's own spacedBy(8), nothing more
        self.hold = HoldButton("Hold 3 seconds for SOS", self.sos_fire, self.sos_activate)
        self.sos_card.append(self.hold)
        # TextButton { Text(..., color = OffWhite) }: both words in OffWhite, not the orange of a
        # plain TextButton
        self.idle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.contacts_button = text_button("Emergency contacts", self.open_contacts)
        self.contacts_button.add_css_class("off-white")
        self.idle_row.append(self.contacts_button)
        self.test_button = text_button("Test the alarm", self.test_asked)
        self.test_button.add_css_class("off-white")
        self.idle_row.append(self.test_button)
        self.sos_card.append(self.idle_row)
        self.active_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        self.see = filled_button("See where it went", lambda: app.open_route("sos"))
        self.see.remove_css_class("filled")
        self.see.add_css_class("tonal")
        self.active_row.append(self.see)
        # OutlinedButton { Text("Cancel SOS" / "Stop test", color = OffWhite) }; the label is kept
        # when set_label() changes its words, and its colour with it
        self.cancel = outlined_button("Cancel SOS", self.sos_cancel_asked)
        paint(self.cancel.get_child(), theme.OFF_WHITE)
        self.active_row.append(self.cancel)
        self.sos_card.append(self.active_row)

    def build_queue_card(self) -> None:
        """The "Message queue" card: a bar per lane, the four counts, and the way to the queue."""
        self.queue_card = Card(spacing=4)
        self.queue_card.append(text(dashboard.QUEUE_TITLE, "title-medium"))
        self.queue_bars = []
        for (label, _channels), lane in zip(dashboard.LANES, ("satellite", "mesh", "sms")):
            bar = QueueBar(label, theme.lane_colour(lane))
            self.queue_bars.append(bar)
            self.queue_card.append(bar)
        badges = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0, homogeneous=True)
        badges.set_margin_top(theme.dp(8))
        self.badges = []
        for label, _count, tone in dashboard.queue_counts([])["badges"]:
            badge = StatBadge(label, {"amber": theme.AMBER, "red": theme.RED, "muted": theme.TEXT_MUTED}[tone])
            self.badges.append(badge)
            badges.append(badge)
        self.queue_card.append(badges)
        open_queue = text_button(dashboard.OPEN_QUEUE, lambda: self.app.open_route("deliveries"))
        open_queue.add_css_class("off-white")
        open_queue.set_halign(Gtk.Align.START)
        self.queue_card.append(open_queue)

    def build_position_card(self) -> None:
        """"Your position": the phone's own fix, as Android's (never the node's or a typed one)."""
        self.position_card = Card(spacing=4)
        self.position_card.append(text(dashboard.POSITION_TITLE, "title-medium"))
        self.pos_coords = text("", "title-medium")
        self.pos_age = text("", "body-small", theme.TEXT_SECONDARY)
        self.pos_extra = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        self.pos_waiting = text(dashboard.WAITING_FOR_FIX, "body-medium", theme.TEXT_MUTED, wrap=True)
        for w in (self.pos_coords, self.pos_age, self.pos_extra, self.pos_waiting):
            self.position_card.append(w)

    def build_signals(self) -> None:
        """The signals group: the satellite sky card, then the mobile signal of the last 6 hours,
        each only with something to draw. Android's third chart, "Mesh signal strength", is the
        Bluetooth RSSI between phone and node, which this edition cannot read (not ported)."""
        self.signals = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.sky_card = Card(spacing=4)
        self.sky_card.append(text(SKY_TITLE, "title-medium"))
        self.sky = SkyChart(compact=True)
        chart = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        chart.append(self.sky)
        chart.append(sky_legend(True, SKY_WINDOW))
        tap = Gtk.Button()
        tap.add_css_class("sky-tap")
        tap.set_child(chart)
        name_widget(tap, SKY_TITLE, "Opens the satellite passes")
        tap.connect("clicked", lambda *_: self.app.open_route("passes"))
        self.sky_card.append(tap)
        self.sky_card.set_visible(False)
        self.signals.append(self.sky_card)
        self.mobile_chart = SignalChart(dashboard.MOBILE_TITLE, dashboard.MOBILE_RANGE, theme.SMS)
        self.mobile_chart.set_visible(False)
        self.signals.append(self.mobile_chart)
        self.signals.set_visible(False)

    def place_cards(self) -> None:
        clear(self.cards)
        for card in self.order:
            self.cards.append(self.card_widgets[card])

    # ── Life ─────────────────────────────────────────────────────────────────────────────────
    def on_show(self) -> None:
        self.every(5, self.load_stats)
        self.every(5, self.render_position)
        self.every(300, self.load_passes)
        self.every(600, self.load_sky_history)
        self.every(30, self.render_sky)
        self.every(60, self.load_mobile)
        if self.app.state.modem_connected():
            self.mailbox.load()

    def load_stats(self) -> None:
        self.fetch("/api/deliveries/stats", self.stats_loaded)

    def stats_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.stats = answer.body
        elif (answer.ok and answer.body is None) or answer.status == 404:
            # The Bridge answers null for an empty queue (a Go nil slice): nothing waits, and the
            # last counts must not stay on the card.
            self.stats = []
        self.render_queue()
        if self.app.state.polled_at:
            self.render_lanes(self.app.state)

    def load_passes(self) -> None:
        """The passes the satellite lane and the sky card read: now-3 h to now+6 h, 5° and up,
        for the phone's position (else the node's or the one typed in, as the passes page)."""
        position = self.app.state.position()
        if not position:
            self.passes = []
            self.render_sky()
            return
        lat, lon, _source = position
        start = int(time.time()) - 3 * 3600
        self.fetch(f"/api/iridium/passes?lat={lat}&lon={lon}&hours=9&min_elev=5&start={start}", self.passes_loaded, timeout=20.0)

    def passes_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.passes = sorted(answer.body.get("passes") or [], key=lambda p: p.get("aos", 0))
            self.render_sky()
            if self.app.state.polled_at:
                self.render_lanes(self.app.state)

    def load_sky_history(self) -> None:
        now = int(time.time())
        start = now - 3 * 3600
        self.fetch(f"/api/iridium/signal/history?source=iridium&from={start}&to={now}", self.signals_loaded)
        self.fetch(f"/api/iridium/signal/history?source=gss&from={start}&to={now}", self.sessions_loaded)

    def signals_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.sky_signals = [{"at": int(r.get("timestamp") or 0), "bars": float(r.get("value") or 0)} for r in answer.body if isinstance(r, dict)]
            self.render_sky()

    def sessions_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.sky_sessions = [{"at": int(r.get("timestamp") or 0), "ok": float(r.get("value") or 0) >= 1} for r in answer.body if isinstance(r, dict)]
            self.render_sky()

    def load_mobile(self) -> None:
        self.fetch("/api/cellular/signal/history?hours=6", self.mobile_loaded)

    def mobile_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.mobile = [{"timestamp": int(p.get("timestamp") or 0) * 1000, "value": float(p.get("dbm") or 0)} for p in answer.body if isinstance(p, dict)]
            self.mobile.sort(key=lambda r: r["timestamp"])
        elif answer.status == 404:
            self.mobile = []
        self.mobile_chart.set_records(self.mobile)
        self.mobile_chart.set_visible(bool(self.mobile))
        self.signals.set_visible(self.sky_card.get_visible() or self.mobile_chart.get_visible())

    # ── Taps ─────────────────────────────────────────────────────────────────────────────────
    def night_changed(self, on: bool) -> None:
        self.night_button.set_child(icon(night_icon(on), 24, theme.TEXT_SECONDARY))
        self.night_button.set_tooltip_text("Night mode off" if on else "Night mode on")
        name_widget(self.night_button, "Night mode off" if on else "Night mode on")

    def hide_checklist(self) -> None:
        self.app.prefs.set(checklist_dismissed=True)
        self.show_checklist(False)

    def show_checklist(self, shown: bool) -> None:
        """Getting started, or its empty place: Android's hidden checklist is still an item of
        Home's LazyColumn, an empty one, so the 12 dp between items comes twice and the first card
        stands 24 dp under the lanes. GTK leaves a hidden child out of the spacing altogether: the
        cards take the second 12 dp as their own margin."""
        self.started.set_visible(shown)
        self.cards.set_margin_top(0 if shown else theme.dp(12))

    def arrange(self) -> None:
        ArrangeDialog(self.app, self.order, self.arranged)

    def arranged(self, order: list) -> None:
        self.order = list(order)
        self.app.prefs.set(dashboard_card_order=",".join(self.order))
        self.place_cards()

    # SOS: hold three seconds, as on Android; a screen reader or a test asks in a dialog. The three
    # dialogs answer as SosScreens.kt's do: a filled button (MeshSatRed with ink words for "Send
    # SOS", the orange Button for the other two) and the way out in OffWhite.
    def sos_activate(self, how: str) -> None:
        if how == "tap":
            self.app.toast("Hold 3 seconds for SOS")
            return
        confirm(self.app, "Send an SOS?", "Your position goes out on every route this phone has, and the phone keeps trying until you cancel.",
                "Send SOS", self.sos_fire, cancel="Don't send", danger=True, filled=True, cancel_colour=theme.OFF_WHITE)

    def sos_cancel_asked(self) -> None:
        run = self.app.sos.active()
        if run is not None and run.test:
            self.app.sos.cancel(self.app.state)  # a test stops without a question
            return
        confirm(self.app, "Cancel the SOS?", "Nothing more goes out, and everyone who got the SOS is told you are safe.", "Cancel SOS", self.sos_cancel, cancel="Keep it on",
                filled=True, cancel_colour=theme.OFF_WHITE)

    def sos_fire(self) -> None:
        """The hold ran its course, or the dialog said Send: a real SOS, which replaces a test."""
        self.app.sos.start(self.app.state, test=False, trigger="hold")
        self.app.poller.poll_now()

    def sos_cancel(self) -> None:
        self.app.sos.cancel(self.app.state)
        self.app.poller.poll_now()

    def open_contacts(self) -> None:
        s = self.app.state
        self.app.open_route("setup/safety" if s.sms_ready() else "setup/node")

    def test_asked(self) -> None:
        """TestAlarmDialog: what the test text is, what each route carries and costs (the same
        dialog as Setup > Safety's, pages/sos.ask_test)."""
        ask_test(self.app, self.test_fire)

    def test_fire(self) -> None:
        self.app.sos.start(self.app.state, test=True, trigger="hold")
        self.app.poller.poll_now()

    # ── Drawing ──────────────────────────────────────────────────────────────────────────────
    def update(self, s: api.State) -> None:
        self.render_lanes(s)
        self.render_checklist(s)
        self.update_sos_card(s)
        self.render_position()
        connected = s.modem_connected()
        if connected and not self.mailbox_card.get_visible() and self.alive:
            self.mailbox.load()
        self.mailbox_card.set_visible(connected)
        self.mailbox.set_connected(connected)
        self.render_recent(s)

    def render_lanes(self, s: api.State) -> None:
        pass_line = dashboard.pass_line(self.passes, time.time())
        lanes = words_of_home.lanes(s, self.stats, pass_line)
        depths = words_of_home.depths(self.stats)
        for lane, (state, detail, figure) in lanes.items():
            self.lanes[lane].set_state(state, detail, figure, in_flight=depths.get(lane, 0) > 0)
        first, second = words_of_home.sentence(lanes, s, self.stats)
        self.sentence.set_text(first)
        self.second.set_text(second or "")
        self.second.set_visible(bool(second))

    def render_checklist(self, s: api.State) -> None:
        steps = words_of_home.checklist(s)
        shown = dashboard.checklist_shown(steps, bool(self.app.prefs.get("checklist_dismissed", False)))
        self.show_checklist(shown)
        if not shown:
            return
        self.started_count.set_text(dashboard.checklist_count(steps))
        key = tuple((title, done) for title, _detail, done, _route in steps)
        if key == self._steps_key:
            return
        self._steps_key = key
        clear(self.step_rows)
        for title, detail, done, route in steps:
            self.step_rows.append(checklist_row(title, detail, done, None if done else (lambda r=route: self.app.open_route(r))))

    def render_queue(self) -> None:
        counts = dashboard.queue_counts(self.stats)
        for bar, (_label, depth, fill) in zip(self.queue_bars, counts["lanes"]):
            bar.set_depth(depth, fill)
        for badge, (_label, count, _tone) in zip(self.badges, counts["badges"]):
            badge.set_count(count)

    def render_position(self) -> None:
        fix = self.app.state.fix
        lines = dashboard.position_lines(fix)
        waiting = fix is None
        self.pos_waiting.set_visible(waiting)
        for w in (self.pos_coords, self.pos_age, self.pos_extra):
            w.set_visible(not waiting)
        if waiting:
            return
        self.pos_coords.set_text(lines[0])
        self.pos_age.set_text(lines[1])
        self.pos_extra.set_text(lines[2] if len(lines) > 2 else "")
        self.pos_extra.set_visible(len(lines) > 2)

    def render_sky(self) -> None:
        now = int(time.time())
        shown = sky.card_shown(self.passes, self.sky_signals, now)  # SatelliteSkyCard's rule
        self.sky_card.set_visible(shown)
        if shown:
            self.sky.set_data(self.passes, self.sky_signals, self.sky_sessions, now - 3 * 3600, now + 3 * 3600, now)
        self.signals.set_visible(shown or self.mobile_chart.get_visible())

    def render_recent(self, s: api.State) -> None:
        texts = dashboard.recent(s.messages, sms_as_messages(s))
        key = tuple((m.get("id"), m.get("rx_time"), m.get("decoded_text"), m.get("direction")) for m in texts)
        if key == self._recent_key:
            return
        self._recent_key = key
        clear(self.recent)
        if not texts:
            empty = text(dashboard.NO_MESSAGES, "body-medium", theme.TEXT_MUTED)
            empty.set_margin_top(theme.dp(8))
            empty.set_margin_bottom(theme.dp(8))
            self.recent.append(empty)
        for m in texts:
            self.recent.append(activity_row(m))

    def update_sos_card(self, s: api.State) -> None:
        """SosCard: hold to send, or where the SOS or the test in progress stands. Where an SOS
        would go is SosReach's: every route set up, not only the ones up this minute (a modem this
        phone has had, the node it paired or started, the contacts, the Hub)."""
        run = self.app.sos.active()
        bridge_sos = (s.sos or {}) if (s.sos or {}).get("active") else None
        for c in ("sos-test", "sos-on"):
            self.sos_card.remove_css_class(c)
        seen = self.app.prefs.get(words_of_home.MODEM_SEEN, "")
        anywhere = words_of_home.reach(s, seen)["anywhere"]
        if run is None and bridge_sos is None:
            self.sos_title.set_text("SOS")
            paint(self.sos_title, theme.TEXT_PRIMARY)
            self.sos_text.set_text(words_of_home.reach_sentence(s, seen))
            self.hold.set_visible(anywhere)
            self.idle_row.set_visible(True)
            self.active_row.set_visible(False)
            self.contacts_button.set_label(words_of_home.contacts_button(s))
            self.test_button.set_visible(anywhere)
            return
        test = run is not None and run.test
        self.sos_card.add_css_class("sos-test" if test else "sos-on")
        if test:
            self.sos_title.set_text("Alarm test running")
            paint(self.sos_title, theme.AMBER)
            self.sos_text.set_text(sosrun.summary(run.routes))
        else:
            started = run.id if run is not None else None
            self.sos_title.set_text(f"SOS is on since {sosrun.clock(started)}" if started else f"SOS is on since {sos_clock(bridge_sos)}")
            paint(self.sos_title, theme.RED)
            if run is not None:
                self.sos_text.set_text(sosrun.summary(run.routes))
            else:
                sends = (bridge_sos or {}).get("sends") or 0
                self.sos_text.set_text(f"Sent {sends} times so far. It keeps trying until you cancel." if sends else "Sending your position. It keeps trying until you cancel.")
        # A real emergency during a test: the hold still works, and replaces the test.
        self.hold.set_visible(test)
        self.idle_row.set_visible(False)
        self.active_row.set_visible(True)
        self.cancel.set_label("Stop test" if test else "Cancel SOS")


def checklist_row(title: str, detail: str, done: bool, on_tap) -> Gtk.Widget:
    """A step: the check or the empty ring (22 dp, "Done"/"To do"), 12 dp, the title in bodyLarge
    (TextSecondary when done, OffWhite when not) over the detail in bodySmall TextMuted. Only a
    step still to do opens its page."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
    mark = icon("outlined-check-circle" if done else "outlined-radio-button-unchecked", 22, theme.GREEN if done else theme.TEXT_MUTED)
    name_widget(mark, dashboard.DONE if done else dashboard.TO_DO)
    row.append(mark)
    texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    texts.set_hexpand(True)
    texts.append(text(title, "body-large", theme.TEXT_SECONDARY if done else theme.OFF_WHITE, wrap=True))
    texts.append(text(detail, "body-small", theme.TEXT_MUTED, wrap=True))
    row.append(texts)
    if on_tap is None:
        row.add_css_class("checklist-row")
        name_widget(row, title, dashboard.DONE)
        return row
    button = Gtk.Button()
    button.add_css_class("checklist-row")
    button.set_child(row)
    name_widget(button, title, dashboard.TO_DO)
    button.connect("clicked", lambda *_: on_tap())
    return button


def activity_row(m: dict) -> Gtk.Widget:
    """ActivityLogEntry: HH:mm, the transport in its colour (64 dp), the arrow, the first 80 characters."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
    row.set_margin_top(theme.dp(3))
    row.set_margin_bottom(theme.dp(3))
    row.append(text(when(m.get("rx_time")), "label-small", theme.TEXT_MUTED))
    lane = dashboard.recent_lane(m.get("transport"))
    tag = text(words.transport(m.get("transport") or "mesh"), "label-small", theme.lane_colour(lane) if lane else theme.TEXT_MUTED, ellipsize=True)
    tag.set_size_request(theme.dp(64), -1)
    tag.set_max_width_chars(1)
    row.append(tag)
    out = m.get("direction") == "tx"
    arrow = text("↑" if out else "↓", "body-small", theme.GREEN if out else theme.SIGNAL_ORANGE if m.get("direction") == "rx" else theme.TEXT_MUTED)
    arrow.add_css_class("bold")
    row.append(arrow)
    body = text(dashboard.recent_text(m.get("decoded_text", "")), "body-small", ellipsize=True)
    body.set_hexpand(True)
    body.set_max_width_chars(1)
    row.append(body)
    return row


class QueueBar(Gtk.Box):
    """QueueBar: the lane's name (bodySmall TextMuted, 64 dp), a 6 dp track with the fill in the
    lane's colour (depth/20, 5 % to 100 %, only with something waiting), the depth in bold (24 dp)."""

    def __init__(self, label: str, colour: str):
        # A group, so its name ("Satellite: 3 waiting") reaches a screen reader
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), accessible_role=Gtk.AccessibleRole.GROUP)
        self.label, self.colour, self.fill = label, colour, 0.0
        self.set_margin_top(theme.dp(2))
        self.set_margin_bottom(theme.dp(2))
        name = text(label, "body-small", theme.TEXT_MUTED)
        name.set_size_request(theme.dp(64), -1)
        self.append(name)
        self.track = Gtk.DrawingArea()
        self.track.set_hexpand(True)
        self.track.set_valign(Gtk.Align.CENTER)
        self.track.set_content_height(theme.dp(6))
        self.track.set_draw_func(self.draw)
        self.append(self.track)
        self.depth = text("0", "body-small")
        self.depth.add_css_class("bold")
        self.depth.set_size_request(theme.dp(24), -1)
        self.append(self.depth)
        name_widget(self, f"{label}: 0 waiting")

    def set_depth(self, depth: int, fill: float) -> None:
        self.depth.set_text(str(depth))
        self.fill = fill
        name_widget(self, f"{self.label}: {depth} waiting")
        self.track.queue_draw()

    def draw(self, area, cr, w, h):
        def rounded(width):
            r = min(theme.dp(3), h / 2, width / 2)
            cr.new_sub_path()
            cr.arc(width - r, r, r, -1.5708, 0)
            cr.arc(width - r, h - r, r, 0, 1.5708)
            cr.arc(r, h - r, r, 1.5708, 3.1416)
            cr.arc(r, r, r, 3.1416, 4.7124)
            cr.close_path()

        colour = Gdk.RGBA()
        colour.parse(theme.BORDER)
        cr.set_source_rgba(colour.red, colour.green, colour.blue, 1)
        rounded(w)
        cr.fill()
        if self.fill > 0:
            colour.parse(self.colour)
            cr.set_source_rgba(colour.red, colour.green, colour.blue, 1)
            rounded(max(1.0, w * self.fill))
            cr.fill()


class StatBadge(Gtk.Box):
    """StatBadge: the count in titleMedium bold in its colour over the label in labelSmall TextMuted."""

    def __init__(self, label: str, colour: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, accessible_role=Gtk.AccessibleRole.GROUP)
        self.label = label
        self.set_halign(Gtk.Align.CENTER)
        self.count = text("0", "title-medium", colour, xalign=0.5)
        self.count.add_css_class("bold")
        self.append(self.count)
        self.append(text(label, "label-small", theme.TEXT_MUTED, xalign=0.5))
        name_widget(self, f"{label}: 0")

    def set_count(self, count: int) -> None:
        self.count.set_text(str(count))
        name_widget(self, f"{self.label}: {count}")


class SignalChart(Gtk.Box):
    """SignalChart (DashboardScreen.kt:433-571): the title and the newest value, the first and last
    times, 80 dp of chart with 30-minute averages, and min, avg, max under it."""

    def __init__(self, title: str, value_range: tuple, colour: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("card")
        self.add_css_class("card-pad")
        self.low, self.high = value_range
        self.colour = colour
        self.points = []
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        head = text(title, "title-medium", wrap=True)
        head.set_hexpand(True)
        top.append(head)
        self.latest = text("", "body-medium", colour)
        self.latest.set_valign(Gtk.Align.START)
        top.append(self.latest)
        self.append(top)
        self.times = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.times.set_margin_top(theme.dp(2))
        self.first_time = text("", "label-small", theme.TEXT_MUTED)
        self.first_time.set_hexpand(True)
        self.times.append(self.first_time)
        self.last_time = text("", "label-small", theme.TEXT_MUTED)
        self.times.append(self.last_time)
        self.append(self.times)
        self.area = Gtk.DrawingArea()
        self.area.set_content_height(theme.dp(76))
        self.area.set_margin_top(theme.dp(4))
        self.area.set_draw_func(self.draw)
        name_widget(self.area, title)
        self.append(self.area)
        self.summary = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.min = text("", "label-small", theme.TEXT_MUTED)
        self.avg = text("", "label-small", theme.TEXT_MUTED, xalign=0.5)
        self.max = text("", "label-small", theme.TEXT_MUTED, xalign=1.0)
        for w in (self.min, self.avg, self.max):
            w.set_hexpand(True)
            self.summary.append(w)
        self.append(self.summary)

    def set_records(self, records: list) -> None:
        summary = dashboard.chart_summary(records)
        self.points = dashboard.chart_points(records) if records else []
        if summary is None:
            return
        self.latest.set_text(summary["latest"])
        self.times.set_visible(len(records) >= 2)
        if len(records) >= 2:
            self.first_time.set_text(when(records[0]["timestamp"] / 1000))
            self.last_time.set_text(when(records[-1]["timestamp"] / 1000))
        self.min.set_text(summary["min"])
        self.avg.set_text(summary["avg"])
        self.max.set_text(summary["max"])
        self.area.queue_draw()

    def draw(self, area, cr, w, h):
        rgba = Gdk.RGBA()
        rgba.parse(theme.BORDER)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        cr.set_line_width(0.5)
        for i in range(5):
            y = h * i / 4
            cr.move_to(0, y)
            cr.line_to(w, y)
        cr.stroke()
        pts = self.points
        if len(pts) < 2:
            return
        span = (self.high - self.low) or 1.0
        step = w / (len(pts) - 1)

        def y_of(v):
            return h - min(max((v - self.low) / span, 0.0), 1.0) * h

        rgba.parse(self.colour)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 0.12)
        cr.move_to(0, h)
        for i, v in enumerate(pts):
            cr.line_to(i * step, y_of(v))
        cr.line_to((len(pts) - 1) * step, h)
        cr.close_path()
        cr.fill()
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        cr.set_line_width(theme.dp(2))
        for i, v in enumerate(pts):
            if i:
                cr.line_to(i * step, y_of(v))
            else:
                cr.move_to(0, y_of(v))
        cr.stroke()
        if len(pts) < 30:
            for i, v in enumerate(pts):
                cr.arc(i * step, y_of(v), theme.SCALE * 2.5, 0, 6.2832)
                cr.fill()


class ArrangeDialog:
    """ReorderDialog (DashboardScreen.kt:722-805), an AlertDialog on the Sheet: "Arrange Home",
    the line of what to do, then one row per card with ▲ and ▼ moving it in a draft; the answers
    at the bottom right, "Cancel" (a TextButton in its own orange) and "Apply" (the orange Button
    with ink words), which saves the draft. Cancel, a tap outside or Escape keeps the order as it
    was."""

    def __init__(self, app, order: list, on_apply):
        self.draft = list(order)
        self.on_apply = on_apply
        self.sheet = Sheet(app, dashboard.ARRANGE_TITLE)
        self.dialog = self.sheet.dialog
        # Column(spacedBy(4.dp)) { the line; Spacer(8.dp); the rows }: 16 dp from the line to the
        # first row, 4 dp between rows
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        box.append(text(dashboard.ARRANGE_TEXT, "body-small", theme.TEXT_MUTED, wrap=True))
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.rows.set_margin_top(theme.dp(12))
        box.append(self.rows)
        self.sheet.body.append(box)
        cancel_button = self.sheet.button(dashboard.CANCEL, self.sheet.close)
        apply_button = self.sheet.button(dashboard.APPLY, self.apply, kind="filled")
        for button, word in ((cancel_button, dashboard.CANCEL), (apply_button, dashboard.APPLY)):
            name_widget(button, word)
        self.fill()
        self.sheet.present()

    def fill(self) -> None:
        clear(self.rows)
        last = len(self.draft) - 1
        for i, card in enumerate(self.draft):
            label = dashboard.CARD_LABELS.get(card, card)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            row.add_css_class("arrange-row")
            name = text(label, "body-medium")
            name.set_hexpand(True)
            name.set_valign(Gtk.Align.CENTER)
            row.append(name)
            for up, glyph, can in ((True, "▲", i > 0), (False, "▼", i < last)):
                # The glyph as a child, not the button's label: a labelled button is named by its
                # label ("▲"), and a screen reader must hear which card moves where.
                arrow = Gtk.Button()
                arrow.set_child(Gtk.Label(label=glyph))
                arrow.add_css_class("arrow-button")
                arrow.set_sensitive(can)
                name_widget(arrow, f"Move {label} {'up' if up else 'down'}")
                arrow.connect("clicked", lambda *_, k=i, u=up: self.move(k, u))
                row.append(arrow)
            self.rows.append(row)

    def move(self, index: int, up: bool) -> None:
        self.draft = dashboard.moved(self.draft, index, up)
        self.fill()

    def apply(self) -> None:
        self.sheet.close()
        self.on_apply(self.draft)


def sos_clock(sos_state: dict | None) -> str:
    """HH:MM of the SOS start, from the Bridge's RFC 3339 stamp (local time, as Android's clock())."""
    stamp = (sos_state or {}).get("started_at") or ""
    if isinstance(stamp, str) and len(stamp) >= 16:
        try:
            import datetime  # noqa: PLC0415

            at = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            return at.astimezone().strftime("%H:%M")
        except ValueError:
            return stamp[11:16]
    return "now"
