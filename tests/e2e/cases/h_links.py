# SPDX-License-Identifier: GPL-3.0-or-later
"""Links (InterfacesScreen.kt): the six tabs with their words and badges, a link switched off
after a question and on again, a reconnect on request; the empty texts. The scenario's links:
the mesh working (the Bridge binds no device for it, the app sees the lane up), the satellite
off with its modem's port, SMS failing, the Hub off, ham radio switched off."""
SCENARIO = "queue-busy"
LINKS = ("Mesh", "Satellite", "SMS", "Ham radio", "Hub")


def start(ctx, scenario: str = "queue-busy") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.open("interfaces")
    ctx.tree.wait_text("Each way this phone can send and receive messages, and how well it is working.", timeout=10)


def case_six_tabs_in_androids_words(ctx):
    start(ctx)
    ctx.tree.wait_text("Working", timeout=10)
    for tab in ("Links", "Rules", "Capabilities", "Groups", "Backup links", "Health"):
        ctx.tree.find("button", name=tab)
    for link in LINKS:
        ctx.tree.switch(f"Use {link}")
    assert ctx.tree.switch("Use Mesh").checked and not ctx.tree.switch("Use Ham radio").checked
    for words in ("last message 5 min ago", "Off", "Not working", "modem not registered", "Switched off"):
        ctx.tree.wait_text(words)
    assert len(ctx.tree.find_all("button", name="Try to connect now")) == 1, "only the satellite has a device to reconnect"
    ctx.shot("links")
    ctx.tree.click("Capabilities")
    for words in ("What each link can carry, and how it retries.", "Largest message", "237 bytes", "340 bytes", "160 bytes", "No limit",
                  "Carries data, not only text", "Paid", "Retries: waits for the next satellite pass, at most 10 times.",
                  "Retries: first after 30 s, then up to 300 s apart, at most 3 times."):
        ctx.tree.wait_text(words)
    ctx.shot("capabilities")
    ctx.tree.click("Groups")
    for words in ("Named groups of nodes, senders or message types that rules can match.", "Spammers", "2 members", "Senders"):
        ctx.tree.wait_text(words)
    ctx.tree.click("Backup links")
    for words in ("Groups of links that stand in for each other, or that all carry the same message.", "Satellite backup", "2 links", "Uses the first link that works"):
        ctx.tree.wait_text(words)
    ctx.tree.click("Health")
    for words in ("A score out of 100 for each link, from its signal, how many messages got through, how fast, and what it costs.", "85", "Not connected",
                  "Got through", "Low cost"):
        ctx.tree.wait_text(words)
    ctx.shot("health")
    ctx.tree.click("Rules")
    for words in ("The routing rules of every link. Change them in Routing rules.", "SOS to satellite", "Forward: Mesh to Satellite", "No matches yet", "3 matches",
                  "Drop: Messages from SMS"):
        ctx.tree.wait_text(words)
    ctx.tree.click("Links")


def case_switch_off_asks_first(ctx):
    start(ctx)
    ctx.tree.wait_text("Working", timeout=10)
    ctx.app.mark()
    before = ctx.bridge.count()
    ctx.tree.toggle("Use Mesh")
    ctx.tree.wait_text("Switch off Mesh?")
    ctx.tree.wait_text("Messages stop going out by Mesh until you switch it back on. Messages waiting for it stay in the queue.")
    ctx.shot("switch-off-asked")
    ctx.tree.click_in_dialog("Keep it on")
    ctx.tree.wait_switch("Use Mesh", True)
    assert not [r for r in ctx.bridge.requests(before) if r["method"] == "POST"], "Keep it on sent a request"
    ctx.tree.toggle("Use Mesh")
    ctx.tree.wait_text("Switch off Mesh?")
    ctx.tree.click_in_dialog("Switch off")
    ctx.bridge.wait_request("POST", "/api/interfaces/mesh_0/disable", since=before)
    ctx.app.wait_toast("Mesh switched off")
    ctx.tree.wait_switch("Use Mesh", False)
    ctx.tree.wait_gone("Working", timeout=10)  # the mesh was the one link working
    count = ctx.bridge.count()
    ctx.tree.toggle("Use Mesh")
    ctx.bridge.wait_request("POST", "/api/interfaces/mesh_0/enable", since=count)
    ctx.app.wait_toast("Mesh switched on")
    ctx.tree.wait_switch("Use Mesh", True)
    ctx.tree.wait_text("Working", timeout=10)
    # The satellite: the same question, the words true of the Bridge.
    ctx.tree.toggle("Use Satellite")
    ctx.tree.wait_text("Switch off Satellite?")
    ctx.tree.wait_text("Messages stop going out by Satellite until you switch it back on. Messages waiting for it stay in the queue.")
    ctx.tree.click_in_dialog("Keep it on")
    # Reconnect: the Bridge is asked to bind the link's device.
    count = ctx.bridge.count()
    ctx.tree.click("Try to connect now")
    bind = ctx.bridge.wait_request("POST", "/api/interfaces/iridium_0/bind", since=count)
    assert bind["body"] == {"device_id": "/dev/ttyUSB4"}, bind
    ctx.app.wait_toast("Trying to connect Satellite now")


def case_empty_texts(ctx):
    start(ctx, "mesh-only")
    ctx.bridge.set("GET /api/interfaces", [])
    ctx.bridge.set("GET /api/interfaces/health", [])
    ctx.app.open("interfaces")
    ctx.tree.wait_text("No links yet. They appear once the MeshSat service is running.", timeout=10)
    ctx.tree.click("Rules")
    ctx.tree.wait_text("No routing rules yet. Add them in Routing rules.")
    ctx.tree.click("Capabilities")
    ctx.tree.wait_text("Nothing to show yet. It appears once the MeshSat service is running.")
    ctx.tree.click("Groups")
    ctx.tree.wait_text("No groups yet.")
    ctx.tree.click("Backup links")
    ctx.tree.wait_text("No backup links set up.")
    ctx.tree.click("Health")
    ctx.tree.wait_text("No scores yet. They appear once the MeshSat service is running.")
    ctx.shot("empty")
    ctx.app.open("home")
