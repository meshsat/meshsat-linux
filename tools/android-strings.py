#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The words MeshSat Android shows, out of its Kotlin sources: every string literal in ui/ and
sos/ that a person can read, split at $name and ${...} into its fixed fragments, one JSON
object per source file. The parity check (tools/parity-check.py) holds the Linux sources up
against this list. Android keeps its words as literals (no string resources), so this is the
whole list.

  tools/android-strings.py ../meshsat-android [--out tests/parity/android-strings.json]

Pinned to the Android tag the ledger names; the output carries the commit it was made from."""
import argparse
import json
import os
import re
import subprocess
import sys

FOLDERS = ("app/src/main/java/net/meshsat/android/ui", "app/src/main/java/net/meshsat/android/sos")
# Literals that are not words: routes, keys, ids, formats, log tags, colours, units alone.
IGNORE = re.compile(r"^(setup(/.*)?|chat/.*|home|messages|map|people|passes|radio-config|rules|interfaces|deliveries|topology|geofence|audit|credentials|decrypt|nodelog|about|sos"
                    r"|[a-z_]+(\.[a-z_]+)*|[A-Z_]+|%[.\dsdf]+|[\d.,%/ -]*|.*\\n.*|[#][0-9A-Fa-f]{3,8}|[a-z]+://.*|.*[{}<>\[\]|=]+.*|[\w.-]+@[\w.-]+|.*[:/]\d+.*)$")
STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
TEMPLATE = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*")


def readable(fragment: str) -> bool:
    text = fragment.strip()
    if len(text) < 3:
        return False
    if IGNORE.match(text):
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    # a word with a space, or a capitalised word: something a person reads
    return (" " in text) or (text[0].isupper() and len(text) >= 4) or text.endswith((".", "?", "!"))


def fragments(literal: str) -> list:
    literal = literal.replace('\\"', '"').replace("\\'", "'")
    # Kotlin's \uXXXX escapes are the characters a person reads (\u00B0 is the degree sign)
    literal = re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), literal)
    parts = TEMPLATE.split(literal)
    return [p.strip() for p in parts if readable(p)]


def strip_comments(source: str) -> str:
    """Kotlin without its comments, its string and character literals kept whole. A regex took
    the "//" in "meshsat://key/" for a comment, and every word after it in SettingsScreen.kt
    (lines 295 to 1766) was lost."""
    out, i, n = [], 0, len(source)
    while i < n:
        if source.startswith('"""', i):
            j = source.find('"""', i + 3)
            j = n if j < 0 else j + 3
            out.append(source[i:j])
            i = j
        elif source[i] in "\"'":
            quote, j = source[i], i + 1
            while j < n and source[j] != quote and source[j] != "\n":
                j += 2 if source[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(source[i:j])
            i = j
        elif source.startswith("//", i):
            j = source.find("\n", i)
            i = n if j < 0 else j
        elif source.startswith("/*", i):
            j = source.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        else:
            out.append(source[i])
            i += 1
    return "".join(out)


def extract(root: str) -> dict:
    out = {}
    for folder in FOLDERS:
        base = os.path.join(root, folder)
        for dirpath, _dirs, files in os.walk(base):
            for name in sorted(files):
                if not name.endswith(".kt"):
                    continue
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, root)
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
                # comments go: a literal in a comment is not shown
                source = strip_comments(source)
                found = []
                for match in STRING.finditer(source):
                    for fragment in fragments(match.group(1)):
                        if fragment not in found:
                            found.append(fragment)
                if found:
                    out[rel] = found
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("android", help="the meshsat-android checkout, or an export of the pinned tag (git archive)")
    parser.add_argument("--ref", help="the tag the sources are, when they are an export and not a checkout")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "parity", "android-strings.json"))
    args = parser.parse_args()
    try:
        commit = args.ref or subprocess.run(["git", "-C", args.android, "describe", "--tags", "--always"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = "unknown"
    strings = extract(args.android)
    total = sum(len(v) for v in strings.values())
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"android": commit, "files": len(strings), "strings": total, "by_file": strings}, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    print(f"{total} readable strings in {len(strings)} files of {commit} -> {args.out}")
    for rel, found in sorted(strings.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f"  {len(found):4} {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
