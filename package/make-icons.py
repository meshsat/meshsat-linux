#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The app icon: the MeshSat mark in light ink on the brand orange, as a rounded square,
in the hicolor sizes Phosh and GNOME use.

    make-icons.py docs/images/mark-dark.png build/root/usr/share/icons/hicolor
"""
import os
import sys

from PIL import Image, ImageDraw

ORANGE = (242, 92, 5, 255)
SIZES = (512, 256, 128, 64, 48)


def icon(mark: Image.Image, size: int) -> Image.Image:
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=ORANGE)
    box = int(size * 0.72)
    scale = min(box / mark.width, box / mark.height)
    glyph = mark.resize((max(1, round(mark.width * scale)), max(1, round(mark.height * scale))), Image.LANCZOS)
    out.alpha_composite(glyph, ((size - glyph.width) // 2, (size - glyph.height) // 2))
    return out


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
