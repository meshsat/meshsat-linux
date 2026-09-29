# SPDX-License-Identifier: GPL-3.0-or-later
"""What a code from the Setup scanner leads to, held by the app rather than by a screen, as
MeshSat Android holds it (SettingsScreen.kt:283-344, ProvisionClaimHost.kt, ProvisionLinkDialog.kt,
KeyBundleImporter.kt): the router (a provisioning code, a key bundle, a 64-hex key, or Android's
refusal), the key bundles with their trust on first use, and the Hub's provisioning by QR code
and by `meshsat://provision/` link, with its wait, its question and its result."""
import os
import threading
import time
import urllib.error
import urllib.request
import weakref

from gi.repository import GLib, Gtk

from . import api, store, system, theme, trace
from .model import keybundle, provision
from .widgets import Sheet, confirm, text

HUB_SCHEME = os.environ.get("MESHSAT_APP_HUB_SCHEME", "https")  # the tests' scripted Hub answers plain http


def route_setup_code(app, value, on_hex_key) -> None:
    """The Setup scanner's router, in Android's order, the text as scanned (no trim)."""
    if not value:
        return
    if value.startswith(provision.PREFIX):
        app.provisioning.from_qr(value)
    elif value.startswith(keybundle.PREFIX):
        app.keys.import_url(value)
    elif keybundle.is_hex_key(value):
        on_hex_key(value)
    else:
        app.toast(keybundle.NOT_A_KEY)


