# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh radio settings (ui/screens/RadioConfigScreen.kt, ui/components/RegionCheck.kt, and
ble/MeshtasticProtocol.kt's LoRaRegion and ModemPreset): the words, the limits, what counts as
a change, and the body each Apply sends. The Bridge lays a write over the node's own settings
(MESHSAT-1405), so a body names only what changed, as Android's builder sets only what changed.
The settings come from the Bridge's GET /api/config?format=names. Pure."""
import os

from . import words

TABS = ("Name", "Radio", "Channels", "Position", "Bluetooth", "WiFi", "Restart and reset")

READING = "Reading the radio's settings..."
CONNECT_TO_READ = "Connect your node to read its settings."
NOT_CONNECTED = "Your phone is not connected to your node, so its settings cannot be read or changed."
CONNECT = "Connect your node"
RESTARTS = "Sent to the radio. It restarts to apply the change."
RADIO_SENT = "Sent to the radio. It switches over in a few seconds; older firmware restarts to do it."
SENT = "Sent to the radio."
APPLY_RESTARTS = "Applying restarts the node. The phone reconnects by itself."

# The Bridge's answers to a write, in words (its 409 and 503).
NOT_LOADED = "The node has not sent these settings yet; try again in a moment."
NODE_GONE = "The node is not connected."


def refused(status: int, error: str) -> str:
    """What to say when the Bridge refuses a write: its own reason for a 400, else the state."""
    if status == 409:
        return NOT_LOADED
    if status in (0, 503):
        return NODE_GONE
    return error or "The node did not take the change."


# ── Name ─────────────────────────────────────────────────────────────────────────────────────
NAME_HINT = "The long name shows in other people's node lists. The short name, up to 4 characters, is used where space is tight."
LONG_MAX = 39
SHORT_MAX = 4


def has_line(metadata: dict | None) -> str:
    """The "Has" row: WiFi, Bluetooth, Ethernet, Power off."""
    if not metadata:
        return "-"
    parts = [label for key, label in (("has_wifi", "WiFi"), ("has_bluetooth", "Bluetooth"), ("has_ethernet", "Ethernet"), ("can_shutdown", "Power off"))
             if metadata.get(key)]
    return ", ".join(parts) or "-"


def node_facts(named: dict, proto_name: str = "") -> list:
    """The "This node" card: (label, value, mono). `proto_name` is the model's name in the
    protobuf enum (the Bridge's hw_model_name), for a model the app's table lacks."""
    owner = named.get("owner") or {}
    metadata = named.get("metadata") or {}
    hw = int(owner.get("hw_model") or 0) or int(metadata.get("hw_model") or 0)
    firmware = metadata.get("firmware_version") or named.get("firmware_version") or ""
    return [
        ("Node ID", named.get("node_id") or "-", True),
        ("Hardware", words.hardware_name(hw, proto_name) if hw else "-", False),
        ("Firmware", firmware or "-", True),
        ("Has", has_line(metadata), False),
    ]


def name_changed(long_name: str, short_name: str, owner: dict) -> bool:
    return long_name.strip() != (owner.get("long_name") or "") or short_name.strip() != (owner.get("short_name") or "")


def can_save_name(long_name: str, short_name: str, owner: dict) -> bool:
    return name_changed(long_name, short_name, owner) and bool(long_name.strip()) and bool(short_name.strip())


def owner_body(long_name: str, short_name: str) -> dict:
    """POST /api/config/owner; the Bridge sends the node's own is_licensed back with it."""
    return {"long_name": long_name.strip(), "short_name": short_name.strip()}


# ── Radio ────────────────────────────────────────────────────────────────────────────────────
REGIONS = ((0, "Unset"), (1, "US"), (2, "EU 433"), (3, "EU 868"), (4, "CN"), (5, "JP"), (6, "ANZ"), (7, "KR"), (8, "TW"), (9, "RU"), (10, "IN"),
           (11, "NZ 865"), (12, "TH"), (13, "2.4 GHz"), (14, "UA 433"), (15, "UA 868"), (16, "MY 433"), (17, "MY 919"), (18, "SG 923"))
REGION_NAMES = dict(REGIONS)
UNSET, LORA_24 = 0, 13
PRESETS = ((0, "Long Fast"), (1, "Long Slow"), (2, "Very Long Slow"), (3, "Medium Slow"), (4, "Medium Fast"), (5, "Short Slow"), (6, "Short Fast"),
           (7, "Long Moderate"), (8, "Short Turbo"))
