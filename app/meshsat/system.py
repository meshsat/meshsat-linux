# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app asks of the system it runs on: the state of the package's units, the node's
journal, a privileged restart through polkit, a service started for the person at the screen.
Under MESHSAT_APP_TEST=1 nothing privileged runs: the command goes to the trace instead, and
unit states come from MESHSAT_APP_UNITS ("meshtasticd.service=active,meshsat-bridge.service=inactive"),
so a test never opens a polkit dialog and never restarts the phone's services."""
import os
import subprocess

from . import trace

TEST = os.environ.get("MESHSAT_APP_TEST") == "1"


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
