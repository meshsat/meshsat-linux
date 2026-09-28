# SPDX-License-Identifier: GPL-3.0-or-later
"""Satellite passes, as ui/screens/PassPredictorScreen.kt and ui/components/SkyChart.kt: the
pass overhead or the next one, the window, the chart of passes against the modem's signal,
the surroundings, every pass in the window, and the bookkeeping last. The predictions come
from the Bridge (its TLE set and predictor, the same as the Bridge's own passes page) for the
phone's position: geoclue's fix, else the node's, else the position typed in here."""
import datetime
import math
import threading
import time

from gi.repository import Gdk, GLib, Gtk

from . import api, theme
from .widgets import Card, SubHeader, clear, filled_button, page, scroller, spacer, text, text_button

# Elevation environment presets, the Bridge's and Android's
ELEV_PRESETS = ((5, "Open", "Open field or rooftop"), (20, "Trees", "Some trees or low buildings"), (40, "City", "Tall buildings, narrow streets"), (60, "Canyon", "Deep valley or dense city"))
WINDOW_OPTIONS = (6, 12, 24, 48)  # 72 h is gone: on a phone its passes are hairlines (MESHSAT-1300)

# SkyChart.kt's colours
INDIGO = "#818CF8"
INDIGO_ACTIVE = "#A5B4FC"
SIGNAL_GREEN = "#10B981"
NOW_AMBER = "#F59E0B"
SESSION_OK = "#E879F9"
SESSION_FAIL = "#F87171"
GRID = "#374151"
LABEL = "#6B7280"
TIP_BG = "#1F2937"
TIP_FG = "#D1D5DB"


def rgba(colour: str, alpha: float = 1.0):
    c = Gdk.RGBA()
    c.parse(colour)
    return c.red, c.green, c.blue, alpha


def hhmm(ts) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%H:%M")


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def date_short(ts) -> str:
    """dd MMM in English, as the apps print it whatever the phone's locale."""
    d = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    return f"{d.day:02d} {MONTHS[d.month - 1]}"


def duration_text(minutes: float) -> str:
    m = round(minutes)
    return f"{m // 60}h{m % 60}m" if m >= 60 else f"{m}m"


def countdown_text(seconds: int) -> str:
    if seconds <= 0:
        return "00:00"
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def cache_age_text(sec) -> str:
    if sec is None or sec < 0:
        return "No data"
    if sec < 3600:
        return f"{sec // 60}m old"
    if sec < 86400:
        return f"{sec // 3600}h old"
    return f"{sec // 86400}d old"


def elevation_colour(elev: float) -> str:
    if elev >= 60:
        return theme.IRIDIUM
    if elev >= 30:
        return theme.GREEN
    if elev >= 15:
        return theme.AMBER
    return theme.TEXT_MUTED


def signal_colour(bars: float) -> str:
    """Green from 3 bars, amber at 1 and 2, red at 0: the Bridge's thresholds."""
    b = round(bars)
    return SIGNAL_GREEN if b >= 3 else NOW_AMBER if b >= 1 else "#EF4444"


