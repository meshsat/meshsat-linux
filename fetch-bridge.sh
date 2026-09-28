#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Take the Bridge binary for the package from the Bridge's container image.
#
#   sh fetch-bridge.sh 79692f8c [inputs-dir] [arch: arm64 (default) | amd64]
#
# The `build` job of the meshsat pipeline builds bare binaries WITHOUT the web interface
# (`make web` is not part of it), so a binary from its artifacts serves every asset as
# index.html and the app shows a blank page (found on the phone, 28 Sep 2026). The
# container image is built from the same commit with the interface embedded, for arm64
# and amd64; this pulls the image for the architecture asked and copies
# /usr/local/bin/meshsat out of it.
set -eu
TAG=${1:?the image tag: the first 8 characters of the commit, or latest}
INPUTS=${2:-$HOME/build/meshsat-linux/inputs}
ARCH=${3:-arm64}
IMAGE=ghcr.io/meshsat/meshsat
mkdir -p "$INPUTS"
docker pull --platform "linux/$ARCH" "$IMAGE:$TAG" >/dev/null
C=$(docker create --platform "linux/$ARCH" "$IMAGE:$TAG")
docker cp "$C:/usr/local/bin/meshsat" "$INPUTS/meshsat-$ARCH"
docker rm "$C" >/dev/null
chmod 0755 "$INPUTS/meshsat-$ARCH"
echo "$IMAGE:$TAG ($ARCH) -> $INPUTS/meshsat-$ARCH"
sha256sum "$INPUTS/meshsat-$ARCH"
