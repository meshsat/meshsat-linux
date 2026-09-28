# SPDX-License-Identifier: GPL-3.0-or-later
"""The parity ledger is well formed: every verified row names a test that exists, every
exclusion its reason, every row a state and a kind the keeper knows."""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "tools", "parity-check.py")


def keeper():
    spec = importlib.util.spec_from_file_location("parity_check", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LedgerTest(unittest.TestCase):
    def test_the_ledger_has_no_problems(self):
        pc = keeper()
        ledger = pc.load(pc.LEDGER, None)
        self.assertIsNotNone(ledger, "tests/parity/ledger.json is missing")
        problems = pc.check(ledger, pc.test_names())
        self.assertEqual(problems, [])

    def test_the_ledger_covers_every_android_route(self):
        pc = keeper()
        ledger = pc.load(pc.LEDGER, {"rows": []})
        ids = {r["id"] for r in ledger["rows"]}
        for route in ("home", "messages", "chat", "map", "people", "setup", "setup.node", "setup.satellite", "setup.hub", "setup.sms", "setup.safety", "setup.messaging",
                      "setup.maps", "setup.integrations", "setup.advanced", "passes", "radio-config", "rules", "interfaces", "deliveries", "topology", "geofence",
                      "audit", "credentials", "decrypt", "nodelog", "about", "sos", "welcome"):
            self.assertIn(route, ids, f"no ledger row for the route {route}")

    def test_the_words_list_is_pinned_to_android(self):
        pc = keeper()
        strings = pc.load(pc.STRINGS, None)
        self.assertIsNotNone(strings, "tests/parity/android-strings.json is missing: run tools/android-strings.py")
        self.assertTrue(strings["android"].startswith("v2.19.4"), strings["android"])
        self.assertGreater(strings["strings"], 1000)


if __name__ == "__main__":
    unittest.main()
