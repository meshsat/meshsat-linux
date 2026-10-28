# SPDX-License-Identifier: GPL-3.0-or-later
"""The voice notes and photos of the chat, as this app holds them (MESHSAT-1735): the list an
LXMF message carries, asked of the Bridge once per message and kept (an empty list and a 404
kept too, so a chat of plain texts costs one call per message and no more); the bytes, fetched
on the first play or view and kept up to a budget; the note and photo this app just sent, kept
in memory under the sent record's id until the Bridge's own row for the message appears; and a
photo made small enough for one message, through Pillow (the GdkPixbuf path lives in
playback.py beside the players). No GTK here: the unit tests run it against the scripted
Bridge on the runner. Android keeps the same bytes in a Room table, 16 MiB at most; here the
Bridge's store (16 MiB, lxmf_attachments) is the record and this is a cache."""
import io
import threading
import urllib.error
import urllib.request

from . import api, trace
from .model import attachments as words

try:
    from gi.repository import GLib
except (ImportError, ValueError):  # the unit tests, on a machine without GTK
    GLib = None

BYTES_BUDGET = 8 * 1024 * 1024  # what the bytes cache keeps before the oldest go
LIST_PATH = "/api/lxmf/messages/{id}/attachments"


def _on_main(fn, *args) -> None:
    if GLib is not None:
        GLib.idle_add(lambda: fn(*args) or False)
    else:
        fn(*args)


