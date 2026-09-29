# SPDX-License-Identifier: GPL-3.0-or-later
"""The alarm test with the phone's position (SosController.kt:166-170): its satellite route is
Android's position report, POST /api/sos/test {"satellite": true, latitude, longitude, altitude}
(MESHSAT-1430), followed through the Bridge's queue to the Hub's receipt; the test text goes on
the mesh and not by satellite as well."""
import time

SCENARIO = "all-four"
# lat, lon, accuracy (m), altitude (m), speed, heading, age (s): a GPS fix as geoclue gives it
ENV = {"MESHSAT_APP_FIX": "52.1601,4.497,8,3.9,,,5"}


def case_the_satellite_route_is_a_position_report(ctx):
    ctx.app.open("home")
    ctx.app.refresh()
    ctx.tree.wait_text("Messages can go out by satellite, mesh, SMS and the Hub.", timeout=15)
    before = ctx.bridge.count()
    ctx.tree.click("Test the alarm")
    ctx.tree.wait_text("Test the alarm?")
    ctx.tree.click_in_dialog("Send the test")
    deadline = time.time() + 15
    reports = []
    while time.time() < deadline and not reports:
        reports = [r["body"] for r in ctx.bridge.requests(before) if r["path"] == "/api/sos/test" and (r["body"] or {}).get("satellite")]
        time.sleep(0.5)
    assert reports == [{"satellite": True, "latitude": 52.1601, "longitude": 4.497, "altitude": 3.9}], reports
    sends = [r["body"] for r in ctx.bridge.requests(before) if r["path"] == "/api/messages/send"]
    assert not [b for b in sends if b.get("gateway") == "iridium"], f"the test text went by satellite as well: {sends}"
    assert [b for b in sends if "gateway" not in b], f"no test text on the mesh: {sends}"
    queued = ctx.bridge.state()["queued"]
    refs = [ref for ref, row in queued.items() if row.get("text_preview") == "Alarm test: position report to the Hub"]
    assert len(refs) == 1, queued
    ctx.app.open("sos")
    ctx.tree.wait_text("Waiting to send", timeout=10)
    ctx.bridge.delivery(refs[0], status="sent", ack_status="acked")
    ctx.tree.wait_text("Sent, and the Hub has it", timeout=20)
    ctx.shot("position-report-confirmed")
