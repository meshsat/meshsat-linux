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
import re
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
        self.deliveries = None  # the queue, when the scenario has one (`_deliveries`): cancel and retry change it as the Bridge does
        self.rules = None  # the routing rules, when the scenario has them (`_rules`): create, replace, delete, switch
        self.audit = None  # the audit log, newest last (`_audit`); `_audit_broken_at` makes the check fail there
        self.audit_broken_at = -1
        self.credentials = None  # the credential store (`_credentials`): upload, delete
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
        deliveries = routes.pop("_deliveries", None)
        self.deliveries = [dict(d) for d in deliveries] if deliveries is not None else None
        rules = routes.pop("_rules", None)
        self.rules = [dict(r) for r in rules] if rules is not None else None
        audit = routes.pop("_audit", None)
        self.audit = [dict(e) for e in audit] if audit is not None else None
        self.audit_broken_at = int(routes.pop("_audit_broken_at", -1))
        creds = routes.pop("_credentials", None)
        self.credentials = [dict(c) for c in creds] if creds is not None else None
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
        reduced = self.reduce(method, bare, body, path)
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

    def reduce(self, method: str, path: str, body, full_path: str = ""):
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
            # A direct send on the mesh while every mesh link is switched off: refused, as the Bridge since MESHSAT-1401.
            listed = self.routes.get("GET /api/interfaces")
            meshes = [i for i in listed if str(i.get("id", "")).startswith("mesh")] if isinstance(listed, list) else []
            if not (body or {}).get("gateway") and meshes and not any(i.get("enabled") for i in meshes):
                return 409, {"error": "Not sent: Mesh is switched off. Switch it on in Links."}
            self.sent.append(body or {})
            feed = self.routes.setdefault("GET /api/packets?limit=200", {"packets": []})
            if isinstance(feed, dict):
                feed.setdefault("packets", []).insert(0, {"dir": "tx", "portnum_name": "TEXT_MESSAGE_APP", "text": (body or {}).get("text", ""), "to": (body or {}).get("to") or "broadcast",
                                                         "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "bearer": "mesh"})
            return 200, {"status": "sent", "id": len(self.sent)}
        if path == "/api/nodes/request-info" and method == "POST":
            return 200, {"status": "nodeinfo request sent"}
        # The queue, as the Bridge's deliveries.go: cancel only what is queued or waiting for a
        # retry, retry only what failed or gave up; anything else is a 500 with the Bridge's words.
        if self.deliveries is not None and path.startswith("/api/deliveries"):
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            if path == "/api/deliveries" and method == "GET":
                # Newest first, as the Bridge's ORDER BY created_at DESC.
                return 200, [dict(d) for d in sorted(self.deliveries, key=lambda d: d.get("created_at", ""), reverse=True)]
            parts = path.split("/")
            if len(parts) == 5 and method == "POST" and parts[4] in ("cancel", "retry"):
                row = next((d for d in self.deliveries if str(d.get("id")) == parts[3]), None)
                if row is None:
                    return 500, {"error": f"failed to {parts[4]} delivery"}
                if parts[4] == "cancel":
                    if row.get("status") not in ("queued", "retry"):
                        return 500, {"error": "failed to cancel delivery"}
                    row.update(status="dead", last_error="cancelled", updated_at=stamp)
                    return 200, {"status": "cancelled"}
                if row.get("status") not in ("failed", "dead"):
                    return 500, {"error": "failed to retry delivery"}
                row.update(status="queued", next_retry=None, updated_at=stamp)
                return 200, {"status": "requeued"}
        # The routing rules, as the Bridge's interfaces.go: a POST answers 201 with the record
        # (qos_level 1 when absent), a PUT replaces every column, a DELETE answers 204.
        if self.rules is not None and path.startswith("/api/access-rules"):
            stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            parts = path.split("/")
            if path == "/api/access-rules" and method == "GET":
                return 200, [dict(r) for r in self.rules]
            if path == "/api/access-rules" and method == "POST":
                record = dict(body or {})
                for key, missing in (("interface_id", None), ("direction", None), ("action", None)):
                    if not record.get(key):
                        return 400, {"error": f"{key} is required"}
                if "qos_level" not in record:
                    record["qos_level"] = 1
                record.setdefault("match_count", 0)
                record["id"] = max([r.get("id", 0) for r in self.rules] + [0]) + 1
                record["created_at"] = record["updated_at"] = stamp
                self.rules.append(record)
                return 201, dict(record)
            if len(parts) == 4 and parts[3].isdigit():
                row = next((r for r in self.rules if str(r.get("id")) == parts[3]), None)
                if method == "PUT":
                    if row is None:
                        return 500, {"error": "rule not found"}
                    kept = {"id": row["id"], "match_count": row.get("match_count", 0), "created_at": row.get("created_at", stamp)}
                    row.clear()
                    row.update(body or {})
                    row.update(kept)
                    row["updated_at"] = stamp
                    return 200, dict(row)
                if method == "DELETE":
                    if row is not None:
                        self.rules.remove(row)
                    return 204, None
            if len(parts) == 5 and method == "POST" and parts[4] in ("enable", "disable"):
                row = next((r for r in self.rules if str(r.get("id")) == parts[3]), None)
                if row is None:
                    return 500, {"error": "rule not found"}
                row["enabled"] = parts[4] == "enable"
                row["updated_at"] = stamp
                return 200, {"status": f"{parts[4]}d"}
        # The audit log, as the Bridge's audit.go: newest first, at most 1000, by link, before an id.
        if self.audit is not None and path.startswith("/api/audit") and method == "GET":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(full_path).query)
            if path == "/api/audit/count":
                return 200, {"count": len(self.audit)}
            if path == "/api/audit/verify":
                limit = min(int(query.get("limit", ["1000"])[0]), 10000)
                checked = min(limit, len(self.audit))
                broken = self.audit_broken_at
                return 200, {"verified": broken == -1, "valid": broken if broken >= 0 else checked, "checked": limit, "broken_at": broken}
            if path == "/api/audit":
                limit = min(max(int(query.get("limit", ["100"])[0]), 1), 1000)
                before = int(query.get("before", ["0"])[0] or 0)
                link = query.get("interface_id", [""])[0]
                rows = [e for e in reversed(self.audit) if (not before or e["id"] < before) and (not link or e.get("interface_id") == link)]
                return 200, rows[:limit]
        # The credential store, as the Bridge's credentials_local.go.
        if self.credentials is not None and path.startswith("/api/credentials"):
            parts = path.split("/")
            if path == "/api/credentials" and method == "GET":
                return 200, {"credentials": [dict(c) for c in self.credentials]}
            if path == "/api/credentials/upload" and method == "POST":
                raw = (body or {}).get("_raw", "") if isinstance(body, dict) else ""
                fields = dict(re.findall(r'name="(provider|name)"\r\n\r\n([^\r]*)\r\n', raw))
                if not fields.get("provider"):
                    return 400, {"error": "provider is required"}
                if "BEGIN CERTIFICATE" not in raw and "PRIVATE KEY" not in raw:
                    return 400, {"error": "no certificates or keys found in uploaded files"}
                cred = {"id": f"cred-{len(self.credentials) + 1}", "provider": fields["provider"], "name": fields.get("name") or fields["provider"], "cred_type": "x509_cert",
                        "cert_not_after": "2030-01-01T00:00:00Z", "cert_subject": "CN=e2e.meshsat.net", "cert_fingerprint": "ab" * 32, "version": 1, "source": "local", "applied": 0}
                self.credentials.append(cred)
                return 201, {"id": cred["id"], "provider": cred["provider"], "name": cred["name"], "cred_type": "x509_cert", "files_found": 1}
            if len(parts) == 4 and method == "DELETE":
                before = len(self.credentials)
                self.credentials = [c for c in self.credentials if c["id"] != parts[3]]
                return (200, {"status": "deleted"}) if len(self.credentials) < before else (404, {"error": "credential not found"})
        # A link switched on or off changes the interface list the scenario serves; a bind is taken.
        if path.startswith("/api/interfaces/") and method == "POST":
            parts = path.split("/")
            if len(parts) == 5 and parts[4] in ("enable", "disable"):
                listed = self.routes.get("GET /api/interfaces")
                if isinstance(listed, list):
                    for iface in listed:
                        if iface.get("id") == parts[3]:
                            iface["enabled"] = parts[4] == "enable"
                return 200, {"status": f"{parts[4]}d"}
            if len(parts) == 5 and parts[4] == "bind":
                if not (body or {}).get("device_id"):
                    return 400, {"error": "device_id is required"}
                return 200, {"status": "bound"}
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
                return 200, {"sos": self.sos, "deadman": self.deadman, "down": self.down, "delay": self.delay, "deliveries": self.deliveries, "rules": self.rules,
                             "credentials": self.credentials, "audit_count": len(self.audit) if self.audit is not None else None}
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
