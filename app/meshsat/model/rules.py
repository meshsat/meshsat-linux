# SPDX-License-Identifier: GPL-3.0-or-later
"""Routing rules' words and records (ui/screens/RulesScreen.kt): which tab a rule is listed
under, what its card says, what the editor offers and checks, and the record a save writes
(the Bridge's PUT replaces every column, so the record is the rule itself with the editor's
fields over it, as Android's base.copy). Pure: no GTK, no Bridge."""
import json
import re

from . import words

TABS = ("From mesh", "Into mesh", "Between links", "Deliveries", "Queue")
RULE_TABS = TABS[:3]
INTRO = "Rules decide which messages are passed from one link to another."
SUBTITLES = {
    "From mesh": "What happens to messages heard on the mesh.",
    "Into mesh": "Messages from satellite, SMS or the Hub that are passed into the mesh.",
    "Between links": "Messages from satellite, SMS or the Hub that go to another link, or are stopped or only logged.",
}
EMPTY = {
    "From mesh": "No rules for mesh messages yet, so they stay on the mesh. Tap + to add one.",
    "Into mesh": "No rules pass messages into the mesh yet. Tap + to add one.",
    "Between links": "No rules between the other links yet. Tap + to add one.",
}
ADD = "Add rule"
ACTIONS = ("forward", "drop", "log")
ACTION_HELP = {"forward": "Pass it on to another link.", "drop": "Stop it. It is not passed on, whatever other rules say.", "log": "Only count the match. Other rules still decide what happens."}
GUARANTEES = ("0", "1", "2")
GUARANTEE_HELP = "Try once gives up after one failed attempt. Keep trying retries until it goes out."
HUB_DUPLICATE_WARNING = ("The Hub already receives satellite messages straight from the provider. This rule sends a second copy, so anything the Hub does "
                         "with them - alerts, TAK, webhooks - happens twice.")
NAME_ERROR = "Give the rule a name so you can find it later."
TARGET_ERROR = "Pick a different link from the one it arrives by."
NO_LIMIT = "No limit. Fill in both boxes to set one, for example 5 messages every 60 seconds."
TOAST_ADDED, TOAST_SAVED, TOAST_DELETED = "Rule added", "Rule saved", "Rule deleted"
FALLBACK_LINKS = ("mesh_0", "iridium_0", "sms_0")
# The Hub reporter's own links, hub_0, hub_1: deliberately not hub_relay, a tunnel to another
# bridge that puts nothing in the Hub's message store.
HUB_REPORT_LINK = re.compile(r"hub_\d+")


def tab_of(rule: dict) -> str:
    """The tab a rule is listed under. Every rule lands on exactly one tab, whatever its action or
    direction, so a Drop or Log only rule never vanishes once saved."""
    if (rule.get("interface_id") or "").startswith("mesh"):
        return "From mesh"
    if (rule.get("forward_to") or "").startswith("mesh"):
        return "Into mesh"
    return "Between links"


def by_tab(rules: list) -> dict:
    out = {tab: [] for tab in RULE_TABS}
    for rule in rules:
        out[tab_of(rule)].append(rule)
    return out


def badges(rules: list, queue_count: int) -> dict:
    counts = {tab: len(items) for tab, items in by_tab(rules).items()}
    counts["Deliveries"] = 0
    counts["Queue"] = queue_count
    return counts


def link_choices(all_links: list, keep: str) -> list:
    """The links a rule can name: the ones this phone is set up to use, plus `keep`, the one a
    saved rule already names, so opening an old rule never blanks its field. A link that is
    switched off holds whatever is routed to it for ever, so offering it writes a rule that
    silently delivers nothing (MESHSAT-1281). `all_links`: (id, switched off) pairs."""
    return [id_ for id_, disabled in all_links if not disabled or id_ == keep]


def available_links(interfaces: list, keep: str = "") -> list:
    """The editor's choices from the Bridge's interfaces, with Android's fallback when the
    Bridge lists none."""
    ids = link_choices([(i.get("id", ""), not i.get("enabled", True)) for i in interfaces if i.get("id")], keep)
    return ids or list(FALLBACK_LINKS)


