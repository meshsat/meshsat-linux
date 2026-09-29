# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline maps (ui/screens/SettingsScreen.kt:1984-2223, map/MBTilesManager.kt, map/MapTiles.kt,
ui/components/MapChrome.kt:119-152): the words of Setup > Maps and of the note on both maps,
the settings ("Use my detailed map", the chosen file), the names added files get, and which
tile source answers. Pure."""
import os
import re

from .mbtiles import MBTiles, NotRaster

WORLD_FILE = "world.mbtiles"
WORLD_VERSION = "2"

# ── Setup > Maps ─────────────────────────────────────────────────────────────────────────────
TITLE = "Maps"
CARD = "Offline maps"
INTRO = "The map downloads its detail from the internet. Without internet it shows what is installed here."
INSTALLED = "Installed"
WORLD = "World overview"
WORLD_TEXT = "Built in and always installed. Countries and coastlines at a zoomed-out scale, shown when there is no internet."
VECTOR = "Vector tiles: the map cannot show this file."
IN_USE = "In use"
USE_DETAILED = "Use my detailed map"
USE_DETAILED_HINT = "Shown first. Outside it the map uses online tiles, or the world overview without internet."
ADD = "Add a detailed map"
ADDING = "Adding the map"
ADD_HINT = ("Use an MBTiles file with PNG or JPEG tiles, for example one exported from OpenStreetMap for your area. "
            "Files with vector tiles cannot be shown.")
ADDED_VECTOR = "Added, but this file has vector tiles, which the map cannot show."
DELETE_TITLE = "Delete this map?"
DELETE_CONFIRM = "Delete"
DELETE_KEEP = "Keep it"
MISSING_TILES = "Not a valid MBTiles file: missing 'tiles' table"
MISSING_METADATA = "Not a valid MBTiles file: missing 'metadata' table"
NOT_FOUND = "MBTiles file not found: {}"


def use_name(name: str) -> str:
    return f"Use {name}"


def delete_name(name: str) -> str:
    return f"Delete {name}"


def delete_body(name: str) -> str:
    return f"{name} is removed from this phone. You can add it again from a file."


def added(name: str) -> str:
    return f"Map added: {name}"


def deleted(name: str) -> str:
    return f"Map deleted: {name}"


def could_not_add(reason: str) -> str:
    return f"Could not add this map: {reason}"


def invalid(reason: str) -> str:
    return f"Invalid MBTiles file: {reason}"


# ── The note on both maps ────────────────────────────────────────────────────────────────────
ONLINE = "© OpenStreetMap contributors"
OFFLINE_WORLD = "Offline map: world overview, country level only. Add a detailed map in Setup > Maps."


def offline_detailed(name: str) -> str:
    return f"Offline map: {name}. Outside it, the world overview."


def note(offline: bool, detailed_name: str | None, zones: bool = False) -> tuple:
    """(text, "credit" or "note"): the credit online; offline, the detailed map's name, or the
    world overview (the Zones screen's own sentence there)."""
    if not offline:
        return ONLINE, "credit"
    if detailed_name:
        return offline_detailed(detailed_name), "note"
    from .geofence import OFFLINE_NOTE  # noqa: PLC0415

    return (OFFLINE_NOTE if zones else OFFLINE_WORLD), "note"


# ── Files ────────────────────────────────────────────────────────────────────────────────────
def safe_name(display: str) -> str:
    """The name an added file gets in the maps folder (MBTilesManager.kt:171-174)."""
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", display or "") or "map.mbtiles"
    name = name if name.endswith(".mbtiles") else name + ".mbtiles"
    # Android lets a file named world.mbtiles overwrite the bundled overview and vanish from the
    # list (spec 2.13); here it keeps a name of its own.
    return "my_" + name if name == WORLD_FILE else name


def open_checked(path: str) -> MBTiles:
    """An MBTiles file as the reader checks it: both tables present. Raises ValueError with
    Android's words."""
    import sqlite3  # noqa: PLC0415

    if not os.path.exists(path):
        raise ValueError(NOT_FOUND.format(os.path.abspath(path)))
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        db.close()
    except sqlite3.Error as error:
        raise ValueError(str(error)) from error
    if "tiles" not in tables:
        raise ValueError(MISSING_TILES)
    if "metadata" not in tables:
        raise ValueError(MISSING_METADATA)
    try:
        return MBTiles(path)
    except NotRaster:
        raise
    except Exception as error:  # noqa: BLE001
        raise ValueError(str(error)) from error


class Entry:
    """One installed detailed map: its file name, display name, size, zooms, and whether the
    map can show it."""

    def __init__(self, filename: str, name: str, size_bytes: int, min_zoom, max_zoom, vector: bool):
        self.filename, self.name, self.size_bytes = filename, name, size_bytes
        self.min_zoom, self.max_zoom, self.vector = min_zoom, max_zoom, vector

    def details(self) -> str:
        """"12.3 MB, zoom 0 to 14" (binary megabytes, one decimal, half up)."""
        from .geofence import half_up  # noqa: PLC0415

        parts = [f"{half_up(self.size_bytes / 1048576, 1)} MB"]
        if self.min_zoom is not None and self.max_zoom is not None:
            parts.append(f"zoom {self.min_zoom} to {self.max_zoom}")
        return ", ".join(parts)


def listing(folder: str) -> list:
    """Every *.mbtiles in the folder that opens as MBTiles, the world overview left out, sorted
    by display name; broken files are skipped (they stay on disk)."""
    import sqlite3  # noqa: PLC0415

    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for filename in names:
        if not filename.endswith(".mbtiles") or filename == WORLD_FILE or filename.startswith("."):  # ".adding-*": a copy under way
            continue
        path = os.path.join(folder, filename)
        try:
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "tiles" not in tables or "metadata" not in tables:
                db.close()
                continue
            meta = {str(k): str(v) for k, v in db.execute("SELECT name, value FROM metadata")}
            db.close()
        except sqlite3.Error:
            continue

        def zoom(key: str):
            try:
                return int(meta[key])
            except (KeyError, ValueError):
                return None

        out.append(Entry(filename, meta.get("name") or filename[: -len(".mbtiles")], os.path.getsize(path), zoom("minzoom"), zoom("maxzoom"),
                         meta.get("format", "png").lower() == "pbf"))
    return sorted(out, key=lambda e: e.name)


def active(entries: list, enabled: bool, chosen: str):
    """The detailed map in use: switched on and the chosen file one of the raster maps."""
    if not enabled:
        return None
    return next((e for e in entries if e.filename == chosen and not e.vector), None)


def turn_on(entries: list, chosen: str):
    """The file "Use my detailed map" switches to: the saved one when still usable, else the
    first usable map by name."""
    usable = [e for e in entries if not e.vector]
    return next((e for e in usable if e.filename == chosen), usable[0] if usable else None)


# ── Offline ──────────────────────────────────────────────────────────────────────────────────
OFFLINE_AFTER = 3  # failed OpenStreetMap downloads in a row


class Online:
    """Offline after three failed tile downloads in a row; one that works clears it
    (MapTiles.kt:45-53). Shared by both maps."""

    def __init__(self):
        self.failures = 0

    @property
    def offline(self) -> bool:
        return self.failures >= OFFLINE_AFTER

    def failed(self) -> None:
        self.failures += 1

    def worked(self) -> None:
        self.failures = 0
