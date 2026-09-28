# SPDX-License-Identifier: GPL-3.0-or-later
"""Every place a screen can be asked for by name (the `open` action over D-Bus, a notification,
a banner, a lane, a link, the capture tool, the tests) and where it leads: Android's route
strings (ui/MeshSatUI.kt) with the tab that owns each, so the tab stays lit on the screens
below it. The screen classes are looked up late: this module has no GTK in it."""

TABS = ("home", "messages", "map", "people", "setup")

# route: (tab, module, class). A route with no class is the tab itself.
ROUTES = {
    "home": ("home", None, None),
    "messages": ("messages", None, None),
    "map": ("map", None, None),
    "people": ("people", None, None),
    "setup": ("setup", None, None),
    "passes": ("home", "passes", "PassesScreen"),
    "topology": ("people", "pages.topology", "TopologyScreen"),
    "audit": ("setup", "pages.audit", "AuditScreen"),
    "credentials": ("setup", "pages.credentials", "CredentialsScreen"),
    "decrypt": ("setup", "pages.decrypt", "DecryptScreen"),
    "setup/diagnostics": ("setup", "pages.diagnostics", "DiagnosticsScreen"),
    "setup/node": ("setup", "setup", "NodeScreen"),
    "setup/satellite": ("setup", "setup", "SatelliteScreen"),
    "setup/hub": ("setup", "setup", "HubScreen"),
    "setup/sms": ("setup", "setup", "SmsScreen"),
    "setup/safety": ("setup", "pages.safety", "SafetyScreen"),
    "setup/messaging": ("setup", "setup", "MessagingScreen"),
    "setup/maps": ("setup", "setup", "MapsScreen"),
    "setup/integrations": ("setup", "setup", "IntegrationsScreen"),
    "setup/advanced": ("setup", "setup", "AdvancedScreen"),
    "setup/about": ("setup", "setup", "AboutScreen"),
    "radio-config": ("setup", "setup", "RadioScreen"),
    "about": ("setup", "setup", "AboutScreen"),
    "nodelog": ("setup", "pages.nodelog", "NodeLogScreen"),
    "sos": ("setup", "pages.sos", "SosScreen"),
    "rules": ("setup", "pages.rules", "RulesScreen"),
    "interfaces": ("setup", "pages.links", "LinksScreen"),
    "deliveries": ("setup", "pages.deliveries", "DeliveryScreen"),
}

# The names the `open` action took before the routes were Android's (kept for the tools).
ALIASES = {"node": "setup/node", "satellite": "setup/satellite", "hub": "setup/hub", "sms": "setup/sms", "safety": "setup/safety",
           "messaging": "setup/messaging", "maps": "setup/maps", "integrations": "setup/integrations", "radio": "radio-config",
           "advanced": "setup/advanced", "everyone": "chat/!ffffffff", "links": "interfaces", "queue": "deliveries", "diagnostics": "setup/diagnostics"}

# Which routes a notification may open (MainActivity.kt OPENABLE_ROUTES), and where a lane leads.
OPENABLE = ("sos", "messages", "home")
LANES = {"mesh": "setup/node", "satellite": "setup/satellite", "hub": "setup/hub", "sms": "setup/sms"}


def resolve(name: str) -> str:
    return ALIASES.get(name, name)


def tab_of(route: str) -> str:
    """The tab a route belongs to, as MeshSatUI.tabOf."""
    if route in ROUTES:
        return ROUTES[route][0]
    if route.startswith("chat/"):
        return "messages"
    return "setup"


def screen_of(route: str):
    """The screen class behind a route, or None for a tab."""
    entry = ROUTES.get(route)
    if entry is None or entry[2] is None:
        return None
    module = __import__(f"{__package__}.{entry[1]}", fromlist=[entry[2]])
    return getattr(module, entry[2])
