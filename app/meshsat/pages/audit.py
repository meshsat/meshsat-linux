# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit log (ui/screens/AuditScreen.kt): the Bridge's signed, hash-chained record of what the
gateway did, newest first, filtered by link; "Check the log" asks the Bridge to walk the chain;
"Save a copy" writes the whole log as tab-separated text where the person chooses."""
import time
import urllib.parse

from gi.repository import Gtk

from .. import api, files, theme
from ..layout import empty_text, flow_row
from ..model import audit as model
from ..model import words
from ..screen import SubScreen
from ..widgets import Card, clear, dot, filled_button, name_widget, outlined_button, text, tone_colour


class AuditScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Audit log", spacing=8)
        self.route = "audit"
        self.entries, self.total, self.signer = [], None, ""
        self.limit = model.PAGE
        self.link = None
        self.links = list(model.FALLBACK_LINKS)
        self.rule_names = {}
        self.checking = self.saving = False
        self.check = None
        self._key = None
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.count = text("", "body-medium", theme.TEXT_SECONDARY)
        self.count.set_hexpand(True)
        top.append(self.count)
        self.key_button = Gtk.Button()
        self.key_button.add_css_class("flat")
        key_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        key_row.append(text("Signing key ", "body-small", theme.TEXT_MUTED))
        self.key_text = text("", "body-small", mono=True)
        key_row.append(self.key_text)
        self.key_button.set_child(key_row)
        self.key_button.set_size_request(-1, theme.dp(48))
        self.key_button.connect("clicked", lambda *_: self.copy_key())
        self.key_button.set_visible(False)
        top.append(self.key_button)
        self.column.append(top)
        # AuditScreen.kt:290: Spacer(4.dp), FlowRow(spacedBy(6.dp)) of FilterChips, Spacer(8.dp):
        # every link on screen, the chips wrapping onto more lines. Material's 48 dp touch height
        # round a 32 dp chip adds 8 dp above the first line and 8 dp under the last: above, 4 + 8
        # less the column's own 8 dp spacing; under, those 8.
        self.chip_row = flow_row(6, 16)
        self.chip_row.set_margin_top(theme.dp(4))
        self.chip_row.set_margin_bottom(theme.dp(8))
        self.column.append(self.chip_row)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.check_button = outlined_button(model.CHECK, self.check_log)
        self.check_button.set_visible(False)
        self.save_button = outlined_button(model.SAVE, self.save_copy)
        actions.append(self.check_button)
        actions.append(self.save_button)
        self.column.append(actions)
        self.check_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        self.column.append(self.check_box)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(6))
        self.list.set_margin_top(theme.dp(8))
        self.column.append(self.list)
        self._chips()

    # Data
    def on_show(self) -> None:
        self.fetch("/api/audit/signer", self.got_signer)
        self.fetch("/api/interfaces", self.got_links)
        self.fetch("/api/access-rules", self.got_rules)
        self.every(10, self.load)

    def load(self) -> None:
        query = {"limit": str(min(self.limit, 1000))}
        if self.link:
            query["interface_id"] = self.link
        self.fetch("/api/audit?" + urllib.parse.urlencode(query), self.got_entries)
        self.fetch("/api/audit/count", self.got_count)

    def got_entries(self, answer: api.Answer) -> None:
        if answer.ok:
            self.entries = answer.body if isinstance(answer.body, list) else []
            self.render()

    def got_count(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.total = int(answer.body.get("count") or 0)
        elif answer.status == 404:
            self.total = None  # a Bridge before the count: what is loaded is what is shown
        self.render()

    def got_signer(self, answer: api.Answer) -> None:
        self.signer = (answer.body or {}).get("signer_id", "") if answer.ok else ""
        self.key_text.set_text(model.signer_short(self.signer))
        self.key_button.set_visible(bool(self.signer))
        self.check_button.set_visible(bool(self.signer))
        name_widget(self.key_button, "Signing key " + model.signer_short(self.signer))

    def got_links(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.links = model.links_offered(answer.body)
            self._chips()

    def got_rules(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.rule_names = {r.get("id"): r.get("name", "") for r in answer.body}
            self._key = None
            self.render()

    # Filter
    def _chips(self) -> None:
        clear(self.chip_row)
        for link in [None] + self.links:
            chip = Gtk.Button()
            chip.add_css_class("chip")
            if self.link == link:
                chip.add_css_class("selected")
            name = "All links" if link is None else words.channel(link)
            name_widget(chip, name)
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
            if link is not None:
                inner.append(dot(words.channel_lane(link), 8))
            inner.append(text(name, "label-large"))
            chip.set_child(inner)
            chip.set_halign(Gtk.Align.START)  # its own width, also in a Gtk.FlowBox's column
            chip.connect("clicked", lambda _b, l=link: self.set_link(l))
            self.chip_row.append(chip)

    def set_link(self, link) -> None:
        self.link = None if link is None or self.link == link else link
        self.limit = model.PAGE
        self._chips()
        self._key = None
        self.load()

    # Actions
    def copy_key(self) -> None:
        if self.signer:
            self.app.window.get_clipboard().set(self.signer)
            self.app.toast(model.KEY_COPIED)

    def check_log(self) -> None:
        self.checking = True
        self.check_button.set_label(model.CHECKING)
        self.check_button.set_sensitive(False)

        def verified(answer: api.Answer) -> None:
            if not answer.ok:
                self.checking = False
                self.check_button.set_label(model.CHECK)
                self.check_button.set_sensitive(True)
                self.app.toast(f"That did not work: {answer.error}")
                return
            result = answer.body or {}
            if int(result.get("broken_at", -1)) >= 0:
                # The first changed entry by its number: the window the Bridge checked, oldest first.
                self.fetch(f"/api/audit?limit={model.VERIFY_WINDOW}", lambda a: self.checked(result, list(reversed(a.body)) if a.ok and isinstance(a.body, list) else None))
            else:
                self.checked(result, None)

        self.call(f"/api/audit/verify?limit={model.VERIFY_WINDOW}", verified, method="GET", timeout=30)

    def checked(self, result: dict, oldest_first) -> None:
        self.checking = False
        self.check_button.set_label(model.CHECK)
        self.check_button.set_sensitive(True)
        self.check = model.check_words(result, oldest_first)
        clear(self.check_box)
        for line, style, tone in self.check:
            self.check_box.append(text(line, style, tone_colour(tone), wrap=True))

    def save_copy(self) -> None:
        self.saving = True
        self.save_button.set_label(model.SAVING)
        self.save_button.set_sensitive(False)
        collected = []

        def page(answer: api.Answer) -> None:
            if not answer.ok or not isinstance(answer.body, list):
                self.saved(False)
                return
            collected.extend(answer.body)
            if len(answer.body) == 1000 and len(collected) < model.EXPORT_LIMIT and answer.body:
                oldest = answer.body[-1].get("id")
                self.call(f"/api/audit?limit=1000&before={oldest}", page, method="GET", timeout=30)
                return
            files.save(self.app, model.export_name(), model.export_text(collected, self.signer or None), self.saved)

        self.call("/api/audit?limit=1000", page, method="GET", timeout=30)

    def saved(self, ok) -> None:
        self.saving = False
        self.save_button.set_label(model.SAVE)
        self.save_button.set_sensitive(self.shown_total() > 0)
        if ok is None:
            return
        self.app.toast(model.SAVED if ok else model.NOT_SAVED)

    def older(self) -> None:
        self.limit += model.PAGE
        self.load()

    # Drawing
    def shown_total(self) -> int:
        return self.total if self.total is not None else len(self.entries)

    def render(self) -> None:
        total = self.shown_total()
        self.count.set_text(model.count_text(total))
        if not self.saving:
            self.save_button.set_sensitive(total > 0)
        now = time.time()
        key = (self.link, self.limit, int(now // 60), tuple((e.get("id"), e.get("hash")) for e in self.entries), tuple(sorted(self.rule_names.items())))
        if key == self._key:
            return
        self._key = key
        clear(self.list)
        if not self.entries:
            # Box(weight(1f), Alignment.Center): in the middle of the room under the buttons
            self.list.append(empty_text(model.empty_text(self.link is not None)))
            return
        for entry in self.entries:
            self.list.append(self.card(entry, now))
        if len(self.entries) >= self.limit and self.limit < 1000:
            more = filled_button(model.OLDER, self.older)
            more.add_css_class("tonal-surface")
            more.set_size_request(-1, theme.dp(48))
            self.list.append(more)

    def card(self, entry: dict, now: float) -> Card:
        card = Card(spacing=0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(10))
        marker = Gtk.Box()
        marker.add_css_class("lane-dot")
        marker.set_size_request(theme.dp(10), theme.dp(10))
        marker.set_valign(Gtk.Align.START)
        marker.set_margin_top(theme.dp(5))
        from ..widgets import paint  # noqa: PLC0415

        paint(marker, tone_colour(model.event_tone(entry.get("event_type", ""))), background=True)
        row.append(marker)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        title = text(model.event_label(entry.get("event_type", "")), "title-small", ellipsize=True)
        title.set_hexpand(True)
        head.append(title)
        head.append(text(model.time_text(entry, now), "body-small", theme.TEXT_MUTED, mono=True))
        texts.append(head)
        where = model.where_line(entry)
        if where:
            iface = entry.get("interface_id") or ""
            texts.append(text(where, "body-small", theme.lane_colour(words.channel_lane(iface)) if iface else theme.TEXT_SECONDARY))
        if (entry.get("detail") or "").strip():
            detail = text(entry["detail"], "body-small", theme.TEXT_SECONDARY, wrap=True, ellipsize=True)
            detail.set_lines(2)
            texts.append(detail)
        refs = model.refs_line(entry, self.rule_names)
        if refs:
            texts.append(text(refs, "body-small", theme.TEXT_MUTED))
        row.append(texts)
        card.append(row)
        return card
