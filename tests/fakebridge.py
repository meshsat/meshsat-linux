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


def solid_png(rgb: tuple, size: int = 256) -> bytes:
    """A tile of one colour, as an OpenStreetMap tile server would send one (PNG, 8-bit RGB)."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


TILE = solid_png((242, 239, 233))  # OpenStreetMap's land colour


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
        self.settings = None  # the node's settings as GET /api/config?format=names gives them (`_settings`)
        self.gateways = None  # gateway configs by type (`_gateways`): GET and PUT /api/gateways/{type}
        self.msvqsc = False  # MSVQ-SC can encode (`_msvqsc`)
        self.radio_log = None  # the radio log lines (`_radio_log`), and whether the node offers it over Bluetooth
        self.log_available = False
        self.follows = 0
        self.zones = None  # the zones (`_zones`), as the Bridge's geofence monitor holds them; None: no monitor (503)
        self.zone_events = []  # their crossings, newest first (`_zone_events`)
        self.inside = {}  # zone id -> {node id: inside}, as GeofenceMonitor
        self.positions = None  # the position log, newest first (`_positions`)
        self.tiles_down = False  # the map's tile server (MESHSAT_APP_OSM_URL={bridge}/tiles/...) unreachable
        self.tile_requests = 0
        self.card = None  # this phone's contact card (`_card`); None: 503, no routing identity
        self.key_imports = []  # POST /api/keys/import bodies
        self.hub = None  # the Hub settings PUT /api/routing/hub wrote
        self.claim = None  # a scripted Hub's provisioning claim (`_claim`): {bid, nonce, busy, bundle}
        self.claims = 0
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
                if self.path.startswith("/tiles/") and method == "GET":
                    fake.tile(self)
                    return
                if self.path.startswith("/api/bridges/") and "/provision/" in self.path and method == "GET":
                    fake.provision_claim(self)
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
        settings = routes.pop("_settings", None)
        self.settings = json.loads(json.dumps(settings)) if settings is not None else None
        gateways = routes.pop("_gateways", None)
        self.gateways = json.loads(json.dumps(gateways)) if gateways is not None else None
        self.msvqsc = bool(routes.pop("_msvqsc", False))
        log = routes.pop("_radio_log", None)
        self.radio_log = [dict(line) for line in log] if log is not None else None
        self.log_available = bool(routes.pop("_log_available", False))
        self.follows = 0
        zones = routes.pop("_zones", None)
        self.zones = [dict(z) for z in zones] if zones is not None else None
        self.zone_events = [dict(e) for e in routes.pop("_zone_events", [])]
        self.inside = {z["id"]: {} for z in self.zones or []}
        positions = routes.pop("_positions", None)
        self.positions = [dict(p) for p in positions] if positions is not None else None
        card = routes.pop("_card", None)
        self.card = dict(card) if card else None
        claim = routes.pop("_claim", None)
        self.claim = json.loads(json.dumps(claim)) if claim else None
        self.claims = 0
        self.key_imports, self.hub = [], None
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
        # A link's transform chains on their own, as the Bridge's interfaces.go (MESHSAT-1412).
        if path.startswith("/api/interfaces/") and path.endswith("/transforms") and method == "PUT":
            return self.reduce_transforms(path.split("/")[3], body if isinstance(body, dict) else {})
        if path == "/api/transforms/capabilities" and method == "GET":
            return 200, {"msvqsc_encode": self.msvqsc, "msvqsc_decode": True, "types": ["encrypt", "decrypt", "base64", "zstd", "smaz2", "llamazip", "msvqsc", "fec"]}
        if self.gateways is not None and path.startswith("/api/gateways/") and path.count("/") == 3:
            kind = path.rsplit("/", 1)[1]
            if method == "GET":
                gw = self.gateways.get(kind)
                return (200, json.loads(json.dumps(gw))) if gw is not None else (404, {"error": f"gateway {kind} not configured"})
            if method == "PUT":
                config = (body or {}).get("config") or {}
                stored = (self.gateways.get(kind) or {}).get("config") or {}
                for k, v in list(config.items()):
                    if v == "****" and k in stored:
                        config[k] = stored[k]
                self.gateways[kind] = {"type": kind, "instance_id": kind + "_0", "enabled": bool((body or {}).get("enabled")), "config": config}
                return 200, {"status": "ok"}
        # The node's settings, as the Bridge's node_config.go (MESHSAT-1405): a write names only
        # the fields it changes and is laid over the node's own; 400 for what cannot stand, 409
        # while the node has not sent the section.
        if self.settings is not None and (path.startswith("/api/config") or path == "/api/channels" or path.startswith("/api/admin/")):
            return self.reduce_settings(method, path, body, full_path)
        if self.radio_log is not None and path == "/api/mesh/radio-log" and method == "GET":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(full_path).query)
            after = int(query.get("after", ["0"])[0] or 0)
            following = False
            if query.get("follow", [""])[0] == "1":
                self.follows += 1
                following = self.log_available
            lines = [dict(line) for line in self.radio_log if line.get("seq", 0) > after]
            security = ((self.settings or {}).get("config") or {}).get("security")
            return 200, {"count": len(lines), "last_reset_reason": "", "lines": lines, "available": self.log_available, "following": following,
                         "debug_log_api_enabled": security.get("debug_log_api_enabled") if security else None}
        # The zones, as the Bridge's geofence.go (MESHSAT-1414): 503 without a monitor, a zone
        # needs an id and three vertices, alert_on defaults to "both", a delete answers 204.
        if path.startswith("/api/geofences"):
            if self.zones is None:
                return 503, {"error": "geofence monitor not available"}
            if path == "/api/geofences" and method == "GET":
                return 200, [dict(z) for z in self.zones]
            if path == "/api/geofences/events" and method == "GET":
                return 200, {"events": [dict(e) for e in self.zone_events[:50]]}
            if path == "/api/geofences" and method == "POST":
                zone = dict(body or {})
                if not zone.get("id"):
                    return 400, {"error": "id is required"}
                if len(zone.get("polygon") or []) < 3:
                    return 400, {"error": "polygon must have at least 3 vertices"}
                zone.setdefault("alert_on", "both")
                zone["alert_on"] = zone["alert_on"] or "both"
                zone = {"id": zone["id"], "name": zone.get("name", ""), "polygon": zone["polygon"], "alert_on": zone["alert_on"], "message": zone.get("message", "")}
                self.zones.append(zone)
                self.inside[zone["id"]] = {}
                return 201, dict(zone)
            parts = path.split("/")
            if len(parts) == 4 and method == "DELETE":
                zone_id = urllib.parse.unquote(parts[3])
                for zone in self.zones:
                    if zone["id"] == zone_id:
                        self.zones.remove(zone)
                        break
                self.inside.pop(zone_id, None)
                return 204, None
        # This phone's contact card, as the Bridge signs it (MESHSAT-1416).
        if path == "/api/contacts/card" and method == "GET":
            return (200, dict(self.card)) if self.card else (503, {"error": "routing not initialized"})
        # Key bundles, as the Bridge's keyexchange.go: v1 needs signing_pub; the count of entries.
        if path == "/api/keys/import" and method == "POST":
            self.key_imports.append(body or {})
            url = (body or {}).get("url", "")
            try:
                import base64 as b64  # noqa: PLC0415

                raw = url[len("meshsat://key/"):]
                data = b64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            except ValueError:
                return 400, {"error": "invalid bundle URL"}
            if data[:1] == b"\x01" and not (body or {}).get("signing_pub"):
                return 400, {"error": "v1 bundles require signing_pub (hex)"}
            count = data[21] if len(data) > 21 else 0
            return 200, {"imported_count": count, "skipped_count": 0, "bundle_version": data[0]}
        # The Hub settings, as routing_handlers.go: an empty password or certificate keeps the
        # stored one; the CA is always written.
        if path == "/api/routing/hub" and method == "PUT":
            new = dict(body or {})
            prev = dict(self.hub or {})
            for key in ("url", "bridge_id", "username"):
                prev[key] = new.get(key, "")
            for key in ("password", "tls_cert_pem", "tls_key_pem"):
                if new.get(key):
                    prev[key] = new[key]
            prev["tls_ca_pem"] = new.get("tls_ca_pem", "")
            self.hub = prev
            return 200, {"url": prev.get("url"), "bridge_id": prev.get("bridge_id"), "warning": "Hub connection config saved. Restart the bridge for changes to take effect."}
        if self.positions is not None and path == "/api/positions" and method == "GET":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(full_path).query)
            since = query.get("since", [""])[0]
            limit = min(max(int(query.get("limit", ["100"])[0] or 100), 1), 10000)
            rows = [dict(p) for p in self.positions if not since or p.get("created_at", "").replace("T", " ").rstrip("Z") >= since]
            return 200, {"positions": rows[:limit], "node_id": query.get("node", [""])[0]}
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

    def reduce_transforms(self, link: str, body: dict):
        listed = self.routes.get("GET /api/interfaces")
        record = next((i for i in listed if i.get("id") == link), None) if isinstance(listed, list) else None
        if record is None:
            return 404, {"error": "interface not found: " + link}
        if "ingress_transforms" not in body and "egress_transforms" not in body:
            return 400, {"error": "ingress_transforms or egress_transforms is required"}
        errors = []
        for side in ("egress_transforms", "ingress_transforms"):
            if side not in body:
                continue
            try:
                chain = json.loads(body[side] or "[]")
            except ValueError:
                errors.append(f"{side[:-11]}: invalid transforms JSON")
                continue
            binary = False
            for step in chain:
                kind, params = step.get("type"), step.get("params") or {}
                if kind in ("encrypt", "decrypt"):
                    key = params.get("key", "")
                    if not key and not params.get("key_ref"):
                        errors.append(f"{side[:-11]}: {kind} transform requires 'key' or 'key_ref' param")
                    elif key and (len(key) not in (32, 48, 64) or any(c not in "0123456789abcdefABCDEF" for c in key)):
                        errors.append(f"{side[:-11]}: {kind} key must be 64 hex characters (AES-256; 32 or 48 for AES-128 or -192)")
                    binary = True
                elif kind in ("msvqsc", "smaz2", "zstd", "llamazip", "fec"):
                    binary = True
                elif kind == "base64":
                    binary = False
                else:
                    errors.append(f"{side[:-11]}: unknown transform type {kind!r}")
            if binary and record.get("channel_type") in ("cellular", "mqtt", "webhook"):
                errors.append(f"{side[:-11]}: text-only transport (SMS/MQTT/webhook) requires base64 as the final transform after encrypt/compress")
        if errors:
            return 400, {"error": "transform validation failed", "errors": errors, "warnings": None}
        for side in ("egress_transforms", "ingress_transforms"):
            if side in body:
                record[side] = body[side]
        return 200, dict(record)

    def reduce_settings(self, method: str, path: str, body, full_path: str):
        settings = self.settings
        body = body if isinstance(body, dict) else {}
        if path == "/api/config" and method == "GET":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(full_path).query)
            if query.get("format", [""])[0] == "names":
                return 200, json.loads(json.dumps(settings))
            return None
        if path.startswith("/api/config/") and method == "GET":
            return 200, {"status": "config request sent for section: " + path.rsplit("/", 1)[1]}
        if path in ("/api/config/radio", "/api/config/module") and method == "POST":
            kind = "config" if path.endswith("radio") else "module"
            section = body.get("section", "")
            config = body.get("config")
            if not section:
                return 400, {"error": "section is required"}
            if not isinstance(config, dict) or not config:
                return 400, {"error": f"config must be a JSON object of the {section} settings"}
            current = (settings.get(kind) or {}).get(section)
            if current is None:
                return 409, {"error": f"the node has not sent these settings yet: {section}"}
            for key, value in config.items():
                if key not in current:
                    return 400, {"error": f'unknown {section} setting "{key}"'}
                if value is None:
                    return 400, {"error": f'{section} setting "{key}" needs a value'}
            if section == "security":
                if {"private_key", "public_key"} & set(config):
                    return 400, {"error": "the node's keys are not changed through the settings; only its other security settings are"}
                if not current.get("private_key_set"):
                    return 409, {"error": "the node has not sent these settings yet: the node has not sent its private key"}
            current.update(config)
            return 200, {"status": ("radio" if kind == "config" else "module") + " config updated"}
        if path == "/api/channels" and method == "POST":
            index = int(body.get("index", 0))
            if index > 7:
                return 400, {"error": f"there is no channel {index}: channels are 0 to 7"}
            channel = next((c for c in settings.get("channels") or [] if int(c.get("index", 0)) == index), None)
            if channel is None:
                return 409, {"error": f"the node has not sent these settings yet: channel {index}"}
            roles = {"PRIMARY": 1, "SECONDARY": 2, "DISABLED": 0}
            role = roles.get(body.get("role") or "", channel.get("role", 0)) if body.get("role") in roles or not body.get("role") else None
            if role is None:
                return 400, {"error": "unknown channel role: " + str(body.get("role"))}
            if (index == 0) != (role == 1):
                return 400, {"error": "channel 0 is always the main channel" if index == 0 else "only channel 0 is the main channel"}
            channel.update(role=role, name=body.get("name", ""), uplink_enabled=bool(body.get("uplink_enabled")), downlink_enabled=bool(body.get("downlink_enabled")))
            if body.get("psk"):
                channel["key"] = "private" if len(body["psk"]) > 4 else "default"
            return 200, {"status": "channel updated"}
        if path == "/api/config/owner" and method == "POST":
            owner = settings.get("owner")
            if not owner:
                return 409, {"error": "the node has not sent these settings yet: the node's own name"}
            if not body.get("long_name") and not body.get("short_name"):
                return 400, {"error": "at least one of long_name or short_name is required"}
            owner.update({k: body[k] for k in ("long_name", "short_name") if body.get(k)})
            return 200, {"status": "owner updated"}
        if path.startswith("/api/admin/") and method == "POST":
            order = path.rsplit("/", 1)[1]
            if order in ("reboot", "factory_reset", "set_clock", "shutdown", "nodedb_reset"):
                return 200, {"status": order + " sent"}
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
            if order == "log":
                # Lines the node "sent" since: appended to the radio log with the next numbers.
                if self.radio_log is None:
                    self.radio_log = []
                for line in body.get("lines", []):
                    line = dict(line)
                    line["seq"] = max([l.get("seq", 0) for l in self.radio_log] + [0]) + 1
                    self.radio_log.append(line)
                return 200, {"lines": len(self.radio_log)}
            if order == "position":
                # A node reports a position: logged, the node moved, the zones checked, as the
                # Bridge's processor does with every mesh position.
                node_id, lat, lon = body["node_id"], float(body["lat"]), float(body["lon"])
                stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if self.positions is not None:
                    self.positions.insert(0, {"id": len(self.positions) + 1, "node_id": node_id, "latitude": lat, "longitude": lon, "altitude": 0, "created_at": stamp})
                listed = (self.routes.get("GET /api/nodes") or {}).get("nodes") or []
                for n in listed:
                    if n.get("user_id") == node_id:
                        n.update(latitude=lat, longitude=lon, last_heard=int(time.time()))
                crossings = self.check_zones(node_id, lat, lon)
                return 200, {"crossings": crossings}
            if order == "tiles":
                self.tiles_down = bool(body.get("down", False))
                return 200, {"down": self.tiles_down, "requests": self.tile_requests}
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
                             "credentials": self.credentials, "audit_count": len(self.audit) if self.audit is not None else None, "settings": self.settings,
                             "follows": self.follows, "gateways": self.gateways, "zones": self.zones, "zone_events": self.zone_events,
                             "tiles_down": self.tiles_down, "tile_requests": self.tile_requests,
                             "key_imports": self.key_imports, "hub": self.hub, "claims": self.claims,
                             "interfaces": self.routes.get("GET /api/interfaces")}
        if order == "event":
            self.push(body)
            return 200, {"listeners": len(self.listeners)}
        return 404, {"error": f"no such order: {order}"}

    def tile(self, handler) -> None:
        """A map tile, never logged with the API calls; with the tiles "down" the connection ends
        unanswered, as with no network."""
        with self.lock:
            self.tile_requests += 1
            down = self.tiles_down or self.down
        if down:
            handler.close_connection = True
            return
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "image/png")
            handler.send_header("Content-Length", str(len(TILE)))
            handler.end_headers()
            handler.wfile.write(TILE)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def provision_claim(self, handler) -> None:
        """The Hub's claim (bridge_provision.go): 404 for a wrong bridge or nonce; 503 with
        Retry-After while "busy"; the settings once; then 404, the stash spent."""
        with self.lock:
            self.claims += 1
            claim = self.claim
            parts = handler.path.split("?", 1)[0].split("/")
            status, body, headers = 404, {"error": "invalid or expired provisioning token"}, {}
            if claim and len(parts) == 6 and parts[3] == claim.get("bid") and parts[5] == claim.get("nonce"):
                if claim.get("status"):
                    status, body = claim["status"], {"error": "scripted"}
                elif claim.get("busy", 0) > 0:
                    claim["busy"] -= 1
                    status, body, headers = 503, {"error": "not ready"}, {"Retry-After": str(claim.get("retry_after", 1))}
                elif claim.get("bundle") is not None:
                    status, body = 200, claim.pop("bundle")
        data = json.dumps(body).encode()
        try:
            handler.send_response(status)
            handler.send_header("Content-Type", "application/json")
            for key, value in headers.items():
                handler.send_header(key, value)
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def check_zones(self, node_id: str, lat: float, lon: float) -> list:
        """GeofenceMonitor.CheckPosition: ray casting on degrees, no hysteresis; entering is
        remembered even by a zone that alerts only on leaving."""
        out = []
        for zone in self.zones or []:
            poly = zone.get("polygon") or []
            inside, j = False, len(poly) - 1
            for i in range(len(poly)):
                yi, xi, yj, xj = poly[i]["lat"], poly[i]["lon"], poly[j]["lat"], poly[j]["lon"]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
            if len(poly) < 3:
                inside = False
            state = self.inside.setdefault(zone["id"], {})
            was = state.get(node_id, False)
            event = None
            if inside and not was:
                event = "enter" if zone.get("alert_on") in ("enter", "both") else None
                state[node_id] = True
            elif not inside and was:
                event = "exit" if zone.get("alert_on") in ("exit", "both") else None
                state[node_id] = False
            if event:
                record = {"zone_name": zone.get("name", ""), "node_id": node_id, "event": event, "timestamp": int(time.time() * 1000)}
                self.zone_events.insert(0, record)
                out.append(record)
        return out

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