def duplicates_the_hub(source: str, destination: str) -> bool:
    """Whether a rule would hand the Hub something it already has (MESHSAT-1276): a RockBLOCK's
    own message reaches the Hub through the provider's webhook."""
    return bool(HUB_REPORT_LINK.fullmatch(destination or "")) and (source or "").startswith("iridium")


def action_label(action: str) -> str:
    low = (action or "").lower()
    return {"forward": "Forward", "drop": "Drop", "log": "Log only"}.get(low, (action[:1].upper() + action[1:]) if action else "")


def route_parts(rule: dict) -> list:
    """"Forward: Mesh to Satellite" as (text, lane) parts: the first part is the action (bold),
    a link's part carries its lane (its colour), the words between carry None."""
    parts = [(action_label(rule.get("action", "")) + ": ", "bold")]
    source = rule.get("interface_id") or ""
    target = rule.get("forward_to") or ""
    if rule.get("direction") == "egress":
        parts += [("messages leaving by ", None), (words.channel(source), words.channel_lane(source))]
    elif rule.get("action") == "forward" and target.strip():
        parts += [(words.channel(source), words.channel_lane(source)), (" to ", None), (words.channel(target), words.channel_lane(target))]
    else:
        parts += [("messages from ", None), (words.channel(source), words.channel_lane(source))]
    return parts


def route_text(rule: dict) -> str:
    return "".join(t for t, _ in route_parts(rule))


def rate_limit_text(per_window, window_seconds) -> str | None:
    """"At most 5 messages per minute", or None when the rule has no limit (both numbers are needed)."""
    try:
        per_window, window_seconds = int(per_window or 0), int(window_seconds or 0)
    except (TypeError, ValueError):
        return None
    if per_window <= 0 or window_seconds <= 0:
        return None
    per = "per minute" if window_seconds == 60 else f"per {words.count(window_seconds, 'second')}"
    return f"At most {words.count(per_window, 'message')} {per}"


def limit_helper(per_window, window_seconds) -> str:
    limit = rate_limit_text(per_window, window_seconds)
    return f"{limit}. Leave either box at 0 for no limit." if limit else NO_LIMIT


def urgency_helper(priority_text: str) -> str:
    try:
        priority = int(priority_text)
    except (TypeError, ValueError):
        priority = 10
    from .deliveries import urgency_label  # noqa: PLC0415

    return f"{urgency_label(priority)}. Lower numbers go first and are checked first; 0 never expires."


def json_list_text(raw) -> str:
    """A JSON array of ids or numbers as "a, b, c"; anything else as it is."""
    try:
        arr = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(arr, list):
            return ", ".join(str(v) for v in arr)
    except ValueError:
        pass
    return str(raw)


def _filters(rule: dict):
    raw = rule.get("filters")
    if isinstance(raw, dict):
        return raw
    raw = (raw or "").strip()
    if not raw or raw == "{}":
        return {}
    try:
        obj = json.loads(raw)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _present(value) -> bool:
    """A filter list that holds something: not empty, not "[]"."""
    if isinstance(value, list):
        return bool(value)
    return bool(value) and value != "[]"


def filter_summary(rule: dict) -> str:
    parts = []
    obj = _filters(rule)
    if obj:
        if obj.get("keyword"):
            parts.append(f"Contains “{obj['keyword']}”")
        if _present(obj.get("channels")):
            parts.append(f"Mesh channels {json_list_text(obj['channels'])}")
        if _present(obj.get("nodes")):
            parts.append(f"From nodes {json_list_text(obj['nodes'])}")
        if _present(obj.get("portnums")):
            parts.append(f"Message types {json_list_text(obj['portnums'])}")
    if rule.get("filter_node_group"):
        parts.append(f"Node group {rule['filter_node_group']}")
    if rule.get("filter_sender_group"):
        parts.append(f"Sender group {rule['filter_sender_group']}")
    if rule.get("filter_portnum_group"):
        parts.append(f"Message type group {rule['filter_portnum_group']}")
    return " · ".join(parts)


