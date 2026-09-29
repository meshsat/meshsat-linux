# SPDX-License-Identifier: GPL-3.0-or-later
"""Imported first by `unittest discover` (files load in name order): every test after it keeps
the app's state, settings and cache in a directory of its own, never in the person's. Without it
the tests wrote into ~/.local/state/meshsat (the sent log, the names file) of whatever machine
ran them, the phone included."""
import os
import tempfile
import unittest

ROOT = tempfile.mkdtemp(prefix="meshsat-unit-")
for name in ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
    os.environ[name] = os.path.join(ROOT, name.split("_")[1].lower())
    os.makedirs(os.environ[name], exist_ok=True)


class IsolationTest(unittest.TestCase):
    def test_the_app_writes_under_the_tests_own_directories(self):
        import sys  # noqa: PLC0415

        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
        from meshsat import store  # noqa: PLC0415

        home = os.path.realpath(os.path.expanduser("~"))
        for path in (store.state_dir() if hasattr(store, "state_dir") else os.environ["XDG_STATE_HOME"], os.environ["XDG_CONFIG_HOME"]):
            self.assertTrue(os.path.realpath(path).startswith(os.path.realpath(ROOT)), path)
            self.assertFalse(os.path.realpath(path).startswith(os.path.join(home, ".local")), path)


if __name__ == "__main__":
    unittest.main()
