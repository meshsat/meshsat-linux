# SPDX-License-Identifier: GPL-3.0-or-later
"""The pieces every screen is built from, each the Android counterpart by name and measure
(the iOS app draws the same ones by hand): the status strip, the banners, the wordmark, the
lane rows, cards, NavRows, chips, the bottom navigation, sub-screen headers, buttons."""
import os
import time

import gi

gi.require_version("Graphene", "1.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Graphene, Gtk, Pango, PangoCairo  # noqa: E402

from . import theme  # noqa: E402
from .model import words  # noqa: E402

BRAND_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brand", "app-icon-1024.png")


def paint(widget: Gtk.Widget, colour: str, background: bool = False) -> Gtk.Widget:
    """One widget in one token colour, as a CSS class (.fg-x for icons and text, .bg-x for
    dots and lines); the previous colour class goes."""
    prefix = "bg-" if background else "fg-"
    slug = theme.class_of(colour)
    for c in widget.get_css_classes():
        if c.startswith(prefix):
            widget.remove_css_class(c)
    if slug:
        widget.add_css_class(prefix + slug)
    else:  # a colour outside the token table: a private provider (text only)
        provider = Gtk.CssProvider()
        provider.load_from_string(f"* {{ {'background-color' if background else 'color'}: {colour}; }}")
        widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    return widget


def icon(name: str, size: int = 24, colour: str | None = None) -> Gtk.Image:
    image = Gtk.Image.new_from_icon_name(f"meshsat-{name}-symbolic")
    image.set_pixel_size(theme.dp(size))
    if colour:
        paint(image, colour)
    return image


def text(value: str, style: str | list = "body-medium", colour: str | None = None, xalign: float = 0.0,
         wrap: bool = False, ellipsize: bool = False, mono: bool = False) -> Gtk.Label:
    out = Gtk.Label(label=value, xalign=xalign)
    for c in ([style] if isinstance(style, str) else style):
        out.add_css_class(c)
    if mono:
        out.add_css_class("mono")
    if colour:
        paint(out, colour)
    if wrap:
        out.set_wrap(True)
        out.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if ellipsize:
        out.set_ellipsize(Pango.EllipsizeMode.END)
    return out


def spacer() -> Gtk.Box:
    box = Gtk.Box()
    box.set_hexpand(True)
    return box


def filled_button(label_text: str, on_click=None, expand: bool = True) -> Gtk.Button:
    button = Gtk.Button(label=label_text)
    button.add_css_class("filled")
    button.set_hexpand(expand)
    if on_click:
        button.connect("clicked", lambda *_: on_click())
    return button


def outlined_button(label_text: str, on_click=None) -> Gtk.Button:
    button = Gtk.Button(label=label_text)
    button.add_css_class("outlined")
    if on_click:
        button.connect("clicked", lambda *_: on_click())
    return button


def text_button(label_text: str, on_click=None) -> Gtk.Button:
    button = Gtk.Button(label=label_text)
    button.add_css_class("textbutton")
    if on_click:
        button.connect("clicked", lambda *_: on_click())
    return button


def icon_button(name: str, on_click, size: int = 24, colour: str | None = None, tooltip: str | None = None, small: bool = False) -> Gtk.Button:
    """An icon-only button. `tooltip` is also its accessible name (Android's contentDescription):
    it is how a screen reader and the tests find it, so every one has it. `small`: Android's
    20 dp IconButton with a 12 dp icon (the copy button inside a bubble)."""
    button = Gtk.Button()
    button.add_css_class("icon-button")
    if small:
        button.add_css_class("small")
    button.set_child(icon(name, size, colour))
    if tooltip:
        button.set_tooltip_text(tooltip)
        name_widget(button, tooltip)
    button.connect("clicked", lambda *_: on_click())
    return button


def name_widget(widget: Gtk.Widget, name: str, description: str | None = None) -> Gtk.Widget:
    """The accessible name (and description) of a widget, as Android's contentDescription."""
    widget.update_property([Gtk.AccessibleProperty.LABEL], [name])
    if description:
        widget.update_property([Gtk.AccessibleProperty.DESCRIPTION], [description])
    return widget


class Card(Gtk.Box):
    """Surface, a 1 px border, radius 8, no shadow; 12 px inside."""

    def __init__(self, padded: bool = True, spacing: int = 8):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(spacing))
        self.add_css_class("card")
        if padded:
            self.add_css_class("card-pad")


