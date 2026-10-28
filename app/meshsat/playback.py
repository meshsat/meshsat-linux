# SPDX-License-Identifier: GPL-3.0-or-later
"""Sound and pictures for the voice notes and photos (MESHSAT-1735), through what a Linux
phone has: GStreamer plays an Opus note (playbin on the Ogg file written under the runtime
directory, as Android's MediaPlayer plays a temporary file) and records one (the microphone
into opusenc and oggmux, mono, 48 kHz, 16 kbit/s, the bytes a standard Ogg Opus file as
Sideband writes); a Codec2 note is decoded by pycodec2 when the phone has it (the packed frames
at the mode's frame size into 8 kHz 16-bit mono, played as a WAV), else named and kept as on
Android; GdkPixbuf shows a photo and, with its WebP loader, makes one small enough, Pillow
otherwise (media.py). One note plays at a time, as Android's VoiceNotePlayer.

MESHSAT_APP_AUDIO_SOURCE replaces the microphone with any GStreamer source (the tests:
audiotestsrc), as MESHSAT_APP_SCAN_SOURCE replaces the camera."""
import os
import struct
import tempfile
import time

from gi.repository import GLib

from . import media, trace
from .model import attachments as words

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    Gst.init(None)
except (ValueError, ImportError):
    Gst = None

try:
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
except (ValueError, ImportError, NameError):
    GdkPixbuf = None


def temp_dir() -> str:
    return os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()


def temp_file(suffix: str, data: bytes) -> str:
    handle, path = tempfile.mkstemp(prefix="meshsat-note-", suffix=suffix, dir=temp_dir())
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    return path


def has_element(name: str) -> bool:
    return Gst is not None and Gst.ElementFactory.find(name) is not None


# ── Codec2 ───────────────────────────────────────────────────────────────────────────────────
_codec2_checked = None


def codec2_available() -> bool:
    """pycodec2 (the LGPL codec2 library's Python binding) is importable on this device."""
    global _codec2_checked
    if _codec2_checked is None:
        try:
            import pycodec2  # noqa: F401, PLC0415

            _codec2_checked = True
        except ImportError:
            _codec2_checked = False
    return _codec2_checked


def can_play(mode: int) -> bool:
    """Whether this phone plays a note of this mode: Opus through GStreamer, Codec2 through
    pycodec2 when it is there (never 450 and 450PWB, which no client decodes)."""
    if words.is_opus(mode):
        return Gst is not None and has_element("playbin")
    return words.is_codec2(mode) and words.codec2_decodable(mode) and codec2_available() and Gst is not None


def decode_codec2(mode: int, data: bytes) -> bytes:
    """The PCM (8 kHz, 16-bit, mono, little-endian) of the whole frames in `data`."""
    import pycodec2  # noqa: PLC0415

    rate = words.CODEC2_GEOMETRY[mode][2]
    codec = None
    for name in (rate, str(rate), f"{rate}C" if rate == 700 else None):
        if name is None:
            continue
        try:
            codec = pycodec2.Codec2(name)
            break
        except (ValueError, TypeError, KeyError):
            continue
    if codec is None:
        raise ValueError(f"pycodec2 does not open mode {rate}")
    per = codec.bytes_per_frame() if hasattr(codec, "bytes_per_frame") else words.codec2_bytes_per_frame(mode)
    out = bytearray()
    for i in range(0, len(data) - per + 1, per):
        samples = codec.decode(bytes(data[i:i + per]))
        out += samples.astype("<i2").tobytes() if hasattr(samples, "astype") else bytes(samples)
    return bytes(out)


def wav_bytes(pcm: bytes, rate: int = words.CODEC2_RATE) -> bytes:
    """A WAV file around 16-bit mono PCM."""
    head = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm))
    return head + pcm


