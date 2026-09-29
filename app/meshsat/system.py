# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app asks of the system it runs on: the state of the package's units, the node's
journal, a privileged restart through polkit, a service started for the person at the screen,
the Bridge shared on the network or not.
Under MESHSAT_APP_TEST=1 nothing privileged runs: the command goes to the trace instead, and
unit states come from MESHSAT_APP_UNITS ("meshtasticd.service=active,meshsat-bridge.service=inactive"),
so a test never opens a polkit dialog and never restarts the phone's services."""
import os
import subprocess
import threading

from . import trace
from .model import share

try:
    from gi.repository import GLib
except (ImportError, ValueError):  # the unit tests, on a machine without GTK
    GLib = None

TEST = os.environ.get("MESHSAT_APP_TEST") == "1"
# Sharing the Bridge on the network: meshsat-share keeps the flag and the rules, as root through
# pkexec; anyone may read the flag.
SHARE_TOOL = "/usr/lib/meshsat/bin/meshsat-share"
SHARE_FLAG = "/etc/meshsat/share-on-network"
BRIDGE_ENV = "/etc/meshsat/bridge.env"
_share_running = threading.Event()


def _test_units() -> dict:
    out = {}
    for item in os.environ.get("MESHSAT_APP_UNITS", "").split(","):
        if "=" in item:
            unit, state = item.split("=", 1)
            out[unit.strip()] = state.strip()
    return out


