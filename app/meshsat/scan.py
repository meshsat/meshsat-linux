# SPDX-License-Identifier: GPL-3.0-or-later
"""The QR scanner, as MeshSat Android's (zxing's CaptureActivity, ContactCards.kt:100-116,
SettingsScreen.kt:283-344, 863-884, 1693-1710): the camera with the caller's prompt, QR codes
only, closed on the first code, its text handed back; cancelled, nothing. The camera is
libcamera's through GStreamer (the PinePhone Pro's rear camera by preference), decoded by
GStreamer's zbar element and shown through GTK 4's own video sink. Linux adds "Open an image"
(a photo or a screenshot of a code), for a phone or a desktop with no camera; a code read from a
file counts as imported, not as scanned in person.

MESHSAT_APP_SCAN_SOURCE replaces the camera with any GStreamer source (the tests show it a PNG
of a code), MESHSAT_APP_CAMERA names the libcamera camera to use."""
import os
import threading

from gi.repository import Adw, GLib, Gtk

from . import files, theme, trace
from .widgets import name_widget, text, text_button

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    Gst.init(None)
except (ValueError, ImportError):
    Gst = None

CAMERA, IMAGE = "camera", "image"
OPEN_IMAGE = "Open an image"
NO_CODE = "No QR code in that image."
REAR = "camera@1a"  # the PinePhone Pro's IMX258 (the front OV8858 is camera@36)


def camera_source() -> str:
    source = os.environ.get("MESHSAT_APP_SCAN_SOURCE")
    if source:
        return source
    name = os.environ.get("MESHSAT_APP_CAMERA") or rear_camera()
    return f'libcamerasrc camera-name="{name}"' if name else "libcamerasrc"


def rear_camera() -> str:
    """The camera on the back, where there is one to choose; else libcamera's own first."""
    if Gst is None:
        return ""
    try:
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Video/Source", None)
        monitor.start()
        names = [d.get_display_name() for d in monitor.get_devices()]
        monitor.stop()
    except GLib.Error:
        return ""
    return next((n for n in names if n.endswith(REAR)), "")


def decode_image(path: str, timeout_s: float = 5.0):
    """The text of the first QR code in an image file, or None. Blocking."""
    if Gst is None:
        return None
    location = path.replace("\\", "\\\\").replace('"', '\\"')
    try:
        pipeline = Gst.parse_launch(f'filesrc location="{location}" ! decodebin ! videoconvert ! imagefreeze num-buffers=4 ! videoconvert ! zbar ! fakesink')
    except GLib.Error:
        return None
    found = None
    pipeline.set_state(Gst.State.PLAYING)
    bus = pipeline.get_bus()
    deadline = GLib.get_monotonic_time() + int(timeout_s * 1e6)
    while GLib.get_monotonic_time() < deadline:
        message = bus.timed_pop_filtered(200 * Gst.MSECOND, Gst.MessageType.ELEMENT | Gst.MessageType.EOS | Gst.MessageType.ERROR)
        if message is None:
            continue
        if message.type == Gst.MessageType.ELEMENT:
            found = qr_text(message)
            if found is not None:
                break
        else:
            break
    pipeline.set_state(Gst.State.NULL)
    return found


def qr_text(message):
    s = message.get_structure()
    if s is None or s.get_name() != "barcode":
        return None
    kind = s.get_string("type") or ""
    return s.get_string("symbol") if kind.upper().startswith("QR") else None


class Scanner:
    """`on_text(text, how)`: the code's text and CAMERA or IMAGE, or (None, None) when the person
    closed it. `on_error(reason)` when the camera cannot start (the caller's own words go
    around it)."""

    def __init__(self, app, prompt: str, on_text, on_error=None):
        self.app, self.prompt, self.on_text, self.on_error = app, prompt, on_text, on_error
        self.pipeline = None
        self.done = False
        self.dialog = Adw.Dialog(title=prompt, content_width=360)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        box.add_css_class("sheet")
        box.append(text(prompt, "dialog-title", wrap=True))
        self.picture = Gtk.Picture()
        self.picture.add_css_class("scanner-view")
        self.picture.set_size_request(theme.dp(300), theme.dp(300))
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        name_widget(self.picture, prompt)
        box.append(self.picture)
        self.status = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        self.status.set_visible(False)
        box.append(self.status)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
        buttons.set_halign(Gtk.Align.END)
        buttons.append(text_button(OPEN_IMAGE, self.open_image))
        buttons.append(text_button("Cancel", self.cancel))
        box.append(buttons)
        self.dialog.set_child(box)
        self.dialog.connect("closed", lambda *_: self.finish(None, None))

    def present(self) -> None:
        self.dialog.present(self.app.window)
        self.start()

    def start(self) -> None:
        if Gst is None:
            self.failed("GStreamer is not installed")
            return
        description = (f"{camera_source()} ! videoconvert ! tee name=t "
                       "t. ! queue leaky=downstream max-size-buffers=1 ! videoscale ! video/x-raw,width=640 ! videoconvert ! zbar ! fakesink sync=false "
                       "t. ! queue leaky=downstream max-size-buffers=1 ! videoconvert ! gtk4paintablesink name=sink")
        try:
            self.pipeline = Gst.parse_launch(description)
        except GLib.Error as error:
            self.failed(error.message)
            return
        sink = self.pipeline.get_by_name("sink")
        if sink is not None:
            self.picture.set_paintable(sink.get_property("paintable"))
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::element", self.on_element)
        bus.connect("message::error", lambda _b, m: self.failed(m.parse_error()[0].message))
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.failed("the camera did not start")
        trace.event("scanner", prompt=self.prompt, source=camera_source())

    def failed(self, reason: str) -> None:
        self.stop()
        self.status.set_text(reason)
        self.status.set_visible(True)
        trace.event("scanner-error", reason=reason)
        if self.on_error is not None:
            self.on_error(reason)

    def on_element(self, _bus, message) -> None:
        found = qr_text(message)
        if found is not None and not self.done:
            self.finish(found, CAMERA)

    def open_image(self) -> None:
        def picked(gfile) -> None:
            if gfile is None or not gfile.get_path():
                return
            path = gfile.get_path()

            def work() -> None:
                found = decode_image(path)
                GLib.idle_add(lambda: self.from_image(found) or False)

            threading.Thread(target=work, daemon=True).start()

        files.pick_file(self.app, OPEN_IMAGE, picked, patterns=("*.png", "*.jpg", "*.jpeg"))

    def from_image(self, found) -> None:
        if found is None:
            self.status.set_text(NO_CODE)
            self.status.set_visible(True)
            return
        self.finish(found, IMAGE)

    def cancel(self) -> None:
        self.finish(None, None)

    def stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            bus = self.pipeline.get_bus()
            bus.remove_signal_watch()
            self.pipeline = None

    def finish(self, found, how) -> None:
        if self.done:
            return
        self.done = True
        self.stop()
        self.dialog.close()
        trace.event("scanned", how=how or "", length=len(found or ""))
        self.on_text(found, how)
