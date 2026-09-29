# SPDX-License-Identifier: GPL-3.0-or-later
"""The Setup scanner's router on the Messaging page (SettingsScreen.kt:283-344, 863-884,
KeyBundleImporter.kt) against the scripted Bridge: a kit's key bundle read by the camera is
checked, its signer pinned on first use and the keys handed to the Bridge; the same kit again is
verified against the pin; a new signer for a known kit asks "This kit's key has changed" and
imports only when trusted; a 64-hex key becomes the SMS link's key; anything else is refused in
Android's words. The bundles are signed here as the Bridge signs them."""
import base64
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from driver.qr import write_png  # noqa: E402

SCENARIO = "messaging"
ENV = {"MESHSAT_APP_SCAN_SOURCE": 'filesrc location="{work}/scan.png" ! pngdec ! imagefreeze'}
KEY = "0123456789abcdef" * 4


def bundle(seed: bytes) -> str:
    """A v2 bundle for kit 11..11 with one SMS entry, signed by the key from `seed`."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: PLC0415
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: PLC0415

    private = Ed25519PrivateKey.from_private_bytes(seed)
    pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    entry = bytes([0x00, 12]) + b"+31612345678" + bytes([0x22]) * 32
    header = bytes([2]) + bytes([0x11]) * 16 + struct.pack(">I", 1789900000) + bytes([1])
    raw = header + pub + private.sign(header + pub + entry) + entry
    return "meshsat://key/" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def scan(ctx, value: str) -> None:
    write_png(value, ctx.app.work + "/scan.png")
    ctx.app.mark()
    ctx.tree.click("Scan QR Code (Hub Key Sync)")


def start(ctx) -> None:
    ctx.app.open("setup/messaging")
    ctx.tree.find("button", name="Scan QR Code (Hub Key Sync)", timeout=10)


def case_a_a_new_kit_is_pinned(ctx):
    ctx.bridge.scenario("messaging")
    start(ctx)
    before = ctx.bridge.count()
    scan(ctx, bundle(bytes(range(32))))
    ctx.app.wait_toast("Imported 1 key(s) — new bridge 11111111 pinned", timeout=15)
    sent = ctx.bridge.wait_request("POST", "/api/keys/import", since=before)["body"]
    assert sent == {"url": bundle(bytes(range(32)))}, sent


def case_b_the_same_kit_is_verified_against_its_pin(ctx):
    start(ctx)
    scan(ctx, bundle(bytes(range(32))))
    ctx.app.wait_toast("Imported 1 key(s) — signature verified against pinned bridge", timeout=15)


def case_c_a_changed_key_asks_first(ctx):
    start(ctx)
    before = ctx.bridge.count()
    scan(ctx, bundle(bytes([7]) * 32))
    ctx.tree.wait_text("This kit's key has changed", timeout=15)
    names = [n.name for n in ctx.tree.dialog()]
    assert any(n.startswith("Kit 11111111 signed these keys with a different key") for n in names), names
    ctx.shot("key-changed")
    ctx.tree.click_in_dialog("Keep the old key")
    assert not [r for r in ctx.bridge.requests(before) if r["path"] == "/api/keys/import"], "imported without trust"
    scan(ctx, bundle(bytes([7]) * 32))
    ctx.tree.wait_text("This kit's key has changed", timeout=15)
    ctx.tree.click_in_dialog("Trust the new key")
    ctx.app.wait_toast("New kit key saved, 1 key(s) imported", timeout=10)
    ctx.bridge.wait_request("POST", "/api/keys/import", since=before)
    scan(ctx, bundle(bytes([7]) * 32))
    ctx.app.wait_toast("Imported 1 key(s) — signature verified against pinned bridge", timeout=15)


def case_d_a_hex_key_becomes_the_sms_key(ctx):
    start(ctx)
    before = ctx.bridge.count()
    scan(ctx, KEY)
    ctx.app.wait_toast("Key imported via QR", timeout=15)
    import json  # noqa: PLC0415

    put = ctx.bridge.wait_request("PUT", "/api/interfaces/cellular_0/transforms", since=before)["body"]
    assert KEY in json.dumps(put), put


def case_e_anything_else_is_refused(ctx):
    start(ctx)
    scan(ctx, "hello from a poster")
    ctx.app.wait_toast("QR code doesn't contain a valid key or bundle", timeout=15)