PRESET_NAMES = dict(PRESETS)
PRESET_DETAILS = {
    0: "spreading factor 11, bandwidth 250 kHz, coding rate 4/5",
    1: "spreading factor 12, bandwidth 125 kHz, coding rate 4/8",
    2: "spreading factor 12, bandwidth 62.5 kHz, coding rate 4/8",
    3: "spreading factor 10, bandwidth 250 kHz, coding rate 4/5",
    4: "spreading factor 9, bandwidth 250 kHz, coding rate 4/5",
    5: "spreading factor 8, bandwidth 250 kHz, coding rate 4/5",
    6: "spreading factor 7, bandwidth 250 kHz, coding rate 4/5",
    7: "spreading factor 11, bandwidth 125 kHz, coding rate 4/8",
    8: "spreading factor 7, bandwidth 500 kHz, coding rate 4/5",
}
REGION_HINT = "The radio band for the country you are in. Every node on your mesh uses the same one."
PRESET_HINT = "How far and how fast the radio talks. Every node on your mesh must use the same preset."
POWER_HINT = "In dBm. 0 means the highest power allowed in your region."
POWER_ERROR = "Enter a number from 0 to 30."
HOPS_HINT = "How many times other nodes pass your messages on, 1 to 7. Fewer keeps the mesh quieter."
HOPS_ERROR = "Enter a number from 1 to 7."
TRANSMIT_HINT = "Off makes your node listen only: nothing you send leaves it."
# Linux only: the LoRa back cover is qualified at 0 dBm, and its node's service caps it there
# (meshsat-lora-backplate docs/INSTALL.md, SX126X_MAX_POWER), whatever the setting says.
COVER_POWER = "0 dBm (1 mW), capped"
COVER_POWER_HINT = ("The LoRa back cover sends at 0 dBm, the one power it is qualified at: it has a plain crystal, which drifts as the amplifier heats, and above "
                    "that the frames arrive damaged. The node's service caps it there, whatever is set here.")
RADIO_CONFIRM = "Apply these radio settings?"
REGION_OR_PRESET = "Changing the region or preset can cut you off from other nodes until they change too."
TRANSMIT_OFF = "With transmit off, nothing you send reaches the mesh, and other nodes stop hearing your node."


def region_label(code: int) -> str:
    if code == UNSET:
        return "Not set"
    return REGION_NAMES.get(code, f"Region code {code}")


def preset_label(code: int) -> str:
    return PRESET_NAMES.get(code, f"Preset code {code}")


def region_options() -> list:
    """The region picker: every region but Unset, (code, label, detail)."""
    return [(code, label, "") for code, label in REGIONS if code != UNSET]


def preset_options() -> list:
    return [(code, label, "") for code, label in PRESETS]


def is_custom(lora: dict, preset_picked: bool) -> bool:
    return not lora.get("use_preset") and not preset_picked


def preset_button(lora: dict, preset: int, preset_picked: bool) -> str:
    return "Custom settings" if is_custom(lora, preset_picked) else preset_label(preset)


def preset_details(lora: dict, preset: int, preset_picked: bool) -> str:
    if is_custom(lora, preset_picked):
        return (f"Custom: spreading factor {lora.get('spread_factor', 0)}, bandwidth {lora.get('bandwidth', 0)} kHz, "
                f"coding rate 4/{lora.get('coding_rate', 0)}. Picking a preset replaces these.")
    details = PRESET_DETAILS.get(preset)
    if details is None:
        return "This app does not know the details of this preset."
    return f"{preset_label(preset)}: {details}. Radios on 2.4 GHz use wider bandwidths."


def digits(value: str, limit: int) -> str:
    """What a number field keeps of what was typed: digits only, at most `limit` of them."""
    return "".join(ch for ch in value if ch.isdigit())[:limit]


