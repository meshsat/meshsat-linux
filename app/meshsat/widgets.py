# SPDX-License-Identifier: GPL-3.0-or-later
"""The pieces every screen is built from, each the Android counterpart by name and measure
(the iOS app draws the same ones by hand): the status strip, the banners, the wordmark, the
lane rows, cards, NavRows, chips, the bottom navigation, sub-screen headers, buttons."""
import time

import gi

gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

from . import theme  # noqa: E402


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


def icon_button(name: str, on_click, size: int = 24, colour: str | None = None, tooltip: str | None = None) -> Gtk.Button:
    button = Gtk.Button()
    button.add_css_class("icon-button")
    button.set_child(icon(name, size, colour))
    if tooltip:
        button.set_tooltip_text(tooltip)
    button.connect("clicked", lambda *_: on_click())
    return button


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
        for lane, name in (("satellite", "transport-satellite"), ("mesh", "transport-mesh"), ("hub", "outlined-cloud"), ("location", "outlined-my-location")):
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

    def set_lane(self, lane: str, state: str, figure: str = "") -> None:
        """state: working, trying, off, failed."""
        image, label = self.parts[lane]
        colour = {"working": theme.lane_colour(lane), "trying": theme.AMBER, "failed": theme.RED}.get(state, theme.TEXT_MUTED)
        paint(image, colour)
        label.set_text(figure)
        paint(label, colour)


class Banner(Gtk.Button):
    """Full width above the content on every screen. Amber: the node cannot be reached. Red:
    an SOS is on (it outranks the node banner)."""

    def __init__(self, on_tap):
        super().__init__()
        self.add_css_class("banner")
        self.label = text("", "body-large", wrap=True)
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
    """The brand lockup, 26 px high, as the Home header shows it: drawn at exactly that
    size from the shared 600x122 bitmap, sharp on a 2x screen."""

    __gtype_name__ = "MeshSatWordmark"
    HEIGHT = theme.dp(26)

    def __init__(self, path: str):
        super().__init__()
        self.texture = Gdk.Texture.new_from_filename(path)
        self.width = round(self.HEIGHT * self.texture.get_width() / self.texture.get_height())
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.CENTER)

    def do_measure(self, orientation, for_size):
        size = self.width if orientation == Gtk.Orientation.HORIZONTAL else self.HEIGHT
        return size, size, -1, -1

    def do_snapshot(self, snapshot):
        rect = Graphene.Rect.alloc().init(0, 0, self.width, self.HEIGHT)
        snapshot.append_scaled_texture(self.texture, Gsk.ScalingFilter.TRILINEAR, rect)


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
    """The 56 px '<- Title' row of a sub-screen, with a 1 px divider under it."""

    def __init__(self, title: str, on_back, orange: bool = False, subtitle: str | None = None, subtitle_colour: str | None = None, trailing: Gtk.Widget | None = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        self.add_css_class("subheader")
        self.append(icon_button("outlined-arrow-back", on_back, 22, theme.SIGNAL_ORANGE if orange else theme.TEXT_PRIMARY))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(0))
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        texts.append(text(title, "title-large", ellipsize=True))
        if subtitle:
            texts.append(text(subtitle, "body-medium", subtitle_colour or theme.TEXT_SECONDARY))
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
    """Relative time, in the apps' words."""
    if not ts:
        return "never"
    delta = int(time.time() - ts)
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60} min ago"
    if delta < 86400:
        return f"{delta // 3600} h ago"
    return f"{delta // 86400} d ago"
