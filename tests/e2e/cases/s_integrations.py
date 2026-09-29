# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > "Ham radio, TAK and Reticulum" against a real, scratch Bridge (MESHSAT-1421), with every
far end a small server this case runs on 127.0.0.1: a KISS TNC, an APRS-IS server, a Reticulum
node. Nothing reaches a radio, a real APRS-IS server, the network around the phone or the Hub:
KISS always goes through an external Direwolf that is not there, the status beacon is off, TAK
multicast stays off, the only callsign is N0CALL."""
import socket
import threading
import time

SCENARIO = None  # the scratch Bridge


class Server:
    """A TCP server on 127.0.0.1 with one handler thread per connection; `received` keeps bytes."""

    def __init__(self, handler=None):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.received = bytearray()
        self.connections = []
        self.lines = []
        self.handler = handler
        self.stop = False
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self) -> None:
        self.sock.settimeout(0.5)
        while not self.stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.connections.append(conn)
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn) -> None:
        conn.settimeout(0.5)
        if self.handler:
            self.handler(self, conn)
            return
        while not self.stop:
            try:
                data = conn.recv(4096)
            except OSError:
                continue
            if not data:
                return
            self.received.extend(data)

    def close(self) -> None:
        self.stop = True
        for conn in self.connections:
            try:
                conn.close()
            except OSError:
                pass
        self.sock.close()


def address(call: str, ssid: int, last: bool) -> bytes:
    call = call.ljust(6)[:6]
    return bytes(ord(ch) << 1 for ch in call) + bytes([0x60 | (ssid << 1) | (1 if last else 0)])


def kiss_ui(src: str, src_ssid: int, dst: str, info: str) -> bytes:
    frame = address(dst, 0, False) + address(src, src_ssid, True) + b"\x03\xf0" + info.encode()
    frame = frame.replace(b"\xdb", b"\xdb\xdd").replace(b"\xc0", b"\xdb\xdc")
    return b"\xc0\x00" + frame + b"\xc0"


def wait_for(check, what: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    while True:
        got = check()
        if got:
            return got
        if time.time() > deadline:
            raise AssertionError(what)
        time.sleep(0.5)


def aprs_status(ctx) -> dict:
    return ctx.bridge.get("/api/aprs/status") or {}


def case_a_aprs_kiss_to_a_loopback_tnc(ctx):
    tnc = Server()
    try:
        status, body = ctx.bridge.call("PUT", "/api/gateways/aprs", {"enabled": True, "config": {
            "callsign": "N0CALL", "ssid": 10, "mode": "kiss", "kiss_host": "127.0.0.1", "kiss_port": tnc.port,
            "external_direwolf": True, "beacon_secs": 0, "position_beacon": False}}, timeout=45)
        assert status == 200, (status, body)
        st = wait_for(lambda: (lambda s: s if s.get("connected") else None)(aprs_status(ctx)), "the Bridge never reached the loopback TNC")
        assert st.get("state") == "connected" and st.get("mode") in ("kiss", None), st
        for conn in tnc.connections:
            conn.sendall(kiss_ui("PA3ABC", 5, "APMSHT", ":N0CALL-10:e2e hello{1"))
        wait_for(lambda: any("PA3ABC" in (h.get("callsign") or h.get("source") or "") for h in (ctx.bridge.get("/api/aprs/heard") or [])),
                 "the Bridge never heard the loopback TNC's station")
        ctx.app.open("setup/integrations")
        ctx.tree.wait_text("KISS TNC", timeout=15)
        ctx.tree.wait_text("Connected", timeout=15)
        ctx.shot("integrations-kiss-connected")
        time.sleep(2)
        assert not tnc.received, f"the Bridge sent {len(tnc.received)} bytes to the TNC (it would have gone over the radio)"
        # A PUT without `enabled` switches the gateway off, as the Bridge's contract says
        status, _ = ctx.bridge.call("PUT", "/api/gateways/aprs", {"config": {"callsign": "N0CALL", "ssid": 10, "kiss_host": "127.0.0.1", "kiss_port": tnc.port,
                                                                           "external_direwolf": True, "beacon_secs": 0}}, timeout=20)
        assert status == 200
        assert ctx.bridge.get("/api/gateways/aprs").get("enabled") is False
    finally:
        tnc.close()


def aprs_is_server(logins: list, reply: str):
    def handler(server, conn) -> None:
        conn.sendall(b"# aprsc 2.1.14-gc04b4ac 29 Sep 2026 08:00:00 GMT T2TEST 127.0.0.1:14580\r\n")
        buf = b""
        while not server.stop:
            try:
                data = conn.recv(4096)
            except OSError:
                continue
            if not data:
                return
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", "replace").strip()
                server.lines.append(text)
                if text.startswith("user "):
                    logins.append(text)
                    call = text.split()[1]
                    conn.sendall(f"# logresp {call} {reply}, server T2TEST\r\n".encode())
    return handler


def case_b_aprs_is_to_a_loopback_server(ctx):
    logins = []
    fake = Server(aprs_is_server(logins, "unverified"))
    try:
        status, body = ctx.bridge.call("PUT", "/api/gateways/aprs", {"enabled": True, "config": {
            "callsign": "N0CALL", "ssid": 10, "mode": "is", "aprs_is_server": f"127.0.0.1:{fake.port}", "aprs_is_passcode": "-1",
            "aprs_is_filter_km": 100, "aprs_is_filter_lat": 52.3676, "aprs_is_filter_lon": 4.9041, "position_beacon": False, "beacon_secs": 0}}, timeout=45)
        assert status == 200, (status, body)
        wait_for(lambda: logins, "the Bridge never logged in to the loopback APRS-IS server")
        assert logins[0] == "user N0CALL-10 pass -1 vers MeshSat 1.0 filter r/52.4/4.9/100", logins
        st = wait_for(lambda: (lambda s: s if s.get("state") == "connected" else None)(aprs_status(ctx)), "never connected")
        assert st.get("aprs_is_verified") is False, st
        ctx.app.open("setup/integrations")
        ctx.tree.wait_text("APRS-IS", timeout=15)
        ctx.tree.wait_text("Connected", timeout=15)
        assert not ctx.tree.has_text("APRS-IS (verified)")
        ctx.shot("integrations-is-unverified")
    finally:
        fake.close()
    logins = []
    fake = Server(aprs_is_server(logins, "verified"))
    try:
        status, _ = ctx.bridge.call("PUT", "/api/gateways/aprs", {"enabled": True, "config": {
            "callsign": "N0CALL", "ssid": 10, "mode": "is", "aprs_is_server": f"127.0.0.1:{fake.port}", "aprs_is_passcode": "13023",
            "aprs_is_filter_km": 100, "position_beacon": False, "beacon_secs": 0}}, timeout=45)
        assert status == 200
        wait_for(lambda: logins and " pass 13023 " in logins[0], "the verified login never came")
        wait_for(lambda: aprs_status(ctx).get("aprs_is_verified") is True, "never verified")
        assert ctx.bridge.get("/api/gateways/aprs")["config"]["aprs_is_passcode"] == "****"
        ctx.app.refresh()
        ctx.tree.wait_text("APRS-IS (verified)", timeout=15)
    finally:
        fake.close()
        ctx.bridge.call("PUT", "/api/gateways/aprs", {"enabled": False, "config": {"callsign": "N0CALL", "ssid": 10, "mode": "kiss", "external_direwolf": True,
                                                                                 "beacon_secs": 0}}, timeout=20)


def case_c_tak_without_a_server(ctx):
    status, body = ctx.bridge.call("PUT", "/api/gateways/tak", {"enabled": True, "config": {"callsign_prefix": "E2E", "multicast": False, "hub_export": True}}, timeout=20)
    assert status == 200, (status, body)
    got = ctx.bridge.get("/api/gateways/tak")
    assert got["enabled"] is True and got["config"]["callsign_prefix"] == "E2E" and got["config"]["multicast"] is False, got
    ctx.app.open("setup/integrations")
    ctx.tree.wait_switch("Enable TAK", True, timeout=15)
    assert not ctx.tree.switch("ATAK Broadcast").checked and ctx.tree.switch("MQTT Export to Hub").checked
    status, _ = ctx.bridge.call("PUT", "/api/gateways/tak", {"enabled": False, "config": got["config"]}, timeout=20)
    assert status == 200


def case_d_reticulum_tcp_to_a_loopback_node(ctx):
    node = Server()
    try:
        status, row = ctx.bridge.call("POST", "/api/routing/ifaces", {"type": "tcp_rns", "enabled": True, "config": {"host": "127.0.0.1", "port": node.port, "tls": False}})
        assert status == 201 and row.get("id") == "tcp_rns_0", (status, row)
        wait_for(lambda: (ctx.bridge.get("/api/routing/ifaces/tcp_rns_0") or {}).get("online"), "tcp_rns_0 never came online", 20)
        ctx.app.open("setup/integrations")
        ctx.tree.wait_text("RNS TCP", timeout=15)
        ctx.tree.wait_switch("Enable RNS TCP", True, timeout=15)
        status, _ = ctx.bridge.call("PUT", "/api/routing/ifaces/tcp_rns_0", {"enabled": False})
        assert status == 200
        off = ctx.bridge.get("/api/routing/ifaces/tcp_rns_0")
        assert off["enabled"] is False and off["config"]["host"] == "127.0.0.1", off
    finally:
        node.close()
        ctx.bridge.call("DELETE", "/api/routing/ifaces/tcp_rns_0")
