#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Screen captures of the installed app on a Phosh phone, one per tab and Setup page, for the
# parity check against MeshSat Android and iOS. Runs ON the phone, inside the user's session
# (over ssh: `ssh phone bash -s < tools/capture-phone.sh > shots.tgz`), and writes a tar of
# PNGs to stdout. Needs grim and libglib2.0-bin (gapplication), both on Mobian.
#
# The app is started as the app grid starts it (its desktop entry) and walked with its own
# D-Bus actions (`tab`, `open`, `night`), so nothing here touches the screen or the node.
set -u
U=$(id -u)
export XDG_RUNTIME_DIR=/run/user/$U WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0} DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$U/bus
D=${1:-/tmp/meshsat-shots}
rm -rf "$D"; mkdir -p "$D"
{
    pkill -f "[p]ython3 -m meshsat"; sleep 1
    gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.SetActive false >/dev/null 2>&1
    gio launch /usr/share/applications/net.meshsat.Bridge.desktop
    sleep 8
    act() { gapplication action net.meshsat.Bridge "$@" 2>&1; sleep 0.5; }
    shot() { sleep "${2:-2}"; grim "$D/$1.png" 2>&1 && echo "shot $1"; }
    shot home 0
    for tab in messages map people setup; do act tab "'$tab'"; shot "$tab" $([ "$tab" = map ] && echo 7 || echo 2); done
    act open "'everyone'"; shot chat-everyone
    for page in node satellite passes hub safety messaging maps integrations radio advanced about; do act open "'$page'"; shot "setup-$page"; done
    act tab "'home'"; act night; shot home-night; act night
    echo "== app"; pgrep -fa "[p]ython3 -m meshsat"; meshsat-app --version; dpkg-query -W meshsat
} > "$D/capture.log" 2>&1
tar czf - -C "$(dirname "$D")" "$(basename "$D")"
