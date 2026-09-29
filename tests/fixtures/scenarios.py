# SPDX-License-Identifier: GPL-3.0-or-later
"""The states the scripted Bridge plays for the tests, each a map of "METHOD /path" to the
answer. They start from the Bridge's own answers recorded on the bench phone
(tests/fixtures/recorded/<date>-<sha>/, tools/record-fixtures.sh) and change what the state
is about; what no recording holds is written here in the Bridge's shapes."""
import copy
import glob
import json
import math
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


def settings(node_id: str = None, long_name: str = "meshsat-pinephone-pro", short_name: str = "MSPP", hw_model: int = 37, firmware: str = "2.7.3.dev",
             wifi: bool = False, bluetooth: bool = False, can_shutdown: bool = False, debug_log: bool = False) -> dict:
    """The node's settings as the Bridge's GET /api/config?format=names gives them (MESHSAT-1405):
    named sections with every field (protojson, enums as numbers), channels with their key as
    a word, no private key. Defaults: the phone's LoRa back cover (meshtasticd, portduino)."""
    node_id = node_id or ME
    lora = {"use_preset": True, "modem_preset": 0, "bandwidth": 0, "spread_factor": 0, "coding_rate": 0, "frequency_offset": 0, "region": 3, "hop_limit": 3,
            "tx_enabled": True, "tx_power": 0, "channel_num": 0, "override_duty_cycle": False, "sx126x_rx_boosted_gain": False, "override_frequency": 0,
            "pa_fan_disabled": False, "ignore_incoming": [], "ignore_mqtt": False, "config_ok_to_mqtt": False}
    position = {"position_broadcast_secs": 900, "position_broadcast_smart_enabled": True, "fixed_position": False, "gps_enabled": False, "gps_update_interval": 120,
                "gps_attempt_time": 0, "position_flags": 811, "rx_gpio": 0, "tx_gpio": 0, "broadcast_smart_minimum_distance": 100,
                "broadcast_smart_minimum_interval_secs": 30, "gps_en_gpio": 0, "gps_mode": 0}
    security = {"public_key": "", "admin_key": [], "is_managed": False, "serial_enabled": True, "debug_log_api_enabled": debug_log, "admin_channel_enabled": False,
                "private_key_set": True}
    channels = [{"index": 0, "role": 1, "name": "msat-ttc-01", "key": "private", "uplink_enabled": False, "downlink_enabled": False, "position_precision": 13},
                {"index": 1, "role": 2, "name": "i9603", "key": "private", "uplink_enabled": False, "downlink_enabled": False, "position_precision": 0}]
    channels += [{"index": i, "role": 0, "name": "", "key": "none", "uplink_enabled": False, "downlink_enabled": False} for i in range(2, 8)]
    return {
        "loaded": True, "node_num": int(node_id[1:], 16), "node_id": node_id, "firmware_version": firmware,
        "owner": {"long_name": long_name, "short_name": short_name, "is_licensed": False, "hw_model": hw_model},
        "metadata": {"firmware_version": firmware, "device_state_version": 24, "hw_model": hw_model, "role": 0, "position_flags": 811, "can_shutdown": can_shutdown,
                     "has_wifi": wifi, "has_bluetooth": bluetooth, "has_ethernet": False, "has_remote_hardware": False, "has_pkc": True},
        "config": {"lora": lora, "position": position, "security": security,
                   "bluetooth": {"enabled": bluetooth, "mode": 0, "fixed_pin": 123456},
                   "network": {"wifi_enabled": False, "wifi_ssid": "", "wifi_psk": "", "ntp_server": "meshtastic.pool.ntp.org", "eth_enabled": False, "address_mode": 0,
                               "rsyslog_server": "", "enabled_protocols": 0, "ipv6_enabled": False},
                   "device": {"role": 0, "serial_enabled": False, "button_gpio": 0, "buzzer_gpio": 0, "rebroadcast_mode": 0, "node_info_broadcast_secs": 10800,
                              "double_tap_as_button_press": False, "is_managed": False, "disable_triple_click": False, "tzdef": "", "led_heartbeat_disabled": False,
                              "buzzer_mode": 0}},
        "module": {"mqtt": {"enabled": False, "address": "", "username": "", "password": "", "encryption_enabled": True, "json_enabled": False, "tls_enabled": False,
                            "root": "msh", "proxy_to_client_enabled": False, "map_reporting_enabled": False}},
        "channels": channels,
    }


