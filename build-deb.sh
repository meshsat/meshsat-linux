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

VERSION=1.0.3
ARCH=arm64
INPUTS=$HOME/build/meshsat-linux/inputs
HERE=$(cd "$(dirname "$0")" && pwd)
BACKPLATE=${MESHSAT_BACKPLATE_DIR:-$HERE/../meshsat-lora-backplate}
BACKPLATE_COMMIT=f80fa16
# The Bridge's container image this package takes its binary from (fetch-bridge.sh <tag>):
# the first 8 characters of the meshsat commit the image was built from.
BRIDGE_TAG=cad98d15
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
# The node daemon drives the PinePhone's LoRa back cover: it is built for arm64 phones only.
# On any other architecture the package is the Bridge and the app, with a node over Bluetooth.
NODE=0; [ "$ARCH" = arm64 ] && NODE=1
need "$INPUTS/meshsat-$ARCH"
if [ "$NODE" = 1 ]; then
    need "$INPUTS/meshtasticd"; need "$INPUTS/lora-listen"; need "$INPUTS/bridge-selftest"
    need "$INPUTS/web-build-$WEB_VERSION.tar"; need "$BACKPLATE/packaging/install.sh"
    echo "$WEB_SHA256  $INPUTS/web-build-$WEB_VERSION.tar" | sha256sum -c --quiet
    echo "$DAEMON_SHA256  $INPUTS/meshtasticd" | sha256sum -c --quiet
    at=$(git -C "$BACKPLATE" rev-parse --short "$BACKPLATE_COMMIT" 2>/dev/null || true)
    head=$(git -C "$BACKPLATE" rev-parse --short HEAD 2>/dev/null || echo unknown)
    if [ "$head" != "$at" ]; then say "warning: $BACKPLATE is at $head, the pinned commit is $BACKPLATE_COMMIT"; fi
fi

ROOT=$HERE/build/root
rm -rf "$ROOT"; mkdir -p "$ROOT"
P="$BACKPLATE/packaging"

# Binaries
install -D -m 0755 "$INPUTS/meshsat-$ARCH" "$ROOT/usr/bin/meshsat"
strip --strip-unneeded "$ROOT/usr/bin/meshsat" 2>/dev/null || true
install -D -m 0755 "$HERE/bin/meshsat-app" "$ROOT/usr/bin/meshsat-app"
mkdir -p "$ROOT/usr/lib/meshsat/app"
cp -r "$HERE/app/meshsat" "$ROOT/usr/lib/meshsat/app/meshsat"
find "$ROOT/usr/lib/meshsat/app" -name "__pycache__" -prune -exec rm -rf {} +
chmod -R go+rX "$ROOT/usr/lib/meshsat/app"
install -D -m 0644 "$HERE/package/rootfs/etc/meshsat/bridge.env" "$ROOT/etc/meshsat/bridge.env"
# The Bridge's service user may use ModemManager (SMS through the phone's SIM)
install -D -m 0644 "$HERE/package/rootfs/etc/polkit-1/rules.d/50-meshsat.rules" "$ROOT/etc/polkit-1/rules.d/50-meshsat.rules"
install -D -m 0644 "$HERE/package/rootfs/lib/systemd/system/meshsat-bridge.service" "$ROOT/lib/systemd/system/meshsat-bridge.service"
# Which node this device has (the LoRa back cover, or a node over Bluetooth), decided before the
# daemon and the Bridge start; the daemon and the watchdog run only when a cover answered.
install -D -m 0755 "$HERE/package/rootfs/usr/lib/meshsat/bin/meshsat-hardware" "$ROOT/usr/lib/meshsat/bin/meshsat-hardware"
install -D -m 0644 "$HERE/package/rootfs/lib/systemd/system/meshsat-hardware.service" "$ROOT/lib/systemd/system/meshsat-hardware.service"
# Who reaches the Bridge and the node over the network: this device only, unless the person
# shares the Bridge (the app's Diagnostics switch runs meshsat-share through pkexec).
install -D -m 0755 "$HERE/package/rootfs/usr/lib/meshsat/bin/meshsat-share" "$ROOT/usr/lib/meshsat/bin/meshsat-share"
install -D -m 0644 "$HERE/package/rootfs/lib/systemd/system/meshsat-share.service" "$ROOT/lib/systemd/system/meshsat-share.service"