def averaged(signals, step: int):
    """Readings averaged into steps, one point per step at its middle (SkyGeometry.averaged)."""
    if step <= 60:
        return sorted((s["at"], float(s["bars"])) for s in signals)
    buckets = {}
    for s in signals:
        buckets.setdefault(s["at"] // step, []).append(s["bars"])
    return [(b * step + step // 2, sum(v) / len(v)) for b, v in sorted(buckets.items())]


def step_for(span: int, width: float, min_gap: float) -> int:
    points = max(1.0, width / min_gap)
    return max(60, int(span / points))


def ticks(start: int, end: int, step: int):
    t = math.ceil(start / step) * step
    while t < end:
        yield t
        t += step


class SkyChart(Gtk.DrawingArea):
    """Predicted passes with the modem's real signal and its satellite sessions on one time
    axis: the Bridge's "Signal vs passes" chart. A pass is a triangle from AOS to LOS whose apex
    is its peak elevation on a 0-90 degree scale, readings sit on a 0-5 bar scale, sessions are
    dots on the baseline. Tap to inspect."""

    def __init__(self):
        super().__init__()
        self.set_content_height(theme.dp(220))
        self.set_hexpand(True)
        self.passes, self.signals, self.sessions = [], [], []
        self.start = self.end = self.now = 0
        self.tap = None
        self.set_draw_func(self.draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_tap)
        self.add_controller(click)

    def set_data(self, passes, signals, sessions, start: int, end: int, now: int) -> None:
        self.passes = [p for p in passes if p["los"] > start and p["aos"] < end]
        self.signals, self.sessions = signals, sessions
        self.start, self.end, self.now = start, end, now
        self.queue_draw()

    def on_tap(self, gesture, n, x, y):
        self.tap = None if self.tap is not None else x
        self.queue_draw()

    def x_of(self, ts, left, width):
        return left + (ts - self.start) / max(1, self.end - self.start) * width

    def draw(self, area, cr, w, h):
        d = theme.SCALE
        pad_l, pad_r, top, bottom = 22 * d, 24 * d, 14 * d, h - 22 * d
        plot_w, plot_h = w - pad_l - pad_r, bottom - top
        if plot_w <= 0 or plot_h <= 0 or self.end <= self.start:
            return
        cr.select_font_face(theme.FONT)
        cr.set_font_size(9 * d)

        def bars_y(bars):
            return bottom - max(0.0, min(5.0, bars)) / 5.0 * plot_h

        def elev_y(deg):
            return bottom - deg / 90.0 * plot_h

        def label(s, x, y, align="left", colour=LABEL, alpha=1.0):
            ext = cr.text_extents(s)
            if align == "right":
                x -= ext.x_advance
            elif align == "center":
                x -= ext.x_advance / 2
            cr.set_source_rgba(*rgba(colour, alpha))
            cr.move_to(x, y)
            cr.show_text(s)

        # Grid at the bar positions, both scales
        cr.set_line_width(0.5 * d)
        cr.set_dash([2 * d, 3 * d])
        cr.set_source_rgba(*rgba(GRID))
        for v in range(6):
            cr.move_to(pad_l, bars_y(v))
            cr.line_to(w - pad_r, bars_y(v))
        cr.stroke()
        cr.set_dash([])
        for v in range(6):
            label(str(v), pad_l - 5 * d, bars_y(v) + 3 * d, "right")
        label("bars", pad_l - 5 * d, top - 4 * d, "right")
        for deg in (0, 15, 30, 45, 60, 75, 90):
            label(str(deg), w - pad_r + 5 * d, elev_y(deg) + 3 * d, "left", INDIGO, 0.5)
        label("deg", w - pad_r + 5 * d, top - 4 * d, "left", INDIGO, 0.5)

        cr.save()
        cr.rectangle(pad_l, top, plot_w, plot_h)
        cr.clip()
        # Pass triangles, the background layer
        cr.set_font_size(8 * d)
        for p in self.passes:
            x1 = max(pad_l, self.x_of(p["aos"], pad_l, plot_w))
            x2 = min(pad_l + plot_w, self.x_of(p["los"], pad_l, plot_w))
            mid, peak_y = (x1 + x2) / 2, elev_y(p["peak_elev_deg"])
            base = INDIGO_ACTIVE if p.get("is_active") else INDIGO
            cr.move_to(x1, bottom)
            cr.line_to(mid, peak_y)
            cr.line_to(x2, bottom)
            cr.close_path()
            import cairo  # noqa: PLC0415  (pycairo comes with PyGObject)
            gradient = cairo.LinearGradient(0, peak_y, 0, bottom)
            gradient.add_color_stop_rgba(0, *rgba(base, 0.50 if p.get("is_active") else 0.30))
            gradient.add_color_stop_rgba(1, *rgba(base, 0.08 if p.get("is_active") else 0.03))
            cr.set_source(gradient)
            cr.fill_preserve()
            cr.set_source_rgba(*rgba(base, 0.5 if p.get("is_active") else 0.2))
            cr.set_line_width(1 * d)
            cr.stroke()
            if x2 - x1 > 20 * d:
                label(str(int(p["peak_elev_deg"])), mid, peak_y - 3 * d, "center", INDIGO_ACTIVE, 0.6)
        # Signal: soft area, the line, then a dot per reading coloured by strength
        step = step_for(self.end - self.start, plot_w, 3 * d)
        pts = [(self.x_of(ts, pad_l, plot_w), bars_y(bars), bars) for ts, bars in averaged([s for s in self.signals if self.start <= s["at"] <= self.end], step)]
        if len(pts) > 1:
            import cairo  # noqa: PLC0415
            cr.move_to(pts[0][0], bottom)
            for x, y, _b in pts:
                cr.line_to(x, y)
            cr.line_to(pts[-1][0], bottom)
            cr.close_path()
            gradient = cairo.LinearGradient(0, top, 0, bottom)
            gradient.add_color_stop_rgba(0, *rgba(SIGNAL_GREEN, 0.15))
            gradient.add_color_stop_rgba(1, *rgba(SIGNAL_GREEN, 0.02))
            cr.set_source(gradient)
            cr.fill()
            cr.move_to(pts[0][0], pts[0][1])
            for x, y, _b in pts[1:]:
                cr.line_to(x, y)
            cr.set_source_rgba(*rgba(SIGNAL_GREEN, 0.7))
            cr.set_line_width(1.5 * d)
            cr.stroke()
        for x, y, bars in pts:
            cr.set_source_rgba(*rgba(signal_colour(bars), 0.85))
            cr.arc(x, y, 1.8 * d, 0, 2 * math.pi)
            cr.fill()
        # Satellite sessions on the baseline
        for s in self.sessions:
            if not self.start <= s["at"] <= self.end:
                continue
            cr.set_source_rgba(*rgba(SESSION_OK, 0.9) if s["ok"] else rgba(SESSION_FAIL, 0.7))
            cr.arc(self.x_of(s["at"], pad_l, plot_w), bottom - 6 * d, 3 * d, 0, 2 * math.pi)
            cr.fill()
        # Now
        now_x = self.x_of(self.now, pad_l, plot_w)
        cr.set_source_rgba(*rgba(NOW_AMBER, 0.6))
        cr.set_line_width(1 * d)
        cr.set_dash([3 * d, 2 * d])
        cr.move_to(now_x, top)
        cr.line_to(now_x, bottom)
        cr.stroke()
        cr.set_dash([])
        cr.restore()

        # Time labels: every hour up to 6 h, every 3 h up to a day, else every 6 h; room for "now"
        cr.set_font_size(9 * d)
        span = self.end - self.start
        label_step = 3600 if span <= 6 * 3600 else 3 * 3600 if span <= 24 * 3600 else 6 * 3600
        for t in ticks(self.start, self.end, label_step):
            x = self.x_of(t, pad_l, plot_w)
            if abs(x - now_x) < 30 * d:
                continue
            label(hhmm(t), x, h - 3 * d, "center")
        label("now", now_x, h - 3 * d, "center", NOW_AMBER)

        # Tap to inspect: the time, the highest pass there, the nearest reading
        tx = self.tap
        if tx is not None and pad_l <= tx <= w - pad_r:
            cr.set_source_rgba(*rgba("#9CA3AF", 0.5))
            cr.set_line_width(0.5 * d)
            cr.move_to(tx, top)
            cr.line_to(tx, bottom)
            cr.stroke()
            ts = int(self.start + (tx - pad_l) / plot_w * span)
            over = max((p for p in self.passes if p["aos"] <= ts <= p["los"]), key=lambda p: p["peak_elev_deg"], default=None)
            near = min(self.signals, key=lambda s: abs(s["at"] - ts), default=None)
            lines = [f"{hhmm(ts)} UTC"]
            if over:
                lines.append(f"{over['satellite']} {int(over['peak_elev_deg'])}°")
            if near and abs(near["at"] - ts) < 15 * 60:
                lines.append(f"Signal: {near['bars']} bars")
            box_w, line_h = 120 * d, 12 * d
            box_x = tx - box_w - 6 * d if tx > w / 2 else tx + 6 * d
            cr.set_source_rgba(*rgba(TIP_BG, 0.95))
            cr.rectangle(box_x, top + 2 * d, box_w, len(lines) * line_h + 6 * d)
            cr.fill()
            for i, s in enumerate(lines):
                label(s, box_x + 6 * d, top + 2 * d + line_h * (i + 1), "left", TIP_FG)


class SegmentedChoice(Gtk.Box):
    """A row of equal choices, the chosen one filled: sized to the screen, never cut off."""

    def __init__(self, options, selected, label_of, on_select):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(3), homogeneous=True)
        self.add_css_class("segments")
        self.buttons = {}
        for option in options:
            button = Gtk.Button(label=label_of(option))
            button.add_css_class("segment")
            button.connect("clicked", lambda _b, o=option: on_select(o))
            self.buttons[option] = button
            self.append(button)
        self.select(selected)

    def select(self, option) -> None:
        for o, button in self.buttons.items():
            (button.add_css_class if o == option else button.remove_css_class)("on")


class PassesScreen(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.window_hours, self.min_elev = 12, 5
        self.passes, self.signals, self.sessions = [], [], []
        self.loading, self.error, self.expanded = False, None, False
        self.tle_source, self.tle_age, self.cache_age = "none", -1, -1
        self.loaded_for = None
        self.append(SubHeader("Satellite passes", app.pop))
        self.column = page(spacing=12)
        self.column.set_margin_start(theme.dp(12))
        self.column.set_margin_end(theme.dp(12))
        self.banner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.column.append(self.banner)
        self.column.append(SegmentedChoice(WINDOW_OPTIONS, self.window_hours, lambda h: f"{h} h", self.set_window))
        self.chart_card = Card(spacing=theme.dp(4))
        self.chart_card.remove_css_class("card-pad")
        self.chart_card.add_css_class("chart-card")
        self.chart_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.chart_card.append(self.chart_body)
        self.chart = SkyChart()
        self.column.append(self.chart_card)

        surroundings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(6))
        surroundings.append(text("Your surroundings", "label-medium", theme.TEXT_SECONDARY))
        presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6), homogeneous=True)
        self.presets = {}
        for value, name, _desc in ELEV_PRESETS:
            button = Gtk.Button()
            button.add_css_class("preset")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            inner.append(text(f"{value}°", "title-small", xalign=0.5, mono=True))
            inner.append(text(name, "label-small", xalign=0.5))
            button.set_child(inner)
            button.connect("clicked", lambda _b, v=value: self.set_min_elev(v))
            self.presets[value] = button
            presets.append(button)
        surroundings.append(presets)
        self.preset_desc = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        surroundings.append(self.preset_desc)
        self.column.append(surroundings)

        self.list_toggle = Gtk.Button()
        self.list_toggle.add_css_class("flat")
        self.list_toggle.add_css_class("card")
        toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        toggle_row.set_margin_start(theme.dp(12))
        toggle_row.set_margin_end(theme.dp(12))
        toggle_row.set_margin_top(theme.dp(12))
        toggle_row.set_margin_bottom(theme.dp(12))
        self.list_title = text("Every pass in the window (0)", "body-medium")
        toggle_row.append(self.list_title)
        toggle_row.append(spacer())
        self.list_chevron = Gtk.Image.new_from_icon_name("meshsat-outlined-expand-more-symbolic")
        self.list_chevron.add_css_class("fg-text-muted")
        toggle_row.append(self.list_chevron)
        self.list_toggle.set_child(toggle_row)
        self.list_toggle.connect("clicked", lambda *_: self.toggle_list())
        self.column.append(self.list_toggle)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.rows.set_visible(False)
        self.column.append(self.rows)

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        footer.set_margin_top(theme.dp(4))
        position_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
        self.position_dot = Gtk.Box()
        self.position_dot.add_css_class("dot-small")
        self.position_dot.set_valign(Gtk.Align.CENTER)
        position_row.append(self.position_dot)
        self.position_label = text("", "label-small", theme.TEXT_MUTED, wrap=True)
        position_row.append(self.position_label)
        footer.append(position_row)
        self.position_hint = text("", "label-small", theme.TEXT_MUTED, wrap=True)
        footer.append(self.position_hint)
        self.enter_position = text_button("Enter a position", lambda: PositionDialog(app, self).present())
        self.enter_position.set_halign(Gtk.Align.START)
        footer.append(self.enter_position)
        orbit_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
        self.orbit_label = text("Orbit data: No data", "label-small", theme.TEXT_MUTED, ellipsize=True)
        self.orbit_label.set_hexpand(True)
        orbit_row.append(self.orbit_label)
        self.update_button = text_button("Update", self.refresh_tles)
        orbit_row.append(self.update_button)
        footer.append(orbit_row)
        self.column.append(footer)
        self.append(scroller(self.column))
        self.set_min_elev(5, reload=False)
        self.render()
        self._ticker = GLib.timeout_add_seconds(1, self.tick)
        self.update(app.state)

    # Choices
    def set_window(self, hours: int) -> None:
        self.window_hours = hours
        for child in self.column:
            if isinstance(child, SegmentedChoice):
                child.select(hours)
        self.reload()

    def set_min_elev(self, value: int, reload: bool = True) -> None:
        self.min_elev = value
        for v, button in self.presets.items():
            (button.add_css_class if v == value else button.remove_css_class)("on")
        desc = next((d for val, _n, d in ELEV_PRESETS if val == value), "Custom")
        self.preset_desc.set_text(f"{desc}: counts the passes that climb above {value}°.")
        if reload:
            self.reload()

    def toggle_list(self) -> None:
        self.expanded = not self.expanded
        self.rows.set_visible(self.expanded)
        self.list_chevron.set_from_icon_name(f"meshsat-outlined-{'expand-less' if self.expanded else 'expand-more'}-symbolic")

    # Data
    def update(self, s: api.State) -> None:
        position = s.position()
        key = (round(position[0], 3), round(position[1], 3), self.window_hours, self.min_elev) if position else None
        if key != self.loaded_for:
            self.reload()
        else:
            self.render()

    def reload(self) -> None:
        position = self.app.state.position()
        if not position:
            self.loaded_for = None
            self.passes = []
            self.render()
            return
        lat, lon, _source = position
        self.loaded_for = (round(lat, 3), round(lon, 3), self.window_hours, self.min_elev)
        self.loading, self.error = True, None
        self.render()
        threading.Thread(target=self._fetch, args=(lat, lon, self.window_hours, self.min_elev), daemon=True).start()

    def _fetch(self, lat, lon, hours, min_elev):
        now = int(time.time())
        start, end = now - hours * 1800, now + hours * 1800
        answer = api.get(f"/api/iridium/passes?lat={lat}&lon={lon}&hours={hours}&min_elev={min_elev}&start={start}", timeout=20)
        signals = api.get(f"/api/iridium/signal/history?source=iridium&from={start}&to={now}", timeout=10) or []
        sessions = api.get(f"/api/iridium/signal/history?source=gss&from={start}&to={now}", timeout=10) or []
        GLib.idle_add(self._fetched, hours, min_elev, answer, signals, sessions)

    def _fetched(self, hours, min_elev, answer, signals, sessions) -> bool:
        if (hours, min_elev) != (self.window_hours, self.min_elev):
            return False
        self.loading = False
        if answer is None:
            self.error = "The Bridge did not answer."
            self.passes = []
        elif "error" in answer and "passes" not in answer:
            self.error = "No orbit data. Tap Update when online." if "TLE" in str(answer.get("error", "")) else str(answer["error"])
            self.passes = []
        else:
            self.passes = sorted(answer.get("passes") or [], key=lambda p: p["aos"])
            self.tle_source, self.tle_age, self.cache_age = answer.get("tle_source", "none"), answer.get("tle_age_sec", -1), answer.get("cache_age_sec", -1)
        self.signals = [{"at": int(r.get("timestamp") or r.get("ts") or r.get("bucket") or 0), "bars": float(r.get("value") if r.get("value") is not None else r.get("avg", 0))} for r in (signals if isinstance(signals, list) else [])]
        self.sessions = [{"at": int(r.get("timestamp") or r.get("ts") or 0), "ok": float(r.get("value") or 0) >= 1} for r in (sessions if isinstance(sessions, list) else [])]
        self.render()
        return False

    def refresh_tles(self) -> None:
        self.update_button.set_sensitive(False)
        self.update_button.set_label("Updating")

        def run():
            result = api.post("/api/iridium/passes/refresh", timeout=60)
            GLib.idle_add(done, result)

        def done(result) -> bool:
            self.update_button.set_sensitive(True)
            self.update_button.set_label("Update")
            if not result or result.get("error"):
                self.app.toast("Could not download new orbit data; predicting with the data on the phone.")
            self.loaded_for = None
            self.reload()
            return False

        threading.Thread(target=run, daemon=True).start()

    def tick(self) -> bool:
        if self.get_root() is None:
            return False
        if self.passes:
            self.render_banner()
        return True

    # Drawing
    def render(self) -> None:
        now = int(time.time())
        self.render_banner()
        clear(self.chart_body)
        if self.loading:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            row.set_size_request(-1, theme.dp(220))
            row.set_halign(Gtk.Align.CENTER)
            spinner = Gtk.Spinner()
            spinner.start()
            spinner.set_valign(Gtk.Align.CENTER)
            row.append(spinner)
            row.append(text("Working out the passes", "body-small", theme.TEXT_MUTED))
            row.get_last_child().set_valign(Gtk.Align.CENTER)
            self.chart_body.append(row)
        elif not self.passes:
            position = self.app.state.position()
            message = self.error or ("No position yet. Allow location, or wait for a fix." if not position else f"No passes above {self.min_elev}° in this window.")
            empty = text(message, "body-small", theme.RED if self.error else theme.TEXT_MUTED, wrap=True)
            for side in ("start", "end", "top", "bottom"):
                getattr(empty, f"set_margin_{side}")(theme.dp(24))
            self.chart_body.append(empty)
        else:
            self.chart.set_data(self.passes, self.signals, self.sessions, now - self.window_hours * 1800, now + self.window_hours * 1800, now)
            self.chart_body.append(self.chart)
            legend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(10))
            legend.set_margin_start(theme.dp(4))
            legend.set_margin_top(theme.dp(4))
            for mark, colour, name in (("▲", INDIGO, "Pass"), ("●", SIGNAL_GREEN, "Signal"), ("●", SESSION_OK, "Session sent"), ("●", SESSION_FAIL, "Session failed")):
                item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                item.append(text(mark, "label-small", colour))
                item.append(text(f" {name}", "label-small", LABEL))
                legend.append(item)
            self.chart_body.append(legend)
        self.list_toggle.set_visible(bool(self.passes) and not self.loading)
        self.list_title.set_text(f"Every pass in the window ({len(self.passes)})")
        clear(self.rows)
        if self.expanded:
            for p in self.passes:
                self.rows.append(self.pass_row(p, now))
        # The bookkeeping, quiet and last
        position = self.app.state.position()
        for c in ("bg-green", "bg-red"):
            self.position_dot.remove_css_class(c)
        self.position_dot.add_css_class("bg-green" if position else "bg-red")
        if position:
            lat, lon, source = position
            self.position_label.set_text(f"Position from {source}, {lat:.4f}, {lon:.4f}")
            self.position_label.remove_css_class("fg-red")
            self.position_label.add_css_class("fg-text-muted")
            self.position_hint.set_visible(False)
        else:
            self.position_label.set_text("No position: allow location for predictions")
            self.position_label.remove_css_class("fg-text-muted")
            self.position_label.add_css_class("fg-red")
            self.position_hint.set_text(self.app.state.location_hint or "")
            self.position_hint.set_visible(bool(self.app.state.location_hint))
        self.enter_position.set_label("Change the position you entered" if position and position[2] == "the position you entered" else "Enter a position")
        source_text = {"downloaded": "downloaded", "bundled": "built-in", "builtin": "built-in", "none": "No data"}.get(str(self.tle_source), str(self.tle_source))
        self.orbit_label.set_text("Orbit data: No data" if self.tle_source in ("none", None, "") else f"Orbit data: {source_text}, {cache_age_text(self.tle_age)}")

    def render_banner(self) -> None:
        now = int(time.time())
        active = next((p for p in self.passes if p["aos"] <= now <= p["los"]), None)
        upcoming = next((p for p in self.passes if p["aos"] > now), None)
        clear(self.banner)
        if active is None and upcoming is None:
            self.banner.set_visible(False)
            return
        self.banner.set_visible(True)
        overhead = active is not None
        p = active or upcoming
        accent = theme.GREEN if overhead else theme.IRIDIUM
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        card.add_css_class("pass-banner")
        card.add_css_class("pass-banner-green" if overhead else "pass-banner-iridium")
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.set_hexpand(True)
        left.append(text("Overhead now" if overhead else "Next pass", "label-medium", accent))
        left.append(text(p["satellite"], "title-medium", accent))
        top.append(left)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        right.set_halign(Gtk.Align.END)
        if not overhead:
            right.append(text(countdown_text(p["aos"] - now), "headline-small", accent, xalign=1.0, mono=True))
        right.append(text(hhmm(p["aos"]), "title-medium", theme.TEXT_SECONDARY if not overhead else accent, xalign=1.0, mono=True))
        right.append(text(f"{date_short(p['aos'])} UTC", "label-small", theme.TEXT_MUTED, xalign=1.0))
        top.append(right)
        card.append(top)
        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(16))
        for name, value in (("Duration", duration_text(p["duration_min"])), ("Peak", f"{round(p['peak_elev_deg'])}°"), ("Az", f"{round(p['peak_azimuth'])}°")):
            chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
            chip.append(text(name, "label-small", theme.TEXT_MUTED))
            chip.append(text(value, "label-small", theme.TEXT_SECONDARY))
            chips.append(chip)
        card.append(chips)
        if overhead:
            card.append(text("A message can go out now.", "label-small", accent))
        self.banner.append(card)

    def pass_row(self, p: dict, now: int) -> Gtk.Widget:
        active = p["aos"] <= now <= p["los"]
        past = p["los"] < now
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        row.add_css_class("pass-row")
        if active:
            row.add_css_class("active")
        if past:
            row.add_css_class("past")
        dot = Gtk.Box()
        dot.add_css_class("dot")
        dot.add_css_class("bg-iridium" if active else "bg-surface-light")
        dot.set_valign(Gtk.Align.CENTER)
        row.append(dot)
        name = text(p["satellite"], "label-small", ellipsize=True)
        name.set_hexpand(True)
        row.append(name)
        row.append(text(f"{hhmm(p['aos'])}-{hhmm(p['los'])}", "label-small", theme.TEXT_SECONDARY, mono=True))
        duration = text(duration_text(p["duration_min"]), "label-small", theme.TEXT_MUTED, mono=True)
        duration.set_size_request(theme.dp(40), -1)
        row.append(duration)
        bar = Gtk.DrawingArea()
        bar.set_content_width(theme.dp(48))
        bar.set_content_height(theme.dp(4))
        bar.set_valign(Gtk.Align.CENTER)
        fraction, colour = min(1.0, p["peak_elev_deg"] / 90.0), elevation_colour(p["peak_elev_deg"])

        def draw_bar(area, cr, w, h, fraction=fraction, colour=colour):
            cr.set_source_rgba(*rgba(theme.SURFACE_LIGHT))
            cr.rectangle(0, 0, w, h)
            cr.fill()
            cr.set_source_rgba(*rgba(colour))
            cr.rectangle(0, 0, w * fraction, h)
            cr.fill()

        bar.set_draw_func(draw_bar)
        row.append(bar)
        row.append(text(f"{round(p['peak_elev_deg'])}°", "label-small", theme.TEXT_MUTED, mono=True))
        return row


