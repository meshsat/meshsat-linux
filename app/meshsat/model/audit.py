# SPDX-License-Identifier: GPL-3.0-or-later
"""The audit log's words (ui/screens/AuditScreen.kt): what each event is called, which way it
went, its colour, the check of the hash chain in plain words, and the copy "Save a copy"
writes. The Bridge keeps the log (/api/audit, /api/audit/verify, /api/audit/signer). Pure."""
import time

from . import words

VERIFY_WINDOW = 1000  # how many entries the Bridge checks by default
EXPORT_LIMIT = 100_000  # the most entries "Save a copy" writes out
PAGE = 100
FALLBACK_LINKS = ("mesh_0", "iridium_0", "sms_0")

CHECKING, CHECK = "Checking…", "Check the log"
SAVING, SAVE = "Saving…", "Save a copy"
SAVED, NOT_SAVED = "Audit log saved", "Could not save the audit log. Try another place."
KEY_COPIED = "Signing key copied"
OLDER = "Show older entries"

KNOWN = {"dispatch": "Queued", "deliver": "Sent", "delivered": "Sent", "forward": "Passed on", "drop": "Stopped", "deny": "Blocked", "denied": "Blocked",
         "reject": "Refused", "rejected": "Refused", "failover": "Switched to a backup link", "delivery_preempt": "Held back for a more urgent message",
         "sos_activated": "SOS started", "oob_command": "Remote command", "oob_reject": "Remote command refused", "oob_address_learn": "Learned a reply address",
         "oob_key_exported": "Remote control key exported", "connect": "Connected", "connected": "Connected", "disconnect": "Disconnected", "disconnected": "Disconnected"}


def event_label(event_type: str) -> str:
    """An audit event type (the Bridge's names, e.g. "dispatch", "oob_reject") in plain words."""
    t = (event_type or "").strip()
    known = KNOWN.get(t.lower())
    if known:
        return known
    plain = t.replace("_", " ").replace(".", " ").replace(":", " ").strip()
    return plain[:1].upper() + plain[1:] if plain else "Event"


def event_tone(event_type: str) -> str:
    low = (event_type or "").lower()
    if "forward" in low or "deliver" in low:
        return "green"
    if "deny" in low or "reject" in low:
        return "red"
    if "bind" in low or "connect" in low:
        return "blue"
    return "muted"


def direction_label(direction) -> str | None:
    """Which way a message went, from the direction field."""
    low = (direction or "").lower()
    if low in ("inbound", "in", "ingress", "rx"):
        return "received"
    if low in ("outbound", "out", "egress", "tx"):
        return "sent"
    return None


def links_offered(interfaces: list) -> list:
    """The links the filter offers: the ones the Bridge has, or the three every phone has."""
    ids = [i.get("id") for i in interfaces if i.get("id")]
    return ids or list(FALLBACK_LINKS)


def count_text(n: int) -> str:
    return words.count(n, "entry", "entries")


def signer_short(signer_id: str) -> str:
    return (signer_id or "")[:12] + "…"


def where_line(entry: dict) -> str:
    """Link and direction: "Satellite, received"."""
    iface = (entry.get("interface_id") or "").strip()
    link = words.channel(iface) if iface else None
    way = direction_label(entry.get("direction"))
    return ", ".join(p for p in (link, way) if p)


def refs_line(entry: dict, rule_names: dict) -> str:
    """Which message and which rule, by name where the rule still exists."""
    refs = []
    if entry.get("delivery_id") is not None:
        refs.append(f"Message #{entry['delivery_id']}")
    rule = entry.get("rule_id")
    if rule is not None:
        name = (rule_names.get(rule) or "").strip()
        refs.append(f"Rule “{name}”" if name else f"Rule #{rule}")
    return " · ".join(refs)


def time_text(entry: dict, now: float) -> str:
    """Stored in UTC; shown in the phone's time zone like every other screen."""
    at = words.stamp_epoch(entry.get("timestamp"))
    return words.local_stamp(at, now) if at else str(entry.get("timestamp") or "")


def empty_text(filtered: bool) -> str:
    return "Nothing in the audit log for this link." if filtered else "Nothing in the audit log yet."


def check_words(result: dict, entries_oldest_first: list | None = None) -> list:
    """The outcome of "Check the log" from the Bridge's /api/audit/verify: (text, style, tone)
    lines. The first changed entry is named by its number when the entries checked are at hand."""
    broken = int(result.get("broken_at", -1))
    valid = int(result.get("valid") or 0)
    if broken >= 0:
        number = None
        if entries_oldest_first and 0 <= broken < len(entries_oldest_first):
            number = entries_oldest_first[broken].get("id")
        where = f"The first changed entry is number {number}." if number is not None else \
            f"The first changed entry is {broken + 1} from the oldest of the last {VERIFY_WINDOW}."
        return [("The log was changed after it was written.", "body-medium", "red"),
                ("Save a copy and keep it, then contact your MeshSat admin.", "body-medium", "secondary"),
                (where, "body-small", "muted")]
    if valid == 0:
        return [("Nothing to check yet.", "body-medium", "secondary")]
    return [(f"The last {words.count(valid, 'entry', 'entries')} are as they were written.", "body-medium", "green")]


def export_name(now: float | None = None) -> str:
    return time.strftime("meshsat-audit-%Y%m%d-%H%M.txt", time.localtime(now if now is not None else time.time()))


def export_text(newest_first: list, signer_id: str | None, now: float | None = None) -> str:
    """The whole log as tab-separated text, oldest first, with the hashes that make it checkable."""
    now = time.time() if now is None else now
    saved = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    lines = ["MeshSat audit log", f"Saved: {saved}"]
    if signer_id:
        lines.append(f"Signing key: {signer_id}")
    lines += [f"Entries: {len(newest_first)}", "", "id\ttimestamp_utc\tinterface\tdirection\tevent\tdelivery_id\trule_id\tdetail\tprev_hash\thash"]
    for e in reversed(newest_first):
        detail = (e.get("detail") or "").replace("\t", " ").replace("\n", " ")
        lines.append("\t".join(str(v) for v in (e.get("id", ""), e.get("timestamp", ""), e.get("interface_id") or "", e.get("direction") or "", e.get("event_type", ""),
                                                   "" if e.get("delivery_id") is None else e["delivery_id"], "" if e.get("rule_id") is None else e["rule_id"],
                                                   detail, e.get("prev_hash", ""), e.get("hash", ""))))
    return "\n".join(lines) + "\n"
