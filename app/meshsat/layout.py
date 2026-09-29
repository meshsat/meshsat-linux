# SPDX-License-Identifier: GPL-3.0-or-later
"""Compose layouts the screens need that widgets.py has no piece for yet: a list's empty state
centred in the room the page's header leaves (Box(Modifier.fillMaxSize() or .weight(1f),
contentAlignment = Alignment.Center)); FlowRow, chips that wrap onto more lines instead of running
off the edge of the screen; a header that stays put over the list that scrolls under it; and the
few looks Android gives one element that the stylesheet has no class for (a label's own colour or
size, a Material glyph in a colour outside theme.py's tokens)."""
import re

from gi.repository import Adw, Gdk, Gtk

from . import theme
from .widgets import name_widget, text


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


def pinned_head(screen, spacing: float = 0, gap: float = 0) -> Gtk.Box:
    """The part of a page that stays put while the list under it scrolls: Android's Column(padding
    16 dp) with the page's header rows first and a LazyColumn(weight 1f) under them, only that list
    scrolling (the Routing rules' intro and tabs, the Links' tabs, the Message queue's counts and
    chips, the Audit log's count, chips and buttons). A box between the '<- Title' row of `screen`
    (a screen.SubScreen) and its scroller, 16 dp in from the sides and the top like the page's
    column, its rows `spacing` dp apart, the scroller's top edge `gap` dp under it (where Android's
    list starts, and where the list slides out of sight). The column in the scroller keeps its
    sides and its bottom; its top margin goes. Fill it with append()."""
    head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(spacing))
    for side in ("start", "end", "top"):
        getattr(head, f"set_margin_{side}")(theme.dp(16))
    head.set_margin_bottom(theme.dp(gap))
    screen.insert_child_after(head, screen.header)
    screen.column.set_margin_top(0)
    return head


def body_text(button: Gtk.Button, style: str = "body-small") -> Gtk.Button:
    """A Button whose Text Android sets in bodySmall (12 sp, the settings pages' Save, Poll Signal,
    Scan for Meshtastic devices...) or bodyMedium (14 sp): the size, and the Regular weight that
    Android's body styles have and the stylesheet's Medium button labels do not (theme.py's
    `button label.body-*` rule). The colours stay the button's own."""
    if style == "body-small":
        button.add_css_class("small-text")
    label = button.get_child()
    if isinstance(label, Gtk.Label):
        label.add_css_class(style)
    return button


def restyle(widget: Gtk.Widget, css: str) -> Gtk.Widget:
    """A look of `widget`'s own that theme.py has no class for, as Android gives it to one element
    (a label's OffWhite that stays when the button is disabled, an outline in Signal Orange or in
    Border): CSS over the stylesheet's rules for it, its states included. `css` is declarations for
    the widget itself ("border-color: #F96118;"), or whole rules in which "&" stands for it
    ("& { ... } &:focus-within { ... }"); "" takes it away again. One provider per widget, replaced
    on each call. Text, borders, backgrounds and sizes only: GTK 4.18 recolours a symbolic icon
    from the stylesheet's classes alone (material_icon draws a glyph in any colour)."""
    name = widget.get_css_name()
    rules = "" if not css else css.replace("&", name) if "{" in css else f"{name} {{ {css} }}"
    provider = getattr(widget, "_own_style", None)
    if provider is None:
        if not rules:
            return widget
        provider = Gtk.CssProvider()
        widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        widget._own_style = provider
    elif getattr(widget, "_own_rules", None) == rules:
        return widget  # a poll that brings the same look reloads nothing
    widget._own_rules = rules
    provider.load_from_string(rules)
    return widget


# Material Icons' filled glyphs that Android draws where the app's icon theme has only the outlined
# ones, as their SVG path data on the 24 dp viewport (androidx.compose.material.icons, the same
# Material Icons, Apache License 2.0, as the icon theme's files).
MATERIAL = {
    "delete": "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",  # Icons.Filled.Delete
    "warning": "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z",  # Icons.Filled.Warning
}
_PATH_TOKEN = re.compile(r"[MmLlHhVvCcZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def path_steps(data: str) -> list:
    """SVG path data with the commands Material's glyphs use (M, L, H, V, C and Z, absolute and
    relative, a command's numbers repeated for more segments) as absolute steps: ("move", x, y),
    ("line", x, y), ("curve", x1, y1, x2, y2, x, y), ("close",)."""
    tokens = _PATH_TOKEN.findall(data)
    steps, at, command = [], 0, ""
    x = y = start_x = start_y = 0.0

    def numbers(n: int) -> list:
        nonlocal at
        values = [float(v) for v in tokens[at:at + n]]
        at += n
        return values

    while at < len(tokens):
        if tokens[at].isalpha():
            command = tokens[at]
            at += 1
            if command in "Zz":
                steps.append(("close",))
                x, y = start_x, start_y
            continue
        if command in ("", "Z", "z"):
            at += 1  # a number with no command to take it: not in Material's data
            continue
        relative, kind = command.islower(), command.upper()
        if kind in "ML":
            dx, dy = numbers(2)
            x, y = (x + dx, y + dy) if relative else (dx, dy)
            if kind == "M":
                start_x, start_y = x, y
                steps.append(("move", x, y))
                command = "l" if relative else "L"  # more pairs after a move are lines
            else:
                steps.append(("line", x, y))
        elif kind == "H":
            (value,) = numbers(1)
            x = x + value if relative else value
            steps.append(("line", x, y))
        elif kind == "V":
            (value,) = numbers(1)
            y = y + value if relative else value
            steps.append(("line", x, y))
        elif kind == "C":
            v = numbers(6)
            if relative:
                v = [v[i] + (x if i % 2 == 0 else y) for i in range(6)]
            x, y = v[4], v[5]
            steps.append(("curve", *v))
    return steps


def material_icon(name: str, size: int = 24, colour: str = theme.TEXT_PRIMARY) -> Gtk.DrawingArea:
    """A filled Material glyph of MATERIAL, `size` dp, in any colour: Android's Icon(tint = ...)
    where the tint is none of theme.py's tokens (the certificates' Color(0xFFE57373)), which a
    symbolic icon of the icon theme cannot take. Drawn on the glyph's own 24 dp viewport."""
    steps = path_steps(MATERIAL[name])
    rgba = Gdk.RGBA()
    rgba.parse(colour)
    area = Gtk.DrawingArea(accessible_role=Gtk.AccessibleRole.PRESENTATION)
    area.set_content_width(theme.dp(size))
    area.set_content_height(theme.dp(size))
    area.set_halign(Gtk.Align.CENTER)
    area.set_valign(Gtk.Align.CENTER)

    def draw(_area, cr, width: int, height: int) -> None:
        cr.scale(width / 24.0, height / 24.0)
        for step in steps:
            if step[0] == "move":
                cr.move_to(*step[1:])
            elif step[0] == "line":
                cr.line_to(*step[1:])
            elif step[0] == "curve":
                cr.curve_to(*step[1:])
            else:
                cr.close_path()
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.fill()

    area.set_draw_func(draw)
    return area


def material_icon_button(name: str, on_click, size: int = 24, colour: str = theme.TEXT_PRIMARY, tooltip: str | None = None) -> Gtk.Button:
    """widgets.icon_button with a MATERIAL glyph: Android's IconButton around a filled Icon. The
    tooltip is its accessible name, as there."""
    button = Gtk.Button()
    button.add_css_class("icon-button")
    button.set_child(material_icon(name, size, colour))
    if tooltip:
        button.set_tooltip_text(tooltip)
        name_widget(button, tooltip)
    button.connect("clicked", lambda *_: on_click())
    return button
