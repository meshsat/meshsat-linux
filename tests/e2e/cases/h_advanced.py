# SPDX-License-Identifier: GPL-3.0-or-later
"""The rest of Advanced (0.8.0): Mesh topology (TopologyScreen.kt), Audit log (AuditScreen.kt),
Certificates and keys (CredentialsScreen.kt), Encrypt or decrypt text (DecryptScreen.kt),
Diagnostics (SettingsScreen.kt's sections) and Node log (NodeLogScreen.kt), against the
scripted Bridge; every case starts from the scenario "advanced" afresh."""
import time

SCENARIO = "advanced"
VECTOR = "AAECAwQFBgcICQoL0kvJPXaIUWHuoqZ9V4uV7nuCNI/pwgQo/xPd5EsnPE4TdHqtVdeUmU0="  # the Bridge's construction, fixed nonce
PEM = b"-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIUe2e\n-----END CERTIFICATE-----\n"


def start(ctx, route: str, scenario: str = "advanced") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.refresh()
    ctx.app.open(route)


def case_topology_is_what_was_heard(ctx):
    start(ctx, "topology")
    for words in ("Pinch to zoom, drag to move.", "Heard in 15 min", "1 of 2", "Links", "Average SNR, heard directly", "5.5 dB", "Who hears whom",
                  "Your node hears MSPA", "MSPA hears Far Hill", "Nodes", "meshsat-pinephone-pro (your node)", "!52cb81e7  Custom hardware",
                  "Heard directly, SNR 5.5 dB, RSSI -60 dBm, Battery 78%", "2 hops away, Battery 40%", "Your node", "Heard in the last 15 min",
                  "Not heard for 15 min or more", "Recent link", "Older link"):
        ctx.tree.wait_text(words, timeout=10)
    assert any(t.startswith("SNR -3.3 dB, ") and t.endswith(", as it reported") for t in ctx.tree.texts()), "the reported hearing has no detail line"
    assert not ctx.tree.has_text("Links appear when nodes share who they hear."), "the Neighbor Info notice showed with a report in"
    ctx.shot("topology")


def case_topology_without_reports_or_others(ctx):
    start(ctx, "topology", "mesh-only")
    ctx.tree.wait_text("Links appear when nodes share who they hear. This needs Neighbor Info turned on in the nodes' module settings.", timeout=10)
    start(ctx, "topology", "one-node")
    ctx.tree.wait_text("Your node is listening.", timeout=10)
    ctx.tree.wait_text("Nodes appear here once they transmit on the mesh.")
    ctx.shot("topology-empty")
    ctx.app.open("home")


def case_audit_counts_filters_checks_and_saves(ctx):
    start(ctx, "audit")
    ctx.tree.wait_text("120 entries", timeout=10)
    ctx.tree.wait_text("Remote command refused")
    ctx.tree.wait_text("Mesh, sent")
    ctx.tree.wait_text("Message #120 · Rule “SOS to satellite”")
    ctx.shot("audit")
    ctx.app.mark()
    ctx.tree.click_containing("Signing key 082d35bc64aa")
    ctx.app.wait_toast("Signing key copied")
    ctx.tree.click("Satellite")
    ctx.tree.wait_text("Satellite, received", timeout=10)
    ctx.tree.wait_gone("Mesh, sent", timeout=10)
    ctx.tree.click("All links")
    ctx.tree.wait_text("Mesh, sent", timeout=10)
    ctx.tree.click("Check the log")
    ctx.tree.wait_text("The last 120 entries are as they were written.", timeout=10)
    ctx.tree.find("button", name="Show older entries")
    count = ctx.bridge.count()
    ctx.tree.click("Show older entries")
    ctx.bridge.wait_request("GET", "/api/audit?limit=200", since=count)
    ctx.tree.click("Save a copy")
    ctx.app.wait_toast("Audit log saved", timeout=10)
    saved = ctx.app.saved()
    assert len(saved) == 1, saved.keys()
    name, copy = next(iter(saved.items()))
    assert name.startswith("meshsat-audit-") and name.endswith(".txt"), name
    lines = copy.splitlines()
    assert lines[0] == "MeshSat audit log" and "Entries: 120" in lines, lines[:6]
    assert lines[-1].startswith("120\t") and lines[6].startswith("1\t"), (lines[6], lines[-1])
    ctx.note(f"saved {name}: {len(lines)} lines")