if [ "$NODE" = 1 ]; then
    install -D -m 0755 "$INPUTS/meshtasticd" "$ROOT/usr/bin/meshtasticd"
    install -D -m 0755 "$P/bin/meshsat-node-channels" "$ROOT/usr/bin/meshsat-node-channels"
    install -D -m 0755 "$INPUTS/lora-listen" "$ROOT/usr/lib/meshsat/bin/lora-listen"
    install -D -m 0755 "$INPUTS/bridge-selftest" "$ROOT/usr/lib/meshsat/bin/bridge-selftest"
    install -D -m 0644 "$P/watchdog/meshsat_radio_watch.py" "$ROOT/usr/lib/meshsat/watchdog/meshsat_radio_watch.py"
    install -D -m 0644 "$BACKPLATE/tools/node-setup/set-channels.py" "$ROOT/usr/lib/meshsat/node-setup/set-channels.py"

    # Configuration (conffiles) and the bus
    install -D -m 0644 "$P/meshtasticd/config.yaml" "$ROOT/etc/meshtasticd/config.yaml"
    install -D -m 0644 "$P/meshtasticd/config.d/lora-pinedio-backcover.yaml" "$ROOT/etc/meshtasticd/config.d/lora-pinedio-backcover.yaml"
    install -D -m 0644 "$P/modules-load.d/meshsat-node.conf" "$ROOT/etc/modules-load.d/meshsat-node.conf"
    install -D -m 0644 "$P/udev/60-meshsat-node.rules" "$ROOT/etc/udev/rules.d/60-meshsat-node.rules"
    install -D -m 0644 "$P/modprobe.d/meshsat-no-keyboard.conf" "$ROOT/etc/modprobe.d/meshsat-no-keyboard.conf"

    # Units
    install -D -m 0644 "$P/systemd/meshtasticd.service" "$ROOT/lib/systemd/system/meshtasticd.service"
    install -D -m 0644 "$P/systemd/meshsat-radio-watch.service" "$ROOT/lib/systemd/system/meshsat-radio-watch.service"
    install -D -m 0644 "$P/systemd/meshsat-radio-watch.timer" "$ROOT/lib/systemd/system/meshsat-radio-watch.timer"
    install -D -m 0644 "$HERE/package/rootfs/lib/systemd/system/meshtasticd.service.d/meshsat-hardware.conf" "$ROOT/lib/systemd/system/meshtasticd.service.d/meshsat-hardware.conf"
    install -D -m 0644 "$HERE/package/rootfs/lib/systemd/system/meshsat-radio-watch.timer.d/meshsat-hardware.conf" "$ROOT/lib/systemd/system/meshsat-radio-watch.timer.d/meshsat-hardware.conf"

    # Meshtastic's web client, uncompressed: the Linux web server serves the path it is asked for
    mkdir -p "$ROOT/usr/share/meshtasticd/web"
    tar xf "$INPUTS/web-build-$WEB_VERSION.tar" -C "$ROOT/usr/share/meshtasticd/web"
    find "$ROOT/usr/share/meshtasticd/web" -name '*.gz' -exec gunzip -f {} \;
fi

