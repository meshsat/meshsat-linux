# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > "Ham radio, TAK and Reticulum" in MeshSat Android's words (ui/screens/SettingsScreen.kt:
1180-1623 at v2.19.4): the three cards' words, the fields' input filters, the APRS-IS passcode,
what each switch and Save writes to the Bridge (the `aprs` and `tak` gateways, the `tcp_rns_0`
Reticulum interface) and the status rows' words. Pure: no GTK, tested on the runner.

The Bridge's gateway PUT replaces the stored config whole and reads a missing `enabled` as false,
so every body carries `enabled` and the config as read, with the change laid over it."""

TITLE = "Ham radio, TAK and Reticulum"

# ── Ham radio (APRS), SettingsScreen.kt:1181-1453 ─────────────────────────────────────────────
APRS_TITLE = "Ham radio (APRS)"
ENABLE_APRS = "Enable APRS"
KISS = "KISS TNC"
IS = "APRS-IS Direct"
IS_ROW = "APRS-IS"
IS_ROW_VERIFIED = "APRS-IS (verified)"
CALLSIGN = "Callsign"
SSID = "SSID (0-15)"
KISS_HOST = "KISS Host"
PORT = "Port"
FREQUENCY_NOTE = "The frequency is set on the radio itself: 144.800 MHz in Europe, 144.390 MHz in North America."
IS_SERVER = "APRS-IS Server"
PASSCODE = "Passcode"
AUTO = "Auto"
RADIUS = "Filter radius (km)"
BEACON = "Position beacon"
BEACON_INTERVAL = "Beacon interval (min)"
SAVE = "Save"
APRS_SAVED = "APRS settings saved"
# Android names APRSDroid, which Linux phones do not have: the Bridge speaks to Direwolf's KISS
# server (its link is "APRS (Direwolf)"). Recorded in tests/parity/excluded-strings.json.
KISS_NOTE = ("Connect to Direwolf's KISS TCP server for local RF APRS via AIOC + handheld radio. "
             "SSID 7 = handheld, 10 = igate. EU: 144.800 MHz, NA: 144.390 MHz.")
IS_NOTE = ("Connect directly to APRS-IS (rotate.aprs2.net) over the internet. "
           "No Direwolf or radio needed. Use passcode -1 for receive-only, or Auto to calculate from callsign. "
           "Position beacon sends GPS location at the configured interval.")

# ── TAK, SettingsScreen.kt:1458-1530 ──────────────────────────────────────────────────────────
TAK_TITLE = "TAK"
ENABLE_TAK = "Enable TAK"
PREFIX = "Callsign Prefix"
ATAK = "ATAK Broadcast"
MQTT_EXPORT = "MQTT Export to Hub"
TAK_SAVED = "TAK settings saved"
# Android ends with "Restart service after changing prefix.": the Bridge applies a Save at once.
TAK_NOTE = ("Generates CoT (Cursor on Target) events for positions, SOS, telemetry, and chat. "
            "ATAK Broadcast sends locally to ATAK if installed. MQTT Export sends to Hub for relay to a TAK server. "
            "Callsign format: PREFIX-XXXX (last 4 hex of device ID).")

# ── Reticulum, SettingsScreen.kt:1535-1622 ────────────────────────────────────────────────────
RNS_TITLE = "Reticulum"
ENABLE_RNS = "Enable RNS TCP"
RNS_ROW = "RNS TCP"
HOST = "Host"
TLS = "TLS"
RNS_SAVED = "RNS TCP settings saved"
RNS_NOTE = ("Connect to a stock Reticulum (Python RNS) node over TCP/IP. "
            "Enable TLS for public endpoints (e.g. port 443 via HAProxy/stunnel). "
            "Default port 4242. Uses HDLC framing for wire compatibility.")

# The status rows' words (ConnectionStatusRow)
CONNECTED, CONNECTING, ERROR, DISCONNECTED = "Connected", "Connecting...", "Error", "Disconnected"

# Android's defaults (SettingsRepository.kt)
DEFAULT_SSID, DEFAULT_KISS_HOST, DEFAULT_KISS_PORT = "10", "localhost", "8001"
DEFAULT_IS_HOST, DEFAULT_IS_PORT, DEFAULT_PASSCODE = "rotate.aprs2.net", "14580", "-1"
DEFAULT_RADIUS, DEFAULT_INTERVAL = "100", "10"
DEFAULT_PREFIX, DEFAULT_RNS_PORT = "MESHSAT", "4242"
RNS_ID = "tcp_rns_0"


# ── Input filters, as Android's onValueChange ─────────────────────────────────────────────────
def digits(value: str, most: int) -> str:
    """Kotlin's filter{isDigit}.take(n): Unicode decimal digits only."""
    return "".join(ch for ch in value if ch.isdecimal())[:most]


