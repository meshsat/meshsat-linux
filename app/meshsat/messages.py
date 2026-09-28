# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages, as ui/screens/MessagesScreen.kt: the filter chips, the counts, Chats / All
Messages / New message, the conversation cards; the chat with its orange back arrow, lane
subtitle, lock, bubbles and composer; the New message dialog."""
import time

from gi.repository import GLib, Gtk

from . import api, theme
from .model import chat as chat_words
from .model import words
from .screen import Screen
from .widgets import Card, Chip, PickerDialog, SubHeader, Tag, clear, hscroll, icon, icon_button, name_widget, page, scroller, spacer, state_tag, text, tone_colour, when, when_date

EVERYONE = "!ffffffff"
SATELLITE = "satellite"
# The transport's badge on a message, as Android stores the transport ("iridium", not "satellite").
BADGE = {"mesh": "MESH", "satellite": "IRIDIUM", "sms": "SMS"}
TRANSPORT_OF_LANE = {"mesh": "mesh", "satellite": "iridium", "sms": "sms"}


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
                    "decoded_text": m.get("text", ""), "rx_time": m.get("timestamp") or 0, "direction": "rx" if rx else "tx", "transport": "sms", "delivery_status": m.get("status", "")})
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
            title = s.contact_name(key[4:])
        else:
            title = name_of(key, s)
        out.append({"key": key, "title": title, "lane": lane_of(items[0]), "items": items, "last": items[0]})
    out.sort(key=lambda c: c["last"].get("rx_time") or 0, reverse=True)
    return out


class MessagesScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.filter = "all"
        self.view = "chats"
        self._list_key = None
        column = page(spacing=12)
        column.append(text("Messages", "headline-medium"))

        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.filter_chips = {}
        for key, label_text in (("all", "All"), ("mesh", "Mesh"), ("satellite", "Satellite"), ("sms", "SMS")):
            chip = Chip(label_text, lambda c, k=key: self.set_filter(k), selected=key == "all")
            self.filter_chips[key] = chip
            filters.append(chip)
        column.append(hscroll(filters))

        self.counts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(16))
        self.count_labels = [text("0 nodes", "body-medium", theme.TEXT_SECONDARY), text("0 today", "body-medium", theme.TEXT_SECONDARY), text("0 stored", "body-medium", theme.TEXT_SECONDARY)]
        for label in self.count_labels:
            self.counts.append(label)
        column.append(self.counts)

        views = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.view_chips = {}
        for key, label_text in (("chats", "Chats"), ("all", "All Messages")):
            chip = Chip(label_text, lambda c, k=key: self.set_view(k), selected=key == "chats")
            self.view_chips[key] = chip
            views.append(chip)
        views.append(Chip("New message", lambda c: new_message(self.app)))
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
        self.count_labels[0].set_text(words.count(len(s.others()), "node"))
        self.count_labels[1].set_text(f"{stats.get('today_text', 0)} today")
        self.count_labels[2].set_text(f"{stats.get('total', 0)} stored")
        if self.view == "chats":
            chats = [c for c in conversations(s) if self.filter == "all" or c["lane"] == self.filter]
            key = ("chats", tuple((c["key"], c["title"], len(c["items"]), c["last"].get("rx_time"), c["last"].get("decoded_text")) for c in chats))
            if key == self._list_key:
                return
            self._list_key = key
            clear(self.list)
            if not chats:
                self.list.append(text("No conversations yet", "body-medium", theme.TEXT_SECONDARY))
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
                empty = text("No messages yet", "body-large", theme.TEXT_MUTED, xalign=0.5)
                empty.set_margin_top(theme.dp(16))
                self.list.append(empty)
            for m in texts:
                self.list.append(self.message_card(m, s))

    def chat_card(self, chat: dict) -> Gtk.Widget:
        button = Gtk.Button()
        button.add_css_class("flat")
        card = Card()
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        top.append(text(chat["title"], "title-medium", ellipsize=True))
        top.append(Tag(chat["lane"]))
        top.append(spacer())
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        right.append(text(when_date(chat["last"].get("rx_time")), "body-medium", theme.TEXT_SECONDARY, xalign=1.0, mono=True))
        count = text(str(len(chat["items"])), "count", xalign=1.0)
        count.set_halign(Gtk.Align.END)
        right.append(count)
        top.append(right)
        card.append(top)
        card.append(text(chat["last"].get("decoded_text", ""), "body-large", theme.TEXT_SECONDARY, ellipsize=True))
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
        self.key, self.lane, self.title = key, lane, title
        self.route = "chat/" + key
        self._key = None
        self.sending = False
        # No per-chat key on this phone yet (0.12.0): Android's open lock, muted.
        lock = icon_button("outlined-lock-open", lambda: app.toast("Encryption keys are managed by the Bridge."), 24, theme.TEXT_MUTED, tooltip="Encryption key")
        # Under the name, as the Android header: the node's id, the channel, or the transport.
        subtitle = detail_of(key) or {"sms": "SMS"}.get(lane, "Mesh")
        self.append(SubHeader(title, app.pop, orange=True, subtitle=subtitle, subtitle_colour=theme.lane_colour(lane), trailing=lock, plain=True))
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
        self.entry = Gtk.Entry(placeholder_text=chat_words.placeholder(self.transport, self.everyone))
        self.entry.add_css_class("field")
        self.entry.add_css_class("compose-field")
        self.entry.set_hexpand(True)
        self.entry.update_property([Gtk.AccessibleProperty.LABEL], ["Message"])
        self.entry.connect("activate", lambda *_: self.send())
        self.entry.connect("changed", lambda *_: self.composer_changed())
        row.append(self.entry)
        self.send_button = icon_button("outlined-send", self.send, 24, theme.TEXT_MUTED, tooltip="Send")
        row.append(self.send_button)
        composer.append(row)
        self.hint = text("", "body-small", theme.TEXT_SECONDARY, wrap=True)
        self.hint.set_margin_start(theme.dp(4))
        self.hint.set_margin_top(theme.dp(4))
        composer.append(self.hint)
        self.append(composer)
        self.composer_changed()
        self.update(app.state)

    def composer_changed(self) -> None:
        """The hint and the send button follow what is typed and what is connected."""
        s = self.app.state
        value = self.entry.get_text()
        self.hint.set_text(chat_words.compose_hint(self.transport, value, self.everyone, s.mesh_connected(), s.modem_connected()))
        ready = chat_words.can_send(self.transport, value) and not self.sending
        self.send_button.set_sensitive(ready)
        self.send_button.set_child(icon("outlined-send", 24, theme.SIGNAL_ORANGE if ready else theme.TEXT_MUTED))

    def send(self) -> None:
        value = self.entry.get_text().strip()
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
            self.entry.set_text("")
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
    """New message, as the Android dialog: Satellite, everyone on the mesh, then the twenty
    nodes heard most recently ("Node !id" until one has told its name), then a phone number.
    A node opens that node's chat: its texts go to it and nowhere else."""
    s = app.state
    nodes = sorted(s.others(), key=lambda n: -(n.get("last_heard") or 0))[:20]
    choices = [("satellite", "Satellite", "Through Rock7 to the Hub, from anywhere with a view of the sky"),
               ("mesh", "Everyone on the mesh", "Every node on your channel")]
    choices += [("node:" + n["user_id"], name_of(n["user_id"], s), f"On the mesh, {n['user_id']}") for n in nodes if n.get("user_id")]
    choices.append(("sms", "SMS", "A text from this phone's SIM, to a phone number"))

    def picked(key: str) -> None:
        if key == "satellite":
            app.open_route("chat/satellite")
        elif key == "mesh":
            app.open_route("chat/" + EVERYONE)
        elif key.startswith("node:"):
            app.open_route("chat/" + key[5:])
        else:
            ask_number(app)

    PickerDialog(app, "New message", choices, "mesh", picked).present()


def ask_number(app) -> None:
    """The phone number for a text by SMS."""
    from .widgets import Sheet  # noqa: PLC0415

    sheet = Sheet(app, "Text a phone number")
    entry = Gtk.Entry(placeholder_text="Phone number, with country code", input_purpose=Gtk.InputPurpose.PHONE)
    entry.add_css_class("field")
    entry.update_property([Gtk.AccessibleProperty.LABEL], ["Phone number"])
    sheet.body.append(entry)

    def go() -> None:
        number = "".join(ch for ch in entry.get_text() if ch.isdigit() or ch == "+")
        if not number.startswith("+") or len(number) < 8:
            app.toast("A phone number with its country code, like +31612345678.")
            return
        sheet.close()
        app.open_route("chat/sms:" + number)

    entry.connect("activate", lambda *_: go())
    sheet.button("Cancel", sheet.close)
    sheet.button("Write", go)
    sheet.present()
