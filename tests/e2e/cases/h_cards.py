# SPDX-License-Identifier: GPL-3.0-or-later
"""People you carry (ContactCards.kt) against the scripted Bridge: the section in Android's
words, My card as the Bridge signs it (MESHSAT-1416) with its QR code and Copy, the words when
the Bridge has no key yet, a card pasted and added as imported, the three errors, a card read
by the camera (a QR code shown to GStreamer's zbar through the scanner) and added as scanned,
Forget, and the scanner that keeps looking until a code shows and adds nothing when cancelled. The cards are the fixed vectors Android's JVM and the Bridge's Go test produce."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from driver.qr import write_blank_png, write_png  # noqa: E402

SCENARIO = "mesh-only"
ENV = {"MESHSAT_APP_SCAN_SOURCE": 'filesrc location="{work}/scan.png" ! pngdec ! imagefreeze'}
KYRIAKOS = ("meshsat:contact:1:S3lyaWFrb3MfQTZFSHZfUE9FTDRkY04wWTUwdkFtV2ZrMWpDYnBRMWZIZHlHWkJKVk1iZx8hYmY2ZWU3YmMfbXNhLWZsYW5ldXIfMTc4OTkwMDAwMA."
            "oKXEDt4bFgUMr1qBHOBVgUiKRqAi50xVXnxeSukzSnMqXztpxqSABg4L9xSqbDVJdlTrh76ycQN_f1A22DgaAA")
ALTERED = ("meshsat:contact:1:TWFsbG9yeR9BNkVIdl9QT0VMNGRjTjBZNTB2QW1XZmsxakNicFExZkhkeUdaQkpWTWJnHyFiZjZlZTdiYx9tc2EtZmxhbmV1ch8xNzg5OTAwMDAw."
           "oKXEDt4bFgUMr1qBHOBVgUiKRqAi50xVXnxeSukzSnMqXztpxqSABg4L9xSqbDVJdlTrh76ycQN_f1A22DgaAA")
DAMAGED = "meshsat:contact:1:U29tZW9uZR9BQUFBHx8fMA.AAAA"
FP = "5647 5aa7 5463 474c"


def on_people(ctx, scenario: str = "mesh-only") -> None:
    ctx.bridge.scenario(scenario)
    ctx.app.tab("people")
    ctx.tree.wait_text("People you carry", timeout=10)


def paste(ctx, value: str) -> None:
    ctx.tree.click("Paste a card instead")
    ctx.tree.wait_text("A card that did not come through the camera is kept as imported: the signature still holds, but nothing says who passed it on.")
    ctx.tree.set_text("meshsat:contact:1:...", value)
    ctx.tree.click_in_dialog("Read it")


def case_a_the_section_in_androids_words(ctx):
    on_people(ctx)
    ctx.tree.wait_text("Cards swapped face to face by QR code. Read the fingerprint aloud to each other: it is what says the card is theirs.")
    ctx.tree.wait_text("No cards yet.")
    for button in ("My card", "Scan a card", "Paste a card instead"):
        ctx.tree.find("button", name=button)


def case_b_my_card_is_the_one_the_bridge_signs(ctx):
    on_people(ctx)
    ctx.tree.click("My card")
    ctx.tree.wait_text(FP, timeout=10)
    ctx.tree.wait_text("Read this out to whoever scans it.")
    ctx.tree.find(name="This phone's contact card as a QR code")
    ctx.shot("my-card")
    ctx.app.mark()
    ctx.tree.click_in_dialog("Copy")
    ctx.app.wait_toast("Card copied")
    ctx.tree.click_in_dialog("Done")


def case_c_no_key_no_card(ctx):
    on_people(ctx)
    ctx.bridge.set("GET /api/contacts/card", {"error": "routing not initialized"}, status=503)
    ctx.tree.click("My card")
    ctx.tree.wait_text("The gateway has not started yet, so this phone has no key to sign a card with.", timeout=10)
    assert not [n for n in ctx.tree.dialog() if n.role == "button" and n.name == "Copy"], "Copy offered with no card"
    ctx.tree.click_in_dialog("Done")


def case_d_a_pasted_card_is_added_as_imported(ctx):
    on_people(ctx)
    paste(ctx, KYRIAKOS)
    names = [n.name for n in ctx.tree.dialog()]
    for words in ("Add Kyriakos?", "Check this fingerprint against the one on their screen. If it differs, the card is not theirs.", FP,
                  "Mesh node !bf6ee7bc", "Hub msa-flaneur", "Imported as text."):
        assert words in names, (words, names)
    ctx.tree.click_in_dialog("Add")
    ctx.tree.wait_text("Imported as text · mesh !bf6ee7bc · msa-flaneur", timeout=5)
    ctx.tree.wait_gone("No cards yet.")
    ctx.shot("card-added")


def case_e_the_three_errors(ctx):
    on_people(ctx)
    for value, words in ((ALTERED, "That card has been altered since it was made. Not saved."), (DAMAGED, "That is a MeshSat card, but a damaged one."),
                         ("https://meshsat.net", "That is not a MeshSat contact card."), ("", "That is not a MeshSat contact card.")):
        ctx.app.mark()
        paste(ctx, value)
        ctx.app.wait_toast(words)


def case_f_a_card_read_by_the_camera_is_added_as_scanned(ctx):
    on_people(ctx)
    anna = ctx.app.work + "/anna.txt"
    # Anna's card: another key (seed 07 x 32), made here as Android makes one.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: PLC0415
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: PLC0415

    sys.path.insert(0, ctx.app.app_dir)
    from meshsat.model import cards  # noqa: PLC0415

    private = Ed25519PrivateKey.from_private_bytes(bytes([7]) * 32)
    pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    card = cards.encode("Anna", pub, "!a1b3c2ec", "", 1789900000, private.sign)
    with open(anna, "w", encoding="utf-8") as handle:
        handle.write(card)
    write_png(card, ctx.app.work + "/scan.png")
    ctx.tree.click("Scan a card")
    ctx.tree.wait_text("Add Anna?", timeout=15)
    names = [n.name for n in ctx.tree.dialog()]
    assert "Scanned from a screen in front of you." in names and "fe81 2c12 f3ab 4ce6" in names, names
    ctx.tree.click_in_dialog("Add")
    ctx.tree.wait_text("Scanned in person · mesh !a1b3c2ec", timeout=5)
    events = [e for e in ctx.app.trace() if e.get("kind") == "scanned"]
    assert events and events[-1]["how"] == "camera", events[-2:]
    ctx.shot("scanned")


def case_g_forget(ctx):
    on_people(ctx)
    ctx.tree.wait_text("Scanned in person · mesh !a1b3c2ec", timeout=5)
    before = ctx.tree.count_text("Imported as text · mesh !bf6ee7bc · msa-flaneur")
    ctx.tree.click_after("Anna", "Forget")
    ctx.tree.wait_gone("Scanned in person · mesh !a1b3c2ec", timeout=5)
    assert ctx.tree.count_text("Imported as text · mesh !bf6ee7bc · msa-flaneur") == before
    time.sleep(0.5)


def case_h_the_scanner_keeps_looking_and_cancel_adds_nothing(ctx):
    on_people(ctx)
    before = ctx.tree.count_text("Scanned in person")
    write_blank_png(ctx.app.work + "/scan.png")
    ctx.app.mark()
    ctx.tree.click("Scan a card")
    ctx.tree.wait_text("Scan the other phone's card", timeout=10)
    time.sleep(2)  # frames keep coming and none holds a code: the scanner stays open
    names = [n.name for n in ctx.tree.dialog()]
    assert "Open an image" in names and "Cancel" in names, names
    ctx.shot("scanner")
    ctx.tree.click_in_dialog("Cancel")
    ctx.tree.wait_gone("Scan the other phone's card", timeout=5)
    events = [e for e in ctx.app.trace() if e.get("kind") == "scanned"]
    assert events and events[-1]["length"] == 0 and events[-1]["how"] == "", events[-2:]
    assert ctx.tree.count_text("Scanned in person") == before
