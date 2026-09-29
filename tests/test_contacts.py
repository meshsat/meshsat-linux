# SPDX-License-Identifier: GPL-3.0-or-later
"""Emergency contacts (0.11.0) against MeshSat Android v2.19.4: EmergencyContactAddingTest ported
(the two contactsAppAmong cases test Android's package manager and have no counterpart), and the
address book's rows read from vCards."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))

from meshsat.model import contacts  # noqa: E402


class EmergencyContactAddingTest(unittest.TestCase):
    """app/src/test/java/net/meshsat/android/EmergencyContactAddingTest.kt"""

    def test_a_number_as_a_contacts_app_writes_it_is_taken(self):
        new, why = contacts.adding([], "Anna de Vries", "+31 6 1234-5678")
        self.assertIsNone(why)
        self.assertEqual(new, [{"name": "Anna de Vries", "phone": "+31612345678"}])
        new, why = contacts.adding(new, "Huisarts", "(020) 555 01 00")
        self.assertEqual(new[-1], {"name": "Huisarts", "phone": "0205550100"})

    def test_the_same_person_picked_twice_is_said_not_doubled(self):
        new, why = contacts.adding([{"name": "Anna", "phone": "+31612345678"}], "Anna again", "+31 6 12345678")
        self.assertEqual((new, why), (None, "That number is already on the list."))

    def test_a_contact_with_no_number_or_not_a_number_is_refused_in_words(self):
        self.assertEqual(contacts.adding([], "Bo", ""), (None, "That contact has no phone number."))
        self.assertEqual(contacts.adding([], "Bo", "bo@example.org"), (None, "That is not a phone number."))

    def test_the_list_stops_at_its_limit(self):
        full = [{"name": f"C{i}", "phone": f"+3161234567{i}"} for i in range(10)]
        self.assertEqual(contacts.adding(full, "One more", "+31699999999"), (None, "The list is full: 10 contacts at most."))

    def test_a_name_cannot_break_the_stored_list(self):
        new, _why = contacts.adding([], "Anna\tde\nVries", "+31612345678")
        self.assertEqual(new[0]["name"], "Anna de Vries")


class NormaliseTest(unittest.TestCase):
    def test_what_android_takes_and_refuses(self):
        for raw, want in (("+31 6 1234-5678", "+31612345678"), (" 112 ", "112"), ("12", None), ("+1234567890123456", None), ("06/12345678", None),
                          ("abc123", None), ("++31612345678", None), ("٣١٢٣٤٥", None), ("31 612", None), ("+31.6.12", "+31612")):
            self.assertEqual(contacts.normalise_phone(raw), want, raw)

    def test_the_full_list_is_said_before_the_number_is_read(self):
        full = [{"name": "", "phone": f"+3161234567{i}"} for i in range(10)]
        self.assertEqual(contacts.adding(full, "x", "not a number")[1], contacts.FULL)

    def test_names(self):
        self.assertEqual(contacts.clean_name("  Anna   de  Vries  "), "Anna   de  Vries")
        self.assertEqual(len(contacts.clean_name("x" * 60)), 40)
        self.assertEqual(contacts.remove_name({"name": "", "phone": "+31612345678"}), "Remove +31612345678")
        self.assertEqual(contacts.remove_name({"name": "Anna", "phone": "+316"}), "Remove Anna")


class AddressBookTest(unittest.TestCase):
    def test_one_row_per_number(self):
        vcf = ("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Anna de Vries\r\nTEL;TYPE=CELL:+31 6 1234-5678\r\nTEL;TYPE=HOME:020 555 0100\r\nEND:VCARD\r\n"
               "BEGIN:VCARD\nVERSION:3.0\nFN:Nobody\nEMAIL:n@example.org\nEND:VCARD\n"
               "BEGIN:VCARD\nVERSION:3.0\nFN:Huisarts\nTEL:(020) 555 01 00\nEND:VCARD\n")
        self.assertEqual(contacts.rows_of_vcards(vcf), [("Anna de Vries", "+31 6 1234-5678"), ("Anna de Vries", "020 555 0100"), ("Huisarts", "(020) 555 01 00")])


if __name__ == "__main__":
    unittest.main()
