# SPDX-License-Identifier: GPL-3.0-or-later
"""The voice note and the photo in the chat (MESHSAT-1735), as ui/components/VoiceNote.kt: the
microphone that records while held (a 48 dp round button, red while recording, "Recording,
4.2 s" as its name; with a screen reader, where holding is awkward, a click starts and a second
click stops), the rows for a note and a photo waiting to go, each with its size and a cross,
the card of a received note with play and stop (or the "playback not supported" line of a
Codec2 note this phone cannot decode, the bytes offered to save), and a photo shown inline. The
words are model/attachments.py's; the sound and the pictures playback.py's."""
import time

from gi.repository import Gdk, GLib, Gtk

from . import files, playback, theme
from .model import attachments as words
from .widgets import icon, icon_button, name_widget, text, text_button


class RecordButton(Gtk.Button):
    """RecordNoteButton: `on_note(ogg_bytes, ms)` once a held press ends with a note; the app's
    toast for a press that recorded nothing, a note too long for one message, or a microphone
    that could not be opened."""

    def __init__(self, app, on_note):
        super().__init__()
        self.app, self.on_note = app, on_note
        self.add_css_class("record")
        self.set_valign(Gtk.Align.CENTER)
        self.recorder = None
        self._timer = None
        self._pressed = False
        self._held = False
        self._gesture_at = 0.0  # when a finger last left the button: its own click follows and is not a second note
        self.image = icon("filled-mic", 24, theme.SIGNAL_ORANGE if playback.recorder_available() else theme.TEXT_MUTED)
        self.set_child(self.image)
        name_widget(self, words.HOLD_TO_RECORD)
        self.set_tooltip_text(words.HOLD_TO_RECORD)
        press = Gtk.GestureClick()
        press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        press.connect("pressed", self._pressed_at)
        press.connect("released", self._released)
        press.connect("cancel", lambda *_: self._released(None, 0, 0, 0))
        self.add_controller(press)
        self.connect("clicked", self._clicked)
        self.connect("unmap", lambda *_: self.cancel())

    @property
    def holding(self) -> bool:
        return self.recorder is not None

    def _pressed_at(self, _gesture, _n, _x, _y) -> None:
        self._pressed = True
        self._held = self.begin()

    def _released(self, _gesture, _n, _x, _y) -> None:
        if self._pressed:
            self._gesture_at = time.monotonic()
        if self._pressed and self._held:
            self.end()
        self._pressed = False
        self._held = False

    def _clicked(self, *_) -> None:
        """No press reached the gesture (a screen reader's activation, the tests): a click starts
        the note and the next one ends it, as Android's click action with TalkBack. The click
        that follows a finger's own release is not one."""
        if self._pressed or self._held or time.monotonic() - self._gesture_at < 0.5:
            return
        if self.holding:
            self.end()
        else:
            self.begin()

    def begin(self) -> bool:
        if not self.get_sensitive() or self.holding:
            return False
        if not playback.recorder_available():
            self.app.toast(words.NO_ENCODER)
            return False
        recorder = playback.Recorder()
        try:
            recorder.start()
        except RuntimeError as error:
            self.app.toast(str(error) or words.MICROPHONE_FAILED)
            return False
        self.recorder = recorder
        self.add_css_class("holding")
        self._paint()
        self._timer = GLib.timeout_add(100, self._tick)
        return True

    def _tick(self) -> bool:
        if self.recorder is None:
            self._timer = None
            return False
        self._paint()
        if self.recorder.elapsed_ms() >= words.MAX_NOTE_MS:
            self._timer = None
            self.end()
            return False
        return True

    def _paint(self) -> None:
        holding = self.holding
        label = words.recording_label(self.recorder.elapsed_ms()) if holding else words.HOLD_TO_RECORD
        name_widget(self, label, words.STOP_RECORDING if holding else words.START_RECORDING)
        self.set_tooltip_text(label)
        self.set_child(icon("filled-mic", 24, theme.RED if holding else theme.SIGNAL_ORANGE if playback.recorder_available() else theme.TEXT_MUTED))

    def end(self) -> None:
        recorder = self.recorder
        if recorder is None:
            return
        self.recorder = None
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        ms = recorder.elapsed_ms()
        data = recorder.stop()
        self.remove_css_class("holding")
        self._paint()
        if not data:
            self.app.toast(words.HOLD_WHILE_YOU_SPEAK)
            return
        if len(data) > words.MAX_BYTES:
            self.app.toast(words.too_long(len(data)))
            return
        self.on_note(data, min(ms, words.MAX_NOTE_MS))

    def cancel(self) -> None:
        if self.recorder is not None:
            self.recorder.cancel()
            self.recorder = None
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self.remove_css_class("holding")


