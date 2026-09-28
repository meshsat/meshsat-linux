# SPDX-License-Identifier: GPL-3.0-or-later
"""The Bridge behind the app under test: the scripted one, started in this process and told
what to answer; or the live one on this device, only read."""
import json
import os
import sys
import time
import urllib.request

TESTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

from fakebridge import FakeBridge, load_scenario  # noqa: E402


class Scripted:
    """The scripted Bridge as the cases see it."""

    def __init__(self, scenario: str = "mesh-only"):
        self.fake = FakeBridge(load_scenario(scenario)).start()
        self.url = self.fake.url
        self.scenario_name = scenario

    def stop(self) -> None:
        self.fake.stop()

    def scenario(self, name: str, reset_log: bool = True) -> None:
        self.fake.control("POST", "/__fake__/scenario", {"name": name, "reset_log": reset_log})
        self.scenario_name = name

    def set(self, key: str, body, status: int | None = None) -> None:
        order = {"key": key, "body": body}
        if status is not None:
            order["status"] = status
        self.fake.control("POST", "/__fake__/set", order)

    def requests(self, since: int = 0) -> list:
        return self.fake.control("GET", f"/__fake__/requests?since={since}", None)[1]["requests"]

    def count(self) -> int:
        return len(self.fake.requests)

    def unexpected(self) -> list:
        return list(self.fake.unexpected)

    def sent(self) -> list:
        return list(self.fake.sent)

    def event(self, event: dict) -> None:
        self.fake.push(event)

    def delay(self, seconds: float) -> None:
        self.fake.control("POST", "/__fake__/delay", {"seconds": seconds})

    def down(self, down: bool = True) -> None:
        self.fake.control("POST", "/__fake__/down", {"down": down})

    def reset(self) -> None:
        self.fake.control("POST", "/__fake__/reset", {})

    def state(self) -> dict:
        return self.fake.control("GET", "/__fake__/state", None)[1]

    def wait_request(self, method: str, path_prefix: str, timeout: float = 5.0, since: int = 0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for r in self.requests(since):
                if r["method"] == method and r["path"].startswith(path_prefix):
                    return r
            time.sleep(0.2)
        raise AssertionError(f"the app never sent {method} {path_prefix}; sent: {[(r['method'], r['path']) for r in self.requests(since)][-12:]}")


class Live:
    """The live Bridge on this device, read only."""

    def __init__(self, url: str = "http://127.0.0.1:6050"):
        self.url = url

    def get(self, path: str, timeout: float = 5.0):
        with urllib.request.urlopen(self.url + path, timeout=timeout) as response:
            return json.load(response)

    def call(self, method: str, path: str, body=None, timeout: float = 8.0) -> tuple:
        """(status, body) of one call; an HTTP error is an answer, not an exception."""
        import urllib.error  # noqa: PLC0415

        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw.strip() else None)
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw) if raw.strip() else None
            except ValueError:
                return error.code, {"error": raw.decode("utf-8", "replace")}


class Scratch(Live):
    """A second, real Bridge (the packaged /usr/bin/meshsat) for the tier S cases: on a free
    port, with a database of its own in the run's work directory, and no device at all. Every
    device port is named and none of them exists, the serial scan is told to skip every serial
    port there is, the Reticulum listener is off: it can touch neither the live Bridge on 6050
    nor the radios. What it answers is the real API's behaviour for rules, links and the queue."""

    BINARY = os.environ.get("MESHSAT_E2E_BRIDGE", "/usr/bin/meshsat")

    def __init__(self, work: str, timeout: float = 40.0):
        import glob  # noqa: PLC0415
        import socket  # noqa: PLC0415
        import subprocess  # noqa: PLC0415

        from . import BridgeError  # noqa: PLC0415

        self.work = os.path.join(work, "bridge")
        os.makedirs(self.work, exist_ok=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        super().__init__(f"http://127.0.0.1:{self.port}")
        if not os.path.exists(self.BINARY):
            raise BridgeError(f"no Bridge binary at {self.BINARY}")
        serial = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyAMA*") + glob.glob("/dev/ttyS*"))
        env = dict(os.environ)
        env.update({
            "MESHSAT_MODE": "direct", "MESHSAT_PORT": str(self.port), "MESHSAT_DB_PATH": os.path.join(self.work, "meshsat.db"),
            "MESHSAT_MESHTASTIC_PORT": "tcp://127.0.0.1:1", "MESHSAT_IRIDIUM_PORT": "/nonexistent/e2e-iridium", "MESHSAT_IMT_PORT": "/nonexistent/e2e-imt",
            "MESHSAT_CELLULAR_PORT": "/nonexistent/e2e-cellular", "MESHSAT_ZIGBEE_PORT": "/nonexistent/e2e-zigbee", "MESHSAT_TCP_LISTEN": "none",
            "MESHSAT_SERIAL_SKIP_PORTS": ",".join(serial), "HUB_API_KEY": "", "MESHSAT_BRIDGE_NAME": "e2e-scratch",
        })
        self.log_path = os.path.join(self.work, "bridge.log")
        self.process = subprocess.Popen([self.BINARY], env=env, cwd=self.work, stdout=open(self.log_path, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise BridgeError(f"the scratch Bridge exited with {self.process.returncode}: {self.log_tail()}")
            try:
                self.get("/api/status", timeout=2)
                return
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        self.stop()
        raise BridgeError(f"the scratch Bridge never answered on {self.url}: {self.log_tail()}")

    def log_tail(self, lines: int = 12) -> str:
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as handle:
                return "\n".join(handle.read().splitlines()[-lines:])
        except OSError:
            return ""

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except Exception:  # noqa: BLE001
                self.process.kill()
