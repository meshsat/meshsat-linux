# SPDX-License-Identifier: GPL-3.0-or-later
"""Emergency contacts (SosScreens.kt:445-659, EmergencyContact.kt) against the scripted Bridge with
a SIM: "Choose from your contacts" lists the address book one number per row (under test a vCard
file the case writes, never the phone's own address book) and adds the one picked, as Android
normalises it; the same number again is refused above "Or type a number"; a phone with no
address book is told so and typing opens; the typed path adds and folds away."""
import os

SCENARIO = "sim-ready"
ENV = {"MESHSAT_APP_CONTACTS": "{work}/contacts.vcf"}
VCF = ("BEGIN:VCARD\nVERSION:3.0\nFN:Anna de Vries\nTEL;TYPE=CELL:+31 6 1234-5678\nEND:VCARD\n"
       "BEGIN:VCARD\nVERSION:3.0\nFN:Huisarts\nTEL:(020) 555 01 00\nEND:VCARD\n")


def start(ctx, vcf: str | None = VCF) -> None:
    path = os.path.join(ctx.app.work, "contacts.vcf")
    if vcf is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(vcf)
    ctx.app.open("setup/safety")
    ctx.tree.find("button", name="Choose from your contacts", timeout=10)


def case_a_a_contact_picked_from_the_address_book(ctx):
    ctx.app.action("tab", "setup")
    start(ctx)
    ctx.tree.find("button", name="Or type a number")
    ctx.tree.click("Choose from your contacts")
    ctx.tree.wait_text("Huisarts", timeout=10)
    ctx.shot("picker")
    ctx.tree.click_in_dialog("Anna de Vries", contains=True)  # the picker's row, never the list behind it
    ctx.tree.find("button", name="Remove Anna de Vries", timeout=5)
    ctx.tree.wait_text("+31612345678")
    assert ctx.app.trace() is not None


def case_b_the_same_number_again_is_said(ctx):
    start(ctx)
    ctx.tree.click("Choose from your contacts")
    ctx.tree.wait_text("Huisarts", timeout=10)
    ctx.tree.click_in_dialog("Anna de Vries", contains=True)  # the picker's row, never the list behind it
    ctx.tree.wait_text("That number is already on the list.", timeout=5)
    ctx.tree.find("button", name="Or type a number")  # not typing: the line shows above it


def case_c_no_address_book_opens_typing(ctx):
    start(ctx, vcf=None)
    ctx.tree.click("Choose from your contacts")
    ctx.tree.wait_text("This phone has no contacts app. Type the number instead.", timeout=10)
    ctx.tree.find("text", name="Phone number, with country code")
    assert not ctx.tree.find_all("button", name="Or type a number"), "still offering to type while typing"


def case_d_a_typed_number_is_added_and_the_fields_fold_away(ctx):
    start(ctx)
    if ctx.tree.find_all("button", name="Or type a number"):
        ctx.tree.click("Or type a number")
    ctx.tree.set_text("Name", "Huisarts")
    ctx.tree.set_text("Phone number, with country code", "(020) 555 01 00")
    ctx.tree.click("Add this number")
    ctx.tree.find("button", name="Remove Huisarts", timeout=5)
    ctx.tree.wait_text("0205550100")
    ctx.tree.find("button", name="Or type a number", timeout=5)
    ctx.shot("contacts")
