# SPDX-License-Identifier: GPL-3.0-or-later
"""The map's tiles, in the order MeshSat Android's MapTiles.kt tries its sources: the chosen
detailed MBTiles (Setup > Maps), then OpenStreetMap (a tile saved before, or a download), then
the bundled world overview (zoom 0 to 3). A tile no source has at its zoom is cut from its
nearest ancestor and scaled up, as osmdroid's approximater does, so offline the world overview
shows scaled up instead of blank. Three failed downloads in a row make the map offline
(maps.Online); a download that works clears it. The map widget draws every tile through the
dark matrix, so the world overview, stored through its inverse, shows its own colours.

The tiles reach libshumate through a data source of its own, not a URL: libshumate keeps every
tile it downloads for seven days in a folder named after the URL, and a tile scaled up while
offline must not outlive the offline spell. One `Tiles` serves the whole app, so the Map tab
and Zones always agree on being offline (MapTiles.kt:45-53)."""
import os
import threading
import time
import urllib.request
import weakref
from concurrent.futures import ThreadPoolExecutor

import gi

from gi.repository import GdkPixbuf, Gio, GLib

from . import __version__
from .model import maps
from .model.mbtiles import MBTiles

try:
    gi.require_version("Shumate", "1.0")
    from gi.repository import Shumate
except (ValueError, ImportError):
    Shumate = None

OSM_URL = os.environ.get("MESHSAT_APP_OSM_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
USER_AGENT = f"MeshSat-Linux/{__version__} (+https://meshsat.net)"
HERE = os.path.dirname(os.path.abspath(__file__))
WORLD_PATH = os.environ.get("MESHSAT_APP_WORLD") or os.path.join(HERE, "maps", maps.WORLD_FILE)
MIN_ZOOM, MAX_ZOOM = 0, 19  # osmdroid's MAPNIK source: zoom 0 to 19, 256 px tiles
TILE_SIZE = 256
FRESH_S = 7 * 86400  # a saved OpenStreetMap tile younger than this is shown without asking again
OFFLINE_RETRY_S = float(os.environ.get("MESHSAT_APP_OFFLINE_RETRY", "30"))  # offline, one download now and then tells when the network is back
CACHE_LIMIT = 256 * 1024 * 1024  # saved tiles past this go, the oldest first


def data_dir() -> str:
    """The detailed maps added in Setup > Maps (Android: <filesDir>/mbtiles)."""
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "meshsat", "mbtiles")


def cache_dir() -> str:
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "meshsat", "tiles")


