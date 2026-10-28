# SPDX-License-Identifier: GPL-3.0-or-later
"""Voice notes and photos (model/attachments.py) against MeshSat Android's AttachmentPolicy.kt,
LxAttachments.kt, VoiceNote.kt and OggOpus.kt: the policy and its lines, the sizes and seconds
as Kotlin formats them, the mode names, what a Codec2 frame weighs in every mode, an Ogg Opus
file written and read back for its length, and the body of the Bridge's send."""
import base64
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from meshsat.model import attachments as att  # noqa: E402


class PolicyTest(unittest.TestCase):
    def test_only_a_reticulum_message_carries_them(self):
        self.assertTrue(att.carries("lxmf"))
        for transport in ("mesh", "iridium", "sms", "hub", "tak"):
            self.assertFalse(att.carries(transport), transport)

    def test_seconds_and_sizes_as_kotlin_writes_them(self):
        self.assertEqual(att.seconds(4200), "4.2 s")
        self.assertEqual(att.seconds(800), "0.8 s")
        self.assertEqual(att.seconds(1250), "1.3 s")  # "%.1f".format rounds half up
        self.assertEqual(att.seconds(12000), "12 s")
        self.assertEqual(att.seconds(30000), "30 s")
        self.assertEqual(att.size(640), "640 B")
        self.assertEqual(att.size(1024), "1 KB")
        self.assertEqual(att.size(1535), "1 KB")
        self.assertEqual(att.size(1536), "2 KB")
        self.assertEqual(att.size(18 * 1024), "18 KB")
        self.assertEqual(att.size(7000), "7 KB")

    def test_the_line_under_the_box(self):
        self.assertIsNone(att.note("lxmf", 0, 0, 0))
        self.assertEqual(att.note("lxmf", 18 * 1024, 12000, 0), "With a voice note 12 s, 18 KB, by Reticulum; the far end sees it once the whole message is across.")
        self.assertEqual(att.note("sms", 18 * 1024, 12000, 0), "By SMS only the text goes: a voice note 12 s, 18 KB travels by Reticulum alone, so it is not sent.")
        self.assertEqual(att.note("mesh", 0, 0, 3000), "By the mesh only the text goes: a photo 3 KB travels by Reticulum alone, so it is not sent.")
        self.assertEqual(att.note("iridium", 7000, 4200, 3000), "By satellite only the text goes: a voice note 4.2 s, 7 KB and photo 3 KB travels by Reticulum alone, so it is not sent.")
        self.assertEqual(att.note("lxmf", 7000, 4200, 3000), "With a voice note 4.2 s, 7 KB and photo 3 KB, by Reticulum; the far end sees it once the whole message is across.")

    def test_what_may_be_sent(self):
        self.assertTrue(att.can_send("sms", "hello", False))
        self.assertTrue(att.can_send("lxmf", "", True))
        self.assertFalse(att.can_send("sms", "", True), "a note alone cannot go by SMS")
        self.assertFalse(att.can_send("lxmf", "  ", False))
        self.assertTrue(att.fits(60 * 1024, 4 * 1024))
        self.assertFalse(att.fits(60 * 1024, 4 * 1024 + 1))
        self.assertEqual(att.MAX_BYTES, 65536)
        self.assertEqual(att.MAX_NOTE_MS, 30000)


