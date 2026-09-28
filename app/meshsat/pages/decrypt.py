# SPDX-License-Identifier: GPL-3.0-or-later
"""Encrypt or decrypt text (ui/screens/DecryptScreen.kt): AES-256-GCM by hand, with the key the
Bridge's links encrypt with, for checking what a kit, the Hub or another phone sent."""
from gi.repository import Gtk

from .. import api, theme
from ..model import crypto
from ..screen import SubScreen
from ..widgets import Card, filled_button, name_widget, text


class DecryptScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Encrypt or decrypt text", spacing=12)
        self.route = "decrypt"
        self.key = ""
        self.last = ""
        self.warning = text(crypto.NO_KEY, "body-medium", theme.AMBER, wrap=True)
        self.column.append(self.warning)
        field = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        field.append(text("Input text", "body-small", theme.TEXT_SECONDARY))
        self.input = Gtk.TextView()
        self.input.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.input.add_css_class("field")
        self.input.add_css_class("multiline")
        self.input.add_css_class("mono")
        name_widget(self.input, "Input text")
        self.input.get_buffer().connect("changed", lambda *_: self.show_error(""))
        field.append(self.input)
        self.column.append(field)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8), homogeneous=True)
        self.encrypt_button = filled_button("Encrypt", self.encrypt)
        self.decrypt_button = filled_button("Decrypt", self.decrypt)
        self.decrypt_button.add_css_class("amber-fill")
        paste = filled_button("Paste", self.paste)
        paste.add_css_class("tonal-surface")
        for button in (self.encrypt_button, self.decrypt_button, paste):
            buttons.append(button)
        self.column.append(buttons)
        self.error = text("", "body-medium", theme.RED, wrap=True)
        self.error.set_visible(False)
        self.column.append(self.error)
        self.output = Card(spacing=8)
        self.output_title = text("", "title-medium")
        self.output_text = text("", "label-medium", wrap=True)
        self.output_text.set_selectable(True)
        copy = filled_button("Copy", self.copy, expand=False)
        copy.set_halign(Gtk.Align.START)
        self.output.append(self.output_title)
        self.output.append(self.output_text)
        self.output.append(copy)
        self.output.set_visible(False)
        self.column.append(self.output)
        self.column.append(text(crypto.HELP, "body-small", theme.TEXT_MUTED, wrap=True))
        self.set_key("")

    def on_show(self) -> None:
        self.fetch("/api/interfaces", self.got_links)

    def got_links(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, list):
            self.set_key(crypto.key_from_links(answer.body))

    def set_key(self, key: str) -> None:
        self.key = key
        self.warning.set_visible(not key)
        self.encrypt_button.set_sensitive(bool(key))
        self.decrypt_button.set_sensitive(bool(key))

    def value(self) -> str:
        buffer = self.input.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

    def show_error(self, message: str) -> None:
        self.error.set_text(message)
        self.error.set_visible(bool(message))

    def show_output(self, value: str, encrypted: bool) -> None:
        self.last = value
        self.output_title.set_text("Encrypted (base64):" if encrypted else "Decrypted:")
        from ..widgets import paint  # noqa: PLC0415

        paint(self.output_title, theme.SIGNAL_ORANGE if encrypted else theme.GREEN)
        self.output_text.set_text(value)
        self.output.set_visible(bool(value))

    def encrypt(self) -> None:
        if not self.key:
            self.show_error("No key configured")
            return
        try:
            self.show_output(crypto.encrypt_to_base64(self.value(), self.key), True)
            self.show_error("")
        except crypto.CryptoError as error:
            self.show_error(f"Encrypt failed: {error}")
            self.show_output("", True)

    def decrypt(self) -> None:
        if not self.key:
            self.show_error("No key configured")
            return
        try:
            self.show_output(crypto.decrypt_from_base64(self.value().strip(), self.key), False)
            self.show_error("")
        except crypto.CryptoError as error:
            self.show_error(f"Decrypt failed: {error}")
            self.show_output("", False)

    def paste(self) -> None:
        clipboard = self.app.window.get_clipboard()

        def read(cb, result) -> None:
            try:
                value = cb.read_text_finish(result)
            except Exception:  # noqa: BLE001 -- nothing to paste
                value = None
            if value:
                self.input.get_buffer().set_text(value)
                self.app.toast("Pasted from clipboard")

        clipboard.read_text_async(None, read)

    def copy(self) -> None:
        if self.last:
            self.app.window.get_clipboard().set(self.last)
            self.app.toast("Copied to clipboard")