def _int(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def power_ok(text: str, lora: dict) -> bool:
    """Whatever the radio reported is accepted as it is; a new value must be in range."""
    power = _int(text)
    return power is not None and (0 <= power <= 30 or power == int(lora.get("tx_power", 0)))


def hops_ok(text: str, lora: dict) -> bool:
    hops = _int(text)
    return hops is not None and (1 <= hops <= 7 or hops == int(lora.get("hop_limit", 0)))


def radio_changes(lora: dict, region: int, preset: int, preset_picked: bool, power_text: str, hops_text: str, transmit: bool) -> dict:
    """The fields of the LoRa section a person changed, as the body's config names them."""
    out = {}
    if region != int(lora.get("region", 0)):
        out["region"] = region
    if preset_picked and (preset != int(lora.get("modem_preset", 0)) or not lora.get("use_preset")):
        out["modem_preset"] = preset
        out["use_preset"] = True
    if power_ok(power_text, lora) and _int(power_text) != int(lora.get("tx_power", 0)):
        out["tx_power"] = _int(power_text)
    if hops_ok(hops_text, lora) and _int(hops_text) != int(lora.get("hop_limit", 0)):
        out["hop_limit"] = _int(hops_text)
    if bool(transmit) != bool(lora.get("tx_enabled")):
        out["tx_enabled"] = bool(transmit)
    return out


def radio_consequences(lora: dict, changes: dict) -> list:
    """Why Apply asks first: an empty list applies at once."""
    out = []
    if "region" in changes or "modem_preset" in changes:
        out.append(REGION_OR_PRESET)
    if lora.get("tx_enabled") and changes.get("tx_enabled") is False:
        out.append(TRANSMIT_OFF)
    return out


def section_body(section: str, changes: dict) -> dict:
    """POST /api/config/radio."""
    return {"section": section, "config": dict(changes)}


# RegionCheck: whether a region fits the country the phone is in. Only ever a warning.
EUROPE = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI",
          "ES", "SE", "IS", "LI", "NO", "CH", "GB", "AD", "MC", "SM", "VA", "GI", "FO", "IM", "JE", "GG", "AL", "BA", "ME", "MK", "RS", "XK", "MD"}
EXPECTED = {"US": (1,), "CA": (1,), "PR": (1,), "AU": (6,), "NZ": (6, 11), "CN": (4,), "JP": (5,), "KR": (7,), "TW": (8,), "RU": (9,), "IN": (10,),
            "TH": (12,), "UA": (15, 14), "MY": (17, 16), "SG": (18,)}
# The names Android's Locale gives these countries in English (getDisplayCountry).
COUNTRIES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia", "FI": "Finland",
    "FR": "France", "DE": "Germany", "GR": "Greece", "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia", "LT": "Lithuania", "LU": "Luxembourg",
    "MT": "Malta", "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
    "IS": "Iceland", "LI": "Liechtenstein", "NO": "Norway", "CH": "Switzerland", "GB": "United Kingdom", "AD": "Andorra", "MC": "Monaco", "SM": "San Marino",
    "VA": "Vatican City", "GI": "Gibraltar", "FO": "Faroe Islands", "IM": "Isle of Man", "JE": "Jersey", "GG": "Guernsey", "AL": "Albania",
    "BA": "Bosnia & Herzegovina", "ME": "Montenegro", "MK": "North Macedonia", "RS": "Serbia", "XK": "Kosovo", "MD": "Moldova", "US": "United States",
    "CA": "Canada", "PR": "Puerto Rico", "AU": "Australia", "NZ": "New Zealand", "CN": "China", "JP": "Japan", "KR": "South Korea", "TW": "Taiwan",
    "RU": "Russia", "IN": "India", "TH": "Thailand", "UA": "Ukraine", "MY": "Malaysia", "SG": "Singapore",
}


def expected_regions(iso: str):
    """The region codes radios in `iso` normally use, or None when this app does not know."""
    if iso in EUROPE:
        return (3, 2)
    return EXPECTED.get(iso)


def phone_country(env=None, sim_iso: str = "") -> str | None:
    """The phone's country as an upper-case ISO code: the SIM's when there is one, else the
    territory of the language settings (en_GB.UTF-8 gives GB); None when neither tells.
    MESHSAT_APP_COUNTRY overrides both (the tests)."""
    env = os.environ if env is None else env
    override = env.get("MESHSAT_APP_COUNTRY", "")
    if override:
        return override.upper() if len(override) == 2 else None
    if sim_iso and len(sim_iso) == 2:
        return sim_iso.upper()
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = env.get(key, "")
        if value:
            territory = value.split(".")[0].split("@")[0]
            if "_" in territory:
                code = territory.split("_", 1)[1]
                return code.upper() if len(code) == 2 and code.isalpha() else None
            return None
    return None


def region_warning(code: int, iso) -> str | None:
    """A warning about the region for the phone's country, or None when it fits or cannot be judged."""
    if code == LORA_24:
        return None  # 2.4 GHz is allowed worldwide
    if code == UNSET:
        return "No region is set, so the radio does not transmit. Pick the region you are in."
    if not iso:
        return None
    expected = expected_regions(iso)
    if expected is None or code in expected:
        return None
    names = " or ".join(REGION_NAMES[c] for c in expected)
    return (f"Your phone is set to {COUNTRIES.get(iso, iso)}, where radios use {names}. Check the region matches where you are: the wrong one can be illegal "
            "there, and you will not hear nearby nodes.")


