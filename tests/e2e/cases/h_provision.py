# SPDX-License-Identifier: GPL-3.0-or-later
"""Hub provisioning (ProvisionImporter.kt, ProvisionClaim.kt, ProvisionClaimHost.kt,
ProvisionLinkDialog.kt) against the scripted Bridge and a scripted Hub (plain http on the
Bridge's port, MESHSAT_APP_HUB_SCHEME): a scanned code is claimed through the Hub's "not yet"
answers and then asked about; Provision writes the settings to the Bridge, stores the client
certificate and restarts the Bridge (dry under test); an expired code says so; a link is asked
about first and applied at once; an inline code by link is refused; Cancel during the wait
drops the claim."""
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from driver.qr import write_png  # noqa: E402

SCENARIO = "mesh-only"
ENV = {"MESHSAT_APP_SCAN_SOURCE": 'filesrc location="{work}/scan.png" ! pngdec ! imagefreeze', "MESHSAT_APP_HUB_SCHEME": "http"}
NONCE = "0123456789abcdef0123456789abcdef"
BUNDLE = {"v": "1", "bid": "e2e-kit", "mqtt": "wss://mqtt-hub.meshsat.net/mqtt", "user": "e2e-kit", "pass": "e2e-secret", "ca": "-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----",
          "cert": "-----BEGIN CERTIFICATE-----\nC\n-----END CERTIFICATE-----", "key": "-----BEGIN PRIVATE KEY-----\nK\n-----END PRIVATE KEY-----", "cert_exp": "2027-09-29T00:00:00Z",
          "ret_tcp": ""}


def host(ctx) -> str:
    return urllib.parse.urlparse(ctx.bridge.url).netloc


def link(ctx, bid: str = "e2e-kit", nonce: str = NONCE) -> str:
    return f"meshsat://provision/{bid}/{nonce}?hub={host(ctx)}"


def scan(ctx, value: str) -> None:
    ctx.app.open("setup/messaging")
    ctx.tree.find("button", name="Scan QR Code (Hub Key Sync)", timeout=10)
    write_png(value, ctx.app.work + "/scan.png")
    ctx.app.mark()
    ctx.tree.click("Scan QR Code (Hub Key Sync)")


def case_a_a_scanned_code_is_claimed_then_asked_about(ctx):
    ctx.bridge.scenario("mesh-only")
    # "Not yet" three times, 8 s apart. One walk of the tree takes seconds on the phone behind the
    # Messaging page and reads the dialogs' list when it starts, so the wait is long, and the
    # dialog's words are all read in one walk.
    ctx.bridge.claim("e2e-kit", NONCE, dict(BUNDLE), busy=3, retry_after=8)
    before = ctx.bridge.count()
    scan(ctx, link(ctx))
    waiting = ("The Hub gives this phone its new password once all its servers accept it. That usually takes about a minute. "
               "You can leave this screen; the phone keeps asking.")
    deadline = time.time() + 20
    while True:
        names = [n.name for n in ctx.tree.dialog(timeout=20)]
        if "Getting the Hub's settings" in names and waiting in names:
            break
        assert time.time() < deadline, names
    ctx.shot("waiting")
    ctx.tree.wait_text("Use these Hub settings?", timeout=40)
    names = [n.name for n in ctx.tree.dialog()]
    for words in ('This phone becomes bridge "e2e-kit" on the Hub. Its current Hub settings are replaced.', "Hub: wss://mqtt-hub.meshsat.net/mqtt",
                  "Certificate expires: 2027-09-29T00:00:00Z"):
        assert words in names, (words, names)
    assert ctx.bridge.state()["claims"] == 4, ctx.bridge.state()["claims"]  # three "not yet", then the settings
    ctx.shot("ready")
    ctx.tree.click_in_dialog("Provision")
    ctx.app.wait_toast("Hub provisioned: e2e-kit. Connecting to the Hub.", timeout=10)
    put = ctx.bridge.wait_request("PUT", "/api/routing/hub", since=before)["body"]
    assert put == {"url": BUNDLE["mqtt"], "bridge_id": "e2e-kit", "username": "e2e-kit", "password": "e2e-secret", "tls_cert_pem": BUNDLE["cert"],
                   "tls_key_pem": BUNDLE["key"], "tls_ca_pem": BUNDLE["ca"]}, put
    ctx.bridge.wait_request("POST", "/api/credentials/upload", since=before)
    assert ["pkexec", "systemctl", "restart", "meshsat-bridge.service"] in ctx.app.commands(), ctx.app.commands()


def case_b_a_spent_code_says_so(ctx):
    ctx.bridge.claim("e2e-kit", NONCE, None)
    scan(ctx, link(ctx))
    ctx.tree.wait_text("No settings from the Hub", timeout=15)
    ctx.tree.wait_text("Provisioning token expired or already used. Generate a new QR from the Hub.")
    ctx.tree.click_in_dialog("OK")


def case_c_a_link_is_asked_about_first_and_applied_at_once(ctx):
    ctx.bridge.claim("e2e-link", NONCE, {**BUNDLE, "bid": "e2e-link"})
    before = ctx.bridge.count()
    ctx.app.mark()
    ctx.app.open_uri(link(ctx, "e2e-link"))
    ctx.tree.wait_text("Provision Hub Connection", timeout=10)
    names = [n.name for n in ctx.tree.dialog()]
    want = (f'Provision this phone as bridge "e2e-link" with credentials from {host(ctx)}?\n\n'
            "This will overwrite existing Hub settings. Only continue if you generated this link on your own Hub.")
    assert want in names and f"Hub: {host(ctx)}" in names, names
    assert ctx.bridge.state()["claims"] == 0, "claimed before the question was answered"
    ctx.tree.click_in_dialog("Provision")
    ctx.app.wait_toast("Hub provisioned: e2e-link. Connecting to the Hub.", timeout=15)
    assert ctx.bridge.wait_request("PUT", "/api/routing/hub", since=before)["body"]["bridge_id"] == "e2e-link"


def case_d_an_inline_code_by_link_is_refused(ctx):
    ctx.app.mark()
    ctx.app.open_uri("meshsat://provision/eyJicmlkZ2VfaWQiOiJ4In0")
    ctx.app.wait_toast("Provisioning link rejected: Inline provisioning codes must be scanned in Settings", timeout=10)


def case_e_cancel_during_the_wait_drops_the_claim(ctx):
    ctx.bridge.claim("e2e-kit", NONCE, dict(BUNDLE), busy=100, retry_after=1)
    before = ctx.bridge.count()
    scan(ctx, link(ctx))
    ctx.tree.wait_text("Getting the Hub's settings", timeout=15)
    ctx.tree.click_in_dialog("Cancel")
    time.sleep(3)
    assert not [r for r in ctx.bridge.requests(before) if r["method"] == "PUT" and r["path"] == "/api/routing/hub"], "applied after Cancel"
    assert not ctx.tree.dialogs_open()
