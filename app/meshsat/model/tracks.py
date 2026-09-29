# SPDX-License-Identifier: GPL-3.0-or-later
"""The Map tab (ui/screens/MapScreen.kt, map/MapTracks.kt, ui/components/MapChrome.kt): the
tracks of the last 24 hours, the "Layers and nodes" panel's words, the markers' bubbles and
"Show on map". Positions come from the Bridge (GET /api/positions, newest first; each row with
its node, MESHSAT-1397). Pure."""
import time

from . import words

WINDOW_S = 24 * 3600
LIMIT = 5000
RELOAD_S = 30
STALE_S = 15 * 60

MAP = "Map"
CENTRE_ON_ME = "Centre on me"
SHOW_EVERYONE = "Show everyone on the map"
ZOOM_IN, ZOOM_OUT = "Zoom in", "Zoom out"
NO_POSITION = "Your position is not known yet."
NO_POSITIONS = "No positions to show yet."
NO_NODE_POSITION = "This node has not sent a position yet."
THIS_PHONE = "This phone"
PANEL = "Layers and nodes"
NO_NODE_POSITIONS = "No node positions yet"
OPEN_PANEL, CLOSE_PANEL = "Open layers and nodes", "Close layers and nodes"
LAYERS = "Layers"
NODES = "Nodes"
TRACKS = "Tracks from the last 24 hours"
SHOW_ALL, HIDE_ALL = "Show all", "Hide all"
EMPTY_NODES = "Nodes appear here when they send a position."
ACCURACY_UNKNOWN = "Accuracy unknown"


def since_param(now_s: float | None = None) -> str:
    """The Bridge's positions are stamped by SQLite in UTC ("2026-09-29 04:10:00")."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime((now_s if now_s is not None else time.time()) - WINDOW_S))


def summary(shown: int, total: int) -> str:
    if total == 0:
        return NO_NODE_POSITIONS
    return f"{shown} of {words.count(total, 'node')} shown"


def heard(last_heard_s: float, now_s: float) -> str:
    """"Heard 4 min ago", or "Last heard 2 h ago" once the position is stale."""
    prefix = "Last heard" if now_s - (last_heard_s or 0) > STALE_S else "Heard"
    return f"{prefix} {words.ago(last_heard_s, now_s)}"


def node_snippet(node: dict, now_s: float) -> str:
    text = heard(node.get("last_heard") or 0, now_s)
    altitude = int(node.get("altitude") or 0)
    return text + (f", altitude {altitude} m" if altitude else "")


def accuracy(metres) -> str:
    return f"Within about {int(metres)} m" if metres else ACCURACY_UNKNOWN


def phone_line(lat: float, lon: float, metres) -> str:
    """The panel's phone row: "52.12345, 5.12345, within about 12 m"."""
    from .geofence import half_up  # noqa: PLC0415

    line = accuracy(metres)
    return f"{half_up(lat, 5)}, {half_up(lon, 5)}, {line[0].lower()}{line[1:]}"


def show_label(label: str) -> str:
    return f"Show {label} on the map"


def centre_label(label: str) -> str:
    return f"Centre the map on {label}"


def track_title(label: str) -> str:
    return "Track of " + label


def label(node: dict) -> str:
    """MapChrome.meshNodeNames and positionLabel: the long name, else the short name, else the id."""
    return (node.get("long_name") or "").strip() or (node.get("short_name") or "").strip() or node.get("user_id") or ""


def markers(nodes: list, rows: list, skip: set, now_s: float) -> list:
    """The nodes on the map, newest first (getLatestPerNode): every node of the radio's list with
    a position, then the stations only the position log knows (APRS, TAK), each at its newest
    row; `skip` names the nodes that are this phone. Each {"id", "lat", "lon", "label", "heard",
    "altitude", "stale"}."""
    out, seen = [], set()
    for node in nodes:
        node_id = node.get("user_id") or ""
        if not node_id or node_id in skip or not node.get("latitude") or not node.get("longitude"):
            continue
        seen.add(node_id)
        heard_s = float(node.get("last_heard") or 0)
        out.append({"id": node_id, "lat": float(node["latitude"]), "lon": float(node["longitude"]), "label": label(node) or node_id, "heard": heard_s,
                    "altitude": int(node.get("altitude") or 0), "stale": now_s - heard_s > STALE_S})
    known = {n.get("user_id") for n in nodes}
    for row in rows:  # newest first: the first row of a station is its latest
        node_id = row.get("node_id") or ""
        if not node_id or node_id in seen or node_id in skip or node_id in known:
            continue
        seen.add(node_id)
        heard_s = words.stamp_epoch(row.get("created_at")) or 0.0
        out.append({"id": node_id, "lat": float(row["latitude"]), "lon": float(row["longitude"]), "label": node_id, "heard": heard_s,
                    "altitude": int(row.get("altitude") or 0), "stale": now_s - heard_s > STALE_S})
    return sorted(out, key=lambda m: -m["heard"])


def marker_snippet(marker: dict, now_s: float, zones: bool = False) -> str:
    """The bubble's second line: on the Map tab the heard line and the altitude; on Zones only
    "Heard ..." (GeofenceScreen.kt:267)."""
    if zones:
        return "Heard " + words.ago(marker["heard"], now_s)
    return node_snippet({"last_heard": marker["heard"], "altitude": marker["altitude"]}, now_s)


def group(rows: list, hidden: set, latest: dict | None = None) -> dict:
    """The tracks to draw, by node: rows oldest first (the Bridge answers newest first), hidden
    nodes left out, each joined to its marker when the marker is newer than the last point; a
    track needs two points."""
    tracks = {}
    for row in reversed(rows):
        node = row.get("node_id") or ""
        if not node or node in hidden:
            continue
        tracks.setdefault(node, []).append((float(row["latitude"]), float(row["longitude"]), row.get("created_at") or ""))
    for node, points in list(tracks.items()):
        mark = (latest or {}).get(node)
        if mark and (mark[0], mark[1]) != (points[-1][0], points[-1][1]):
            points.append((mark[0], mark[1], "marker"))
        if len(points) < 2:
            del tracks[node]
    return {node: [(p[0], p[1]) for p in points] for node, points in tracks.items()}
