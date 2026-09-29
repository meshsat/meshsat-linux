# SPDX-License-Identifier: GPL-3.0-or-later
"""The message queue (ui/screens/DeliveryScreen.kt): every message on its way out, by link, with
what happened to it in plain words; the counts by state as filters, a chip per link, a card per
message, the details dialog, and a retry or cancel that is always confirmed. Routing rules >
Deliveries and > Queue are drawn with the same parts."""
import time

from gi.repository import Gtk

from .. import api, theme
from ..layout import empty_text
from ..model import deliveries as model
from ..model import words
from ..screen import SubScreen
from ..widgets import Card, Sheet, clear, confirm, dot, fact_row, hscroll, name_widget, paint, text, text_button, tone_colour


class DeliveryCard(Gtk.Box):
    """One message on its way: the link, its state, the text, when, and what went wrong. The
    card is a button (a tap opens the details); `on_cancel` and `on_retry` add the text buttons
    of the Queue tab for a message that can be cancelled or retried."""

    def __init__(self, d: dict, now: float, on_open, on_cancel=None, on_retry=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("card")
        button = Gtk.Button()
        button.add_css_class("flat")
        button.add_css_class("card-tap")
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        top.append(dot(words.channel_lane(model.channel(d))))
        title = text(model.link(d), "title-small", ellipsize=True)
        title.set_hexpand(True)
        top.append(title)
        top.append(text(model.state_text(d), "label-large", tone_colour(model.state_tone(d))))
        body.append(top)
        preview = d.get("text_preview") or ""
        if preview.strip():
            lines = text(preview, "body-medium", theme.TEXT_SECONDARY, wrap=True, ellipsize=True)
            lines.set_lines(2)
            body.append(lines)
        body.append(text(model.card_meta(d, now), "body-small", theme.TEXT_MUTED, wrap=True))
        problem, tone = model.problem_line(d)
        if problem:
            line = text(problem, "body-small", tone_colour(tone), wrap=True, ellipsize=True)
            line.set_lines(2)
            body.append(line)
        button.set_child(body)
        button.connect("clicked", lambda *_: on_open(d))
        self.append(button)
        show_cancel = on_cancel is not None and model.can_cancel(d)
        show_retry = on_retry is not None and model.can_retry(d)
        if show_cancel or show_retry:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            row.set_halign(Gtk.Align.END)
            row.set_margin_end(theme.dp(4))
            row.set_margin_bottom(theme.dp(4))
            if show_cancel:
                cancel = text_button("Cancel", lambda: on_cancel(d))
                paint(cancel.get_child(), theme.RED)
                row.append(cancel)
            if show_retry:
                row.append(text_button("Retry", lambda: on_retry(d)))
            self.append(row)


class Ledger(Gtk.Box):
    """DeliveryLedger: the counts by state (tapping one filters by it), one chip per link (the
    row slides when there are more links than fit), and one card per message."""

    def __init__(self, app, on_open, on_cancel=None, on_retry=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.app = app
        self.on_open, self.on_cancel, self.on_retry = on_open, on_cancel, on_retry
        self.group = None
        self.channel = None
        self.deliveries = []
        self._list_key = None
        self._chips_key = None
        counts = Card(padded=False, spacing=0)
        counts.add_css_class("ledger-counts")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True)
        self.groups = {}
        for key, _statuses in model.GROUPS:
            tone = words.delivery_tone(key)
            button = Gtk.Button()
            button.add_css_class("flat")
            button.add_css_class("ledger-group")
            button.add_css_class(f"tint-{tone}")
            name_widget(button, model.group_label(key))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            box.set_valign(Gtk.Align.CENTER)
            count = text("0", "title-medium", tone_colour(tone), xalign=0.5, mono=True)
            label = text(model.group_label(key), "body-small", theme.TEXT_MUTED, xalign=0.5, ellipsize=True)
            box.append(count)
            box.append(label)
            button.set_child(box)
            button.connect("clicked", lambda _b, k=key: self.set_group(k))
            self.groups[key] = (button, count, label)
            row.append(button)
        counts.append(row)
        self.append(counts)
        self.chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.chips = {}
        self.chips_scroll = hscroll(self.chip_row)
        self.chips_scroll.set_visible(False)
        self.append(self.chips_scroll)
        # Box(weight(1f), Alignment.Center): the empty text in the middle of the room under the
        # counts and the chips
        self.empty = empty_text()
        self.append(self.empty)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(6))
        self.append(self.list)

    def set_group(self, key: str) -> None:
        self.group = None if self.group == key else key
        self.render()

    def set_channel(self, channel: str | None) -> None:
        self.channel = None if channel is None or self.channel == channel else channel
        self.render()

    def set(self, deliveries: list) -> None:
        self.deliveries = list(deliveries or [])
        self.render()

    def _chip(self, channel: str | None) -> Gtk.Button:
        chip = Gtk.Button()
        chip.add_css_class("chip")
        name = model.ALL_LINKS if channel is None else words.channel(channel)
        name_widget(chip, name)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
        if channel is not None:
            inner.append(dot(words.channel_lane(channel), 8))
        inner.append(text(name, "label-large"))
        chip.set_child(inner)
        chip.connect("clicked", lambda *_: self.set_channel(channel))
        return chip

    def render(self) -> None:
        now = time.time()
        counts = model.group_counts(self.deliveries)
        for key, (button, count, label) in self.groups.items():
            count.set_text(str(counts.get(key, 0)))
            selected = self.group == key
            (button.add_css_class if selected else button.remove_css_class)("selected")
            paint(label, tone_colour(words.delivery_tone(key)) if selected else theme.TEXT_MUTED)
        channels = model.channels(self.deliveries)
        if tuple(channels) != self._chips_key:
            self._chips_key = tuple(channels)
            clear(self.chip_row)
            self.chips = {}
            if channels:
                for channel in [None] + channels:
                    chip = self._chip(channel)
                    self.chips[channel] = chip
                    self.chip_row.append(chip)
            if self.channel not in channels:
                self.channel = None
        for channel, chip in self.chips.items():
            (chip.add_css_class if self.channel == channel else chip.remove_css_class)("selected")
        self.chips_scroll.set_visible(bool(channels))
        items = model.filtered(self.deliveries, self.group, self.channel)
        key = (self.group, self.channel, bool(self.deliveries), int(now // 60), tuple(model.record_key(d) for d in items))
        if key == self._list_key:
            return
        self._list_key = key
        clear(self.list)
        self.empty.set_text(model.empty_text(self.deliveries))
        self.empty.set_visible(not items)
        self.list.set_visible(bool(items))  # an empty list takes no spacing under the empty text
        for d in items:
            self.list.append(DeliveryCard(d, now, self.on_open, self.on_cancel, self.on_retry))


def open_details(app, screen, d: dict, on_changed) -> Sheet:
    """DeliveryDetailsDialog: everything about one message; the raw fields experts want sit
    behind "Show details"; Retry and Cancel message when the message allows them."""
    sheet = Sheet(app, model.details_title(d), width=360)
    now = time.time()
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(6))
    for label, value, tone in model.facts(d, now):
        body.append(fact_row(label, value, tone_colour(tone) if tone else None))
    preview = d.get("text_preview") or ""
    if preview.strip():
        box = Gtk.Box()
        box.add_css_class("tonal-box")
        box.set_margin_top(theme.dp(4))
        words_label = text(preview, "body-medium", wrap=True)
        words_label.set_hexpand(True)
        box.append(words_label)
        body.append(box)
    hidden = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(6))
    hidden.set_visible(False)
    for label, value in model.details(d):
        hidden.append(fact_row(label, value, mono=True))
    toggle = text_button("Show details")
    paint(toggle.get_child(), theme.TEXT_SECONDARY)

    def flip() -> None:
        shown = not hidden.get_visible()
        hidden.set_visible(shown)
        toggle.set_label("Hide details" if shown else "Show details")
        paint(toggle.get_child(), theme.TEXT_SECONDARY)

    toggle.connect("clicked", lambda *_: flip())
    body.append(toggle)
    body.append(hidden)
    scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=theme.dp(480), hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(body)
    sheet.body.append(scroll)
    if model.can_retry(d):
        sheet.button("Retry", lambda: (sheet.close(), ask(app, screen, d, True, on_changed)))
    if model.can_cancel(d):
        cancel = sheet.button("Cancel message", lambda: (sheet.close(), ask(app, screen, d, False, on_changed)))
        paint(cancel.get_child(), theme.RED)
    close = sheet.button("Close", sheet.close)
    paint(close.get_child(), theme.TEXT_SECONDARY)
    sheet.present()
    return sheet