def callsign(value: str) -> str:
    return value.upper()[:6]


def ssid(value: str) -> str:
    return digits(value, 2)


def port(value: str) -> str:
    return digits(value, 5)


def passcode_input(value: str) -> str:
    return "".join(ch for ch in value if ch.isdecimal() or ch == "-")[:6]


def radius(value: str) -> str:
    return digits(value, 4)


def interval(value: str) -> str:
    return digits(value, 3)


def prefix(value: str) -> str:
    return value.upper()[:10]


# ── APRS-IS ───────────────────────────────────────────────────────────────────────────────────
def passcode(call: str) -> str:
    """AprsIsPasscode.calculate: the callsign without its SSID, upper case; "-1" when empty."""
    base = call.split("-")[0].upper()
    if not base:
        return "-1"
    h = 0x73E2
    for i in range(0, len(base), 2):
        h ^= ord(base[i]) << 8
        if i + 1 < len(base):
            h ^= ord(base[i + 1])
    return str(h & 0x7FFF)


def full_callsign(call: str, ssid_text: str) -> str:
    """GatewayService.kt:1429: the bare call for an SSID of "" or "0"; "00" keeps its SSID."""
    return call if ssid_text in ("", "0") else f"{call}-{ssid_text}"


def split_server(server: str) -> tuple:
    """"host:port" at the last colon, a bracketed IPv6 host kept whole."""
    server = server or ""
    if server.startswith("[") and "]" in server:
        host, _, rest = server.partition("]")
        return host + "]", rest.lstrip(":") or DEFAULT_IS_PORT
    if ":" in server:
        host, _, p = server.rpartition(":")
        return host, p
    return server, DEFAULT_IS_PORT


def number(text: str, fallback: int) -> int:
    return int(text) if text.isdecimal() else fallback


# ── What the Bridge holds, and what a write sends ─────────────────────────────────────────────
def aprs_form(record: dict | None, saved_passcode: str | None = None) -> dict:
    """The APRS card's fields from the Bridge's `aprs` gateway (Android's defaults for a 404)."""
    config = dict((record or {}).get("config") or {})
    host, p = split_server(config.get("aprs_is_server") or f"{DEFAULT_IS_HOST}:{DEFAULT_IS_PORT}")
    stored = config.get("aprs_is_passcode")
    if saved_passcode:
        code = saved_passcode
    elif not stored:
        code = DEFAULT_PASSCODE
    else:
        code = ""  # a secret the Bridge keeps and shows as ****: sent back as ****
    return {"enabled": bool((record or {}).get("enabled")), "mode": config.get("mode") or "kiss",
            "callsign": config.get("callsign") or "", "ssid": str(config.get("ssid", DEFAULT_SSID)) if record else DEFAULT_SSID,
            "kiss_host": config.get("kiss_host") or DEFAULT_KISS_HOST, "kiss_port": str(config.get("kiss_port") or DEFAULT_KISS_PORT),
            "is_host": host, "is_port": p, "passcode": code,
            "radius": str(config.get("aprs_is_filter_km", DEFAULT_RADIUS)) if record else DEFAULT_RADIUS,
            "beacon": bool(config.get("position_beacon")), "interval": str(config.get("position_beacon_min") or DEFAULT_INTERVAL)}


def aprs_flag_body(record: dict, **changed) -> dict:
    """A switch or a chip: the stored config unchanged but for that one key, `enabled` always there."""
    config = dict(record.get("config") or {})
    enabled = changed.pop("enabled", bool(record.get("enabled")))
    config.update(changed)
    return {"enabled": bool(enabled), "config": config}