def pending_row(label: str, on_remove, lead: Gtk.Widget) -> Gtk.Box:
    """PendingRow: the lead (play, or a thumbnail), the words in bodySmall TextSecondary, a
    small cross."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
    row.add_css_class("pending-row")
    row.append(lead)
    label_widget = text(label, "body-small", theme.TEXT_SECONDARY, ellipsize=True)
    label_widget.set_hexpand(True)
    label_widget.set_valign(Gtk.Align.CENTER)
    row.append(label_widget)
    row.append(icon_button("outlined-close", on_remove, 16, theme.TEXT_MUTED, tooltip=words.REMOVE, small=True))
    return row


class PlayButton(Gtk.Button):
    """Play, or Stop while this note sounds (one note at a time, through playback.PLAYER)."""

    def __init__(self, note_id, data_fn, mode: int, size: int = 36, play_label: str = words.PLAY_VOICE_NOTE):
        super().__init__()
        self.add_css_class("icon-button")
        self.note_id, self.data_fn, self.mode, self.play_label = note_id, data_fn, mode, play_label
        self.set_valign(Gtk.Align.CENTER)
        self.set_size_request(theme.dp(size), theme.dp(size))
        self.connect("clicked", self._clicked)
        self.connect("map", lambda *_: playback.PLAYER.listen(self._paint))
        self.connect("unmap", lambda *_: playback.PLAYER.unlisten(self._paint))
        self._paint()

    @property
    def mine(self) -> bool:
        return playback.PLAYER.playing == self.note_id

    def _paint(self) -> None:
        mine = self.mine
        self.set_child(icon("filled-stop" if mine else "filled-play-arrow", 24, theme.SIGNAL_ORANGE))
        name_widget(self, words.STOP if mine else self.play_label)
        self.set_tooltip_text(words.STOP if mine else self.play_label)

    def _clicked(self, *_) -> None:
        if self.mine:
            playback.PLAYER.stop()
            return

        def play(data: bytes | None, mode: int) -> None:
            if data is None:
                playback.PLAYER.error = "cannot play this note (the Bridge did not give its bytes)"
                playback.PLAYER._changed()
                return
            playback.PLAYER.play(self.note_id, data, mode or self.mode)

        self.data_fn(play)


def pending_audio_row(data: bytes, ms: int, on_remove) -> Gtk.Box:
    play = PlayButton(("pending", "audio"), lambda done: done(data, words.AUDIO_OPUS_OGG), words.AUDIO_OPUS_OGG, size=32, play_label=words.PLAY_NOTE)
    return pending_row(words.pending_audio_label(ms, len(data)), on_remove, play)


def pending_image_row(data: bytes, on_remove) -> Gtk.Box:
    lead = picture_widget(data, theme.dp(32), theme.dp(32), words.THE_PHOTO_TO_SEND) or icon("filled-add-photo-alternate", 24, theme.TEXT_MUTED)
    return pending_row(words.pending_image_label(len(data)), on_remove, lead)


def picture_widget(data: bytes, width: int, height: int, description: str) -> Gtk.Widget | None:
    """A picture's pixels in a Gtk.Picture, or None when nothing on this phone reads them."""
    pixbuf = playback.load_pixbuf(data)
    if pixbuf is None:
        return None
    picture = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
    picture.set_content_fit(Gtk.ContentFit.COVER if width == height else Gtk.ContentFit.SCALE_DOWN)
    picture.set_size_request(width, height)
    picture.set_can_shrink(True)
    picture.add_css_class("photo")
    picture.update_property([Gtk.AccessibleProperty.LABEL], [description])
    return picture


