#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Record the answers of a live Bridge to every call the app makes, as the scripted Bridge's
# raw material: one JSON file per call under tests/fixtures/recorded/<date>-<bridge sha8>/.
# Runs against 127.0.0.1:6050 (or $1); writes to $2 (default: a directory named after today and
# the Bridge's commit). The scenarios in tests/fixtures/scenarios.py start from these files.
set -u
B=${1:-http://127.0.0.1:6050}
sha=$(curl -s -m 5 "$B/api/version" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("commit") or d.get("git_commit") or d.get("version") or "unknown")[:8])' 2>/dev/null || echo unknown)
D=${2:-tests/fixtures/recorded/$(date +%Y-%m-%d)-$sha}
mkdir -p "$D"
calls="
status
nodes
messages?limit=200
packets?limit=200
messages/stats
iridium/modem
iridium/signal
routing/hub
sos/status
deadman
keys/stats
cellular/status
cellular/sms?limit=200
mesh/ble/status
config
aprs/status
tak/enroll/status
rns/status
access-rules
interfaces
interfaces/health
object-groups
failover-groups
deliveries
deliveries/stats
audit?limit=50
audit/signer
credentials
devices/health
topology
version
routing/config
"
for c in $calls; do
    name=$(echo "$c" | tr '/?=&' '____')
    code=$(curl -s -m 8 -o "$D/$name.json" -w '%{http_code}' "$B/api/$c")
    echo "$code GET /api/$c -> $name.json"
    [ "$code" = 200 ] || rm -f "$D/$name.json"
done
echo "recorded in $D"