# The app in the app grid
install -D -m 0644 "$HERE/package/rootfs/usr/share/applications/net.meshsat.Bridge.desktop" "$ROOT/usr/share/applications/net.meshsat.Bridge.desktop"
install -D -m 0644 "$HERE/package/rootfs/usr/share/metainfo/net.meshsat.Bridge.metainfo.xml" "$ROOT/usr/share/metainfo/net.meshsat.Bridge.metainfo.xml"
python3 "$HERE/package/make-icons.py" "$HERE/app/meshsat/brand/app-icon-1024.png" "$ROOT/usr/share/icons/hicolor" >/dev/null
# The apps' symbolic icons (Material and MeshSat's own), in the icon theme so GTK recolours them
install -d "$ROOT/usr/share/icons/hicolor/scalable/actions"
install -m 0644 "$HERE"/app/meshsat/icons/hicolor/scalable/actions/meshsat-*-symbolic.svg "$ROOT/usr/share/icons/hicolor/scalable/actions/"
# The satellite signal, 0 to 5 bars, for notifications, the panel and a tray (tools/make-signal-icons.py).
install -d "$ROOT/usr/share/icons/hicolor/scalable/status"
install -m 0644 "$HERE"/app/meshsat/icons/hicolor/scalable/status/meshsat-*-symbolic.svg "$ROOT/usr/share/icons/hicolor/scalable/status/"
# MeshSat outside its window: the notifier, a user service of every session.
install -D -m 0755 "$HERE/bin/meshsat-notify" "$ROOT/usr/bin/meshsat-notify"
install -D -m 0644 "$HERE/package/rootfs/usr/lib/systemd/user/meshsat-notify.service" "$ROOT/usr/lib/systemd/user/meshsat-notify.service"
# MeshSat in Phosh: the quick-settings tile and the lock-screen widget (phosh-plugins/, built on
# a phone by phosh-plugins/build.sh, as the daemon is). Phosh finds them at its next start.
case "$ARCH" in
    arm64) TRIPLET=aarch64-linux-gnu ;;
    amd64) TRIPLET=x86_64-linux-gnu ;;
    *) TRIPLET= ;;
esac
if [ -n "$TRIPLET" ] && [ -f "$INPUTS/phosh-plugins/libphosh-plugin-meshsat-quick-setting.so" ]; then
    PLUGINS="/usr/lib/$TRIPLET/phosh/plugins"
    for n in quick-setting lockscreen; do
        install -D -m 0644 "$INPUTS/phosh-plugins/libphosh-plugin-meshsat-$n.so" "$ROOT$PLUGINS/libphosh-plugin-meshsat-$n.so"
        sed "s#@plugins_dir@#$PLUGINS#" "$HERE/phosh-plugins/meshsat-$n.plugin.in" > "$ROOT$PLUGINS/meshsat-$n.plugin"
        chmod 0644 "$ROOT$PLUGINS/meshsat-$n.plugin"
    done
else
    say "no Phosh plugins in $INPUTS/phosh-plugins: the package goes without the quick-settings tile and the lock-screen widget"
fi

