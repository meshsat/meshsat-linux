# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages, as ui/screens/MessagesScreen.kt: the filter chips, the counts, Chats / All
Messages / New message, the conversation cards; the chat with its orange back arrow, lane
subtitle, lock, bubbles and composer; the New message dialog."""
import time

from gi.repository import Gdk, GLib, Gtk, Pango

from . import api, theme
from .layout import empty_text
from .model import chat as chat_words
from .model import chatkeys, words
from .screen import Screen
from .widgets import (Card, Chip, Field, SubHeader, Tag, clear, hscroll, icon, icon_button, name_widget, page, paint, scroller, spacer, state_tag, text, tone_colour,
                      when, when_date)

EVERYONE = "!ffffffff"
SATELLITE = "satellite"
# The transport's badge on a message, as Android stores the transport ("iridium", not "satellite").
BADGE = {"mesh": "MESH", "satellite": "IRIDIUM", "sms": "SMS"}
TRANSPORT_OF_LANE = {"mesh": "mesh", "satellite": "iridium", "sms": "sms"}
# The compose box (OutlinedTextField, maxLines = 4): the text 16 dp in from the outline on every
# side, at most four lines before it scrolls.
COMPOSE_PAD = 16
COMPOSE_LINES = 4


def css() -> str:
    """The chat's compose bar, which theme.py has no class for (its .field is an entry's), on a
    stylesheet of this screen's own, one priority step above theme.py's, for classes only this
    screen sets:

    - the compose box (OutlinedTextField with focusedBorderColor = TextSecondary and
      unfocusedBorderColor = Border): see-through on its card, a 1 dp Border outline, 2 dp in
      TextSecondary while typing (drawn inside it, so nothing moves), 4 dp corners, 56 dp for
      one line, the text 16 dp in; bodyLarge text, the orange cursor;
    - the send arrow in TextMuted at full strength while there is nothing to send (Compose's
      explicit tint on a disabled IconButton), where GTK dims a disabled button and its image."""
    border = 1  # px: GTK lays the border out, Compose draws it inside the bounds
    return "\n".join((
        f".compose-box {{ background: none; border: {border}px solid {theme.BORDER}; border-radius: {theme.px(4)}; padding: 0 {16 * theme.SCALE - border:.1f}px; "
        f"min-height: {56 * theme.SCALE - 2 * border:.1f}px; box-shadow: none; }}",
        f".compose-box:focus-within {{ border-color: {theme.TEXT_SECONDARY}; box-shadow: inset 0 0 0 1px {theme.TEXT_SECONDARY}; }}",
        f"textview.compose-text, textview.compose-text > text {{ background: none; color: {theme.TEXT_PRIMARY}; font-size: {theme.px(16)}; "
        f"font-weight: 400; caret-color: {theme.SIGNAL_ORANGE}; }}",
        ".send-button:disabled, .send-button:disabled > image { filter: none; opacity: 1; -gtk-icon-filter: none; }",
    ))


_STYLE = None


def style() -> None:
    """css() on the display, once."""
    global _STYLE
    display = Gdk.Display.get_default()
    if _STYLE is not None or display is None:
        return
    _STYLE = Gtk.CssProvider()
    _STYLE.load_from_string(css())
    Gtk.StyleContext.add_provider_for_display(display, _STYLE, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)


def filter_chip(label_text: str, on_tap, lane: str | None = None, selected: bool = False) -> Chip:
    """A FilterChip (theme.py's .chip: see-through with its outline, a grey bodySmall label;
    selected, SurfaceLight and OffWhite). `lane` (mesh, satellite, sms): selected, the lane's colour
    at 20 % behind a label in that colour (MessagesScreen.kt:227-244, theme.py's .chip.lane-*)."""
    chip = Chip(label_text, on_tap, selected=selected)
    if lane:
        chip.add_css_class(f"lane-{lane}")
    return chip


def lane_of(message: dict) -> str:
    transport = message.get("transport")
    if transport in ("iridium", "iridium_imt", "sbd", "imt"):
        return "satellite"
    if transport in ("sms", "cellular"):
        return "sms"
    return "mesh"


def sms_as_messages(s: api.State) -> list:
    """The texts that went through the phone's SIM (the Bridge's SMS store, plus this app's
    own sent log for SMS), in the shape of the mesh messages so one chat list holds both."""
    me = (s.bridge or {}).get("node_id") or ""
    out = []
    for m in s.sms:
        rx = m.get("direction") == "rx"
        out.append({"id": m.get("id"), "from_node": m.get("phone") if rx else me, "to_node": me if rx else m.get("phone"), "portnum_name": "TEXT_MESSAGE_APP",
                    "decoded_text": m.get("text", ""), "rx_time": m.get("timestamp") or 0, "direction": "rx" if rx else "tx", "transport": "sms", "delivery_status": m.get("status", ""),
                    "encrypted": bool(m.get("encrypted"))})
    for m in s.messages:
        if m.get("transport") == "sms" and m.get("local") and not any(o.get("direction") == "tx" and o["decoded_text"] == m.get("decoded_text") and abs((o.get("rx_time") or 0) - (m.get("rx_time") or 0)) < 120 for o in out):
            out.append(m)
    return out


def conversations(s: api.State) -> list:
    texts = [m for m in s.messages if m.get("portnum_name") == "TEXT_MESSAGE_APP" and m.get("decoded_text") and m.get("transport") != "sms"] + sms_as_messages(s)
    me = (s.bridge or {}).get("node_id")
    groups = {}
    for m in texts:
        if lane_of(m) == "satellite":
            key = SATELLITE
        elif lane_of(m) == "sms":
            key = "sms:" + str(m.get("from_node") if m.get("direction") == "rx" else m.get("to_node"))
        elif m.get("to_node") == EVERYONE or m.get("from_node") == EVERYONE:
            key = EVERYONE
        else:
            key = m.get("from_node") if m.get("from_node") != me else m.get("to_node")
        groups.setdefault(key, []).append(m)
    out = []
    for key, items in groups.items():
        items.sort(key=lambda m: m.get("rx_time") or 0, reverse=True)
        if key == SATELLITE:
            title = "Satellite"
        elif key == EVERYONE:
            title = "Everyone on the mesh"
        elif key.startswith("sms:"):
            title = key[4:]  # Peers.displayName: a phone number is named by itself, an emergency contact's too
        else:
            title = name_of(key, s)
        out.append({"key": key, "title": title, "lane": lane_of(items[0]), "items": items, "last": items[0]})
    out.sort(key=lambda c: c["last"].get("rx_time") or 0, reverse=True)
    return out


class MessagesScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        style()
        self.filter = "all"
        self.view = "chats"
        self._list_key = None
        column = page(spacing=12)
        column.append(text("Messages", "headline-medium"))

        # The transport filters: a selected Mesh, Satellite or SMS chip takes its lane's colour
        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.filter_chips = {}
        for key, label_text in (("all", "All"), ("mesh", "Mesh"), ("satellite", "Satellite"), ("sms", "SMS")):
            chip = filter_chip(label_text, lambda c, k=key: self.set_filter(k), lane=None if key == "all" else key, selected=key == "all")
            self.filter_chips[key] = chip
            filters.append(chip)
        column.append(hscroll(filters))

        # The counts in bodySmall TextMuted, 16 dp apart
        self.counts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(16))
        self.count_labels = [text(value, "body-small", theme.TEXT_MUTED) for value in ("0 nodes", "0 today", "0 stored")]
        for label in self.count_labels:
            self.counts.append(label)
        column.append(self.counts)

        views = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.view_chips = {}
        for key, label_text in (("chats", "Chats"), ("all", "All Messages")):
            chip = filter_chip(label_text, lambda c, k=key: self.set_view(k), selected=key == "chats")
            self.view_chips[key] = chip
            views.append(chip)
        views.append(filter_chip("New message", lambda c: new_message(self.app)))
        column.append(hscroll(views))

        # The search bar of All Messages (MessagesScreen.kt): a magnifier, the query, a clear button.
        self.query = ""
        self.search = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.search.add_css_class("search")
        magnifier = icon("outlined-search", 24, theme.TEXT_MUTED)
        magnifier.set_valign(Gtk.Align.CENTER)
        name_widget(magnifier, "Search")
        self.search.append(magnifier)
        self.search_entry = Gtk.Entry(placeholder_text=chat_words.SEARCH_PLACEHOLDER)
        self.search_entry.set_hexpand(True)
        name_widget(self.search_entry, "Search messages")
        self.search_entry.connect("changed", self.query_changed)
        self.search.append(self.search_entry)
        self.clear_button = icon_button("outlined-clear", lambda: self.search_entry.set_text(""), 24, theme.TEXT_MUTED, tooltip="Clear")
        self.clear_button.set_visible(False)
        self.search.append(self.clear_button)
        self.search.set_visible(False)
        column.append(self.search)

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        column.append(self.list)
        self.append(scroller(column))

    def set_filter(self, key: str) -> None:
        self.filter = key
        for k, chip in self.filter_chips.items():
            chip.set_selected(k == key)
        self._list_key = None
        self.update(self.app.state)

    def set_view(self, key: str) -> None:
        self.view = key
        for k, chip in self.view_chips.items():
            chip.set_selected(k == key)
        self.search.set_visible(key == "all")
        self._list_key = None
        self.update(self.app.state)

    def query_changed(self, entry) -> None:
        self.query = entry.get_text()
        self.clear_button.set_visible(bool(self.query.strip()))
        self._list_key = None
        self.update(self.app.state)

    def update(self, s: api.State) -> None:
        stats = s.message_stats or {}
        # Every node of the radio's list, the phone's own included (MessagesScreen.kt: nodes.size)
        self.count_labels[0].set_text(words.count(len(s.nodes), "node"))
        self.count_labels[1].set_text(f"{stats.get('today_text', 0)} today")
        self.count_labels[2].set_text(f"{stats.get('total', 0)} stored")
        if self.view == "chats":
            chats = [c for c in conversations(s) if self.filter == "all" or c["lane"] == self.filter]
            key = ("chats", tuple((c["key"], c["title"], len(c["items"]), c["last"].get("rx_time"), c["last"].get("decoded_text"), sealed(c)) for c in chats))
            if key == self._list_key:
                return
            self._list_key = key
            clear(self.list)
            if not chats:
                # MessagesScreen.kt:354-362: Box(fillMaxSize, padding(top = 16.dp), Center)
                self.list.append(empty_text("No conversations yet", "body-large", top=theme.dp(16)))
            for chat in chats:
                self.list.append(self.chat_card(chat))
        else:
            texts = [m for m in s.messages if m.get("portnum_name") == "TEXT_MESSAGE_APP" and m.get("decoded_text") and m.get("transport") != "sms"] + sms_as_messages(s)
            texts.sort(key=lambda m: m.get("rx_time") or 0, reverse=True)
            texts = chat_words.search(texts, self.query)
            texts = [m for m in texts if self.filter == "all" or lane_of(m) == self.filter][:100]
            key = ("all", self.query, tuple((m.get("id"), m.get("rx_time"), m.get("decoded_text"), m.get("delivery_status")) for m in texts))
            if key == self._list_key:
                return
            self._list_key = key
            clear(self.list)
            if not texts:
                # MessagesScreen.kt:334-342, the same centred Box
                self.list.append(empty_text("No messages yet", "body-large", top=theme.dp(16)))
            for m in texts:
                self.list.append(self.message_card(m, s))

    def chat_card(self, chat: dict) -> Gtk.Widget:
        """ConversationCard (MessagesScreen.kt:396-448): the name in titleMedium, the lane's tag,
        the amber lock when a message of the conversation went or came sealed; at the right the
        date in bodySmall TextMuted right over the count on its SurfaceLight badge; the last text
        in bodyMedium TextMuted, one line, 4 dp under them."""
        button = Gtk.Button()
        button.add_css_class("flat")
        card = Card(spacing=4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        top.append(text(chat["title"], "title-medium", ellipsize=True))
        top.append(Tag(chat["lane"]))
        if sealed(chat):
            lock = icon("filled-lock", 16, theme.AMBER)
            lock.set_valign(Gtk.Align.CENTER)
            name_widget(lock, "Encrypted")
            top.append(lock)
        top.append(spacer())
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        right.append(text(when_date(chat["last"].get("rx_time")), "body-small", theme.TEXT_MUTED, xalign=1.0))
        count = text(str(len(chat["items"])), "count", xalign=1.0)  # theme.py's .count: bodySmall in Plex Sans on SurfaceLight
        count.set_halign(Gtk.Align.END)
        right.append(count)
        top.append(right)
        card.append(top)
        card.append(text(chat["last"].get("decoded_text", ""), "body-medium", theme.TEXT_MUTED, ellipsize=True))
        button.set_child(card)
        button.update_property([Gtk.AccessibleProperty.LABEL], [f"Chat with {chat['title']}"])
        button.connect("clicked", lambda *_: self.app.push(ChatScreen(self.app, chat["key"], chat["title"], chat["lane"]), chat["title"]))
        return button

    def message_card(self, m: dict, s: api.State) -> Gtk.Widget:
        """One message of All Messages, as Android's MessageCard: the transport and the
        direction as tags, a forwarded message's state, the time to the second, a copy button,
        who it is with, and the text."""
        lane = lane_of(m)
        out = m.get("direction") == "tx"
        card = Card(spacing=4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        badge = text(BADGE.get(lane, lane.upper()), "body-small", theme.lane_colour(lane))
        badge.add_css_class("state-tag")
        badge.add_css_class(f"tint-{lane}")
        top.append(badge)
        top.append(state_tag("TX" if out else "RX", "amber" if out else "teal", "body-small"))
        if m.get("forwarded"):
            top.append(state_tag(chat_words.delivery_label(m.get("delivery_status", "")), "muted", "body-small"))
        top.append(spacer())
        top.append(text(time.strftime("%H:%M:%S", time.localtime(m.get("rx_time") or 0)) if m.get("rx_time") else "", "body-small", theme.TEXT_MUTED))
        top.append(icon_button("outlined-content-copy", lambda t=m.get("decoded_text", ""): self.app.copy(t), 16, theme.TEXT_MUTED, tooltip="Copy", small=True))
        card.append(top)
        peer = m.get("to_node") if out else m.get("from_node")
        card.append(text(str(peer or ""), "body-small", theme.TEXT_MUTED))
        card.append(text(m.get("decoded_text", ""), "body-large", wrap=True))
        return card


class ChatScreen(Screen):
    """One conversation, as ConversationChatView (MessagesScreen.kt): everything inside 16 dp of
    padding; the header (orange back arrow, the name in titleLarge, the lane under it in
    bodySmall, the lock) 8 dp above the messages; the bubbles 4 dp apart; the compose bar with
    its line under the box."""

    def __init__(self, app, key: str, title: str, lane: str):
        super().__init__(app)
        style()
        self.key, self.lane, self.title = key, lane, title
        self.route = "chat/" + key
        self._key = None
        self.sending = False
        # The lock: this chat's own key, kept by the Bridge (Android's KeyManagementSection).
        self.chat_key = None
        self.lock = icon_button("filled-lock-open", self.toggle_key, 24, theme.TEXT_MUTED, tooltip=chatkeys.LOCK)
        # Under the name, as the Android header: the node's id, the channel, or the transport.
        subtitle = detail_of(key) or {"sms": "SMS"}.get(lane, "Mesh")
        self.append(SubHeader(title, app.pop, orange=True, subtitle=subtitle, subtitle_colour=theme.lane_colour(lane), trailing=self.lock, plain=True))
        self.key_section = ChatKeySection(self)
        self.key_section.set_visible(False)
        self.append(self.key_section)
        self.bubbles = page(spacing=4, padded=False)
        self.bubbles.set_margin_start(theme.dp(16))
        self.bubbles.set_margin_end(theme.dp(16))
        self.bubbles.set_margin_top(theme.dp(4))
        self.bubbles.set_margin_bottom(theme.dp(4))
        self.scroll = scroller(self.bubbles)
        self.append(self.scroll)
        # The compose bar (MessagesScreen.kt): the box, the send button, and under them the line
        # that says how this message goes, and for a satellite message its size and cost.
        self.transport = TRANSPORT_OF_LANE.get(lane, "mesh")
        self.everyone = key == EVERYONE
        composer = Card(padded=False, spacing=0)
        composer.add_css_class("compose")
        composer.set_margin_start(theme.dp(16))
        composer.set_margin_end(theme.dp(16))
        composer.set_margin_bottom(theme.dp(16))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        # OutlinedTextField(maxLines = 4): the text wraps and the box grows with it to four lines,
        # then scrolls. A TextView in a scroller that takes its height, up to four lines; the
        # placeholder lies over it while it is empty (a TextView has none of its own).
        placeholder = chat_words.placeholder(self.transport, self.everyone)
        self.entry = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        self.entry.set_top_margin(theme.dp(COMPOSE_PAD))
        self.entry.set_bottom_margin(theme.dp(COMPOSE_PAD))
        self.entry.add_css_class("compose-text")
        self.entry.update_property([Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.PLACEHOLDER], ["Message", placeholder])
        self.buffer = self.entry.get_buffer()
        self.buffer.connect("changed", lambda *_: self.composer_changed())
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)  # before the TextView makes Enter a new line
        keys.connect("key-pressed", self.composer_key)
        self.entry.add_controller(keys)
        self.entry_box = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC, propagate_natural_height=True)
        self.entry_box.add_css_class("compose-box")
        self.entry_box.set_child(self.entry)
        self.fit_composer(round(16 * theme.SCALE * 1.3))  # IBM Plex Sans' line is 1.3 em; measured once on view
        self.placeholder = Gtk.Label(label=placeholder, xalign=0.0, accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.placeholder.add_css_class("body-medium")
        paint(self.placeholder, theme.TEXT_SECONDARY)
        self.placeholder.set_ellipsize(Pango.EllipsizeMode.END)
        self.placeholder.set_can_target(False)
        self.placeholder.set_halign(Gtk.Align.FILL)
        self.placeholder.set_valign(Gtk.Align.START)
        self.placeholder.set_margin_start(theme.dp(COMPOSE_PAD))
        self.placeholder.set_margin_end(theme.dp(COMPOSE_PAD))
        self.placeholder.set_margin_top(1 + theme.dp(COMPOSE_PAD))  # under the 1 px outline, where the first line starts
        field = Gtk.Overlay()
        field.set_hexpand(True)
        field.set_child(self.entry_box)
        field.add_overlay(self.placeholder)
        row.append(field)
        # IconButton(48 dp) with the filled Send arrow, in the middle of the box's height
        self.send_button = icon_button("filled-send", self.send, 24, theme.TEXT_MUTED, tooltip="Send")
        self.send_button.add_css_class("send-button")
        self.send_button.set_valign(Gtk.Align.CENTER)
        row.append(self.send_button)
        composer.append(row)
        self.hint = text("", "body-small", theme.TEXT_SECONDARY, wrap=True)
        self.hint.set_margin_start(theme.dp(4))
        self.hint.set_margin_top(theme.dp(4))
        composer.append(self.hint)
        self.append(composer)
        self.composer_changed()
        self.update(app.state)

    # The chat's key
    def on_show(self) -> None:
        self.fit_composer(self.entry.create_pango_layout("Mg").get_pixel_size()[1])
        self.fetch(chatkeys.path(self.key), self.key_loaded)
        self.paint_lock()

    def key_loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict) and chatkeys.valid(str(answer.body.get("key") or "")):
            self.chat_key = answer.body["key"]
            self.key_section.show_key(self.chat_key)
        elif answer.status == 404:
            self.chat_key = None
            self.key_section.show_key(None)
        self.paint_lock()

    def paint_lock(self) -> None:
        on = chatkeys.lock_on(self.chat_key, self.app.prefs.get("messaging_key", ""))
        self.lock.set_child(icon("filled-lock" if on else "filled-lock-open", 24, theme.AMBER if on else theme.TEXT_MUTED))

    def toggle_key(self) -> None:
        self.key_section.set_visible(not self.key_section.get_visible())

    def fit_composer(self, line: int) -> None:
        """The box grows to COMPOSE_LINES lines of `line` px, then scrolls."""
        if line > 0:
            self.entry_box.set_max_content_height(2 * theme.dp(COMPOSE_PAD) + COMPOSE_LINES * line)

    def composed(self) -> str:
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)

    def composer_key(self, _controller, keyval: int, _keycode: int, state) -> bool:
        """Enter sends, as the keyboard's Send key does on Android (ImeAction.Send); Shift+Enter
        starts a new line."""
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter) and not state & Gdk.ModifierType.SHIFT_MASK:
            self.send()
            return True
        return False

    def composer_changed(self) -> None:
        """The hint and the send button follow what is typed and what is connected; the
        placeholder shows while the box is empty."""
        s = self.app.state
        value = self.composed()
        self.placeholder.set_visible(not value)
        self.hint.set_text(chat_words.compose_hint(self.transport, value, self.everyone, s.mesh_connected(), s.modem_connected()))
        ready = chat_words.can_send(self.transport, value) and not self.sending
        self.send_button.set_sensitive(ready)
        self.send_button.set_child(icon("filled-send", 24, theme.SIGNAL_ORANGE if ready else theme.TEXT_MUTED))

    def send(self) -> None:
        value = self.composed().strip()
        if not chat_words.can_send(self.transport, value) or self.sending:
            return
        body = {"text": value}
        if self.lane == "sms":
            if not self.app.state.sms_ready():
                self.app.toast(self.app.state.sms_reason() or "SMS cannot go right now.")
                return
            body["gateway"] = "cellular"
            body["to"] = self.key[4:]
        elif self.key not in (EVERYONE, SATELLITE):
            body["to"] = self.key
        if self.lane == "satellite":
            body["gateway"] = "iridium"  # queued even without the modem: it goes out once a session succeeds
        elif not self.app.state.mesh_connected():
            self.app.toast(chat_words.NODE_NOT_CONNECTED)
            return
        self.sending = True
        self.composer_changed()
        me = (self.app.state.bridge or {}).get("node_id")

        def sent(answer: api.Answer) -> None:
            self.sending = False
            if not answer.ok:
                self.composer_changed()
                self.app.toast(answer.error or "The message did not go.")
                return
            self.buffer.set_text("")
            self.composer_changed()
            api.record_sent(value, body.get("to"), self.lane, me)
            self.app.poller.poll_now()

        api.fetch("/api/messages/send", sent, method="POST", body=body)

    def update(self, s: api.State) -> None:
        me = (s.bridge or {}).get("node_id")
        self.composer_changed()
        chat = next((c for c in conversations(s) if c["key"] == self.key), None)
        messages = list(reversed(chat["items"])) if chat else []
        key = tuple((m.get("id"), m.get("rx_time"), m.get("decoded_text"), m.get("delivery_status")) for m in messages[-80:])
        if key == self._key:
            return  # the same bubbles: no rebuild, no jump to the end under a finger
        self._key = key
        clear(self.bubbles)  # an empty chat is an empty list, as on Android
        for m in messages[-80:]:
            self.bubbles.append(self.bubble(m, me))
        adjustment = self.scroll.get_vadjustment()
        GLib.idle_add(lambda: adjustment.set_value(adjustment.get_upper()) or False)

    def bubble(self, m: dict, me: str | None) -> Gtk.Widget:
        """ChatBubble: four fifths of the width, at the right for the phone's own messages; the
        transport's badge and, at the right of the header, the time, the delivery mark of a
        message the phone sent, and a small copy button; the text under them."""
        mine = m.get("direction") == "tx" or m.get("from_node") == me
        lane = lane_of(m)
        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bubble.add_css_class("bubble")
        if mine:
            bubble.add_css_class("mine")
        # The header: labelSmall (12 sp, medium), 20 dp tall with the copy button.
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        top.append(text(BADGE.get(lane, lane.upper()), "label-medium", theme.lane_colour(lane)))
        if m.get("encrypted"):
            # It went or came sealed, and the Bridge opened it: Android's amber lock, "Decrypted"
            lock = icon("filled-lock", 12, theme.AMBER)
            lock.set_valign(Gtk.Align.CENTER)
            name_widget(lock, "Decrypted")
            top.append(lock)
        if m.get("forwarded") and not mine:
            top.append(text("Forwarded", "label-medium", theme.TEXT_MUTED))
        top.append(spacer())
        top.append(text(when(m.get("rx_time")), "label-medium", theme.TEXT_MUTED))
        if mine:
            icon_name, tone, label = chat_words.mark(m.get("delivery_status", ""))
            mark = icon(icon_name, 14, tone_colour(tone))
            mark.set_valign(Gtk.Align.CENTER)
            name_widget(mark, label)
            top.append(mark)
        top.append(icon_button("outlined-content-copy", lambda t=m.get("decoded_text", ""): self.app.copy(t), 12, theme.TEXT_MUTED, tooltip="Copy", small=True))
        bubble.append(top)
        body = text(m.get("decoded_text", ""), "body-medium", wrap=True)
        body.set_margin_top(theme.dp(4))
        body.set_selectable(True)
        bubble.append(body)
        # Android's fillMaxWidth(0.8f): four of five equal columns, the fifth empty.
        row = Gtk.Grid(column_homogeneous=True)
        row.attach(bubble, 1 if mine else 0, 0, 4, 1)
        filler = Gtk.Box()
        row.attach(filler, 0 if mine else 4, 0, 1, 1)
        return row


