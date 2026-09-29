# SPDX-License-Identifier: GPL-3.0-or-later
"""Hub provisioning by QR code and by link (crypto/ProvisionImporter.kt, crypto/ProvisionClaim.kt,
ui/components/ProvisionClaimHost.kt, ProvisionLinkDialog.kt): the Hub's QR code or link
`meshsat://provision/{bridge}/{nonce}?hub={host}` is claimed at
`https://{host}/api/bridges/{bridge}/provision/{nonce}`, which answers the settings once (503
with Retry-After while its brokers catch up); an inline code carries the settings itself. The
app then writes them to the Bridge (PUT /api/routing/hub) and restarts it. Pure: the network
and the clock are passed in."""
import base64
import json
import time

PREFIX = "meshsat://provision/"
CLAIM_WAIT_MAX_MS = 120_000
HEX = set("0123456789abcdef")

# ── Words ────────────────────────────────────────────────────────────────────────────────────
WAITING_TITLE = "Getting the Hub's settings"
WAITING_TEXT = ("The Hub gives this phone its new password once all its servers accept it. That usually takes about a minute. "
                "You can leave this screen; the phone keeps asking.")
HIDE = "Hide"
CANCEL = "Cancel"
READY_TITLE = "Use these Hub settings?"
PROVISION = "Provision"
FAILED_TITLE = "No settings from the Hub"
OK = "OK"
LINK_TITLE = "Provision Hub Connection"
EXPIRED_404 = "Provisioning token expired or already used. Generate a new QR from the Hub."
EXPIRED_410 = "Provisioning token expired (>30 minutes). Generate a new QR."
STILL_WAITING = "The Hub is still getting the new credentials ready. Wait a minute, then scan the same code again."
NO_SETTINGS = "The Hub did not hand out the settings"
SCAN_HUB = "Scan the Hub's QR code"


def waited(seconds: int) -> str:
    return f"Waiting for the Hub, {max(0, int(seconds))} s"


def card_wait(seconds: int) -> str:
    """The Hub card's line while a claim waits (SettingsScreen.kt:1664-1680)."""
    return f"Getting the Hub's settings, {max(0, int(seconds))} s"


def ready_text(bridge_id: str) -> str:
    return f'This phone becomes bridge "{bridge_id}" on the Hub. Its current Hub settings are replaced.'


def ready_lines(bundle: dict) -> list:
    out = [f"Hub: {bundle.get('mqtt', '')}"]
    if bundle.get("cert_exp"):
        out.append(f"Certificate expires: {bundle['cert_exp']}")
    if bundle.get("ret_tcp"):
        out.append(f"Reticulum: {bundle['ret_tcp']}")
    return out


def applied(bridge_id: str) -> str:
    return f"Hub provisioned: {bridge_id}. Connecting to the Hub."


def link_text(bridge_id: str, host: str) -> str:
    return (f'Provision this phone as bridge "{bridge_id}" with credentials from {host}?\n\n'
            "This will overwrite existing Hub settings. Only continue if you generated this link on your own Hub.")


def link_host(host: str) -> str:
    return f"Hub: {host}"


def rejected(reason: str) -> str:
    return f"Provisioning link rejected: {reason}"


def http_error(code: int) -> str:
    return f"Hub returned HTTP {code}. Try again or generate a new QR."


def unreachable(host: str) -> str:
    return f"Cannot reach Hub at {host}. Check network connectivity."


def failed(reason) -> str:
    return f"Provisioning failed: {reason}"


def not_saved(reason) -> str:
    return f"Could not save the Hub settings: {reason}"


class ProvisionError(Exception):
    """A provisioning failure in Android's own words (shown as it is)."""


# ── Parsing (ProvisionImporter.kt:48-119) ────────────────────────────────────────────────────
def parse_nonce(url: str) -> dict:
    """{bridge_id, nonce, hub_host} of a nonce link; ValueError with Android's message."""
    rest = url[len(PREFIX):]
    q = rest.find("?")
    if q <= 0:
        raise ValueError("Missing ?hub= parameter")
    parts = rest[:q].split("/")
    if len(parts) != 2:
        raise ValueError("Expected {bid}/{nonce}")
    bid, nonce = parts
    if not bid.strip():
        raise ValueError("Empty bridge ID")
    if len(nonce) != 32 or not set(nonce) <= HEX:
        raise ValueError("Invalid nonce: must be 32 hex chars")
    hub = ""
    for pair in rest[q + 1:].split("&"):
        key, _sep, value = pair.partition("=")
        if key == "hub":
            hub = value
    if not hub.strip():
        raise ValueError("Missing hub host")
    return {"bridge_id": bid, "nonce": nonce, "hub_host": hub}


