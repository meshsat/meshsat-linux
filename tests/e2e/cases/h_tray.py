# SPDX-License-Identifier: GPL-3.0-or-later
"""The tray icon (outside.tray, notify.py): wherever the shell has a tray (Plasma Mobile, a
desktop; Phosh has none) the notifier registers an org.kde.StatusNotifierItem with the tray's
watcher. A stand-in tray (driver/tray.py) comes up on the test session's bus as a desktop's tray
host would, and reads the item as a tray draws it: MeshSat, the satellite or the mesh in the
owner's words, an icon of the package's own theme, all following the Bridge; a click opens the
app on Home; a tray that restarts gets the item again. What a real tray host draws from it is the
desktop's (not tried here).

Needs wip-100/patch-100-outside.py (driver/tray.py, and the notifier opening a test instance)."""
import glob
import os
import time

from driver.tray import Tray

SCENARIO = "mesh-only"
NOTIFIER = True
# (IconName, the tooltip's text) from outside.status(): the owner's words (CLAUDE.md, "Outside the app")
MESH_ONLY = ("meshsat-transport-mesh-symbolic", "Mesh: 1 node")
SATELLITE = ("meshsat-iridium-3-symbolic", "Satellite: 3/5, Mesh: 1 node")
NO_BRIDGE = ("meshsat-iridium-0-symbolic", "Nothing can send yet.")
_tray = []  # the stand-in tray these cases share; the last case stops it


def tray() -> Tray:
    if _tray and _tray[0].alive():
        return _tray[0]
    _tray[:] = [Tray().start()]
    return _tray[0]


def shows(t: Tray, item: dict, expected: tuple, timeout: float = 20.0) -> dict:
    """Until the item's icon and tooltip are these (the notifier polls every 5 s); its properties."""
    icon, words = expected
    deadline = time.time() + timeout
    props = {}
    while time.time() < deadline:
        props = t.properties(item)
        tip = tuple(props.get("ToolTip") or ("", [], "", ""))
        if props.get("IconName") == icon and tip[3] == words:
            return props
        time.sleep(0.5)
    raise AssertionError(f"the tray item never showed {icon} / {words!r}; it shows {props}")


def themed(ctx, icon: str) -> bool:
    """The icon is in the app's own hicolor tree (the package installs the same files in
    /usr/share/icons/hicolor, where a tray looks them up)."""
    return bool(glob.glob(os.path.join(ctx.app.app_dir, "meshsat", "icons", "hicolor", "scalable", "*", icon + ".svg")))


def notifier_well(ctx) -> None:
    try:
        with open(os.path.join(ctx.app.work, "notify.stderr"), encoding="utf-8", errors="replace") as handle:
            said = handle.read()
    except OSError:
        said = ""
    assert "Traceback" not in said and "the tray refused the icon" not in said and "cannot open the app" not in said, said[-1500:]


def case_a_the_item_registers_with_a_tray(ctx):
    ctx.bridge.scenario("mesh-only")
    t = tray()
    item = t.wait_item(timeout=10)
    assert item["service"] == item["sender"], f"the item names another bus: {item}"
    props = shows(t, item, MESH_ONLY)
    fixed = {k: props.get(k) for k in ("Category", "Id", "Title", "Status", "ItemIsMenu", "Menu")}
    assert fixed == {"Category": "Communications", "Id": "meshsat", "Title": "MeshSat", "Status": "Active", "ItemIsMenu": False, "Menu": "/NO_DBUSMENU"}, fixed
    assert tuple(props["ToolTip"]) == ("meshsat-transport-mesh-symbolic", [], "MeshSat", "Mesh: 1 node"), props["ToolTip"]
    assert themed(ctx, props["IconName"]), f"{props['IconName']} is not in the package's icon theme"
    notifier_well(ctx)


def case_b_the_icon_and_the_words_follow_the_bridge(ctx):
    t = tray()
    item = t.wait_item(timeout=10)
    shows(t, item, MESH_ONLY)
    since = time.time()
    ctx.bridge.scenario("satellite-3-bars")
    props = shows(t, item, SATELLITE)
    members = {s["member"] for s in t.signals_since(since) if s["sender"] == item["sender"]}
    assert {"NewIcon", "NewToolTip"} <= members, f"a tray redraws on NewIcon and NewToolTip; it got {members}"
    assert themed(ctx, props["IconName"]), props["IconName"]
    ctx.bridge.scenario("fresh")  # the Bridge not running
    props = shows(t, item, NO_BRIDGE)
    assert themed(ctx, props["IconName"]), props["IconName"]
    ctx.bridge.scenario("mesh-only")
    shows(t, item, MESH_ONLY)
    notifier_well(ctx)


def case_c_a_click_opens_the_app(ctx):
    ctx.bridge.scenario("mesh-only")
    t = tray()
    item = t.wait_item(timeout=10)
    for method in ("Activate", "SecondaryActivate"):
        ctx.app.open("setup")
        ctx.tree.wait_text("Get connected", timeout=10)
        ctx.app.mark()
        t.call(item, method, 0, 0)
        deadline = time.time() + 10
        while time.time() < deadline and not [e for e in ctx.app.trace_since_mark() if e.get("kind") == "route" and e.get("route") == "home"]:
            time.sleep(0.3)
        assert [e for e in ctx.app.trace_since_mark() if e.get("kind") == "route" and e.get("route") == "home"], f"{method} did not open Home"
        ctx.tree.wait_text("Messages can go out by mesh.", timeout=8)
    notifier_well(ctx)


def case_z_a_tray_that_restarts_gets_the_item_again(ctx):
    t = tray()
    t.wait_item(timeout=10)
    t.stop()
    _tray.clear()
    time.sleep(1.0)
    again = Tray().start()
    try:
        item = again.wait_item(timeout=10)
        shows(again, item, MESH_ONLY)
    finally:
        again.stop()
    notifier_well(ctx)