class Tiles:
    def __init__(self, prefs):
        self.prefs = prefs
        self.online = maps.Online()
        self.lock = threading.Lock()
        self.last_try = 0.0
        self._world = None
        self._detailed = None  # (path, mtime, MBTiles or None)
        self.listeners = []  # weak references to methods called with `offline` when it changes
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tiles")
        self.downloads = threading.Semaphore(2)  # OpenStreetMap's tile policy: two connections at most
        self.served = {"detailed": 0, "saved": 0, "download": 0, "world": 0, "scaled": 0, "none": 0}  # for the tests
        self.asked = {}  # zoom -> tiles libshumate asked for (the tests)
        threading.Thread(target=trim_cache, daemon=True).start()

    @property
    def offline(self) -> bool:
        return self.online.offline

    # The detailed map in use: Setup > Maps' switch and file (MapTiles.detailedMap)
    def resolved(self):
        """(path, mtime) of the detailed map the settings choose and the map can show, else None:
        the maps rebuild their tiles only when this changes."""
        if not self.prefs.get("offline_map_enabled", True):
            return None
        name = str(self.prefs.get("offline_map_file", "") or "")
        if not name.strip() or name == maps.WORLD_FILE or "/" in name:
            return None
        path = os.path.join(data_dir(), name)
        try:
            return path, os.path.getmtime(path)
        except OSError:
            return None

    def detailed(self):
        resolved = self.resolved()
        if resolved is None:
            with self.lock:  # switched off, or its file gone: let the file go too
                if self._detailed and self._detailed[2] is not None:
                    self._detailed[2].close()
                self._detailed = None
            return None
        with self.lock:
            if self._detailed and self._detailed[:2] == resolved:
                return self._detailed[2]
            if self._detailed and self._detailed[2] is not None:
                self._detailed[2].close()
            try:
                reader = MBTiles(resolved[0])
            except Exception:  # noqa: BLE001 - a broken or vector file is no detailed map
                reader = None
            self._detailed = (*resolved, reader)
            return reader

    def detailed_name(self):
        reader = self.detailed()
        return reader.name if reader else None

    def forget(self, path: str) -> None:
        """A map file is about to be deleted: close it first."""
        with self.lock:
            if self._detailed and self._detailed[0] == path:
                if self._detailed[2] is not None:
                    self._detailed[2].close()
                self._detailed = None

    def world(self):
        with self.lock:  # opened once, whichever worker asks first
            if self._world is None:
                try:
                    self._world = MBTiles(WORLD_PATH)
                except Exception:  # noqa: BLE001
                    self._world = False
            return self._world or None

    # OpenStreetMap: saved tiles, then a download
    def cached(self, z: int, x: int, y: int):
        """(bytes, age in seconds) of a saved tile, or (None, None)."""
        path = os.path.join(cache_dir(), str(z), str(x), f"{y}.png")
        try:
            with open(path, "rb") as handle:
                return handle.read(), time.time() - os.path.getmtime(path)
        except OSError:
            return None, None

    def download(self, z: int, x: int, y: int):
        with self.lock:
            now = time.monotonic()
            if self.online.offline and now - self.last_try < OFFLINE_RETRY_S:
                return None
            self.last_try = now
            was = self.online.offline
        data = None
        with self.downloads:
            try:
                request = urllib.request.Request(OSM_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=4 if was else 10) as answer:
                    data = answer.read()
            except Exception:  # noqa: BLE001 - no network, a refusal, a timeout: all "failed"
                data = None
        with self.lock:
            (self.online.worked if data else self.online.failed)()
            changed = was != self.online.offline
        if data:
            folder = os.path.join(cache_dir(), str(z), str(x))
            try:
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, f"{y}.png.tmp"), "wb") as handle:
                    handle.write(data)
                os.replace(os.path.join(folder, f"{y}.png.tmp"), os.path.join(folder, f"{y}.png"))
            except OSError:
                pass
        if changed:
            GLib.idle_add(self._tell)
        return data

    def listen(self, method) -> None:
        """`method(offline)` on the main loop when the map goes offline or back online. Held
        weakly: a Zones screen that is gone stops listening by itself."""
        self.listeners.append(weakref.WeakMethod(method))

    def _tell(self) -> bool:
        for ref in list(self.listeners):
            method = ref()
            if method is None:
                self.listeners.remove(ref)
            else:
                method(self.online.offline)
        return False

    # One tile, from the first source that has it
    def tile(self, z: int, x: int, y: int):
        source, data = self.find(z, x, y)
        with self.lock:
            self.served[source] += 1
        return data

    def find(self, z: int, x: int, y: int) -> tuple:
        if z < 0 or x < 0 or y < 0 or x >= 1 << z or y >= 1 << z:
            return "none", None
        detailed = self.detailed()
        if detailed is not None:
            data = detailed.tile(z, x, y)
            if data:
                return "detailed", data
        saved, age = self.cached(z, x, y)
        if saved and age < FRESH_S:
            return "saved", saved
        data = self.download(z, x, y)
        if data:
            return "download", data
        if saved:
            return "saved", saved  # an old saved tile beats none
        world = self.world()
        if world is not None and z <= 3:
            data = world.tile(z, x, y)
            if data:
                return "world", data
        data = self.approximate(z, x, y, detailed, world)
        return ("scaled" if data else "none"), data

    def ancestor(self, z: int, x: int, y: int, detailed, world):
        if detailed is not None:
            data = detailed.tile(z, x, y)
            if data:
                return data
        data, _age = self.cached(z, x, y)
        if data:
            return data
        if world is not None and z <= 3:
            return world.tile(z, x, y)
        return None

    def approximate(self, z: int, x: int, y: int, detailed, world):
        """The nearest ancestor that some source has, cut to this tile's part and scaled up: the
        detailed map first, then a saved OpenStreetMap tile, then the world overview."""
        for dz in range(1, z + 1):
            data = self.ancestor(z - dz, x >> dz, y >> dz, detailed, world)
            if data:
                return scale_part(data, dz, x - ((x >> dz) << dz), y - ((y >> dz) << dz))
        return None

    # For the data source: the work off the main loop, the answer on it
    def request(self, z: int, x: int, y: int, cancellable, deliver) -> None:
        self.asked[z] = self.asked.get(z, 0) + 1

        def work() -> None:
            data = None
            if cancellable is None or not cancellable.is_cancelled():
                try:
                    data = self.tile(z, x, y)
                except Exception:  # noqa: BLE001 - a tile that fails is a tile not shown
                    data = None
            GLib.idle_add(lambda: deliver(data) or False)

        self.pool.submit(work)

    def renderer(self):
        """A new renderer over these tiles (a map rebuilds it when the detailed map changes, or
        when the network is back and the tiles scaled up offline should go)."""
        return Shumate.RasterRenderer.new_full("meshsat", "OpenStreetMap", maps.ONLINE, "https://www.openstreetmap.org/copyright", MIN_ZOOM, MAX_ZOOM, TILE_SIZE,
                                               Shumate.MapProjection.MERCATOR, TileSource(self))


