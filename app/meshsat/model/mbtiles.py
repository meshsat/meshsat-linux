# SPDX-License-Identifier: GPL-3.0-or-later
"""An MBTiles file read as MeshSat Android's MBTilesReader reads it (map/MBTilesReader.kt): a
SQLite database with a `metadata` table (name, format, minzoom, maxzoom, bounds...) and a `tiles`
table keyed by zoom, column and row, the row counted from the bottom (TMS), so the row an XYZ
map asks for is flipped. Raster tiles only (png, jpg, webp); a vector (pbf) file is refused.
Opened read-only. Pure: the standard library's sqlite3."""
import os
import sqlite3
import threading

RASTER = ("png", "jpg", "jpeg", "webp")


class NotRaster(ValueError):
    """The file holds vector tiles (pbf) or no tiles at all."""


class MBTiles:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()  # the map's tile workers share one connection
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self.meta = self._metadata()
        fmt = (self.meta.get("format") or "").lower()
        if fmt and fmt not in RASTER:
            self.db.close()
            raise NotRaster(f"{os.path.basename(path)} holds {fmt} tiles; only raster maps (png, jpg, webp) are shown")

    def _metadata(self) -> dict:
        try:
            return {str(k): str(v) for k, v in self.db.execute("SELECT name, value FROM metadata")}
        except sqlite3.Error:
            return {}

    def close(self) -> None:
        with self.lock:
            self.db.close()

    @property
    def name(self) -> str:
        return self.meta.get("name") or os.path.splitext(os.path.basename(self.path))[0]

    def zoom_range(self) -> tuple:
        """(min, max) from the metadata, else from the tiles themselves."""
        try:
            return int(self.meta["minzoom"]), int(self.meta["maxzoom"])
        except (KeyError, ValueError):
            pass
        try:
            with self.lock:
                row = self.db.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles").fetchone()
        except sqlite3.Error:
            return 0, 0
        return (row[0] or 0, row[1] or 0) if row else (0, 0)

    def bounds(self):
        """(west, south, east, north) in degrees, or None."""
        try:
            west, south, east, north = (float(v) for v in self.meta["bounds"].split(","))
            return west, south, east, north
        except (KeyError, ValueError):
            return None

    def tile(self, z: int, x: int, y: int):
        """The tile an XYZ map asks for (y from the top), or None."""
        if z < 0 or x < 0 or y < 0 or x >= 1 << z or y >= 1 << z:
            return None
        try:
            with self.lock:
                row = self.db.execute("SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                                      (z, x, (1 << z) - 1 - y)).fetchone()
        except sqlite3.Error:  # closed (the file deleted) or damaged
            return None
        return bytes(row[0]) if row and row[0] is not None else None

    def size_mb(self) -> float:
        try:
            return os.path.getsize(self.path) / (1024 * 1024)
        except OSError:
            return 0.0


def content_type(data: bytes) -> str:
    """The image type of a tile from its first bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"
