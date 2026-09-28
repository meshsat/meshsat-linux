# SPDX-License-Identifier: GPL-3.0-or-later
"""The states the scripted Bridge plays for the tests, each a map of "METHOD /path" to the
answer. They start from the Bridge's own answers recorded on the bench phone
(tests/fixtures/recorded/<date>-<sha>/, tools/record-fixtures.sh) and change what the state
is about; what no recording holds is written here in the Bridge's shapes."""
import copy
import glob
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ME = "!52cb81e7"
OTHER = "!a1b3c2ec"
THIRD = "!b1b3c2ed"
NOW = int(time.time())


def recorded() -> dict:
    """The latest recording, as {"GET /api/path": body}."""
    folders = sorted(glob.glob(os.path.join(HERE, "recorded", "*")))
    if not folders:
        return {}
    out = {}
    for path in glob.glob(os.path.join(folders[-1], "*.json")):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as handle:
            try:
                body = json.load(handle)
            except ValueError:
                continue
        # the file name is the call with / ? = & turned into _ (record-fixtures.sh)
        out[name] = body
    return out


REC = recorded()


def rec(name: str, default):
    return copy.deepcopy(REC.get(name, default))


def node(user_id: str, long_name: str, short_name: str, last_heard: int, **more) -> dict:
    num = int(user_id[1:], 16)
    out = {"user_id": user_id, "num": num, "long_name": long_name, "short_name": short_name, "hw_model": 43, "hw_model_name": "T_DECK", "last_heard": last_heard,
           "snr": 8.5, "rssi": -60, "battery_level": 78, "latitude": 0, "longitude": 0}
    out.update(more)
    return out


def text_message(id_: int, sender: str, to: str, text: str, when: int, direction: str = "rx", transport: str = "radio", snr: float = 7.25) -> dict:
    return {"id": id_, "from_node": sender, "to_node": to, "portnum": 1, "portnum_name": "TEXT_MESSAGE_APP", "decoded_text": text, "rx_time": when,
            "rx_snr": snr, "rx_rssi": -70, "direction": direction, "transport": transport, "delivery_status": "sent" if direction == "tx" else ""}


def status(connected: bool = True, **more) -> dict:
    out = rec("status", {"address": "tcp://127.0.0.1:4403", "connected": True, "node_id": ME, "node_name": "meshsat-pinephone-pro", "num_nodes": 2, "firmware_version": "2.7.3.dev",
                         "hw_model_name": "PORTDUINO", "reboot_count": 0, "radio_last_reset_reason": "", "transport": "tcp", "directory": {"hub_version": 0, "last_sync_at": ""}})
    out["connected"] = connected
    out.update(more)
    return out