class VoiceNoteCard(Gtk.Box):
    """VoiceNoteCard: play/stop and "Voice note, 4.2 s, 7 KB" for a note this phone plays; a
    microphone, "Voice note (Codec2 700C), 7 KB" and the "playback not supported" line for one
    it cannot, with the bytes offered to save (this edition's own)."""

    def __init__(self, app, message_id, attachment: dict, cache):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(6))
        self.add_css_class("note-card")
        self.set_margin_top(theme.dp(6))
        self.app, self.message_id, self.attachment, self.cache = app, message_id, attachment, cache
        self.index = attachment.get("index", 0)
        self.played = False
        mode = attachment.get("mode", 0)
        playable = playback.can_play(mode)
        if playable:
            self.append(PlayButton((message_id, self.index), self.load, mode))
        else:
            lead = icon("filled-mic", 20, theme.TEXT_MUTED)
            lead.set_valign(Gtk.Align.CENTER)
            self.append(lead)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_hexpand(True)
        column.set_valign(Gtk.Align.CENTER)
        # An Opus note's length is read from its Ogg pages, so it shows once the bytes are
        # here (the first play); a Codec2 note's from its byte count at once.
        self.label = text(words.voice_note_label(mode, attachment.get("size", 0), words.duration_ms(attachment, cache.cached(message_id, self.index))), "body-small", wrap=True)
        column.append(self.label)
        self.error = text("", "label-small", theme.RED, wrap=True)
        self.error.set_visible(False)
        if playable:
            column.append(self.error)
            self.connect("map", lambda *_: playback.PLAYER.listen(self.state_changed))
            self.connect("unmap", lambda *_: playback.PLAYER.unlisten(self.state_changed))
        else:
            column.append(text(words.unsupported_line(mode), "label-small", theme.TEXT_MUTED, wrap=True))
        self.append(column)
        if not playable:
            save = text_button(words.SAVE_A_COPY, self.save, halign=Gtk.Align.END)
            save.add_css_class("small-text")
            save.set_valign(Gtk.Align.CENTER)
            self.append(save)
        if words.is_opus(mode) and cache.cached(message_id, self.index) is None:
            # Android has the bytes in the row and shows the length at once; here they are
            # fetched on view (a note is 64 KiB at most) and kept for the play.
            cache.data(message_id, attachment, lambda _data, _mode: self.state_changed())

    def state_changed(self) -> None:
        mine = playback.PLAYER.playing == (self.message_id, self.index)
        error = playback.PLAYER.error if self.played and (mine or playback.PLAYER.playing is None) else ""
        self.error.set_text(error)
        self.error.set_visible(bool(error))
        data = self.cache.cached(self.message_id, self.index)
        if data is not None:
            self.label.set_text(words.voice_note_label(self.attachment.get("mode", 0), len(data), words.duration_ms(self.attachment, data)))

    def load(self, done) -> None:
        self.played = True
        self.cache.data(self.message_id, self.attachment, done)

    def save(self) -> None:
        mode = self.attachment.get("mode", 0)
        name = f"voice-note-{words.audio_mode_name(mode).replace(' ', '-').lower()}.{'c2' if words.is_codec2(mode) else 'ogg'}"

        def got(data: bytes | None, _mode: int) -> None:
            if data is None:
                self.app.toast("The Bridge did not give the note's bytes.")
                return
            files.save_bytes(self.app, name, data, lambda ok: self.app.toast("Saved." if ok else "Not saved.") if ok is not None else None)

        self.cache.data(self.message_id, self.attachment, got)


class PhotoCard(Gtk.Box):
    """PhotoCard: the photo as it came, full bubble width, at most 320 dp tall; fetched on view."""

    def __init__(self, app, message_id, attachment: dict, cache):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(theme.dp(6))
        self.app, self.message_id, self.attachment, self.cache = app, message_id, attachment, cache
        self.placeholder = text(words.photo_label(attachment.get("size", 0)), "body-small", theme.TEXT_MUTED)
        self.append(self.placeholder)
        cache.data(message_id, attachment, self.show)

    def show(self, data: bytes | None, _mode: int) -> None:
        size = len(data) if data else self.attachment.get("size", 0)
        picture = picture_widget(data, -1, -1, words.photo_label(size)) if data else None
        self.remove(self.placeholder)
        if picture is None:
            self.append(text(words.photo_failed(self.attachment.get("format") or "?", size), "body-small", theme.TEXT_MUTED, wrap=True))
            return
        pixbuf = playback.load_pixbuf(data)
        height = min(theme.dp(320), pixbuf.get_height()) if pixbuf else theme.dp(320)
        picture.set_size_request(-1, height)
        picture.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
        self.append(picture)
