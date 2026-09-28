# SPDX-License-Identifier: GPL-3.0-or-later
"""Sends an SOS on every route the phone has, or a test of the alarm, and keeps the record
(sos/SosController.kt). A real SOS: one call starts the Bridge's own burst on the mesh, the
satellite modem and the Hub's uplink, which keeps trying by itself; the app adds an SMS to
each emergency contact from the phone's SIM. A test: the test text on the mesh, by SMS to the
contacts and, with a modem, by satellite (one credit), and a test event to the Hub that raises
nothing. The run is kept in the preferences, so the banner, the result screen and the
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
            self._send("sat", {"text": text, "gateway": "iridium"})
        self._text_contacts(s, text, cancel=False)
        if self.run.route("hub") is not None:
            self._tell_hub(text, fix)

    def _send(self, key: str, body: dict) -> None:
        self._set(key, sosrun.SENDING, "Sending now")

        def done(answer: api.Answer) -> None:
            state, detail = sosrun.state_of_answer(answer.ok, answer.error, queued=isinstance(answer.body, dict) and answer.body.get("status") == "queued")
            self._set(key, state, detail)
            self._settle_test()

        api.fetch("/api/messages/send", done, method="POST", body=body)

    def _text_contacts(self, s, text: str, cancel: bool) -> None:
        """The SMS legs, one per emergency contact, through the Bridge's SMS gateway."""
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
                if cancel:
                    with self._lock:
                        route = self.run.route(key) if self.run else None
                        if route is not None:
                            route.cancel = sosrun.SENT if answer.ok else sosrun.FAILED
                    self.save()
                else:
                    state, detail = sosrun.state_of_answer(answer.ok, answer.error)
                    self._set(key, state, detail)
                    self._settle_test()

            api.fetch("/api/messages/send", done, method="POST", body={"text": text, "gateway": "cellular", "to": contact["phone"]})

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
    def follow(self, s) -> None:
        """Every poll: a real SOS's Bridge-carried routes follow the Bridge's status; a real
        SOS the Bridge no longer knows (it restarted) is over."""
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
                    route.state, route.detail = sosrun.STOPPED, "Stopped"
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