def parse_link(url: str) -> dict:
    """The link path (ProvisionImporter.parseLink): the nonce form only."""
    if not url.startswith(PREFIX):
        raise ValueError("Not a MeshSat provisioning link")
    if "?hub=" not in url:
        raise ValueError("Inline provisioning codes must be scanned in Settings")
    return parse_nonce(url)


def is_inline(url: str) -> bool:
    return url.startswith(PREFIX) and "?hub=" not in url


def bundle_from_json(text: str) -> dict:
    """The settings the Hub hands out, each field as optString reads it (missing = "")."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")

    def opt(key: str, default: str = "") -> str:
        value = data.get(key, default)
        return "null" if value is None else str(value)

    return {"v": opt("v", "1"), "bid": opt("bid"), "mqtt": opt("mqtt"), "user": opt("user"), "pass": opt("pass"), "cert": opt("cert"),
            "key": opt("key"), "ca": opt("ca"), "cert_exp": opt("cert_exp"), "ret_tcp": opt("ret_tcp")}


def inline_bundle(url: str) -> dict:
    raw = url[len(PREFIX):]
    try:
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(f"bad inline code: {error}") from error
    return bundle_from_json(text)


# ── The claim (ProvisionImporter.kt:121-198) ─────────────────────────────────────────────────
def claim_url(request: dict) -> str:
    return f"https://{request['hub_host']}/api/bridges/{request['bridge_id']}/provision/{request['nonce']}"


def retry_delay_ms(retry_after) -> int:
    """Retry-After clamped to 1-15 s; 5 s when absent or unreadable."""
    try:
        seconds = int(str(retry_after).strip()) if retry_after is not None else 5
    except ValueError:
        seconds = 5
    return max(1, min(15, seconds)) * 1000


def claim(request: dict, get, sleep=time.sleep, now_ms=None, on_wait=None, cancelled=lambda: False) -> dict:
    """The settings for a nonce link. `get(url) -> (status, headers, body text)` raises OSError
    for no connection; ProvisionError with Android's words for what the Hub refuses; waits
    through 503s until CLAIM_WAIT_MAX_MS. `on_wait(attempts)` after each 503."""
    now_ms = now_ms or (lambda: int(time.time() * 1000))
    deadline = now_ms() + CLAIM_WAIT_MAX_MS
    attempts = 0
    while True:
        if cancelled():
            raise ProvisionError("cancelled")
        try:
            status, headers, body = get(claim_url(request))
        except OSError as error:
            raise ProvisionError(unreachable(request["hub_host"])) from error
        if status == 200:
            try:
                return bundle_from_json(body)
            except ValueError as error:
                raise ProvisionError(unreachable(request["hub_host"])) from error
        if status == 503:
            wait = retry_delay_ms({k.lower(): v for k, v in (headers or {}).items()}.get("retry-after"))
            if now_ms() + wait > deadline:
                raise ProvisionError(STILL_WAITING)
            attempts += 1
            if on_wait is not None:
                on_wait(attempts)
            sleep(wait / 1000)
            continue
        if status == 404:
            raise ProvisionError(EXPIRED_404)
        if status == 410:
            raise ProvisionError(EXPIRED_410)
        raise ProvisionError(http_error(status))


def hub_body(bundle: dict) -> dict:
    """PUT /api/routing/hub from the settings: the CA always sent (the Bridge clears it when it
    is left out)."""
    return {"url": bundle.get("mqtt", ""), "bridge_id": bundle.get("bid", ""), "username": bundle.get("user", ""), "password": bundle.get("pass", ""),
            "tls_cert_pem": bundle.get("cert", ""), "tls_key_pem": bundle.get("key", ""), "tls_ca_pem": bundle.get("ca", "")}
