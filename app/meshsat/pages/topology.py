# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh topology (ui/screens/TopologyScreen.kt): the mesh as it was heard, drawn as a graph that
lays itself out (pinch to zoom, drag to move, "Reset view"), above the figures, the notices,
"Who hears whom", "Nodes" and the legend."""
import time

from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from .. import api, theme
from ..model import topology as model
from ..screen import SubScreen
from ..widgets import Card, clear, text, text_button, tone_colour


def _rgba(colour: str, alpha: float = 1.0) -> tuple:
    c = Gdk.RGBA()
    c.parse(colour)
    return c.red, c.green, c.blue, alpha


class Graph(Gtk.Overlay):
    """The canvas: nodes and the links that were heard, laid out by forces in 90 steps."""

    def __init__(self):
        super().__init__()
        self.add_css_class("card")
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self.draw)
        self.area.set_hexpand(True)
        self.set_child(self.area)
        self.reset = text_button(model.RESET, self.reset_view)
        self.reset.set_halign(Gtk.Align.END)
        self.reset.set_valign(Gtk.Align.START)
        self.reset.set_visible(False)
        self.add_overlay(self.reset)
        self.topology = {"nodes": [], "links": [], "hearings": []}
        self.positions, self.edges, self.ids = [], [], ()
        self.scale, self.dx, self.dy = 1.0, 0.0, 0.0
        self._step, self._timer = 0, None
        self._zoom_from, self._drag_from = 1.0, (0.0, 0.0)
        zoom = Gtk.GestureZoom()
        zoom.connect("begin", lambda g, s: setattr(self, "_zoom_from", self.scale))
        zoom.connect("scale-changed", self._zoomed)
        self.area.add_controller(zoom)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", lambda g, x, y: setattr(self, "_drag_from", (self.dx, self.dy)))
        drag.connect("drag-update", self._dragged)
        self.area.add_controller(drag)

    def set_topology(self, topology: dict) -> None:
        self.topology = topology
        ids = tuple(n["num"] for n in topology["nodes"])
        edges = model.edges_of(topology)
        if ids != self.ids or edges != self.edges:
            # A new node set restarts the layout (a stable order: the layout does not restart
            # when only the names or the times change).
            if ids != self.ids:
                self.positions = model.start_positions(len(ids))
            self.ids, self.edges = ids, edges
            self._step = 0
            if self._timer is None:
                self._timer = GLib.timeout_add(16, self._advance)
        self.area.queue_draw()

    def stop(self) -> None:
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _advance(self) -> bool:
        if self._step >= model.STEPS:
            self._timer = None
            return False
        model.simulate(self.positions, self.edges, model.temperature(self._step))
        self._step += 1
        self.area.queue_draw()
        return True

    def _zoomed(self, gesture, scale) -> None:
        self.scale = min(max(self._zoom_from * scale, 0.5), 4.0)
        self._moved()

    def _dragged(self, gesture, x, y) -> None:
        self.dx, self.dy = self._drag_from[0] + x, self._drag_from[1] + y
        self._moved()

    def _moved(self) -> None:
        self.reset.set_visible(self.scale != 1.0 or self.dx != 0.0 or self.dy != 0.0)
        self.area.queue_draw()

    def reset_view(self) -> None:
        self.scale, self.dx, self.dy = 1.0, 0.0, 0.0
        self._moved()

    def draw(self, area, cr, width, height) -> None:
        nodes = self.topology["nodes"]
        if not self.positions or len(self.positions) != len(nodes):
            return
        fit, mid_x, mid_y = model.fit(self.positions, width, height, theme.dp(36))

        def screen(i: int) -> tuple:
            return (width / 2 + self.dx + (self.positions[i][0] - mid_x) * fit * self.scale,
                    height / 2 + self.dy + (self.positions[i][1] - mid_y) * fit * self.scale)

        for i, j, fresh in self.edges:
            cr.set_source_rgba(*(_rgba(theme.MESH) if fresh else _rgba(theme.TEXT_MUTED, 0.6)))
            cr.set_line_width(theme.dp(2) if fresh else theme.dp(1.5))
            cr.set_dash([] if fresh else [theme.dp(4), theme.dp(4)])
            cr.move_to(*screen(i))
            cr.line_to(*screen(j))
            cr.stroke()
        cr.set_dash([])
        now = time.time()
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription.from_string(f"{theme.FONT} {theme.px(12)}"))
        for i, node in enumerate(nodes):
            x, y = screen(i)
            radius = theme.dp(9) if node["is_me"] else theme.dp(6)
            if node["is_me"]:
                cr.set_source_rgba(*_rgba(theme.MESH))
                cr.arc(x, y, radius + theme.dp(3), 0, 6.2832)
                cr.fill()
            colour = theme.TEXT_PRIMARY if node["is_me"] else (theme.GREEN if model.is_fresh(node["last_seen"], now) else theme.TEXT_MUTED)
            cr.set_source_rgba(*_rgba(colour))
            cr.arc(x, y, radius, 0, 6.2832)
            cr.fill()
            layout.set_text(node["label"], -1)
            w, _h = layout.get_pixel_size()
            cr.set_source_rgba(*_rgba(theme.TEXT_PRIMARY if node["is_me"] else theme.TEXT_SECONDARY))
            cr.move_to(x - w / 2, y + radius + theme.dp(4))
            PangoCairo.show_layout(cr, layout)


class TopologyScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Mesh topology", spacing=12)
        self.route = "topology"
        self.nodes, self.neighbors = [], {}
        self._key = None
        # The graph sits above the list, never inside a scroll, so pinch and drag reach it.
        scroll = self.get_last_child()
        self.graph = Graph()
        self.graph.set_margin_start(theme.dp(16))
        self.graph.set_margin_end(theme.dp(16))
        self.graph.set_margin_top(theme.dp(12))
        self.graph.set_size_request(-1, theme.dp(260))
        self.insert_child_after(self.graph, self.header)
        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.empty.set_valign(Gtk.Align.CENTER)
        self.empty.set_vexpand(True)
        self.empty.set_margin_start(theme.dp(32))
        self.empty.set_margin_end(theme.dp(32))
        self.empty_title = text("", "title-medium", xalign=0.5, wrap=True)
        self.empty_title.set_justify(Gtk.Justification.CENTER)
        self.empty_text = text("", "body-medium", theme.TEXT_SECONDARY, xalign=0.5, wrap=True)
        self.empty_text.set_justify(Gtk.Justification.CENTER)
        self.empty.append(self.empty_title)
        self.empty.append(self.empty_text)
        self.insert_child_after(self.empty, scroll)
        self.scroll = scroll

    def on_show(self) -> None:
        self.every(10, self.load)
        self.every(30, self.render)  # freshness moves with the clock, not only with new packets

    def on_hide(self) -> None:
        self.graph.stop()

    def load(self) -> None:
        self.fetch("/api/nodes", self.got_nodes)
        self.fetch("/api/neighbors", self.got_neighbors)

    def got_nodes(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.nodes = answer.body.get("nodes") or []
            self.render()

    def got_neighbors(self, answer: api.Answer) -> None:
        if answer.ok:
            self.neighbors = answer.body or {}
            self.render()

    def update(self, s: api.State) -> None:
        self.render()

    def render(self) -> None:
        s = self.app.state
        now = time.time()
        me = (s.bridge or {}).get("node_id")
        topology = model.build(self.nodes, me, self.neighbors, now)
        connected = s.mesh_connected()
        empty = model.empty(topology)
        self.graph.set_visible(not empty)
        self.scroll.set_visible(not empty)
        self.empty.set_visible(empty)
        if empty:
            title, detail = model.EMPTY_CONNECTED if connected else model.EMPTY_DISCONNECTED
            self.empty_title.set_text(title)
            self.empty_text.set_text(detail)
            return
        self.graph.set_topology(topology)
        key = (int(now // 30), connected, repr([(n["num"], n["name"], n["last_seen"]) for n in topology["nodes"]]), repr(topology["hearings"]), topology["reports"])
        if key == self._key:
            return
        self._key = key
        clear(self.column)
        self.column.append(text(model.HINT, "body-small", theme.TEXT_MUTED))
        stats = Card(padded=False, spacing=0)
        stats.add_css_class("stats-card")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12), homogeneous=True)
        for label, value in model.stats(topology, now):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
            column.append(text(label, "body-small", theme.TEXT_MUTED, wrap=True))
            column.append(text(value, "title-small", mono=True))
            row.append(column)
        stats.append(row)
        self.column.append(stats)
        notices = []
        if not topology["reports"]:
            notices.append(model.NO_REPORTS)
        if not connected:
            notices.append(model.NOT_CONNECTED)
        for notice in notices:
            card = Card()
            card.append(text(notice, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            self.column.append(card)
        hearings = model.hearing_lines(topology, now)
        if hearings:
            self.column.append(self.section("Who hears whom"))
            for line, detail, fresh in hearings:
                self.column.append(self.hearing_row(line, detail, fresh))
        self.column.append(self.section("Nodes"))
        for row_data in model.node_rows(topology, now):
            self.column.append(self.node_row(row_data))
        self.column.append(self.legend())

    @staticmethod
    def section(title: str) -> Gtk.Label:
        label = text(title, "title-small", theme.TEXT_SECONDARY)
        label.set_margin_top(theme.dp(4))
        return label

    @staticmethod
    def sample(fresh: bool) -> Gtk.DrawingArea:
        area = Gtk.DrawingArea()
        area.set_content_width(theme.dp(24))
        area.set_content_height(theme.dp(12))
        area.set_valign(Gtk.Align.CENTER)

        def draw(_a, cr, width, height):
            cr.set_source_rgba(*(_rgba(theme.MESH) if fresh else _rgba(theme.TEXT_MUTED, 0.6)))
            cr.set_line_width(theme.dp(2))
            cr.set_dash([] if fresh else [theme.dp(4), theme.dp(4)])
            cr.move_to(0, height / 2)
            cr.line_to(width, height / 2)
            cr.stroke()

        area.set_draw_func(draw)
        return area

    def hearing_row(self, line: str, detail: str, fresh: bool) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        row.set_size_request(-1, theme.dp(48))
        row.append(self.sample(fresh))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        texts.set_valign(Gtk.Align.CENTER)
        texts.set_hexpand(True)
        texts.append(text(line, "body-medium", theme.TEXT_PRIMARY if fresh else theme.TEXT_SECONDARY, wrap=True))
        texts.append(text(detail, "body-small", theme.TEXT_MUTED))
        row.append(texts)
        return row

    @staticmethod
    def node_row(data: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        row.set_size_request(-1, theme.dp(48))
        dot = Gtk.Box()
        dot.add_css_class("lane-dot")
        dot.set_size_request(theme.dp(10), theme.dp(10))
        dot.set_valign(Gtk.Align.START)
        dot.set_margin_top(theme.dp(6))
        from ..widgets import paint  # noqa: PLC0415

        paint(dot, tone_colour(data["tone"]), background=True)
        row.append(dot)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        texts.set_hexpand(True)
        texts.append(text(data["title"], "body-medium", ellipsize=True))
        texts.append(text(data["id_line"], "body-small", theme.TEXT_MUTED, ellipsize=True, mono=True))
        if data["detail"]:
            texts.append(text(data["detail"], "body-small", theme.TEXT_SECONDARY, wrap=True))
        row.append(texts)
        if data["ago"]:
            row.append(text(data["ago"], "body-small", tone_colour(data["tone"] if data["tone"] == "green" else "muted")))
        return row

    def legend(self) -> Card:
        card = Card(spacing=8)
        from ..widgets import paint  # noqa: PLC0415

        for kind, label, tone in model.legend():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            if kind == "dot":
                dot = Gtk.Box()
                dot.add_css_class("lane-dot")
                dot.set_size_request(theme.dp(10), theme.dp(10))
                dot.set_margin_start(theme.dp(7))
                dot.set_margin_end(theme.dp(7))
                dot.set_valign(Gtk.Align.CENTER)
                paint(dot, tone_colour(tone), background=True)
                row.append(dot)
            else:
                row.append(self.sample(tone == "fresh"))
            row.append(text(label, "body-small", theme.TEXT_SECONDARY))
            card.append(row)
        card.append(text(model.LEGEND_NOTE, "body-small", theme.TEXT_MUTED, wrap=True))
        return card
