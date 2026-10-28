# SPDX-License-Identifier: GPL-3.0-or-later
"""The voice notes and photos against the scripted Bridge (tests/fakebridge.py, scenario
`lxmf`): the attachment list asked once per message and kept (a 404 and an empty list too),
the bytes with their media type and the audio mode, this app's own send recorded in the
Bridge's shape and refused as the Bridge refuses it, the note and photo of a send kept in
memory under the sent record, and a picture made small enough through Pillow."""
import base64
import io
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import fakebridge  # noqa: E402
from meshsat import api, media  # noqa: E402
from meshsat.model import attachments as att  # noqa: E402

PEER = "1234567890abcdef" * 2


def wait(fn, timeout: float = 5.0):
    """`fn(done)`: the arguments `done` was called with, within `timeout`."""
    got, event = [], threading.Event()

    def done(*args):
        got.extend(args)
        event.set()

    fn(done)
    if not event.wait(timeout):
        raise AssertionError("no answer in time")
    return got


class CacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = fakebridge.FakeBridge(fakebridge.load_scenario("lxmf")).start()
        cls.old = api.BRIDGE
        api.BRIDGE = cls.fake.url

    @classmethod
    def tearDownClass(cls):
        api.BRIDGE = cls.old
        cls.fake.stop()

    def setUp(self):
        self.fake.control("POST", "/__fake__/reset", {})
        self.cache = media.Attachments()

    def listing(self, message_id):
        return wait(lambda done: self.cache.listing({"id": message_id}, done))[0]

    def test_the_list_is_asked_once_and_kept(self):
        items = self.listing(14)
        self.assertEqual([a["kind"] for a in items], ["audio"])
        self.assertEqual(items[0]["mode"], 0x10)
        self.assertEqual(items[0]["content_type"], "audio/ogg")
        self.assertEqual(items[0]["url"], "/api/lxmf/messages/14/attachments/0")
        before = len(self.fake.requests)
        self.assertEqual(self.listing(14), items)
        self.assertEqual(len(self.fake.requests), before, "the second look costs no call")
        self.assertEqual(self.cache.known(14), items)

    def test_an_empty_list_and_a_404_are_kept_too(self):
        self.assertEqual(self.listing(11), [], "a text with nothing attached")
        self.assertEqual(self.listing(3), [], "a mesh message: not an LXMF message at all")
        self.assertEqual(self.listing(999), [], "no such message")
        before = len(self.fake.requests)
        self.listing(11)
        self.listing(3)
        self.listing(999)
        self.assertEqual(len(self.fake.requests), before)
        self.assertEqual(self.listing(-5), [], "a local record is never asked of the Bridge")
        self.assertEqual(len(self.fake.requests), before)

    def test_the_bytes_with_their_type_and_mode(self):
        items = self.listing(13)
        data, mode = wait(lambda done: self.cache.data(13, items[0], done))
        self.assertEqual(data, bytes(range(100)))
        self.assertEqual(mode, 0x03)
        self.assertEqual(self.cache.cached(13, 0), data)
        status, ctype, header_mode, raw = media.fetch_bytes("/api/lxmf/messages/13/attachments/0")
        self.assertEqual((status, ctype, header_mode, raw), (200, "audio/codec2", 3, bytes(range(100))))
        self.assertEqual(media.fetch_bytes("/api/lxmf/messages/13/attachments/7")[0], 404)
        self.assertEqual(media.fetch_bytes("/api/lxmf/messages/12/attachments/0")[1], "image/webp")
        opus = wait(lambda done: self.cache.data(14, self.listing(14)[0], done))[0]
        self.assertTrue(att.looks_like_ogg_opus(opus))
        self.assertEqual(att.ogg_opus_duration_ms(opus), 2000)

    def test_a_bridge_that_is_away_is_asked_again(self):
        self.fake.control("POST", "/__fake__/down", {"down": True})
        self.assertEqual(self.listing(14), [])
        self.assertIsNone(self.cache.known(14), "nothing is remembered of a Bridge that did not answer")
        self.fake.control("POST", "/__fake__/down", {"down": False})
        self.assertEqual(len(self.listing(14)), 1)

    def test_the_budget(self):
        media.BYTES_BUDGET, old = 100, media.BYTES_BUDGET
        try:
            self.cache.keep(1, 0, bytes(60))
            self.cache.keep(2, 0, bytes(60))
            self.assertIsNone(self.cache.cached(1, 0), "the oldest went")
            self.assertIsNotNone(self.cache.cached(2, 0))
        finally:
            media.BYTES_BUDGET = old

    def test_a_send_is_kept_in_memory_until_the_bridge_files_it(self):
        self.cache.put_pending(-7, [{"kind": "audio", "mode": 0x10, "format": "", "size": 3, "data": b"abc"}, {"kind": "image", "mode": 0, "format": "webp", "size": 2, "data": b"de"}])
        items = self.listing(-7)
        self.assertEqual([a["kind"] for a in items], ["image", "audio"], "the image first, as the Bridge orders them")
        self.assertEqual(items[0]["content_type"], "image/webp")
        self.assertEqual(wait(lambda done: self.cache.data(-7, items[1], done)), [b"abc", 0x10])
        self.assertEqual(self.cache.cached(-7, 0), b"de")


class SendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = fakebridge.FakeBridge(fakebridge.load_scenario("lxmf")).start()
        cls.old = api.BRIDGE
        api.BRIDGE = cls.fake.url

    @classmethod
    def tearDownClass(cls):
        api.BRIDGE = cls.old
        cls.fake.stop()

    def setUp(self):
        self.fake.control("POST", "/__fake__/reset", {})

    def test_the_bridge_takes_the_body_and_files_the_message(self):
        ogg = att.ogg_opus_write(att.silent_opus_packets(1000))
        answer = api.request("POST", "/api/lxmf/send", att.send_body(PEER, "listen", ogg, image=b"RIFFwebp"))
        self.assertEqual(answer.status, 202, answer.error)
        self.assertEqual(answer.body["channel"], "lxmf_0")
        sent = self.fake.lxmf_sent[-1]
        self.assertEqual(sent["to"], PEER)
        self.assertEqual(sent["content"], "listen")
        self.assertEqual(sent["audio"]["mode"], 0x10)
        self.assertEqual(base64.b64decode(sent["audio"]["data_b64"]), ogg)
        self.assertEqual(sent["image"], {"format": "webp", "data_b64": base64.b64encode(b"RIFFwebp").decode()})
        row = api.get("/api/messages?limit=200")["messages"][0]
        self.assertEqual((row["direction"], row["transport"], row["portnum_name"], row["decoded_text"], row["to_node"]), ("tx", "reticulum", "LXMF", "listen", "lxmf:" + PEER))
        listed = api.get(f"/api/lxmf/messages/{row['id']}/attachments")["attachments"]
        self.assertEqual([a["kind"] for a in listed], ["image", "audio"])
        self.assertEqual(media.fetch_bytes(listed[1]["url"])[3], ogg)

    def test_a_note_alone_goes_and_a_bad_body_is_refused(self):
        self.assertEqual(api.request("POST", "/api/lxmf/send", att.send_body(PEER, "", b"OggS")).status, 202)
        self.assertEqual(api.request("POST", "/api/lxmf/send", att.send_body(PEER, "")).status, 400, "nothing to send")
        self.assertEqual(api.request("POST", "/api/lxmf/send", att.send_body("short", "x")).status, 400)
        self.assertEqual(api.request("POST", "/api/lxmf/send", att.send_body(PEER, "x", bytes(att.MAX_BYTES + 1))).status, 413)
        self.assertEqual(len(self.fake.lxmf_sent), 1)


class ShrinkTest(unittest.TestCase):
    def picture(self, width: int, height: int) -> bytes:
        from PIL import Image, ImageDraw  # noqa: PLC0415

        picture = Image.new("RGB", (width, height), (40, 80, 160))
        draw = ImageDraw.Draw(picture)
        for i in range(0, width, 37):
            draw.line((i, 0, width - i, height), fill=(250, 120, 20), width=3)
        out = io.BytesIO()
        picture.save(out, format="PNG")
        return out.getvalue()

    def test_a_picture_becomes_a_small_webp(self):
        try:
            from PIL import Image  # noqa: PLC0415
        except ImportError:
            self.skipTest("Pillow is not on this machine")
        small = media.shrink_photo_pil(self.picture(1600, 1200), att.MAX_BYTES)
        self.assertIsNotNone(small)
        self.assertLessEqual(len(small), att.MAX_BYTES)
        self.assertEqual(small[:4], b"RIFF")
        self.assertEqual(small[8:12], b"WEBP")
        shown = Image.open(io.BytesIO(small))
        self.assertEqual(max(shown.size), att.MAX_EDGE)
        self.assertEqual(shown.size, (640, 480))
        tight = media.shrink_photo_pil(self.picture(1600, 1200), 3000)
        self.assertIsNotNone(tight)
        self.assertLessEqual(len(tight), 3000)
        self.assertLess(max(Image.open(io.BytesIO(tight)).size), att.MAX_EDGE, "the edge came down to fit")
        self.assertIsNone(media.shrink_photo_pil(b"not a picture", att.MAX_BYTES))
        self.assertIsNone(media.shrink_photo_pil(self.picture(400, 400), 10), "nothing fits ten bytes")
        rgb = media.photo_rgb_pil(small)
        self.assertEqual((rgb[0], rgb[1], rgb[2]), (640, 480, False))
        self.assertEqual(len(rgb[3]), 640 * 480 * 3)


if __name__ == "__main__":
    unittest.main()
