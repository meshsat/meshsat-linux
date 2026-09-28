# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app keeps on disk survives a crash, a bad byte and a long life."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import store  # noqa: E402


class JsonFilesTest(unittest.TestCase):
    def test_a_broken_file_reads_as_empty_and_is_kept_aside(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "app.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"contacts": [')
            self.assertEqual(store.read_json(path, {}), {})
            self.assertTrue(os.path.exists(path + ".broken"))
            self.assertFalse(os.path.exists(path))

    def test_write_is_atomic_and_readable(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "deep", "app.json")
            self.assertTrue(store.write_json(path, {"night": True}))
            self.assertEqual(store.read_json(path, {}), {"night": True})
            self.assertFalse(os.path.exists(path + ".tmp"))


class PrefsTest(unittest.TestCase):
    def test_changes_are_written_once_after_a_pause(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "app.json")
            prefs = store.Prefs(path)
            prefs.DELAY = 0.05
            for letter in "Kyriakos":
                prefs.set(sos_name=(prefs.get("sos_name", "") + letter))
            self.assertFalse(os.path.exists(path))  # nothing yet
            time.sleep(0.2)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), {"sos_name": "Kyriakos"})
            again = store.Prefs(path)
            self.assertEqual(again.get("sos_name"), "Kyriakos")

    def test_a_broken_prefs_file_does_not_lose_new_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "app.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{broken")
            prefs = store.Prefs(path)
            prefs.set(night=True)
            prefs.flush()
            self.assertEqual(store.read_json(path, {}), {"night": True})


class SentLogTest(unittest.TestCase):
    def test_one_bad_line_loses_that_line_only(self):
        with tempfile.TemporaryDirectory() as d:
            log = store.SentLog(os.path.join(d, "sent.jsonl"))
            log.append(store.sent_record("one", None, "mesh", "!aa"))
            with open(log.path, "a", encoding="utf-8") as handle:
                handle.write("{not json\n")
            log.append(store.sent_record("two", "+316", "sms", "!aa"))
            texts = [r["decoded_text"] for r in log.read()]
            self.assertEqual(texts, ["one", "two"])
            self.assertEqual(log.read()[1]["to_node"], "+316")
            self.assertEqual(log.read()[1]["transport"], "sms")

    def test_the_log_is_cut_to_the_last_records(self):
        with tempfile.TemporaryDirectory() as d:
            log = store.SentLog(os.path.join(d, "sent.jsonl"))
            store.KEEP, kept = 5, store.KEEP
            try:
                for i in range(8):
                    log.append(store.sent_record(str(i), None, "mesh", "!aa"))
                self.assertEqual([r["decoded_text"] for r in log.read()], ["3", "4", "5", "6", "7"])
                with open(log.path, encoding="utf-8") as handle:
                    self.assertEqual(len(handle.readlines()), 5)
            finally:
                store.KEEP = kept

    def test_reads_are_cached_until_the_file_changes(self):
        with tempfile.TemporaryDirectory() as d:
            log = store.SentLog(os.path.join(d, "sent.jsonl"))
            self.assertEqual(log.read(), [])
            log.append(store.sent_record("x", None, "mesh", "!aa"))
            self.assertEqual(len(log.read()), 1)
            first = log.read()
            first.append({"stray": True})  # a copy, not the cache
            self.assertEqual(len(log.read()), 1)


if __name__ == "__main__":
    unittest.main()