def case_audit_a_changed_log_says_where(ctx):
    ctx.bridge.scenario("advanced")
    ctx.bridge.fake.audit_broken_at = 40
    ctx.app.open("audit")
    ctx.tree.wait_text("120 entries", timeout=10)
    ctx.tree.click("Check the log")
    ctx.tree.wait_text("The log was changed after it was written.", timeout=10)
    ctx.tree.wait_text("Save a copy and keep it, then contact your MeshSat admin.")
    ctx.tree.wait_text("The first changed entry is number 41.")
    ctx.shot("audit-changed")


def case_credentials_cards_import_and_delete(ctx):
    start(ctx, "credentials")
    for words in ("hub.meshsat.net", "hub_mqtt", "mqtt_bundle", "SHA-256: 0A:1B:2C:3D:4E:5F:60:71", "Subject: CN=hub.meshsat.net", "v2", "soon.pem", "old.pem"):
        ctx.tree.wait_text(words, timeout=10)
    assert any(t.startswith("Expires: ") for t in ctx.tree.texts())
    ctx.shot("credentials")
    ctx.app.mark()
    before = ctx.bridge.count()
    ctx.app.pick(PEM)
    ctx.tree.click("Import PEM")
    upload = ctx.bridge.wait_request("POST", "/api/credentials/upload", since=before)
    assert 'filename="picked.pem"' in upload["body"].get("_raw", ""), upload["body"]
    ctx.app.wait_toast("Certificate imported")
    ctx.tree.wait_text("picked.pem", timeout=10)
    ctx.app.pick(b"not a certificate")
    ctx.tree.click("Import PEM")
    ctx.app.wait_toast("Import failed: no certificates or keys found in uploaded files")
    ctx.app.pick(None)
    count = ctx.bridge.count()
    ctx.tree.click_after("old.pem", "Delete")
    ctx.tree.wait_text("Delete Credential?")
    ctx.tree.wait_text("Remove 'old.pem' (local)? This cannot be undone.")
    ctx.tree.click_in_dialog("Cancel")
    assert not [r for r in ctx.bridge.requests(count) if r["method"] == "DELETE"], "Cancel deleted"
    ctx.tree.click_after("old.pem", "Delete")
    ctx.tree.click_in_dialog("Delete")
    ctx.bridge.wait_request("DELETE", "/api/credentials/cred-old", since=count)
    ctx.tree.wait_gone("old.pem", timeout=10)


def case_credentials_empty(ctx):
    start(ctx, "credentials", "mesh-only")
    ctx.tree.wait_text("No credentials stored", timeout=10)
    ctx.tree.wait_text("Import PEM files or receive via Hub sync")


def case_decrypt_with_the_links_key(ctx):
    start(ctx, "decrypt")
    ctx.tree.wait_text("Paste a base64 ciphertext from an SMS to decrypt it, or type plaintext to encrypt it.", timeout=10)
    ctx.tree.wait_gone("No encryption key configured. Go to Settings to set one.", timeout=10)
    ctx.tree.set_text("Input text", VECTOR)
    ctx.tree.click("Decrypt")
    ctx.tree.wait_text("Decrypted:", timeout=5)
    ctx.tree.wait_text("SOS position 47.3N 122.5W")
    ctx.shot("decrypted")
    ctx.tree.set_text("Input text", "field report: all clear at grid 4523")
    ctx.tree.click("Encrypt")
    ctx.tree.wait_text("Encrypted (base64):", timeout=5)
    cipher = next(t for t in ctx.tree.texts() if len(t) > 60 and " " not in t)
    ctx.tree.set_text("Input text", cipher)
    ctx.tree.click("Decrypt")
    ctx.tree.wait_text("field report: all clear at grid 4523", timeout=5)
    ctx.tree.set_text("Input text", "not base64 at all")
    ctx.tree.click("Decrypt")
    ctx.tree.wait_text("Decrypt failed: not base64", timeout=5)
    ctx.app.mark()
    ctx.tree.set_text("Input text", VECTOR)
    ctx.tree.click("Decrypt")
    ctx.tree.click("Copy")
    ctx.app.wait_toast("Copied to clipboard")


