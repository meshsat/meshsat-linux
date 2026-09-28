#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The app icon: the same artwork as the Android and iOS apps (a 1024 px square), in the
shape those platforms give it. Android's launcher and iOS mask the square themselves; Phosh
and GNOME show the file as it is, so the mask is applied here: iOS's continuous corner (a
radius of 22.4 % of the side) on a canvas with the small margin GNOME app icons keep, in the
hicolor sizes Phosh and GNOME use.

    make-icons.py app/meshsat/brand/app-icon-1024.png build/root/usr/share/icons/hicolor
"""
import os
import sys

from PIL import Image, ImageDraw

SIZES = (512, 256, 128, 64, 48)
MARGIN = 0.06  # of the canvas, each side
RADIUS = 0.2237  # of the icon's side, iOS's corner
OVERSAMPLE = 4


def icon(source: Image.Image, size: int) -> Image.Image:
    big = size * OVERSAMPLE
    inner = round(big * (1 - 2 * MARGIN))
    offset = (big - inner) // 2
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((offset, offset, offset + inner - 1, offset + inner - 1), radius=round(inner * RADIUS), fill=255)
    art = source.resize((inner, inner), Image.LANCZOS)
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    canvas.paste(art, (offset, offset))
    canvas.putalpha(mask)
    return canvas.resize((size, size), Image.LANCZOS)


def main() -> int:
    source, root = sys.argv[1], sys.argv[2]
    mark = Image.open(source).convert("RGBA")
    for size in SIZES:
        folder = os.path.join(root, f"{size}x{size}", "apps")
        os.makedirs(folder, exist_ok=True)
        icon(mark, size).save(os.path.join(folder, "net.meshsat.Bridge.png"), optimize=True)
    print(f"icons written under {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
