# SPDX-License-Identifier: GPL-3.0-or-later
"""The satellite sky chart's geometry, as MeshSat Android's SkyGeometry (ui/components/SkyChart.kt:
53-118), shared by the passes page and Home's "Satellite signal and passes" card. Pure: no GTK.
Passes are dicts with `aos`, `los` (Unix seconds) and `peak_elev_deg`; readings dicts with `at`
(Unix seconds) and `bars`."""
import math

SIGNAL_GREEN, AMBER, RED = "#10B981", "#F59E0B", "#EF4444"


def x(ts: float, start: float, end: float, left: float, width: float) -> float:
    return left + ((ts - start) / (end - start)) * width


def elev_y(deg: float, bottom: float, height: float) -> float:
    return bottom - (deg / 90.0) * height


def bars_y(bars: float, bottom: float, height: float) -> float:
    return bottom - (min(max(float(bars), 0.0), 5.0) / 5.0) * height


def averaged(signals, step: int) -> list:
    """Readings averaged into steps, one point per step at its middle; a step of a minute or less
    keeps every reading (a reading a minute over twelve hours is 720 points in a few hundred pixels)."""
    if step <= 60:
        return sorted((s["at"], float(s["bars"])) for s in signals)
    buckets = {}
    for s in signals:
        buckets.setdefault(s["at"] // step, []).append(s["bars"])
    return [(b * step + step // 2, sum(v) / len(v)) for b, v in sorted(buckets.items())]


def step_for(span: int, width: float, min_gap: float) -> int:
    """The step that leaves about `min_gap` pixels between points, never under a minute."""
    points = max(1.0, width / min_gap)
    return max(60, int(span / points))


def triangle(p: dict, start: float, end: float, left: float, width: float, bottom: float, height: float) -> tuple:
    """(x1, x_mid, x2, peak_y): AOS and LOS on the baseline clipped to the plot, the apex half way
    between the clipped ends at the peak elevation (the Bridge clips first, then finds the middle)."""
    x1 = max(left, x(p["aos"], start, end, left, width))
    x2 = min(left + width, x(p["los"], start, end, left, width))
    return x1, (x1 + x2) / 2.0, x2, elev_y(float(p["peak_elev_deg"]), bottom, height)


def signal_colour(bars: float) -> str:
    """Green from 3 bars, amber at 1 and 2, red at 0: the Bridge's thresholds (half rounds up, as Kotlin's round)."""
    b = math.floor(float(bars) + 0.5)
    return SIGNAL_GREEN if b >= 3 else AMBER if b >= 1 else RED


def ticks(start: int, end: int, step: int) -> list:
    """Label times on whole multiples of `step` inside the window."""
    out, t = [], math.ceil(start / step) * step
    while t < end:
        out.append(t)
        t += step
    return out


def overlaps(p: dict, start: float, end: float) -> bool:
    return p["los"] > start and p["aos"] < end


def card_shown(passes: list, readings: list, now: float) -> bool:
    """Home's card shows with a reading in the last 3 h or a pass touching now-3 h to now+3 h (DashboardScreen.kt:402)."""
    return any(r["at"] >= now - 3 * 3600 for r in readings) or any(overlaps(p, now - 3 * 3600, now + 3 * 3600) for p in passes)
