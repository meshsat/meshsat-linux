# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Safety, as SosScreens.kt's SosSettingsCard and SettingsScreen.kt's check-in timer:
who an SOS goes to, the name it gives, the test of the alarm, and the dead man's switch."""
from gi.repository import Gtk

from .. import api, sos, theme
from ..model import home as words_of_home
from ..model import sosrun
from ..screen import SubScreen
from ..widgets import Field, NavRow, SwitchRow, clear, confirm, icon_button, outlined_button, text, text_button

MAX_CONTACTS = 10  # as Android's EmergencyContact.MAX
TIMEOUTS = (("30", "30 min"), ("60", "1 hour"), ("120", "2 hours"), ("240", "4 hours"), ("480", "8 hours"))


def normalise_phone(raw: str) -> str | None:
    """EmergencyContact.normalisePhone: digits with an optional leading +, 3 to 15 digits."""
    cleaned = "".join(ch for ch in (raw or "") if ch.isdigit() or ch == "+")
    if cleaned.count("+") > 1 or ("+" in cleaned and not cleaned.startswith("+")):
        return None
    digits = cleaned.lstrip("+")
    if not digits.isdigit() or not 3 <= len(digits) <= 15:
        return None
    return cleaned


def adding(contacts: list, name: str, phone: str):
    """EmergencyContact.adding: (the new list, None) or (None, why not)."""
    number = normalise_phone(phone)
    if number is None:
        return None, "That is not a phone number. Use the country code, like +31 6 1234 5678."
    if any(c.get("phone") == number for c in contacts):
        return None, "That number is already in the list."
    if len(contacts) >= MAX_CONTACTS:
        return None, f"Up to {MAX_CONTACTS} contacts."
    clean = " ".join((name or "").replace("\t", " ").replace("\n", " ").split())[:40]
    return contacts + [{"name": clean, "phone": number}], None


class SafetyScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Safety")
        self.route = "setup/safety"
        zones = NavRow("outlined-fence", "Zones", lambda: app.toast("Zones come with 0.10.0."))
        zones.set_detail("Not on this device yet")
        self.column.append(zones)

        card = self.card("SOS")
        self.reach = text("", "body-small", theme.TEXT_SECONDARY, wrap=True)
        card.append(self.reach)
        self.name = Field("Your name in an SOS", "A MeshSat user", max_length=sos.MAX_NAME, on_change=self.name_changed)
        self.name.set_text(app.state.sos_name)
        card.append(self.name)
        self.contacts_title = text("Emergency contacts", "title-small")
        card.append(self.contacts_title)
        self.contacts_note = text("Each one gets an SMS with your position and a map link from this phone's SIM, whenever it has a signal.", "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.contacts_note)
        self.sms_note = text("", "body-small", theme.AMBER, wrap=True)
        card.append(self.sms_note)
        self.contact_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        card.append(self.contact_rows)
        self.no_sms = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.no_sms)
        # The phone's address book comes with 0.11.0; until then the number is typed.
        self.new_name = Field("Name", max_length=40)
        card.append(self.new_name)
        self.new_phone = Field("Phone number, with country code", "+31 6 1234 5678", purpose=Gtk.InputPurpose.PHONE, max_length=24)
        card.append(self.new_phone)
        self.add_button = outlined_button("Add this number", self.add_a_contact)
        card.append(self.add_button)
        card.append(text("Test the alarm", "title-small"))
        card.append(text("Sends a test on every route an SOS would take, and shows what got through. It says it is a test, and raises nothing at the Hub.", "body-small", theme.TEXT_MUTED, wrap=True))
        self.test_button = outlined_button("Test the alarm", self.test_asked)
        card.append(self.test_button)
        self.no_way = text("A test needs somewhere to go first.", "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.no_way)

        timer = self.card("Check-in timer (dead man's switch)")
        self.enabled = SwitchRow("Enabled", self.set_enabled)
        timer.append(self.enabled)
        self.timeout_title = text("Timeout (triggers SOS if no activity)", "body-small", theme.TEXT_MUTED)
        timer.append(self.timeout_title)
        self.timeout_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(4))
        self.timeouts = {}
        for value, label in TIMEOUTS:
            row = Gtk.Button()
            row.add_css_class("flat")
            row.add_css_class("timeout-row")
            row.update_property([Gtk.AccessibleProperty.LABEL], [label])
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            inner.append(text(label, "body-small"))
            mark = text("selected", "body-small", theme.GREEN, xalign=1.0)
            mark.set_hexpand(True)
            mark.set_visible(False)
            inner.append(mark)
            row.set_child(inner)
            row.connect("clicked", lambda _b, v=value: self.set_timeout(int(v)))
            self.timeouts[value] = (row, mark)
            self.timeout_rows.append(row)
        timer.append(self.timeout_rows)
        self.triggered = text_button("TRIGGERED — SOS was sent. Tap to reset.", self.reset_timer)
        self.triggered.get_child().add_css_class("body-small")
        from ..widgets import paint  # noqa: PLC0415

        paint(self.triggered.get_child(), theme.RED)
        timer.append(self.triggered)
        timer.append(text("Automatically sends SOS if no user activity (message send, button press) within the timeout period.", "body-small", theme.TEXT_MUTED, wrap=True))
        self._contacts_key = None
        self.update(app.state)

    # The name
    def name_changed(self, value: str) -> None:
        if value != self.app.state.sos_name:
            self.app.set_sos_name(value)

    # Contacts
    def add_a_contact(self) -> None:
        new, why = adding(self.app.state.contacts, self.new_name.text, self.new_phone.text)
        if why:
            self.new_phone.set_error(why)
            return
        self.new_phone.set_error(None)
        self.app.set_contacts(new)
        self.new_name.set_text("")
        self.new_phone.set_text("")
        self.update(self.app.state)

    def remove_contact(self, phone: str) -> None:
        self.app.set_contacts([c for c in self.app.state.contacts if c.get("phone") != phone])
        self.update(self.app.state)

    # The test
    def test_asked(self) -> None:
        s = self.app.state
        parts = sosrun.test_parts(s, s.sos_name)
        confirm(self.app, "Test the alarm?", sosrun.test_dialog_text(sos.test_text(s.sos_name), parts), "Send the test", self.test_fire, cancel="Not now")

    def test_fire(self) -> None:
        self.app.sos.start(self.app.state, test=True, trigger="hold")
        self.app.poller.poll_now()
        self.app.open_route("sos")

    # The timer
    def set_enabled(self, on: bool) -> None:
        current = self.app.state.deadman or {}
        self.call("/api/deadman", lambda a: self.app.poller.poll_now(), body={"enabled": bool(on), "timeout_min": current.get("timeout_min", 240)})

    def set_timeout(self, minutes: int) -> None:
        current = self.app.state.deadman or {}
        self.call("/api/deadman", lambda a: self.app.poller.poll_now(), body={"enabled": current.get("enabled", False), "timeout_min": minutes})

    def reset_timer(self) -> None:
        current = self.app.state.deadman or {}
        self.call("/api/deadman", lambda a: self.app.poller.poll_now(), body={"enabled": current.get("enabled", False), "timeout_min": current.get("timeout_min", 240)})

    def update(self, s: api.State) -> None:
        self.reach.set_text(words_of_home.reach_sentence(s))
        can_sms = bool((s.cellular or {}).get("connected")) and bool(s.bridge)
        reason = s.sms_reason()
        for w in (self.contacts_title, self.contacts_note, self.contact_rows, self.new_name, self.new_phone, self.add_button):
            w.set_visible(can_sms)
        self.sms_note.set_text(f"SMS is not ready yet: {reason[0].lower() + reason[1:]}" if can_sms and reason else "")
        self.sms_note.set_visible(bool(can_sms and reason))
        self.no_sms.set_text(((reason or "This phone cannot send SMS.") + " An SOS goes by satellite, the mesh and the Hub.") if not can_sms else "")
        self.no_sms.set_visible(not can_sms)
        key = tuple((c.get("name"), c.get("phone")) for c in s.contacts)
        if key != self._contacts_key:
            self._contacts_key = key
            clear(self.contact_rows)
            for c in s.contacts:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
                row.add_css_class("contact-row")
                texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                texts.set_hexpand(True)
                texts.set_valign(Gtk.Align.CENTER)
                texts.append(text(c.get("name") or c["phone"], "body-medium"))
                if c.get("name"):
                    texts.append(text(c["phone"], "body-small", theme.TEXT_SECONDARY, mono=True))
                row.append(texts)
                row.append(icon_button("outlined-close", lambda phone=c["phone"]: self.remove_contact(phone), 20, theme.TEXT_SECONDARY, f"Remove {c.get('name') or c['phone']}"))
                self.contact_rows.append(row)
        room = len(s.contacts) < MAX_CONTACTS
        self.new_name.set_visible(can_sms and room)
        self.new_phone.set_visible(can_sms and room)
        self.add_button.set_visible(can_sms and room)
        run = self.app.sos.active()
        can_test = sosrun.anywhere(s) and run is None
        self.test_button.set_sensitive(can_test)
        self.no_way.set_visible(not sosrun.anywhere(s))
        d = s.deadman or {}
        self.enabled.set_active(bool(d.get("enabled")))
        on = bool(d.get("enabled"))
        self.timeout_title.set_visible(on)
        self.timeout_rows.set_visible(on)
        for value, (row, mark) in self.timeouts.items():
            selected = str(d.get("timeout_min", "")) == value
            mark.set_visible(selected)
            (row.add_css_class if selected else row.remove_css_class)("selected")
        self.triggered.set_visible(on and bool(d.get("triggered")))