def ask(app, screen, d: dict, retry: bool, on_done) -> None:
    """Retry (True) or cancel (False) one delivery, after the user has confirmed."""
    question = model.request_dialog(d, retry)
    confirm(app, question["title"], question["body"], question["ok"], lambda: apply(app, screen, d, retry, on_done), cancel=question["cancel"], danger=not retry)


def apply(app, screen, d: dict, retry: bool, on_done) -> None:
    """Carry out a confirmed request at the Bridge, and tell the user what happened."""
    path = f"/api/deliveries/{d.get('id')}/{'retry' if retry else 'cancel'}"

    def done(answer: api.Answer) -> None:
        if answer.ok:
            app.toast(model.applied_text(d, retry))
        elif not retry and answer.status == 500:
            # The Bridge refuses to cancel what is no longer queued or waiting for a retry.
            app.toast(model.applied_text(d, False, changed=False))
        else:
            app.toast(model.failed_text(answer.error))
        on_done()

    screen.call(path, done)


class DeliveryScreen(SubScreen):
    """Setup > Advanced > Message queue."""

    def __init__(self, app):
        super().__init__(app, "Message queue", spacing=8)
        self.route = "deliveries"
        self.ledger = Ledger(app, self.open)
        self.column.append(self.ledger)

    def on_show(self) -> None:
        self.every(4, self.load)

    def load(self) -> None:
        self.fetch("/api/deliveries?limit=200", self.loaded)

    def loaded(self, answer: api.Answer) -> None:
        if answer.ok:
            self.ledger.set(answer.body if isinstance(answer.body, list) else [])

    def open(self, d: dict) -> None:
        open_details(self.app, self, d, self.load)