def name_of(rule: dict) -> str:
    return (rule.get("name") or "").strip() or f"Rule {rule.get('id', '')}"


def matches_text(rule: dict) -> str:
    matches = int(rule.get("match_count") or 0)
    return "No matches yet" if matches == 0 else words.count(matches, "match", "matches")


def meta_line(rule: dict, now: float) -> str:
    from .deliveries import guarantee_label, urgency_label  # noqa: PLC0415

    parts = [matches_text(rule)]
    last = words.stamp_epoch(rule.get("last_match_at"))
    if last:
        parts.append(f"last {words.ago(last, now)}")
    parts.append(rate_limit_text(rule.get("rate_limit_per_min"), rule.get("rate_limit_window")))
    qos = int(rule.get("qos_level", 1) or 0)
    if qos <= 0:
        parts.append(guarantee_label(qos))
    if int(rule.get("priority", 10) or 0) == 0:
        parts.append(urgency_label(0))
    return " · ".join(p for p in parts if p)


def switch_name(rule: dict) -> str:
    """The switch's accessible name, Android's contentDescription."""
    return f"Rule {name_of(rule)} is {'on' if rule.get('enabled') else 'off'}"


def delete_consequence(rule: dict) -> str:
    """What deleting the rule changes, in one sentence."""
    action = rule.get("action")
    if action == "forward":
        if (rule.get("forward_to") or "").strip():
            return f"Messages that matched it will no longer be forwarded to {words.channel(rule['forward_to'])}."
        return "Messages that matched it will no longer be forwarded."
    if action == "drop":
        return "Messages it stopped can get through again, if another rule passes them on."
    if action == "log":
        return "Its matches will no longer be counted. Messages are not affected."
    return "Messages that matched it will no longer be handled by it."


def delete_dialog(rule: dict) -> dict:
    return {"title": "Delete this rule?", "body": delete_consequence(rule) + " You cannot undo this.", "ok": "Delete", "cancel": "Keep it"}


# The editor
def keyword(rule: dict | None) -> str:
    """The keyword filter of a rule, or "" when it has none."""
    if not rule:
        return ""
    obj = _filters(rule)
    return str(obj.get("keyword", "")) if obj else ""


def merge_keyword_filter(existing, keyword_text: str) -> str:
    """The rule's filters with the keyword set (removed when blank). Every other filter (mesh
    channels, nodes, message types) is kept. Filters this code cannot read are kept as they are
    unless a keyword was typed. Written as Android's JSONObject does: no spaces."""
    raw = (existing or "").strip() if isinstance(existing, str) else json.dumps(existing or {}, separators=(",", ":"))
    if not raw:
        obj = {}
    else:
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                obj = None
        except ValueError:
            obj = None
    if obj is None:
        return raw if not keyword_text.strip() else json.dumps({"keyword": keyword_text}, separators=(",", ":"))
    if keyword_text.strip():
        obj["keyword"] = keyword_text
    else:
        obj.pop("keyword", None)
    return "{}" if not obj else json.dumps(obj, separators=(",", ":"))


def hidden_settings(rule: dict | None) -> list:
    """The settings of the rule that the editor does not show, which saving keeps."""
    if not rule:
        return []
    hidden = []
    obj = _filters(rule)
    if obj is None:
        hidden.append("filters this screen cannot read")
    elif obj:
        if _present(obj.get("channels")):
            hidden.append("mesh channels")
        if _present(obj.get("nodes")):
            hidden.append("nodes")
        if _present(obj.get("portnums")):
            hidden.append("message types")
    if rule.get("filter_portnum_group"):
        hidden.append("a message type group")
    options = (rule.get("forward_options") or "").strip() if isinstance(rule.get("forward_options"), str) else ""
    if options and options != "{}":
        hidden.append("forwarding options")
    return hidden


