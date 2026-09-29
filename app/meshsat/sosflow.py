# SPDX-License-Identifier: GPL-3.0-or-later
"""Sends an SOS on every route the phone has, or a test of the alarm, and keeps the record
(sos/SosController.kt). A real SOS: one call starts the Bridge's own burst on the mesh, the
satellite modem and the Hub's uplink, which keeps trying by itself; the app adds an SMS to
each emergency contact from the phone's SIM. A test: the test text on the mesh and by SMS to the
contacts; with a modem, a position report to the Hub by satellite (one credit; the test text
when the phone has no fix); and a test event to the Hub that raises nothing. The run is kept in the preferences, so the banner, the result screen and the
cancellation survive a restart. No GTK here: the tests drive it against a scripted Bridge."""
import threading
import time

from . import api, sos, trace
from .model import sosrun

HUB_RETRY = 15.0
HUB_RETRIES = 40  # ten minutes of trying to tell the Hub about a test


class Flow:
    def __init__(self, prefs, on_change=None):
        self.prefs = prefs
        self.on_change = on_change or (lambda: None)
        self.run = sosrun.Run.from_json(prefs.get("sos_run"))
        self._lock = threading.Lock()
        self._hub_tries = 0

    # What the screens read
    def active(self) -> "sosrun.Run | None":
        return self.run if self.run is not None and self.run.active else None

    def save(self) -> None:
        self.prefs.set(sos_run=self.run.to_json() if self.run else None)
        self.on_change()

    def _set(self, key: str, state: str, detail: str) -> None:
        with self._lock:
            route = self.run.route(key) if self.run else None
            if route is None:
                return
            route.state, route.detail = state, detail
        self.save()

    # Starting
    def start(self, s, test: bool, trigger: str) -> "sosrun.Run":
        """The SOS or the test, from the state `s` (the plan), started on every route."""
        if self.run is not None and self.run.active:
            if not self.run.test or test:
                return self.run  # an SOS or a test is already running
            self.run.finished_at = time.time()  # a real SOS replaces a test
        now = time.time()
        name = s.sos_name
        fix = s.position()
        fix_tuple = None
        if fix:
            phone = s.phone
            fix_tuple = (fix[0], fix[1], phone[2] if phone else None, phone[3] if phone else now)
        routes, skipped = sosrun.plan(s, test, bool(s.contacts))
        self.run = sosrun.Run(now, test, trigger, name, fix_tuple, routes, skipped)
        self._hub_tries = 0
        self.save()
        trace.event("sos", test=test, trigger=trigger, routes=[r.key for r in routes], skipped=skipped)
        if test:
            self._start_test(s, name, fix)
        else:
            self._start_sos(s, name, fix)
        return self.run

    def _start_sos(self, s, name: str, fix) -> None:
        text = sos.mesh_text(name, fix)
        run = self.run

        def started(answer: api.Answer) -> None:
            if answer.ok or answer.status == 409:
                # The Bridge's burst carries the mesh, the satellite and the Hub's uplink; its
                # status counts the sends, which mark those routes sent (see follow()).
                for key in ("mesh", "sat"):
                    self._set(key, sosrun.SENDING, "Sending now")
            else:
                for key in ("mesh", "sat"):
                    self._set(key, sosrun.FAILED, answer.error or "Not sent")
                self._set("hub", sosrun.FAILED, answer.error or "Not sent")

        api.fetch("/api/sos/activate", started, method="POST", body={"message": text, "trigger": run.trigger})
        self._text_contacts(s, sos.sms_text(name, fix), cancel=False)

    def _start_test(self, s, name: str, fix) -> None:
        text = sos.test_text(name)
        if self.run.route("mesh") is not None:
            self._send("mesh", {"text": text})
        if self.run.route("sat") is not None:
            if s.phone:
                self._position_report(s)
            else:
                self._send("sat", {"text": text, "gateway": "iridium"})
        self._text_contacts(s, text, cancel=False)
        if self.run.route("hub") is not None:
            self._tell_hub(text, fix)

    def _send(self, key: str, body: dict) -> None:
        self._set(key, sosrun.SENDING, "Sending now")

        def done(answer: api.Answer) -> None:
            queued = isinstance(answer.body, dict) and answer.body.get("status") == "queued"
            if answer.ok and queued:
                self._queued(key, answer.body.get("msg_ref"), cancel=False)
            elif not answer.ok and body.get("gateway"):
                self._set(key, sosrun.FAILED, sosrun.NOT_QUEUED)
            else:
                state, detail = sosrun.state_of_answer(answer.ok, answer.error)
                self._set(key, state, detail)
            self._settle_test()

        api.fetch("/api/messages/send", done, method="POST", body=body)

    def _queued(self, key: str, ref, cancel: bool) -> None:
        """A leg the Bridge queued: its delivery tells the rest (follow_deliveries)."""
        with self._lock:
            route = self.run.route(key) if self.run else None
            if route is None:
                return
            if cancel:
                route.cancel_ref, route.cancel = ref or None, sosrun.WAITING
            else:
                route.ref, route.state, route.detail = ref or None, sosrun.WAITING, "Waiting to send"
        self.save()

    def _position_report(self, s) -> None:
        """The test's satellite leg with the phone's fix: a position report to the Hub
        (SosMessages.positionFrame). The Bridge queues Android's frame on its satellite modem,
        on the same path to the Hub's uplink decoder as an SOS frame, and it never reaches the
        Hub's routing engine (MESHSAT-1430)."""
        body = {"satellite": True, "latitude": s.phone[0], "longitude": s.phone[1]}
        altitude = (s.fix or {}).get("altitude")
        if altitude is not None:
            body["altitude"] = altitude
        self._set("sat", sosrun.SENDING, "Sending now")

        def done(answer: api.Answer) -> None:
            ref = answer.body.get("msg_ref") if answer.ok and isinstance(answer.body, dict) else None
            if ref:
                self._queued("sat", ref, cancel=False)
            else:
                self._set("sat", sosrun.FAILED, sosrun.NOT_QUEUED)
            self._settle_test()

        api.fetch("/api/sos/test", done, method="POST", body=body)

    def _text_contacts(self, s, text: str, cancel: bool) -> None:
        """The SMS legs, one per emergency contact, through the Bridge's SMS gateway, as the words
        themselves: `plain` keeps the SMS link's encryption and a chat key off them (a contact
        must read an SOS on any phone, as Android sends it through SmsManager; MESHSAT-1424)."""
        if not s.sms_ready() or not s.contacts:
            return
        me = (s.bridge or {}).get("node_id")
        for contact in s.contacts:
            key = "sms:" + contact["phone"]
            if self.run.route(key) is None:
                continue
            if not cancel:
                self._set(key, sosrun.SENDING, "Sending now")

            def done(answer: api.Answer, key=key, phone=contact["phone"]) -> None:
                if answer.ok:
                    api.record_sent(text, phone, "sms", me)
                ref = answer.body.get("msg_ref") if answer.ok and isinstance(answer.body, dict) else None
                if cancel:
                    if ref:
                        self._queued(key, ref, cancel=True)
                        return
                    with self._lock:
                        route = self.run.route(key) if self.run else None
                        if route is not None:
                            route.cancel = sosrun.SENT if answer.ok else sosrun.FAILED
                    self.save()
                elif ref:
                    self._queued(key, ref, cancel=False)
                    self._settle_test()
                elif answer.ok:
                    self._set(key, sosrun.SENT, "Sent")
                    self._settle_test()
                else:
                    self._set(key, sosrun.FAILED, sosrun.NOT_QUEUED)
                    self._settle_test()

            api.fetch("/api/messages/send", done, method="POST", body={"text": text, "gateway": "cellular", "to": contact["phone"], "plain": True})

    def _tell_hub(self, text: str, fix) -> None:
        body = {"message": text}
        if fix:
            body.update(latitude=fix[0], longitude=fix[1])
        run = self.run

        def done(answer: api.Answer) -> None:
            if self.run is not run or not run.active:
                return
            if answer.ok:
                self._set("hub", sosrun.SENT, "Sent")
                self._settle_test()
            elif answer.status == 503 and self._hub_tries < HUB_RETRIES:
                self._hub_tries += 1
                self._set("hub", sosrun.WAITING, "Waiting for the Hub connection")
                timer = threading.Timer(HUB_RETRY, lambda: self._tell_hub(text, fix) if self.run is run and run.active else None)
                timer.daemon = True
                timer.start()
            else:
                self._set("hub", sosrun.FAILED, answer.error or "Not sent")
                self._settle_test()

        api.fetch("/api/sos/test", done, method="POST", body=body)

    def _settle_test(self) -> None:
        run = self.run
        if run is None or not run.test or not run.active:
            return
        if sosrun.all_settled(run.routes):
            run.finished_at = time.time()
            self.save()

    # Following the Bridge
    FOLLOW_FOR = 1800.0
    FOLLOW_EVERY = 5.0

    def follow_deliveries(self) -> None:
        """The legs the app queued, read from the Bridge's queue (SosProgress.routes): state and
        words from each delivery, the cancellation's too; for half an hour after the start, so a
        late confirmation (the Hub's receipt, the carrier's report) still shows."""
        run = self.run
        now = time.time()
        if run is None or now - run.id > self.FOLLOW_FOR or now - getattr(self, "_followed", 0.0) < self.FOLLOW_EVERY:
            return
        self._followed = now
        for route in list(run.routes):
            for ref, cancel in ((route.ref, False), (route.cancel_ref, True)):
                if not ref:
                    continue

                def done(answer: api.Answer, key=route.key, cancel=cancel, run=run) -> None:
                    if self.run is not run or not answer.ok or not isinstance(answer.body, list) or not answer.body:
                        return
                    delivery = answer.body[0]
                    state, detail = sosrun.state_of_delivery(delivery), sosrun.detail_of_delivery(delivery)
                    with self._lock:
                        route = run.route(key)
                        if route is None:
                            return
                        if cancel:
                            if route.cancel == state:
                                return
                            route.cancel = state
                        else:
                            if (route.state, route.detail) == (state, detail):
                                return
                            route.state, route.detail = state, detail
                    self.save()
                    self._settle_test()

                api.fetch(f"/api/deliveries/message/{ref}", done)

    def follow(self, s) -> None:
        """Every poll: the legs the app queued follow their deliveries; a real SOS's
        Bridge-carried routes follow the Bridge's status; a real SOS the Bridge no longer knows
        (it restarted) is over."""
        self.follow_deliveries()
        run = self.run
        if run is None or run.test or not run.active:
            return
        status = s.sos or {}
        sends = status.get("sends") or 0
        if status.get("active") and sends:
            changed = False
            with self._lock:
                for key, detail in (("mesh", "Sent"), ("sat", "Sent")):
                    route = run.route(key)
                    if route is not None and route.state != sosrun.SENT:
                        route.state, route.detail = sosrun.SENT, detail
                        changed = True
                hub = run.route("hub")
                if hub is not None and hub.state != sosrun.SENT:
                    link = (s.hub or {}).get("link") or ""
                    if link == "connected":
                        hub.state, hub.detail = sosrun.SENT, "Sent"
                        changed = True
            if changed:
                self.save()
        elif s.bridge and not status.get("active") and time.time() - run.id > 20:
            # The Bridge's burst is over (three sends), or it restarted: the SOS is no longer on.
            run.finished_at = time.time()
            self.save()

    # Cancelling
    def cancel(self, s) -> None:
        """Cancel the SOS, or stop the test."""
        run = self.run
        if run is None or not run.active:
            return
        if run.test:
            run.finished_at = time.time()
            for route in run.routes:
                if route.state in (sosrun.WAITING, sosrun.SENDING):
                    route.state, route.detail = sosrun.STOPPED, sosrun.HUB_STOPPED if route.key == "hub" else "Stopped"
            self.save()
            trace.event("sos", test=True, stopped=True)
            return
        run.cancelled_at = time.time()
        for route in run.routes:
            if route.state in (sosrun.WAITING, sosrun.SENDING):
                route.state, route.detail = sosrun.STOPPED, "Stopped"
        self.save()
        trace.event("sos", cancelled=True)
        api.fetch("/api/sos/cancel", lambda answer: None, method="POST")
        # Every route that carried the SOS is told it is over: the mesh by a broadcast, the
        # contacts by SMS; the satellite leg keeps its credit.
        text = sos.cancel_text(run.name)
        mesh = run.route("mesh")
        if mesh is not None and mesh.state == sosrun.SENT:
            mesh.cancel = sosrun.SENDING

            def done(answer: api.Answer) -> None:
                mesh.cancel = sosrun.SENT if answer.ok else sosrun.FAILED
                self.save()

            api.fetch("/api/messages/send", done, method="POST", body={"text": text})
        for route in run.routes:
            if route.key.startswith("sms:") and route.state == sosrun.SENT:
                route.cancel = sosrun.SENDING
        self.save()
        self._text_contacts(s, text, cancel=True)
