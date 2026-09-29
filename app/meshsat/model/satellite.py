# SPDX-License-Identifier: GPL-3.0-or-later
"""The satellite mailbox check in MeshSat Android's words (ui/components/CheckMailboxButton.kt):
a check opens a billed Iridium session, so it is asked about first."""

CHECK_MAILBOX = "Check Mailbox"
CHECKING = "Checking mailbox..."
CONFIRM_TITLE = "Check the satellite mailbox?"
CONFIRM_TEXT = "This opens an Iridium session, which can take up to 90 seconds. It uses at least 1 credit, even when no message is waiting. A message waiting to be sent goes out in the same session."  # noqa: E501
CHECK = "Check"
CANCEL = "Cancel"

# ── The Satellite page (SettingsScreen.kt:528-733), for the RockBLOCK 9603 on USB-C: Android's
# card words where they fit a modem on the phone's own port, this edition's where Android's
# name the node's pipe or an HC-05 ────────────────────────────────────────────────────────────
USB_TITLE = "Satellite modem on USB-C"
USB_NOTE = "A RockBLOCK 9603 on the phone's USB-C port, through a USB adapter. The Bridge finds it by itself."
POLL_SIGNAL = "Poll Signal"
IMT_TITLE = "RockBLOCK 9704 (separate modem)"
IMT_FOLD = "Using a RockBLOCK 9704 instead? Set it up"
IMT_PLUG = "Plug a RockBLOCK 9704 into USB-C. The Bridge finds it by itself."
DISCONNECT = "Disconnect"
STATUS = "Status"


def _has_port(modem: dict) -> bool:
    return (modem or {}).get("port") not in ("", "supervisor", None)


def usb_status(bridge_up: bool, modem: dict | None, bars: int) -> tuple:
    """(the Status row's words, connected): Green "Connected (Signal: N/5)" or TextMuted."""
    modem = modem or {}
    if not bridge_up:
        return "Connect your node first.", False
    if modem.get("connected"):
        return f"Connected (Signal: {int(bars or 0)}/5)", True
    if _has_port(modem):
        if modem.get("silent"):
            return "The modem does not answer (still trying)", False
        return "Checking the modem...", False
    return "No modem on this radio. Plug a RockBLOCK into USB-C.", False


def usb_rows(modem: dict | None) -> list:
    """InfoRows while connected: Manufacturer, Model, IMEI, each only when the modem said it."""
    modem = modem or {}
    if not modem.get("connected"):
        return []
    return [(k, str(modem.get(f) or "")) for k, f in (("Manufacturer", "manufacturer"), ("Model", "model"), ("IMEI", "imei")) if str(modem.get(f) or "").strip()]


def imt_used(modem: dict | None) -> bool:
    """The 9704's card unfolds by itself once a 9704 is there (Android: once one was connected)."""
    return bool(modem) and (bool(modem.get("connected")) or _has_port(modem))


def imt_status(modem: dict | None, bars: int) -> tuple:
    modem = modem or {}
    if modem.get("connected"):
        return f"Ready (Signal: {int(bars or 0)}/5)", True
    if _has_port(modem):
        return "Connecting...", False
    return "Disconnected", False


def imt_rows(modem: dict | None) -> list:
    modem = modem or {}
    if not modem.get("connected"):
        return []
    return [(k, str(modem.get(f) or "")) for k, f in (("IMEI", "imei"), ("Serial", "serial"), ("Firmware", "firmware")) if str(modem.get(f) or "").strip()]


def signal_toast(body, prefix: str = "") -> str | None:
    """"Signal: N/5" ("9704 Signal: N/5") from a reading, or None when there is none."""
    if isinstance(body, dict) and body.get("bars") is not None:
        return f"{prefix}Signal: {int(body['bars'])}/5"
    return None


# ── The node's own modem (SettingsScreen.kt:528-629, ble/NodeStatsText.kt, bt/IridiumSpp.kt:101-122),
# read from the Bridge's pipe to the node (Bridge change B9) ─────────────────────────────────────
NODE_TITLE = "Satellite modem on the node"
USE_NODE_MODEM = "Use the node's modem"
NO_NODE_NOTE = "The RockBLOCK 9603 is reached through your MeshSat node. Connect the node under Your MeshSat node; its modem appears here."  # noqa: E501
HEALTH_TITLE = "Node health"
HEALTH_WAITING = "Waiting for the node's report."
HEALTH_NOTE = "What the node reports about its own modem, whoever holds it. The signal here is information, never a reason to hold a send."  # noqa: E501
MO_LINK_LOST = -1
MO_WORDS = {MO_LINK_LOST: "the link to the node dropped during the session", 10: "the gateway did not finish the call in time",
            11: "the modem's outgoing queue is full", 12: "the message has too many segments", 13: "the session did not complete",
            14: "the segment size is invalid", 15: "the gateway denied access", 16: "the modem is locked", 17: "the gateway did not answer",
            18: "the radio link dropped", 19: "the link failed", 32: "no network service", 33: "antenna fault", 34: "the radio is switched off",
            35: "the modem is busy", 36: "the gateway asked to try again later", 37: "satellite messaging is paused by the network",
            38: "the network is limiting traffic"}


