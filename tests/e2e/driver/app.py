# SPDX-License-Identifier: GPL-3.0-or-later
"""The app as a process under test: started with its test seams set (its own application id,
its own configuration and state directories, the Bridge it talks to, a trace file, the units'
states), driven through its D-Bus actions, watched through its stderr and its trace."""
import json
import os
import shutil
import subprocess
import time

from . import HarnessError
from .a11y import Tree


class App:
    def __init__(self, work: str, bridge_url: str, app_dir: str | None = None, app_id: str = "net.meshsat.Test",
                 units: str = "meshtasticd.service=active,meshsat-bridge.service=active", hardware: dict | None = None, poll: float = 2.0, env: dict | None = None):
        self.work = work
        self.bridge_url = bridge_url
        self.app_dir = app_dir or "/usr/lib/meshsat/app"
        self.app_id = app_id
        self.units = units
        self.hardware = hardware if hardware is not None else {"node": "cover", "why": "the LoRa back cover answers on the pogo bus", "model": "PinePhone Pro"}
        self.poll = poll
        self.extra_env = env or {}
        self.process = None
        self.tree = None
        self.stderr_path = os.path.join(work, "app.stderr")
        self.trace_path = os.path.join(work, "trace.jsonl")
        self._trace_seen = 0

    def environment(self) -> dict:
        env = dict(os.environ)
        for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            path = os.path.join(self.work, "xdg", name.split("_")[1].lower())
            os.makedirs(path, exist_ok=True)
            env[name] = path
        hardware = os.path.join(self.work, "hardware.json")
        with open(hardware, "w", encoding="utf-8") as handle:
            json.dump(self.hardware, handle)
        status = os.path.join(self.work, "status.json")
        if not os.path.exists(status):
            with open(status, "w", encoding="utf-8") as handle:
                json.dump({"radio": "ok", "message": "The radio answers."}, handle)
        env.update({"MESHSAT_APP_ID": self.app_id, "MESHSAT_APP_TEST": "1", "MESHSAT_APP_BRIDGE": self.bridge_url, "MESHSAT_APP_TRACE": self.trace_path,
                    "MESHSAT_APP_UNITS": self.units, "MESHSAT_APP_HARDWARE": hardware, "MESHSAT_APP_STATUS": status, "MESHSAT_APP_POLL": str(self.poll),
                    "PYTHONPATH": self.app_dir, "GTK_A11Y": "atspi", "GSK_RENDERER": os.environ.get("GSK_RENDERER", "cairo"), "LC_ALL": "C.UTF-8", "TZ": os.environ.get("TZ", "UTC")})
        env.update(self.extra_env)
        return env

    def start(self, timeout: float = 25.0) -> "App":
        os.makedirs(self.work, exist_ok=True)
        for path in (self.stderr_path, self.trace_path):
            if os.path.exists(path):
                os.remove(path)
        self.process = subprocess.Popen(["python3", "-m", "meshsat"], env=self.environment(), stdout=subprocess.DEVNULL, stderr=open(self.stderr_path, "w", encoding="utf-8"), cwd=self.work)
        self.tree = Tree(self.process.pid)
        self.tree.wait_for_application(timeout)
        # The window opens once the first poll is in (or 1.5 s later): wait for the frame.
        self.tree.find("frame", timeout=timeout)
        return self

    def action(self, name: str, argument: str | None = None) -> None:
        command = ["gapplication", "action", self.app_id, name]
        if argument is not None:
            command.append(f"'{argument}'")
        run = subprocess.run(command, capture_output=True, text=True, timeout=10)
        if run.returncode != 0:
            raise HarnessError(f"gapplication {name}: {run.stderr.strip()}")

    def open(self, route: str) -> None:
        self.action("open", route)

    def tab(self, name: str) -> None:
        self.action("tab", name)

    def refresh(self) -> None:
        """One poll now (F5): the way a test waits for a changed scenario to reach the screen."""
        self.action("refresh")

    def inspect(self) -> dict:
        path = os.path.join(self.work, "inspect.json")
        if os.path.exists(path):
            os.remove(path)
        self.action("inspect", path)
        deadline = time.time() + 5
        while time.time() < deadline:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    return json.load(handle)
            time.sleep(0.1)
        raise HarnessError("the app wrote no inspection")

    def trace(self) -> list:
        try:
            with open(self.trace_path, encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except OSError:
            return []

    def trace_since_mark(self) -> list:
        return self.trace()[self._trace_seen:]

    def mark(self) -> None:
        """From here on: `trace_since_mark()` and `wait_toast()` look only at what comes after."""
        self._trace_seen = len(self.trace())

    def toasts(self, since_mark: bool = False) -> list:
        events = self.trace_since_mark() if since_mark else self.trace()
        return [e["text"] for e in events if e.get("kind") == "toast"]

    def wait_toast(self, contains: str, timeout: float = 5.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for t in self.toasts(since_mark=True):
                if contains in t:
                    return t
            time.sleep(0.2)
        raise AssertionError(f"no toast with {contains!r} since the mark; toasts: {self.toasts()[-5:]}")

    def http_since_mark(self, method: str | None = None, path_prefix: str = "") -> list:
        return [e for e in self.trace_since_mark() if e.get("kind") == "http" and (method is None or e.get("method") == method) and str(e.get("path", "")).startswith(path_prefix)]

    def stderr(self) -> str:
        try:
            with open(self.stderr_path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    def tracebacks(self) -> list:
        text = self.stderr()
        return [chunk for chunk in text.split("Traceback (most recent call last):")[1:]]

    def screenshot(self, path: str) -> bool:
        if shutil.which("grim") is None:
            return False
        run = subprocess.run(["grim", path], capture_output=True, text=True, timeout=15)
        return run.returncode == 0

    def stop(self) -> None:
        if self.process is None:
            return
        try:
            self.action("quit")
            self.process.wait(timeout=5)
        except (HarnessError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None
