# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Safety, as SosScreens.kt's SosSettingsCard and SettingsScreen.kt's check-in timer:
who an SOS goes to, the name it gives, the test of the alarm, and the dead man's switch."""
import threading

from gi.repository import GLib, Gtk

from .. import addressbook, api, sos, theme
from ..layout import restyle
from ..model import contacts as book
from ..model import home as words_of_home
from ..screen import SubScreen
from ..widgets import Field, NavRow, Sheet, SwitchRow, clear, filled_button, icon_button, name_widget, outlined_button, paint, text, text_button
from .sos import ask_test

TIMEOUTS = (("30", "30 min"), ("60", "1 hour"), ("120", "2 hours"), ("240", "4 hours"), ("480", "8 hours"))


class SafetyScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Safety")
        self.route = "setup/safety"
        # SetupPageLinks (MeshSatUI.kt:250): the row full width under the '<- Safety' row, and fixed
        # there while the cards scroll under it.
        zones = NavRow("outlined-fence", "Zones", lambda: app.open_route("geofence"))
        zones.set_detail("Alerts when someone enters or leaves an area")
        self.insert_child_after(zones, self.header)

        card = self.card("SOS")
        self.reach = text("", "body-small", theme.TEXT_SECONDARY, wrap=True)
        card.append(self.reach)
        self.name = Field("Your name in an SOS", "A MeshSat user", max_length=sos.MAX_NAME, on_change=self.name_changed)
        self.name.set_text(app.state.sos_name)
        card.append(self.name)
        self.contacts_title = text(book.TITLE, "title-small")
        card.append(self.contacts_title)
        self.contacts_note = text(book.NOTE, "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.contacts_note)
        self.sms_note = text("", "body-small", theme.AMBER, wrap=True)
        card.append(self.sms_note)
        # SosScreens.kt:517-530: each contact a row of the card's Column, 8 dp apart.
        self.contact_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        card.append(self.contact_rows)
        self.no_sms = text("", "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.no_sms)
        # SosScreens.kt:531-581: the address book first; typing the number is the other way. An
        # error shows above "Or type a number", or under the number field while typing. Android's
        # Button and OutlinedButton here wrap their words, from the left.
        self.typing = False
        self.adding_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.choose = filled_button(book.CHOOSE, self.choose_contact, expand=False)
        self.choose.set_halign(Gtk.Align.START)
        self.adding_box.append(self.choose)
        self.pick_error = text("", "body-small", theme.AMBER, wrap=True)
        self.pick_error.set_visible(False)
        self.adding_box.append(self.pick_error)
        self.type_button = text_button(book.TYPE, self.start_typing)
        paint(self.type_button.get_child(), theme.TEXT_SECONDARY)
        self.type_button.set_halign(Gtk.Align.START)
        self.adding_box.append(self.type_button)
        self.new_name = Field(book.NAME)
        self.new_name.on_change = self.name_typed
        self.adding_box.append(self.new_name)
        self.new_phone = Field(book.NUMBER, book.NUMBER_HINT, purpose=Gtk.InputPurpose.PHONE)
        self.new_phone.on_change = self.number_typed
        self.adding_box.append(self.new_phone)
        # Text("Add this number", color = OffWhite): OffWhite, disabled or not.
        self.add_button = outlined_button(book.ADD, self.add_a_contact)
        self.add_button.set_halign(Gtk.Align.START)
        restyle(self.add_button.get_child(), f"color: {theme.OFF_WHITE}; filter: none;")
        self.add_button.set_sensitive(False)
        self.adding_box.append(self.add_button)
        card.append(self.adding_box)
        self.show_typing()
        card.append(text("Test the alarm", "title-small"))
        card.append(text("Sends a test on every route an SOS would take, and shows what got through. It says it is a test, and raises nothing at the Hub.", "body-small", theme.TEXT_MUTED, wrap=True))
        # SosScreens.kt:600-602: its words in OffWhite, in TextMuted while it cannot test.
        self.test_button = outlined_button("Test the alarm", self.test_asked)
        self.test_button.set_halign(Gtk.Align.START)
        card.append(self.test_button)
        self.no_way = text("A test needs somewhere to go first.", "body-small", theme.TEXT_MUTED, wrap=True)
        card.append(self.no_way)

        timer = self.card("Check-in timer (dead man's switch)")
        self.enabled = SwitchRow("Enabled", self.set_enabled)
        timer.append(self.enabled)
        self.timeout_title = text("Timeout (triggers SOS if no activity)", "body-small", theme.TEXT_MUTED)
        timer.append(self.timeout_title)
        # SettingsScreen.kt:1015-1045: each timeout a row of the card's Column (8 dp apart), the
        # chosen one on Signal Orange at 15 % (theme.py's .timeout-row.selected) with "selected" in
        # Signal Orange.
        self.timeout_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        self.timeouts = {}
        for value, label in TIMEOUTS:
            row = Gtk.Button()
            row.add_css_class("flat")
            row.add_css_class("timeout-row")
            row.update_property([Gtk.AccessibleProperty.LABEL], [label])
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(8))
            inner.append(text(label, "body-small"))
            mark = text("selected", "body-small", theme.SIGNAL_ORANGE, xalign=1.0)
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
    def show_typing(self) -> None:
        self.type_button.set_visible(not self.typing)
        for widget in (self.new_name, self.new_phone, self.add_button):
            widget.set_visible(self.typing)

    def show_error(self, why) -> None:
        """Above "Or type a number" while not typing, under the number field while typing."""
        if self.typing:
            self.pick_error.set_visible(False)
            self.new_phone.set_error(why)
        else:
            self.new_phone.set_error(None)
            self.pick_error.set_text(why or "")
            self.pick_error.set_visible(bool(why))

    def start_typing(self) -> None:
        self.typing = True
        self.show_typing()
        self.show_error(None)

    def name_typed(self, value: str) -> None:
        kept = book.typed_name(value)
        if kept != value:
            self.new_name.set_text(kept)

    def number_typed(self, value: str) -> None:
        if len(value) > book.NUMBER_MAX:
            self.new_phone.set_text(value[:book.NUMBER_MAX])
            return
        self.add_button.set_sensitive(bool(value.strip()))
        self.new_phone.set_error(None)

    def add_a_contact(self) -> None:
        new, why = book.adding(self.app.state.contacts, self.new_name.text, self.new_phone.text)
        if why:
            self.show_error(why)
            return
        self.app.set_contacts(new)
        self.new_name.set_text("")
        self.new_phone.set_text("")
        self.typing = False
        self.show_typing()
        self.show_error(None)
        self.update(self.app.state)

    def choose_contact(self) -> None:
        """The phone's address book, read off the main loop; no address book: typing, with
        Android's words."""
        self.show_error(None)

        def work() -> None:
            try:
                found = addressbook.rows()
            except Exception:  # noqa: BLE001 - an address book that fails to answer is none
                found = None
            GLib.idle_add(lambda: self.got_contacts(found) or False)

        threading.Thread(target=work, daemon=True).start()

    def got_contacts(self, found) -> None:
        if found is None:
            self.typing = True
            self.show_typing()
            self.show_error(book.NO_APP)
            return
        ContactPicker(self.app, found, self.picked).present()

    def picked(self, name: str, number: str) -> None:
        if not (number or "").strip() and not (name or "").strip():
            self.typing = True
            self.show_typing()
            self.show_error(book.UNREADABLE)
            return
        new, why = book.adding(self.app.state.contacts, name, number)
        if why:
            self.show_error(why)
            return
        self.show_error(None)
        self.app.set_contacts(new)
        self.update(self.app.state)

    def remove_contact(self, phone: str) -> None:
        self.app.set_contacts([c for c in self.app.state.contacts if c.get("phone") != phone])
        self.update(self.app.state)

    # The test: TestAlarmDialog, the same dialog as Home's (the routes of the reach rule)
    def test_asked(self) -> None:
        ask_test(self.app, self.test_fire)

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
        # SosReach, as Home's SOS card reads it (model/home.reach): every route set up, a modem this
        # phone has had included, not only the routes up this minute.
        seen = self.app.prefs.get(words_of_home.MODEM_SEEN, "")
        anywhere = words_of_home.reach(s, seen)["anywhere"]
        self.reach.set_text(words_of_home.reach_sentence(s, seen))
        # The name an SOS carries when this one is left empty: the Hub callsign (SosScreens.kt:502).
        placeholder = sos.name_placeholder(s.hub_callsign())
        if self.name.entry.get_placeholder_text() != placeholder:
            self.name.entry.set_placeholder_text(placeholder)
        can_sms = bool((s.cellular or {}).get("connected")) and bool(s.bridge)
        reason = s.sms_reason()
        for w in (self.contacts_title, self.contacts_note, self.contact_rows):
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
                    texts.append(text(c["phone"], "body-small", theme.TEXT_SECONDARY))
                row.append(texts)
                row.append(icon_button("outlined-close", lambda phone=c["phone"]: self.remove_contact(phone), 20, theme.TEXT_SECONDARY, book.remove_name(c)))
                self.contact_rows.append(row)
        self.adding_box.set_visible(can_sms and len(s.contacts) < book.MAX)
        run = self.app.sos.active()
        can_test = anywhere and run is None  # reach.anywhere && run?.active != true
        self.test_button.set_sensitive(can_test)
        restyle(self.test_button.get_child(), f"color: {theme.OFF_WHITE if can_test else theme.TEXT_MUTED}; filter: none;")
        self.no_way.set_visible(not anywhere)
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


class ContactPicker(Sheet):
    """The address book's phone numbers, one row per number, with a search: Android opens the
    phone's own picker here; this is that picker, and nothing of what it shows is kept."""

    def __init__(self, app, found: list, on_pick):
        super().__init__(app, book.CHOOSE, width=360)
        self.on_pick = on_pick
        self.search = Gtk.SearchEntry()
        name_widget(self.search, "Search")
        self.search.connect("search-changed", lambda *_: self.fill())
        self.body.append(self.search)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=theme.dp(420), hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.rows)
        self.body.append(scroll)
        self.found = found
        self.button("Cancel", self.close)
        self.fill()

    def fill(self) -> None:
        clear(self.rows)
        needle = self.search.get_text().strip().casefold()
        for name, number in self.found:
            if needle and needle not in name.casefold() and needle not in number:
                continue
            row = Gtk.Button()
            row.add_css_class("flat")
            row.add_css_class("pick-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(2))
            inner.append(text(name or number, "body-large", ellipsize=True))
            if name:
                inner.append(text(number, "body-medium", theme.TEXT_SECONDARY, mono=True))
            row.set_child(inner)
            row.connect("clicked", lambda _b, n=name, p=number: (self.close(), self.on_pick(n, p)))
            self.rows.append(row)