def fetch_bytes(path: str, timeout: float = 20.0) -> tuple:
    """One attachment's bytes from the Bridge, on the calling thread: (status, content type,
    the LXMF audio mode from X-LXMF-Audio-Mode or 0, bytes). Status 0 when the Bridge did not
    answer."""
    req = urllib.request.Request(api.BRIDGE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            mode = response.headers.get("X-LXMF-Audio-Mode") or "0"
            try:
                mode = int(mode)
            except ValueError:
                mode = 0
            out = (response.status, response.headers.get("Content-Type") or "", mode, data)
    except urllib.error.HTTPError as error:
        out = (error.code, "", 0, b"")
    except (OSError, urllib.error.URLError):
        out = (0, "", 0, b"")
    trace.event("http", method="GET", path=path, status=out[0], bytes=len(out[3]))
    return out


class Attachments:
    """The cache: `listing(message, on_done)` hands `on_done(list)` the message's attachments
    (now, when known; else once the Bridge answered, on the main loop), `data(message_id, item,
    on_done)` the bytes of one. A message this app sent and the Bridge has not filed yet (a
    negative id, the sent log's) is answered from `pending`."""

    def __init__(self):
        self.lists = {}  # message id -> [attachment dicts]
        self.bytes = {}  # (message id, index) -> bytes
        self.pending = {}  # a local sent record's id -> [attachment dicts with "data"]
        self.waiting = {}  # message id -> [on_done] while the Bridge is asked
        self.order = []  # (message id, index) oldest first, for the budget
        self.lock = threading.Lock()

    # The list
    def known(self, message_id) -> list | None:
        """The list when it is cached (or pending), else None."""
        if message_id in self.pending:
            return [dict(a) for a in self.pending[message_id]]
        return self.lists.get(message_id)

    def listing(self, message: dict, on_done) -> None:
        message_id = message.get("id")
        if message_id is None:
            on_done([])
            return
        known = self.known(message_id)
        if known is not None:
            on_done(known)
            return
        if message_id < 0:
            on_done([])  # a local record with nothing attached
            return
        with self.lock:
            if message_id in self.waiting:
                self.waiting[message_id].append(on_done)
                return
            self.waiting[message_id] = [on_done]
        api.fetch(LIST_PATH.format(id=message_id), lambda answer: self._listed(message_id, answer))

    def _listed(self, message_id, answer: api.Answer) -> None:
        if answer.ok:
            items = words.listed(answer.body)
        elif answer.status in (404, 400):
            items = []  # not an LXMF message, or one with nothing attached: remembered as empty
        elif answer.down or answer.status >= 500 or answer.status == 429:
            items = None  # the Bridge is away or busy: ask again later
        else:
            items = []
        with self.lock:
            callbacks = self.waiting.pop(message_id, [])
            if items is not None:
                self.lists[message_id] = items
        for fn in callbacks:
            _on_main(fn, items or [])

    # The bytes
    def cached(self, message_id, index: int) -> bytes | None:
        for a in self.pending.get(message_id, []):
            if a.get("index") == index:
                return a.get("data")
        return self.bytes.get((message_id, index))

    def data(self, message_id, item: dict, on_done) -> None:
        """`on_done(bytes or None, mode)` with the attachment's bytes, from the cache or the
        Bridge (off the main loop; the answer on it)."""
        index = item.get("index", 0)
        have = self.cached(message_id, index)
        if have is not None:
            on_done(have, item.get("mode", 0))
            return
        path = item.get("url") or f"{LIST_PATH.format(id=message_id)}/{index}"

        def run() -> None:
            status, _ctype, mode, data = fetch_bytes(path)
            if 200 <= status < 300 and data:
                self.keep(message_id, index, data)
                _on_main(on_done, data, mode or item.get("mode", 0))
            else:
                _on_main(on_done, None, item.get("mode", 0))

        threading.Thread(target=run, daemon=True).start()

    def keep(self, message_id, index: int, data: bytes) -> None:
        with self.lock:
            key = (message_id, index)
            if key in self.bytes:
                self.order.remove(key)
            self.bytes[key] = data
            self.order.append(key)
            total = sum(len(v) for v in self.bytes.values())
            while total > BYTES_BUDGET and len(self.order) > 1:
                old = self.order.pop(0)
                total -= len(self.bytes.pop(old))

    # What this app sent
    def put_pending(self, record_id, items: list) -> None:
        """The note and the photo of a message this app just sent, under its sent record's id,
        each {"kind", "mode", "format", "size", "data"} in the Bridge's order (the image first)."""
        ordered = sorted(items, key=lambda a: 0 if a["kind"] == words.KIND_IMAGE else 1)
        self.pending[record_id] = [dict(a, index=i, content_type=words.content_type(a["kind"], a.get("mode", 0), a.get("format", "")), url="")
                                   for i, a in enumerate(ordered)]

    def forget(self) -> None:
        with self.lock:
            self.lists.clear()
            self.bytes.clear()
            self.order.clear()
            self.pending.clear()


CACHE = Attachments()


def shrink_photo_pil(data: bytes, budget: int) -> bytes | None:
    """A picture down to a WebP that fits `budget` (PhotoShrinker.kt through Pillow): the long
    edge at most MAX_EDGE, then the quality and the edge come down until the bytes fit; the
    picture's own rotation applied first. None when it cannot be read or made small enough, or
    when Pillow is not there."""
    try:
        from PIL import Image, ImageOps  # noqa: PLC0415
    except ImportError:
        return None
    try:
        source = Image.open(io.BytesIO(data))
        source.load()
        source = ImageOps.exif_transpose(source)
    except (OSError, ValueError):
        return None
    if source.mode not in ("RGB", "RGBA"):
        source = source.convert("RGB")
    edge = words.MAX_EDGE
    while edge >= 64:
        picture = source
        long_edge = max(source.width, source.height)
        if long_edge > edge:
            factor = edge / long_edge
            picture = source.resize((max(1, int(source.width * factor)), max(1, int(source.height * factor))), Image.LANCZOS)
        for quality in words.QUALITIES:
            out = io.BytesIO()
            try:
                picture.save(out, format="WEBP", quality=quality, method=4)
            except (OSError, ValueError, KeyError):
                return None
            if out.tell() <= budget:
                return out.getvalue()
        edge //= 2
    return None


def photo_rgb_pil(data: bytes) -> tuple | None:
    """A photo's pixels through Pillow, for a screen without GdkPixbuf's WebP loader: (width,
    height, has alpha, the bytes in RGB or RGBA rows); None when it cannot be read."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return None
    try:
        picture = Image.open(io.BytesIO(data))
        picture.load()
    except (OSError, ValueError):
        return None
    alpha = picture.mode in ("RGBA", "LA") or (picture.mode == "P" and "transparency" in picture.info)
    picture = picture.convert("RGBA" if alpha else "RGB")
    return picture.width, picture.height, alpha, picture.tobytes()