def aprs_save_body(record: dict | None, enabled: bool, mode: str, fields: dict, position: tuple | None) -> dict:
    """Save: the stored config with the card's fields laid over it. KISS on a phone always uses an
    external Direwolf (the package has none of its own); the kits' radio keys are never written."""
    config = dict((record or {}).get("config") or {})
    config.update({"callsign": fields["callsign"], "ssid": number(fields["ssid"], 0), "mode": mode})
    if mode == "kiss":
        config.update({"kiss_host": fields["kiss_host"] or DEFAULT_KISS_HOST, "kiss_port": number(fields["kiss_port"], int(DEFAULT_KISS_PORT)),
                       "external_direwolf": True})
    else:
        host = fields["is_host"] or DEFAULT_IS_HOST
        p = fields["is_port"] if fields["is_port"].isdecimal() else DEFAULT_IS_PORT
        lat, lon = position if position else (0.0, 0.0)
        config.update({"aprs_is_server": f"{host}:{p}", "aprs_is_passcode": fields["passcode"] or ("****" if config.get("aprs_is_passcode") else DEFAULT_PASSCODE),
                       "aprs_is_filter_km": number(fields["radius"], int(DEFAULT_RADIUS)), "aprs_is_filter_lat": lat, "aprs_is_filter_lon": lon,
                       "position_beacon": bool(fields["beacon"]), "position_beacon_min": number(fields["interval"], int(DEFAULT_INTERVAL))})
    config.pop("kiss_device", None)
    return {"enabled": bool(enabled), "config": config}


def aprs_status(record: dict | None, status: dict | None, pending: bool = False) -> tuple | None:
    """(label, words, connected) of the APRS row, or None: shown while the gateway is on."""
    if not (record or {}).get("enabled") and not pending:
        return None
    status = status or {}
    mode = ((record or {}).get("config") or {}).get("mode") or "kiss"
    state = status.get("state")
    if state is None:  # a Bridge from before batch 3b: running = kiss_addr present
        state = "connected" if status.get("connected") else ("connecting" if status.get("kiss_addr") or pending else "error")
    words = {"connected": CONNECTED, "connecting": CONNECTING, "error": ERROR}.get(state, DISCONNECTED)
    if mode == "is":
        label = IS_ROW_VERIFIED if state == "connected" and status.get("aprs_is_verified") else IS_ROW
    else:
        label = KISS
    return label, words, state == "connected"


def tak_form(record: dict | None) -> dict:
    if record is None:
        return {"enabled": False, "prefix": DEFAULT_PREFIX, "atak": True, "export": True}
    config = record.get("config") or {}
    return {"enabled": bool(record.get("enabled")), "prefix": config.get("callsign_prefix") or DEFAULT_PREFIX,
            "atak": bool(config.get("multicast")), "export": bool(config.get("hub_export"))}


def tak_body(record: dict | None, **changed) -> dict:
    """The first write carries Android's defaults (prefix MESHSAT, both outputs on)."""
    config = dict((record or {}).get("config") or {"callsign_prefix": DEFAULT_PREFIX, "multicast": True, "hub_export": True})
    enabled = changed.pop("enabled", bool((record or {}).get("enabled")))
    if "prefix" in changed:
        config["callsign_prefix"] = changed.pop("prefix")
    if "atak" in changed:
        config["multicast"] = bool(changed.pop("atak"))
    if "export" in changed:
        config["hub_export"] = bool(changed.pop("export"))
    return {"enabled": bool(enabled), "config": config}


def rns_form(iface: dict | None, prefs: dict) -> dict:
    """The card from the Bridge's tcp_rns_0, or from the app's preferences before it exists."""
    if iface:
        config = iface.get("config") or {}
        return {"enabled": bool(iface.get("enabled")), "host": config.get("host") or "", "port": str(config.get("port") or DEFAULT_RNS_PORT),
                "tls": bool(config.get("tls"))}
    return {"enabled": bool(prefs.get("enabled")), "host": prefs.get("host") or "", "port": prefs.get("port") or DEFAULT_RNS_PORT, "tls": bool(prefs.get("tls"))}


def rns_config(host: str, port_text: str, tls: bool) -> dict:
    return {"host": host.strip(), "port": number(port_text, int(DEFAULT_RNS_PORT)), "tls": bool(tls)}


def rns_status(iface: dict | None) -> tuple | None:
    """(label, words, connected) of the RNS row, or None: shown while tcp_rns_0 is on."""
    if not iface or not iface.get("enabled"):
        return None
    if iface.get("online"):
        return RNS_ROW, CONNECTED, True
    if iface.get("running"):
        return RNS_ROW, DISCONNECTED if iface.get("last_error") else CONNECTING, False
    return RNS_ROW, ERROR, False
