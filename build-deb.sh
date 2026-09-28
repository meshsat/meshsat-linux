#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the one meshsat package: the node daemon, its configuration, Meshtastic's web client,
# the watchdog, the MeshSat Bridge and the app, as one .deb installed with one command.
#
#   sh build-deb.sh --version 0.1.0 --inputs ~/build/meshsat-linux/inputs
#
# Inputs, all pinned here and checked by sha256 where they come from elsewhere:
#   $INPUTS/meshtasticd          built on a PinePhone from meshsat-firmware (packaging/build-daemon.sh
#                                of meshsat-lora-backplate), stripped
#   $INPUTS/lora-listen, bridge-selftest   built there from meshsat-lora-backplate
#   $INPUTS/meshsat-arm64        the Bridge, out of its container image (fetch-bridge.sh <tag>): the
#                                pipeline's bare `build` artifact lacks the web interface
#   $INPUTS/web-build-<ver>.tar  meshtastic/web release bundle
#   $BACKPLATE                   a checkout of meshsat-lora-backplate at the pinned commit
set -eu

VERSION=0.3.0
ARCH=arm64
INPUTS=$HOME/build/meshsat-linux/inputs
HERE=$(cd "$(dirname "$0")" && pwd)
BACKPLATE=${MESHSAT_BACKPLATE_DIR:-$HERE/../meshsat-lora-backplate}
BACKPLATE_COMMIT=f80fa16
WEB_VERSION=v2.7.2
WEB_SHA256=62657b85b4c24af4d44da2932b64143abdbf6e65a79fcb51fd0801d9540616e2
DAEMON_SHA256=96b02d077d99b1f4d9a44e9882f571bf66cd3f9128550394989298dc24b7b1d4
FIRMWARE_COMMIT=6777ecc53657b3f5a6684a78e4f906f6e12ee042

while [ $# -gt 0 ]; do
    case "$1" in
        --version) VERSION=$2; shift 2 ;;
        --arch) ARCH=$2; shift 2 ;;
        --inputs) INPUTS=$2; shift 2 ;;
        --backplate) BACKPLATE=$2; shift 2 ;;
        --daemon-sha256) DAEMON_SHA256=$2; shift 2 ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "build-deb: $*"; }
need() { [ -e "$1" ] || { echo "missing input: $1" >&2; exit 1; }; }
need "$INPUTS/meshtasticd"; need "$INPUTS/lora-listen"; need "$INPUTS/bridge-selftest"; need "$INPUTS/meshsat-$ARCH"
need "$INPUTS/web-build-$WEB_VERSION.tar"; need "$BACKPLATE/packaging/install.sh"
echo "$WEB_SHA256  $INPUTS/web-build-$WEB_VERSION.tar" | sha256sum -c --quiet
echo "$DAEMON_SHA256  $INPUTS/meshtasticd" | sha256sum -c --quiet
at=$(git -C "$BACKPLATE" rev-parse --short "$BACKPLATE_COMMIT" 2>/dev/null || true)
head=$(git -C "$BACKPLATE" rev-parse --short HEAD 2>/dev/null || echo unknown)
if [ "$head" != "$at" ]; then say "warning: $BACKPLATE is at $head, the pinned commit is $BACKPLATE_COMMIT"; fi

ROOT=$HERE/build/root
rm -rf "$ROOT"; mkdir -p "$ROOT"
P="$BACKPLATE/packaging"

# Binaries
install -D -m 0755 "$INPUTS/meshtasticd" "$ROOT/usr/bin/meshtasticd"
install -D -m 0755 "$INPUTS/meshsat-$ARCH" "$ROOT/usr/bin/meshsat"
strip --strip-unneeded "$ROOT/usr/bin/meshsat" 2>/dev/null || true
install -D -m 0755 "$HERE/bin/meshsat-app" "$ROOT/usr/bin/meshsat-app"
install -D -m 0755 "$P/bin/meshsat-node-channels" "$ROOT/usr/bin/meshsat-node-channels"
install -D -m 0755 "$INPUTS/lora-listen" "$ROOT/usr/lib/meshsat/bin/lora-listen"
install -D -m 0755 "$INPUTS/bridge-selftest" "$ROOT/usr/lib/meshsat/bin/bridge-selftest"
mkdir -p "$ROOT/usr/lib/meshsat/app"
cp -r "$HERE/app/meshsat" "$ROOT/usr/lib/meshsat/app/meshsat"
find "$ROOT/usr/lib/meshsat/app" -name "__pycache__" -prune -exec rm -rf {} +
chmod -R go+rX "$ROOT/usr/lib/meshsat/app"
install -D -m 0644 "$P/watchdog/meshsat_radio_watch.py" "$ROOT/usr/lib/meshsat/watchdog/meshsat_radio_watch.py"
install -D -m 0644 "$BACKPLATE/tools/node-setup/set-channels.py" "$ROOT/usr/lib/meshsat/node-setup/set-channels.py"

