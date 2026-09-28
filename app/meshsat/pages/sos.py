# SPDX-License-Identifier: GPL-3.0-or-later
"""The SOS result screen (SosScreens.kt SosScreen): where each route of the SOS or the alarm
test stands, what was not used, and Cancel."""
from gi.repository import Gtk

from .. import api, sos, theme
from ..model import sosrun
from ..screen import SubScreen
from ..widgets import Card, clear, confirm, filled_button, icon, text, text_button

ICONS = {sosrun.SENT: ("outlined-done", theme.GREEN), sosrun.SENDING: ("outlined-sync", theme.AMBER), sosrun.WAITING: ("outlined-schedule", theme.AMBER),
         sosrun.STOPPED: ("outlined-block", theme.TEXT_MUTED), sosrun.FAILED: ("outlined-error-outline", theme.RED)}


class SosScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "SOS", spacing=12)
        self.route = "sos"
        self.title_label = text("", "headline-small", wrap=True)
        self.column.append(self.title_label)
        self.started = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.column.append(self.started)
        self.cancelling = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.cancelling.set_visible(False)
        self.column.append(self.cancelling)
        self.routes = Card(padded=False, spacing=0)
        self.column.append(self.routes)
        self.skipped_title = text("Not used", "title-small", theme.TEXT_SECONDARY)
        self.column.append(self.skipped_title)
        self.skipped = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        self.column.append(self.skipped)
        self.cancel = filled_button("Cancel SOS: I am safe", self.cancel_asked)
        self.cancel.remove_css_class("filled")
        self.cancel.add_css_class("outlined")
        self.column.append(self.cancel)
        self.none = text("No SOS has been sent from this phone.", "body-large", wrap=True)
        self.column.append(self.none)
        self.column.append(text_button("Emergency contacts and alarm test", lambda: app.open_route("setup/safety")))
        self._key = None
        self.update(app.state)

    def cancel_asked(self) -> None:
        run = self.app.sos.run
        if run is None:
            return
        if run.test:
            self.app.sos.cancel(self.app.state)
            self.update(self.app.state)
            return
        confirm(self.app, "Cancel the SOS?", "Nothing more goes out, and everyone who got the SOS is told you are safe.", "Cancel SOS",
                lambda: (self.app.sos.cancel(self.app.state), self.update(self.app.state)), cancel="Keep it on")

    def update(self, s: api.State) -> None:
        run = self.app.sos.run
        if run is None:
            for w in (self.title_label, self.started, self.cancelling, self.routes, self.skipped_title, self.skipped, self.cancel):
                w.set_visible(False)
            self.none.set_visible(True)
            return
        self.none.set_visible(False)
        title, tone = sosrun.titles(run)
        self.title_label.set_text(title)
        colour = {"amber": theme.AMBER, "red": theme.RED}.get(tone, theme.TEXT_SECONDARY)
        from ..widgets import paint  # noqa: PLC0415

        paint(self.title_label, colour)
        self.title_label.set_visible(True)
        self.started.set_text(sosrun.started_line(run))
        self.started.set_visible(True)
        if run.cancelled_at is not None and not run.test:
            self.cancelling.set_text(f"Every route that carried the SOS is sending \"{sos.cancel_text(run.name)}\"")
            self.cancelling.set_visible(True)
        else:
            self.cancelling.set_visible(False)
        key = (run.id, tuple((r.key, r.state, r.detail, r.cancel) for r in run.routes), run.cancelled_at, run.finished_at)
        self.cancel.set_visible(run.active)
        self.cancel.set_label("Stop test" if run.test else "Cancel SOS: I am safe")
        if key == self._key:
            return
        self._key = key
        clear(self.routes)
        self.routes.set_visible(True)
        if not run.routes:
            line = text("Nothing could be sent.", "body-medium")
            line.set_margin_start(theme.dp(12))
            line.set_margin_top(theme.dp(12))
            line.set_margin_bottom(theme.dp(12))
            self.routes.append(line)
        show_cancel = run.cancelled_at is not None and not run.test
        for r in run.routes:
            self.routes.append(self.row(r, show_cancel))
        clear(self.skipped)
        self.skipped_title.set_visible(bool(run.skipped))
        self.skipped.set_visible(bool(run.skipped))
        for line in run.skipped:
            self.skipped.append(text(line, "body-small", theme.TEXT_MUTED, wrap=True))

    def row(self, r: sosrun.Route, show_cancel: bool) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        row.set_margin_start(theme.dp(12))
        row.set_margin_end(theme.dp(12))
        row.set_margin_top(theme.dp(10))
        row.set_margin_bottom(theme.dp(10))
        name, colour = ICONS.get(r.state, ICONS[sosrun.FAILED])
        mark = icon(name, 20, colour)
        mark.set_valign(Gtk.Align.START)
        mark.set_margin_top(theme.dp(2))
        row.append(mark)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        texts.append(text(r.label, "body-large", wrap=True))
        texts.append(text(r.detail, "body-small", theme.TEXT_SECONDARY, wrap=True))
        if show_cancel and r.cancel:
            texts.append(text("Cancellation: " + sosrun.cancel_words(r.cancel), "body-small", theme.TEXT_MUTED))
        row.append(texts)
        return row
