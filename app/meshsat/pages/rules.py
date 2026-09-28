# SPDX-License-Identifier: GPL-3.0-or-later
"""Routing rules (ui/screens/RulesScreen.kt): which messages pass from one link to another, in
five tabs (the rules from the mesh, into it and between the other links, the deliveries, the
queue), each rule a card with its switch, its route and its filters; an editor for a new or an
existing rule; a delete that says what it changes first."""
import time

from gi.repository import GLib, Gtk

from .. import api, theme
from ..model import deliveries as deliveries_model
from ..model import rules as model
from ..model import words
from ..screen import SubScreen
from ..widgets import Card, Fab, Field, PickerField, Sheet, SwitchRow, Tabs, clear, confirm, divider, hscroll, icon_button, name_widget, paint, text
from .deliveries import DeliveryCard, Ledger, ask, open_details


class RulesScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Routing rules", spacing=8)
        self.route = "rules"
        self.rules, self.deliveries, self.interfaces = [], [], []
        self._content_key = None
        self._quiet = False
        self.ledger = None
        # The add button floats over the list: the column's scroller goes into an overlay.
        scroll = self.get_last_child()
        self.remove(scroll)
        overlay = Gtk.Overlay()
        overlay.set_vexpand(True)
        overlay.set_child(scroll)
        self.fab = Fab("outlined-add", model.ADD, self.add_rule)
        overlay.add_overlay(self.fab)
        self.append(overlay)
        self.column.append(text(model.INTRO, "body-medium", theme.TEXT_SECONDARY, wrap=True))
        self.tabs = Tabs(list(model.TABS), self.select_tab, plain=True)
        self.column.append(hscroll(self.tabs))
        self.column.append(divider())
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.column.append(self.content)
        self.render()

    # Data
    def on_show(self) -> None:
        self.every(5, self.load)
        self.every(30, self.load_links)

    def load(self) -> None:
        self.fetch("/api/access-rules", lambda a: self.got("rules", a))
        self.fetch("/api/deliveries?limit=200", lambda a: self.got("deliveries", a))

    def load_links(self) -> None:
        self.fetch("/api/interfaces", lambda a: self.got("interfaces", a))

    def got(self, field: str, answer: api.Answer) -> None:
        if answer.ok:
            setattr(self, field, answer.body if isinstance(answer.body, list) else [])
        elif answer.status >= 400:
            setattr(self, field, [])
        else:
            return
        self.render()

    # Drawing
    def select_tab(self, name: str) -> None:
        self._content_key = None
        self.render()

    def render(self) -> None:
        badges = model.badges(self.rules, deliveries_model.queue_count(self.deliveries))
        for tab in model.TABS:
            self.tabs.set_badge(tab, badges.get(tab, 0))
        tab = self.tabs.selected
        self.fab.set_visible(tab in model.RULE_TABS)
        now = time.time()
        if tab == "Deliveries":
            if self._content_key != ("Deliveries",):
                self._content_key = ("Deliveries",)
                clear(self.content)
                self.ledger = Ledger(self.app, self.open_details)
                self.content.append(self.ledger)
            self.ledger.set(self.deliveries)
            return
        if tab == "Queue":
            key = ("Queue", int(now // 60), tuple(deliveries_model.record_key(d) for d in self.deliveries))
        else:
            key = (tab, int(now // 60), tuple(model.record_key(r) for r in model.by_tab(self.rules)[tab]))
        if key == self._content_key:
            return
        self._content_key = key
        clear(self.content)
        if tab == "Queue":
            self.queue_tab(now)
        else:
            self.rules_tab(tab, now)

    def rules_tab(self, tab: str, now: float) -> None:
        subtitle = text(model.SUBTITLES[tab], "body-small", theme.TEXT_MUTED, wrap=True)
        subtitle.set_margin_bottom(theme.dp(4))
        self.content.append(subtitle)
        rules = model.by_tab(self.rules)[tab]
        if not rules:
            empty = text(model.EMPTY[tab], "body-medium", theme.TEXT_MUTED, xalign=0.5, wrap=True)
            empty.set_justify(Gtk.Justification.CENTER)
            empty.set_margin_top(theme.dp(48))
            empty.set_margin_bottom(theme.dp(48))
            self.content.append(empty)
            return
        for rule in rules:
            self.content.append(self.rule_card(rule, now))
        room = Gtk.Box()  # room under the last card for the add button
        room.set_size_request(-1, theme.dp(72))
        self.content.append(room)

    def rule_card(self, rule: dict, now: float) -> Card:
        name = model.name_of(rule)
        card = Card(padded=False, spacing=2)
        card.add_css_class("card-tight")
        if not rule.get("enabled"):
            card.add_css_class("dimmed")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        title = text(name, "title-small", wrap=True, ellipsize=True)
        title.set_lines(2)
        title.set_hexpand(True)
        top.append(title)
        switch = Gtk.Switch(active=bool(rule.get("enabled")))
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_margin_start(theme.dp(8))
        switch.set_margin_end(theme.dp(8))
        name_widget(switch, model.switch_name(rule))
        switch.connect("state-set", lambda sw, on, r=rule: self.toggle(sw, on, r))
        top.append(switch)
        card.append(top)
        route = Gtk.Label(xalign=0.0)
        route.set_markup(self.route_markup(rule))
        route.add_css_class("body-medium")
        route.set_wrap(True)
        route.set_margin_end(theme.dp(8))
        paint(route, theme.TEXT_SECONDARY)
        card.append(route)
        meta = text(model.meta_line(rule, now), "body-small", theme.TEXT_MUTED, wrap=True)
        meta.set_margin_end(theme.dp(8))
        card.append(meta)
        filters = model.filter_summary(rule)
        if filters:
            summary = text(filters, "body-small", theme.TEXT_SECONDARY, wrap=True)
            summary.set_margin_end(theme.dp(8))
            card.append(summary)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        actions.set_halign(Gtk.Align.END)
        actions.append(icon_button("outlined-edit", lambda r=rule: self.edit_rule(r), 24, theme.TEXT_SECONDARY, tooltip=f"Edit rule {name}"))
        actions.append(icon_button("outlined-delete", lambda r=rule: self.delete_asked(r), 24, theme.TEXT_SECONDARY, tooltip=f"Delete rule {name}"))
        card.append(actions)
        return card

    @staticmethod
    def route_markup(rule: dict) -> str:
        """"Forward: Mesh to Satellite", the action bold, each link in its colour."""
        out = []
        for part, lane in model.route_parts(rule):
            escaped = GLib.markup_escape_text(part)
            if lane == "bold":
                out.append(f'<span weight="600" foreground="{theme.TEXT_PRIMARY}">{escaped}</span>')
            elif lane:
                out.append(f'<span foreground="{theme.lane_colour(lane)}">{escaped}</span>')
            else:
                out.append(escaped)
        return "".join(out)

    # The queue tab
    def queue_tab(self, now: float) -> None:
        intro = text(deliveries_model.QUEUE_INTRO, "body-small", theme.TEXT_MUTED, wrap=True)
        intro.set_margin_bottom(theme.dp(4))
        self.content.append(intro)
        waiting, gave_up = deliveries_model.queue_sections(self.deliveries)
        if not waiting and not gave_up:
            empty = text(deliveries_model.QUEUE_EMPTY, "body-medium", theme.TEXT_MUTED, xalign=0.5, wrap=True)
            empty.set_justify(Gtk.Justification.CENTER)
            empty.set_margin_top(theme.dp(48))
            empty.set_margin_bottom(theme.dp(48))
            self.content.append(empty)
            return
        for is_waiting, items in ((True, waiting), (False, gave_up)):
            if not items:
                continue
            title = text(deliveries_model.section_title(is_waiting, len(items)), "title-small", theme.TEXT_SECONDARY)
            title.set_margin_top(theme.dp(8))
            title.set_margin_bottom(theme.dp(2))
            self.content.append(title)
            for d in items:
                self.content.append(DeliveryCard(d, now, self.open_details, on_cancel=self.cancel_asked if is_waiting else None, on_retry=self.retry_asked if not is_waiting else None))

    def open_details(self, d: dict) -> None:
        open_details(self.app, self, d, self.load)

    def cancel_asked(self, d: dict) -> None:
        ask(self.app, self, d, False, self.load)

    def retry_asked(self, d: dict) -> None:
        ask(self.app, self, d, True, self.load)

    # Writes
    def toggle(self, switch: Gtk.Switch, on: bool, rule: dict) -> bool:
        if self._quiet:
            return False
        self.call(f"/api/access-rules/{rule.get('id')}/{'enable' if on else 'disable'}", self.written)
        return False

    def written(self, answer: api.Answer, toast: str | None = None) -> None:
        if not answer.ok:
            self.app.toast(f"That did not work: {answer.error}")
        elif toast:
            self.app.toast(toast)
        self._content_key = None
        self.load()

    def add_rule(self) -> None:
        RuleEditor(self, None, self.tabs.selected)

    def edit_rule(self, rule: dict) -> None:
        RuleEditor(self, rule, self.tabs.selected)

    def saved(self, rule: dict, was_new: bool) -> None:
        self.app.toast(model.TOAST_ADDED if was_new else model.TOAST_SAVED)
        # Show the tab the rule is listed under, so it never seems to disappear.
        self.tabs.select(model.tab_of(rule))
        self._content_key = None
        self.load()

    def delete_asked(self, rule: dict) -> None:
        question = model.delete_dialog(rule)
        confirm(self.app, question["title"], question["body"], question["ok"], lambda: self.call(f"/api/access-rules/{rule.get('id')}", lambda a: self.written(a, model.TOAST_DELETED), method="DELETE"),
                cancel=question["cancel"], danger=True)


class RuleEditor:
    """AddEditRuleDialog: the editor reads the rule once and from then on holds what the user
    types; saving writes the rule itself with the editor's fields over it."""

    def __init__(self, screen: RulesScreen, rule: dict | None, tab: str):
        self.screen, self.app, self.rule = screen, screen.app, rule
        self.fields = model.editor_fields(rule, tab)
        self.tried = False
        self.sheet = Sheet(self.app, "Edit rule" if rule else "New rule", width=360)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.name = Field("Rule name")
        body.append(self.name)
        links = model.available_links(screen.interfaces, keep=self.fields["interface_id"])
        self.source = PickerField(self.app, model.interface_label(rule), [(id_, words.channel(id_), "") for id_ in links], self.fields["interface_id"], lambda k: self.set("interface_id", k))
        body.append(self.source)
        self.action = PickerField(self.app, "Then", [(a, model.action_label(a), "") for a in model.ACTIONS], self.fields["action"], self.action_picked, helper=model.ACTION_HELP[self.fields["action"]])
        body.append(self.action)
        self.target = PickerField(self.app, "Pass it on by", [], self.fields["forward_to"], lambda k: self.set("forward_to", k))
        body.append(self.target)
        # Satellite messages reach the Hub twice if this rule exists (MESHSAT-1276).
        self.hub_note = text(model.HUB_DUPLICATE_WARNING, "body-small", theme.AMBER, wrap=True)
        body.append(self.hub_note)
        self.enabled = SwitchRow("Rule is on", lambda on: self.set("enabled", on), active=self.fields["enabled"])
        body.append(self.enabled)
        self.priority = Field("Urgency", helper=model.urgency_helper(self.fields["priority"]), max_length=6, purpose=Gtk.InputPurpose.DIGITS)
        body.append(self.priority)
        self.qos = PickerField(self.app, "Delivery guarantee", [(g, deliveries_model.guarantee_label(int(g)), "") for g in model.GUARANTEES], str(self.fields["qos_level"]),
                               lambda k: self.set("qos_level", int(k)), helper=model.GUARANTEE_HELP)
        body.append(self.qos)
        limit = text("Limit", "title-small", theme.TEXT_SECONDARY)
        limit.set_margin_top(theme.dp(4))
        body.append(limit)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        self.per = Field("At most (messages)", max_length=6, purpose=Gtk.InputPurpose.DIGITS)
        self.window = Field("Every (seconds)", max_length=6, purpose=Gtk.InputPurpose.DIGITS)
        row.append(self.per)
        row.append(self.window)
        body.append(row)
        self.limit_help = text(model.limit_helper(self.fields["rate_limit_per_min"], self.fields["rate_limit_window"]), "body-small", theme.TEXT_MUTED, wrap=True)
        body.append(self.limit_help)
        match = text("Only messages that match", "title-small", theme.TEXT_SECONDARY)
        match.set_margin_top(theme.dp(8))
        body.append(match)
        self.keyword = Field("Contains the text (optional)")
        self.node_group = Field("From a node group (group id, optional)")
        self.sender_group = Field("From a sender group (group id, optional)")
        for field in (self.keyword, self.node_group, self.sender_group):
            body.append(field)
        hidden = model.hidden_settings(rule)
        if hidden:
            body.append(text(model.hidden_note(hidden), "body-small", theme.TEXT_MUTED, wrap=True))
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=theme.dp(560), hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(body)
        self.sheet.body.append(scroll)
        cancel = self.sheet.button("Cancel", self.sheet.close)
        paint(cancel.get_child(), theme.TEXT_SECONDARY)
        self.sheet.button("Save" if rule else "Add", self.save)
        # The fields' values, then their handlers: a handler must never run before the editor is whole.
        self.name.set_text(self.fields["name"])
        self.priority.set_text(self.fields["priority"])
        self.per.set_text(self.fields["rate_limit_per_min"])
        self.window.set_text(self.fields["rate_limit_window"])
        self.keyword.set_text(self.fields["keyword"])
        self.node_group.set_text(self.fields["node_group"])
        self.sender_group.set_text(self.fields["sender_group"])
        self.name.on_change = lambda v: self.set("name", v)
        self.priority.on_change = self.priority_changed
        self.per.on_change = lambda v: self.limit_changed(self.per, "rate_limit_per_min", v)
        self.window.on_change = lambda v: self.limit_changed(self.window, "rate_limit_window", v)
        self.keyword.on_change = lambda v: self.set("keyword", v)
        self.node_group.on_change = lambda v: self.set("node_group", v)
        self.sender_group.on_change = lambda v: self.set("sender_group", v)
        self.refresh()
        self.sheet.present()

    def set(self, key: str, value) -> None:
        self.fields[key] = value
        self.refresh()

    def action_picked(self, key: str) -> None:
        self.fields["action"] = key
        self.action.set_helper(model.ACTION_HELP[key])
        self.refresh()

    @staticmethod
    def _digits(field: Field, value: str) -> str | None:
        digits = "".join(c for c in value if c.isdigit())[:6]
        if digits != value:
            field.set_text(digits)  # the change handler runs again with the digits
            return None
        return digits

    def priority_changed(self, value: str) -> None:
        digits = self._digits(self.priority, value)
        if digits is None:
            return
        self.fields["priority"] = digits
        self.priority.set_helper(model.urgency_helper(digits))

    def limit_changed(self, field: Field, key: str, value: str) -> None:
        digits = self._digits(field, value)
        if digits is None:
            return
        self.fields[key] = digits
        self.limit_help.set_text(model.limit_helper(self.fields["rate_limit_per_min"], self.fields["rate_limit_window"]))

    def refresh(self) -> None:
        forward = self.fields["action"] == "forward"
        self.target.set_visible(forward)
        targets = [(id_, words.channel(id_), "") for id_ in model.available_links(self.screen.interfaces, keep=self.fields["forward_to"]) if id_ != self.fields["interface_id"]]
        self.target.set_options(targets, self.fields["forward_to"])
        self.hub_note.set_visible(forward and model.duplicates_the_hub(self.fields["interface_id"], self.fields["forward_to"]))
        if self.tried:
            name_error, target_error = model.errors(self.fields)
            self.name.set_error(name_error)
            self.target.set_error(target_error)

    def save(self) -> None:
        self.tried = True
        self.refresh()
        name_error, target_error = model.errors(self.fields)
        if name_error or target_error:
            return
        body = model.save_body(self.rule, self.fields)
        if self.rule:
            self.screen.call(f"/api/access-rules/{self.rule.get('id')}", lambda a: self.saved(a, body), body=body, method="PUT")
        else:
            self.screen.call("/api/access-rules", lambda a: self.saved(a, body), body=body, method="POST")

    def saved(self, answer: api.Answer, body: dict) -> None:
        if not answer.ok:
            self.app.toast(f"That did not work: {answer.error}")
            return
        self.sheet.close()
        record = answer.body if isinstance(answer.body, dict) and answer.body.get("interface_id") else body
        self.screen.saved(record, was_new=self.rule is None)
