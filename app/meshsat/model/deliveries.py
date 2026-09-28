# SPDX-License-Identifier: GPL-3.0-or-later
"""The message queue's words (ui/screens/DeliveryScreen.kt): every message on its way out, by
link, with what happened to it in plain words. Routing rules > Deliveries and > Queue are built
from the same parts, so a state, an urgency or a time reads the same on both screens. Pure
functions of the Bridge's delivery records (/api/deliveries), so the tests can hold every
word up against Android's."""
from . import words

# Statuses of a message that has not gone out yet, and of one that stopped without going out.
WAITING = frozenset(("queued", "retry", "held", "sending"))
GAVE_UP = frozenset(("failed", "dead", "expired", "denied", "cancelled"))
# A waiting message that can still be cancelled (one being sent cannot); a message that gave
# up and can be put back in the queue (what the Bridge's retry accepts).
CANCELLABLE = frozenset(("queued", "retry", "held"))
RETRYABLE = frozenset(("failed", "dead"))

# The state groups at the top of the list (LedgerGroup): the key is the status whose words name
# the group, the set is what it counts.
GROUPS = (
    ("queued", frozenset(("queued", "retry", "held"))),
    ("sending", frozenset(("sending",))),
    ("sent", frozenset(("sent", "delivered"))),
    ("failed", frozenset(("failed",))),
    ("dead", frozenset(("dead", "expired", "denied", "cancelled"))),
)

EMPTY = "No messages here yet. Messages you send, and messages your rules pass on, show up here."
NO_MATCH = "No messages match this filter."
ALL_LINKS = "All links"
QUEUE_INTRO = "Messages still waiting to go out, and messages that did not. Cancel one that is waiting, or retry one that gave up."
QUEUE_EMPTY = "Nothing is waiting, and nothing has failed."


def status(d: dict) -> str:
    return str(d.get("status") or "").lower()


def channel(d: dict) -> str:
    return d.get("channel") or ""


def link(d: dict) -> str:
    return words.channel(channel(d))


def can_cancel(d: dict) -> bool:
    return status(d) in CANCELLABLE


def can_retry(d: dict) -> bool:
    return status(d) in RETRYABLE


def is_satellite(channel_id: str) -> bool:
    return (channel_id or "").startswith("iridium")


def cancelled_by_user(d: dict) -> bool:
    """A message the user cancelled says so instead of "Gave up"."""
    return status(d) == "dead" and (d.get("last_error") or "") == "cancelled"


def state_text(d: dict) -> str:
    return words.delivery_state("cancelled" if cancelled_by_user(d) else status(d))


def state_tone(d: dict) -> str:
    return words.delivery_tone("cancelled" if cancelled_by_user(d) else status(d))


def urgency_label(priority) -> str:
    """How urgent a message is, from its priority number (lower goes first)."""
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        priority = 1
    return {0: "Critical", 1: "Normal"}.get(priority, "Low")


def guarantee_label(qos) -> str:
    """What the phone does when a send fails (QoS 0 has no retries; 1 and above retry)."""
    try:
        qos = int(qos)
    except (TypeError, ValueError):
        qos = 1
    if qos <= 0:
        return "Try once"
    if qos == 1:
        return "Keep trying"
    return "Keep trying (high)"


def problem_text(error) -> str:
    """The last error of a delivery, in plain words where the app wrote it itself."""
    e = (error or "").strip()
    if not e:
        return ""
    if e == "cancelled":
        return "You cancelled it."
    if e.startswith("cancelled: exceeded retry limit"):
        return "Stopped after too many tries."
    if e.startswith("TTL expired"):
        return "It waited too long and expired."
    # Two very different waits, and the queue used to read the same for both (MESHSAT-615): the
    # radio being out of reach is something a person can act on, a satellite that is not overhead is not.
    if e.startswith("Could not hand the message to the modem"):
        return "The phone cannot reach the node's radio. It is waiting for the radio, not for a satellite."
    if "no network service" in e:
        return "The satellite modem found no network. It is waiting for a satellite to come over."
    if e == "egress rules denied":
        return "A rule on this link blocked it."
    if e == "recovered after restart":
        return "The app restarted while sending it, so it is tried again."
    return e[:1].upper() + e[1:]


def ack_text(ack) -> str:
    """Whether the other end confirmed the message."""
    low = (ack or "").lower()
    return {"pending": "Waiting for confirmation", "acked": "Confirmed received", "nacked": "Refused by the other end", "timeout": "No confirmation came back"}.get(
        low, (ack[:1].upper() + ack[1:]) if ack else "")


def tries_text(d: dict) -> str | None:
    """"Retried 2 of 3 times", or None before the first retry."""
    retries = int(d.get("retries") or 0)
    if retries <= 0:
        return None
    max_retries = int(d.get("max_retries") or 0)
    if max_retries > 0:
        return f"Retried {retries} of {max_retries} times"
    return f"Retried {words.count(retries, 'time')}"


def group_label(key: str) -> str:
    return words.delivery_state(key)


def group_counts(deliveries: list) -> dict:
    return {key: sum(1 for d in deliveries if status(d) in statuses) for key, statuses in GROUPS}


def channels(deliveries: list) -> list:
    return sorted({channel(d) for d in deliveries})


def filtered(deliveries: list, group: str | None, channel_id: str | None) -> list:
    statuses = dict(GROUPS).get(group) if group else None
    return [d for d in deliveries if (statuses is None or status(d) in statuses) and (channel_id is None or channel(d) == channel_id)]


