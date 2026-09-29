#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The parity ledger's keeper: checks tests/parity/ledger.json (every row well formed, every
verified row backed by a test that exists, every exclusion with its reason), measures how many
of Android's words (tests/parity/android-strings.json) the Linux sources carry, and writes
docs/PARITY.md from both.

  tools/parity-check.py            the check and the numbers
  tools/parity-check.py --write    also rewrite docs/PARITY.md
  tools/parity-check.py --strict   fail on any row that is not verified or excluded, and on any
                                   Android string neither carried nor excluded (the 1.0.0 gate)"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "tests", "parity", "ledger.json")
STRINGS = os.path.join(ROOT, "tests", "parity", "android-strings.json")
EXCLUDED_STRINGS = os.path.join(ROOT, "tests", "parity", "excluded-strings.json")
DOC = os.path.join(ROOT, "docs", "PARITY.md")
STATES = ("missing", "partial", "built", "verified", "excluded", "blocked")
KINDS = ("screen", "tab", "card", "dialog", "sheet", "banner", "notification", "strings", "behaviour", "linux-only")


def load(path: str, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def linux_sources() -> str:
    """The app's sources, and every string they hold as Python reads it: adjacent literals joined
    (a sentence written over two lines is one string) and an f-string's fixed parts, split at
    its fields as the Android words are split at Kotlin's templates."""
    import ast  # noqa: PLC0415

    text = []
    for path in glob.glob(os.path.join(ROOT, "app", "meshsat", "**", "*.py"), recursive=True):
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        text.append(source)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text.append(node.value)
    return "\n".join(text)


def test_names() -> set:
    """Every e2e case (module::case) and every unit test method (TestClass.test_x)."""
    names = set()
    for path in glob.glob(os.path.join(ROOT, "tests", "e2e", "cases", "*.py")):
        module = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as handle:
            for match in re.finditer(r"^def case_(\w+)\(", handle.read(), re.M):
                names.add(f"{module}::{match.group(1)}")
    for path in glob.glob(os.path.join(ROOT, "tests", "test_*.py")):
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        cls = None
        for line in source.splitlines():
            m = re.match(r"class (\w+)\(", line)
            if m:
                cls = m.group(1)
            m = re.match(r"\s+def (test_\w+)\(", line)
            if m and cls:
                names.add(f"{cls}.{m.group(1)}")
    return names


def coverage(strings: dict, sources: str, excluded: dict) -> dict:
    """Per Android file: the fragments the Linux sources carry, the excluded, the missing."""
    out = {}
    for rel, fragments in strings.get("by_file", {}).items():
        carried, gone, missing = [], [], []
        for fragment in fragments:
            if fragment in sources:
                carried.append(fragment)
            elif fragment in excluded.get(rel, {}) or fragment in excluded.get("*", {}):
                gone.append(fragment)
            else:
                missing.append(fragment)
        out[rel] = {"total": len(fragments), "carried": len(carried), "excluded": len(gone), "missing": missing}
    return out


def check(ledger: dict, tests: set) -> list:
    problems = []
    seen = set()
    for row in ledger.get("rows", []):
        rid = row.get("id", "?")
        if rid in seen:
            problems.append(f"{rid}: listed twice")
        seen.add(rid)
        for field in ("id", "kind", "android", "linux", "modes", "state"):
            if field not in row:
                problems.append(f"{rid}: no {field}")
        if row.get("kind") not in KINDS:
            problems.append(f"{rid}: kind {row.get('kind')!r} is not one of {KINDS}")
        if row.get("state") not in STATES:
            problems.append(f"{rid}: state {row.get('state')!r} is not one of {STATES}")
        if row.get("modes") not in ("cover", "bluetooth", "both"):
            problems.append(f"{rid}: modes {row.get('modes')!r}")
        if row.get("state") == "verified":
            test = row.get("test", "")
            if not test:
                problems.append(f"{rid}: verified without a test")
            elif test not in tests:
                problems.append(f"{rid}: its test {test!r} does not exist")
            if not row.get("capture"):
                problems.append(f"{rid}: verified without a capture")
        if row.get("state") == "excluded" and not row.get("note"):
            problems.append(f"{rid}: excluded without a reason")
        if row.get("state") == "blocked" and not row.get("note"):
            problems.append(f"{rid}: blocked without saying by what")
    return problems


def write_doc(ledger: dict, cov: dict, strings: dict) -> None:
    rows = ledger.get("rows", [])
    by_state = {s: sum(1 for r in rows if r.get("state") == s) for s in STATES}
    total_strings = sum(c["total"] for c in cov.values())
    carried = sum(c["carried"] for c in cov.values())
    excluded = sum(c["excluded"] for c in cov.values())
    lines = ["# Parity with MeshSat Android", "",
             f"MeshSat Android is the reference, pinned at `{ledger.get('android', strings.get('android', '?'))}`. One row per screen, tab, card, dialog, banner and notification of the Android app; "
             "a row is done when the Linux app has it, in Android's words, and a test proves it. Kept by `tools/parity-check.py` from `tests/parity/ledger.json`; "
             "the words by `tools/android-strings.py`.", "",
             f"**Rows:** {len(rows)}: " + ", ".join(f"{by_state[s]} {s}" for s in STATES) + ".", "",
             f"**Words:** {carried} of {total_strings} readable strings of Android's `ui/` and `sos/` are in the Linux sources, {excluded} excluded with a reason, {total_strings - carried - excluded} still to port.", "",
             "States: `missing` (not there), `partial` (some of it), `built` (there, untested), `verified` (there, in Android's words, with a test that ran green on the phone), "
             "`excluded` (not ported, with the reason), `blocked` (built and tested against the scripted Bridge, waiting for hardware the bench lacks).", "",
             "| id | kind | Android | Linux | modes | state | test | note |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['kind']} | `{r['android']}` | `{r.get('linux', '')}` | {r['modes']} | {r['state']} | {r.get('test', '')} | {r.get('note', '')} |")
    lines += ["", "## Words, per Android file", "", "| file | carried | excluded | missing |", "|---|---|---|---|"]
    for rel, c in sorted(cov.items(), key=lambda kv: -len(kv[1]["missing"])):
        lines.append(f"| `{rel.split('net/meshsat/android/')[-1]}` | {c['carried']}/{c['total']} | {c['excluded']} | {len(c['missing'])} |")
    with open(DOC, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="rewrite docs/PARITY.md")
    parser.add_argument("--strict", action="store_true", help="the 1.0.0 gate")
    parser.add_argument("--missing", metavar="FILE", help="list the missing words of one Android file (a substring of its path)")
    args = parser.parse_args()
    ledger = load(LEDGER, {"rows": []})
    strings = load(STRINGS, {"by_file": {}})
    excluded = load(EXCLUDED_STRINGS, {})
    tests = test_names()
    problems = check(ledger, tests)
    cov = coverage(strings, linux_sources(), excluded)
    rows = ledger.get("rows", [])
    total = sum(c["total"] for c in cov.values())
    carried = sum(c["carried"] for c in cov.values())
    gone = sum(c["excluded"] for c in cov.values())
    print(f"ledger: {len(rows)} rows, " + ", ".join(f"{sum(1 for r in rows if r.get('state') == s)} {s}" for s in STATES))
    print(f"words: {carried}/{total} carried, {gone} excluded, {total - carried - gone} missing")
    if args.missing:
        for rel, c in cov.items():
            if args.missing in rel:
                print(f"\n{rel}: {len(c['missing'])} missing")
                for fragment in c["missing"]:
                    print("  -", fragment)
    for problem in problems:
        print("problem:", problem)
    if args.strict:
        for r in rows:
            if r.get("state") not in ("verified", "excluded"):
                problems.append(f"{r['id']}: {r.get('state')} at the gate")
        if total - carried - gone:
            problems.append(f"{total - carried - gone} Android strings neither carried nor excluded")
    if args.write:
        write_doc(ledger, cov, strings)
        print(f"wrote {DOC}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
