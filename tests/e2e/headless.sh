#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# A private session for the end-to-end tests on a phone or any Linux with phoc: its own runtime
# directory (so its Wayland socket and its accessibility bus never touch the user's session),
# its own session bus (dbus-run-session), a headless phoc at the phone's geometry, and the
# accessibility bus switched on; then the runner inside it:
#
#   tests/e2e/headless.sh --tiers h --out /tmp/meshsat-e2e/out [--app-dir app]
#
# Needs phoc, dbus-run-session, at-spi2-core, gir1.2-atspi-2.0, grim; every argument goes to
# tests/e2e/run.py. Nothing of the user's session is read or changed.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
B=${MESHSAT_E2E_DIR:-/tmp/meshsat-e2e-session}
R=$B/run
rm -rf "$R"; mkdir -p "$R"; chmod 700 "$R"
export XDG_RUNTIME_DIR=$R
export LC_ALL=C.UTF-8 TZ=${TZ:-UTC} GTK_A11Y=atspi GSK_RENDERER=cairo
# Settings stay in memory. The app under test reads its settings from its own directories, but a
# write through dconf reaches the person's real settings: the session bus's dconf service writes
# to ~/.config. The test notifier's offer of Phosh's plugins would otherwise replace the owner's
# own plugin lists.
export GSETTINGS_BACKEND=memory
unset WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
cat > "$B/inside.sh" <<IN
#!/bin/bash
set -u
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
phoc -C /usr/share/phosh/phoc.ini > "$B/phoc.log" 2>&1 &
PHOC=\$!
for i in \$(seq 1 50); do ls "$R"/wayland-* >/dev/null 2>&1 && break; sleep 0.2; done
export WAYLAND_DISPLAY=\$(basename "\$(ls "$R"/wayland-* | grep -v lock | head -1)")
gdbus call --session --dest org.a11y.Bus --object-path /org/a11y/bus --method org.freedesktop.DBus.Properties.Set org.a11y.Status IsEnabled '<true>' >/dev/null 2>&1
cd "$ROOT" && python3 -m tests.e2e.run "\$@"
STATUS=\$?
kill \$PHOC 2>/dev/null; sleep 0.3
exit \$STATUS
IN
chmod +x "$B/inside.sh"
exec dbus-run-session -- "$B/inside.sh" "$@" </dev/null
