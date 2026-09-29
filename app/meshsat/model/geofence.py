# SPDX-License-Identifier: GPL-3.0-or-later
"""Zones (ui/screens/GeofenceScreen.kt, engine/GeofenceMonitor.kt): the words, the numbers and
the geometry of MeshSat Android's Zones screen. The zones themselves live in the Bridge
(/api/geofences, MESHSAT-1414), which checks every mesh position against them and keeps the
crossings, in memory, as Android's service does. Pure."""
import math
import time
from decimal import ROUND_HALF_UP, Decimal

from . import words

# ── Words (GeofenceScreen.kt) ────────────────────────────────────────────────────────────────
TITLE = "Zones"
EXPLAINER = ("When a mesh node reports a position that crosses a zone's edge, the alert is listed here. "
             "It does not send a message or a notification, and zones are kept only until the MeshSat service restarts.")
NO_SERVICE = "Zones are not available until the MeshSat service is running."
ADD = "Add zone"
NO_ZONES = "No zones yet."
RECENT = "Recent alerts"
NO_ALERTS = "No alerts yet."
HINT_NO_CENTRE = "Long-press the map where the zone should be."
HINT_MOVE = "Long-press the map to move the zone."
HINT_IDLE = "Long-press the map to place a zone."
CENTRE_ON_ME = "Centre on me"
NO_POSITION = "Your position is not known yet."
OFFLINE_NOTE = "Offline, with no street detail here. Zones still work: place one around your position. For detail, add a map in Setup > Maps."
THIS_PHONE = "This phone"
NEW_ZONE = "New zone"
CENTRE_SET = "The orange circle is the zone. Long-press the map to move it."
NAME = "Name"
NAME_ERROR = "Give the zone a name."
RADIUS = "Radius"
RADIUS_FIELD = "Radius in metres"
MIN_RADIUS_M = 10
MAX_RADIUS_M = 50000
RADIUS_ERROR = f"Use a radius between {MIN_RADIUS_M} m and {MAX_RADIUS_M // 1000} km."
ALERT_WHEN = "Alert when a node"
ALERT_CHOICES = (("enter", "Enters the zone"), ("exit", "Leaves the zone"), ("both", "Enters or leaves"))
NOTE = "Note (optional)"
SAVE = "Save zone"
CANCEL = "Cancel"
DELETE_BODY = "MeshSat stops watching this zone. Alerts it already raised stay in the list."
DELETE_CONFIRM = "Delete zone"
DELETE_KEEP = "Keep it"
DEFAULT_RADIUS = 200
STALE_S = 15 * 60
ALERTS_SHOWN = 20
SLIDER_MIN, SLIDER_MAX = 50.0, 5000.0


def added(name: str) -> str:
    return f"Zone added: {name}"


def delete_title(name: str) -> str:
    return f"Delete {name}?"


def delete_name(name: str) -> str:
    return f"Delete zone {name}"


def show_name(name: str) -> str:
    return f"Show {name} on the map"


def alert_when(alert_on: str) -> str:
    return {"enter": "enters", "exit": "leaves"}.get(alert_on, "enters or leaves")


def zone_snippet(zone: dict) -> str:
    """The saved zone's bubble on the map: no full stop."""
    return f"Alerts when a node {alert_when(zone.get('alert_on', ''))}"


def zone_subtitle(zone: dict) -> str:
    return f"Alerts when a node {alert_when(zone.get('alert_on', ''))}. Radius about {format_distance(zone_radius(zone.get('polygon') or []))}."


def event_line(record: dict, names: dict, now_s: float) -> str:
    """"Alice entered Home, 4 min ago": the node's name when the radio knows one, else its id."""
    node = str(record.get("node_id") or "")
    who = names.get(node) or node
    did = "entered" if record.get("event") == "enter" else "left"
    return f"{who} {did} {record.get('zone_name', '')}, {words.ago_ms(int(record.get('timestamp') or 0), int(now_s * 1000))}"


# ── Numbers ──────────────────────────────────────────────────────────────────────────────────
def half_up(value: float, digits: int = 0) -> Decimal:
    """Kotlin's roundToInt and Java's "%.1f": half away from zero on the decimal written."""
    quantum = Decimal(1).scaleb(-digits)
    return Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def format_distance(m: float) -> str:
    """"200 m", "1 km", "1.5 km" (GeofenceScreen.kt:748-753)."""
    if m < 1000:
        return f"{int(half_up(m))} m"
    return f"{half_up(m / 1000, 1)} km".replace(".0 km", " km")


def slider_to_radius(t: float) -> int:
    raw = 50 * math.exp(t * math.log(100))
    step = 10 if raw < 200 else 25 if raw < 1000 else 100
    return int(half_up(raw / step)) * step


def radius_to_slider(r: float) -> float:
    return math.log(min(max(r, SLIDER_MIN), SLIDER_MAX) / SLIDER_MIN) / math.log(100)


def radius_ok(text: str):
    """The radius typed, when it is a whole number from 10 m to 50 km; else None."""
    digits = "".join(ch for ch in text if ch.isdigit())[:5]
    if not digits or digits != text:
        return None
    value = int(digits)
    return value if MIN_RADIUS_M <= value <= MAX_RADIUS_M else None


def zoom_for_radius(r: float) -> float:
    for limit, zoom in ((100, 17), (250, 16), (500, 15), (1000, 14), (2500, 13), (5000, 12), (15000, 11)):
        if r <= limit:
            return zoom
    return 9


