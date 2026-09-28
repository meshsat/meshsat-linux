# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs the end-to-end cases on this device, inside a session with a Wayland compositor and an
accessibility bus (tests/e2e/headless.sh gives a private one):

  python3 -m tests.e2e.run --tiers h,s,l --out DIR [--app-dir app] [--cases h_home]

A case module (tests/e2e/cases/h_*.py, s_*.py, l_*.py) names its tier by its first letter,
its starting scenario in SCENARIO, and its cases as functions `case_<name>(ctx)`. Each module
gets a fresh app instance against a fresh scripted Bridge (tier h) or the live one (tier l).
A Python traceback in the app's stderr fails the case that caused it. The report (report.json,
summary.txt) and every case's artifacts land in --out."""
import argparse
import glob
import importlib.util
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from driver import HarnessError  # noqa: E402
from driver.app import App  # noqa: E402
from driver.bridge import Live, Scripted  # noqa: E402
from driver.report import Report  # noqa: E402


class Context:
    """What a case gets: the app, its tree, the Bridge, the notifier and the notification
    daemon when the module asked for them, and where to leave artifacts."""

    def __init__(self, app: App, bridge, report: Report, module: str, name: str, notifications=None, notifier=None):
        self.app = app
        self.tree = app.tree
        self.bridge = bridge
        self.report = report
        self.notifications = notifications
        self.notifier = notifier
        self.module, self.name = module, name
        self.dir = report.case_dir(module, name)
        self.shots = 0

    def shot(self, label: str = "") -> str:
        self.shots += 1
        path = os.path.join(self.dir, f"{self.shots:02d}-{label or 'shot'}.png")
        self.app.screenshot(path)
        return path

    def note(self, text: str) -> None:
        with open(os.path.join(self.dir, "notes.txt"), "a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    def dump_tree(self, label: str = "tree") -> None:
        import json

        with open(os.path.join(self.dir, f"{label}.json"), "w", encoding="utf-8") as handle:
            json.dump(self.tree.dump(), handle, indent=1)


def load_module(path: str):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return name, module


def run_module(path: str, args, report: Report) -> None:
    name, module = load_module(path)
    tier = name[0]
    cases = [(attr[5:], getattr(module, attr)) for attr in dir(module) if attr.startswith("case_")]
    if args.cases and not any(pattern in name for pattern in args.cases):
        return
    work = os.path.join(args.out, "_work", name)
    os.makedirs(work, exist_ok=True)
    bridge = None
    app = None
    notifications = None
    notifier = None
    try:
        if tier in ("h", "s"):
            bridge = Scripted(getattr(module, "SCENARIO", "mesh-only"))
            url = bridge.url
        else:
            bridge = Live()
            url = bridge.url
        hardware = getattr(module, "HARDWARE", "real" if tier == "l" else None)
        units = getattr(module, "UNITS", "real" if tier == "l" else "meshtasticd.service=active,meshsat-bridge.service=active")
        app = App(work, url, app_dir=args.app_dir, hardware=hardware, units=units, poll=getattr(module, "POLL", 2.0)).start()
        if getattr(module, "NOTIFIER", False):
            from driver.notifications import NotificationDaemon  # noqa: PLC0415

            notifications = NotificationDaemon().start()
            import subprocess  # noqa: PLC0415

            notifier = subprocess.Popen(["python3", "-m", "meshsat.notify"], env=app.environment(), stdout=subprocess.DEVNULL, stderr=open(os.path.join(work, "notify.stderr"), "w", encoding="utf-8"), cwd=work)
            time.sleep(3)
    except Exception as error:  # noqa: BLE001
        for case_name, _fn in cases:
            report.record(name, case_name, tier, "fail", 0.0, HarnessError(f"the module could not start: {error}"))
        if app is not None:
            app.stop()
        if bridge is not None and hasattr(bridge, "stop"):
            bridge.stop()
        return
    for case_name, fn in cases:
        started = time.time()
        ctx = Context(app, bridge, report, name, case_name, notifications, notifier)
        before = len(app.tracebacks())
        try:
            fn(ctx)
            after = app.tracebacks()
            if len(after) > before:
                raise AssertionError("the app raised: " + after[-1][-1500:])
            report.record(name, case_name, tier, "pass", time.time() - started)
            print(f"ok   {name}::{case_name}", flush=True)
        except Exception as error:  # noqa: BLE001
            ctx.shot("failure")
            try:
                ctx.dump_tree("tree-at-failure")
            except Exception:  # noqa: BLE001
                pass
            report.record(name, case_name, tier, "fail", time.time() - started, error)
            print(f"FAIL {name}::{case_name}: {type(error).__name__}: {error}", flush=True)
            traceback.print_exc()
        finally:
            with open(os.path.join(ctx.dir, "trace.jsonl"), "w", encoding="utf-8") as handle:
                import json

                for event in app.trace():
                    handle.write(json.dumps(event) + "\n")
    with open(os.path.join(work, "app.stderr.txt"), "w", encoding="utf-8") as handle:
        handle.write(app.stderr())
    if notifier is not None:
        notifier.terminate()
        try:
            notifier.wait(timeout=5)
        except Exception:  # noqa: BLE001
            notifier.kill()
    if notifications is not None:
        notifications.stop()
    app.stop()
    if hasattr(bridge, "stop"):
        bridge.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiers", default="h", help="comma-separated: h (scripted Bridge), s (scratch Bridge), l (live)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--app-dir", default=None, help="the app's package directory (default: the installed /usr/lib/meshsat/app)")
    parser.add_argument("--cases", nargs="*", default=None, help="module name patterns to run")
    parser.add_argument("--inbound", default="", help="tier l: the text the far end sent before this run")
    parser.add_argument("--expect-file", default="", help="tier l: where a case writes the text the far end must hear")
    args = parser.parse_args()
    if args.inbound:
        os.environ["MESHSAT_E2E_INBOUND"] = args.inbound
    if args.expect_file:
        os.environ["MESHSAT_E2E_EXPECT_FILE"] = args.expect_file
    if not os.environ.get("WAYLAND_DISPLAY"):
        print("no WAYLAND_DISPLAY: run inside tests/e2e/headless.sh or a session", file=sys.stderr)
        return 2
    tiers = set(args.tiers.split(","))
    report = Report(args.out)
    modules = sorted(glob.glob(os.path.join(HERE, "cases", "*.py")))
    for path in modules:
        if os.path.basename(path)[0] in tiers and not os.path.basename(path).startswith("_"):
            run_module(path, args, report)
    out = report.write()
    print(open(os.path.join(args.out, "summary.txt"), encoding="utf-8").read())
    return 1 if out["summary"]["app_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
