#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run the end-to-end tests on the bench phone from a machine that reaches it, and bring the
# report back:
#
#   E2E_PHONE="ssh -i ~/.ssh/key user@phone" [E2E_HOP="ssh -i ~/.ssh/key user@laptop"] \
#     tools/e2e-run.sh [--tiers h] [--installed] [--out DIR] [--cases h_home ...]
#
# The repo's app/, tests/ and tools/ go to the phone as one tarball (a file, never a command's
# stdin, so a nested ssh cannot eat it); tools/e2e-remote.sh runs there, in a private headless
# session (tests/e2e/headless.sh), against the app in the tarball or the installed one
# (--installed); report.json, summary.txt, the run log and every case's captures come back to
# --out (default: ~/bench-data/meshsat-linux/e2e/<stamp>).
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
TIERS=h; INSTALLED=0; OUT=""; CASES=()
while [ $# -gt 0 ]; do
    case "$1" in
        --tiers) TIERS=$2; shift 2 ;;
        --installed) INSTALLED=1; shift ;;
        --out) OUT=$2; shift 2 ;;
        --cases) shift; while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do CASES+=("$1"); shift; done ;;
        *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
: "${E2E_PHONE:?E2E_PHONE: the ssh command that reaches the phone}"
HOP=${E2E_HOP:-}
OUT=${OUT:-$HOME/bench-data/meshsat-linux/e2e/$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"
remote() {  # remote <command with no single quotes>; stdin passes through both hops
    if [ -n "$HOP" ]; then $HOP "$E2E_PHONE '$1'"; else $E2E_PHONE "$1"; fi
}
BUNDLE=$(mktemp /tmp/meshsat-e2e-XXXXXX.tgz)
tar czf "$BUNDLE" -C "$HERE" app tests tools
echo "bundle: $(du -h "$BUNDLE" | cut -f1)"
remote "mkdir -p /tmp/meshsat-e2e && cat > /tmp/meshsat-e2e/bundle.tgz" < "$BUNDLE"
rm -f "$BUNDLE"
remote "cd /tmp/meshsat-e2e && rm -rf tree && mkdir tree && tar xzf bundle.tgz -C tree && bash tree/tools/e2e-remote.sh $TIERS $INSTALLED ${CASES[*]}" </dev/null
remote "cat /tmp/meshsat-e2e/out.tgz" </dev/null > "$OUT/out.tgz"
tar xzf "$OUT/out.tgz" -C "$OUT" && rm -f "$OUT/out.tgz"
echo "report: $OUT/out/summary.txt"
cat "$OUT/out/summary.txt" 2>/dev/null