def unit_active(unit: str) -> bool:
    if TEST:
        return _test_units().get(unit, "inactive") == "active"
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def start_unit(unit: str) -> str | None:
    """`systemctl start` as this user (polkit allows the person at the screen the package's
    units, meshsat-hardware for one). None when it worked, else the reason."""
    trace.event("command", command=["systemctl", "start", unit])
    if TEST:
        return None
    try:
        run = subprocess.run(["systemctl", "start", unit], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as error:
        return str(error)
    return None if run.returncode == 0 else (run.stderr.strip() or f"systemctl exited {run.returncode}")


def privileged(*command: str) -> None:
    """A command through polkit's pkexec (a restart of the node's units, say): the person at
    the screen is asked once. Not waited for."""
    trace.event("command", command=["pkexec", *command])
    if TEST:
        return
    try:
        subprocess.Popen(["pkexec", *command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def shared_on_network() -> bool:
    """Whether the Bridge is shared on the network: meshsat-share's flag file is there
    (MESHSAT_APP_SHARE_FLAG names another file: the tests)."""
    return os.path.exists(os.environ.get("MESHSAT_APP_SHARE_FLAG") or SHARE_FLAG)


def share_changing() -> bool:
    """A change of the sharing is under way (pkexec asking for the password, the rules
    loading): the switch waits for it, whichever page started it."""
    return _share_running.is_set()


def share_on_network(on: bool, done) -> None:
    """Share the Bridge on the network, or stop: `pkexec meshsat-share on|off` on a thread (the
    person is asked for their password), then `done(ok)` on the main loop once it exited (ok:
    it exited 0; a password prompt that was dismissed is 126). Under test nothing runs: the
    command goes to the trace as `privileged` writes it, the file MESHSAT_APP_SHARE_FLAG names
    (never the system's own) is made or removed, and done(True)."""
    command = ["pkexec", SHARE_TOOL, "on" if on else "off"]
    trace.event("command", command=command)
    _share_running.set()

    def finish(ok: bool) -> None:
        _share_running.clear()
        if GLib is not None:
            GLib.idle_add(lambda: done(ok) or False)
        else:
            done(ok)

    if TEST:
        path, ok = os.environ.get("MESHSAT_APP_SHARE_FLAG"), True
        if path:
            try:
                if on:
                    open(path, "a", encoding="utf-8").close()
                elif os.path.exists(path):
                    os.remove(path)
            except OSError:
                ok = False
        finish(ok)
        return

    def run() -> None:
        try:
            ok = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        finish(ok)

    threading.Thread(target=run, daemon=True).start()


def bridge_port() -> int:
    """The Bridge's port as meshsat-share opens it: MESHSAT_PORT in /etc/meshsat/bridge.env
    (MESHSAT_APP_BRIDGE_ENV names another file), 6050 without one."""
    try:
        with open(os.environ.get("MESHSAT_APP_BRIDGE_ENV") or BRIDGE_ENV, encoding="utf-8", errors="replace") as handle:
            return share.bridge_port(handle.read())
    except OSError:
        return share.DEFAULT_PORT


def lan_addresses() -> list:
    """This phone's addresses on the network it is on, the ones to open the Bridge at
    (model/share.py says which count). MESHSAT_APP_ADDRESSES="192.168.1.20,10.0.0.5" stands in
    for them (the tests, and captures that must not show a real address); under test without
    it, none."""
    override = os.environ.get("MESHSAT_APP_ADDRESSES")
    if override is not None:
        return [a.strip() for a in override.split(",") if a.strip()]
    if TEST:
        return []
    try:
        run = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return []
    try:
        virtual = set(os.listdir("/sys/devices/virtual/net"))
    except OSError:
        virtual = set()
    return share.lan_addresses(run.stdout, virtual)


def unit_enabled(unit: str) -> bool:
    """Whether a unit starts at boot. Under test from MESHSAT_APP_ENABLED ("unit=enabled,...")."""
    if TEST:
        for item in os.environ.get("MESHSAT_APP_ENABLED", "").split(","):
            if "=" in item and item.split("=", 1)[0].strip() == unit:
                return item.split("=", 1)[1].strip() == "enabled"
        return False
    try:
        run = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return False
    return run.stdout.strip() == "enabled"


def journal_follow(unit: str, cursor: str | None, lines: int = 200, timeout: float = 5.0) -> tuple:
    """The unit's journal lines since `cursor` (the last `lines` the first time), and the
    cursor to ask from next time: (lines, cursor, why not). Under test the journal is the file
    MESHSAT_APP_JOURNAL and the cursor its line count."""
    if TEST:
        path = os.environ.get("MESHSAT_APP_JOURNAL", "")
        try:
            with open(path, encoding="utf-8") as handle:
                all_lines = handle.read().splitlines()
        except OSError:
            return [], cursor, None
        start = int(cursor) if cursor and cursor.isdigit() else max(0, len(all_lines) - lines)
        return all_lines[start:], str(len(all_lines)), None
    command = ["journalctl", "-u", unit, "--no-pager", "-o", "cat", "--show-cursor"]
    command += ["--after-cursor", cursor] if cursor else ["-n", str(lines)]
    try:
        run = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        return [], cursor, str(error)
    out, new_cursor = [], cursor
    for line in run.stdout.splitlines():
        if line.startswith("-- cursor: "):
            new_cursor = line[len("-- cursor: "):].strip()
        elif line.startswith("-- No entries --"):
            continue
        elif line.startswith("Hint: ") or line.startswith("      Users in groups") or line.startswith("      Pass -q"):
            continue
        else:
            out.append(line)
    why = None
    if not out and not new_cursor and "not seeing messages from other users" in (run.stdout + run.stderr):
        why = "not in systemd-journal"
    return out, new_cursor, why


def journal(unit: str, lines: int = 80, timeout: float = 5.0) -> str:
    """The last lines of a unit's journal, or the reason there are none."""
    if TEST:
        path = os.environ.get("MESHSAT_APP_JOURNAL", "")
        try:
            with open(path, encoding="utf-8") as handle:
                return "".join(handle.readlines()[-lines:])
        except OSError:
            return ""
    try:
        run = subprocess.run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return "Cannot read the node's log."
    if run.returncode != 0 and not run.stdout:
        return run.stderr.strip() or "Cannot read the node's log."
    return run.stdout


def bluetooth_on() -> None:
    """NodeLinkBanner's "Tap to switch it on": what Phosh's own Bluetooth switch does
    (gnome-settings-daemon lifts the rfkill block), then BlueZ's adapter power; when neither
    answers, the Settings page for Bluetooth, as Android falls back to its Bluetooth settings.
    Not waited for."""
    trace.event("command", command=["bluetooth", "on"])
    if TEST:
        return
    import threading  # noqa: PLC0415

    def run() -> None:
        lifted = False
        try:
            lifted = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.SettingsDaemon.Rfkill", "--object-path", "/org/gnome/SettingsDaemon/Rfkill",
                                     "--method", "org.freedesktop.DBus.Properties.Set", "org.gnome.SettingsDaemon.Rfkill", "BluetoothAirplaneMode", "<false>"],
                                    capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
        powered = False
        try:
            powered = subprocess.run(["busctl", "--system", "set-property", "org.bluez", "/org/bluez/hci0", "org.bluez.Adapter1", "Powered", "b", "true"],
                                     capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
        if not lifted and not powered:
            try:
                subprocess.Popen(["gnome-control-center", "bluetooth"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass

    threading.Thread(target=run, daemon=True).start()
