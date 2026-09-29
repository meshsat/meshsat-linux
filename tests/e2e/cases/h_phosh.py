# SPDX-License-Identifier: GPL-3.0-or-later
"""MeshSat in Phosh (outside.tile, outside.lockscreen): the package's two Phosh plugins, the
quick-settings tile and the lock-screen widget. This tier's session is a headless phoc without
Phosh, so each plugin is loaded as Phosh's plugin loader loads it, from the installed module, but
in a GTK 3 host of its own (driver/phosh_host.py). They are installed where Phosh looks, built for
this device, with the descriptors Phosh Mobile Settings lists and the module cache GIO reads; they
show what the notifier says on net.meshsat.Status in the owner's words and follow the Bridge; they
say so when MeshSat is not running; a tap on the tile opens the app on Home. Phosh itself drawing
them (the tile among its quick settings, the widget on its lock screen) is not proven here:
wip-100/tile-lockscreen.md.

The tile runs under stand-ins of Phosh 0.46's PhoshQuickSetting and PhoshStatusIcon, or under
Phosh's own types with MESHSAT_E2E_PHOSH_TYPES=libphosh (the phone needs libphosh-0.45-0).

Needs wip-100/patch-100-outside.py (driver/phosh_host.py, and the notifier opening a test instance)."""
import configparser
import glob
import os
import platform
import subprocess
import time

from driver.phosh_host import KINDS, PluginHost, plugin_dir

SCENARIO = "mesh-only"
NOTIFIER = True
TYPES = os.environ.get("MESHSAT_E2E_PHOSH_TYPES", "stand-in")
ELF_MACHINES = {"aarch64": 183, "x86_64": 62, "armv7l": 40, "riscv64": 243}
# What the notifier's outside.status() makes of each scenario (the owner's words for the tile):
# (tile, tile on, the widget's satellite line, the widget's mesh line, the icon of both)
SHOWS = {
    "mesh-only": ("Mesh: 1 node", True, "No satellite modem.", "Connected to meshsat-pinephone-pro.", "meshsat-transport-mesh-symbolic"),
    "advanced": ("Mesh: 2 nodes", True, "No satellite modem.", "Connected to meshsat-pinephone-pro.", "meshsat-transport-mesh-symbolic"),
    "satellite-3-bars": ("Satellite: 3/5", True, "Iridium signal 3/5", "Connected to meshsat-pinephone-pro.", "meshsat-iridium-3-symbolic"),
    "bluetooth-pairing": ("Mesh: connecting", False, "No satellite modem.", "Reconnecting to your node.", "meshsat-iridium-0-symbolic"),
    "fresh": ("MeshSat: no node", False, "No satellite modem.", "The Bridge is not running on this device.", "meshsat-iridium-0-symbolic"),
}
NOT_RUNNING = ("MeshSat: off", "MeshSat is not running.", "meshsat-iridium-0-symbolic")  # the plugins' own words without net.meshsat.Status


def widget_shows(scenario: str):
    _tile, _on, satellite, mesh, icon = SHOWS[scenario]
    return lambda s: s.get("shown") == ["MeshSat", satellite, mesh] and s.get("icons") == [icon]


def tile_shows(scenario: str):
    tile, on, _satellite, _mesh, icon = SHOWS[scenario]
    return lambda s: s.get("info") == tile and s.get("active") is on and s.get("icon") == icon


def themed(ctx, icon: str) -> bool:
    return bool(glob.glob(os.path.join(ctx.app.app_dir, "meshsat", "icons", "hicolor", "scalable", "*", icon + ".svg")))


def quiet(host: PluginHost) -> None:
    said = [line for line in host.stderr().splitlines() if "CRITICAL" in line or "Traceback" in line]
    assert not said, said[:6]


def case_a_installed_where_phosh_looks_for_them(ctx):
    folder = plugin_dir()
    assert folder, "the package installed no Phosh plugins (/usr/lib/<triplet>/phosh/plugins)"
    machine = ELF_MACHINES.get(platform.machine())
    cache = {}
    cache_path = os.path.join(folder, "giomodule.cache")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as handle:
            for line in handle:
                if ":" in line:
                    name, points = line.split(":", 1)
                    cache[name.strip()] = [p.strip() for p in points.split(",") if p.strip()]
    for kind, (point, plugin_id) in KINDS.items():
        module = os.path.join(folder, f"libphosh-plugin-meshsat-{kind}.so")
        assert os.path.exists(module), module
        with open(module, "rb") as handle:
            head = handle.read(20)
        assert head[:4] == b"\x7fELF", f"{module} is not a shared object"
        built_for = int.from_bytes(head[18:20], "little")
        assert machine is None or built_for == machine, f"{module} is built for ELF machine {built_for}; this device is {platform.machine()} ({machine})"
        descriptor = configparser.ConfigParser(interpolation=None)
        assert descriptor.read(os.path.join(folder, f"{plugin_id}.plugin")), f"no {plugin_id}.plugin beside it"
        found = {k: descriptor.get("Plugin", k, fallback="") for k in ("Id", "Types", "Plugin")}
        assert found == {"Id": plugin_id, "Types": kind + ";", "Plugin": module}, found
        name = os.path.basename(module)
        if name in cache:
            assert cache[name] == [point], f"{cache_path} lists {name} at {cache[name]}, not {point}"
        else:
            ctx.note(f"{name} is not in {cache_path}: GIO loads it at once rather than lazily (it works; postinst's gio-querymodules lists it)")


