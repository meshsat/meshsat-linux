# SPDX-License-Identifier: GPL-3.0-or-later
"""Two Compose layouts the screens need that widgets.py has no piece for yet: a list's empty
state centred in the room the page's header leaves (Box(Modifier.fillMaxSize() or .weight(1f),
contentAlignment = Alignment.Center)), and FlowRow, chips that wrap onto more lines instead of
running off the edge of the screen."""
from gi.repository import Adw, Gtk

from . import theme
from .widgets import text


def centred(widget: Gtk.Widget, top: int = 0) -> Gtk.Widget:
    """`widget` in the middle of the free space under the page's header, across and down.

    GTK gives a box's spare height to the children that expand, and a box expands as soon as one
    of its children does: the height the rows above leave reaches `widget` through every box
    between it and the page's scroller, whose viewport already makes the page's column at least
    as tall as the screen. CENTER then puts it in the middle of that room. `top` is the Box's
    padding(top = N.dp), in pixels (theme.dp): the middle of what is left under it."""
    widget.set_vexpand(True)
    widget.set_valign(Gtk.Align.CENTER)
    widget.set_margin_top(top)
    widget.set_margin_bottom(0)
    return widget


def empty_text(value: str = "", style: str = "body-medium", colour: str = theme.TEXT_MUTED, top: int = 0) -> Gtk.Label:
    """A list's empty text: Android's Text(textAlign = TextAlign.Center) in the centred Box,
    wrapping when it is longer than the screen is wide."""
    label = text(value, style, colour, xalign=0.5, wrap=True)
    label.set_justify(Gtk.Justification.CENTER)
    return centred(label, top)


def flow_row(spacing: float = 6, line_spacing: float = 16) -> Gtk.Widget:
    """FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) of Material chips: each chip at
    its own width, as many on a line as fit, the next one on the line below, none cut off.
    Material keeps a 48 dp touch height round a 32 dp chip, so the lines of a FlowRow of chips
    stand 16 dp apart (48 dp from line to line on the Audit log's capture). `spacing` and
    `line_spacing` in dp. Children go in with append() and out with widgets.clear().

    Adw.WrapBox (libadwaita 1.7; the phone has 1.7.6) lays its children out as FlowRow does, like
    the words of a wrapped line. Before 1.7: a Gtk.FlowBox, which wraps as well but lines its
    children up in columns (theme.py's `.legend flowboxchild` takes the padding off its cells)."""
    if hasattr(Adw, "WrapBox"):
        return Adw.WrapBox(child_spacing=theme.dp(spacing), line_spacing=theme.dp(line_spacing))
    box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False, max_children_per_line=64,
                      column_spacing=theme.dp(spacing), row_spacing=theme.dp(line_spacing))
    box.add_css_class("legend")
    return box
