# SPDX-License-Identifier: GPL-3.0-or-later
"""The alarm test's notification (notification.alarm-test; SosController.notify at v2.19.4):
while a test runs the app posts "Alarm test running", the routes in one line
(SosProgress.summary) and "Stop test", one notification kept up to date in place; a tap opens the
test's screen, "Stop test" stops the test, and the notification goes when the test ends. The test
here takes the mesh (sent at once) and the Hub, which the Bridge answers 503 ("the Hub is not
connected") until a case lets it through, so the test runs as long as a case needs it to.

Needs wip-100/patch-100-alarm-notify.py (MESHSAT_APP_NOTIFY, one notification) and
wip-100/patch-100-outside.py (NOTIFICATIONS: the stand-in daemon without the notifier)."""
import time

SCENARIO = "hub-set-up"
NOTIFICATIONS = True
ENV = {"MESHSAT_APP_NOTIFY": "1"}
TITLE = "Alarm test running"  # SosController.notify: r.test -> "Alarm test running"
STOP = "Stop test"  # its action while the run is active
RUNNING = "Sent by mesh. Still trying the Hub online."  # SosProgress.summary: mesh sent, the Hub waiting
BANNER = "Alarm test running. Tap to see it."  # SosScreens.kt:276
NO_HUB = {"error": "the Hub is not connected"}  # the Bridge's 503 for POST /api/sos/test without its Hub link (sos_handler.go)


def start(ctx) -> int:
    """A test from Home, the Hub not reachable; the number of notifications before it."""
    if ctx.notifications is None:
        from driver import HarnessError  # noqa: PLC0415

        raise HarnessError("no stand-in notification daemon: run.py needs NOTIFICATIONS (patch-100-outside.py)")
    ctx.bridge.scenario("hub-set-up")
    ctx.bridge.set("POST /api/sos/test", NO_HUB, status=503)
    ctx.app.open("home")
    ctx.app.refresh()
    ctx.tree.find("button", name="Test the alarm", timeout=15)
    before = ctx.notifications.count()
    ctx.tree.click("Test the alarm")
    ctx.tree.wait_text("Test the alarm?", timeout=8)
    ctx.tree.click_in_dialog("Send the test")
    return before


def alarm(ctx, since: int) -> list:
    return [p for p in ctx.notifications.since(since) if p["summary"] == TITLE]


def wait_alarm(ctx, since: int, body: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = [p for p in alarm(ctx, since) if p["body"] == body]
        if found:
            return found[-1]
        time.sleep(0.3)
    raise AssertionError(f"no {TITLE!r} saying {body!r}; posted: {ctx.notifications.since(since)}")


def one_in_place(posts: list) -> int:
    """Android posts one notification (NOTIFICATION_ID) and updates it: one id, each later post
    replacing the first."""
    ids = {p["id"] for p in posts}
    assert len(ids) == 1, f"{len(ids)} notifications for one test: {posts}"
    assert posts[0]["replaces"] == 0 and all(p["replaces"] == posts[0]["id"] for p in posts[1:]), posts
    return posts[0]["id"]


def actions(posted: dict) -> dict:
    flat = posted["actions"]
    return dict(zip(flat[0::2], flat[1::2]))


def routed_to(ctx, route: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if [e for e in ctx.app.trace_since_mark() if e.get("kind") == "route" and e.get("route") == route]:
            return True
        time.sleep(0.3)
    return False


def case_a_the_notification_in_androids_words_kept_in_place(ctx):
    before = start(ctx)
    posted = wait_alarm(ctx, before, RUNNING)
    assert posted["app"] == "MeshSat", posted
    assert posted["hints"].get("desktop-entry") == ctx.app.app_id, posted["hints"]
    assert posted["hints"].get("urgency") == 1, posted["hints"]  # PRIORITY_HIGH; 2 would be critical
    acts = actions(posted)
    assert acts.get("app.stop-test") == STOP, acts
    assert "default" in acts, f"a tap on it opens nothing: {acts}"
    ctx.tree.find("button", contains=BANNER, timeout=8)
    ctx.tree.wait_text(RUNNING, timeout=8)  # Home's SOS card says the same line
    number = one_in_place(alarm(ctx, before))
    ctx.shot("alarm-test-running")
    # The Hub is asked again every 15 s: still that one notification
    count = ctx.bridge.count()
    ctx.bridge.wait_request("POST", "/api/sos/test", since=count, timeout=25)
    time.sleep(1.5)
    number = one_in_place(alarm(ctx, before))
    # Stop test, on the notification
    posts = len(alarm(ctx, before))
    ctx.notifications.invoke(number, "app.stop-test")
    ctx.tree.wait_gone(BANNER, timeout=10)
    ctx.app.open("sos")
    ctx.tree.wait_text("Alarm test finished", timeout=10)
    time.sleep(2)
    assert len(alarm(ctx, before)) == posts, f"posted again after Stop test: {alarm(ctx, before)[posts:]}"
    # The daemon removes a notification whose action was taken unless it is resident (the
    # notification spec; Phosh's notify-manager), which is where this one goes.
    assert not alarm(ctx, before)[-1]["hints"].get("resident"), "resident: it would stay after Stop test"


def case_b_it_goes_when_the_test_ends(ctx):
    before = start(ctx)
    number = wait_alarm(ctx, before, RUNNING)["id"]
    ctx.bridge.set("POST /api/sos/test", {"status": "sent", "message": "Test from A MeshSat user: checking the MeshSat alarm routes. No help needed."})
    # The next ask (15 s) reaches the Hub, the test settles, the app takes its notification back
    deadline = time.time() + 30
    while time.time() < deadline and number not in ctx.notifications.closed:
        time.sleep(0.5)
    assert number in ctx.notifications.closed, f"the notification stayed after the test ended; closed: {ctx.notifications.closed}"
    one_in_place(alarm(ctx, before))
    ctx.app.open("sos")
    ctx.tree.wait_text("Alarm test finished", timeout=10)


def case_c_a_tap_opens_the_test(ctx):
    before = start(ctx)
    posted = wait_alarm(ctx, before, RUNNING)
    ctx.app.open("people")
    ctx.app.mark()
    ctx.notifications.invoke(posted["id"], "default")
    assert routed_to(ctx, "sos"), f"a tap did not open the test; the trace: {ctx.app.trace_since_mark()[-8:]}"
    ctx.tree.wait_text("Satellite: no satellite modem has been connected to this phone yet.", timeout=8)
    ctx.tree.find("button", name=STOP, timeout=8)
    posts = len(alarm(ctx, before))
    ctx.app.mark()
    ctx.tree.click(STOP)
    ctx.tree.wait_text("Alarm test finished", timeout=10)
    time.sleep(2)
    assert len(alarm(ctx, before)) == posts, "posted again after the test stopped"
    taken_back = [e for e in ctx.app.trace_since_mark() if e.get("kind") == "notification" and e.get("withdrawn")]
    assert taken_back, "the app did not take its notification back when the test stopped"
