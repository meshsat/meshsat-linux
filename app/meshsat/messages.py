# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages, as ui/screens/MessagesScreen.kt: the filter chips, the counts, Chats / All
Messages / New message, the conversation cards; the chat with its orange back arrow, lane
subtitle, lock, bubbles and composer; the New message dialog."""
from gi.repository import GLib, Gtk

from . import api, theme
from .model import words
from .screen import Screen
from .widgets import Card, Chip, PickerDialog, SubHeader, Tag, clear, hscroll, icon_button, page, scroller, spacer, text, when, when_date

EVERYONE = "!ffffffff"
SATELLITE = "satellite"


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

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
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
            texts = [m for m in texts if self.filter == "all" or lane_of(m) == self.filter][:100]
            key = ("all", tuple((m.get("id"), m.get("rx_time"), m.get("decoded_text")) for m in texts))
            if key == self._list_key:
                return
            self._list_key = key
            clear(self.list)
            if not texts:
                self.list.append(text("No messages yet", "body-medium", theme.TEXT_SECONDARY))
            for m in texts:
                self.list.append(self.message_row(m))

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

    def message_row(self, m: dict) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        row.append(text(when(m.get("rx_time")), "body-medium", theme.TEXT_SECONDARY, mono=True))
        tag = text({"satellite": "Satellite", "mesh": "Mesh", "sms": "SMS"}[lane_of(m)], "body-medium", theme.lane_colour(lane_of(m)))
        tag.set_size_request(theme.dp(64), -1)
        row.append(tag)
        out = m.get("direction") == "tx"
        row.append(text("↑" if out else "↓", "body-medium", theme.GREEN if out else theme.SIGNAL_ORANGE))
        body = text(m.get("decoded_text", ""), "body-large", ellipsize=True)
        body.set_hexpand(True)
        row.append(body)
        return row


class ChatScreen(Screen):
    """One conversation, as ChatScreen.kt: orange back arrow, title with the lane under it, a
    lock button, the bubbles, the composer with its footer line."""

    def __init__(self, app, key: str, title: str, lane: str):
        super().__init__(app)
        self.key, self.lane, self.title = key, lane, title
        self.route = "chat/" + key
        self._key = None
        self.sending = False
        lock = icon_button("outlined-lock", lambda: app.toast("Encryption keys are managed by the Bridge."), 24, theme.TEXT_SECONDARY, tooltip="Conversation encryption key")
        # Under the name, as the Android header: the node's id, the channel, or the transport.
        subtitle = detail_of(key) or {"sms": "SMS"}.get(lane, "Mesh")
        self.append(SubHeader(title, app.pop, orange=True, subtitle=subtitle, subtitle_colour=theme.lane_colour(lane), trailing=lock))
        self.bubbles = page(spacing=12)
        self.scroll = scroller(self.bubbles)
        self.append(self.scroll)
        composer = Card()
        composer.set_margin_start(theme.dp(12))
        composer.set_margin_end(theme.dp(12))
        composer.set_margin_bottom(theme.dp(12))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.entry = Gtk.Entry(placeholder_text="Message by satellite" if lane == "satellite" else "Text message")
        self.entry.add_css_class("field")
        self.entry.set_hexpand(True)
        self.entry.update_property([Gtk.AccessibleProperty.LABEL], ["Message"])
        self.entry.connect("activate", lambda *_: self.send())
        row.append(self.entry)
        self.send_button = icon_button("outlined-send", self.send, 24, theme.TEXT_PRIMARY, tooltip="Send")
        row.append(self.send_button)
        composer.append(row)
        footer = {"satellite": "By satellite, through Rock7 to the Hub.", "sms": "By SMS from this phone."}.get(lane, "By mesh, from your node.")
        composer.append(text(footer, "body-medium", theme.TEXT_SECONDARY))
        self.append(composer)
        self.update(app.state)

    def send(self) -> None:
        value = self.entry.get_text().strip()
        if not value or self.sending:
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
            body["gateway"] = "iridium"
        self.sending = True
        self.send_button.set_sensitive(False)
        me = (self.app.state.bridge or {}).get("node_id")

        def sent(answer: api.Answer) -> None:
            self.sending = False
            self.send_button.set_sensitive(True)
            if not answer.ok:
                self.app.toast(answer.error or "The message did not go.")
                return
            self.entry.set_text("")
            api.record_sent(value, body.get("to"), self.lane, me)
            self.app.poller.poll_now()

        api.fetch("/api/messages/send", sent, method="POST", body=body)

    def update(self, s: api.State) -> None:
        me = (s.bridge or {}).get("node_id")
        chat = next((c for c in conversations(s) if c["key"] == self.key), None)
        messages = list(reversed(chat["items"])) if chat else []
        key = tuple((m.get("id"), m.get("rx_time"), m.get("decoded_text"), m.get("delivery_status")) for m in messages[-80:])
        if key == self._key:
            return  # the same bubbles: no rebuild, no jump to the end under a finger
        self._key = key
        clear(self.bubbles)
        if not messages:
            self.bubbles.append(text("No messages yet", "body-medium", theme.TEXT_SECONDARY))
        for m in messages[-80:]:
            mine = m.get("direction") == "tx" or m.get("from_node") == me
            bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(6))
            bubble.add_css_class("bubble")
            if mine:
                bubble.add_css_class("mine")
            bubble.set_halign(Gtk.Align.END if mine else Gtk.Align.START)
            bubble.set_size_request(theme.dp(220), -1)
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            who = text("You" if mine else name_of(m.get("from_node"), s), "label-medium", theme.lane_colour(lane_of(m)))
            top.append(who)
            top.append(spacer())
            top.append(text(when(m.get("rx_time")), "label-medium", theme.TEXT_SECONDARY, mono=True))
            top.append(icon_button("outlined-content-copy", lambda t=m.get("decoded_text", ""): self.app.copy(t), 16, theme.TEXT_SECONDARY, tooltip="Copy"))
            bubble.append(top)
            bubble.append(text(m.get("decoded_text", ""), "body-large", wrap=True))
            self.bubbles.append(bubble)
        adjustment = self.scroll.get_vadjustment()
        GLib.idle_add(lambda: adjustment.set_value(adjustment.get_upper()) or False)


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
