# SPDX-License-Identifier: GPL-3.0-or-later
"""The rest of Advanced against a real, scratch Bridge: a certificate imported in the app is the
one the Bridge stores (its subject, its SHA-256, its expiry), and deleted again; a text a rule
passes on is an audit entry the app shows, checks and saves, and the saved copy's hashes
check."""
import hashlib
import time

from driver import BridgeError

SCENARIO = None  # the scratch Bridge
# A self-signed leaf certificate made for this test (openssl, 29 Sep 2026; CA:FALSE, since the Bridge
# keeps the subject, expiry and fingerprint of a leaf only, MESHSAT-1404): CN e2e.meshsat.test,
# until 25 Sep 2036, SHA-256 84:7A:3C:55:67:D2:8A:0A:...
CERT = b"""-----BEGIN CERTIFICATE-----
MIIBtDCCAVqgAwIBAgIUfPvbp5TM2hfLrOGkjs4jXAtBu/wwCgYIKoZIzj0EAwIw
MTEZMBcGA1UEAwwQZTJlLm1lc2hzYXQudGVzdDEUMBIGA1UECgwLTWVzaFNhdCBl
MmUwHhcNMjYwOTI4MjI0NTUyWhcNMzYwOTI1MjI0NTUyWjAxMRkwFwYDVQQDDBBl
MmUubWVzaHNhdC50ZXN0MRQwEgYDVQQKDAtNZXNoU2F0IGUyZTBZMBMGByqGSM49
AgEGCCqGSM49AwEHA0IABLWkBZk7Omc2u1ZC8WhC18ms+GBeA3b58cNBcdKHozjI
TbD+ZV0plPMni6CCSLjhye7THzPP2F75fHW2PJxYhIKjUDBOMB0GA1UdDgQWBBT1
zMbQHEYYtbRTzhenHCXWMYN7NDAfBgNVHSMEGDAWgBT1zMbQHEYYtbRTzhenHCXW
MYN7NDAMBgNVHRMBAf8EAjAAMAoGCCqGSM49BAMCA0gAMEUCIQDkjTUBtiDxrsaA
NGBt2wK3nVktuySN+Z7J2z8IazvlSAIgYSoF1Jp3LYodtgGvVzGoWMicgsZV6sY6
inOjoN86n44=
-----END CERTIFICATE-----
"""


def case_a_certificate_is_the_one_the_bridge_stores(ctx):
    ctx.app.open("credentials")
    ctx.tree.wait_text("No credentials stored", timeout=10)
    ctx.app.mark()
    ctx.app.pick(CERT)
    ctx.tree.click("Import PEM")
    ctx.app.wait_toast("Certificate imported", timeout=10)
    stored = (ctx.bridge.get("/api/credentials") or {}).get("credentials") or []
    ctx.note(f"stored: {stored}")
    assert len(stored) == 1 and stored[0].get("cert_subject") == "e2e.meshsat.test", stored
    ctx.tree.wait_text("picked.pem", timeout=10)
    ctx.tree.wait_text("SHA-256: 84:7A:3C:55:67:D2:8A:0A")
    ctx.tree.wait_text("Subject: e2e.meshsat.test")
    ctx.tree.wait_text("Expires: 2036-09-25")
    ctx.shot("stored")
    ctx.tree.click_after("picked.pem", "Delete")
    ctx.tree.click_in_dialog("Delete")
    ctx.tree.wait_text("No credentials stored", timeout=10)
    assert not ((ctx.bridge.get("/api/credentials") or {}).get("credentials") or []), "the Bridge still has it"
    ctx.app.pick(None)
    ctx.app.open("home")


def case_a_passed_on_text_is_an_audit_entry_the_copy_can_check(ctx):
    # A rule that passes mesh texts to the 9704 link, its gateway on (a port that does not exist:
    # nothing can leave), and one text from the mesh through the Bridge's own inbound path.
    status, rule = ctx.bridge.call("POST", "/api/access-rules", {"interface_id": "mesh_0", "direction": "ingress", "name": "e2e-audit", "enabled": True, "action": "forward",
                                                                 "forward_to": "iridium_imt_0", "filters": "{}", "priority": 1, "qos_level": 1})
    gw, _ = ctx.bridge.call("PUT", "/api/gateways/iridium_imt", {"enabled": True, "config": {}})
    sent, answer = ctx.bridge.call("POST", "/api/messages/simulate-mesh-rx", {"text": "e2e audit text"})
    ctx.note(f"rule {status} {rule}; gateway {gw}; simulate {sent} {answer}")
    if status != 201 or sent != 200:
        raise BridgeError(f"the scratch Bridge would not pass a text on (rule {status}, simulate {sent} {answer})")
    count = 0
    deadline = time.time() + 15
    while time.time() < deadline and count == 0:
        count = int((ctx.bridge.get("/api/audit/count") or {}).get("count") or 0)
        time.sleep(0.5)
    if count == 0:
        raise BridgeError("the scratch Bridge wrote no audit entry for the text it passed on")
    ctx.app.open("audit")
    ctx.tree.wait_text(f"{count} entr", timeout=10)
    ctx.tree.wait_text("Queued")
    ctx.tree.wait_text("Rule “e2e-audit”", timeout=10)
    ctx.shot("audit")
    ctx.app.mark()
    ctx.tree.click("Check the log")
    ctx.tree.wait_text(" are as they were written.", timeout=10)
    ctx.tree.click("Save a copy")
    ctx.app.wait_toast("Audit log saved", timeout=15)
    name, copy = next(iter(ctx.app.saved().items()))
    rows = [line.split("\t") for line in copy.splitlines()[6:] if line]
    assert len(rows) == count, (len(rows), count)
    # The copy is checkable on its own: each hash is sha256(prev_hash + timestamp + event + detail), and chains.
    previous = rows[0][8]
    for row in rows:
        entry_id, stamp, _iface, _dir, event, _del, _rule, detail, prev_hash, digest = row
        assert prev_hash == previous, f"entry {entry_id} does not chain"
        assert hashlib.sha256((prev_hash + stamp + event + detail).encode()).hexdigest() == digest, f"entry {entry_id} does not check"
        previous = digest
    ctx.note(f"{name}: {len(rows)} entries, the chain checks")
    ctx.app.open("home")