# Configuration (conffiles) and the bus
install -D -m 0644 "$P/meshtasticd/config.yaml" "$ROOT/etc/meshtasticd/config.yaml"
install -D -m 0644 "$P/meshtasticd/config.d/lora-pinedio-backcover.yaml" "$ROOT/etc/meshtasticd/config.d/lora-pinedio-backcover.yaml"
install -D -m 0644 "$HERE/package/rootfs/etc/meshsat/bridge.env" "$ROOT/etc/meshsat/bridge.env"
install -D -m 0644 "$P/modules-load.d/meshsat-node.conf" "$ROOT/etc/modules-load.d/meshsat-node.conf"
install -D -m 0644 "$P/udev/60-meshsat-node.rules" "$ROOT/etc/udev/rules.d/60-meshsat-node.rules"
install -D -m 0644 "$P/modprobe.d/meshsat-no-keyboard.conf" "$ROOT/etc/modprobe.d/meshsat-no-keyboard.conf"
# The Bridge's service user may use ModemManager (SMS through the phone's SIM)
install -D -m 0644 "$HERE/package/rootfs/etc/polkit-1/rules.d/50-meshsat.rules" "$ROOT/etc/polkit-1/rules.d/50-meshsat.rules"

# Units
install -D -m 0644 "$P/systemd/meshtasticd.service" "$ROOT/lib/systemd/system/meshtasticd.service"
install -D -m 0644 "$P/systemd/meshsat-radio-watch.service" "$ROOT/lib/systemd/system/meshsat-radio-watch.service"
install -D -m 0644 "$P/systemd/meshsat-radio-watch.timer" "$ROOT/lib/systemd/system/meshsat-radio-watch.timer"
install -D -m 0644 "$HERE/package/rootfs/lib/systemd/system/meshsat-bridge.service" "$ROOT/lib/systemd/system/meshsat-bridge.service"

# Meshtastic's web client, uncompressed: the Linux web server serves the path it is asked for
mkdir -p "$ROOT/usr/share/meshtasticd/web"
tar xf "$INPUTS/web-build-$WEB_VERSION.tar" -C "$ROOT/usr/share/meshtasticd/web"
find "$ROOT/usr/share/meshtasticd/web" -name '*.gz' -exec gunzip -f {} \;

# The app in the app grid
install -D -m 0644 "$HERE/package/rootfs/usr/share/applications/net.meshsat.Bridge.desktop" "$ROOT/usr/share/applications/net.meshsat.Bridge.desktop"
install -D -m 0644 "$HERE/package/rootfs/usr/share/metainfo/net.meshsat.Bridge.metainfo.xml" "$ROOT/usr/share/metainfo/net.meshsat.Bridge.metainfo.xml"
python3 "$HERE/package/make-icons.py" "$HERE/app/meshsat/brand/app-icon-1024.png" "$ROOT/usr/share/icons/hicolor" >/dev/null
# The apps' symbolic icons (Material and MeshSat's own), in the icon theme so GTK recolours them
install -d "$ROOT/usr/share/icons/hicolor/scalable/actions"
install -m 0644 "$HERE"/app/meshsat/icons/hicolor/scalable/actions/meshsat-*-symbolic.svg "$ROOT/usr/share/icons/hicolor/scalable/actions/"

# IBM Plex, the apps' typeface (OFL), the same files the Android and iOS apps carry
install -d "$ROOT/usr/share/fonts/truetype/meshsat"
install -m 0644 "$HERE"/package/fonts/*.ttf "$ROOT/usr/share/fonts/truetype/meshsat/"
install -D -m 0644 "$HERE/package/fonts/LICENSE.txt" "$ROOT/usr/share/doc/meshsat/IBM-Plex-LICENSE.txt"

# Documentation
install -D -m 0644 "$HERE/LICENSE" "$ROOT/usr/share/doc/meshsat/copyright"
install -D -m 0644 "$HERE/docs/INSTALL.md" "$ROOT/usr/share/doc/meshsat/INSTALL.md"
{
    echo "meshsat $VERSION, built $(date -u '+%F %T UTC')"
    echo "meshtasticd: meshsat-firmware $FIRMWARE_COMMIT, env meshsat-pinephone-pro, sha256 $DAEMON_SHA256"
    echo "node packaging: meshsat-lora-backplate $BACKPLATE_COMMIT"
    echo "bridge: meshsat $(sha256sum "$INPUTS/meshsat-$ARCH" | cut -c1-16)…"
    echo "web client: meshtastic/web $WEB_VERSION"
} > "$ROOT/usr/share/doc/meshsat/PROVENANCE"

# Control
mkdir -p "$ROOT/DEBIAN"
SIZE=$(du -sk "$ROOT" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@ARCH@/$ARCH/" -e "s/@SIZE@/$SIZE/" "$HERE/package/DEBIAN/control.in" > "$ROOT/DEBIAN/control"
install -m 0755 "$HERE/package/DEBIAN/preinst" "$ROOT/DEBIAN/preinst"
install -m 0755 "$HERE/package/DEBIAN/postinst" "$ROOT/DEBIAN/postinst"
install -m 0755 "$HERE/package/DEBIAN/prerm" "$ROOT/DEBIAN/prerm"
install -m 0755 "$HERE/package/DEBIAN/postrm" "$ROOT/DEBIAN/postrm"
install -m 0644 "$HERE/package/DEBIAN/conffiles" "$ROOT/DEBIAN/conffiles"

OUT="$HERE/build/meshsat_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group -Zxz --build "$ROOT" "$OUT" >/dev/null
sha256sum "$OUT"
say "$(ls -l "$OUT" | awk '{printf "%.1f MB", $5/1048576}') $OUT"
