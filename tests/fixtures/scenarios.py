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
        "GET /api/deliveries": rec("deliveries", {"deliveries": []}),
        "GET /api/iridium/passes": {"passes": [], "tle_source": "none", "tle_age": -1, "cache_age": -1, "error": "no orbit data"},
        "GET /api/iridium/signal/history": [],
        "GET /api/position/fixed": {"latitude": 0, "longitude": 0},
        "POST /api/sos/test": {"status": "sent"},
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


SCENARIOS = {"fresh": fresh, "mesh-only": mesh_only, "one-node": one_node, "nameless-node": nameless_node, "satellite-3-bars": satellite_3_bars, "sim-ready": sim_ready,
             "all-four": all_four, "hub-set-up": hub_set_up, "sos-active": sos_active, "bluetooth-pairing": bluetooth_pairing, "bluetooth-connected": bluetooth_connected}


def build(name: str) -> dict:
    if name not in SCENARIOS:
        raise KeyError(f"no scenario {name!r}; there are {sorted(SCENARIOS)}")
    return SCENARIOS[name]()