class ModesTest(unittest.TestCase):
    def test_names_as_lxmf_spells_them(self):
        self.assertEqual(att.audio_mode_name(0x03), "Codec2 700C")
        self.assertEqual(att.audio_mode_name(0x01), "Codec2 450PWB")
        self.assertEqual(att.audio_mode_name(0x10), "Opus OGG")
        self.assertEqual(att.audio_mode_name(0x19), "Opus LOSSLESS")
        self.assertEqual(att.audio_mode_name(0xFF), "custom")
        self.assertEqual(att.audio_mode_name(0x20), "mode 0x20")
        self.assertTrue(att.is_opus(0x10) and att.is_opus(0x19) and not att.is_opus(0x09))
        self.assertTrue(att.is_codec2(0x01) and att.is_codec2(0x09) and not att.is_codec2(0x10))

    def test_content_types_as_the_bridge_serves_them(self):
        self.assertEqual(att.content_type("audio", 0x03), "audio/codec2")
        self.assertEqual(att.content_type("audio", 0x10), "audio/ogg")
        self.assertEqual(att.content_type("image", fmt="webp"), "image/webp")
        self.assertEqual(att.content_type("image", fmt="jpg"), "image/jpeg")
        self.assertEqual(att.describe("audio", 1024, 0x10), "audio Opus OGG 1024 B")
        self.assertEqual(att.describe("image", 2048, fmt="webp"), "image webp 2048 B")

    def test_the_codec2_frame_table(self):
        # codec2.c: bits per frame and samples per frame, as the kit's web UI and the Bridge read them
        expected = {0x03: (4, 40), 0x04: (6, 40), 0x05: (7, 40), 0x06: (7, 40), 0x07: (8, 40), 0x08: (6, 20), 0x09: (8, 20)}
        for mode, (per_frame, ms) in expected.items():
            self.assertEqual(att.codec2_bytes_per_frame(mode), per_frame, att.audio_mode_name(mode))
            self.assertEqual(att.codec2_frame_ms(mode), ms, att.audio_mode_name(mode))
            self.assertTrue(att.codec2_decodable(mode))
        for mode in (0x01, 0x02, 0x10):
            self.assertEqual(att.codec2_bytes_per_frame(mode), 0)
            self.assertFalse(att.codec2_decodable(mode))

    def test_whole_frames_only(self):
        data = bytes(range(103))  # 25 frames of 700C and 3 bytes over
        frames = att.codec2_frames(0x03, data)
        self.assertEqual(len(frames), 25)
        self.assertEqual(frames[0], bytes([0, 1, 2, 3]))
        self.assertEqual(frames[-1], bytes([96, 97, 98, 99]))
        self.assertEqual(att.codec2_duration_ms(0x03, 103), 1000)
        self.assertEqual(att.codec2_duration_ms(0x09, 8 * 50), 1000)
        self.assertEqual(att.codec2_duration_ms(0x02, 100), 0)
        self.assertEqual(att.codec2_frames(0x02, data), [])


def reference_crc(data: bytes) -> int:
    """The Ogg checksum again, by a table, to check the code's bitwise one."""
    table = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else r << 1
        table.append(r & 0xFFFFFFFF)
    crc = 0
    for byte in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[((crc >> 24) ^ byte) & 0xFF]
    return crc


class OggOpusTest(unittest.TestCase):
    def test_the_checksum(self):
        self.assertEqual(att.ogg_crc(b""), 0)
        rng = random.Random(7)
        for n in (1, 27, 100, 300):
            data = bytes(rng.randrange(256) for _ in range(n))
            self.assertEqual(att.ogg_crc(data), reference_crc(data))

    def test_toc_durations(self):
        self.assertEqual(att.opus_packet_samples(bytes([0x48])), 960)  # SILK WB 20 ms, one frame
        self.assertEqual(att.opus_packet_samples(bytes([0x40])), 480)  # SILK WB 10 ms
        self.assertEqual(att.opus_packet_samples(bytes([0x50])), 1920)  # SILK WB 40 ms
        self.assertEqual(att.opus_packet_samples(bytes([0x58])), 2880)  # SILK WB 60 ms
        self.assertEqual(att.opus_packet_samples(bytes([0x49])), 1920)  # code 1: two 20 ms frames
        self.assertEqual(att.opus_packet_samples(bytes([0x4B, 0x03])), 2880)  # code 3: three frames
        self.assertEqual(att.opus_packet_samples(bytes([0xF8])), 960)  # CELT FB 20 ms
        self.assertEqual(att.opus_packet_samples(bytes([0x80])), 120)  # CELT NB 2.5 ms
        self.assertEqual(att.opus_packet_samples(bytes([0x60])), 480)  # hybrid SWB 10 ms
        self.assertEqual(att.opus_packet_samples(b""), 0)

    def test_written_and_read_back(self):
        packets = att.silent_opus_packets(2000)
        self.assertEqual(len(packets), 100)
        ogg = att.ogg_opus_write(packets, pre_skip=312)
        self.assertTrue(att.looks_like_ogg_opus(ogg))
        pages = att.ogg_pages(ogg)
        self.assertEqual(len(pages), 4, "OpusHead, OpusTags, two pages of fifty packets")
        self.assertEqual(pages[0][0], 0x02, "the first page begins the stream")
        self.assertEqual(pages[-1][0], 0x04, "the last page ends it")
        self.assertEqual([p[3] for p in pages], [0, 1, 2, 3], "page sequence")
        self.assertEqual(pages[-1][1], 312 + 100 * 960, "the last granule counts every packet from the pre-skip")
        read = att.ogg_packets(pages)
        self.assertEqual(read[0][:8], att.OPUS_HEAD)
        self.assertEqual(read[1][:8], att.OPUS_TAGS)
        self.assertEqual(read[2:], packets)
        self.assertEqual(att.opus_pre_skip(read[0]), 312)
        self.assertEqual(att.ogg_opus_duration_ms(ogg), 2000)

    def test_a_long_packet_is_laced_over_255s(self):
        packet = bytes([0x48]) + bytes(600)
        ogg = att.ogg_opus_write([packet])
        read = att.ogg_packets(att.ogg_pages(ogg))
        self.assertEqual(read[2], packet)

    def test_corruption_is_refused(self):
        ogg = bytearray(att.ogg_opus_write(att.silent_opus_packets(200)))
        self.assertEqual(att.ogg_opus_duration_ms(bytes(ogg)), 200)
        ogg[-3] ^= 0xFF  # a byte of the last page
        self.assertEqual(att.ogg_opus_duration_ms(bytes(ogg)), 0, "the last page's checksum fails, and with it the length")
        self.assertEqual(att.ogg_opus_duration_ms(b"not ogg at all"), 0)
        self.assertFalse(att.looks_like_ogg_opus(b"OggS" + bytes(40)))
        self.assertEqual(att.ogg_opus_duration_ms(att.ogg_opus_write([])), 0)