def base() -> dict:
    """The bench phone in cover mode: the node up, one other node heard and named, a few
    texts, no modem, no SIM, no Hub."""
    me = node(ME, "meshsat-pinephone-pro", "MSPP", NOW - 5, hw_model=255, hw_model_name="PORTDUINO", battery_level=101, rssi=0, snr=0)
    other = node(OTHER, "MSPA", "MSPA", NOW - 120, latitude=52.3731, longitude=4.8932)
    messages = [text_message(3, OTHER, "!ffffffff", "mew", NOW - 300), text_message(2, ME, "!ffffffff", "hello from the phone", NOW - 900, "tx"),
                text_message(1, OTHER, "!ffffffff", "first light", NOW - 3600)]
    return {
        "GET /api/status": status(),
        "GET /api/nodes": {"nodes": [me, other]},
        "GET /api/messages?limit=200": {"messages": messages},
        "GET /api/packets?limit=200": {"packets": []},
        "GET /api/messages/stats": {"today_text": 2, "total": 3},
        "GET /api/iridium/modem": {"connected": False, "port": "", "model": "", "imei": ""},
        "GET /api/iridium/signal": {"bars": 0, "timestamp": ""},
        "GET /api/routing/hub": {"url": "", "bridge_id": "", "username": "", "has_password": False, "has_cert": False},
        "GET /api/deadman": {"enabled": False, "timeout_min": 240, "last_activity": "", "triggered": False},
        "GET /api/keys/stats": {"active": 0, "retired": 0, "revoked": 0, "enabled": False},
        "GET /api/cellular/status": {"connected": False, "sim_state": "NOT_INSERTED", "registration": "", "operator": "", "model": "", "phone_number": "", "sms_sent": 0, "sms_received": 0},
        "GET /api/cellular/sms?limit=200": [],
        "GET /api/mesh/ble/status": {"mode": "off", "address": "", "name": "", "connected": False, "pairing_pending": False, "satellite_pipe": False},
        "GET /api/config": rec("config", {"config_6": {"7": 3, "2": 0, "8": 3, "10": 0}, "channel_0": {"2": {"3": "msat-ttc-01"}}}),
        "GET /api/aprs/status": {"connected": False},
        "GET /api/tak/enroll/status": {"enrolled": False},
        "GET /api/rns/status": {"enabled": False, "links": 0},
        "GET /api/iridium/signal/fast": {"error": "no modem"},
        "GET /api/version": rec("version", {"version": "test"}),
        "GET /api/access-rules": rec("access-rules", []),
        "GET /api/interfaces": rec("interfaces", []),
        "GET /api/interfaces/health": rec("interfaces_health", []),
        "GET /api/object-groups": rec("object-groups", []),
        "GET /api/failover-groups": rec("failover-groups", []),
        "GET /api/deliveries": rec("deliveries", []),
        "GET /api/iridium/passes": {"passes": [], "tle_source": "none", "tle_age": -1, "cache_age": -1, "error": "no orbit data"},
        "GET /api/iridium/signal/history": [],
        "GET /api/position/fixed": {"latitude": 0, "longitude": 0},
        "POST /api/sos/test": {"status": "sent"},
        "GET /api/neighbors": {"neighbors": None, "source": "database"},
        "GET /api/audit/signer": rec("audit_signer", {"signer_id": "082d35bc64aa838a5cb8dd189b75c94ae2cdcaebe8855731203ffb01c761483c"}),
        "_audit": [],
        "_credentials": [],
    }


def fresh() -> dict:
    """The Bridge not running at all: every call goes unanswered (the fake closes the connection)."""
    routes = base()
    routes["_down"] = True
    return routes


def mesh_only() -> dict:
    return base()


def one_node() -> dict:
    routes = base()
    routes["GET /api/nodes"] = {"nodes": [node(ME, "meshsat-pinephone-pro", "MSPP", NOW - 5, hw_model=255, hw_model_name="PORTDUINO", battery_level=101, rssi=0, snr=0)]}
    routes["GET /api/messages?limit=200"] = {"messages": []}
    routes["GET /api/messages/stats"] = {"today_text": 0, "total": 0}
    return routes


def nameless_node() -> dict:
    """After a Bridge restart: the other node is back without its name (the daemon keeps only
    what NodeInfo it decoded), and a third node is heard for the first time."""
    routes = base()
    routes["GET /api/nodes"] = {"nodes": [node(ME, "meshsat-pinephone-pro", "MSPP", NOW - 5, hw_model=255, hw_model_name="PORTDUINO", battery_level=101, rssi=0, snr=0),
                                          node(OTHER, "", "", NOW - 60), node(THIRD, "", "", NOW - 30)]}
    return routes


def satellite_3_bars() -> dict:
    routes = base()
    routes["GET /api/iridium/modem"] = {"connected": True, "port": "/dev/ttyUSB4", "model": "RockBLOCK 9603", "imei": "300434065000000"}
    routes["GET /api/iridium/signal"] = {"bars": 3, "timestamp": "2026-09-28T17:00:00Z"}
    routes["GET /api/iridium/signal/fast"] = {"bars": 3}
    return routes


def sim_ready() -> dict:
    routes = base()
    routes["GET /api/cellular/status"] = {"connected": True, "sim_state": "READY", "registration": "registered_home", "operator": "KPN", "model": "Quectel EG25-G",
                                          "phone_number": "+31600000000", "sms_sent": 2, "sms_received": 1, "network_type": "LTE"}
    routes["GET /api/cellular/sms?limit=200"] = [{"id": 1, "direction": "rx", "phone": "+31611111111", "text": "Are you there?", "timestamp": NOW - 1800, "status": "received"},
                                                 {"id": 2, "direction": "tx", "phone": "+31611111111", "text": "Yes, on my way", "timestamp": NOW - 1700, "status": "sent"}]
    return routes


