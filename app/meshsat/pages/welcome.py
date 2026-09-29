# SPDX-License-Identifier: GPL-3.0-or-later
"""The welcome (ui/screens/Onboarding.kt:64-126): the window's only content at the first start,
before geoclue asks for the phone's position. One scrolling column on the page's background,
24 dp all round and 16 dp apart: the lockup 32 dp high, the headline, the body, "What the app
asks for, and why" with a row per reason, "Continue" full width and 52 dp tall, the footer."""
from gi.repository import Gtk

from .. import theme
from ..model import welcome as model
from ..widgets import Wordmark, filled_button, icon, name_widget, scroller, text


class WelcomeScreen(Gtk.Box):
    def __init__(self, on_continue):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("welcome")
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(16))
        for side in ("start", "end", "top", "bottom"):
            getattr(column, f"set_margin_{side}")(theme.dp(24))
        lockup = Wordmark(height=32)
        lockup.set_halign(Gtk.Align.START)
        name_widget(lockup, model.LOCKUP_NAME)
        column.append(lockup)
        column.append(Gtk.Box(height_request=theme.dp(8)))
        column.append(text(model.HEADLINE, "headline-medium", wrap=True))
        column.append(text(model.BODY, "body-large", theme.TEXT_SECONDARY, wrap=True))
        asks = text(model.ASKS, "title-medium", wrap=True)
        asks.set_margin_top(theme.dp(8))
        column.append(asks)
        for name, title, why in model.REASONS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(16))
            glyph = icon(name, 24, theme.TEXT_SECONDARY)
            glyph.set_valign(Gtk.Align.START)
            row.append(glyph)
            words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            words.append(text(title, "body-large"))
            words.append(text(why, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            row.append(words)
            column.append(row)
        column.append(Gtk.Box(height_request=theme.dp(8)))
        go = filled_button(model.CONTINUE, on_continue)
        go.add_css_class("welcome-continue")
        column.append(go)
        column.append(text(model.FOOTER, "body-small", theme.TEXT_MUTED, wrap=True))
        self.append(scroller(column))
