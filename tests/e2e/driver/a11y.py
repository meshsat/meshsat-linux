# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's widget tree over the accessibility bus (AT-SPI), the way a screen reader sees it:
every label with its text, every button with its name and a click action, every entry with
its text and a way to set it. The app under test is found by its process id, so two MeshSat
instances on one bus never get mixed up. Accessibles are never kept across a poll: the
screens rebuild their rows, and a kept one goes defunct; every action finds its widget again."""
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # noqa: E402

from . import HarnessError  # noqa: E402


class Node:
    """One widget as the bus shows it."""

    def __init__(self, accessible, depth: int = 0):
        self.acc = accessible
        self.depth = depth
        try:
            self.role = accessible.get_role_name() or ""
            self.name = accessible.get_name() or ""
            self.states = accessible.get_state_set()
        except GLib.Error:
            self.role, self.name, self.states = "defunct", "", None

    @property
    def showing(self) -> bool:
        return bool(self.states and self.states.contains(Atspi.StateType.SHOWING))

    @property
    def sensitive(self) -> bool:
        return bool(self.states and self.states.contains(Atspi.StateType.SENSITIVE))

    @property
    def checked(self) -> bool:
        return bool(self.states and self.states.contains(Atspi.StateType.CHECKED))

    def actions(self) -> list:
        try:
            if "Action" not in self.acc.get_interfaces():
                return []
            return [Atspi.Action.get_action_name(self.acc, i) for i in range(Atspi.Action.get_n_actions(self.acc))]
        except GLib.Error:
            return []

    def do(self, action: str = "click") -> bool:
        names = self.actions()
        if action not in names:
            raise HarnessError(f"{self.role} '{self.name}' has no '{action}' action, only {names}")
        return bool(Atspi.Action.do_action(self.acc, names.index(action)))

    def text(self) -> str:
        try:
            n = Atspi.Text.get_character_count(self.acc)
            return Atspi.Text.get_text(self.acc, 0, n) or ""
        except GLib.Error:
            return ""

    def set_text(self, value: str) -> bool:
        return bool(Atspi.EditableText.set_text_contents(self.acc, value))

    def set_value(self, value: float) -> bool:
        return bool(Atspi.Value.set_current_value(self.acc, float(value)))

    def value(self) -> float:
        return float(Atspi.Value.get_current_value(self.acc))

    def extents(self) -> tuple:
        r = Atspi.Component.get_extents(self.acc, Atspi.CoordType.WINDOW)
        return (r.x, r.y, r.width, r.height)

    def __repr__(self) -> str:
        return f"{self.role} {self.name!r}"


class Tree:
    """The tree of the application with process id `pid`."""

    def __init__(self, pid: int, name_hint: str = ""):
        self.pid = pid
        self.name_hint = name_hint

    def application(self):
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            try:
                if app.get_process_id() == self.pid:
                    return app
            except GLib.Error:
                continue
        return None

    def wait_for_application(self, timeout: float = 20.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            app = self.application()
            if app is not None:
                return app
            time.sleep(0.25)
        raise HarnessError(f"the app (pid {self.pid}) never appeared on the accessibility bus")

    def walk(self, showing_only: bool = True) -> list:
        """Every widget, depth first; with `showing_only` the ones on screen (the five tabs
        exist from the start, only one of them is showing)."""
        app = self.application()
        if app is None:
            raise HarnessError(f"the app (pid {self.pid}) is not on the accessibility bus")
        out = []

        def visit(acc, depth):
            node = Node(acc, depth)
            if node.role == "defunct":
                return
            if not showing_only or node.showing or node.role in ("application", "frame"):
                out.append(node)
            try:
                count = acc.get_child_count()
            except GLib.Error:
                return
            for j in range(count):
                try:
                    child = acc.get_child_at_index(j)
                except GLib.Error:
                    continue
                if child is not None:
                    visit(child, depth + 1)

        visit(app, 0)
        return out

    def find_all(self, role: str | None = None, name: str | None = None, contains: str | None = None, showing_only: bool = True) -> list:
        return [n for n in self.walk(showing_only) if (role is None or n.role == role) and (name is None or n.name == name) and (contains is None or contains in n.name)]

    def find(self, role: str | None = None, name: str | None = None, contains: str | None = None, timeout: float = 5.0, showing_only: bool = True) -> Node:
        """The first widget that matches, waiting up to `timeout` for it to appear."""
        deadline = time.time() + timeout
        while True:
            found = self.find_all(role, name, contains, showing_only)
            if found:
                return found[0]
            if time.time() >= deadline:
                what = " ".join(f"{k}={v!r}" for k, v in (("role", role), ("name", name), ("contains", contains)) if v is not None)
                raise AssertionError(f"no widget on view with {what}; on view: {self.summary()[:1500]}")
            time.sleep(0.3)

    def texts(self, showing_only: bool = True) -> list:
        return [n.name for n in self.walk(showing_only) if n.role == "label" and n.name]

    def has_text(self, contains: str) -> bool:
        return any(contains in t for t in self.texts())

    def wait_text(self, contains: str, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.has_text(contains):
                return
            time.sleep(0.3)
        raise AssertionError(f"the text {contains!r} never showed; on view: {self.summary()[:1500]}")

    def wait_gone(self, contains: str, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.has_text(contains):
                return
            time.sleep(0.3)
        raise AssertionError(f"the text {contains!r} is still on view")

    # Acting
    def click(self, name: str, role: str = "button", timeout: float = 5.0) -> None:
        self.find(role, name=name, timeout=timeout).do("click")

    def click_containing(self, contains: str, role: str = "button", timeout: float = 5.0) -> None:
        self.find(role, contains=contains, timeout=timeout).do("click")

    def dialog(self, timeout: float = 5.0) -> list:
        """The widgets of the dialog in front (an alert or a sheet), for a button that shares
        its name with one on the page behind it."""
        deadline = time.time() + timeout
        while True:
            nodes = self.walk()
            starts = [i for i, n in enumerate(nodes) if n.role in ("alert", "dialog")]
            if starts:
                start = starts[-1]
                depth = nodes[start].depth
                out = [nodes[start]]
                for n in nodes[start + 1:]:
                    if n.depth <= depth:
                        break
                    out.append(n)
                return out
            if time.time() >= deadline:
                raise AssertionError(f"no dialog on view; on view: {self.summary()[:800]}")
            time.sleep(0.3)

    def click_in_dialog(self, name: str, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while True:
            for n in self.dialog(timeout):
                if n.role == "button" and n.name == name:
                    n.do("click")
                    return
            if time.time() >= deadline:
                raise AssertionError(f"no button {name!r} in the dialog; there: {[n.name for n in self.dialog(1) if n.role == 'button']}")
            time.sleep(0.3)

    def dialogs_open(self) -> bool:
        return any(n.role in ("alert", "dialog") for n in self.walk())

    def toggle(self, name: str, timeout: float = 5.0) -> None:
        node = self.find(name=name, timeout=timeout)
        node.do("toggle" if "toggle" in node.actions() else "click")

    def set_text(self, name: str, value: str, timeout: float = 5.0) -> None:
        self.find("text", name=name, timeout=timeout).set_text(value)

    def entry_text(self, name: str) -> str:
        return self.find("text", name=name).text()

    def summary(self) -> str:
        return "; ".join(f"{n.role}:{n.name[:40]}" for n in self.walk() if n.name)

    def dump(self) -> list:
        return [{"depth": n.depth, "role": n.role, "name": n.name, "actions": n.actions()} for n in self.walk()]