def all_four() -> dict:
    routes = sim_ready()
    routes.update({k: v for k, v in satellite_3_bars().items() if k.startswith("GET /api/iridium")})
    routes["GET /api/routing/hub"] = {"url": "mqtts://hub.meshsat.net:8883", "bridge_id": "msa-pinephone", "username": "msa-pinephone", "has_password": True, "has_cert": False, "link": "connected"}
    return routes


def hub_set_up() -> dict:
    routes = base()
    routes["GET /api/routing/hub"] = {"url": "mqtts://hub.meshsat.net:8883", "bridge_id": "msa-pinephone", "username": "msa-pinephone", "has_password": True, "has_cert": False}
    return routes


def sos_active() -> dict:
    routes = base()
    routes["_sos"] = {"active": True, "started_at": "2026-09-28T17:05:00Z", "sends": 2, "test": False}
    return routes


def bluetooth_pairing() -> dict:
    routes = base()
    routes["GET /api/status"] = status(connected=False, address="", transport="ble", node_id="", node_name="")
    routes["GET /api/mesh/ble/status"] = {"mode": "pairing", "address": "E0:72:A1:B3:C2:ED", "name": "MSPA_c2ec", "connected": False, "pairing_pending": True, "pairing_since": "2026-09-28T17:00:00Z", "satellite_pipe": False}
    routes["GET /api/mesh/ble/scan"] = {"devices": [{"name": "MSPA_c2ec", "address": "E0:72:A1:B3:C2:ED", "rssi": -55}, {"name": "MSPB_c3a4", "address": "E0:72:A1:B3:C3:A5", "rssi": -70}]}
    return routes


def bluetooth_connected() -> dict:
    routes = base()
    routes["GET /api/status"] = status(address="E0:72:A1:B3:C2:ED", transport="ble", node_id=OTHER, node_name="MSPA")
    routes["GET /api/mesh/ble/status"] = {"mode": "ready", "address": "E0:72:A1:B3:C2:ED", "name": "MSPA_c2ec", "connected": True, "pairing_pending": False, "satellite_pipe": False}
    return routes