class StatusStrip(Gtk.Box):
    """36 px on Surface: 16 px icons 14 px apart, satellite with its bars and mesh with its
    node count only while connected, the cloud for the Hub, my_location for GPS, and the UTC
    clock in Mono on the right. Each icon in its lane's colour when working, amber while
    trying, muted when off, red when failed."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(14))
        self.add_css_class("strip")
        self.parts = {}
        for lane, name in (("satellite", "transport-satellite"), ("mesh", "transport-mesh"), ("sms", "outlined-sms"), ("hub", "outlined-cloud"), ("location", "outlined-my-location")):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
            box.set_valign(Gtk.Align.CENTER)
            image = icon(name, 16, theme.TEXT_MUTED)
            figure = text("", "label-medium", mono=True)
            box.append(image)
            box.append(figure)
            self.parts[lane] = (image, figure)
            self.append(box)
        self.append(spacer())
        self.clock = text("", "label-medium", xalign=1.0, mono=True)
        self.clock.set_valign(Gtk.Align.CENTER)
        self.append(self.clock)
        self.tick()
        GLib.timeout_add_seconds(15, self.tick)

    def tick(self) -> bool:
        self.clock.set_text(time.strftime("%H:%M UTC", time.gmtime()))
        return True

    def set_lane(self, lane: str, state: str, figure: str = "", description: str | None = None) -> None:
        """state: working, trying, off, failed. `description` is what a screen reader says for
        the item (MeshSatUI.kt's StripItem descriptions)."""
        image, label = self.parts[lane]
        colour = {"working": theme.lane_colour(lane), "trying": theme.AMBER, "failed": theme.RED}.get(state, theme.TEXT_MUTED)
        paint(image, colour)
        label.set_text(figure)
        paint(label, colour)
        name_widget(image, description or {"satellite": "Satellite", "mesh": "Mesh", "sms": "SMS", "hub": "Hub", "location": "Location"}[lane])


class Banner(Gtk.Button):
    """Full width above the content on every screen, bodyMedium in SpaceBlack, 16 x 10 dp
    (NodeLinkBanner.kt, SosBanner). Amber: the node cannot be reached. Red: an SOS is on (it
    outranks the node banner)."""

    def __init__(self, on_tap):
        super().__init__()
        self.add_css_class("banner")
        self.label = text("", "body-medium", wrap=True)
        self.set_child(self.label)
        self.connect("clicked", lambda *_: on_tap(self.kind))
        self.kind = None
        self.set_visible(False)

    def show(self, kind: str | None, message: str = "") -> None:
        self.kind = kind
        if kind is None:
            self.set_visible(False)
            return
        if kind == "sos":
            self.add_css_class("sos")
        else:
            self.remove_css_class("sos")
        self.label.set_text(message)
        self.set_visible(True)


class Filtered(Gtk.Widget):
    """One widget drawn through a colour matrix, the way Android draws a view through a
    ColorMatrixColorFilter: the same 4 x 5 rows (offsets in 0..255), handed to GTK's colour
    matrix node. Night mode and the map's dark tiles are both this."""

    __gtype_name__ = "MeshSatFiltered"

    def __init__(self, child: Gtk.Widget, rows=None):
        super().__init__()
        self.set_layout_manager(Gtk.BinLayout())
        self.child = child
        child.set_parent(self)
        self.matrix = None
        self.offset = None
        self.on = rows is not None
        if rows is not None:
            self.set_matrix(rows)

    def set_matrix(self, rows) -> None:
        # Android: out_i = sum_j rows[i][j] * in_j + rows[i][4]. GTK: out = in (a row vector) x M +
        # offset, so M[j][i] = rows[i][j]; row-major, the input channel picks the row.
        values = [0.0] * 16
        for i in range(4):
            for j in range(4):
                values[j * 4 + i] = rows[i * 5 + j]
        self.matrix = Graphene.Matrix.alloc().init_from_float(values)
        self.offset = Graphene.Vec4.alloc().init(*(rows[i * 5 + 4] / 255.0 for i in range(4)))

    def do_snapshot(self, snapshot):
        if self.on and self.matrix is not None:
            snapshot.push_color_matrix(self.matrix, self.offset)
            self.snapshot_child(self.child, snapshot)
            snapshot.pop()
        else:
            self.snapshot_child(self.child, snapshot)


class Wordmark(Gtk.Widget):
    """The brand lockup, 26 dp high as the Home header shows it (32 dp on the welcome screen,
    Onboarding.kt:80-86). The apps' lockup bitmap is
    600x122 and looked soft on a 2x screen, so this draws it itself: the mark cut from the
    1024 px app icon, scaled once to the screen's exact pixels (the icon's black is the
    page's black), and the name set live in IBM Plex Sans Bold, "Mesh" in off-white and
    "Sat" in orange, at the lockup's proportions (cap height 0.55 of the mark's height)."""

    __gtype_name__ = "MeshSatWordmark"
    HEIGHT = theme.dp(26)
    MARK_BOX = (179, 319, 665, 385)  # x, y, w, h of the mark inside app-icon-1024.png
    GAP = 0.18  # of the height, between the mark and the name
    FONT_SIZE = 0.79  # of the height: IBM Plex Sans' cap height is 0.698 em
    TRACKING = -0.03  # of the height, between letters
    BASELINE = 0.91  # of the height

    def __init__(self, icon_path: str | None = None, height: float = 26):
        super().__init__()
        self.icon_path = icon_path or BRAND_ICON
        self.HEIGHT = theme.dp(height)
        self.mark_width = round(self.HEIGHT * self.MARK_BOX[2] / self.MARK_BOX[3])
        self.texture = None
        self.texture_scale = 0
        self.layouts = []
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.CENTER)

    def name_layout(self):
        """One layout for the whole name, so the letters keep their kerning across the colour
        change: "Mesh" in the base colour, "Sat" in orange by a foreground attribute."""
        if not self.layouts:
            size = self.HEIGHT * self.FONT_SIZE
            layout = self.create_pango_layout("MeshSat")
            layout.set_font_description(Pango.FontDescription.from_string(f"IBM Plex Sans Bold {size:.1f}px"))
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(self.TRACKING * self.HEIGHT * Pango.SCALE)))
            orange = Gdk.RGBA()
            orange.parse(theme.SIGNAL_ORANGE)
            colour = Pango.attr_foreground_new(int(orange.red * 65535), int(orange.green * 65535), int(orange.blue * 65535))
            colour.start_index, colour.end_index = len("Mesh"), len("MeshSat")
            attrs.insert(colour)
            layout.set_attributes(attrs)
            self.layouts.append(layout)
        return self.layouts[0]

    def name_width(self) -> int:
        return self.name_layout().get_pixel_size()[0]

    def mark_texture(self):
        scale = max(1, self.get_scale_factor())
        if self.texture is None or self.texture_scale != scale:
            x, y, w, h = self.MARK_BOX
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_path).new_subpixbuf(x, y, w, h)
            pixbuf = pixbuf.scale_simple(self.mark_width * scale, self.HEIGHT * scale, GdkPixbuf.InterpType.HYPER)
            self.texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            self.texture_scale = scale
        return self.texture

    def do_measure(self, orientation, for_size):
        size = self.mark_width + round(self.GAP * self.HEIGHT) + self.name_width() if orientation == Gtk.Orientation.HORIZONTAL else self.HEIGHT
        return size, size, -1, -1

    def do_snapshot(self, snapshot):
        snapshot.append_texture(self.mark_texture(), Graphene.Rect.alloc().init(0, 0, self.mark_width, self.HEIGHT))
        layout = self.name_layout()
        base = Gdk.RGBA()
        base.parse(theme.OFF_WHITE)
        snapshot.save()
        snapshot.translate(Graphene.Point.alloc().init(self.mark_width + round(self.GAP * self.HEIGHT), self.BASELINE * self.HEIGHT - layout.get_baseline() / Pango.SCALE))
        snapshot.append_layout(layout, base)
        snapshot.restore()


