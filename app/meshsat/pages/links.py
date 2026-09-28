# SPDX-License-Identifier: GPL-3.0-or-later
"""Links (ui/screens/InterfacesScreen.kt): each way this phone sends and receives, its rules,
groups, backup links and health, in six tabs; a link switched off after a question, a link
that is off or not working reconnected on request."""
import time

from gi.repository import Gdk, Gtk

from .. import api, theme
from ..model import links as model
from ..model import rules as rules_model
from ..model import words
from ..screen import SubScreen
from ..widgets import Card, Tabs, clear, confirm, divider, dot, hscroll, name_widget, outlined_button, state_tag, text, tone_colour


def _rounded(cr, x: float, y: float, w: float, h: float, r: float) -> None:
    r = min(r, h / 2, w / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    cr.arc(x + r, y + r, r, 3.1416, 4.7124)
    cr.close_path()


class LinksScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Links", spacing=8)
        self.route = "interfaces"
        self.interfaces, self.scores, self.rules, self.groups, self.failover = [], [], [], [], []
        self.lanes = self.lanes_of(app.state)
        self._content_key = None
        self._quiet = False
        self.column.append(text(model.INTRO, "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.tabs = Tabs(list(model.TABS), self.select_tab, plain=True)
        self.column.append(hscroll(self.tabs))
        self.column.append(divider())
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(10))
        self.column.append(self.content)
        self.render()

    # Data
    def on_show(self) -> None:
        self.every(5, self.load_links)
        self.every(30, self.load_health)
        self.every(10, self.load_lists)

    def load_links(self) -> None:
        self.fetch("/api/interfaces", lambda a: self.got("interfaces", a))

    def load_health(self) -> None:
        self.fetch("/api/interfaces/health", lambda a: self.got("scores", a))

    def load_lists(self) -> None:
        self.fetch("/api/access-rules", lambda a: self.got("rules", a))
        self.fetch("/api/object-groups", lambda a: self.got("groups", a))
        self.fetch("/api/failover-groups", lambda a: self.got("failover", a))

    def got(self, field: str, answer: api.Answer) -> None:
        if answer.ok:
            setattr(self, field, answer.body if isinstance(answer.body, list) else [])
        elif answer.status >= 400:
            setattr(self, field, [])  # the Bridge has no such thing (no manager, no scorer): nothing to show
        else:
            return  # no answer at all: keep what is shown
        self.render()

    @staticmethod
    def lanes_of(s: api.State) -> dict:
        """Which lanes the app sees working, for a link the Bridge's device manager does not bind."""
        return {"mesh": s.mesh_connected(), "satellite": s.modem_connected(), "sms": s.sms_ready(), "hub": (s.hub or {}).get("link") == "connected"}

    def update(self, s: api.State) -> None:
        lanes = self.lanes_of(s)
        if lanes != self.lanes:
            self.lanes = lanes
            self.render()

    # Drawing
    def select_tab(self, name: str) -> None:
        self._content_key = None
        self.render()

    def render(self) -> None:
        badges = model.badges(self.interfaces, self.scores, self.lanes)
        for tab in model.TABS:
            self.tabs.set_badge(tab, badges.get(tab, 0))
        tab = self.tabs.selected
        now = time.time()
        data = {
            "Links": tuple((i.get("id"), i.get("enabled"), i.get("state"), i.get("error"), i.get("last_activity"), i.get("device_id"), i.get("device_port")) for i in self.interfaces) + tuple(sorted(self.lanes.items())),
            "Rules": tuple(rules_model.record_key(r) for r in self.rules),
            "Capabilities": tuple((i.get("id"), i.get("channel_type"), i.get("label")) for i in self.interfaces),
            "Groups": tuple((g.get("id"), g.get("label"), g.get("type"), str(g.get("members"))) for g in self.groups),
            "Backup links": tuple((g.get("id"), g.get("label"), g.get("mode"), len(g.get("members") or [])) for g in self.failover),
            "Health": tuple((s.get("interface_id"), s.get("score"), s.get("signal"), s.get("success_rate"), s.get("latency_ms"), s.get("cost_score"), s.get("available")) for s in self.scores),
        }[tab]
        key = (tab, int(now // 60), data)
        if key == self._content_key:
            return
        self._content_key = key
        clear(self.content)
        {"Links": self.links_tab, "Rules": self.rules_tab, "Capabilities": self.capabilities_tab, "Groups": self.groups_tab, "Backup links": self.failover_tab, "Health": self.health_tab}[tab](now)

    def subtitle(self, tab: str) -> None:
        if tab in model.SUBTITLES:
            label = text(model.SUBTITLES[tab], "body-small", theme.TEXT_MUTED, wrap=True)
            label.set_margin_bottom(theme.dp(4))
            self.content.append(label)

    def empty(self, tab: str) -> None:
        label = text(model.EMPTY[tab], "body-medium", theme.TEXT_MUTED, xalign=0.5, wrap=True)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_margin_top(theme.dp(48))
        label.set_margin_bottom(theme.dp(48))
        self.content.append(label)

    @staticmethod
    def title_row(lane: str, title: str, trailing: Gtk.Widget | None = None) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        row.append(dot(lane))
        label = text(title, "title-small", ellipsize=True)
        label.set_hexpand(True)
        row.append(label)
        if trailing is not None:
            row.append(trailing)
        return row

    # Links: live status with controls
    def links_tab(self, now: float) -> None:
        if not self.interfaces:
            self.empty("Links")
            return
        for iface in model.sorted_interfaces(self.interfaces):
            self.content.append(self.link_card(iface, now))

    def link_card(self, iface: dict, now: float) -> Card:
        id_ = iface.get("id", "")
        state = model.state_of(iface, self.lanes)
        card = Card(spacing=4)
        if state == "disabled":
            card.add_css_class("dimmed")
        switch = Gtk.Switch(active=state != "disabled")
        switch.set_valign(Gtk.Align.CENTER)
        name_widget(switch, model.switch_name(id_))
        switch.connect("state-set", lambda sw, on, i=id_: self.switch_changed(sw, on, i))
        card.append(self.title_row(words.channel_lane(id_), words.channel(id_), switch))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        row.append(state_tag(model.state_text(state), model.state_tone(state)))
        if iface.get("error"):
            error = text(iface["error"], "body-small", theme.RED, wrap=True, ellipsize=True)
            error.set_lines(2)
            error.set_hexpand(True)
            error.set_valign(Gtk.Align.CENTER)
            row.append(error)
        card.append(row)
        times = model.times_line(iface, now)
        attempts = model.reconnect_line(iface)
        if times:
            card.append(text(times, "body-small", theme.TEXT_MUTED, wrap=True))
        if attempts:
            card.append(text(attempts, "body-small", theme.AMBER))
        if model.can_reconnect(state) and model.bind_target(iface):
            button = outlined_button(model.RECONNECT, lambda i=iface: self.reconnect(i))
            button.set_halign(Gtk.Align.START)
            button.set_margin_top(theme.dp(4))
            card.append(button)
        return card

    def switch_changed(self, switch: Gtk.Switch, on: bool, id_: str) -> bool:
        if self._quiet:
            return False
        if on:
            self.call(f"/api/interfaces/{id_}/enable", lambda a: self.switched(a, model.toast_on(id_)))
            return False
        question = model.switch_off_dialog(id_)

        def keep() -> None:
            self._quiet = True
            try:
                switch.set_active(True)
            finally:
                self._quiet = False

        confirm(self.app, question["title"], question["body"], question["ok"], lambda: self.call(f"/api/interfaces/{id_}/disable", lambda a: self.switched(a, model.toast_off(id_))),
                cancel=question["cancel"], danger=True, on_cancel=keep)
        return False

    def switched(self, answer: api.Answer, toast: str) -> None:
        self.app.toast(toast if answer.ok else f"That did not work: {answer.error}")
        self._content_key = None
        self.load_links()

    def reconnect(self, iface: dict) -> None:
        id_ = iface.get("id", "")
        self.app.toast(model.toast_reconnect(id_))
        self.call(f"/api/interfaces/{id_}/bind", lambda a: None if a.ok else self.app.toast(f"That did not work: {a.error}"), body={"device_id": model.bind_target(iface)})

    # Rules: the routing rules of every link (read-only)
    def rules_tab(self, now: float) -> None:
        self.subtitle("Rules")
        if not self.rules:
            self.empty("Rules")
            return
        for rule in self.rules:
            card = Card(spacing=2)
            if not rule.get("enabled"):
                card.add_css_class("dimmed")
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            name = text(rules_model.name_of(rule), "title-small", wrap=True, ellipsize=True)
            name.set_lines(2)
            name.set_hexpand(True)
            top.append(name)
            top.append(state_tag("On" if rule.get("enabled") else "Off", "green" if rule.get("enabled") else "muted"))
            card.append(top)
            card.append(text(model.rule_line(rule), "body-medium", theme.TEXT_SECONDARY, wrap=True))
            card.append(text(rules_model.matches_text(rule), "body-small", theme.TEXT_MUTED))
            self.content.append(card)

    # Capabilities: what each link can carry (read-only)
    def capabilities_tab(self, now: float) -> None:
        self.subtitle("Capabilities")
        if not self.interfaces:
            self.empty("Capabilities")
            return
        for iface in model.sorted_interfaces(self.interfaces):
            id_ = iface.get("id", "")
            card = Card(spacing=4)
            card.append(self.title_row(words.channel_lane(id_), words.channel(id_), text(model.channel_label(iface), "body-small", theme.TEXT_MUTED)))
            for label, value in model.capability_rows(iface.get("channel_type", "")):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
                key = text(label, "body-small", theme.TEXT_MUTED)
                key.set_hexpand(True)
                row.append(key)
                row.append(text(value, "body-small", theme.TEXT_PRIMARY if value == "Yes" else theme.TEXT_SECONDARY, xalign=1.0, mono=value[:1].isdigit()))
                card.append(row)
            retries = model.retries_text(iface.get("channel_type", ""))
            if retries:
                line = text(retries, "body-small", theme.TEXT_SECONDARY, wrap=True)
                line.set_margin_top(theme.dp(2))
                card.append(line)
            self.content.append(card)

    # Groups and backup links (read-only)
    def _group_card(self, title: str, count: str, detail: str) -> Card:
        card = Card(spacing=2)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        name = text(title, "title-small", ellipsize=True)
        name.set_hexpand(True)
        top.append(name)
        top.append(text(count, "body-small", theme.TEXT_SECONDARY))
        card.append(top)
        card.append(text(detail, "body-small", theme.TEXT_MUTED))
        return card

    def groups_tab(self, now: float) -> None:
        self.subtitle("Groups")
        if not self.groups:
            self.empty("Groups")
            return
        for group in self.groups:
            self.content.append(self._group_card(model.group_title(group), words.count(model.member_count(group.get("members")), "member"), model.group_type_label(group.get("type", ""))))

    def failover_tab(self, now: float) -> None:
        self.subtitle("Backup links")
        if not self.failover:
            self.empty("Backup links")
            return
        for group in self.failover:
            self.content.append(self._group_card(model.group_title(group), words.count(len(group.get("members") or []), "link"), model.failover_mode(group.get("mode", ""))))

    # Health: one score per link
    def health_tab(self, now: float) -> None:
        self.subtitle("Health")
        if not self.scores:
            self.empty("Health")
            return
        for hs in self.scores:
            id_ = hs.get("interface_id", "")
            score = int(hs.get("score") or 0)
            tone = model.score_tone(score)
            card = Card(spacing=10)
            trailing = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            if not hs.get("available"):
                trailing.append(state_tag(model.NOT_CONNECTED, "muted"))
            figure = text(str(score), "title-medium", tone_colour(tone), mono=True)
            figure.add_css_class("state-tag")
            figure.add_css_class("score-tag")
            figure.add_css_class(f"tint-{tone}")
            trailing.append(figure)
            card.append(self.title_row(words.channel_lane(id_), words.channel(id_), trailing))
            bar = Gtk.DrawingArea()
            bar.set_content_height(theme.dp(6))
            bar.set_hexpand(True)
            bar.set_draw_func(self._draw_bar, (score, tone))
            card.append(bar)
            parts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True)
            for label, value in model.score_parts(hs):
                column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                column.append(text(str(value), "title-small", theme.TEXT_PRIMARY, xalign=0.5, mono=True))
                column.append(text(label, "body-small", theme.TEXT_MUTED, xalign=0.5))
                parts.append(column)
            card.append(parts)
            self.content.append(card)

    @staticmethod
    def _draw_bar(area, cr, width, height, data) -> None:
        score, tone = data
        back = Gdk.RGBA()
        back.parse(theme.BORDER)
        cr.set_source_rgba(back.red, back.green, back.blue, 1.0)
        _rounded(cr, 0, 0, width, height, height / 2)
        cr.fill()
        fill = Gdk.RGBA()
        fill.parse(tone_colour(tone))
        cr.set_source_rgba(fill.red, fill.green, fill.blue, 1.0)
        _rounded(cr, 0, 0, width * min(max(score, 0), 100) / 100.0, height, height / 2)
        cr.fill()
