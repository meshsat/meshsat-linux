# SPDX-License-Identifier: GPL-3.0-or-later
"""A voice note or a photo riding in an LXMF message (MESHSAT-1735), as MeshSat Android's
lxmf/AttachmentPolicy.kt, lxmf/LxAttachments.kt and audio/OggOpus.kt: where they may travel
(a Reticulum link, nothing else), the words under the box and on the bubbles, the LXMF audio
modes and what one Codec2 frame weighs, an Ogg Opus file read for its length and written for
the tests, and the body of the Bridge's POST /api/lxmf/send. Pure: no GTK, no GStreamer, tested
on the runner."""
import base64
import struct

from . import words

LXMF = "lxmf"  # the conversation transport that carries attachments
MAX_BYTES = 64 * 1024  # one message's attachments together (the Bridge's lxmf.MaxAttachmentBytes)
MAX_NOTE_MS = 30_000  # a note is at most this long; the recorder stops itself there
MAX_EDGE = 640  # a photo's long edge, in pixels, before it is compressed to fit
QUALITIES = (70, 50, 35, 20)  # the WebP qualities tried, then the edge halves

KIND_AUDIO, KIND_IMAGE = "audio", "image"
IMAGE_WEBP = "webp"
# The LXMF audio modes (LXMF.py AM_*): Codec2 0x01-0x09 (700C, the satellite default, is 0x03),
# Opus 0x10-0x19 (the bytes are an Ogg Opus stream), 0xFF a custom codec.
AUDIO_CODEC2_FIRST, AUDIO_CODEC2_700C, AUDIO_CODEC2_LAST = 0x01, 0x03, 0x09
AUDIO_OPUS_FIRST, AUDIO_OPUS_OGG, AUDIO_OPUS_LAST = 0x10, 0x10, 0x19
AUDIO_CUSTOM = 0xFF
CODEC2_NAMES = {0x01: "450PWB", 0x02: "450", 0x03: "700C", 0x04: "1200", 0x05: "1300", 0x06: "1400", 0x07: "1600", 0x08: "2400", 0x09: "3200"}
OPUS_NAMES = {0x10: "OGG", 0x11: "LBW", 0x12: "MBW", 0x13: "PTT", 0x14: "RT_HDX", 0x15: "RT_FDX", 0x16: "STANDARD", 0x17: "HQ", 0x18: "BROADCAST", 0x19: "LOSSLESS"}
# Codec2's frame geometry (codec2.c), by LXMF mode: bits per frame and samples per frame at
# 8 kHz, and the rate pycodec2 opens the mode by. The frames travel packed, whole, with no
# header; the last partial frame is dropped, as Sideband and MeshChat do. 450 and 450PWB have no
# decoder in any client.
CODEC2_GEOMETRY = {0x03: (28, 320, 700), 0x04: (48, 320, 1200), 0x05: (52, 320, 1300), 0x06: (56, 320, 1400), 0x07: (64, 320, 1600), 0x08: (48, 160, 2400),
                   0x09: (64, 160, 3200)}
CODEC2_RATE = 8000
OPUS_RATE = 48000


# ── Policy (AttachmentPolicy.kt) ─────────────────────────────────────────────────────────────
def carries(transport: str) -> bool:
    """Whether a message on `transport` takes its attachments along: the LXMF endpoint only."""
    return transport == LXMF


def bearer_name(transport: str) -> str:
    """What the person sees as a bearer: the composer's words for it."""
    return {"iridium": "satellite", "sms": "SMS", "mesh": "the mesh", "hub": "the Hub", "tak": "TAK", LXMF: "Reticulum"}.get(transport, transport)


def seconds(ms: int) -> str:
    """"12 s" or "0.8 s" (Kotlin's "%.1f" rounds half up)."""
    return f"{ms // 1000} s" if ms >= 10_000 else f"{words.fixed(ms / 1000.0)} s"


def size(nbytes: int) -> str:
    """"18 KB" or "640 B"."""
    return f"{(nbytes + 512) // 1024} KB" if nbytes >= 1024 else f"{nbytes} B"


def note(transport: str, audio_bytes: int, audio_ms: int, image_bytes: int) -> str | None:
    """The one line under the message box before a send that has attachments pending: what
    goes, what stays, and how big it is. None when nothing is attached."""
    parts = []
    if audio_bytes > 0:
        parts.append(f"voice note {seconds(audio_ms)}, {size(audio_bytes)}")
    if image_bytes > 0:
        parts.append(f"photo {size(image_bytes)}")
    if not parts:
        return None
    what = " and ".join(parts)
    if carries(transport):
        return f"With a {what}, by Reticulum; the far end sees it once the whole message is across."
    return f"By {bearer_name(transport)} only the text goes: a {what} travels by Reticulum alone, so it is not sent."