if Shumate is not None:
    class TileSource(Shumate.DataSource):
        __gtype_name__ = "MeshSatTileSource"

        def __init__(self, tiles: Tiles):
            super().__init__()
            self.tiles = tiles

        def do_start_request(self, x, y, zoom, cancellable):
            request = Shumate.DataSourceRequest.new(x, y, zoom)

            def deliver(data) -> None:
                if data:
                    request.emit_data(GLib.Bytes.new(data), True)
                else:
                    request.emit_error(GLib.Error.new_literal(Gio.io_error_quark(), "No tile here", Gio.IOErrorEnum.NOT_FOUND))

            self.tiles.request(zoom, x, y, cancellable, deliver)
            return request


def scale_part(data: bytes, dz: int, sx: int, sy: int):
    """Part (sx, sy) of a tile cut 2^dz times each way, scaled back up to a whole tile."""
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pixbuf = loader.get_pixbuf()
        size = pixbuf.get_width()
        part = max(1, size >> dz)
        left = min((sx * size) >> dz, size - part)
        top = min((sy * size) >> dz, size - part)
        scaled = pixbuf.new_subpixbuf(left, top, part, part).scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        ok, buffer = scaled.save_to_bufferv("png", [], [])
        return bytes(buffer) if ok else None
    except (GLib.Error, TypeError):
        return None


def trim_cache() -> None:
    """Saved tiles past CACHE_LIMIT go, the oldest first, down to three quarters of it."""
    files = []
    total = 0
    for folder, _dirs, names in os.walk(cache_dir()):
        for name in names:
            path = os.path.join(folder, name)
            try:
                info = os.stat(path)
            except OSError:
                continue
            files.append((info.st_mtime, info.st_size, path))
            total += info.st_size
    if total <= CACHE_LIMIT:
        return
    for _mtime, size, path in sorted(files):
        try:
            os.remove(path)
        except OSError:
            continue
        total -= size
        if total <= CACHE_LIMIT * 3 // 4:
            return
