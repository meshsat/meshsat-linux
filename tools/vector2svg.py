#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn Android vector drawables into SVG files, so the Linux app shows the very icons the
Android app shows (Material icons and MeshSat's own satellite and mesh vectors).

    vector2svg.py <android-res-drawable-dir> <out-dir> name1 name2 ...

Only what the app's icons use is handled: viewport size, <path> with pathData, fillColor,
strokeColor, strokeWidth, fillAlpha, strokeLineCap/Join, and <group> translate/scale. A fill
of a theme attribute (?attr/...) or a colour resource becomes "currentColor", so GTK can
recolour the icon like a symbolic one.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

ANDROID = "{http://schemas.android.com/apk/res/android}"


def colour(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("#"):
        if len(value) == 9:  # #AARRGGBB -> #RRGGBB (alpha handled separately when opaque enough)
            return "#" + value[3:]
        return value
    return "currentColor"  # ?attr/colorControlNormal, @color/..., @android:color/white


def convert(src: str) -> str:
    root = ET.parse(src).getroot()
    vw = root.get(ANDROID + "viewportWidth", "24")
    vh = root.get(ANDROID + "viewportHeight", "24")
    tint = root.get(ANDROID + "tint")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}" width="{vw}" height="{vh}">']

    def emit(node, indent="  "):
        for child in node:
            tag = child.tag.split("}")[-1]
            if tag == "path":
                d = child.get(ANDROID + "pathData", "")
                attrs = [f'd="{d}"']
                fill = colour(child.get(ANDROID + "fillColor"))
                stroke = colour(child.get(ANDROID + "strokeColor"))
                if tint:
                    fill = "currentColor" if fill else fill
                attrs.append(f'fill="{fill or "none"}"')
                if stroke:
                    attrs.append(f'stroke="{stroke}"')
                    attrs.append(f'stroke-width="{child.get(ANDROID + "strokeWidth", "1")}"')
                    cap = child.get(ANDROID + "strokeLineCap")
                    join = child.get(ANDROID + "strokeLineJoin")
                    if cap:
                        attrs.append(f'stroke-linecap="{cap}"')
                    if join:
                        attrs.append(f'stroke-linejoin="{join}"')
                alpha = child.get(ANDROID + "fillAlpha")
                if alpha:
                    attrs.append(f'fill-opacity="{alpha}"')
                salpha = child.get(ANDROID + "strokeAlpha")
                if salpha:
                    attrs.append(f'stroke-opacity="{salpha}"')
                out.append(f"{indent}<path {' '.join(attrs)}/>")
            elif tag == "group":
                tx, ty = child.get(ANDROID + "translateX", "0"), child.get(ANDROID + "translateY", "0")
                sx, sy = child.get(ANDROID + "scaleX", "1"), child.get(ANDROID + "scaleY", "1")
                rot = child.get(ANDROID + "rotation", "0")
                px, py = child.get(ANDROID + "pivotX", "0"), child.get(ANDROID + "pivotY", "0")
                transform = f"translate({tx} {ty}) rotate({rot} {px} {py}) scale({sx} {sy})"
                out.append(f'{indent}<g transform="{transform}">')
                emit(child, indent + "  ")
                out.append(f"{indent}</g>")
            elif tag == "clip-path":
                continue

    emit(root)
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> int:
    src_dir, out_dir, names = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out_dir, exist_ok=True)
    done = 0
    for name in names:
        src = os.path.join(src_dir, name + ".xml")
        if not os.path.exists(src):
            print(f"missing: {src}", file=sys.stderr)
            continue
        with open(os.path.join(out_dir, name + ".svg"), "w", encoding="utf-8") as handle:
            handle.write(convert(src))
        done += 1
    print(f"{done} icons written to {out_dir}")
    return 0 if done == len(names) else 1


if __name__ == "__main__":
    sys.exit(main())