def can_send(transport: str, text: str, has_attachments: bool) -> bool:
    """A text goes anywhere; without one, only a Reticulum message with an attachment has
    something to send."""
    return bool((text or "").strip()) or (has_attachments and carries(transport))


def fits(audio_bytes: int, image_bytes: int) -> bool:
    """Whether the bytes fit the wire: the two together under MAX_BYTES."""
    return audio_bytes + image_bytes <= MAX_BYTES


# ── Modes (LxAttachments.kt) ─────────────────────────────────────────────────────────────────
def audio_mode_name(mode: int) -> str:
    """The mode's name as LXMF.py spells it ("Codec2 700C", "Opus OGG", "custom"), or
    "mode 0x.." for one it does not know."""
    if mode in CODEC2_NAMES:
        return f"Codec2 {CODEC2_NAMES[mode]}"
    if mode in OPUS_NAMES:
        return f"Opus {OPUS_NAMES[mode]}"
    return "custom" if mode == AUDIO_CUSTOM else f"mode 0x{mode:02x}"


def is_opus(mode: int) -> bool:
    return AUDIO_OPUS_FIRST <= mode <= AUDIO_OPUS_LAST


def is_codec2(mode: int) -> bool:
    return AUDIO_CODEC2_FIRST <= mode <= AUDIO_CODEC2_LAST


def content_type(kind: str, mode: int = 0, fmt: str = "") -> str:
    """The media type a client plays or shows the bytes as (the Bridge's Attachment.ContentType)."""
    if kind == KIND_AUDIO:
        return "audio/codec2" if is_codec2(mode) else "audio/ogg" if is_opus(mode) else "application/octet-stream"
    if kind == KIND_IMAGE:
        if fmt in ("webp", "png", "gif", "bmp", "avif"):
            return f"image/{fmt}"
        return "image/jpeg" if fmt in ("jpg", "jpeg") else "application/octet-stream"
    return "application/octet-stream"


def describe(kind: str, nbytes: int, mode: int = 0, fmt: str = "") -> str:
    """A short line for a log or a ledger row: "audio Opus OGG 1024 B", "image webp 2048 B"."""
    if kind == KIND_AUDIO:
        return f"audio {audio_mode_name(mode)} {nbytes} B"
    if kind == KIND_IMAGE:
        return f"image {fmt} {nbytes} B"
    return f"{kind} {nbytes} B"


# ── Codec2 frames ────────────────────────────────────────────────────────────────────────────
def codec2_bytes_per_frame(mode: int) -> int:
    """What one packed frame weighs, 0 for a mode no client decodes (450, 450PWB)."""
    geometry = CODEC2_GEOMETRY.get(mode)
    return (geometry[0] + 7) // 8 if geometry else 0


def codec2_frame_ms(mode: int) -> int:
    geometry = CODEC2_GEOMETRY.get(mode)
    return geometry[1] * 1000 // CODEC2_RATE if geometry else 0


def codec2_frames(mode: int, data: bytes) -> list:
    """The whole frames in `data`, the last partial one dropped."""
    per = codec2_bytes_per_frame(mode)
    if not per:
        return []
    return [bytes(data[i:i + per]) for i in range(0, len(data) - per + 1, per)]


