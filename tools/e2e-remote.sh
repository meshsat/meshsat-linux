#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The phone's side of tools/e2e-run.sh: unpack the bundle, run the tiers in a private headless
# session, pack the report. Arguments: <tiers> <installed 0|1> [case patterns...].
set -u
TIERS=${1:-h}; INSTALLED=${2:-0}; shift 2 2>/dev/null
B=/tmp/meshsat-e2e
cd "$B" || exit 2
rm -rf tree out; mkdir tree; tar xzf bundle.tgz -C tree || exit 2
cd tree || exit 2
APPDIR=(); [ "$INSTALLED" = 1 ] || APPDIR=(--app-dir "$B/tree/app")
CASES=(); [ $# -eq 0 ] || CASES=(--cases "$@")
timeout 1500 bash tests/e2e/headless.sh --tiers "$TIERS" --out "$B/out" "${APPDIR[@]}" "${CASES[@]}" > "$B/run.log" 2>&1
STATUS=$?
grep -v "dbus-daemon\|xdg-desktop-portal\|SpiRegistry\|^$" "$B/run.log" | tail -60
echo "run exit: $STATUS"
cd "$B" && cp run.log out/ 2>/dev/null; tar czf out.tgz out
exit $STATUS