# ── The player (audio/VoiceNotePlayer.kt) ────────────────────────────────────────────────────
class Player:
    """Plays one note at a time: `play(id, data, mode)` stops whatever sounds and starts this
    one; `playing` names it; `error` the last failure's words; `listen(fn)` is told on every
    change (on the main loop)."""

    def __init__(self):
        self.playing = None
        self.error = ""
        self.pipeline = None
        self.path = None
        self.listeners = []

    def listen(self, fn) -> None:
        self.listeners.append(fn)

    def unlisten(self, fn) -> None:
        if fn in self.listeners:
            self.listeners.remove(fn)

    def _changed(self) -> None:
        for fn in list(self.listeners):
            fn()

    def play(self, note_id, data: bytes, mode: int) -> None:
        self.stop()
        self.error = ""
        if Gst is None:
            self.error = "cannot play this note (no GStreamer)"
            self._changed()
            return
        try:
            if words.is_codec2(mode):
                sound = wav_bytes(decode_codec2(mode, data))
                self.path = temp_file(".wav", sound)
            else:
                self.path = temp_file(".ogg", data)
            self.pipeline = Gst.parse_launch(f'playbin uri="{GLib.filename_to_uri(self.path, None)}"')
        except (GLib.Error, ValueError, ImportError, OSError) as error:
            self.error = f"cannot play this note ({error})"
            self._clean()
            self._changed()
            return
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._message, self.pipeline)
        self.pipeline.set_state(Gst.State.PLAYING)
        self.playing = note_id
        trace.event("play", note=str(note_id), mode=mode, bytes=len(data))
        self._changed()

    def _message(self, _bus, message, pipeline) -> None:
        if pipeline is not self.pipeline:
            return
        if message.type == Gst.MessageType.EOS:
            self.stop()
        elif message.type == Gst.MessageType.ERROR:
            error, _debug = message.parse_error()
            self.error = f"cannot play this note ({error.message})"
            self.stop(keep_error=True)

    def stop(self, keep_error: bool = False) -> None:
        was = self.playing
        self._clean()
        self.playing = None
        if not keep_error:
            self.error = ""
        if was is not None or keep_error:
            self._changed()

    def _clean(self) -> None:
        if self.pipeline is not None:
            try:
                self.pipeline.get_bus().remove_signal_watch()
                self.pipeline.set_state(Gst.State.NULL)
            except GLib.Error:
                pass
            self.pipeline = None
        if self.path:
            try:
                os.remove(self.path)
            except OSError:
                pass
            self.path = None


PLAYER = Player()


# ── The recorder (audio/VoiceRecorder.kt) ────────────────────────────────────────────────────
def audio_source() -> str:
    return os.environ.get("MESHSAT_APP_AUDIO_SOURCE") or "autoaudiosrc"


def recorder_available() -> bool:
    """GStreamer with an Opus encoder and the Ogg muxer: what writes the note."""
    return Gst is not None and has_element("opusenc") and has_element("oggmux")