def codec2_duration_ms(mode: int, nbytes: int) -> int:
    """The milliseconds of speech in `nbytes` of a Codec2 note, whole frames only; 0 for any
    other mode. Known before anything is decoded."""
    per = codec2_bytes_per_frame(mode)
    return (nbytes // per) * codec2_frame_ms(mode) if per else 0


def codec2_decodable(mode: int) -> bool:
    """Whether a decoder for this mode exists at all (pycodec2 speaks these rates)."""
    return mode in CODEC2_GEOMETRY


# ── Ogg Opus (audio/OggOpus.kt) ──────────────────────────────────────────────────────────────
OGG_MAGIC = b"OggS"
OPUS_HEAD = b"OpusHead"
OPUS_TAGS = b"OpusTags"


def looks_like_ogg_opus(data: bytes) -> bool:
    """A file that starts with an Ogg page carrying an OpusHead."""
    return len(data) > 36 and data[:4] == OGG_MAGIC and OPUS_HEAD in data[:80]


def ogg_crc(data: bytes) -> int:
    """The Ogg page checksum: CRC-32 with 0x04c11db7, unreflected, no initial value, no final
    XOR, over the page with its own checksum field zeroed."""
    crc = 0
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else crc << 1
            crc &= 0xFFFFFFFF
    return crc


def ogg_pages(data: bytes) -> list:
    """Every page of an Ogg stream as (header_type, granule, serial, sequence, [segments]);
    a page whose checksum is wrong, or that is cut short, ends the reading there."""
    pages, at = [], 0
    while at + 27 <= len(data) and data[at:at + 4] == OGG_MAGIC:
        header_type = data[at + 5]
        granule, serial, sequence, crc, nsegs = struct.unpack_from("<qIIIB", data, at + 6)
        table = data[at + 27:at + 27 + nsegs]
        if len(table) < nsegs:
            break
        body_at = at + 27 + nsegs
        body_len = sum(table)
        if body_at + body_len > len(data):
            break
        page = bytearray(data[at:body_at + body_len])
        page[22:26] = b"\0\0\0\0"
        if ogg_crc(bytes(page)) != crc:
            break
        segments, offset = [], body_at
        for lacing in table:
            segments.append((lacing, bytes(data[offset:offset + lacing])))
            offset += lacing
        pages.append((header_type, granule, serial, sequence, segments))
        at = body_at + body_len
    return pages


def ogg_packets(pages: list) -> list:
    """The packets of the pages, joined across lacing values of 255 and across page breaks."""
    packets, current = [], bytearray()
    for _type, _granule, _serial, _seq, segments in pages:
        for lacing, piece in segments:
            current += piece
            if lacing < 255:
                packets.append(bytes(current))
                current = bytearray()
    return packets


def opus_pre_skip(head: bytes) -> int:
    """The pre-skip of an OpusHead packet: the samples to drop at the start."""
    if len(head) < 12 or head[:8] != OPUS_HEAD:
        return 0
    return struct.unpack_from("<H", head, 10)[0]


def ogg_opus_duration_ms(data: bytes) -> int:
    """The length of an Ogg Opus file: the last page's granule position (48 kHz samples) less
    the pre-skip; 0 for anything that is not one."""
    pages = ogg_pages(data)
    if not pages:
        return 0
    packets = ogg_packets(pages[:1])
    if not packets or packets[0][:8] != OPUS_HEAD:
        return 0
    pre_skip = opus_pre_skip(packets[0])
    last = max((granule for _t, granule, _s, _q, _segs in pages if granule >= 0), default=0)
    return max(0, (last - pre_skip) * 1000 // OPUS_RATE)


def opus_packet_samples(packet: bytes) -> int:
    """The 48 kHz samples one Opus packet carries, from its TOC byte (RFC 6716 section 3.1)."""
    if not packet:
        return 0
    toc = packet[0]
    config, code = toc >> 3, toc & 3
    if config < 12:
        frame_ms = (10, 20, 40, 60)[config % 4]
    elif config < 16:
        frame_ms = (10, 20)[config % 2]
    else:
        frame_ms = (2.5, 5, 10, 20)[config % 4]
    if code == 0:
        frames = 1
    elif code in (1, 2):
        frames = 2
    else:
        frames = packet[1] & 0x3F if len(packet) > 1 else 0
    return int(frames * frame_ms * OPUS_RATE / 1000)


def ogg_page(header_type: int, granule: int, serial: int, sequence: int, packets: list) -> bytes:
    """One Ogg page holding whole packets (each at most 255 * 255 bytes here)."""
    table, body = bytearray(), bytearray()
    for packet in packets:
        n = len(packet)
        while n >= 255:
            table.append(255)
            n -= 255
        table.append(n)
        body += packet
    head = bytearray(OGG_MAGIC + bytes([0, header_type]) + struct.pack("<qIIIB", granule, serial, sequence, 0, len(table)) + bytes(table))
    page = bytes(head + body)
    crc = ogg_crc(page)
    return page[:22] + struct.pack("<I", crc) + page[26:]


def ogg_opus_write(packets: list, pre_skip: int = 312, serial: int = 0x4D53, per_page: int = 50, channels: int = 1) -> bytes:
    """An Ogg Opus file (RFC 7845) from Opus packets: the OpusHead page, the OpusTags page,
    then the packets `per_page` at a time with the granule position counted from their TOC
    bytes, the last page flagged as the end. What Android's OggOpus.write writes."""
    head = OPUS_HEAD + bytes([1, channels]) + struct.pack("<HIhB", pre_skip, OPUS_RATE, 0, 0)
    vendor = b"MeshSat"
    tags = OPUS_TAGS + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0)
    out = bytearray(ogg_page(0x02, 0, serial, 0, [head]))
    out += ogg_page(0x00, 0, serial, 1, [tags])
    granule, sequence = pre_skip, 2
    groups = [packets[i:i + per_page] for i in range(0, len(packets), per_page)] or [[]]
    for i, group in enumerate(groups):
        granule += sum(opus_packet_samples(p) for p in group)
        out += ogg_page(0x04 if i == len(groups) - 1 else 0x00, granule, serial, sequence, group)
        sequence += 1
    return bytes(out)


def silent_opus_packets(ms: int) -> list:
    """One-byte Opus packets of 20 ms each (a TOC of a silence-length frame: SILK wideband,
    code 0, no frame data, which a decoder plays as silence) for a note of `ms`: the tests'
    and the scripted Bridge's notes, which play without a microphone."""
    return [bytes([0x48])] * (ms // 20)


# ── The wire, as the Bridge takes it ─────────────────────────────────────────────────────────
def send_body(to: str, text: str, audio: bytes | None = None, audio_mode: int = AUDIO_OPUS_OGG, image: bytes | None = None, image_format: str = IMAGE_WEBP) -> dict:
    """The body of POST /api/lxmf/send: `to` (32 hex), `content` (may be empty when the message
    carries an attachment), `audio: {mode, data_b64}`, `image: {format, data_b64}`."""
    body = {"to": to, "content": (text or "").strip()}
    if audio:
        body["audio"] = {"mode": audio_mode, "data_b64": base64.b64encode(audio).decode("ascii")}
    if image:
        body["image"] = {"format": image_format, "data_b64": base64.b64encode(image).decode("ascii")}
    return body


def listed(answer) -> list:
    """The attachments of GET /api/lxmf/messages/{id}/attachments as this app keeps them:
    [{"index", "kind", "mode", "format", "size", "content_type", "url"}], in the message's
    order (the image first); [] for an answer of another shape."""
    items = answer.get("attachments") if isinstance(answer, dict) else answer
    out = []
    for i, a in enumerate(items if isinstance(items, list) else []):
        if not isinstance(a, dict) or a.get("kind") not in (KIND_AUDIO, KIND_IMAGE):
            continue
        out.append({"index": int(a.get("index", i)), "kind": a["kind"], "mode": int(a.get("mode") or 0), "format": str(a.get("format") or ""),
                    "size": int(a.get("size") or 0), "content_type": str(a.get("content_type") or content_type(a["kind"], int(a.get("mode") or 0), str(a.get("format") or ""))),
                    "url": str(a.get("url") or "")})
    return out


# ── The bubbles' and the composer's words (ui/components/VoiceNote.kt) ───────────────────────
HOLD_TO_RECORD = "Hold to record a voice note"
START_RECORDING, STOP_RECORDING = "Start recording", "Stop recording"
HOLD_WHILE_YOU_SPEAK = "Hold the microphone while you speak."
MICROPHONE_FAILED = "The microphone could not be opened."
NO_ENCODER = "Voice notes need GStreamer's Opus encoder on this device."  # this edition's own; Android's says Android 10
ATTACH_PHOTO = "Attach a photo"
PICTURE_FAILED = "That picture could not be read or made small enough."
PLAY_NOTE, PLAY_VOICE_NOTE, STOP, REMOVE = "Play the note", "Play the voice note", "Stop", "Remove"
THE_PHOTO_TO_SEND = "The photo to send"
SAVE_A_COPY = "Save a copy"  # this edition's offer of a note it cannot play


def recording_label(ms: int) -> str:
    return f"Recording, {seconds(ms)}"


def too_long(nbytes: int) -> str:
    return f"Too long for one message ({size(nbytes)}); keep it shorter."


def pending_audio_label(ms: int, nbytes: int) -> str:
    return f"Voice note, {seconds(ms)}, {size(nbytes)}"


def pending_image_label(nbytes: int) -> str:
    return f"Photo, {size(nbytes)}"


def voice_note_label(mode: int, nbytes: int, duration_ms: int) -> str:
    """The card's line: "Voice note, 4.2 s, 7 KB" for a note that plays, the mode's name for
    one that does not ("Voice note (Codec2 700C), 7 KB")."""
    if is_opus(mode):
        return f"Voice note, {seconds(duration_ms)}, {size(nbytes)}"
    return f"Voice note ({audio_mode_name(mode)}), {size(nbytes)}"


def unsupported_line(mode: int) -> str:
    return f"Playback of {audio_mode_name(mode)} is not supported on this phone."


def photo_label(nbytes: int) -> str:
    return f"Photo, {size(nbytes)}"


def photo_failed(fmt: str, nbytes: int) -> str:
    return f"Photo ({fmt}, {size(nbytes)}) could not be shown."


def duration_ms(attachment: dict, data: bytes | None) -> int:
    """What a note lasts: an Opus note from its Ogg pages once the bytes are here, a Codec2 note
    from its byte count alone."""
    mode = attachment.get("mode", 0)
    if is_codec2(mode):
        return codec2_duration_ms(mode, attachment.get("size") or len(data or b""))
    return ogg_opus_duration_ms(data) if data else 0
