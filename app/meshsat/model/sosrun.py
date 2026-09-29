# SPDX-License-Identifier: GPL-3.0-or-later
"""One SOS, or one test of the alarm, and where each of its routes stands (sos/SosRun.kt,
SosProgress). On this edition the Bridge carries the mesh, satellite and Hub legs of a real
SOS itself (one call starts them all, and it keeps trying); the app sends the SMS legs from
the phone's SIM through the Bridge's SMS gateway, and an alarm test route by route. The run
is kept in the app's preferences, so the banner, the result screen and the cancellation
survive a restart."""
import time

from . import home, words

WAITING, SENDING, SENT, STOPPED, FAILED = "waiting", "sending", "sent", "stopped", "failed"
HUB_LABEL = "Hub, over the internet"
HUB_SHORT = "the Hub online"


class Route:
    """One route of a run: its key ("sat", "mesh", "sms:+316...", "hub"), its label, and what
    the app knows of it: state, detail, and the cancellation's state after a cancel."""

    __slots__ = ("key", "label", "state", "detail", "cancel", "short", "ref", "cancel_ref")

    def __init__(self, key: str, label: str, state: str = WAITING, detail: str = "Waiting to send", cancel: str | None = None, short: str | None = None,
                 ref: str | None = None, cancel_ref: str | None = None):
        self.key, self.label, self.state, self.detail, self.cancel = key, label, state, detail, cancel
        self.short = short or {"sat": "satellite", "mesh": "mesh", "hub": HUB_SHORT}.get(key, label)
        self.ref, self.cancel_ref = ref, cancel_ref  # the Bridge's msg_ref of the leg and of its cancellation

    def to_json(self) -> dict:
        return {"key": self.key, "label": self.label, "state": self.state, "detail": self.detail, "cancel": self.cancel, "short": self.short,
                "ref": self.ref, "cancel_ref": self.cancel_ref}

    @classmethod
    def from_json(cls, data: dict) -> "Route":
        return cls(data.get("key", ""), data.get("label", ""), data.get("state", WAITING), data.get("detail", ""), data.get("cancel"), data.get("short"),
                   data.get("ref"), data.get("cancel_ref"))


class Run:
    def __init__(self, id_: float, test: bool, trigger: str, name: str, fix, routes: list, skipped: list, cancelled_at: float | None = None, finished_at: float | None = None):
        self.id = id_  # the start, as a Unix time
        self.test = test
        self.trigger = trigger  # "hold", "accessible", "checkin"
        self.name = name
        self.fix = fix  # (lat, lon, accuracy_m or None, at) or None
        self.routes = routes
        self.skipped = skipped
        self.cancelled_at = cancelled_at
        self.finished_at = finished_at

    @property
    def active(self) -> bool:
        return self.cancelled_at is None and self.finished_at is None

    def route(self, key: str) -> Route | None:
        return next((r for r in self.routes if r.key == key), None)

    def to_json(self) -> dict:
        return {"id": self.id, "test": self.test, "trigger": self.trigger, "name": self.name, "fix": list(self.fix) if self.fix else None,
                "routes": [r.to_json() for r in self.routes], "skipped": list(self.skipped), "cancelled_at": self.cancelled_at, "finished_at": self.finished_at}

    @classmethod
    def from_json(cls, data) -> "Run | None":
        if not isinstance(data, dict) or "id" not in data:
            return None
        try:
            fix = tuple(data["fix"]) if data.get("fix") else None
            return cls(float(data["id"]), bool(data.get("test")), str(data.get("trigger") or "hold"), str(data.get("name") or ""), fix,
                       [Route.from_json(r) for r in data.get("routes") or []], [str(s) for s in data.get("skipped") or []],
                       data.get("cancelled_at"), data.get("finished_at"))
        except (TypeError, ValueError):
            return None


def sentence(items: list) -> str:
    return words.join_and(items)


def summary(routes: list) -> str:
    """One line for the notification and the card: "Sent by SMS to Anna and the Hub online.
    Still trying satellite." """
    if not routes:
        return "No way to send it: add emergency contacts or connect your node."
    sent = [r.short for r in routes if r.state == SENT]
    trying = [r.short for r in routes if r.state in (WAITING, SENDING)]
    parts = []
    if sent:
        parts.append(f"Sent by {sentence(sent)}.")
    if trying:
        parts.append(f"Still trying {sentence(trying)}.")
    if not parts:
        parts.append("Nothing could be sent.")
    return " ".join(parts)


def all_settled(routes: list) -> bool:
    return not any(r.state in (WAITING, SENDING) for r in routes)


def cancel_words(state: str | None) -> str:
    return {SENT: "sent", SENDING: "sending", WAITING: "waiting to send", STOPPED: "stopped", FAILED: "failed"}.get(state or "", "")


