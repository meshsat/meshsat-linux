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
        except (GLib.Error, RuntimeError):
            # A widget that went away between two bus calls (the screens rebuild their rows),
            # or a proxy the bus handed over uninitialised: not on view, seen again next walk.
            self.role, self.name, self.states = "defunct", "", None

    @property
    def showing(self) -> bool:
        return bool(self.states and self.states.contains(Atspi.StateType.SHOWING))

    @property
    def sensitive(self) -> bool:
        return bool(self.states and self.states.contains(Atspi.StateType.SENSITIVE))

    @property
    def checked(self) -> bool:
        return bool(self.states and (self.states.contains(Atspi.StateType.CHECKED) or self.states.contains(Atspi.StateType.PRESSED)))

    def actions(self) -> list:
        try:
            if "Action" not in self.acc.get_interfaces():
                return []
            return [Atspi.Action.get_action_name(self.acc, i) for i in range(Atspi.Action.get_n_actions(self.acc))]
        except (GLib.Error, RuntimeError):
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
        except (GLib.Error, RuntimeError):
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
            except (GLib.Error, RuntimeError):
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
            elif showing_only:
                # Nothing under a widget that is not showing can be showing: the other four
                # tabs and every closed section are skipped, which made a walk take seconds.
                return
            try:
                count = acc.get_child_count()
            except (GLib.Error, RuntimeError):
                return
            for j in range(count):
                try:
                    child = acc.get_child_at_index(j)
                except (GLib.Error, RuntimeError):
                    continue
                if child is not None:
                    visit(child, depth + 1)

        for attempt in range(3):
            out.clear()
            try:
                visit(app, 0)
                return out
            except RuntimeError:
                time.sleep(0.2)  # the tree changed under the walk: once more
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
        self._click_fresh(lambda: self.find(role, name=name, timeout=timeout))

    def click_containing(self, contains: str, role: str = "button", timeout: float = 5.0) -> None:
        self._click_fresh(lambda: self.find(role, contains=contains, timeout=timeout))

    @staticmethod
    def _click_fresh(find) -> None:
        """Click what `find` returns; a widget a screen replaced between the walk and the click is
        gone from the bus with no actions left, so it is looked up again (three tries)."""
        from . import HarnessError  # noqa: PLC0415

        for attempt in range(3):
            try:
                find().do("click")
                return
            except HarnessError as error:
                if "no 'click' action" not in str(error) or attempt == 2:
                    raise
                time.sleep(0.5)

    @staticmethod
    def _subtree(nodes: list, start: int) -> list:
        depth = nodes[start].depth
        out = [nodes[start]]
        for n in nodes[start + 1:]:
            if n.depth <= depth:
                break
            out.append(n)
        return out

    @staticmethod
    def _is_toast(subtree: list) -> bool:
        """An Adw.Toast reaches the bus as an "alert" too; its one button is "Dismiss"."""
        return [n.name for n in subtree if n.role == "button"] == ["Dismiss"]

    def _dialogs(self) -> list:
        nodes = self.walk()
        found = []
        for i, n in enumerate(nodes):
            if n.role in ("alert", "dialog"):
                subtree = self._subtree(nodes, i)
                if not self._is_toast(subtree):
                    found.append(subtree)
        return found

    def dialog(self, timeout: float = 5.0) -> list:
        """The widgets of the dialog in front (an alert or a sheet; never a toast), for a
        button that shares its name with one on the page behind it."""
        deadline = time.time() + timeout
        while True:
            found = self._dialogs()
            if found:
                return found[-1]
            if time.time() >= deadline:
                raise AssertionError(f"no dialog on view; on view: {self.summary()[:800]}")
            time.sleep(0.3)

    def click_in_dialog(self, name: str, timeout: float = 5.0, contains: bool = False) -> None:
        """A button of the dialog in front by its name (or a part of it, with `contains`)."""
        deadline = time.time() + timeout
        while True:
            for n in self.dialog(timeout):
                if n.role == "button" and (name in n.name if contains else n.name == name):
                    n.do("click")
                    return
            if time.time() >= deadline:
                raise AssertionError(f"no button {name!r} in the dialog; there: {[n.name for n in self.dialog(1) if n.role == 'button']}")
            time.sleep(0.3)

    def dialogs_open(self) -> bool:
        return bool(self._dialogs())

    # A Gtk.Switch reaches the bus as a "check box" with a "toggle" action in GTK 4.18.
    TOGGLES = ("check box", "toggle button", "switch", "radio button")

    def toggle(self, name: str, timeout: float = 5.0) -> None:
        """A switch, check box or toggle button by name (never the label beside it)."""
        node = self.switch(name, timeout)
        node.do("toggle" if "toggle" in node.actions() else "click")

    def switch(self, name: str, timeout: float = 5.0) -> Node:
        """A switch, check box or toggle button by its exact name; `.checked` is its state."""
        deadline = time.time() + timeout
        while True:
            for node in self.find_all(name=name):
                if node.role in self.TOGGLES:
                    return node
            if time.time() >= deadline:
                raise AssertionError(f"no switch or check box named {name!r}; on view: {self.summary()[:800]}")
            time.sleep(0.3)

    def switches(self, contains: str = "") -> list:
        return [n for n in self.walk() if n.role in self.TOGGLES and contains in n.name]

    def wait_switch(self, name: str, on: bool, timeout: float = 10.0) -> None:
        """Until the switch named `name` is on (or off): a list rebuilt after a write."""
        deadline = time.time() + timeout
        while True:
            try:
                if self.switch(name, 0.5).checked == on:
                    return
            except AssertionError:
                pass
            if time.time() >= deadline:
                raise AssertionError(f"the switch {name!r} never turned {'on' if on else 'off'}")
            time.sleep(0.3)

    def click_after(self, contains: str, name: str, role: str = "button", timeout: float = 5.0) -> None:
        """The first `name` button after the widget whose name holds `contains`, in the order the
        tree is walked: the Retry of one card among many that all have one."""
        deadline = time.time() + timeout
        while True:
            nodes = self.walk()
            start = next((i for i, n in enumerate(nodes) if contains in n.name), None)
            if start is not None:
                for node in nodes[start + 1:]:
                    if node.role == role and node.name == name:
                        node.do("click")
                        return
            if time.time() >= deadline:
                raise AssertionError(f"no {role} {name!r} after {contains!r}; on view: {self.summary()[:800]}")
            time.sleep(0.3)

    def count_text(self, value: str) -> int:
        return sum(1 for t in self.texts() if t == value)

    def wait_count(self, value: str, n: int, timeout: float = 10.0) -> None:
        deadline = time.time() + timeout
        while True:
            if self.count_text(value) == n:
                return
            if time.time() >= deadline:
                raise AssertionError(f"{value!r} shows {self.count_text(value)} times, not {n}")
            time.sleep(0.3)

    # The harmless answer of every dialog the app has, front dialog first.
    CLOSERS = ("Cancel", "Close", "Keep it", "Keep it on", "Not now", "Don't send", "Keep SOS on")

    def close_dialogs(self, attempts: int = 8) -> int:
        """Every dialog still open (a case that failed halfway leaves its dialogs), each answered
        with its harmless button. Returns how many were closed."""
        closed = 0
        for _ in range(attempts):
            found = self._dialogs()  # one look: a dialog may close between two
            if not found:
                return closed
            nodes = found[-1]
            buttons = {n.name: n for n in nodes if n.role == "button"}
            for name in self.CLOSERS:
                if name in buttons:
                    buttons[name].do("click")
                    closed += 1
                    time.sleep(0.5)
                    break
            else:
                raise HarnessError(f"a dialog with no harmless button is open: {[n.name for n in nodes if n.name][:8]}")
        return closed

    def set_text(self, name: str, value: str, timeout: float = 5.0) -> None:
        self.find("text", name=name, timeout=timeout).set_text(value)

    def entry_text(self, name: str) -> str:
        return self.find("text", name=name).text()

    def summary(self) -> str:
        return "; ".join(f"{n.role}:{n.name[:40]}" for n in self.walk() if n.name)

    def dump(self) -> list:
        return [{"depth": n.depth, "role": n.role, "name": n.name, "actions": n.actions()} for n in self.walk()]
