# SPDX-License-Identifier: GPL-3.0-or-later
"""Emergency contacts (data/EmergencyContact.kt, ui/screens/SosScreens.kt:445-659): who an SOS
texts, picked from the phone's address book or typed, at most ten, each a name and a number
as Android keeps them. Pure."""
MAX = 10

# ── Words (SosScreens.kt, EmergencyContact.kt) ───────────────────────────────────────────────
TITLE = "Emergency contacts"
NOTE = "Each one gets an SMS with your position and a map link from this phone's SIM, whenever it has a signal."
CHOOSE = "Choose from your contacts"
TYPE = "Or type a number"
NAME = "Name"
NUMBER = "Phone number, with country code"
NUMBER_HINT = "+31 6 1234 5678"
ADD = "Add this number"
UNREADABLE = "Could not read that contact. Type the number instead."
NO_APP = "This phone has no contacts app. Type the number instead."
FULL = f"The list is full: {MAX} contacts at most."
NO_NUMBER = "That contact has no phone number."
NOT_A_NUMBER = "That is not a phone number."
ALREADY = "That number is already on the list."
NAME_MAX = 40
NUMBER_MAX = 24


def remove_name(contact: dict) -> str:
    return f"Remove {(contact.get('name') or '').strip() or contact.get('phone', '')}"


def normalise_phone(raw: str):
    """EmergencyContact.normalisePhone: one leading + kept, only space - . ( ) removed, then 3 to
    15 ASCII digits; anything else is not a number (None)."""
    t = (raw or "").strip()
    plus = t.startswith("+")
    body = t[1:] if plus else t
    for ch in " -.()":
        body = body.replace(ch, "")
    if not 3 <= len(body) <= 15 or not all("0" <= ch <= "9" for ch in body):
        return None
    return ("+" if plus else "") + body


def clean_name(name: str) -> str:
    """Tabs and line breaks become spaces, then trimmed, then the first 40 characters; inner runs
    of spaces are kept."""
    return (name or "").replace("\t", " ").replace("\n", " ").strip()[:NAME_MAX]


def adding(contacts: list, name: str, raw_phone: str) -> tuple:
    """EmergencyContact.adding, in its order: (the new list, None) or (None, why not)."""
    if len(contacts) >= MAX:
        return None, FULL
    number = normalise_phone(raw_phone)
    if number is None:
        return None, NO_NUMBER if not (raw_phone or "").strip() else NOT_A_NUMBER
    if any(c.get("phone") == number for c in contacts):
        return None, ALREADY
    return contacts + [{"name": clean_name(name), "phone": number}], None


def typed_name(value: str) -> str:
    """What the Name field keeps while typing (SosScreens.kt:551)."""
    return value.replace("\t", " ").replace("\n", " ")[:NAME_MAX]


def rows_of_vcards(text: str) -> list:
    """(name, number) for every number of every vCard in `text`, as the address book's phone
    list gives them (one row per number)."""
    out, name, numbers = [], "", []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        upper = line.upper()
        if upper == "BEGIN:VCARD":
            name, numbers = "", []
        elif upper.startswith("FN:") or upper.startswith("FN;"):
            name = line.split(":", 1)[1].strip()
        elif upper.startswith("TEL"):
            numbers.append(line.split(":", 1)[1].strip() if ":" in line else "")
        elif upper == "END:VCARD":
            out.extend((name, number) for number in numbers)
    return out
