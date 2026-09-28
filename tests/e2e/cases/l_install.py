# SPDX-License-Identifier: GPL-3.0-or-later
"""The installed package on this device: the units as the mode requires, the app at the
package's version, the Bridge answering."""
import json
import os
import subprocess

from driver import BenchError

SCENARIO = None  # the live Bridge


def unit(name: str) -> str:
    return subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5).stdout.strip()


def case_upgrade_leaves_everything_running(ctx):
    version = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "meshsat"], capture_output=True, text=True, timeout=5).stdout.strip()
    assert version, "the meshsat package is not installed"
    app_version = subprocess.run(["meshsat-app", "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    assert app_version == f"meshsat-app {version}", f"the app says {app_version!r}, the package is {version}"
    try:
        with open("/run/meshsat/hardware.json", encoding="utf-8") as handle:
            hardware = json.load(handle)
    except OSError as error:
        raise BenchError(f"meshsat-hardware left no verdict: {error}")
    mode = hardware.get("node", "cover")
    assert unit("meshsat-bridge.service") == "active", "the Bridge is not running"
    if mode == "cover":
        assert unit("meshtasticd.service") == "active", "cover mode without the node daemon"
        assert unit("meshsat-radio-watch.timer") == "active", "cover mode without the watchdog"
    else:
        assert unit("meshtasticd.service") != "active", "Bluetooth mode with the node daemon running"
    status = ctx.bridge.get("/api/status")
    assert "node_id" in status, status
    ctx.note(f"package {version}, mode {mode}, node {status.get('node_id')} connected={status.get('connected')}")
    ctx.app.open("home")
    ctx.tree.wait_text("Messages can go out by" if status.get("connected") else "Nothing can send yet.", timeout=15)
    ctx.shot("home-live")
    assert unit("meshsat-notify.service") in ("active", "inactive", "unknown", "")  # a user unit: not this session's
    assert not os.path.exists("/run/meshsat/e2e-should-not-exist")
