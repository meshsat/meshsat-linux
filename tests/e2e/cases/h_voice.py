# SPDX-License-Identifier: GPL-3.0-or-later
"""Voice notes and photos on a Reticulum chat (MESHSAT-1735, VoiceNote.kt): the microphone and
the photo on a Reticulum chat and on no other, the cards of a received note, a Codec2 note and
a photo, a note recorded through the test source and sent in the Bridge's body, a photo picked
and sent as WebP, and New message's peers and address. The microphone is audiotestsrc here: no
real microphone is opened in the test session."""
import base64
import struct
import zlib

SCENARIO = "lxmf"
ENV = {"MESHSAT_APP_AUDIO_SOURCE": "audiotestsrc"}
PEER = "1234567890abcdef" * 2
OTHER = "fedcba0987654321" * 2
CHAT = "chat/lxmf:" + PEER


def png(width: int, height: int, rgb=(250, 97, 24)) -> bytes:
    """A plain PNG, for the photo picker."""
    raw = b"".join(b"\0" + bytes(rgb) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def case_a_reticulum_chat_has_the_microphone_and_the_mesh_chat_has_not(ctx):
    ctx.app.open(CHAT)
    ctx.tree.wait_text("Sideband test")
    ctx.tree.wait_text(f"By Reticulum (LXMF), {PEER}")
    ctx.tree.wait_text("By Reticulum to Sideband test. Direct waits for the far end, even by satellite.")
    ctx.tree.find("button", name="Hold to record a voice note")
    ctx.tree.find("button", name="Attach a photo")
    assert not ctx.tree.find("button", name="Send").sensitive, "Send is live with nothing typed and nothing attached"
    ctx.tree.set_text("Message", "x")
    assert ctx.tree.find("button", name="Send").sensitive
    ctx.tree.set_text("Message", "")
    ctx.shot("reticulum-chat")
    ctx.app.open("chat/!ffffffff")
    ctx.tree.wait_text("To everyone on the mesh channel.")
    assert not ctx.tree.find_all("button", name="Hold to record a voice note"), "a mesh chat offers a voice note"
    assert not ctx.tree.find_all("button", name="Attach a photo"), "a mesh chat offers a photo"
    ctx.app.open("messages")
    ctx.tree.wait_text("Reticulum")  # the filter chip
    ctx.tree.click("Reticulum")
    ctx.tree.wait_text("Sideband test")
    assert "Everyone on the mesh" not in ctx.tree.texts(), "the Reticulum filter keeps a mesh chat"
    ctx.tree.click("All")


def case_b_a_received_note_a_codec2_note_and_a_photo_show_their_cards(ctx):
    ctx.app.open(CHAT)
    ctx.tree.wait_text("hello over reticulum")
    # The Opus note: its length once the bytes are here, the play button
    ctx.tree.wait_text("Voice note, 2.0 s, ", timeout=10)
    ctx.tree.find("button", name="Play the voice note")
    # The Codec2 note: named by its mode; the line, or a play button where pycodec2 is installed
    ctx.tree.wait_text("Voice note (Codec2 700C), 100 B")
    supported = len(ctx.tree.find_all("button", name="Play the voice note")) > 1
    if not supported:
        ctx.tree.wait_text("Playback of Codec2 700C is not supported on this phone.")
        ctx.tree.find("button", name="Save a copy")
    # The photo: shown as it came (46 bytes), or named when nothing on the phone reads WebP
    labels = ctx.tree.texts()
    shown = ctx.tree.find_all("image", contains="Photo, 46 B") or [t for t in labels if t.startswith("Photo (webp, 46 B) could not be shown.")]
    assert shown, f"no photo card: {labels[:20]}"
    before = ctx.bridge.count()
    ctx.app.refresh()
    ctx.tree.wait_text("hello over reticulum")
    listed = [r for r in ctx.bridge.requests(before) if r["path"].endswith("/attachments")]
    assert not listed, f"the attachment lists were asked again after a poll: {listed}"
    ctx.shot("reticulum-cards")
    # The Opus note plays through GStreamer
    ctx.tree.click("Play the voice note")
    ctx.tree.find("button", name="Stop", timeout=5)
    ctx.app.open("messages")


def case_c_a_note_recorded_through_the_test_source_goes_in_the_send_body(ctx):
    ctx.app.open(CHAT)
    ctx.tree.wait_text("Sideband test")
    ctx.app.mark()
    # No press reaches the gesture from here: a click starts the note, the next one ends it
    ctx.tree.click("Hold to record a voice note")
    ctx.tree.find("button", contains="Recording, ", timeout=5)
    ctx.tree.click_containing("Recording, ")
    ctx.tree.wait_text("Voice note, ", timeout=5)
    ctx.tree.find("button", name="Play the note")
    ctx.tree.wait_text("With a voice note ")
    assert not ctx.tree.find("button", name="Hold to record a voice note").sensitive, "a second note is offered while one waits"
    assert ctx.tree.find("button", name="Send").sensitive, "a note alone cannot be sent by Reticulum"
    before = ctx.bridge.count()
    ctx.tree.click("Send")
    sent = ctx.bridge.wait_request("POST", "/api/lxmf/send", since=before, timeout=10)
    body = sent["body"]
    assert body["to"] == PEER and body["content"] == "", body
    assert body["audio"]["mode"] == 0x10, body["audio"]["mode"]
    ogg = base64.b64decode(body["audio"]["data_b64"])
    assert ogg[:4] == b"OggS" and b"OpusHead" in ogg[:80], ogg[:40]
    assert "image" not in body
    ctx.tree.wait_text("Voice note, ", timeout=10)  # the bubble, from this app's own record
    assert not ctx.tree.find_all("text", contains="With a voice note "), "the pending row stayed after the send"
    ctx.shot("note-sent")
    ctx.app.open("messages")


def case_d_a_photo_goes_as_webp_with_the_text(ctx):
    ctx.app.open(CHAT)
    ctx.tree.wait_text("Sideband test")
    ctx.app.pick(png(1600, 900), name="photo.png")
    ctx.tree.click("Attach a photo")
    ctx.tree.wait_text("Photo, ", timeout=10)
    ctx.tree.wait_text("With a photo ")
    ctx.tree.set_text("Message", "with a photo")
    before = ctx.bridge.count()
    ctx.tree.click("Send")
    sent = ctx.bridge.wait_request("POST", "/api/lxmf/send", since=before, timeout=10)
    body = sent["body"]
    assert body["content"] == "with a photo", body
    assert body["image"]["format"] == "webp", body["image"]["format"]
    webp = base64.b64decode(body["image"]["data_b64"])
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP", webp[:16]
    assert len(webp) <= 64 * 1024
    assert "audio" not in body
    ctx.tree.wait_text("with a photo", timeout=10)
    ctx.app.open("messages")


def case_e_a_picture_that_cannot_be_read_is_refused_in_androids_words(ctx):
    ctx.app.open(CHAT)
    ctx.tree.wait_text("Sideband test")
    ctx.app.pick(b"not a picture at all", name="broken.png")
    ctx.app.mark()
    ctx.tree.click("Attach a photo")
    ctx.app.wait_toast("That picture could not be read or made small enough.")
    ctx.app.open("messages")


def case_f_new_message_lists_the_peers_and_takes_an_address(ctx):
    ctx.app.open("messages")
    ctx.tree.click("New message")
    ctx.tree.wait_text("New message")
    ctx.tree.wait_text("By Reticulum, 1234567890abcdef... 1 hop away")
    ctx.tree.wait_text("Reticulum fedcba09")
    ctx.tree.wait_text("By Reticulum, fedcba0987654321... 3 hops away")
    ctx.tree.click_containing("By Reticulum, 1234567890abcdef")
    ctx.tree.wait_text("By Reticulum to Sideband test. Direct waits for the far end, even by satellite.")
    ctx.app.open("messages")
    ctx.tree.click("New message")
    ctx.tree.wait_text("New message")
    ctx.tree.set_text("Or a Reticulum (LXMF) address, 32 hex characters", "<" + ("ab" * 16).upper() + ">")
    ctx.tree.click("Message this address")
    ctx.tree.wait_text("Reticulum abababab")
    ctx.tree.wait_text("By Reticulum, once a path to this address is found.")
    ctx.shot("new-reticulum-chat")
    ctx.app.open("messages")