def hidden_note(hidden: list) -> str:
    return f"This rule also has settings this screen does not show ({', '.join(hidden)}). Saving keeps them." if hidden else ""


def defaults_for_tab(tab: str) -> tuple:
    """(arrives by, passed on by) for a new rule on this tab."""
    return {"From mesh": ("mesh_0", "iridium_0"), "Into mesh": ("iridium_0", "mesh_0"), "Between links": ("iridium_0", "sms_0")}.get(tab, ("mesh_0", "iridium_0"))


def editor_fields(rule: dict | None, tab: str) -> dict:
    """What the editor starts with: the rule's values, or a new rule's defaults for the tab."""
    interface_id, forward_to = defaults_for_tab(tab)
    rule = rule or {}
    return {
        "name": rule.get("name") or "",
        "interface_id": rule.get("interface_id") or interface_id,
        "forward_to": (rule.get("forward_to") or "").strip() or forward_to,
        "action": rule.get("action") or "forward",
        "enabled": bool(rule.get("enabled", True)),
        "qos_level": int(rule.get("qos_level", 1) if rule.get("qos_level") is not None else 1),
        "rate_limit_per_min": str(rule.get("rate_limit_per_min") or 0),
        "rate_limit_window": str(rule.get("rate_limit_window") or 0),
        "priority": str(rule.get("priority") if rule.get("priority") is not None else 10),
        "keyword": keyword(rule),
        "node_group": rule.get("filter_node_group") or "",
        "sender_group": rule.get("filter_sender_group") or "",
    }


def interface_label(rule: dict | None) -> str:
    return "When a message leaves by" if rule and rule.get("direction") == "egress" else "When a message arrives by"


def errors(fields: dict) -> tuple:
    """(the name's error, the target's error), None where there is none."""
    name_error = NAME_ERROR if not fields["name"].strip() else None
    bad_target = fields["action"] == "forward" and (not fields["forward_to"].strip() or fields["forward_to"] == fields["interface_id"])
    return name_error, (TARGET_ERROR if bad_target else None)


def _int(text, default: int) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def save_body(rule: dict | None, fields: dict) -> dict:
    """The record to write: the rule itself (so what the editor does not show, direction,
    message type group, forwarding options, survives a save) with the editor's fields over it.
    A new rule arrives by its link (direction ingress), with the Bridge's own defaults."""
    base = {"interface_id": fields["interface_id"], "direction": "ingress", "filters": "{}", "filter_portnum_group": None, "schedule_type": "none",
            "schedule_config": "", "forward_options": "{}"}
    if rule:
        for key in ("interface_id", "direction", "filters", "filter_portnum_group", "schedule_type", "schedule_config", "forward_options"):
            if key in rule:
                base[key] = rule[key]
    base.update({
        "interface_id": fields["interface_id"],
        "priority": _int(fields["priority"], 10),
        "name": fields["name"].strip(),
        "enabled": bool(fields["enabled"]),
        "action": fields["action"],
        "forward_to": fields["forward_to"] if fields["action"] == "forward" else "",
        "filters": merge_keyword_filter(rule.get("filters") if rule else None, fields["keyword"]),
        "filter_node_group": fields["node_group"].strip() or None,
        "filter_sender_group": fields["sender_group"].strip() or None,
        "qos_level": int(fields["qos_level"]),
        "rate_limit_per_min": _int(fields["rate_limit_per_min"], 0),
        "rate_limit_window": _int(fields["rate_limit_window"], 0),
    })
    return base


def record_key(rule: dict) -> tuple:
    return (rule.get("id"), rule.get("name"), rule.get("enabled"), rule.get("action"), rule.get("interface_id"), rule.get("forward_to"), rule.get("match_count"),
            rule.get("last_match_at"), rule.get("filters"), rule.get("filter_node_group"), rule.get("filter_sender_group"), rule.get("filter_portnum_group"),
            rule.get("rate_limit_per_min"), rule.get("rate_limit_window"), rule.get("qos_level"), rule.get("priority"))