# ── Channels ─────────────────────────────────────────────────────────────────────────────────
CHANNELS_HINT = "Nodes hear each other on a channel when they share its name and key."
ROLES = {1: "Main channel", 2: "Extra channel", 0: "Off"}
ROLE_HINTS = {1: "Every node on this mesh shares it.", 2: "A group channel beside the main one.", 0: "Not in use."}
ROLE_WIRE = {1: "PRIMARY", 2: "SECONDARY", 0: "DISABLED"}
# The Bridge names a channel's key in a word and never gives the key (MESHSAT-1405).
KEYS = {
    "main": ("Channel key: same as the main channel", "It is as private as the main channel."),
    "none": ("Channel key: none (not encrypted)", "Anyone in range can read it."),
    "default": ("Channel key: default (not private)", "Every Meshtastic radio knows this key, so anyone can read it."),
    "private": ("Channel key: private", "Only nodes that have this key can read it."),
}
CHANNEL_NAME_MAX = 11
CHANNEL_ZERO = "Channel 0 is always the main channel."
UPLINK_HINT = "Copies this channel's messages to an internet server when the node has internet."
DOWNLINK_HINT = "Brings messages from that server onto this channel."
CHANGE_CHANNEL_BODY = "Changing a channel's name or role can cut you off from nodes that still use the old one until they change too."


def role_label(role: int) -> str:
    return ROLES.get(int(role or 0), "Off")


def role_hint(role: int) -> str:
    return ROLE_HINTS.get(int(role or 0), "Not in use.")


def channel_name(channel: dict) -> str:
    return channel.get("name") or ("Default name" if int(channel.get("role", 0)) == 1 else "No name")


def channel_role_line(channel: dict) -> str:
    return f"{role_label(channel.get('role', 0))}. {role_hint(channel.get('role', 0))}"


def channel_key(channel: dict) -> tuple:
    return KEYS.get(channel.get("key") or "none", KEYS["none"])


def mqtt_line(channel: dict) -> str:
    parts = [label for key, label in (("uplink_enabled", "Send to MQTT"), ("downlink_enabled", "Receive from MQTT")) if channel.get(key)]
    return ", ".join(parts)


def role_options(channel: dict) -> list:
    """Channel 0 is always the main channel, and there is only one: the picker cannot break that."""
    out = []
    if int(channel.get("role", 0)) == 1:
        out.append((1, role_label(1), ""))
    out.append((2, role_label(2), ""))
    out.append((0, role_label(0), ""))
    return out


def channel_needs_asking(original: dict, name: str, role: int) -> bool:
    role_changed = role != int(original.get("role", 0))
    renamed_in_use = name != (original.get("name") or "") and int(original.get("role", 0)) != 0
    return role_changed or renamed_in_use


def channel_body(original: dict, name: str, role: int, uplink: bool, downlink: bool) -> dict:
    """POST /api/channels: never a key (the Bridge keeps the node's own), the role of channel 0
    as it is."""
    index = int(original.get("index", 0))
    if index == 0:
        role = int(original.get("role", 1))
    return {"index": index, "name": name.strip(), "role": ROLE_WIRE.get(role, "DISABLED"), "uplink_enabled": bool(uplink), "downlink_enabled": bool(downlink)}


# ── Position ─────────────────────────────────────────────────────────────────────────────────
FIXED_HINT = "Use a position set by hand instead of the GPS."
SHARING_HINT = "How often the node shares its position, in seconds. 0 uses the default, 15 minutes."
SECONDS_ERROR = "Enter a number of seconds."
SMART_HINT = "Shares sooner when the node moves."


def position_changes(position: dict, gps: bool, fixed: bool, seconds_text: str, smart: bool) -> dict:
    out = {}
    if bool(gps) != bool(position.get("gps_enabled")):
        out["gps_enabled"] = bool(gps)
    if bool(fixed) != bool(position.get("fixed_position")):
        out["fixed_position"] = bool(fixed)
    secs = _int(seconds_text)
    if secs is not None and secs != int(position.get("position_broadcast_secs", 0)):
        out["position_broadcast_secs"] = secs
    if bool(smart) != bool(position.get("position_broadcast_smart_enabled")):
        out["position_broadcast_smart_enabled"] = bool(smart)
    return out