# The fixed vector's card as the Bridge signs it with no node name (seed 00..1f, MESHSAT-1416).
MY_CARD = {"text": "meshsat:contact:1:TWVzaFNhdCBwaG9uZR9BNkVIdl9QT0VMNGRjTjBZNTB2QW1XZmsxakNicFExZkhkeUdaQkpWTWJnHx8fMTc4OTkwMDAwMA."
                   "OGA5_8_Q-mGL0x0kavwMIeFHryIyk4UagJH4KlmSgNDR4Xq9Nzzi98e7TS9eN3ZSCTeAV8GmhK5YVVk8H_sxAA",
           "fingerprint": "5647 5aa7 5463 474c", "signing_pub": "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8", "name": "MeshSat phone",
           "mesh_node_id": "", "bridge_id": "", "issued_at": 1789900000}


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
        "GET /api/routing/hub": {"url": "", "bridge_id": "", "username": "", "has_password": False, "has_cert": False, "enabled": True, "state": ""},
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
        "GET /api/deliveries/stats": [],
        "GET /api/cellular/signal/history": [],
        # No 9704: its gateway is not running (the Bridge answers 503 for type=imt)
        "GET /api/iridium/modem?type=imt": {"_status": 503, "_body": {"error": "IMT gateway not running"}},
        "GET /api/iridium/signal/fast?type=imt": {"_status": 503, "_body": {"error": "IMT gateway not running"}},
        "GET /api/iridium/signal?type=imt": {"_status": 503, "_body": {"error": "IMT gateway not running"}},
        "GET /api/position/fixed": {"latitude": 0, "longitude": 0},
        "POST /api/sos/test": {"status": "sent"},
        "GET /api/neighbors": {"neighbors": None, "source": "database"},
        "GET /api/audit/signer": rec("audit_signer", {"signer_id": "082d35bc64aa838a5cb8dd189b75c94ae2cdcaebe8855731203ffb01c761483c"}),
        "_audit": [],
        "_credentials": [],
        "_settings": settings(),
        "_radio_log": [],
        "_gateways": {},  # no gateway set up: GET /api/gateways/{type} answers 404, as the Bridge
        "_zones": [],  # the geofence monitor running, no zone yet
        "_positions": [],  # no position logged
        "_card": MY_CARD,  # the card the Bridge signs for "My card" (the fixed vector's key)
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
    routes["GET /api/routing/hub"] = {"url": "mqtts://hub.meshsat.net:8883", "bridge_id": "msa-pinephone", "username": "msa-pinephone", "has_password": True, "has_cert": False,
                                      "link": "connected", "state": "connected", "enabled": True, "running_as": "msa-pinephone"}
    return routes


def hub_set_up() -> dict:
    routes = base()
    # Set up and still connecting (the Bridge's state since MESHSAT-1417; its link says "disconnected")
    routes["GET /api/routing/hub"] = {"url": "mqtts://hub.meshsat.net:8883", "bridge_id": "msa-pinephone", "username": "msa-pinephone", "has_password": True, "has_cert": False,
                                      "link": "disconnected", "state": "connecting", "enabled": True, "running_as": "msa-pinephone"}
    return routes


def integrations() -> dict:
    """Setup > Ham radio, TAK and Reticulum: APRS on KISS through an external Direwolf, connected;
    no TAK gateway; no Reticulum TCP interface."""
    routes = base()
    routes["_gateways"] = {"aprs": {"type": "aprs", "instance_id": "aprs_0", "enabled": True,
                                    "config": {"callsign": "N0CALL", "ssid": 10, "mode": "kiss", "kiss_host": "127.0.0.1", "kiss_port": 8001,
                                               "external_direwolf": True, "tx_delay": 300, "beacon_secs": 0, "relay_third_party": False,
                                               "frequency_mhz": 144.8, "aprs_is_server": "rotate.aprs2.net:14580", "aprs_is_passcode": ""}}}
    routes["GET /api/aprs/status"] = {"connected": True, "state": "connected", "mode": "kiss", "kiss_addr": "127.0.0.1:8001", "callsign": "N0CALL-10"}
    routes["_ifaces"] = []
    return routes


