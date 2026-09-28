# SPDX-License-Identifier: GPL-3.0-or-later
"""The run's record: one entry per case with its verdict and failure class, the artifacts each
left (captures, the tree, the trace), and a summary a person and a release gate can read."""
import json
import os
import time
import traceback

from . import BenchError, BridgeError, HarnessError


def classify(error: BaseException) -> str:
    if isinstance(error, HarnessError):
        return "harness"
    if isinstance(error, BridgeError):
        return "bridge"
    if isinstance(error, BenchError):
        return "bench"
    return "app"


class Report:
    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(directory, exist_ok=True)
        self.cases = []
        self.started = time.time()

    def case_dir(self, module: str, name: str) -> str:
        path = os.path.join(self.directory, module, name)
        os.makedirs(path, exist_ok=True)
        return path

    def record(self, module: str, name: str, tier: str, status: str, seconds: float, error: BaseException | None = None, notes: str = "") -> dict:
        entry = {"module": module, "case": name, "tier": tier, "status": status, "seconds": round(seconds, 2), "notes": notes}
        if error is not None:
            entry["class"] = classify(error)
            entry["error"] = f"{type(error).__name__}: {error}"
            entry["traceback"] = "".join(traceback.format_exception(type(error), error, error.__traceback__))[-4000:]
        self.cases.append(entry)
        return entry

    def write(self) -> dict:
        passed = sum(1 for c in self.cases if c["status"] == "pass")
        failed = [c for c in self.cases if c["status"] == "fail"]
        summary = {"started": self.started, "seconds": round(time.time() - self.started, 1), "cases": len(self.cases), "passed": passed,
                   "failed": len(failed), "skipped": sum(1 for c in self.cases if c["status"] == "skip"),
                   "app_failures": sum(1 for c in failed if c.get("class") == "app"), "by_class": {}}
        for c in failed:
            summary["by_class"][c.get("class", "app")] = summary["by_class"].get(c.get("class", "app"), 0) + 1
        out = {"summary": summary, "cases": self.cases}
        with open(os.path.join(self.directory, "report.json"), "w", encoding="utf-8") as handle:
            json.dump(out, handle, indent=1)
        lines = [f"{summary['passed']} passed, {summary['failed']} failed, {summary['skipped']} skipped in {summary['seconds']} s"]
        for c in self.cases:
            mark = {"pass": "ok  ", "fail": "FAIL", "skip": "skip"}[c["status"]]
            lines.append(f"{mark} {c['tier']} {c['module']}::{c['case']} ({c['seconds']} s)" + (f" [{c.get('class')}] {c.get('error', '')[:200]}" if c["status"] == "fail" else ""))
        with open(os.path.join(self.directory, "summary.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return out