def plan(s, test: bool, contacts_reach: bool) -> tuple:
    """The routes an SOS or a test takes from this phone right now, and the ones it cannot:
    (routes, skipped), in Android's words (SosController.start)."""
    routes, skipped = [], []
    if not s.bridge:
        skipped.append("The Bridge is not running on this phone, so nothing could be queued. Start it under Setup, Your MeshSat node.")
        return routes, skipped
    if s.modem_connected():
        routes.append(Route("sat", "Satellite, to the Hub"))
    else:
        skipped.append("Satellite: no satellite modem has been connected to this phone yet.")
    if s.mesh_connected():
        routes.append(Route("mesh", "Mesh, everyone in range"))
    else:
        skipped.append("Mesh: no mesh radio is paired with this phone." if s.node_mode() == "bluetooth" else "Mesh: the node is not connected.")
    if not s.sms_ready():
        skipped.append("SMS: this device cannot send SMS." if not (s.cellular or {}).get("connected") else f"SMS: {s.sms_reason() or 'not ready.'}")
    elif not s.contacts:
        skipped.append("SMS: you have no emergency contacts. Add them in Setup, Safety.")
    else:
        for c in s.contacts:
            who = c.get("name") or c["phone"]
            routes.append(Route("sms:" + c["phone"], f"SMS to {who}"))
    if s.hub_configured():
        routes.append(Route("hub", HUB_LABEL, WAITING, "Waiting for the Hub connection"))
    else:
        skipped.append("Hub: not set up on this phone.")
    return routes, skipped


def state_of_delivery(d: dict) -> str:
    """SosProgress.stateOf: a route's state from its delivery in the Bridge's queue."""
    status = d.get("status")
    if status in ("sent", "delivered"):
        return SENT
    if status == "sending":
        return SENDING
    if status in ("queued", "retry", "held"):
        return WAITING
    if status == "dead":
        return STOPPED if d.get("last_error") == "cancelled" else FAILED
    return FAILED


def detail_of_delivery(d: dict) -> str:
    """SosProgress.detailOf: a confirmation from the far end is said (the Hub's receipt by
    satellite, the carrier's delivery report by SMS); a retry says why."""
    state = state_of_delivery(d)
    error = str(d.get("last_error") or "")
    if state == SENT:
        channel = str(d.get("channel") or "")
        if d.get("ack_status") != "acked":
            return "Sent"
        if channel.startswith("iridium"):
            return "Sent, and the Hub has it"
        if channel.startswith("sms") or channel.startswith("cellular"):
            return "Delivered to their phone"
        return "Sent"
    if state == SENDING:
        return "Sending now"
    if state == STOPPED:
        return "Stopped"
    if state == WAITING:
        return "Waiting to send" if not d.get("retries") and not error.strip() else f"Trying again: {error.strip() or 'not sent yet'}"
    return error.strip() or "Not sent"


NOT_QUEUED = "Could not be queued"
HUB_STOPPED = "Stopped before the Hub could be reached"


def state_of_answer(ok: bool, error: str | None, queued: bool = False) -> tuple:
    """A route's state and detail from the Bridge's answer to its send."""
    if ok and queued:
        return WAITING, "Waiting to send"
    if ok:
        return SENT, "Sent"
    return FAILED, error or "Not sent"


def titles(run: Run, now: float | None = None) -> tuple:
    """The result screen's title and its tone (SosScreen.kt)."""
    if run.test and run.active:
        return "Alarm test running", "amber"
    if run.test:
        return "Alarm test finished", "muted"
    if run.cancelled_at is not None:
        return f"SOS cancelled at {clock(run.cancelled_at)}", "muted"
    return "SOS is on", "red"


def started_line(run: Run) -> str:
    how = "by the check-in timer" if run.trigger == "checkin" else "from this phone"
    if run.fix:
        lat, lon = run.fix[0], run.fix[1]
        acc = run.fix[2] if len(run.fix) > 2 else None
        where = f"Position {lat:.5f}, {lon:.5f}" + (f", within {round(acc)} m." if acc else ".")
    else:
        where = "Position unknown."
    return f"Started at {clock(run.id)} {how}. {where}"


def clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def test_parts(s, modem_seen: str = "") -> list:
    """What each route of a test carries, and what it costs (TestAlarmDialog, SosScreens.kt:414-429).
    The routes are SosReach's, as Home's SOS card and Setup > Safety show them (home.reach: every
    route set up, the satellite once the phone has had a modem, `modem_seen` being the IMEI the
    app remembers), not only the ones up this minute."""
    routes = home.reach(s, modem_seen)
    parts = []
    if routes["satellite"]:
        parts.append("a position report to the Hub by satellite, 1 credit")
    if routes["mesh"]:
        parts.append("the text on the mesh")
    if routes["sms"]:
        if len(s.contacts) == 1:
            name = s.contacts[0].get("name") or ""
            parts.append(f"the text by SMS to {name if name.strip() else '1 contact'}, at your carrier's rate")  # name.ifBlank { "1 contact" }
        else:
            parts.append(f"the text by SMS to {len(s.contacts)} contacts, at your carrier's rate")
    if routes["hub"]:
        parts.append("a test event to the Hub online")
    return parts


def test_dialog_text(text: str, parts: list) -> str:
    joined = parts[0] if len(parts) == 1 else ("; ".join(parts[:-1]) + "; and " + parts[-1] if parts else "")
    return f"The test text is \"{text}\". It goes as {joined}. Nobody is alarmed, and the Hub does not raise an SOS."