def integrations_empty() -> dict:
    """The same page on a Bridge with no APRS, TAK or Reticulum set up."""
    routes = base()
    routes["_gateways"] = {}
    routes["GET /api/aprs/status"] = {"connected": False}
    routes["_ifaces"] = []
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
    """A T-Deck adopted over Bluetooth: its own settings (WiFi and Bluetooth, it can switch
    itself off), its debug log off, a few lines of its log held by the Bridge."""
    routes = base()
    routes["GET /api/status"] = status(address="E0:72:A1:B3:C2:ED", transport="ble", node_id=OTHER, node_name="MSPA")
    routes["GET /api/mesh/ble/status"] = {"mode": "ready", "address": "E0:72:A1:B3:C2:ED", "name": "MSPA_c2ec", "connected": True, "pairing_pending": False, "satellite_pipe": False}
    routes["_settings"] = settings(OTHER, "MSPA", "MSPA", hw_model=50, firmware="2.7.26.a1b2c3d", wifi=True, bluetooth=True, can_shutdown=True)
    routes["_radio_log"] = [
        {"seq": 1, "received_at": "2026-09-29T00:10:01.5Z", "radio_time": 0, "level": "INFO", "source": "Router", "message": "Received text msg from=0x52cb81e7"},
        {"seq": 2, "received_at": "2026-09-29T00:10:02.0Z", "radio_time": 0, "level": "WARNING", "source": "IridiumPipe", "message": "modem did not answer"},
    ]
    routes["_log_available"] = True
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


def messaging(encoder: bool = False) -> dict:
    """Setup > Messaging and the SMS page: the SMS link and the SBD link with empty chains, the
    SMS gateway set up with one allowed sender and a secret (answered masked), MSVQ-SC's
    encoder present or not."""
    routes = base()
    link = lambda id_, ct, label: {"id": id_, "channel_type": ct, "label": label, "enabled": True, "state": "online", "device_id": "", "device_port": "",
                                    "last_activity": "0001-01-01T00:00:00Z", "ingress_transforms": "[]", "egress_transforms": "[]"}
    routes["GET /api/interfaces"] = [link("mesh_0", "mesh", "Meshtastic LoRa"), link("cellular_0", "cellular", "Cellular SMS"), link("iridium_0", "iridium", "Iridium SBD")]
    routes["_gateways"] = {"cellular": {"type": "cellular", "instance_id": "cellular_0", "enabled": True, "connected": False,
                                        "config": {"destination_numbers": [], "allowed_senders": ["+31600000001"], "webhook_in_secret": "****", "max_sms_segments": 1}}}
    routes["_msvqsc"] = encoder
    return routes


def circle(lat: float, lon: float, r: float, n: int = 32) -> list:
    """A zone's polygon as MeshSat Android saves one (GeofenceScreen.circlePolygon)."""
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        out.append({"lat": lat + math.degrees(r * math.cos(a) / 6371000.0), "lon": lon + math.degrees(r * math.sin(a) / (6371000.0 * math.cos(math.radians(lat))))})
    return out


HOME = (52.3731, 4.8932)
STATION = (52.0907, 5.1214)