class WireTest(unittest.TestCase):
    def test_the_send_body(self):
        body = att.send_body("ab" * 16, "  hello  ", b"OggS...", image=b"RIFF")
        self.assertEqual(body["to"], "ab" * 16)
        self.assertEqual(body["content"], "hello")
        self.assertEqual(body["audio"], {"mode": 0x10, "data_b64": base64.b64encode(b"OggS...").decode()})
        self.assertEqual(body["image"], {"format": "webp", "data_b64": base64.b64encode(b"RIFF").decode()})
        bare = att.send_body("ab" * 16, "", b"x")
        self.assertEqual(bare["content"], "")
        self.assertNotIn("image", bare)
        self.assertNotIn("audio", att.send_body("ab" * 16, "text"))

    def test_the_list_as_the_bridge_gives_it(self):
        answer = {"message_id": 7, "lxmf_hash": "", "attachments": [
            {"index": 0, "kind": "image", "mode": 0, "format": "webp", "size": 2048, "content_type": "image/webp", "url": "/api/lxmf/messages/7/attachments/0"},
            {"index": 1, "kind": "audio", "mode": 3, "format": "", "size": 1024, "content_type": "audio/codec2", "url": "/api/lxmf/messages/7/attachments/1"},
            {"index": 2, "kind": "video", "size": 1}]}
        items = att.listed(answer)
        self.assertEqual([a["kind"] for a in items], ["image", "audio"], "a kind nobody knows is left out")
        self.assertEqual(items[1]["mode"], 3)
        self.assertEqual(items[1]["url"], "/api/lxmf/messages/7/attachments/1")
        self.assertEqual(att.listed({"attachments": []}), [])
        self.assertEqual(att.listed(None), [])
        self.assertEqual(att.listed([{"kind": "audio", "mode": 16, "size": 10}])[0]["content_type"], "audio/ogg")


class BubbleWordsTest(unittest.TestCase):
    def test_the_cards(self):
        self.assertEqual(att.voice_note_label(0x10, 7000, 4200), "Voice note, 4.2 s, 7 KB")
        self.assertEqual(att.voice_note_label(0x03, 7000, 1000), "Voice note (Codec2 700C), 7 KB")
        self.assertEqual(att.unsupported_line(0x03), "Playback of Codec2 700C is not supported on this phone.")
        self.assertEqual(att.photo_label(3000), "Photo, 3 KB")
        self.assertEqual(att.photo_failed("webp", 3000), "Photo (webp, 3 KB) could not be shown.")
        self.assertEqual(att.pending_audio_label(4200, 7000), "Voice note, 4.2 s, 7 KB")
        self.assertEqual(att.pending_image_label(3000), "Photo, 3 KB")
        self.assertEqual(att.recording_label(4200), "Recording, 4.2 s")
        self.assertEqual(att.too_long(70000), "Too long for one message (68 KB); keep it shorter.")
        self.assertEqual(att.HOLD_TO_RECORD, "Hold to record a voice note")
        self.assertEqual(att.HOLD_WHILE_YOU_SPEAK, "Hold the microphone while you speak.")
        self.assertEqual(att.PICTURE_FAILED, "That picture could not be read or made small enough.")

    def test_a_notes_length(self):
        ogg = att.ogg_opus_write(att.silent_opus_packets(4200))
        self.assertEqual(att.duration_ms({"mode": 0x10, "size": len(ogg)}, ogg), 4200)
        self.assertEqual(att.duration_ms({"mode": 0x10, "size": len(ogg)}, None), 0, "an Opus note's length waits for its bytes")
        self.assertEqual(att.duration_ms({"mode": 0x03, "size": 100}, None), 1000, "a Codec2 note's length is known from its size")


if __name__ == "__main__":
    unittest.main()
