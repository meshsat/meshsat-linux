#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build MeshSat's two Phosh plugins (the quick-settings tile and the lock-screen widget) on a
# phone, as the node daemon is built: natively, for the architecture the package is for.
#
#   sh phosh-plugins/build.sh [out-dir]        default: phosh-plugins/build
#
# Needs gcc, pkg-config and GTK 3's headers (sudo apt install libgtk-3-dev). Nothing of Phosh
# is needed to build: the tile finds Phosh's types by name when Phosh loads it.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$HERE/build}
mkdir -p "$OUT"
CFLAGS="-fPIC -O2 -Wall -Wno-unused-parameter $(pkg-config --cflags gtk+-3.0 gio-2.0)"
LIBS=$(pkg-config --libs gtk+-3.0 gio-2.0)
for name in quick-setting lockscreen; do
    gcc -shared -o "$OUT/libphosh-plugin-meshsat-$name.so" \
        -DG_LOG_DOMAIN="\"phosh-plugin-meshsat-$name\"" \
        $CFLAGS "$HERE/meshsat-$name.c" "$HERE/meshsat-status.c" $LIBS
    strip --strip-unneeded "$OUT/libphosh-plugin-meshsat-$name.so"
done
ls -l "$OUT"/libphosh-plugin-meshsat-*.so
sha256sum "$OUT"/libphosh-plugin-meshsat-*.so
