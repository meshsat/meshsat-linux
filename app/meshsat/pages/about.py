# SPDX-License-Identifier: GPL-3.0-or-later
"""About (ui/screens/AboutScreen.kt:31-133): a centred title, the version in orange, the subtitle,
then the sections Transports, Encryption, Build and License (model/about.py)."""
from gi.repository import Gtk

from .. import __version__ as VERSION
from .. import theme
from ..model import about as model
from ..screen import SubScreen
from ..widgets import Card, text


class AboutScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "About", spacing=12)
        self.route = "about"
        from ..setup import read_provenance  # noqa: PLC0415 - the package's provenance file

        provenance = read_provenance()
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title = text(model.TITLE, "headline-medium", xalign=0.5)
        title.add_css_class("bold")
        head.append(title)
        version = text(model.version_line(VERSION, provenance.get("build")), "body-large", theme.SIGNAL_ORANGE, xalign=0.5)
        version.set_margin_top(theme.dp(4))
        head.append(version)
        subtitle = text(model.SUBTITLE, "body-medium", theme.TEXT_MUTED, xalign=0.5, wrap=True)
        subtitle.set_margin_top(theme.dp(8))
        subtitle.set_margin_bottom(theme.dp(16))
        head.append(subtitle)
        self.column.append(head)
        s = app.state
        pipe = bool((s.ble or {}).get("satellite_owner") not in (None, "")) if s.node_mode() == "bluetooth" else False
        for heading, rows in model.sections(s.node_mode(), provenance, pipe):
            card = Card(spacing=6)
            card.append(text(heading, "title-medium"))
            for label, value in rows:
                card.append(info_item(label, value))
            self.column.append(card)
        lic = Card(spacing=6)
        lic.append(text("License", "title-medium"))
        lic.append(text(model.LICENSE, "body-medium", wrap=True))
        project = text(model.PROJECT, "body-small", theme.TEXT_MUTED, wrap=True)
        project.set_margin_top(theme.dp(4))
        lic.append(project)
        self.column.append(lic)


def info_item(label: str, value: str) -> Gtk.Box:
    """Android's InfoItem: the label left in TextMuted, the value right, both bodySmall."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
    left = text(label, "body-small", theme.TEXT_MUTED)
    left.set_hexpand(True)
    row.append(left)
    right = text(value, "body-small", xalign=1.0, wrap=True)
    row.append(right)
    return row
