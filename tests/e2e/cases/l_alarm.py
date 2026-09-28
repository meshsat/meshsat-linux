# SPDX-License-Identifier: GPL-3.0-or-later
"""The alarm test on the live bench: its text goes out on the mesh through the Bridge and is
heard at the far end (the runner checks the listener's log after the run). Nothing else is
billed or paged: no SIM, no modem, no Hub on the bench, so those routes are listed as not
used, exactly as Android lists them."""
import os
import time

from driver import BenchError

SCENARIO = None  # the live Bridge


def case_the_test_text_reaches_the_tdeck(ctx):
    status = ctx.bridge.get("/api/status")
    if not status.get("connected"):
        raise BenchError("the node is not connected: no mesh to test on")
    ctx.app.open("home")
    ctx.tree.find("button", name="Test the alarm", timeout=15)
    ctx.app.mark()
    ctx.tree.click("Test the alarm")
    ctx.tree.wait_text("Test the alarm?")
    body = next(t for t in ctx.tree.texts() if t.startswith("The test text is"))
    assert "the text on the mesh" in body, body
    ctx.tree.click_in_dialog("Send the test")
    text = "Test from A MeshSat user: checking the MeshSat alarm routes. No help needed."
    deadline = time.time() + 20
    while time.time() < deadline:
        sends = [e for e in ctx.app.http_since_mark("POST", "/api/messages/send") if e.get("status") == 200]
        if sends:
            break
        time.sleep(1)
    else:
        raise AssertionError("the test text never left through the Bridge")
    ctx.app.open("sos")
    ctx.tree.wait_text("Alarm test", timeout=10)
    ctx.tree.wait_text("Mesh, everyone in range")
    ctx.tree.wait_text("Alarm test finished", timeout=30)
    ctx.tree.wait_text("Not used")
    ctx.shot("alarm-test")
    expect = os.environ.get("MESHSAT_E2E_EXPECT_FILE", "")
    if expect:
        with open(expect, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    ctx.note(f"the test text left through the Bridge; the far end must have heard {text!r}")
    ctx.app.open("home")