# IBM Plex, the apps' typeface (OFL), the same files the Android and iOS apps carry
install -d "$ROOT/usr/share/fonts/truetype/meshsat"
install -m 0644 "$HERE"/package/fonts/*.ttf "$ROOT/usr/share/fonts/truetype/meshsat/"
install -D -m 0644 "$HERE/package/fonts/LICENSE.txt" "$ROOT/usr/share/doc/meshsat/IBM-Plex-LICENSE.txt"
# Material Icons, the apps' icons (Apache License 2.0)
install -D -m 0644 "$HERE/package/icons/LICENSE-Material-Icons.txt" "$ROOT/usr/share/doc/meshsat/Material-Icons-LICENSE.txt"

# Documentation
install -D -m 0644 "$HERE/LICENSE" "$ROOT/usr/share/doc/meshsat/copyright"
install -D -m 0644 "$HERE/docs/INSTALL.md" "$ROOT/usr/share/doc/meshsat/INSTALL.md"
{
    echo "meshsat $VERSION, built $(date -u '+%F %T UTC')"
    if [ "$NODE" = 1 ]; then
        echo "meshtasticd: meshsat-firmware $FIRMWARE_COMMIT, env meshsat-pinephone-pro, sha256 $DAEMON_SHA256"
        echo "node packaging: meshsat-lora-backplate $BACKPLATE_COMMIT"
    else
        echo "meshtasticd: none on $ARCH (the node is a Meshtastic radio over Bluetooth)"
    fi
    echo "bridge: meshsat $(sha256sum "$INPUTS/meshsat-$ARCH" | cut -c1-16)…"
    [ "$NODE" = 1 ] && echo "web client: meshtastic/web $WEB_VERSION"
} > "$ROOT/usr/share/doc/meshsat/PROVENANCE"

# Control: the daemon's libraries are demanded only where the daemon is.
mkdir -p "$ROOT/DEBIAN"
SIZE=$(du -sk "$ROOT" | cut -f1)
NODE_DEPENDS=""
if [ "$NODE" = 1 ]; then
    NODE_DEPENDS=", i2c-tools, libstdc++6, libgcc-s1, zlib1g, libasound2t64, libasyncns0, libbrotli1, libbsd0, libcap2, libcom-err2, libcurl3t64-gnutls, libdbus-1-3, libdecor-0-0, libdrm2, libexpat1, libffi8, libflac14, libgbm1, libgmp10, libgnutls30t64, libgpiod3, libgssapi-krb5-2, libhogweed6t64, libi2c0, libidn2-0, libjansson4, libjsoncpp26, libk5crypto3, libkeyutils1, libkrb5-3, libkrb5support0, libldap2, libmd0, libmicrohttpd12t64, libmp3lame0, libmpg123-0t64, libnettle8t64, libnghttp2-14, libnghttp3-9, libngtcp2-16, libngtcp2-crypto-gnutls8, libogg0, libopus0, liborcania2.3, libp11-kit0, libpsl5t64, libpulse0, librtmp1, libsamplerate0, libsasl2-2, libsdl2-2.0-0, libsndfile1, libssh2-1t64, libssl3t64, libsystemd0, libtasn1-6, libudev1, libulfius2.7t64, libunistring5, libusb-1.0-0, libuv1t64, libvorbis0a, libvorbisenc2, libwayland-client0, libwayland-cursor0, libwayland-egl1, libx11-6, libx11-xcb1, libxau6, libxcb1, libxcursor1, libxdmcp6, libxext6, libxfixes3, libxi6, libxkbcommon0, libxrandr2, libxrender1, libxss1, libyaml-cpp0.8, libyder2.0t64, libzstd1"
fi
sed -e "s/@VERSION@/$VERSION/" -e "s/@ARCH@/$ARCH/" -e "s/@SIZE@/$SIZE/" -e "s/@NODE_DEPENDS@/$NODE_DEPENDS/" "$HERE/package/DEBIAN/control.in" > "$ROOT/DEBIAN/control"
install -m 0755 "$HERE/package/DEBIAN/preinst" "$ROOT/DEBIAN/preinst"
install -m 0755 "$HERE/package/DEBIAN/postinst" "$ROOT/DEBIAN/postinst"
install -m 0755 "$HERE/package/DEBIAN/prerm" "$ROOT/DEBIAN/prerm"
install -m 0755 "$HERE/package/DEBIAN/postrm" "$ROOT/DEBIAN/postrm"
if [ "$NODE" = 1 ]; then
    install -m 0644 "$HERE/package/DEBIAN/conffiles" "$ROOT/DEBIAN/conffiles"
else
    grep -v "meshtasticd\|modules-load\|udev\|modprobe" "$HERE/package/DEBIAN/conffiles" > "$ROOT/DEBIAN/conffiles"
    chmod 0644 "$ROOT/DEBIAN/conffiles"
fi

OUT="$HERE/build/meshsat_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group -Zxz --build "$ROOT" "$OUT" >/dev/null
sha256sum "$OUT"
say "$(ls -l "$OUT" | awk '{printf "%.1f MB", $5/1048576}') $OUT"