def sealed(chat: dict) -> bool:
    """A message of the conversation went or came sealed (ConversationSummary.hasEncrypted)."""
    return any(m.get("encrypted") for m in chat["items"])


def name_of(node_id: str | None, s: api.State) -> str:
    """What the user calls a mesh node, as Peers.displayName: its long name, or "Node !id"
    until the phone has heard a NodeInfo from it."""
    if node_id == EVERYONE:
        return "Everyone on the mesh"
    for n in s.nodes:
        if n.get("user_id") == node_id and n.get("long_name"):
            return n["long_name"]
    return f"Node {node_id}" if node_id else "?"


def detail_of(key: str) -> str | None:
    """The line under the name, as Peers.detail: the id people may need, or what the channel is."""
    if key == EVERYONE:
        return "The mesh channel"
    if key == SATELLITE:
        return "By satellite, through Rock7 to the Hub"
    if key.startswith("sms:"):
        return None
    return key


def new_message(app) -> None:
    """NewMessageDialog (MessagesScreen.kt:1085-1172): the satellite, everyone on the mesh, the
    twenty nodes heard most recently ("Node !id" until one has told its name), each a row with
    its lane's dot, then a phone number and "Text this number". A node opens that node's chat:
    its texts go to it and nowhere else."""
    from .widgets import Field, Sheet  # noqa: PLC0415

    s = app.state
    sheet = Sheet(app, "New message", width=340)
    rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))

    def row(title: str, detail: str, lane: str, route: str) -> None:
        button = Gtk.Button()
        button.add_css_class("flat")
        button.add_css_class("new-row")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        dot = Gtk.Box()
        dot.add_css_class("new-dot")
        dot.add_css_class({"satellite": "bg-iridium", "mesh": "bg-mesh"}.get(lane, "bg-mesh"))
        dot.set_valign(Gtk.Align.CENTER)
        inner.append(dot)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text(title, "title-medium", ellipsize=True))
        texts.append(text(detail, "body-small", theme.TEXT_SECONDARY, wrap=True))
        inner.append(texts)
        button.set_child(inner)
        button.connect("clicked", lambda *_: (sheet.close(), app.open_route(route)))
        rows.append(button)

    row("Satellite", "Through Rock7 to the Hub, from anywhere with a view of the sky", "satellite", "chat/satellite")
    row("Everyone on the mesh", "Every node on your channel", "mesh", "chat/" + EVERYONE)
    for n in sorted(s.others(), key=lambda n: -(n.get("last_heard") or 0))[:20]:
        if n.get("user_id"):
            row(name_of(n["user_id"], s), f"On the mesh, {n['user_id']}", "mesh", "chat/" + n["user_id"])
    number = Field(chat_words.NUMBER_LABEL, purpose=Gtk.InputPurpose.PHONE)
    number.set_margin_top(theme.dp(8))
    rows.append(number)
    scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=theme.dp(420), hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(rows)
    sheet.body.append(scroll)

    def text_it() -> None:
        if chat_words.number_ok(number.text):
            sheet.close()
            app.open_route("chat/sms:" + chat_words.number_of(number.text))

    cancel = sheet.button("Cancel", sheet.close)
    cancel.add_css_class("muted-text")
    go = sheet.button(chat_words.TEXT_NUMBER, text_it)
    go.set_sensitive(False)
    number.on_change = lambda value: go.set_sensitive(chat_words.number_ok(value))
    number.entry.connect("activate", lambda *_: text_it())
    sheet.present()


