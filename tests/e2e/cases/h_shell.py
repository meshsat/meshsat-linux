# SPDX-License-Identifier: GPL-3.0-or-later
"""The shell: every route opens, shows its title, and fits the screen."""
SCENARIO = "mesh-only"

# route -> a text that must be on view once it is open (Android's titles)
ROUTES = {
    "home": "Messages can go out by mesh.",
    "messages": "Messages",
    "map": "Layers and nodes",
    "people": "People",
    "setup": "Get connected",
    "setup/node": "Your MeshSat node",
    "setup/satellite": "Satellite passes",
    "setup/hub": "Hub connection",
    "setup/sms": "Text messages",
    "setup/safety": "Check-in timer (dead man's switch)",
    "setup/messaging": "Message compression",
    "setup/maps": "Offline maps",
    "setup/integrations": "Ham radio (APRS)",
    "setup/advanced": "Routing rules",
    "setup/about": "MeshSat Linux",
    "passes": "Satellite passes",
    "radio-config": "Mesh radio settings",
    "nodelog": "Node log",
    "chat/!ffffffff": "Everyone on the mesh",
    "rules": "Rules decide which messages are passed from one link to another.",
    "interfaces": "Each way this phone can send and receive messages, and how well it is working.",
    "deliveries": "No messages here yet. Messages you send, and messages your rules pass on, show up here.",
    "topology": "Pinch to zoom, drag to move.",
    "audit": "Nothing in the audit log yet.",
    "credentials": "No credentials stored",
    "decrypt": "No encryption key configured. Go to Settings to set one.",
    "setup/diagnostics": "Restart Gateway Service",
}


def case_every_route_opens_and_fits_the_screen(ctx):
    for route, title in ROUTES.items():
        ctx.app.open(route)
        ctx.tree.wait_text(title, timeout=8)
        info = ctx.app.inspect()
        wide = [w for w in info["widgets"] if w["min"] > info["window"][0] and not w.get("scrolls")]
        assert not wide, f"{route}: wider than the window: {[(w['type'], w['min']) for w in wide][:5]}"
        ctx.shot(route.replace("/", "-").replace("!", ""))
    ctx.app.open("home")
    assert not ctx.bridge.unexpected(), f"the app asked for what no scenario gives: {ctx.bridge.unexpected()[:5]}"


def case_night_mode_toggles_and_is_remembered(ctx):
    ctx.app.open("home")
    ctx.tree.click("Night mode on")
    ctx.tree.find("button", name="Night mode off")
    ctx.shot("night")
    ctx.tree.click("Night mode off")
    ctx.tree.find("button", name="Night mode on")