def empty_text(deliveries: list) -> str:
    return EMPTY if not deliveries else NO_MATCH


def created_epoch(d: dict):
    return words.stamp_epoch(d.get("created_at"))


def updated_epoch(d: dict):
    return words.stamp_epoch(d.get("updated_at"))


def card_meta(d: dict, now: float) -> str:
    parts = [words.ago(created_epoch(d) or 0, now)]
    if int(d.get("priority") or 0) == 0 and "priority" in d:
        parts.append(urgency_label(0))
    parts.append(tries_text(d))
    if d.get("ack_status"):
        parts.append(ack_text(d["ack_status"]))
    return " · ".join(p for p in parts if p)


def problem_line(d: dict) -> tuple:
    """(the problem in words, its tone): nothing for a message that went; red when it gave up
    by itself, muted while it waits or when the user cancelled it."""
    if status(d) in ("sent", "delivered"):
        return "", "muted"
    problem = problem_text(d.get("last_error"))
    tone = "red" if status(d) in GAVE_UP and not cancelled_by_user(d) else "muted"
    return problem, tone


def request_dialog(d: dict, retry: bool) -> dict:
    """Retry (True) or cancel (False) one delivery: the question, always asked first."""
    name = link(d)
    if retry:
        if is_satellite(channel(d)):
            return {"title": "Retry by satellite?", "body": "Each satellite attempt that gets through uses at least 1 credit. The message goes back in the queue and is sent at the next chance.",
                    "ok": "Retry", "cancel": "Not now"}
        if channel(d).startswith("sms"):
            return {"title": "Send again by SMS?", "body": "Your carrier may charge for the text. The message goes back in the queue and is sent when SMS is working.", "ok": "Retry", "cancel": "Not now"}
        return {"title": f"Send again by {name}?", "body": f"The message goes back in the queue and is sent when {name} is working.", "ok": "Retry", "cancel": "Not now"}
    return {"title": "Cancel this message?", "body": f"It will not be sent by {name}. You can retry it later from the queue.", "ok": "Cancel message", "cancel": "Keep it"}


def applied_text(d: dict, retry: bool, changed: bool = True) -> str:
    """What to tell the user once the Bridge has done it."""
    name = link(d)
    if retry:
        return f"Back in the queue for {name}"
    return f"Cancelled. It will not be sent by {name}." if changed else "Nothing to cancel: it has already been sent or stopped."


def failed_text(error) -> str:
    return f"That did not work: {error or 'unknown error'}"


def facts(d: dict, now: float) -> list:
    """The details dialog's plain rows: (label, value, tone)."""
    out = [("Status", state_text(d), state_tone(d)), ("Urgency", urgency_label(d.get("priority", 1)), None)]
    created = created_epoch(d)
    out.append(("Added", f"{words.ago(created or 0, now)}, {words.local_stamp(created, now)}" if created else "never", None))
    out.append(("Last change", words.ago(updated_epoch(d) or 0, now), None))
    tries = tries_text(d)
    if tries:
        out.append(("Tries", tries, None))
    if d.get("last_error"):
        out.append(("Problem", problem_text(d["last_error"]), None))
    if d.get("ack_status"):
        out.append(("Confirmation", ack_text(d["ack_status"]), None))
    expires = words.stamp_epoch(d.get("expires_at"))
    if expires:
        out.append(("Gives up", words.in_time(expires, now), None) if expires > now else ("Expired", words.ago(expires, now), None))
    return out


def details(d: dict) -> list:
    """The raw fields experts want, behind "Show details": (label, value)."""
    out = [("Delivery", f"#{d.get('id', '')}"), ("Link id", channel(d)), ("Stored status", status(d)), ("Priority", str(d.get("priority", ""))), ("Message ref", d.get("msg_ref") or "")]
    if d.get("rule_id") is not None:
        out.append(("Rule", f"#{d['rule_id']}"))
    qos = d.get("qos_level", 1)
    out.append(("QoS level", f"{qos} ({guarantee_label(qos)})"))
    if int(d.get("seq_num") or 0) > 0:
        out.append(("Sequence", str(d["seq_num"])))
    if int(d.get("ttl_seconds") or 0) > 0:
        out.append(("TTL", f"{d['ttl_seconds']} s"))
    if d.get("ack_status"):
        out.append(("ACK", d["ack_status"]))
    if d.get("custody_id"):
        out.append(("Custody", d["custody_id"]))
    if d.get("last_error"):
        out.append(("Error", d["last_error"]))
    return out


def details_title(d: dict) -> str:
    return f"Message by {link(d)}"


def queue_sections(deliveries: list) -> tuple:
    """(waiting, gave up): the Queue tab's two lists."""
    return [d for d in deliveries if status(d) in WAITING], [d for d in deliveries if status(d) in GAVE_UP]


def queue_count(deliveries: list) -> int:
    waiting, gave_up = queue_sections(deliveries)
    return len(waiting) + len(gave_up)


def section_title(waiting: bool, n: int) -> str:
    return f"Waiting to go out ({n})" if waiting else f"Did not go out ({n})"


def record_key(d: dict) -> tuple:
    """What a card shows, so a list is rebuilt only when one of its cards would change."""
    return (d.get("id"), status(d), d.get("retries"), d.get("last_error"), d.get("updated_at"), d.get("ack_status"), d.get("text_preview"))