class PositionDialog(Gtk.Window):
    """A position typed by hand, for a phone without a fix: kept by the app, and given to the
    Bridge as the node's fixed position so the SOS and the mesh carry it too."""

    def __init__(self, app, screen: PassesScreen):
        super().__init__(title="Your position", modal=True, transient_for=app.window, decorated=False)
        self.app, self.screen = app, screen
        self.set_default_size(340, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        box.add_css_class("dialog")
        box.append(text("Your position", "dialog-title"))
        box.append(text("Decimal degrees, as a map shows them. Used for the passes here, and given to the node as its fixed position.", "body-medium", theme.TEXT_SECONDARY, wrap=True))
        current = app.state.entered
        self.lat = Gtk.Entry(placeholder_text="Latitude, 52.1601", input_purpose=Gtk.InputPurpose.NUMBER)
        self.lon = Gtk.Entry(placeholder_text="Longitude, 4.4970", input_purpose=Gtk.InputPurpose.NUMBER)
        for entry, value in ((self.lat, current and current[0]), (self.lon, current and current[1])):
            entry.add_css_class("field")
            if value is not None:
                entry.set_text(f"{value:.5f}")
            box.append(entry)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        buttons.set_halign(Gtk.Align.END)
        buttons.append(text_button("Cancel", self.close))
        buttons.append(filled_button("Use this position", self.use, expand=False))
        box.append(buttons)
        self.set_child(box)

    def use(self) -> None:
        try:
            lat, lon = float(self.lat.get_text().replace(",", ".")), float(self.lon.get_text().replace(",", "."))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                raise ValueError
        except ValueError:
            self.app.toast("That is not a position: latitude -90 to 90, longitude -180 to 180.")
            return
        self.close()
        self.app.set_entered_position(lat, lon)
        result = api.post("/api/position/fixed", {"latitude": lat, "longitude": lon, "altitude": 0})
        self.app.toast("The node carries this position now." if not result.get("error") else f"Kept for the passes; the node did not take it: {result['error']}")
        self.screen.loaded_for = None
        self.screen.reload()