def case_decrypt_without_a_key(ctx):
    start(ctx, "decrypt", "mesh-only")
    ctx.tree.wait_text("No encryption key configured. Go to Settings to set one.", timeout=10)
    assert not ctx.tree.find("button", name="Encrypt").sensitive and not ctx.tree.find("button", name="Decrypt").sensitive


def case_diagnostics_health_and_the_service(ctx):
    start(ctx, "setup/diagnostics")
    for words in ("Link health", "mesh_0", "score: 85/100", "score: 40/100", "score: 0/100",
                  "Health = Signal(0.3) + SuccessRate(0.3) + Latency(0.2) + Cost(0.2). Scores update in real-time based on 24h delivery history.",
                  "Background service", "Start after a phone restart", "Restart Gateway Service", "Stop and restart all transports"):
        ctx.tree.wait_text(words, timeout=10)
    assert ctx.tree.switch("Start after a phone restart").checked, "the Bridge is enabled at boot"
    ctx.shot("diagnostics")
    ctx.app.mark()
    ctx.tree.toggle("Start after a phone restart")
    deadline = time.time() + 5
    while time.time() < deadline and ["pkexec", "systemctl", "disable", "meshsat-bridge.service"] not in ctx.app.commands():
        time.sleep(0.2)
    assert ["pkexec", "systemctl", "disable", "meshsat-bridge.service"] in ctx.app.commands(), ctx.app.commands()
    ctx.tree.click("Restart")
    ctx.tree.wait_text("Restart Service?")
    ctx.tree.wait_text("This will disconnect all transports and restart the gateway service. It should take a few seconds.")
    ctx.tree.click_in_dialog("Cancel")
    assert ["pkexec", "systemctl", "restart", "meshsat-bridge.service"] not in ctx.app.commands()
    ctx.tree.click("Restart")
    ctx.tree.click_in_dialog("Restart")
    ctx.app.wait_toast("Service restarting...")
    assert ["pkexec", "systemctl", "restart", "meshsat-bridge.service"] in ctx.app.commands(), ctx.app.commands()


def case_node_log_follows_pauses_clears_and_shares(ctx):
    ctx.app.journal(["INFO  | 23:56:38 1890.659 [DeviceTelemetry] Sending local stats: uptime=1890",
                     "WARN  | 23:56:40 1892.001 [Router] e2e warning line"])
    start(ctx, "nodelog")
    ctx.tree.wait_text("The node runs on this phone: this is its own log, as its service writes it. Newest at the bottom.", timeout=10)
    ctx.tree.wait_text("23:56:38 INFO [DeviceTelemetry] Sending local stats: uptime=1890", timeout=10)
    ctx.tree.wait_text("23:56:40 WARN [Router] e2e warning line")
    ctx.app.journal(["INFO  | 23:57:00 1912.0 [Router] e2e first new line"])
    ctx.tree.wait_text("23:57:00 INFO [Router] e2e first new line", timeout=10)
    ctx.tree.click("Pause")
    ctx.app.journal(["INFO  | 23:57:10 1922.0 [Router] e2e held line"])
    time.sleep(5)
    assert not ctx.tree.has_text("e2e held line"), "a line showed while paused"
    ctx.tree.click("Resume")
    ctx.tree.wait_text("23:57:10 INFO [Router] e2e held line", timeout=10)
    ctx.shot("nodelog")
    ctx.app.mark()
    ctx.tree.click("Share")
    ctx.app.wait_toast("Node log saved", timeout=10)
    saved = ctx.app.saved()
    name, copy = next((n, c) for n, c in saved.items() if n.startswith("meshsat-node-log-"))
    assert "23:57:10 INFO [Router] e2e held line" in copy, copy[-300:]
    ctx.tree.click("Clear")
    ctx.tree.wait_gone("e2e held line", timeout=5)
    ctx.tree.click("Share")
    ctx.app.wait_toast("Nothing to share yet.")
    ctx.app.open("home")