class LaneRow(Gtk.Button):
    """A Home lane: the transport's icon, its name, a detail line, a Mono figure at the
    right, a chevron, and the line underneath: solid when working, dashed 10/7 while trying,
    dotted grey when off, dotted red when failed. A message on its way is an orange dot
    travelling along the line every 2.4 s."""

    ICONS = {"satellite": "transport-satellite", "mesh": "transport-mesh", "hub": "outlined-cloud", "sms": "outlined-sms"}

    def __init__(self, lane: str, title: str, on_tap):
        super().__init__()
        self.lane = lane
        self.add_css_class("flat")
        self.connect("clicked", lambda *_: on_tap())
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        outer.add_css_class("lane-row")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        self.icon = icon(self.ICONS[lane], 24, theme.TEXT_MUTED)
        self.icon.set_valign(Gtk.Align.CENTER)
        row.append(self.icon)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        top.append(text(title, "title-medium"))
        top.append(spacer())
        self.figure = text("", "label-large", theme.lane_colour(lane), xalign=1.0, mono=True)
        top.append(self.figure)
        texts.append(top)
        self.detail = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        texts.append(self.detail)
        row.append(texts)
        chevron = icon("outlined-chevron-right", 24, theme.TEXT_MUTED)
        chevron.set_valign(Gtk.Align.CENTER)
        row.append(chevron)
        outer.append(row)
        self.line = Gtk.DrawingArea()
        self.line.set_content_height(theme.dp(6))
        self.line.set_margin_start(theme.dp(36))
        self.line.set_margin_top(theme.dp(8))
        self.line.set_draw_func(self.draw_line)
        outer.append(self.line)
        self.set_child(outer)
        self.state = "off"
        self.in_flight = False
        self._phase = 0.0
        self._timer = None

    def set_state(self, state: str, detail: str, figure: str = "", in_flight: bool = False) -> None:
        self.state = state
        self.detail.set_text(detail)
        # LaneLine's description (Lane.kt:133-138), for a screen reader
        described = {"working": "working", "trying": "trying", "off": "not available", "failed": "not working"}.get(state, state)
        self.update_property([Gtk.AccessibleProperty.DESCRIPTION], [described + (", a message is on its way" if in_flight else "")])
        self.figure.set_text(figure)
        paint(self.icon, {"working": theme.lane_colour(self.lane), "trying": theme.AMBER, "failed": theme.RED}.get(state, theme.TEXT_MUTED))
        self.in_flight = in_flight
        if in_flight and self._timer is None:
            self._timer = GLib.timeout_add(40, self._advance)
        elif not in_flight and self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self.line.queue_draw()

    def _advance(self) -> bool:
        self._phase = (self._phase + 0.04 / 2.4) % 1.0
        self.line.queue_draw()
        return True

    def draw_line(self, area, cr, width, height):
        rgba = Gdk.RGBA()
        rgba.parse({"working": theme.lane_colour(self.lane), "trying": theme.lane_colour(self.lane), "failed": theme.RED}.get(self.state, theme.TEXT_MUTED))
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1.0)
        cr.set_line_width(2)
        y = height / 2
        if self.state == "trying":
            cr.set_dash([10, 7])
        elif self.state in ("off", "failed"):
            cr.set_dash([2, 4])
        cr.move_to(0, y)
        cr.line_to(width, y)
        cr.stroke()
        if self.in_flight:
            dot = Gdk.RGBA()
            dot.parse(theme.SIGNAL_ORANGE)
            cr.set_source_rgba(dot.red, dot.green, dot.blue, 1.0)
            cr.arc(self._phase * width, y, 3, 0, 6.2832)
            cr.fill()


