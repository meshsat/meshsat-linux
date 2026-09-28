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
