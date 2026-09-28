# SPDX-License-Identifier: GPL-3.0-or-later
"""A scripted MeshSat Bridge for the tests: answers the Bridge's API from a scenario (a map of
"METHOD /path" to a body), records every request the app makes, serves /api/events as the
Bridge does, and takes orders on /__fake__/ (switch scenario, set one answer, push an event,
delay, go down). A path the scenario does not know answers 404 and is counted as unexpected:
the app must never lean on an API the scenario did not give it. Standard library only, so it
runs on the phone and in the unit tests alike."""
import json
import os
import queue
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_scenario(name: str) -> dict:
    """A scenario by name: `tests/fixtures/scenarios.py` builds it from the recorded answers."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("scenarios", os.path.join(FIXTURES, "scenarios.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(name)


class FakeBridge:
    def __init__(self, scenario: dict | None = None, port: int = 0):
        self.routes = {}
        self.requests = []
        self.unexpected = []
        self.delay = 0.0
        self.down = False
        self.lock = threading.Lock()
        self.listeners = []  # queues of event dicts, one per open /api/events
        self.sos = {"active": False, "started_at": "", "sends": 0, "test": False}
        self.deadman = {"enabled": False, "timeout_min": 240, "last_activity": "", "triggered": False}
        self.sent = []  # POST /api/messages/send bodies, also appended to the packet feed
        self.apply(scenario or {})
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    return json.loads(raw) if raw.strip() else None
                except ValueError:
                    return {"_raw": raw.decode("utf-8", "replace")}

            def _send(self, status: int, body) -> None:
                data = json.dumps(body).encode() if body is not None else b""
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    if data:
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the app gave up waiting (its own timeout): not the fake's concern

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_PUT(self):
                self._handle("PUT")

            def do_DELETE(self):
                self._handle("DELETE")

            def _handle(self, method: str) -> None:
                body = self._body() if method != "GET" else None
                if self.path.startswith("/__fake__/"):
                    status, answer = fake.control(method, self.path, body)
                    self._send(status, answer)
                    return
                if self.path == "/api/events" and method == "GET":
                    fake.stream(self)
                    return
                try:
                    status, answer = fake.answer(method, self.path, body)
                except ConnectionError:
                    self.close_connection = True
                    return
                self._send(status, answer)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def apply(self, scenario: dict) -> None:
        """A scenario's routes, and its state under the underscore keys: `_down` (no Bridge at
        all), `_sos` (an SOS in progress), `_deadman`."""
        routes = dict(scenario)
        self.down = bool(routes.pop("_down", False))
        sos = routes.pop("_sos", None)
        self.sos = dict(sos) if sos else {"active": False, "started_at": "", "sends": 0, "test": False}
        deadman = routes.pop("_deadman", None)
        self.deadman = dict(deadman) if deadman else {"enabled": False, "timeout_min": 240, "last_activity": "", "triggered": False}
        self.routes = routes

    # Life
    def start(self) -> "FakeBridge":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # The API
    def answer(self, method: str, path: str, body) -> tuple:
        with self.lock:
            self.requests.append({"t": time.time(), "method": method, "path": path, "body": body})
            delay, down = self.delay, self.down
        if delay:
            time.sleep(delay)
        if down:
            # A closed connection, as a Bridge that is not running: the client sees no answer.
            raise ConnectionError("down")
        bare = path.split("?", 1)[0]
        # An answer the test set by hand (a failure, say) comes before the built-in reducers.
        for key in (f"{method} {path}", f"{method} {bare}"):
            entry = self.routes.get(key)
            if isinstance(entry, dict) and "_status" in entry:
                return entry["_status"], entry.get("_body")
        reduced = self.reduce(method, bare, body)
        if reduced is not None:
            return reduced
        for key in (f"{method} {path}", f"{method} {bare}"):
            if key in self.routes:
                entry = self.routes[key]
                if callable(entry):
                    return entry(method, path, body)
                return 200, entry
        with self.lock:
            self.unexpected.append({"method": method, "path": path})
        return 404, {"error": f"the scenario has no answer for {method} {bare}"}

    def reduce(self, method: str, path: str, body):
        """The few calls whose answer depends on what the app did before."""
        if path == "/api/sos/status" and method == "GET":
            return 200, dict(self.sos)
        if path == "/api/sos/activate" and method == "POST":
            if self.sos["active"]:
                return 409, {"status": "already_active"}
            self.sos.update(active=True, started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), sends=1, trigger=(body or {}).get("trigger", "manual"), message=(body or {}).get("message", ""))
            return 200, {"status": "activated", "started_at": self.sos["started_at"]}
        if path == "/api/sos/cancel" and method == "POST":
            self.sos.update(active=False, sends=0)
            return 200, {"status": "cancelled"}
        if path == "/api/deadman":
            if method == "POST":
                # As the Bridge's handler: the settings, and a touch that resets the timer and its trigger.
                self.deadman.update(enabled=bool((body or {}).get("enabled")), timeout_min=int((body or {}).get("timeout_min") or 240),
                                    last_activity=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), triggered=False)
            return 200, dict(self.deadman)
        if path == "/api/messages/send" and method == "POST":
            self.sent.append(body or {})
            feed = self.routes.setdefault("GET /api/packets?limit=200", {"packets": []})
            if isinstance(feed, dict):
                feed.setdefault("packets", []).insert(0, {"dir": "tx", "portnum_name": "TEXT_MESSAGE_APP", "text": (body or {}).get("text", ""), "to": (body or {}).get("to") or "broadcast",
                                                         "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "bearer": "mesh"})
            return 200, {"status": "sent", "id": len(self.sent)}
        if path == "/api/nodes/request-info" and method == "POST":
            return 200, {"status": "nodeinfo request sent"}
        return None

    # Orders from the test
    def control(self, method: str, path: str, body) -> tuple:
        order = path[len("/__fake__/"):].split("?", 1)[0]
        body = body or {}
        with self.lock:
            if order == "scenario":
                if "name" in body:
                    self.apply(load_scenario(body["name"]))
                if "routes" in body:
                    self.routes.update(body["routes"])
                if body.get("reset_log"):
                    self.requests, self.unexpected = [], []
                return 200, {"routes": len(self.routes)}
            if order == "set":
                self.routes[body["key"]] = body["body"] if "status" not in body else {"_status": body["status"], "_body": body.get("body")}
                return 200, {"ok": True}
            if order == "requests":
                since = int(urllib.parse.parse_qs(urllib.parse.urlparse(path).query).get("since", ["0"])[0])
                return 200, {"requests": self.requests[since:], "total": len(self.requests), "unexpected": self.unexpected, "sent": self.sent}
            if order == "delay":
                self.delay = float(body.get("seconds", 0))
                return 200, {"delay": self.delay}
            if order == "down":
                self.down = bool(body.get("down", True))
                return 200, {"down": self.down}
            if order == "reset":
                self.requests, self.unexpected, self.sent = [], [], []
                self.delay, self.down = 0.0, False
                self.sos = {"active": False, "started_at": "", "sends": 0, "test": False}
                self.deadman = {"enabled": False, "timeout_min": 240, "last_activity": "", "triggered": False}
                return 200, {"ok": True}
            if order == "state":
                return 200, {"sos": self.sos, "deadman": self.deadman, "down": self.down, "delay": self.delay}
        if order == "event":
            self.push(body)
            return 200, {"listeners": len(self.listeners)}
        return 404, {"error": f"no such order: {order}"}

    # The event stream
    def push(self, event: dict) -> None:
        with self.lock:
            listeners = list(self.listeners)
        for q in listeners:
            q.put(event)

    def stream(self, handler) -> None:
        q = queue.Queue()
        with self.lock:
            self.listeners.append(q)
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.end_headers()
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    handler.wfile.write(b": keepalive\n\n")
                    handler.wfile.flush()
                    continue
                handler.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with self.lock:
                if q in self.listeners:
                    self.listeners.remove(q)


def main() -> int:
    """`python3 fakebridge.py [scenario] [port]`: serve until killed, the URL on stdout."""
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "mesh-only"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    fake = FakeBridge(load_scenario(name), port).start()
    print(fake.url, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        fake.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