def case_b_the_lock_screen_widget_follows_the_bridge(ctx):
    host = PluginHost("lockscreen", ctx.app.work)
    try:
        assert host.hello["type"] == "MeshsatLockscreen" and host.hello["parent"] == "GtkBox", host.hello
        for scenario in ("mesh-only", "satellite-3-bars", "bluetooth-pairing", "fresh", "mesh-only"):
            ctx.bridge.scenario(scenario)
            state = host.wait(widget_shows(scenario), timeout=20, what=f"{scenario}: {SHOWS[scenario][2:]}")
            assert all(themed(ctx, icon) for icon in state["icons"]), state["icons"]
            if scenario == "satellite-3-bars":
                ctx.shot("lockscreen-widget")
        quiet(host)
    finally:
        host.stop()


def case_c_the_tile_follows_the_bridge_and_a_tap_opens_the_app(ctx):
    host = PluginHost("quick-setting", ctx.app.work, TYPES)
    try:
        assert host.hello["type"] == "MeshsatQuickSetting" and host.hello["parent"] == "PhoshQuickSetting", host.hello
        ctx.note(f"the tile ran under {host.hello.get('types')} Phosh types")
        for scenario in ("mesh-only", "advanced", "satellite-3-bars", "bluetooth-pairing", "fresh", "mesh-only"):
            ctx.bridge.scenario(scenario)
            state = host.wait(tile_shows(scenario), timeout=20, what=f"{scenario}: {SHOWS[scenario][:2]}")
            assert themed(ctx, state["icon"]), state["icon"]
            if scenario == "satellite-3-bars":
                ctx.shot("quick-setting")
        # A tap: net.meshsat.Status.Open("home"), the notifier opens the app there
        ctx.app.open("setup")
        ctx.tree.wait_text("Get connected", timeout=10)
        ctx.app.mark()
        assert host.click().get("clicked"), "the tile took no tap"
        deadline = time.time() + 10
        while time.time() < deadline and not [e for e in ctx.app.trace_since_mark() if e.get("kind") == "route" and e.get("route") == "home"]:
            time.sleep(0.3)
        assert [e for e in ctx.app.trace_since_mark() if e.get("kind") == "route" and e.get("route") == "home"], "a tap on the tile did not open Home"
        quiet(host)  # a property or signal the tile uses that Phosh's types lack is a CRITICAL here
    finally:
        host.stop()


def case_z_without_the_notifier_they_say_so(ctx):
    """Last: it stops the module's notifier and runs its own until the end."""
    widget = PluginHost("lockscreen", ctx.app.work)
    tile = PluginHost("quick-setting", ctx.app.work, TYPES)
    again = None
    try:
        ctx.bridge.scenario("mesh-only")
        widget.wait(widget_shows("mesh-only"), timeout=20, what="mesh-only")
        tile.wait(tile_shows("mesh-only"), timeout=20, what="mesh-only")
        ctx.notifier.terminate()
        ctx.notifier.wait(timeout=10)
        tile_words, widget_words, icon = NOT_RUNNING
        widget.wait(lambda s: s.get("shown") == ["MeshSat", widget_words] and s.get("icons") == [icon], timeout=15, what=widget_words)
        tile.wait(lambda s: s.get("info") == tile_words and s.get("active") is False and s.get("icon") == icon, timeout=15, what=tile_words)
        ctx.shot("without-the-notifier")
        again = subprocess.Popen(["python3", "-m", "meshsat.notify"], env=dict(ctx.app.environment(), GSETTINGS_BACKEND="memory"), stdout=subprocess.DEVNULL,
                                 stderr=open(os.path.join(ctx.app.work, "notify-again.stderr"), "w", encoding="utf-8"), cwd=ctx.app.work)
        widget.wait(widget_shows("mesh-only"), timeout=25, what="MeshSat back")
        tile.wait(tile_shows("mesh-only"), timeout=25, what="MeshSat back")
    finally:
        widget.stop()
        tile.stop()
        if again is not None:
            again.terminate()
            try:
                again.wait(timeout=5)
            except subprocess.TimeoutExpired:
                again.kill()
