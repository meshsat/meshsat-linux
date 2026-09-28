# SPDX-License-Identifier: GPL-3.0-or-later
"""The routes are Android's, with the tab that owns each."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from meshsat import routes  # noqa: E402


class RoutesTest(unittest.TestCase):
    def test_android_routes_have_their_tab(self):
        self.assertEqual(routes.tab_of("home"), "home")
        self.assertEqual(routes.tab_of("passes"), "home")
        self.assertEqual(routes.tab_of("messages"), "messages")
        self.assertEqual(routes.tab_of("chat/!ffffffff"), "messages")
        self.assertEqual(routes.tab_of("map"), "map")
        self.assertEqual(routes.tab_of("people"), "people")
        self.assertEqual(routes.tab_of("topology"), "people")
        for route in ("setup", "setup/node", "radio-config", "rules", "sos", "about", "geofence"):
            self.assertEqual(routes.tab_of(route), "setup", route)

    def test_old_names_still_resolve(self):
        self.assertEqual(routes.resolve("node"), "setup/node")
        self.assertEqual(routes.resolve("radio"), "radio-config")
        self.assertEqual(routes.resolve("everyone"), "chat/!ffffffff")
        self.assertEqual(routes.resolve("passes"), "passes")

    def test_every_route_names_a_module_and_class_or_a_tab(self):
        for route, (tab, module, cls) in routes.ROUTES.items():
            self.assertIn(tab, routes.TABS, route)
            self.assertEqual(module is None, cls is None, route)

    def test_lanes_and_notifications_lead_where_android_goes(self):
        self.assertEqual(routes.LANES["mesh"], "setup/node")
        self.assertEqual(routes.LANES["hub"], "setup/hub")
        self.assertEqual(set(routes.OPENABLE), {"sos", "messages", "home"})


if __name__ == "__main__":
    unittest.main()