def stamp(seconds_ago: int) -> str:
    """A time stamp as SQLite writes it in the Bridge's database (UTC, no zone)."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(NOW - seconds_ago))


def delivery(id_: int, channel: str, status: str, text: str, ago: int, **more) -> dict:
    out = {"id": id_, "msg_ref": f"msg-{id_}", "channel": channel, "status": status, "priority": 1, "text_preview": text, "retries": 0, "max_retries": 10, "last_error": "",
           "channel_ref": "", "cost": 0, "visited": "[]", "ttl_seconds": 0, "qos_level": 1, "seq_num": id_, "class": "message", "created_at": stamp(ago), "updated_at": stamp(max(0, ago - 30))}
    out.update(more)
    return out


def queue_busy() -> dict:
    """Every state the queue can show, over four links; three rules, one on each tab; a group,
    a backup group, health scores. The links: the mesh working, the satellite modem off (its
    port known), SMS failing, the Hub not connected, ham radio switched off."""
    routes = base()
    routes["_deliveries"] = [
        delivery(1, "iridium_0", "queued", "Position report", 240),
        delivery(2, "iridium_0", "retry", "Camp reached, all well", 900, retries=2, last_error="Not sent: status 32, no network service, MOMSN 233", next_retry="2026-09-28T18:30:00Z"),
        delivery(3, "sms_0", "held", "Back by six", 600),
        delivery(4, "mesh_0", "sending", "on my way", 30),
        delivery(5, "mesh_0", "sent", "hello from the phone", 3600),
        delivery(6, "iridium_0", "delivered", "Test from A MeshSat user", 7200, ack_status="acked"),
        delivery(7, "mesh_0", "failed", "are you there", 1800, retries=1, last_error="Could not hand the message to the modem"),
        delivery(8, "iridium_0", "dead", "Weather closing in", 10800, retries=10, last_error="cancelled: exceeded retry limit (10)"),
        delivery(9, "sms_0", "dead", "Running late", 5400, last_error="cancelled"),
        delivery(10, "iridium_0", "expired", "Old news", 90000, last_error="TTL expired", ttl_seconds=3600, expires_at="2026-09-27T18:00:00Z"),
    ]
    routes["_rules"] = [
        {"id": 1, "interface_id": "mesh_0", "direction": "ingress", "priority": 0, "name": "SOS to satellite", "enabled": True, "action": "forward", "forward_to": "iridium_0",
         "filters": '{"keyword":"SOS","channels":"[0]"}', "filter_node_group": None, "filter_sender_group": None, "filter_portnum_group": None, "schedule_type": "none",
         "schedule_config": "", "forward_options": '{"ttl_seconds":600}', "qos_level": 1, "rate_limit_per_min": 5, "rate_limit_window": 60, "match_count": 0,
         "created_at": "2026-09-28T10:00:00Z", "updated_at": "2026-09-28T10:00:00Z"},
        {"id": 2, "interface_id": "iridium_0", "direction": "ingress", "priority": 10, "name": "Satellite into the mesh", "enabled": True, "action": "forward", "forward_to": "mesh_0",
         "filters": "{}", "filter_node_group": None, "filter_sender_group": None, "filter_portnum_group": None, "schedule_type": "none", "schedule_config": "",
         "forward_options": "{}", "qos_level": 1, "rate_limit_per_min": 0, "rate_limit_window": 0, "match_count": 3, "last_match_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 120)),
         "created_at": "2026-09-28T10:00:00Z", "updated_at": "2026-09-28T10:00:00Z"},
        {"id": 3, "interface_id": "sms_0", "direction": "ingress", "priority": 10, "name": "Stop spam", "enabled": False, "action": "drop", "forward_to": "",
         "filters": "{}", "filter_node_group": None, "filter_sender_group": "spammers", "filter_portnum_group": None, "schedule_type": "none", "schedule_config": "",
         "forward_options": "{}", "qos_level": 0, "rate_limit_per_min": 0, "rate_limit_window": 0, "match_count": 1, "last_match_at": None,
         "created_at": "2026-09-28T10:00:00Z", "updated_at": "2026-09-28T10:00:00Z"},
    ]
    routes["GET /api/interfaces"] = [
        {"id": "mesh_0", "channel_type": "mesh", "label": "Meshtastic LoRa", "enabled": True, "state": "unbound", "last_activity": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 300)),
         "ingress_transforms": "[]", "egress_transforms": "[]"},
        {"id": "iridium_0", "channel_type": "iridium", "label": "Iridium SBD", "enabled": True, "state": "offline", "device_id": "/dev/ttyUSB4", "last_activity": "0001-01-01T00:00:00Z",
         "ingress_transforms": "[]", "egress_transforms": "[]"},
        {"id": "sms_0", "channel_type": "cellular", "label": "Cellular SMS", "enabled": True, "state": "error", "error": "modem not registered", "last_activity": "0001-01-01T00:00:00Z",
         "ingress_transforms": "[]", "egress_transforms": "[]"},
        {"id": "hub_0", "channel_type": "mqtt", "label": "MQTT Broker", "enabled": True, "state": "unbound", "last_activity": "0001-01-01T00:00:00Z", "ingress_transforms": "[]", "egress_transforms": "[]"},
        {"id": "aprs_0", "channel_type": "aprs", "label": "APRS (Direwolf)", "enabled": False, "state": "unbound", "last_activity": "0001-01-01T00:00:00Z", "ingress_transforms": "[]", "egress_transforms": "[]"},
    ]
    routes["GET /api/interfaces/health"] = [
        {"interface_id": "mesh_0", "score": 85, "signal": 70, "success_rate": 1, "latency_ms": 1200, "cost_score": 100, "available": True},
        {"interface_id": "iridium_0", "score": 40, "signal": 0, "success_rate": 0.5, "latency_ms": 90000, "cost_score": 50, "available": True},
        {"interface_id": "sms_0", "score": 0, "signal": 0, "success_rate": 0, "latency_ms": 0, "cost_score": 60, "available": False},
    ]
    routes["GET /api/object-groups"] = [{"id": "spammers", "type": "sender_group", "label": "Spammers", "members": '["+31600000001","+31600000002"]', "created_at": "2026-09-28T10:00:00Z"}]
    routes["GET /api/failover-groups"] = [{"id": "backup-1", "label": "Satellite backup", "mode": "failover", "created_at": "2026-09-28T10:00:00Z",
                                          "members": [{"id": 1, "group_id": "backup-1", "interface_id": "mesh_0", "priority": 1}, {"id": 2, "group_id": "backup-1", "interface_id": "iridium_0", "priority": 2}]}]
    return routes


KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
EVENTS = ("dispatch", "deliver", "forward", "deny", "connect", "sos_activated", "oob_reject")


def advanced() -> dict:
    """The rest of Advanced in use: a node heard directly and one two hops away that another
    reported hearing; 120 audit entries; three certificates (valid, expiring, expired); the
    links' key for encrypting; health scores."""
    routes = queue_busy()
    me = node(ME, "meshsat-pinephone-pro", "MSPP", NOW - 5, hw_model=255, hw_model_name="PORTDUINO", battery_level=101, rssi=0, snr=0)
    near = node(OTHER, "MSPA", "MSPA", NOW - 120, hw_model=50, hw_model_name="T_DECK", snr=5.5, rssi=-60, battery_level=78)
    far = node(THIRD, "Far Hill", "FARH", NOW - 1800, hw_model=43, hw_model_name="HELTEC_V3", battery_level=40, hops_away=2, snr=0, rssi=0)
    routes["GET /api/nodes"] = {"nodes": [me, near, far]}
    routes["GET /api/neighbors"] = {"neighbors": [{"node_id": int(OTHER[1:], 16), "last_sent_by_id": int(OTHER[1:], 16), "node_broadcast_interval_secs": 900,
                                                   "neighbors": [{"node_id": int(THIRD[1:], 16), "snr": -3.25}],
                                                   "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 300))}], "source": "live"}
    audit = []
    for i in range(1, 121):
        event = EVENTS[i % len(EVENTS)]
        entry = {"id": i, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - (121 - i) * 60)), "event_type": event, "detail": f"e2e entry {i}",
                 "prev_hash": f"h{i - 1}", "hash": f"h{i}"}
        if i % 2 == 0:
            entry["interface_id"] = "mesh_0"
            entry["direction"] = "egress"
        elif i % 3 == 0:
            entry["interface_id"] = "iridium_0"
            entry["direction"] = "ingress"
        if i % 4 == 0:
            entry["delivery_id"] = i
            entry["rule_id"] = 1
        audit.append(entry)
    routes["_audit"] = audit
    day = 86400
    routes["_credentials"] = [
        {"id": "cred-hub", "provider": "hub_mqtt", "name": "hub.meshsat.net", "cred_type": "mqtt_bundle", "cert_not_after": time.strftime("%Y-%m-%d", time.gmtime(NOW + 400 * day)),
         "cert_subject": "CN=hub.meshsat.net", "cert_fingerprint": "0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9", "version": 2, "source": "hub", "applied": 1},
        {"id": "cred-soon", "provider": "local", "name": "soon.pem", "cred_type": "x509_cert", "cert_not_after": time.strftime("%Y-%m-%d", time.gmtime(NOW + 10 * day)),
         "cert_subject": "CN=soon.example", "cert_fingerprint": "ff" * 32, "version": 1, "source": "local", "applied": 0},
        {"id": "cred-old", "provider": "local", "name": "old.pem", "cred_type": "x509_cert", "cert_not_after": time.strftime("%Y-%m-%d", time.gmtime(NOW - 10 * day)),
         "cert_subject": "CN=old.example", "cert_fingerprint": "00" * 32, "version": 1, "source": "local", "applied": 0},
    ]
    for iface in routes["GET /api/interfaces"]:
        if iface["id"] == "mesh_0":
            iface["egress_transforms"] = '[{"type":"encrypt","params":{"key":"' + KEY + '"}},{"type":"base64"}]'
    return routes


SCENARIOS = {"fresh": fresh, "mesh-only": mesh_only, "one-node": one_node, "nameless-node": nameless_node, "satellite-3-bars": satellite_3_bars, "sim-ready": sim_ready,
             "all-four": all_four, "hub-set-up": hub_set_up, "sos-active": sos_active, "bluetooth-pairing": bluetooth_pairing, "bluetooth-connected": bluetooth_connected,
             "queue-busy": queue_busy, "advanced": advanced}


def build(name: str) -> dict:
    if name not in SCENARIOS:
        raise KeyError(f"no scenario {name!r}; there are {sorted(SCENARIOS)}")
    return SCENARIOS[name]()