class NavRow(Gtk.Button):
    """A Setup row: a 24 px tinted icon, titleMedium, an 8 px dot with a detail line, a muted chevron; at least 64 px."""

    def __init__(self, icon_name: str, title: str, on_tap, tint: str | None = None):
        super().__init__()
        self.add_css_class("flat")
        self.connect("clicked", lambda *_: on_tap())
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(16))
        row.add_css_class("nav-row")
        self.icon = icon(icon_name, 24, tint or theme.TEXT_PRIMARY)
        self.icon.set_valign(Gtk.Align.CENTER)
        row.append(self.icon)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text(title, "title-medium"))
        detail = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.dot = Gtk.Box()
        self.dot.add_css_class("dot")
        self.dot.set_valign(Gtk.Align.CENTER)
        self.dot.set_visible(False)
        detail.append(self.dot)
        self.detail = text("", "body-medium", theme.TEXT_SECONDARY, wrap=True)
        detail.append(self.detail)
        texts.append(detail)
        row.append(texts)
        chevron = icon("outlined-chevron-right", 24, theme.TEXT_MUTED)
        chevron.set_valign(Gtk.Align.CENTER)
        row.append(chevron)
        self.set_child(row)

    def set_detail(self, value: str, dot: str | None = None) -> None:
        self.detail.set_text(value)
        for c in ("dot-green", "dot-amber", "dot-red", "dot-muted"):
            self.dot.remove_css_class(c)
        if dot:
            self.dot.add_css_class(f"dot-{dot}")
            self.dot.set_visible(True)
        else:
            self.dot.set_visible(False)


class Chip(Gtk.Button):
    def __init__(self, label_text: str, on_tap=None, selected: bool = False):
        super().__init__(label=label_text)
        self.add_css_class("chip")
        self.set_selected(selected)
        if on_tap:
            self.connect("clicked", lambda *_: on_tap(self))

    def set_selected(self, on: bool) -> None:
        (self.add_css_class if on else self.remove_css_class)("selected")


class Tag(Gtk.Label):
    def __init__(self, lane: str):
        super().__init__(label={"mesh": "Mesh", "satellite": "Satellite", "hub": "Hub", "sms": "SMS"}.get(lane, lane))
        self.add_css_class("tag")
        self.add_css_class(f"tag-{lane}")
        self.set_valign(Gtk.Align.CENTER)


class NavBar(Gtk.Box):
    """The Material 3 navigation bar both apps draw: 80 px on Surface, five equal items, the
    selected one with a 64x32 pill in SurfaceLight, its icon filled instead of outlined, its
    label in OffWhite."""

    TABS = (("home", "Home", "home"), ("messages", "Messages", "chat-bubble"), ("map", "Map", "map"), ("people", "People", "group"), ("setup", "Setup", "tune"))

    def __init__(self, on_select):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True)
        self.add_css_class("nav")
        self.items = {}
        for key, label_text, name in self.TABS:
            button = Gtk.Button()
            button.add_css_class("flat")
            button.add_css_class("nav-item")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
            pill = Gtk.Box()
            pill.add_css_class("nav-pill")
            pill.set_halign(Gtk.Align.CENTER)
            outlined = icon(f"outlined-{name}" if name != "chat-bubble" else "outlined-chat-bubble-outline", 24)
            filled = icon(f"filled-{name}", 24)
            outlined.add_css_class("nav-icon")
            filled.add_css_class("nav-icon")
            filled.set_visible(False)
            for image in (outlined, filled):
                image.set_valign(Gtk.Align.CENTER)
                image.set_halign(Gtk.Align.CENTER)
                image.set_hexpand(True)
                pill.append(image)
            box.append(pill)
            box.append(text(label_text, "nav-label", xalign=0.5))
            button.set_child(box)
            button.connect("clicked", lambda _b, k=key: on_select(k))
            self.items[key] = (button, outlined, filled)
            self.append(button)

    def set_active(self, key: str) -> None:
        for k, (button, outlined, filled) in self.items.items():
            active = k == key
            (button.add_css_class if active else button.remove_css_class)("active")
            outlined.set_visible(not active)
            filled.set_visible(active)


class SubHeader(Gtk.Box):
    """The 56 px '<- Title' row of a sub-screen, with a 1 px divider under it. `plain`: the
    chat's own header (ConversationChatView), inside the screen's 16 dp padding, 8 dp above the
    messages, no divider, the subtitle in bodySmall."""

    def __init__(self, title: str, on_back, orange: bool = False, subtitle: str | None = None, subtitle_colour: str | None = None, trailing: Gtk.Widget | None = None,
                 plain: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        self.add_css_class("subheader")
        if plain:
            self.add_css_class("plain")
            for side in ("start", "end", "top"):
                getattr(self, f"set_margin_{side}")(theme.dp(16))
            self.set_margin_bottom(theme.dp(8))
        self.append(icon_button("outlined-arrow-back", on_back, 24 if plain else 22, theme.SIGNAL_ORANGE if orange else theme.TEXT_PRIMARY, tooltip="Back"))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text(title, "title-large", ellipsize=True))
        if subtitle:
            texts.append(text(subtitle, "body-small" if plain else "body-medium", subtitle_colour or theme.TEXT_SECONDARY))
        self.append(texts)
        if trailing:
            self.append(trailing)


