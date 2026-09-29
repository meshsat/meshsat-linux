# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Messaging (ui/screens/SettingsScreen.kt:736-983, 1134-1177): Encryption, Message
compression and Quick messages, in MeshSat Android's words. The settings live where the Bridge
applies them, in the links' transform chains (model/messaging.py); the app's preferences keep
what Android keeps and the chains cannot hold (the key while encryption is off, the switches
before there is a key). Every change is written at once, as Android's settings are."""
from gi.repository import GLib, Gtk

from .. import api, files, theme
from ..model import messaging as model
from ..screen import SubScreen
from ..widgets import Card, SwitchRow, clear, filled_button, name_widget, text

PREFS = ("messaging_enabled", "messaging_key", "messaging_auto_decrypt", "messaging_stages")


def section_card(title: str) -> Card:
    """Android's SectionCard."""
    card = Card(spacing=8)
    card.append(text(title, "title-medium"))
    return card


def small_button(label: str, on_click, style: str) -> Gtk.Button:
    """Android's Button(... weight(1f)) with bodySmall text, in its colour."""
    button = filled_button(label, on_click)
    button.add_css_class("small-text")
    if style:
        button.add_css_class(style)
    return button


class MessagingScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Messaging")
        self.route = "setup/messaging"
        self.links = {}  # link id -> the Bridge's interface record
        self.encoder = False  # MSVQ-SC can encode on this Bridge
        self.loaded = False
        self.shown = False
        self._drawn = None

        # Encryption
        enc = section_card("Encryption")
        self.enabled = SwitchRow("Encryption enabled", self.set_enabled)
        self.auto = SwitchRow("Auto-decrypt incoming SMS", self.set_auto_decrypt)
        enc.append(self.enabled)
        enc.append(self.auto)
        self.key_label = text(model.KEY_LABEL, "label-medium", theme.TEXT_SECONDARY)
        enc.append(self.key_label)
        self.key = Gtk.Entry()
        self.key.add_css_class("field")
        self.key.add_css_class("mono")
        self.key.set_visibility(False)
        self.key.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.key.update_property([Gtk.AccessibleProperty.LABEL], [model.KEY_LABEL])
        enc.append(self.key)
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        self.show_button = small_button("Show", self.toggle_show, "tonal-surface")
        row1.append(self.show_button)
        row1.append(small_button("Generate", self.generate, "amber-fill"))
        row1.append(small_button("Save", self.save_key, ""))
        enc.append(row1)
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        row2.append(small_button("Copy", self.copy_key, "tonal-surface"))
        row2.append(small_button("Paste", self.paste_key, "tonal-surface"))
        row2.append(small_button("Share", self.share_key, "tonal-surface"))
        enc.append(row2)
        self.no_sms = text(model.NO_SMS_LINK, "body-small", theme.AMBER, wrap=True)
        self.no_sms.set_visible(False)
        enc.append(self.no_sms)
        enc.append(text(model.FALLBACK_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        self.column.append(enc)

        # Message compression
        comp = section_card("Message compression")
        comp.append(text(model.COMPRESSION_NOTE.strip(), "body-small", theme.TEXT_MUTED, wrap=True))
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.rows.set_margin_top(theme.dp(8))
        comp.append(self.rows)
        self.no_encoder = text(model.NO_ENCODER, "body-small", theme.TEXT_MUTED, wrap=True)
        comp.append(self.no_encoder)
        self.stages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.stages_box.set_margin_top(theme.dp(8))
        comp.append(self.stages_box)
        self.column.append(comp)

        # Quick messages
        quick = section_card("Quick messages")
        quick.append(text(model.loaded_line(), "body-small", theme.TEXT_MUTED))
        for words, code in model.shown_codes():
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            label = text(words, "body-small", wrap=True)
            label.set_hexpand(True)
            line.append(label)
            line.append(text(code, "label-small", theme.TEXT_MUTED))
            quick.append(line)
        if model.more_line():
            quick.append(text(model.more_line(), "body-small", theme.TEXT_MUTED))
        quick.append(text(model.WIRE_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        self.column.append(quick)
        self.render()

    # Data
    def on_show(self) -> None:
        self.every(15, self.load)

    def load(self) -> None:
        self.fetch("/api/interfaces", self.got_links)
        self.fetch("/api/transforms/capabilities", self.got_caps)

    def got_links(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.links = {i.get("id"): i for i in answer.body if isinstance(i, dict)}
            self.loaded = True
            self.adopt_bridge()
            self.render()

    def got_caps(self, answer: api.Answer) -> None:
        encoder = bool(answer.ok and isinstance(answer.body, dict) and answer.body.get("msvqsc_encode"))
        if encoder != self.encoder:
            self.encoder = encoder
            self.render()

    def chains(self, link: str) -> tuple:
        record = self.links.get(link) or {}
        return model.steps(record.get("egress_transforms")), model.steps(record.get("ingress_transforms"))

    def adopt_bridge(self) -> None:
        """What the SMS link already does wins over what the app remembered: a key set there
        (or by the Links page) is the key."""
        egress, ingress = self.chains(model.SMS)
        key = model.inline_key(egress) or model.inline_key(ingress)
        prefs = self.app.prefs
        if key and model.valid_key(key):
            prefs.set(messaging_key=key, messaging_enabled=model.encrypts(egress), messaging_auto_decrypt=model.decrypts(ingress))

    # Settings (the app's preferences hold what Android's SettingsRepository holds)
    def pref(self, name: str, default):
        return self.app.prefs.get(name, default)

    @property
    def key_text(self) -> str:
        return self.pref("messaging_key", "")

    def render(self) -> None:
        sms = model.SMS in self.links
        state = (self.loaded, sms, self.encoder, self.pref("messaging_enabled", False), self.pref("messaging_auto_decrypt", True),
                 tuple(model.compression(self.chains(l)[0]) for l, _n, _t in model.LINKS), self.pref("messaging_stages", "3"))
        if not self.shown or self.key.get_text() == "" and self.key_text:
            self.key.set_text(self.key_text)
            self.shown = True
        self.enabled.set_active(bool(state[3]))
        self.auto.set_active(bool(state[4]))
        for row in (self.enabled, self.auto):
            row.switch.set_sensitive(sms)
        self.auto.set_visible(True)
        self.no_sms.set_visible(self.loaded and not sms)
        if state == self._drawn:
            return
        self._drawn = state
        clear(self.rows)
        for link, label, _text_link in model.LINKS:
            if self.loaded and link not in self.links:
                continue
            mode = model.compression(self.chains(link)[0])
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            name = text(label, "body-medium")
            name.set_hexpand(True)
            line.append(name)
            for key, word in model.MODES:
                chip = self.mode_chip(word, mode == key, lambda _b, l=link, k=key: self.set_mode(l, k), name=f"{label} {word}")
                chip.set_sensitive(self.loaded and (key == "off" or self.encoder or mode == "msvqsc"))
                line.append(chip)
            self.rows.append(line)
        self.no_encoder.set_visible(self.loaded and not self.encoder)
        clear(self.stages_box)
        if any(model.compression(self.chains(l)[0]) == "msvqsc" for l, _n, _t in model.LINKS):
            self.stages_box.append(text(model.STAGES_HINT, "body-small", theme.TEXT_MUTED))
            chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
            current = self.pref("messaging_stages", "3")
            for value in model.STAGES:
                chips.append(self.mode_chip(model.STAGE_LABELS[value], value == current, lambda _b, v=value: self.set_stages(v)))
            self.stages_box.append(chips)

    @staticmethod
    def mode_chip(label: str, selected: bool, on_click, name: str | None = None) -> Gtk.Button:
        """Android's clickable Text chips: teal on a tint when chosen, muted on the surface. A
        button made with a label announces the label whatever its accessible name says, so the
        label is a child and the name ("SMS Off") is set on the button."""
        chip = Gtk.Button()
        chip.set_child(Gtk.Label(label=label))
        name_widget(chip, name or label)
        chip.add_css_class("mode-chip")
        if selected:
            chip.add_css_class("selected")
        chip.connect("clicked", on_click)
        return chip

    # Writes
    def put_chains(self, link: str, egress=None, ingress=None, done=None) -> None:
        body = {}
        if egress is not None:
            body["egress_transforms"] = model.chain_text(egress)
        if ingress is not None:
            body["ingress_transforms"] = model.chain_text(ingress)

        def answered(answer: api.Answer) -> None:
            if answer.ok and isinstance(answer.body, dict):
                self.links[link] = answer.body
                if done:
                    done()
            else:
                errors = (answer.body or {}).get("errors") if isinstance(answer.body, dict) else None
                self.app.toast((errors or [answer.error or "The Bridge did not take the change."])[0])
            self.render()

        self.call(f"/api/interfaces/{link}/transforms", answered, body=body, method="PUT")

    def apply_sms(self, done=None) -> None:
        if model.SMS not in self.links:
            return
        egress, ingress = self.chains(model.SMS)
        out, back = model.sms_chains(egress, ingress, self.pref("messaging_enabled", False), self.pref("messaging_auto_decrypt", True), self.key_text,
                                     model.compression(egress), self.pref("messaging_stages", "3"))
        self.put_chains(model.SMS, out, back, done)

    def set_enabled(self, on: bool) -> None:
        self.app.prefs.set(messaging_enabled=on)
        self.apply_sms()

    def set_auto_decrypt(self, on: bool) -> None:
        self.app.prefs.set(messaging_auto_decrypt=on)
        self.apply_sms()

    def use_key(self, key: str, toast: str) -> None:
        self.key.set_text(key)
        self.app.prefs.set(messaging_key=key)
        self.apply_sms(lambda: self.app.toast(toast))
        if model.SMS not in self.links:
            self.app.toast(toast)

    def generate(self) -> None:
        self.use_key(model.generate_key(), model.KEY_GENERATED)

    def save_key(self) -> None:
        typed = self.key.get_text().strip()
        if not model.valid_key(typed):
            self.app.toast(model.BAD_KEY)
            return
        self.use_key(typed.lower(), model.KEY_SAVED)

    def toggle_show(self) -> None:
        showing = not self.key.get_visibility()
        self.key.set_visibility(showing)
        self.show_button.set_label("Hide" if showing else "Show")

    def copy_key(self) -> None:
        typed = self.key.get_text()
        if typed.strip():
            self.app.window.get_clipboard().set(typed)
            self.app.toast(model.KEY_COPIED)

    def paste_key(self) -> None:
        clipboard = self.app.window.get_clipboard()

        def read(board, result) -> None:
            try:
                clip = (board.read_text_finish(result) or "").strip()
            except GLib.Error:
                clip = ""
            if model.valid_key(clip):
                self.use_key(clip.lower(), model.KEY_PASTED)
            else:
                self.app.toast(model.NOT_A_KEY)

        clipboard.read_text_async(None, read)

    def share_key(self) -> None:
        """Android hands the key to its share sheet; here it is saved where you choose (the
        approved exclusion of the share sheet)."""
        typed = self.key.get_text().strip()
        if typed:
            files.save(self.app, "meshsat-encryption-key.txt", typed + "\n", lambda ok: self.app.toast("Encryption key saved") if ok else None)

    def set_mode(self, link: str, mode: str) -> None:
        egress, _ingress = self.chains(link)
        if mode == model.compression(egress):
            return
        text_link = next(t for l, _n, t in model.LINKS if l == link)
        if link == model.SMS:
            out, back = model.sms_chains(egress, self.chains(link)[1], self.pref("messaging_enabled", False), self.pref("messaging_auto_decrypt", True),
                                         self.key_text, mode, self.pref("messaging_stages", "3"))
            self.put_chains(link, out, back)
        else:
            self.put_chains(link, model.link_chain(egress, mode, self.pref("messaging_stages", "3"), text_link))

    def set_stages(self, value: str) -> None:
        self.app.prefs.set(messaging_stages=value)
        for link, _label, text_link in model.LINKS:
            egress, ingress = self.chains(link)
            if model.compression(egress) != "msvqsc":
                continue
            if link == model.SMS:
                out, back = model.sms_chains(egress, ingress, self.pref("messaging_enabled", False), self.pref("messaging_auto_decrypt", True),
                                             self.key_text, "msvqsc", value)
                self.put_chains(link, out, back)
            else:
                self.put_chains(link, model.link_chain(egress, "msvqsc", value, text_link))
        self.render()

