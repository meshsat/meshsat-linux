# SPDX-License-Identifier: GPL-3.0-or-later
"""CheckMailboxButton.kt: "Check Mailbox" for the satellite modem, one billed Iridium session
after the person confirmed the cost, and the outcome of the last check under it. The Bridge runs
the check and keeps its outcome (GET /api/iridium/mailbox, Bridge change B22), so Home and the
Satellite page show the same result, as Android's service shares it between them."""
from gi.repository import Gtk

from . import api, theme
from .model import dashboard
from .model import satellite as words
from .widgets import confirm, filled_button, text


class MailboxButton(Gtk.Box):
    """The button full width, "Checking mailbox..." while a check runs, then the outcome in
    bodySmall TextMuted 4 dp under it. `screen` is the Screen it sits on: its fetches are dropped
    once it is gone, and its timers stop with it."""

    POLL_MS = 2000

    def __init__(self, screen):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.screen = screen
        self.connected = False
        self.check = {}  # the Bridge's word: {running, result, finished_at}
        self.button = filled_button(words.CHECK_MAILBOX, self.ask)
        self.button.add_css_class("small-text")
        self.append(self.button)
        self.result = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        self.result.set_margin_top(theme.dp(4))
        self.result.set_visible(False)
        self.append(self.result)
        self.render()

    def set_connected(self, connected: bool) -> None:
        """The modem's state from the poll: the button works only while it is connected."""
        if connected != self.connected:
            self.connected = connected
            self.render()

    def load(self) -> None:
        self.screen.fetch("/api/iridium/mailbox", self.loaded)

    def loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.check = answer.body
            self.render()
            if self.check.get("running"):
                self.screen.after(self.POLL_MS, self.load)

    def ask(self) -> None:
        confirm(self.screen.app, words.CONFIRM_TITLE, words.CONFIRM_TEXT, words.CHECK, self.start, cancel=words.CANCEL)

    def start(self) -> None:
        self.check = {"running": True, "result": None}
        self.render()
        self.screen.call("/api/iridium/mailbox/check", self.started, timeout=20.0)

    def started(self, answer: api.Answer) -> None:
        # 409: a check already runs, which the next read shows; anything else is said once.
        if not answer.ok and answer.status != 409:
            self.screen.app.toast(answer.error or "The Bridge did not answer.")
            self.check = {}
            self.render()
        if self.screen.alive:
            self.load()

    def render(self) -> None:
        running = bool(self.check.get("running"))
        self.button.set_label(words.CHECKING if running else words.CHECK_MAILBOX)
        self.button.set_sensitive(self.connected and not running)
        outcome = None if running else dashboard.mailbox_text(self.check.get("result"))
        self.result.set_text(outcome or "")
        self.result.set_visible(bool(outcome))