class KeyValue(Gtk.Box):
    def __init__(self, key: str, value: str, value_colour: str | None = None, mono: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        self.set_margin_top(theme.dp(4))
        self.set_margin_bottom(theme.dp(4))
        self.append(text(key, "kv-key"))
        self.value = text(value, "kv-value", value_colour, xalign=1.0, ellipsize=True, mono=mono)
        self.value.set_hexpand(True)
        self.append(self.value)


def group_title(value: str) -> Gtk.Label:
    return text(value, "group-title")


def scroller(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    window = Gtk.ScrolledWindow()
    window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    window.set_vexpand(True)
    window.set_child(child)
    return window


def hscroll(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    """A row (chips, sort keys) that slides sideways when the screen is too narrow for it,
    and never widens the screen: no scrollbar, a finger does it."""
    window = Gtk.ScrolledWindow()
    window.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
    window.set_child(child)
    return window


def page(spacing: int = 12, padded: bool = True) -> Gtk.Box:
    """A screen's column: 16 dp screen padding, 12 dp between items."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(spacing))
    if padded:
        box.set_margin_start(theme.dp(16))
        box.set_margin_end(theme.dp(16))
        box.set_margin_top(theme.dp(16))
        box.set_margin_bottom(theme.dp(16))
    return box


def clear(box: Gtk.Box) -> None:
    while child := box.get_first_child():
        box.remove(child)


def when(ts) -> str:
    return time.strftime("%H:%M", time.localtime(ts)) if ts else ""


def when_date(ts) -> str:
    return time.strftime("%m/%d %H:%M", time.localtime(ts)) if ts else ""


def ago(ts) -> str:
    """Relative time, in the apps' words (Words.ago)."""
    return words.ago(ts or 0)


# The building blocks the settings screens are made of, each after its Android counterpart.


class Field(Gtk.Box):
    """A text field as Android's OutlinedTextField: the label above, the entry, a helper or an
    error line under it, and a counter when there is a limit. The entry's accessible name is
    the label."""

    def __init__(self, label: str, placeholder: str = "", helper: str = "", max_length: int = 0, purpose=None, mono: bool = False, on_change=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.label_text = label
        self.max_length = max_length
        self.label = text(label, "label-medium", theme.TEXT_SECONDARY)
        self.append(self.label)
        self.entry = Gtk.Entry(placeholder_text=placeholder)
        self.entry.add_css_class("field")
        if mono:
            self.entry.add_css_class("mono")
        if purpose is not None:
            self.entry.set_input_purpose(purpose)
        if max_length:
            self.entry.set_max_length(max_length)
        name_widget(self.entry, label)
        self.append(self.entry)
        under = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.helper_text = helper
        self.helper = text(helper, "body-small", theme.TEXT_SECONDARY, wrap=True)
        self.helper.set_hexpand(True)
        self.helper.set_visible(bool(helper))
        under.append(self.helper)
        self.counter = text("", "body-small", theme.TEXT_SECONDARY, xalign=1.0, mono=True)
        self.counter.set_visible(bool(max_length))
        under.append(self.counter)
        self.append(under)
        self.entry.connect("changed", self._changed)
        self.on_change = on_change
        self._changed(self.entry)

    def _changed(self, entry) -> None:
        if self.max_length:
            self.counter.set_text(f"{len(entry.get_text())}/{self.max_length}")
        if self.on_change is not None:
            self.on_change(entry.get_text())

    @property
    def text(self) -> str:
        return self.entry.get_text()

    def set_text(self, value: str) -> None:
        if self.entry.get_text() != (value or ""):
            self.entry.set_text(value or "")

    def set_error(self, message: str | None) -> None:
        """An error line in red under the field, or the helper back."""
        if message:
            self.helper.set_text(message)
            paint(self.helper, theme.RED)
            self.helper.set_visible(True)
            self.entry.add_css_class("error")
        else:
            self.helper.set_text(self.helper_text)
            paint(self.helper, theme.TEXT_SECONDARY)
            self.helper.set_visible(bool(self.helper_text))
            self.entry.remove_css_class("error")

    def set_helper(self, message: str) -> None:
        self.helper_text = message
        self.set_error(None)


class SwitchRow(Gtk.Box):
    """A row with a title, an optional detail line and a switch at the right. `set_active`
    moves the switch without telling the handler (a poll never counts as the user's hand)."""

    def __init__(self, title: str, on_change, detail: str = "", active: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        self.add_css_class("switch-row")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text(title, "body-large"))
        self.detail = text(detail, "body-medium", theme.TEXT_SECONDARY, wrap=True)
        self.detail.set_visible(bool(detail))
        texts.append(self.detail)
        self.append(texts)
        self.switch = Gtk.Switch(active=active)
        self.switch.set_valign(Gtk.Align.CENTER)
        name_widget(self.switch, title)
        self.append(self.switch)
        self._quiet = False
        self.on_change = on_change
        self.switch.connect("state-set", self._state_set)

    def _state_set(self, switch, state) -> bool:
        if not self._quiet and self.on_change is not None:
            self.on_change(bool(state))
        return False

    @property
    def active(self) -> bool:
        return self.switch.get_active()

    def set_active(self, value: bool) -> None:
        if self.switch.get_active() == bool(value):
            return
        self._quiet = True
        try:
            self.switch.set_active(bool(value))
        finally:
            self._quiet = False

    def set_detail(self, value: str) -> None:
        self.detail.set_text(value)
        self.detail.set_visible(bool(value))


class CheckRow(Gtk.ToggleButton):
    """A row with a check box and a title, as Android's Checkbox rows: one button, so a finger
    or a screen reader toggles it anywhere on the row."""

    def __init__(self, title: str, on_change=None, active: bool = False, detail: str = "", dot: str | None = None, style: str = "body-large"):
        """`dot`: a 10 dp dot in that colour between the box and the title (the map's layer rows);
        an empty title leaves the box alone (a node row's own check box)."""
        super().__init__(active=active)
        self.add_css_class("flat")
        self.add_css_class("check-row")
        if title:
            name_widget(self, title)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        self.box = Gtk.Box()
        self.box.add_css_class("check")
        self.box.set_valign(Gtk.Align.CENTER)
        self.mark = icon("outlined-done", 14, theme.SPACE_BLACK)
        self.mark.set_halign(Gtk.Align.CENTER)
        self.mark.set_valign(Gtk.Align.CENTER)
        self.box.append(self.mark)
        row.append(self.box)
        if dot:
            spot = Gtk.Box()
            spot.add_css_class("layer-dot")
            paint(spot, dot, background=True)
            spot.set_valign(Gtk.Align.CENTER)
            row.append(spot)
        if title or detail:
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
            texts.set_hexpand(True)
            texts.set_valign(Gtk.Align.CENTER)
            texts.append(text(title, style))
            if detail:
                texts.append(text(detail, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            row.append(texts)
        self.set_child(row)
        self._quiet = False
        self.on_change = on_change
        self._paint()
        self.connect("toggled", self._toggled)

    def _paint(self) -> None:
        (self.box.add_css_class if self.get_active() else self.box.remove_css_class)("on")
        self.mark.set_visible(self.get_active())

    def _toggled(self, *_) -> None:
        self._paint()
        if not self._quiet and self.on_change is not None:
            self.on_change(self.get_active())

    def set_checked(self, value: bool) -> None:
        if self.get_active() == bool(value):
            return
        self._quiet = True
        try:
            self.set_active(bool(value))
        finally:
            self._quiet = False


class SliderRow(Gtk.Box):
    """A title, the value in Mono at the right, and a slider under them."""

    def __init__(self, title: str, low: float, high: float, step: float, on_change, fmt=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        top.append(text(title, "body-large"))
        top.append(spacer())
        self.value_label = text("", "body-medium", theme.TEXT_SECONDARY, xalign=1.0, mono=True)
        top.append(self.value_label)
        self.append(top)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        name_widget(self.scale, title)
        self.append(self.scale)
        self.fmt = fmt or (lambda v: f"{v:g}")
        self._quiet = False
        self.on_change = on_change
        self.scale.connect("value-changed", self._changed)
        self._changed(self.scale)

    def _changed(self, scale) -> None:
        self.value_label.set_text(self.fmt(scale.get_value()))
        if not self._quiet and self.on_change is not None:
            self.on_change(scale.get_value())

    @property
    def value(self) -> float:
        return self.scale.get_value()

    def set_value(self, value: float) -> None:
        self._quiet = True
        try:
            self.scale.set_value(value)
        finally:
            self._quiet = False


class Sheet:
    """A bottom sheet or dialog on the window, as Android's ModalBottomSheet and AlertDialog:
    a title, a body to fill, and a row of text buttons. `present()` shows it."""

    def __init__(self, app, title: str, width: int = 360):
        self.app = app
        self.dialog = Adw.Dialog(title=title, content_width=width)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.box.add_css_class("sheet")
        self.box.append(text(title, "dialog-title", wrap=True))
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.box.append(self.body)
        self.buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.buttons.set_halign(Gtk.Align.END)
        self.box.append(self.buttons)
        self.dialog.set_child(self.box)

    def button(self, label: str, on_click, kind: str = "text") -> Gtk.Button:
        maker = {"text": text_button, "filled": filled_button, "outlined": outlined_button}[kind]
        button = maker(label, on_click) if kind != "filled" else filled_button(label, on_click, expand=False)
        self.buttons.append(button)
        return button

    def present(self) -> None:
        self.dialog.present(self.app.window)

    def close(self) -> None:
        self.dialog.close()


def confirm(app, title: str, body: str, ok: str, on_ok, cancel: str = "Cancel", danger: bool = False, on_cancel=None) -> Adw.AlertDialog:
    """A question with two answers, as Android's AlertDialog. Its buttons carry their words,
    so a screen reader and the tests answer it by name."""
    dialog = Adw.AlertDialog(heading=title, body=body)
    dialog.add_response("cancel", cancel)
    dialog.add_response("ok", ok)
    if danger:
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    def answered(d, response) -> None:
        if response == "ok":
            on_ok()
        elif on_cancel is not None:
            on_cancel()

    dialog.connect("response", answered)
    dialog.present(app.window)
    return dialog


class PickerDialog(Sheet):
    """One choice out of a list, as Android's radio-button dialogs: each option a row with its
    title and a detail line; the chosen one marked. Picking a row answers and closes."""

    def __init__(self, app, title: str, options: list, chosen, on_pick, cancel: str = "Cancel"):
        super().__init__(app, title, width=340)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        for key, name, detail in options:
            # The row's accessible name is its title and its detail together (GTK reads the
            # labels inside), so a screen reader hears both and a test can tell "Satellite"
            # here from a chip of the same name elsewhere.
            row = Gtk.Button()
            row.add_css_class("flat")
            row.add_css_class("pick-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
            radio = Gtk.Box()
            radio.add_css_class("radio")
            if key == chosen:
                radio.add_css_class("on")
            radio.set_valign(Gtk.Align.CENTER)
            inner.append(radio)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
            texts.set_hexpand(True)
            texts.append(text(name, "title-medium", ellipsize=True))
            if detail:
                texts.append(text(detail, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            inner.append(texts)
            row.set_child(inner)
            row.connect("clicked", lambda _b, k=key: (self.close(), on_pick(k)))
            rows.append(row)
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=theme.dp(420), hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(rows)
        self.body.append(scroll)
        self.button(cancel, self.close)


class HoldButton(Gtk.Button):
    """Android's HoldToSend: a 64 dp bar that fills while the finger stays on it and fires
    after `seconds`; a short tap shows how long to hold; a screen reader's or a test's
    activation (no press at all) goes to `on_activate`, which asks in a dialog instead."""

    def __init__(self, label: str, on_fire, on_activate, seconds: float = 3.0, danger: bool = True):
        super().__init__()
        self.add_css_class("hold")
        if danger:
            self.add_css_class("danger")
        self.label_text = label
        self.on_fire, self.on_activate = on_fire, on_activate
        self.seconds = seconds
        self.progress = 0.0
        self._started = 0.0
        self._timer = None
        self._fired = False
        self._pressed = False
        name_widget(self, label)
        self.area = Gtk.DrawingArea()
        self.area.set_content_height(theme.dp(64))
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)
        press = Gtk.GestureClick()
        press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        press.connect("pressed", self._pressed_at)
        press.connect("released", self._released)
        press.connect("cancel", lambda *_: self._released(None, 0, 0, 0))
        self.add_controller(press)
        self.connect("clicked", self._clicked)

    def set_label_text(self, label: str) -> None:
        self.label_text = label
        name_widget(self, label)
        self.area.queue_draw()

    def _pressed_at(self, gesture, n, x, y):
        self._pressed = True
        self._fired = False
        self._started = time.monotonic()
        self.progress = 0.0
        if self._timer is None:
            self._timer = GLib.timeout_add(40, self._tick)

    def _tick(self) -> bool:
        if not self._pressed:
            self._timer = None
            return False
        self.progress = min(1.0, (time.monotonic() - self._started) / self.seconds)
        self.area.queue_draw()
        if self.progress >= 1.0:
            self._fired = True
            self._pressed = False
            self._timer = None
            self.progress = 0.0
            self.area.queue_draw()
            self.on_fire()
            return False
        return True

    def _released(self, gesture, n, x, y):
        self._pressed = False
        self.progress = 0.0
        self.area.queue_draw()

    def _clicked(self, *_):
        if self._fired:
            self._fired = False  # the hold's own release: already sent
            return
        if self._started and time.monotonic() - self._started < self.seconds and time.monotonic() - self._started > 0.05:
            self.on_activate("tap")  # a short tap by a finger
            return
        self.on_activate("accessible")  # no press at all: a screen reader or a test

    def _draw(self, area, cr, width, height):
        colour = Gdk.RGBA()
        colour.parse(theme.RED if self.has_css_class("danger") else theme.SIGNAL_ORANGE)
        cr.set_source_rgba(colour.red, colour.green, colour.blue, 0.10)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        if self.progress > 0:
            cr.set_source_rgba(colour.red, colour.green, colour.blue, 0.55)
            cr.rectangle(0, 0, width * self.progress, height)
            cr.fill()
        # HoldToSend.kt: "Keep holding: N" while held (N the whole seconds left), in titleMedium
        layout = self.create_pango_layout(self.label_text if not self._pressed else f"Keep holding: {max(1, int(self.seconds - (time.monotonic() - self._started) + 0.999))}")
        layout.set_font_description(Pango.FontDescription.from_string(f"{theme.FONT} Medium {theme.px(16)}"))
        w, h = layout.get_pixel_size()
        cr.set_source_rgba(colour.red, colour.green, colour.blue, 1.0)
        cr.move_to((width - w) / 2, (height - h) / 2)
        PangoCairo.show_layout(cr, layout)


class Tabs(Gtk.Box):
    """A row of tabs as Android's ScrollableTabRow: chips that slide sideways, one selected,
    each with a count badge when it has one."""

    def __init__(self, names: list, on_select, selected: str | None = None, plain: bool = False):
        """`plain`: Android's own tab row (InterfacesScreen, RulesScreen): text on nothing,
        the selected one on SurfaceLight, 48 dp tall, 4 dp apart."""
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4 if plain else 8))
        self.chips = {}
        self.badges = {}
        self.on_select = on_select
        self.selected = selected or names[0]
        for name in names:
            chip = Gtk.Button()
            chip.add_css_class("tab-chip" if plain else "chip")
            name_widget(chip, name)
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
            inner.append(text(name, "label-large"))
            badge = text("", "count")
            badge.set_visible(False)
            inner.append(badge)
            chip.set_child(inner)
            chip.connect("clicked", lambda _b, n=name: self.select(n))
            self.chips[name] = chip
            self.badges[name] = badge
            self.append(chip)
        self._paint()

    def _paint(self) -> None:
        for name, chip in self.chips.items():
            (chip.add_css_class if name == self.selected else chip.remove_css_class)("selected")

    def select(self, name: str) -> None:
        if name == self.selected:
            return
        self.selected = name
        self._paint()
        self.on_select(name)

    def set_badge(self, name: str, count: int) -> None:
        badge = self.badges[name]
        badge.set_text(str(count))
        badge.set_visible(count > 0)


def dot(lane: str, size: int = 10) -> Gtk.Box:
    """A round dot in a lane's colour, as Android's Box(size).background(color, CircleShape)."""
    box = Gtk.Box()
    box.add_css_class("lane-dot")
    box.set_size_request(theme.dp(size), theme.dp(size))
    box.set_valign(Gtk.Align.CENTER)
    paint(box, theme.lane_colour(lane), background=True)
    return box


def tone_colour(tone: str) -> str:
    return {"green": theme.GREEN, "amber": theme.AMBER, "red": theme.RED, "teal": theme.SIGNAL_ORANGE, "primary": theme.TEXT_PRIMARY, "secondary": theme.TEXT_SECONDARY,
            "blue": theme.BLUE}.get(tone, theme.TEXT_MUTED)


def state_tag(value: str, tone: str, style: str = "label-large") -> Gtk.Label:
    """A word in its tone on a tinted pill, as Android's state labels (a 12 % tint of the
    colour behind the text)."""
    label = text(value, style, tone_colour(tone))
    label.add_css_class("state-tag")
    label.add_css_class(f"tint-{tone if tone in ('green', 'amber', 'red', 'teal') else 'muted'}")
    label.set_valign(Gtk.Align.CENTER)
    return label


def divider() -> Gtk.Box:
    line = Gtk.Box()
    line.add_css_class("divider")
    return line


def fact_row(label: str, value: str, colour: str | None = None, mono: bool = False) -> Gtk.Box:
    """A label at the left, its value at the right, as Android's DeliveryFact."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
    row.append(text(label, "body-small", theme.TEXT_MUTED))
    value_label = text(value, "body-small", colour, xalign=1.0, wrap=True, mono=mono)
    value_label.set_hexpand(True)
    value_label.set_justify(Gtk.Justification.RIGHT)
    row.append(value_label)
    return row


class PickerField(Gtk.Box):
    """A choice out of a list as Android's DropdownField (an ExposedDropdownMenu on an
    OutlinedTextField): the label above, the chosen option's name with a chevron, a helper or
    an error under it; a tap opens a PickerDialog. The button's accessible name is the label."""

    def __init__(self, app, label: str, options: list, chosen, on_pick, helper: str = ""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.app = app
        self.label_text = label
        self.options = list(options)  # (key, name, detail)
        self.chosen = chosen
        self.on_pick = on_pick
        self.append(text(label, "label-medium", theme.TEXT_SECONDARY))
        self.button = Gtk.Button()
        self.button.add_css_class("picker")
        name_widget(self.button, label)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.value = text("", "body-large", ellipsize=True)
        self.value.set_hexpand(True)
        inner.append(self.value)
        inner.append(icon("outlined-expand-more", 24, theme.TEXT_SECONDARY))
        self.button.set_child(inner)
        self.button.connect("clicked", lambda *_: self.open())
        self.append(self.button)
        self.helper_text = helper
        self.helper = text(helper, "body-small", theme.TEXT_SECONDARY, wrap=True)
        self.helper.set_visible(bool(helper))
        self.append(self.helper)
        self._show()

    def _show(self) -> None:
        name = next((n for k, n, _d in self.options if k == self.chosen), str(self.chosen))
        self.value.set_text(name)

    def set_options(self, options: list, chosen=None) -> None:
        self.options = list(options)
        if chosen is not None:
            self.chosen = chosen
        self._show()

    def set_chosen(self, key) -> None:
        self.chosen = key
        self._show()

    def set_helper(self, message: str) -> None:
        self.helper_text = message
        self.set_error(None)

    def set_error(self, message: str | None) -> None:
        if message:
            self.helper.set_text(message)
            paint(self.helper, theme.RED)
            self.helper.set_visible(True)
            self.button.add_css_class("error")
        else:
            self.helper.set_text(self.helper_text)
            paint(self.helper, theme.TEXT_SECONDARY)
            self.helper.set_visible(bool(self.helper_text))
            self.button.remove_css_class("error")

    def open(self) -> None:
        def picked(key) -> None:
            self.chosen = key
            self._show()
            self.on_pick(key)

        PickerDialog(self.app, self.label_text, self.options, self.chosen, picked).present()


class Fab(Gtk.Button):
    """Android's FloatingActionButton: a 56 dp orange disc at the bottom right with an icon,
    named for a screen reader and the tests."""

    def __init__(self, icon_name: str, name: str, on_click):
        super().__init__()
        self.add_css_class("fab")
        self.set_child(icon(icon_name, 24, theme.ON_PRIMARY))
        name_widget(self, name)
        self.set_tooltip_text(name)
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.END)
        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(theme.dp(16))
        self.connect("clicked", lambda *_: on_click())


class StatusBanner(Gtk.Box):
    """A line of state inside a page: amber while trying, red when failed, green when done."""

    def __init__(self, message: str = "", tone: str = "amber"):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        self.add_css_class("status-banner")
        self.label = text(message, "body-medium", wrap=True)
        self.label.set_hexpand(True)
        self.append(self.label)
        self.set_tone(tone)
        self.set_visible(bool(message))

    def set_tone(self, tone: str) -> None:
        for c in ("amber", "red", "green", "muted"):
            self.remove_css_class(c)
        self.add_css_class(tone)

    def show(self, message: str | None, tone: str = "amber") -> None:
        if not message:
            self.set_visible(False)
            return
        self.label.set_text(message)
        self.set_tone(tone)
        self.set_visible(True)