def mo_status_text(code: int) -> str:
    """IridiumSpp.moStatusText: what an +SBDIX MO status means."""
    if 0 <= code <= 4:
        return "sent"
    return MO_WORDS.get(code, "failed")


def stats_ago(seconds: int) -> str:
    """NodeStatsText.ago."""
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return f"{seconds} s ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86_400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86_400} d ago"


def stats_duration(seconds: int) -> str:
    """NodeStatsText.duration."""
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86_400:
        return f"{seconds // 3600} h {(seconds % 3600) // 60} min"
    return f"{seconds // 86_400} d {(seconds % 86_400) // 3600} h"


def node_stats_rows(s: dict) -> list:
    """NodeStatsText.rows, from the Bridge's decoded STATS (GET /api/mesh/ble/satellite/stats):
    [(label, value)] in Android's order."""
    flags = s.get("flags") or {}
    owner = {"phone": "Held by this phone", "node": "Used by the node", "none": "Free"}.get(s.get("owner") or "", "Unknown owner")
    rows = [("Modem", owner + (", answers" if flags.get("modem_answers") else ", not answering"))]
    if flags.get("session_in_flight"):
        rows.append(("Session", "In flight now"))
    csq = s.get("csq")
    if csq is None:
        rows.append(("Signal", "Never read"))
    else:
        age = s.get("csq_age_s")
        rows.append(("Signal", f"{csq} of 5" + (f", {stats_ago(age)}" if age is not None else "")))
    rows.append(("Sessions since boot", str(s.get("sessions") or 0)))
    mo = s.get("last_mo_status")
    if mo is None:
        rows.append(("Last session", "None yet"))
    else:
        age = s.get("last_session_age_s")
        rows.append(("Last session", f"MO {mo}, {mo_status_text(mo)}, MOMSN {s.get('last_momsn') or 0}" + (f", {stats_ago(age)}" if age is not None else "")))
    queued = int(s.get("last_mt_queued") or 0)
    if queued > 0:
        rows.append(("Gateway", f"{queued} waiting at the gateway"))
    elif flags.get("message_waiting"):
        rows.append(("Gateway", "A message is waiting at the gateway"))
    cap, own = int(s.get("day_sessions_cap") or 0), int(s.get("node_sessions") or 0)
    if cap > 0 or own > 0:
        rows.append(("Node's own routing", f"{int(s.get('day_sessions_used') or 0)} of {cap} sessions today, sent {int(s.get('node_sent') or 0)}, "
                                           f"received {int(s.get('node_received') or 0)}"))
    rows.append(("Node uptime", stats_duration(int(s.get("uptime_s") or 0))))
    if int(s.get("watchdog_reboots") or 0) > 0:
        rows.append(("Bluetooth watchdog reboots", str(s["watchdog_reboots"])))
    if int(s.get("client_bytes_dropped") or 0) > 0:
        rows.append(("Bytes the node could not take", str(s["client_bytes_dropped"])))
    return rows


def node_stats_warning(s: dict) -> str | None:
    """NodeStatsText.warning."""
    flags = s.get("flags") or {}
    if flags.get("buffer_congested"):
        return "The node's incoming buffer is nearly full: the phone writes faster than the modem takes."
    if not flags.get("modem_answers"):
        return "The node's modem is not answering AT commands."
    return None


def node_status(ble: dict | None, modem: dict | None, bars: int) -> tuple:
    """The node card's Status row, first match (SettingsScreen.kt:533-543): (words, connected)."""
    ble, modem = ble or {}, modem or {}
    if modem.get("connected"):
        return f"Connected (Signal: {int(bars or 0)}/5)", True
    if _has_port(modem) and modem.get("silent"):
        return "The node's modem does not answer (still trying)", False
    if _has_port(modem):
        return "Checking the modem...", False
    if ble.get("satellite_enabled") is False:
        return "Off: the node keeps its modem", False
    if not ble.get("satellite_pipe"):
        return "No MeshSat node connected", False
    if ble.get("satellite_owner") == "node":
        return "The node is using its modem", False
    return "Waiting for the node", False