class ChatKeySection(Gtk.Box):
    """KeyManagementSection (MessagesScreen.kt:854-969), between the chat's header and its
    bubbles: the title, what the key does, the key (hidden until Show), Show/Generate/Save and
    Copy/Paste/Remove. Save, Remove and the key itself go to the Bridge's keystore (B21); Generate
    and Paste only fill the field, as on Android."""

    def __init__(self, chat: "ChatScreen"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.chat = chat
        self.add_css_class("card")
        self.add_css_class("card-pad")
        for side in ("start", "end"):
            getattr(self, f"set_margin_{side}")(theme.dp(16))
        self.set_margin_bottom(theme.dp(8))
        self.append(text(chatkeys.TITLE, "title-small"))
        self.append(text(chatkeys.NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        # OutlinedTextField(label = { Text("Hex key (64 chars)", style = bodySmall) }, textStyle =
        # labelMedium): the label inside the box until there is a key, then on its outline, 12 sp
        # in both places (its own style, not the field's bodyLarge); the key in Plex Sans, 12 sp,
        # medium (theme.py's .field.label-medium)
        self.field = Field(chatkeys.FIELD, purpose=Gtk.InputPurpose.PASSWORD)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_size_new_absolute(round(12 * theme.SCALE * Pango.SCALE)))
        self.field.label.set_attributes(attrs)
        self.entry = self.field.entry
        self.entry.add_css_class("label-medium")
        self.entry.set_visibility(False)
        self.append(self.field)
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        self.show_button = key_button(chatkeys.SHOW, self.toggle_show, "tonal-surface")
        row1.append(self.show_button)
        row1.append(key_button(chatkeys.GENERATE, self.generate, "amber-fill"))
        row1.append(key_button(chatkeys.SAVE, self.save, ""))
        self.append(row1)
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        row2.append(key_button(chatkeys.COPY, self.copy, "tonal-surface"))
        row2.append(key_button(chatkeys.PASTE, self.paste, "tonal-surface"))
        self.remove_button = key_button(chatkeys.REMOVE, self.remove, "tonal-surface")
        self.remove_button.set_visible(False)
        row2.append(self.remove_button)
        self.append(row2)

    def show_key(self, key: str | None) -> None:
        """The chat's key as the Bridge has it: in the field (hidden), and Remove offered."""
        self.entry.set_text(key or "")
        self.remove_button.set_visible(bool(key))

    def toggle_show(self) -> None:
        showing = not self.entry.get_visibility()
        self.entry.set_visibility(showing)
        self.show_button.set_label(chatkeys.HIDE if showing else chatkeys.SHOW)

    def generate(self) -> None:
        self.entry.set_text(chatkeys.generate())

    def save(self) -> None:
        typed = self.entry.get_text()
        app = self.chat.app
        if not chatkeys.valid(typed):
            app.toast(chatkeys.INVALID)
            return

        def saved(answer: api.Answer) -> None:
            if not answer.ok:
                app.toast(answer.error or "The Bridge did not take the key.")
                return
            self.chat.chat_key = typed.lower()
            self.remove_button.set_visible(True)
            self.chat.paint_lock()
            app.toast(chatkeys.SAVED)

        self.chat.call(chatkeys.path(self.chat.key), saved, body={"key": typed}, method="PUT")

    def copy(self) -> None:
        typed = self.entry.get_text()
        if typed.strip():
            self.chat.app.window.get_clipboard().set(typed)
            self.chat.app.toast(chatkeys.COPIED)

    def paste(self) -> None:
        clipboard = self.chat.app.window.get_clipboard()

        def read(board, result) -> None:
            try:
                clip = board.read_text_finish(result) or ""
            except GLib.Error:
                clip = ""
            if chatkeys.valid(clip):
                self.entry.set_text(clip)
                self.chat.app.toast(chatkeys.PASTED)
            else:
                self.chat.app.toast(chatkeys.NOT_A_KEY)

        clipboard.read_text_async(None, read)

    def remove(self) -> None:
        app = self.chat.app

        def removed(answer: api.Answer) -> None:
            if not answer.ok and answer.status != 404:
                app.toast(answer.error or "The Bridge did not remove the key.")
                return
            self.chat.chat_key = None
            self.show_key(None)
            self.chat.paint_lock()
            app.toast(chatkeys.REMOVED)

        self.chat.call(chatkeys.path(self.chat.key), removed, method="DELETE")


def key_button(label: str, on_click, style: str) -> Gtk.Button:
    """Android's Button(... weight(1f)) with bodySmall text, in its colour."""
    from .widgets import filled_button  # noqa: PLC0415

    button = filled_button(label, on_click)
    button.add_css_class("small-text")
    if style:
        button.add_css_class(style)
    return button