class Recorder:
    """The microphone while a note is held: a GStreamer pipeline into an Ogg Opus file in the
    runtime directory, mono, 48 kHz, a 16 kbit/s ceiling. `start()` raises with the reason when
    the microphone cannot be opened; `stop()` ends the file and returns its bytes (empty for a
    press that recorded nothing); `elapsed_ms()` while it runs; it stops itself at `max_ms`."""

    def __init__(self, max_ms: int = words.MAX_NOTE_MS, max_bytes: int = words.MAX_BYTES):
        self.max_ms, self.max_bytes = max_ms, max_bytes
        self.pipeline = None
        self.path = None
        self.started = 0.0
        self.hit_max = False

    def start(self) -> None:
        if not recorder_available():
            raise RuntimeError(words.NO_ENCODER)
        handle, self.path = tempfile.mkstemp(prefix="meshsat-rec-", suffix=".ogg", dir=temp_dir())
        os.close(handle)
        location = self.path.replace("\\", "\\\\").replace('"', '\\"')
        try:
            self.pipeline = Gst.parse_launch(f"{audio_source()} ! audioconvert ! audioresample ! audio/x-raw,rate=48000,channels=1 ! "
                                             f'opusenc bitrate=16000 bitrate-type=vbr ! oggmux ! filesink location="{location}"')
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise GLib.Error(words.MICROPHONE_FAILED)
            # A source that fails to open says so on the bus within a moment
            message = self.pipeline.get_bus().timed_pop_filtered(300 * Gst.MSECOND, Gst.MessageType.ERROR)
            if message is not None:
                error, _debug = message.parse_error()
                raise GLib.Error(error.message)
        except GLib.Error as error:
            self._drop()
            raise RuntimeError(f"{words.MICROPHONE_FAILED[:-1]}: {error.message}" if error.message != words.MICROPHONE_FAILED else words.MICROPHONE_FAILED) from error
        self.started = time.monotonic()
        self.hit_max = False
        trace.event("record", state="start", source=audio_source())

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000) if self.started else 0

    def stop(self) -> bytes:
        if self.pipeline is None:
            return b""
        pipeline, self.pipeline = self.pipeline, None
        pipeline.send_event(Gst.Event.new_eos())
        bus = pipeline.get_bus()
        bus.timed_pop_filtered(2 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        pipeline.set_state(Gst.State.NULL)
        data = b""
        try:
            with open(self.path, "rb") as handle:
                data = handle.read()
        except OSError:
            pass
        self._drop()
        trace.event("record", state="stop", bytes=len(data), ms=self.elapsed_ms())
        return data if words.looks_like_ogg_opus(data) else b""

    def cancel(self) -> None:
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        self._drop()

    def _drop(self) -> None:
        if self.pipeline is not None:
            try:
                self.pipeline.set_state(Gst.State.NULL)
            except GLib.Error:
                pass
            self.pipeline = None
        if self.path:
            try:
                os.remove(self.path)
            except OSError:
                pass
            self.path = None


# ── Photos (media/PhotoShrinker.kt, VoiceNote.kt's PhotoCard) ───────────────────────────────
def pixbuf_formats() -> dict:
    """GdkPixbuf's loaders by name, with whether each one writes."""
    if GdkPixbuf is None:
        return {}
    return {f.get_name(): f.is_writable() for f in GdkPixbuf.Pixbuf.get_formats()}


def load_pixbuf(data: bytes):
    """A picture's pixels as a Pixbuf: GdkPixbuf's own loaders first (WebP needs
    webp-pixbuf-loader, which Mobian may lack), Pillow's pixels otherwise; None when neither
    reads it."""
    if GdkPixbuf is None:
        return None
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pixbuf = loader.get_pixbuf()
        if pixbuf is not None:
            return pixbuf.apply_embedded_orientation() or pixbuf
    except GLib.Error:
        pass
    rgb = media.photo_rgb_pil(data)
    if rgb is None:
        return None
    width, height, alpha, pixels = rgb
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pixels), GdkPixbuf.Colorspace.RGB, alpha, 8, width, height, width * (4 if alpha else 3))


def shrink_photo(data: bytes, budget: int) -> bytes | None:
    """A photo down to a WebP that fits `budget`: GdkPixbuf's WebP saver when the phone has it,
    else Pillow's; None when neither can, or the picture cannot be read."""
    if pixbuf_formats().get("webp"):
        pixbuf = load_pixbuf(data)
        if pixbuf is not None:
            edge = words.MAX_EDGE
            while edge >= 64:
                long_edge = max(pixbuf.get_width(), pixbuf.get_height())
                picture = pixbuf
                if long_edge > edge:
                    factor = edge / long_edge
                    picture = pixbuf.scale_simple(max(1, int(pixbuf.get_width() * factor)), max(1, int(pixbuf.get_height() * factor)), GdkPixbuf.InterpType.BILINEAR)
                for quality in words.QUALITIES:
                    try:
                        ok, out = picture.save_to_bufferv("webp", ["quality"], [str(quality)])
                    except GLib.Error:
                        ok, out = False, b""
                    if ok and len(out) <= budget:
                        return bytes(out)
                edge //= 2
    return media.shrink_photo_pil(data, budget)
