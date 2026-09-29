# SPDX-License-Identifier: GPL-3.0-or-later
"""The phone's address book for "Choose from your contacts" (SosScreens.kt:445-659): on Phosh it is
Evolution Data Server, where GNOME Contacts keeps its people. Only names and phone numbers are
read, one row per number (as Android's phone-number picker lists them), and nothing is kept but
the row the person picks. None means the phone has no address book, which Android says as
"This phone has no contacts app."

Under test (MESHSAT_APP_TEST=1) the address book is never the phone's own: it is the vCard file
MESHSAT_APP_CONTACTS, or none at all."""
import os

from . import system
from .model import contacts as words


def rows():
    """[(name, number)], sorted by name, or None for no address book. Blocking: call it off the
    main loop."""
    if system.TEST or os.environ.get("MESHSAT_APP_CONTACTS"):
        path = os.environ.get("MESHSAT_APP_CONTACTS", "")
        try:
            with open(path, encoding="utf-8") as handle:
                return sort(words.rows_of_vcards(handle.read()))
        except OSError:
            return None
    try:
        import gi  # noqa: PLC0415

        gi.require_version("EDataServer", "1.2")
        gi.require_version("EBook", "1.2")
        gi.require_version("EBookContacts", "1.2")
        from gi.repository import EBook, EBookContacts, EDataServer, GLib  # noqa: PLC0415
    except (ValueError, ImportError):
        return None
    try:
        registry = EDataServer.SourceRegistry.new_sync(None)
        sources = registry.list_enabled(EDataServer.SOURCE_EXTENSION_ADDRESS_BOOK)
    except GLib.Error:
        return None
    if not sources:
        return None
    out = []
    for source in sources:
        try:
            client = EBook.BookClient.connect_sync(source, 5, None)
            found = client.get_contacts_sync('(exists "tel")', None)
        except GLib.Error:
            continue
        people = found[1] if isinstance(found, tuple) else found
        for person in people or []:
            name = person.get_property("full-name") or person.get_property("file-as") or ""
            for attribute in person.get_attributes(EBookContacts.ContactField.TEL):
                out.append((name, attribute.get_value() or ""))
    return sort(out)


def sort(found: list) -> list:
    return sorted(found, key=lambda row: (row[0].casefold(), row[1]))