# ── Bluetooth ────────────────────────────────────────────────────────────────────────────────
PAIRING = {0: "PIN shown on the node's screen", 1: "Fixed PIN", 2: "No PIN"}
BLUETOOTH_HINT = "This is how your phone talks to the node."
NO_PIN_HINT = "Anyone nearby can pair with the node."
PIN_ERROR = "Enter 6 digits."
BLUETOOTH_OFF = "Turn off Bluetooth?"
BLUETOOTH_OFF_BODY = ("You will lose the connection to this node from the phone, and with it the satellite modem. "
                      "Turning it back on then needs the node itself or a USB cable.")
NO_BLUETOOTH = "This node has no Bluetooth."


def pairing_label(mode: int) -> str:
    return PAIRING.get(int(mode), f"Pairing mode {mode}")


def pairing_options() -> list:
    return [(mode, pairing_label(mode), "") for mode in (0, 1, 2)]


def pin_text(bluetooth: dict) -> str:
    pin = int(bluetooth.get("fixed_pin", 0))
    return f"{pin:06d}" if pin else ""


def pin_ok(mode: int, text: str) -> bool:
    return mode != 1 or (len(text) == 6 and text.isdigit())


def bluetooth_changes(bluetooth: dict, enabled: bool, mode: int, pin: str) -> dict:
    out = {}
    if bool(enabled) != bool(bluetooth.get("enabled")):
        out["enabled"] = bool(enabled)
    if int(mode) != int(bluetooth.get("mode", 0)):
        out["mode"] = int(mode)
    if mode == 1 and pin_ok(mode, pin) and int(pin) != int(bluetooth.get("fixed_pin", 0)):
        out["fixed_pin"] = int(pin)
    return out


# ── WiFi ─────────────────────────────────────────────────────────────────────────────────────
NO_WIFI = "This node has no WiFi."
WIFI_HINT = "Lets the node reach the internet, for MQTT, when a network is in range."
SSID_MAX = 32
PSK_MAX = 64


def wifi_changes(network: dict, enabled: bool, ssid: str, psk: str) -> dict:
    out = {}
    if bool(enabled) != bool(network.get("wifi_enabled")):
        out["wifi_enabled"] = bool(enabled)
    if ssid != (network.get("wifi_ssid") or ""):
        out["wifi_ssid"] = ssid
    if psk != (network.get("wifi_psk") or ""):
        out["wifi_psk"] = psk
    return out


# Linux only: with the LoRa back cover the node runs on this phone, and the phone's own
# network is its network; its WiFi and Bluetooth settings do nothing there.
COVER_NO_WIFI = "The node runs on this phone and uses the phone's own network, so it has no WiFi of its own."
COVER_NO_BLUETOOTH = "The node runs on this phone, so it has no Bluetooth of its own: the app reaches it inside the phone."


# ── Restart and reset ────────────────────────────────────────────────────────────────────────
CLOCK_HINT = "Sets the node's clock to the phone's time."
RESTART_HINT = "Restarts the node after a delay. The phone reconnects by itself."
SWITCH_OFF_HINT = "Switches the node off. Someone has to switch it on again at the node."
CANNOT_SWITCH_OFF = "This node cannot switch itself off."
FORGET_HINT = "Clears the node's list of the nodes it has heard. They come back as they transmit again."
ERASE_HINT = "Erases every setting on the node and restores the factory ones. This cannot be undone."
ERASE_TITLE = "Erase every setting on your node?"
ERASE_BODY = ("Its region, channels, keys and name go back to the factory ones and it restarts. "
              "It will no longer hear your mesh until it is set up again, and the phone may have to pair "
              "with it again. This cannot be undone.")
ERASE_SENT = "Sent to the radio. It erases its settings and restarts."
SWITCH_OFF_TITLE = "Switch off your node?"
SWITCH_OFF_BODY = "The phone loses the connection to it, and with it the mesh and the satellite modem, until someone switches it on again at the node."
SWITCH_OFF_SENT = "Sent to the radio. It switches off in 5 seconds."
FORGET_TITLE = "Forget heard nodes?"
FORGET_BODY = "Your node clears its list of the nodes it has heard. They come back as they transmit again."


def restart_delay(text: str) -> int:
    value = _int(text)
    return value if value is not None else 5


def restart_body(seconds: int, cover: bool = False) -> str:
    """Android's words; with the back cover the satellite modem is on the phone's USB, not
    behind the node, so it stays."""
    if cover:
        return f"In {seconds} seconds the phone loses the node and the mesh until the node is back, usually within a minute. The phone reconnects by itself."
    return (f"In {seconds} seconds the phone loses the node, the mesh and the satellite modem until the node is back, usually within a minute. "
            "The phone reconnects by itself.")


def restart_sent(seconds: int) -> str:
    return f"Sent to the radio. It restarts in {seconds} seconds."
