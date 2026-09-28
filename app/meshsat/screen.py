# SPDX-License-Identifier: GPL-3.0-or-later
"""A screen with a life of its own: it loads when it comes on view, its timers stop when it
goes, and an answer from the Bridge that arrives after it is gone is dropped. Every tab and
every page is one of these; the app calls `update(state)` on the one on view at each poll."""
from gi.repository import GLib, Gtk

from . import api
from .widgets import SubHeader, page, scroller


class Screen(Gtk.Box):
    def __init__(self, app, orientation=Gtk.Orientation.VERTICAL):
        super().__init__(orientation=orientation)
        self.app = app
        self.alive = False
        self._timers = set()
        self.connect("map", self._mapped)
        self.connect("unmap", self._unmapped)

    # Life
    def _mapped(self, *_):
        self.alive = True
        self.on_show()

    def _unmapped(self, *_):
        self.alive = False
        for source in list(self._timers):
            GLib.source_remove(source)
        self._timers.clear()
        self.on_hide()

    def on_show(self) -> None:
        """Called each time the screen comes on view (the tab chosen, the page pushed, a page
        above it popped)."""

    def on_hide(self) -> None:
        """Called each time the screen goes out of view; its timers are already stopped."""

    def update(self, s: api.State) -> None:
        """The state after a poll, while on view."""

    # Timers that live as long as the screen is on view
    def after(self, ms: int, fn) -> None:
        source = None

        def fire() -> bool:
            self._timers.discard(source)
            if self.alive:
                fn()
            return False

        source = GLib.timeout_add(ms, fire)
        self._timers.add(source)

    def every(self, seconds: int, fn) -> None:
        """`fn` now and every `seconds` while on view (a page's own refresh, on Android's period)."""
        def tick() -> bool:
            if not self.alive:
                return False
            fn()
            return True

        fn()
        self._timers.add(GLib.timeout_add_seconds(seconds, tick))

    # The Bridge, off the main loop; the answer comes on it, and only while on view
    def fetch(self, path: str, on_done, method: str = "GET", body: dict | None = None, timeout: float = 8.0) -> None:
        def done(answer: api.Answer) -> bool:
            if self.alive:
                on_done(answer)
            return False

        api.fetch(path, done, method=method, body=body, timeout=timeout)

    def call(self, path: str, on_done, body: dict | None = None, method: str = "POST", timeout: float = 8.0) -> None:
        """A write: `on_done(answer)` when it is over, whether the screen is still on view or
        not (a toast about a save must not be lost to a back press)."""
        api.fetch(path, lambda answer: on_done(answer) or False, method=method, body=body, timeout=timeout)


class SubScreen(Screen):
    """A page below a tab: the '<- Title' row and a column of cards 16 px apart."""

    def __init__(self, app, title: str, spacing: int = 16, padded: bool = True):
        super().__init__(app)
        self.title = title
        self.header = SubHeader(title, app.pop)
        self.append(self.header)
        self.column = page(spacing=spacing, padded=padded)
        self.append(scroller(self.column))

    def card(self, title: str | None = None):
        from .widgets import Card, text  # noqa: PLC0415

        card = Card(spacing=8)
        if title:
            card.append(text(title, "title-medium"))
        self.column.append(card)
        return card