def zoom_for_span(deg: float) -> float:
    for limit, zoom in ((0.002, 16), (0.01, 15), (0.05, 13), (0.2, 11), (1.0, 9), (5.0, 7), (30.0, 5)):
        if deg < limit:
            return zoom
    return 3


def show_points(points: list):
    """(lat, lon, zoom) for MapChrome's showPoints: the middle of the bounding box, the zoom for
    its larger span; None for no points."""
    if not points:
        return None
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    span = max(max(lats) - min(lats), max(lons) - min(lons))
    return (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2, zoom_for_span(span)


# ── Geometry ─────────────────────────────────────────────────────────────────────────────────
EARTH_R = 6371000.0


def circle_polygon(lat: float, lon: float, r: float, n: int = 32) -> list:
    """The saved zone's vertices (GeofenceScreen.kt:771-779): equirectangular, vertex 0 due north,
    clockwise on the map."""
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        d_lat = r * math.cos(a) / EARTH_R
        d_lon = r * math.sin(a) / (EARTH_R * math.cos(math.radians(lat)))
        out.append({"lat": lat + math.degrees(d_lat), "lon": lon + math.degrees(d_lon)})
    return out


def geodesic_circle(lat: float, lon: float, r: float, n: int = 60) -> list:
    """The zone being placed (osmdroid's Polygon.pointsAsCircle): n points on a great circle, one
    every 360/n degrees of bearing."""
    out = []
    phi1, lam1, delta = math.radians(lat), math.radians(lon), r / EARTH_R
    for i in range(n):
        theta = math.radians(i * 360.0 / n)
        phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
        lam2 = lam1 + math.atan2(math.sin(theta) * math.sin(delta) * math.cos(phi1), math.cos(delta) - math.sin(phi1) * math.sin(phi2))
        out.append((math.degrees(phi2), (math.degrees(lam2) + 540) % 360 - 180))
    return out


def point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    """Ray casting on plain degrees (GeofenceMonitor.kt:123-145), as the Bridge checks."""
    n = len(polygon)
    if n < 3:
        return False
    inside, j = False, n - 1
    for i in range(n):
        yi, xi = polygon[i]["lat"], polygon[i]["lon"]
        yj, xj = polygon[j]["lat"], polygon[j]["lon"]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def vincenty(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """The WGS84 ellipsoidal distance in metres (Vincenty's inverse), as Android's
    Location.distanceBetween measures it."""
    a, f = 6378137.0, 1 / 298.257223563
    b = (1 - f) * a
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    big_l = math.radians(lon2 - lon1)
    u1 = math.atan((1 - f) * math.tan(math.radians(lat1)))
    u2 = math.atan((1 - f) * math.tan(math.radians(lat2)))
    sin_u1, cos_u1, sin_u2, cos_u2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    lam = big_l
    for _ in range(200):
        sin_lam, cos_lam = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(cos_u2 * sin_lam, cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lam)
        if sin_sigma == 0:
            return 0.0
        cos_sigma = sin_u1 * sin_u2 + cos_u1 * cos_u2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_u1 * cos_u2 * sin_lam / sin_sigma
        cos2_alpha = 1 - sin_alpha * sin_alpha
        cos_2sm = cos_sigma - 2 * sin_u1 * sin_u2 / cos2_alpha if cos2_alpha else 0.0
        c = f / 16 * cos2_alpha * (4 + f * (4 - 3 * cos2_alpha))
        previous = lam
        lam = big_l + (1 - c) * f * sin_alpha * (sigma + c * sin_sigma * (cos_2sm + c * cos_sigma * (-1 + 2 * cos_2sm * cos_2sm)))
        if abs(lam - previous) < 1e-12:
            break
    u_sq = cos2_alpha * (a * a - b * b) / (b * b)
    big_a = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
    big_b = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
    d_sigma = big_b * sin_sigma * (cos_2sm + big_b / 4 * (cos_sigma * (-1 + 2 * cos_2sm * cos_2sm)
                                                          - big_b / 6 * cos_2sm * (-3 + 4 * sin_sigma * sin_sigma) * (-3 + 4 * cos_2sm * cos_2sm)))
    return b * big_a * (sigma - d_sigma)


def zone_radius(polygon: list) -> float:
    """The mean WGS84 distance from the polygon's centroid (the mean of its vertices) to its
    vertices: measured, not stored (GeofenceScreen.kt:755-765)."""
    if not polygon:
        return 0.0
    c_lat = sum(p["lat"] for p in polygon) / len(polygon)
    c_lon = sum(p["lon"] for p in polygon) / len(polygon)
    return sum(vincenty(c_lat, c_lon, p["lat"], p["lon"]) for p in polygon) / len(polygon)


def zone_points(zone: dict) -> list:
    return [(p["lat"], p["lon"]) for p in zone.get("polygon") or []]


# ── Saving ───────────────────────────────────────────────────────────────────────────────────
def check(name: str, centre, radius_text: str) -> dict:
    """The editor's three errors, all at once: {"name", "centre", "radius"} → True when wrong."""
    return {"name": not name.strip(), "centre": centre is None, "radius": radius_ok(radius_text) is None}


def new_zone(name: str, centre: tuple, radius: int, alert_on: str, note: str, now_ms: int | None = None) -> dict:
    """POST /api/geofences: Android's zone, the id from the time in milliseconds."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return {"id": f"zone_{now_ms}", "name": name.strip(), "polygon": circle_polygon(centre[0], centre[1], radius, 32), "alert_on": alert_on,
            "message": note.strip()}