def zones() -> dict:
    """Zones, tracks and positions (every age in the middle of its minute, so the words hold for
    half a minute either way): MSPA at home (heard 2 min ago), Far Hill at the station (heard
    30 min ago, so stale), a node that never sent a position, an APRS station only the position
    log knows; two zones, two crossings; tracks of the last hours (and one row older than a day,
    which the map must leave out)."""
    routes = base()
    me = node(ME, "meshsat-pinephone-pro", "MSPP", NOW - 5, hw_model=255, hw_model_name="PORTDUINO", battery_level=101, rssi=0, snr=0)
    near = node(OTHER, "MSPA", "MSPA", NOW - 105, hw_model=50, hw_model_name="T_DECK", latitude=HOME[0], longitude=HOME[1], altitude=12)
    far = node(THIRD, "Far Hill", "FARH", NOW - 1785, hw_model=43, hw_model_name="HELTEC_V3", battery_level=40, hops_away=2, snr=0, rssi=0,
               latitude=STATION[0], longitude=STATION[1])
    quiet = node("!c0ffee01", "Quiet One", "QUIE", NOW - 600, battery_level=0)
    routes["GET /api/nodes"] = {"nodes": [me, near, far, quiet]}
    routes["_zones"] = [
        {"id": "zone_1", "name": "Home", "polygon": circle(HOME[0], HOME[1], 200), "alert_on": "enter", "message": ""},
        {"id": "zone_2", "name": "Station", "polygon": circle(STATION[0], STATION[1], 1000), "alert_on": "both", "message": "Pick-up point"},
    ]
    routes["_zone_events"] = [{"zone_name": "Home", "node_id": OTHER, "event": "enter", "timestamp": (NOW - 225) * 1000},
                              {"zone_name": "Station", "node_id": "!0badf00d", "event": "exit", "timestamp": (NOW - 7200) * 1000}]
    rows = []
    for i, (who, lat, lon, ago) in enumerate([
        (OTHER, HOME[0], HOME[1], 150), (OTHER, 52.3700, 4.8900, 1800), (OTHER, 52.3650, 4.8850, 3600), (OTHER, 52.3600, 4.8800, 5400),
        (THIRD, STATION[0], STATION[1], 1900), (THIRD, 52.0950, 5.1100, 4000), (THIRD, 52.1000, 5.1000, 7000),
        ("PA3XYZ-9", 52.2000, 5.0000, 1185), ("PA3XYZ-9", 52.2100, 5.0100, 2000),
        (OTHER, 50.0, 4.0, 90000)]):
        rows.append({"id": 100 - i, "node_id": who, "latitude": lat, "longitude": lon, "altitude": 0, "sats_in_view": 0, "ground_speed": 0, "ground_track": 0,
                     "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - ago))})
    routes["_positions"] = sorted(rows, key=lambda r: r["created_at"], reverse=True)
    return routes


def zones_down() -> dict:
    """The Bridge up without its geofence monitor: zones answer 503."""
    routes = base()
    routes.pop("_zones")
    return routes


def home_cards() -> dict:
    """Home with every card filled: the 9603 connected at 3 bars, a pass high overhead now and
    a high one later, three hours of readings and two sessions, six hours of the mobile signal,
    and a queue on three lanes (Satellite 3, Mesh 1, SMS 1 waiting; 4 waiting, 1 sending, 3
    failed, 4 gave up)."""
    routes = satellite_3_bars()
    rows, n = [], 0
    for channel, state, count in (("iridium_0", "queued", 2), ("iridium_0", "retry", 1), ("mesh_0", "sending", 1), ("cellular_0", "failed", 3),
                                  ("mesh_0", "dead", 4), ("cellular_0", "held", 1), ("mesh_0", "sent", 2)):
        for _ in range(count):
            n += 1
            rows.append(delivery(n, channel, state, f"message {n}", 60 * n))
    routes["_deliveries"] = rows
    routes["GET /api/iridium/passes"] = {"passes": [
        {"satellite": "IRIDIUM 140", "aos": NOW - 300, "los": NOW + 300, "duration_min": 10, "peak_elev_deg": 55.2, "peak_azimuth": 180, "is_active": True},
        {"satellite": "IRIDIUM 112", "aos": NOW + 1200, "los": NOW + 1500, "duration_min": 5, "peak_elev_deg": 21.0, "peak_azimuth": 90, "is_active": False},
        {"satellite": "IRIDIUM 106", "aos": NOW + 3600, "los": NOW + 4200, "duration_min": 10, "peak_elev_deg": 62.0, "peak_azimuth": 10, "is_active": False},
    ], "tle_source": "cache", "tle_age_sec": 3600, "cache_age_sec": 60}
    routes["_signal_history"] = {"iridium": [{"timestamp": NOW - 600 * i, "value": float(1 + i % 5)} for i in range(18)],
                                 "gss": [{"timestamp": NOW - 3600, "value": 1.0}, {"timestamp": NOW - 5400, "value": 0.0}]}
    routes["GET /api/cellular/signal/history"] = [{"id": 36 - i, "timestamp": NOW - 600 * i, "bars": 3, "dbm": -93 + 10 * (i % 3), "technology": "LTE", "operator": "KPN"}
                                                  for i in range(36)]
    return routes


def bluetooth_off() -> dict:
    """A node adopted over Bluetooth with the phone's Bluetooth switched off: the link is down."""
    routes = base()
    routes["GET /api/status"] = status(connected=False, address="E0:72:A1:B3:C2:ED", transport="ble", node_id="", node_name="")
    routes["GET /api/mesh/ble/status"] = {"mode": "ready", "address": "E0:72:A1:B3:C2:ED", "name": "MSPA_c2ec", "connected": False, "pairing_pending": False,
                                          "satellite_pipe": False, "adapter_powered": False}
    return routes


SCENARIOS = {"fresh": fresh, "mesh-only": mesh_only, "one-node": one_node, "nameless-node": nameless_node, "satellite-3-bars": satellite_3_bars, "sim-ready": sim_ready,
             "all-four": all_four, "hub-set-up": hub_set_up, "integrations": integrations, "integrations-empty": integrations_empty, "sos-active": sos_active, "bluetooth-pairing": bluetooth_pairing, "bluetooth-connected": bluetooth_connected,
             "queue-busy": queue_busy, "advanced": advanced, "messaging": messaging, "messaging-encoder": lambda: messaging(True), "zones": zones, "zones-down": zones_down,
             "home-cards": home_cards, "bluetooth-off": bluetooth_off, "bluetooth-off-sos": lambda: {**bluetooth_off(), "_sos": sos_active()["_sos"]}}


def build(name: str) -> dict:
    if name not in SCENARIOS:
        raise KeyError(f"no scenario {name!r}; there are {sorted(SCENARIOS)}")
    return SCENARIOS[name]()