# ── Key bundles ──────────────────────────────────────────────────────────────────────────────
class KeyImports:
    """Android's importer before the store: the checks and the pins here, the keys to the Bridge
    (POST /api/keys/import), whose count the toast gives."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def path() -> str:
        return os.path.join(store.config_dir(), "meshsat", "bridge_trust.json")

    def pins(self) -> dict:
        pins = store.read_json(self.path(), {})
        return pins if isinstance(pins, dict) else {}

    def import_url(self, url: str, force: bool = False) -> None:
        result, detail, pins = keybundle.check(url, self.pins(), force=force)
        if pins != self.pins():
            store.write_json(self.path(), pins)
        trace.event("key-bundle", result=result, force=force)
        if result == "KeyMismatch":
            self.ask_repin(url, detail)
            return
        if result != "Import":
            words = keybundle.invalid(detail) if result == "InvalidSignature" else keybundle.malformed(detail)
            self.app.toast(keybundle.not_imported(f"{result}(reason={detail})") if force else words)
            return

        def answered(answer: api.Answer) -> None:
            if not answer.ok:
                reason = answer.error or f"HTTP {answer.status}"
                self.app.toast(keybundle.not_imported(f"Malformed(reason={reason})") if force else keybundle.malformed(reason))
                return
            count = int((answer.body or {}).get("imported_count") or 0)
            self.app.toast(keybundle.repinned(count) if force else keybundle.imported(count, detail["trust"], detail["kit"]))

        api.fetch("/api/keys/import", answered, method="POST", body={"url": url})

    def ask_repin(self, url: str, detail: dict) -> None:
        confirm(self.app, keybundle.CHANGED_TITLE, keybundle.changed_text(detail["kit"]), keybundle.TRUST_NEW, lambda: self.import_url(url, force=True),
                cancel=keybundle.KEEP_OLD, danger=True)


# ── Hub provisioning ─────────────────────────────────────────────────────────────────────────
class Provisioning:
    """ProvisionClaim: Idle, Waiting, Ready, Applied, Failed; one claim at a time, held by the app
    so it goes on while the person leaves the screen."""

    def __init__(self, app):
        self.app = app
        self.state = "Idle"
        self.request = None
        self.bundle = None
        self.started = 0.0
        self.attempts = 0
        self.hidden = False
        self.claim_id = 0
        self.dialog = None
        self.waited_label = None
        self.listeners = []  # weak references: the Hub card's "Getting the Hub's settings, N s"

    # What starts a claim
    def from_qr(self, url: str) -> None:
        """A scanned code: claimed first, then the person is asked (Use these Hub settings?)."""
        self.dismiss()
        if provision.is_inline(url):
            try:
                self.ready(provision.inline_bundle(url))
            except ValueError as error:
                self.fail(provision.failed(error))
            return
        try:
            request = provision.parse_nonce(url)
        except ValueError as error:
            self.fail(provision.failed(error))
            return
        self.start(request, apply_at_once=False)

    def from_link(self, url: str) -> None:
        """A link from outside: asked first (Provision Hub Connection), then claimed and applied."""
        try:
            request = provision.parse_link(url)
        except ValueError as error:
            self.app.toast(provision.rejected(error))
            return
        body = provision.link_text(request["bridge_id"], request["hub_host"])

        sheet = Sheet(self.app, provision.LINK_TITLE)
        sheet.body.append(text(body, "body-medium", wrap=True))
        sheet.body.append(text(provision.link_host(request["hub_host"]), "body-small", theme.TEXT_MUTED, wrap=True))
        sheet.button(provision.CANCEL, sheet.close)
        sheet.button(provision.PROVISION, lambda: (sheet.close(), self.dismiss(), self.start(request, apply_at_once=True)), kind="filled")
        sheet.present()

    # The claim
    def start(self, request: dict, apply_at_once: bool) -> None:
        self.claim_id += 1
        claim_id = self.claim_id
        self.request, self.state, self.started, self.attempts, self.hidden = request, "Waiting", time.monotonic(), 0, False
        trace.event("provision", step="claim", bridge=request.get("bridge_id", ""), at_once=apply_at_once)
        self.show_waiting()
        GLib.timeout_add_seconds(1, self.tick, claim_id)

        def on_wait(attempts: int) -> None:
            self.attempts = attempts
            trace.event("provision", step="not yet", attempts=attempts)

        def work() -> None:
            try:
                bundle = provision.claim(request, get_https, on_wait=on_wait, cancelled=lambda: claim_id != self.claim_id)
                GLib.idle_add(self.claimed, claim_id, bundle, None, apply_at_once)
            except provision.ProvisionError as error:
                GLib.idle_add(self.claimed, claim_id, None, str(error) or provision.NO_SETTINGS, apply_at_once)
            except Exception as error:  # noqa: BLE001 - any other failure, in Android's words
                GLib.idle_add(self.claimed, claim_id, None, provision.failed(error), apply_at_once)

        threading.Thread(target=work, daemon=True).start()

    def tick(self, claim_id: int) -> bool:
        if claim_id != self.claim_id or self.state != "Waiting":
            return False
        if self.waited_label is not None:
            self.waited_label.set_text(provision.waited(self.seconds()))
        self.notify()
        return True

    def listen(self, method) -> None:
        """A screen's method called each second of a wait and when the claim's state changes."""
        self.listeners.append(weakref.WeakMethod(method))

    def notify(self) -> None:
        for ref in list(self.listeners):
            method = ref()
            if method is None:
                self.listeners.remove(ref)
            else:
                method()

    def seconds(self) -> int:
        return int(time.monotonic() - self.started) if self.state == "Waiting" else 0

    def claimed(self, claim_id: int, bundle, error, apply_at_once: bool) -> bool:
        trace.event("provision", step="answer", current=claim_id == self.claim_id, error=error or "")
        if claim_id != self.claim_id:
            return False  # dismissed: the answer is dropped
        if error:
            self.fail(error)
        elif apply_at_once:
            self.apply_now(bundle)
        else:
            self.ready(bundle)
        self.notify()
        return False

    # What the person sees
    def close_dialog(self) -> None:
        if self.dialog is not None:
            dialog, self.dialog = self.dialog, None
            dialog.close()

    def show_waiting(self) -> None:
        self.close_dialog()
        sheet = Sheet(self.app, provision.WAITING_TITLE)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(12))
        spinner = Gtk.Spinner(spinning=True)
        spinner.set_size_request(theme.dp(20), theme.dp(20))
        row.append(spinner)
        self.waited_label = text(provision.waited(0), "body-medium")
        row.append(self.waited_label)
        sheet.body.append(row)
        sheet.body.append(text(provision.WAITING_TEXT, "body-small", theme.TEXT_MUTED, wrap=True))
        sheet.button(provision.HIDE, self.hide)
        sheet.button(provision.CANCEL, self.dismiss)
        self.show(sheet, self.hide)  # a tap outside the wait hides it; the claim goes on

    def show(self, sheet, outside) -> None:
        """One dialog at a time; a tap outside it does what Android's onDismissRequest does."""
        trace.event("provision", step="dialog", title=sheet.dialog.get_title())
        self.dialog = sheet
        sheet.dialog.connect("closed", lambda *_: self.dialog is sheet and (setattr(self, "dialog", None) or outside()))
        sheet.present()

    def hide(self) -> None:
        self.hidden = True
        self.close_dialog()

    def ready(self, bundle: dict) -> None:
        self.state, self.bundle = "Ready", bundle
        self.close_dialog()
        sheet = Sheet(self.app, provision.READY_TITLE)
        sheet.body.append(text(provision.ready_text(bundle.get("bid", "")), "body-medium", wrap=True))
        for line in provision.ready_lines(bundle):
            sheet.body.append(text(line, "body-small", theme.TEXT_MUTED, wrap=True))
        sheet.button(provision.CANCEL, self.dismiss)
        sheet.button(provision.PROVISION, self.apply, kind="filled")
        self.show(sheet, self.dismiss)

    def apply(self) -> None:
        if self.state != "Ready":
            return
        bundle, self.state = self.bundle, "Idle"
        self.close_dialog()
        self.apply_now(bundle)

    def apply_now(self, bundle: dict) -> None:
        """The settings to the Bridge, the client certificate to its store, the Bridge restarted."""
        self.close_dialog()

        def saved(answer: api.Answer) -> None:
            if not answer.ok:
                self.fail(provision.not_saved(answer.error or f"HTTP {answer.status}"))
                return
            if bundle.get("cert") and bundle.get("key"):
                data = (bundle["cert"] + "\n" + bundle["key"]).encode("utf-8")
                api.upload("/api/credentials/upload", {"provider": "hub_mqtt", "name": f"Hub mTLS ({bundle.get('bid', '')})"}, "file", "hub-mtls.pem", data,
                           lambda _a: None)
            system.privileged("systemctl", "restart", "meshsat-bridge.service")
            self.state = "Applied"
            self.app.toast(provision.applied(bundle.get("bid", "")))
            self.state = "Idle"
            self.app.poller.poll_now()

        api.fetch("/api/routing/hub", saved, method="PUT", body=provision.hub_body(bundle))

    def fail(self, message: str) -> None:
        self.state = "Failed"
        self.close_dialog()
        sheet = Sheet(self.app, provision.FAILED_TITLE)
        sheet.body.append(text(message, "body-medium", wrap=True))
        sheet.button(provision.OK, self.dismiss)
        self.show(sheet, self.dismiss)

    def dismiss(self) -> None:
        """Back to Idle: a claim still on the wire finishes at the Hub, its answer is dropped."""
        self.claim_id += 1
        self.state, self.bundle, self.request = "Idle", None, None
        self.waited_label = None
        self.close_dialog()
        self.notify()


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith(HUB_SCHEME + "://"):
            raise urllib.error.URLError("redirected away from https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get_https(url: str) -> tuple:
    """(status, headers, body) of one claim; OSError for no answer at all."""
    if HUB_SCHEME != "https":
        url = HUB_SCHEME + url[len("https"):]
    opener = urllib.request.build_opener(_HttpsOnly())
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=10) as answer:
            return answer.status, dict(answer.headers.items()), answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()) if error.headers else {}, error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        raise OSError(str(error.reason)) from error
