# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh radio settings (ui/screens/RadioConfigScreen.kt): seven tabs, Name, Radio, Channels,
Position, Bluetooth, WiFi, Restart and reset, over the node's settings as the Bridge keeps
them (GET /api/config?format=names). Every Apply sends only what was changed, and the Bridge
lays it over the node's own settings (MESHSAT-1405). A tab is drawn again only when the
settings under it change, so a poll never throws away what is being typed (Android's
remember(loaded)). With the LoRa back cover the node runs on this phone: its transmit power is
capped at 0 dBm by its service, and it has no WiFi or Bluetooth of its own."""
import json

from gi.repository import Gtk

from .. import api, theme
from ..model import radio as model
from ..screen import SubScreen
from ..widgets import (Card, Field, PickerDialog, Sheet, StatusBanner, SwitchRow, Tabs, clear, confirm, divider, fact_row, filled_button, hscroll, icon,
                       icon_button, name_widget, outlined_button, text, text_button)

READ_BACK_MS = 2500  # Android reads the settings back 2.5 s after applying


def config_card(title: str) -> Card:
    """Android's ConfigCard: the title in titleSmall, the content under it."""
    card = Card(spacing=4)
    card.append(text(title, "title-small"))
    return card


def hint(value: str) -> Gtk.Label:
    return text(value, "body-small", theme.TEXT_MUTED, wrap=True)


def full(button: Gtk.Button) -> Gtk.Button:
    button.set_hexpand(True)
    button.set_margin_top(theme.dp(4))
    return button


def bound_field(label: str, value: str, on_change, limit: int = 0, purpose=None) -> Field:
    """A text field showing `value`, then telling `on_change` about what is typed (Field's
    constructor reports its first, empty text, which must not reach a draft)."""
    field = Field(label, purpose=purpose)
    if limit:
        field.entry.set_max_length(limit)
    field.set_text(value)
    field.on_change = on_change
    return field


def number_field(label: str, limit: int, value: str, on_change, helper: str = "") -> Field:
    """A number field as Android's: digits only, at most `limit` of them."""
    field = Field(label, helper=helper, purpose=Gtk.InputPurpose.DIGITS)
    field.entry.set_max_length(limit)
    field.set_text(value)

    def changed(typed: str) -> None:
        kept = model.digits(typed, limit)
        if kept != typed:
            field.set_text(kept)
            return
        on_change(kept)

    field.on_change = changed
    return field


class RadioConfigScreen(SubScreen):
    def __init__(self, app):
        super().__init__(app, "Mesh radio settings", spacing=12)
        self.route = "radio-config"
        self.named = None  # GET /api/config?format=names; None until the first answer
        self.tab = model.TABS[0]
        self._drawn = None  # what the tab on view was drawn from
        self.offline = Card(spacing=8)
        self.offline.append(text(model.NOT_CONNECTED, "body-medium", theme.TEXT_SECONDARY, wrap=True))
        connect = filled_button(model.CONNECT, lambda: self.app.open_route("setup/node"), expand=False)
        connect.set_halign(Gtk.Align.START)
        self.offline.append(connect)
        self.column.append(self.offline)
        self.tabs = Tabs(list(model.TABS), self.select_tab, plain=True)
        self.column.append(hscroll(self.tabs))
        self.column.append(divider())
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(12))
        self.column.append(self.content)
        self.update(app.state)

    # Data
    def on_show(self) -> None:
        self.every(10, self.load)

    def load(self) -> None:
        self.fetch("/api/config?format=names", self.loaded)

    def loaded(self, answer: api.Answer) -> None:
        if answer.ok and isinstance(answer.body, dict):
            self.named = answer.body
        elif answer.status >= 400:
            self.named = {}
        self.render()

    def read_back(self, section: str | None) -> None:
        """What the radio holds after a change (it may also correct a value), not what was
        typed: the node is asked for the section, and the page reads it again."""
        def ask() -> None:
            if section:
                self.fetch(f"/api/config/{section}", lambda _a: self.after(1500, self.load))
            else:
                self.load()

        self.after(READ_BACK_MS, ask)

    # State
    @property
    def connected(self) -> bool:
        return self.app.state.mesh_connected()

    @property
    def can_send(self) -> bool:
        """Admin messages go to the node's own number; without it nothing can be sent."""
        return self.connected and bool((self.named or {}).get("node_num"))

    @property
    def cover(self) -> bool:
        return self.app.state.node_mode() == "cover"

    def section(self, name: str):
        return ((self.named or {}).get("config") or {}).get(name)

    def update(self, s: api.State) -> None:
        self.offline.set_visible(not s.mesh_connected())
        self.render()

    # Drawing
    def select_tab(self, name: str) -> None:
        self.tab = name
        self._drawn = None
        self.render()

    def render(self) -> None:
        named = self.named or {}
        basis = {"Name": ("node_id", "owner", "metadata"), "Radio": ("lora",), "Channels": ("channels",), "Position": ("position",), "Bluetooth": ("bluetooth", "metadata"),
                 "WiFi": ("network", "metadata"), "Restart and reset": ("metadata", "node_num")}[self.tab]
        data = {k: named.get(k, self.section(k)) for k in basis}
        key = json.dumps([self.tab, data, self.connected, self.can_send, self.named is None, self.cover], sort_keys=True, default=str)
        if key == self._drawn:
            return
        self._drawn = key
        clear(self.content)
        getattr(self, "draw_" + self.tab.split()[0].lower())()

    def not_loaded(self) -> None:
        self.content.append(text(model.READING if self.connected else model.CONNECT_TO_READ, "body-medium", theme.TEXT_SECONDARY, wrap=True))

    def send(self, path: str, body: dict | None, sent: str, section: str | None = None, back: bool = True) -> None:
        def done(answer: api.Answer) -> None:
            if answer.ok:
                self.app.toast(sent)
                if back and self.alive:
                    self.read_back(section)
            else:
                self.app.toast(model.refused(answer.status, answer.error or ""))

        self.call(path, done, body=body)

    def apply_button(self, on_click, enabled: bool) -> Gtk.Button:
        button = full(filled_button("Apply", on_click))
        button.set_sensitive(enabled)
        return button

    # Name
    def draw_name(self) -> None:
        named = self.named or {}
        facts = config_card("This node")
        own = self.app.state.own_node() or {}
        for label, value, mono in model.node_facts(named, own.get("hw_model_name", "")):
            facts.append(fact_row(label, value, theme.TEXT_SECONDARY, mono=mono))
        self.content.append(facts)
        card = config_card("Name")
        card.append(hint(model.NAME_HINT))
        self.content.append(card)
        owner = named.get("owner") or {}
        if not owner.get("long_name"):
            card.append(text(model.READING if self.connected else model.CONNECT_TO_READ, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            return
        save = full(filled_button("Save name", None))
        long_name = bound_field("Long name", owner.get("long_name", ""), None, model.LONG_MAX)
        short_name = bound_field("Short name", owner.get("short_name", ""), None, model.SHORT_MAX)

        def check(*_) -> None:
            save.set_sensitive(self.can_send and model.can_save_name(long_name.text, short_name.text, owner))

        long_name.on_change = short_name.on_change = check
        for field in (long_name, short_name):
            field.entry.set_sensitive(self.can_send)
        save.connect("clicked", lambda *_: self.send("/api/config/owner", model.owner_body(long_name.text, short_name.text), model.RESTARTS, "device"))
        for widget in (long_name, short_name, save):
            card.append(widget)
        check()

    # Radio
    def draw_radio(self) -> None:
        lora = self.section("lora")
        if not lora:
            self.not_loaded()
            return
        draft = {"region": int(lora.get("region", 0)), "preset": int(lora.get("modem_preset", 0)), "picked": False, "details": False,
                 "power": str(lora.get("tx_power", 0)), "hops": str(lora.get("hop_limit", 0)), "transmit": bool(lora.get("tx_enabled"))}
        country = model.phone_country()

        region_card = config_card("Region")
        region_card.append(hint(model.REGION_HINT))
        region_button = full(outlined_button(model.region_label(draft["region"])))
        region_card.append(region_button)
        warning = StatusBanner()
        warning.set_margin_top(theme.dp(8))
        region_card.append(warning)
        self.content.append(region_card)

        preset_card = config_card("Preset")
        preset_card.append(hint(model.PRESET_HINT))
        preset_button = full(outlined_button(""))
        preset_card.append(preset_button)
        details_button = text_button("Details")
        details_button.set_halign(Gtk.Align.START)
        preset_card.append(details_button)
        details = hint("")
        preset_card.append(details)
        self.content.append(preset_card)

        power_card = config_card("Transmit power")
        if not self.cover:
            power_card.append(hint(model.POWER_HINT))  # "0 means the highest power allowed": not so on the cover
        self.content.append(power_card)
        hops_card = config_card("Hops")
        hops_card.append(hint(model.HOPS_HINT))
        self.content.append(hops_card)
        transmit_card = config_card("Transmit")
        self.content.append(transmit_card)
        apply = self.apply_button(None, False)
        self.content.append(apply)

        def refresh(*_) -> None:
            region_button.set_label(model.region_label(draft["region"]))
            warning.show(model.region_warning(draft["region"], country), "amber")
            preset_button.set_label(model.preset_button(lora, draft["preset"], draft["picked"]))
            details_button.set_label("Hide details" if draft["details"] else "Details")
            details.set_text(model.preset_details(lora, draft["preset"], draft["picked"]))
            details.set_visible(draft["details"])
            changes = model.radio_changes(lora, draft["region"], draft["preset"], draft["picked"], draft["power"], draft["hops"], draft["transmit"])
            if self.cover:
                changes.pop("tx_power", None)
            power_bad = not self.cover and not model.power_ok(draft["power"], lora)
            hops_bad = not model.hops_ok(draft["hops"], lora)
            if power_field is not None:
                power_field.set_error(model.POWER_ERROR if power_bad else None)
            hops_field.set_error(model.HOPS_ERROR if hops_bad else None)
            apply.set_sensitive(self.can_send and bool(changes) and not power_bad and not hops_bad)
            return changes

        def pick_region() -> None:
            def picked(code) -> None:
                draft["region"] = code
                refresh()

            PickerDialog(self.app, "Region", model.region_options(), draft["region"], picked).present()

        def pick_preset() -> None:
            def picked(code) -> None:
                draft["preset"], draft["picked"] = code, True
                refresh()

            chosen = -1 if model.is_custom(lora, draft["picked"]) else draft["preset"]
            PickerDialog(self.app, "Preset", model.preset_options(), chosen, picked).present()

        def toggle_details() -> None:
            draft["details"] = not draft["details"]
            refresh()

        region_button.connect("clicked", lambda *_: pick_region())
        preset_button.connect("clicked", lambda *_: pick_preset())
        details_button.connect("clicked", lambda *_: toggle_details())
        for button in (region_button, preset_button):
            button.set_sensitive(self.can_send)

        power_field = None
        if self.cover:
            power_card.append(text(model.COVER_POWER, "body-large"))
            power_card.append(hint(model.COVER_POWER_HINT))
        else:
            power_field = number_field("dBm", 2, draft["power"], lambda v: (draft.__setitem__("power", v), refresh()))
            power_field.entry.set_sensitive(self.can_send)
            power_card.append(power_field)
        hops_field = number_field("Hops", 1, draft["hops"], lambda v: (draft.__setitem__("hops", v), refresh()))
        hops_field.entry.set_sensitive(self.can_send)
        hops_card.append(hops_field)
        transmit = SwitchRow("Transmit", lambda on: (draft.__setitem__("transmit", on), refresh()), detail=model.TRANSMIT_HINT, active=draft["transmit"])
        transmit.switch.set_sensitive(self.can_send)
        transmit_card.append(transmit)

        def apply_now(changes: dict) -> None:
            self.send("/api/config/radio", model.section_body("lora", changes), model.RADIO_SENT, "lora")

        def clicked(*_) -> None:
            changes = refresh()
            consequences = model.radio_consequences(lora, changes)
            if consequences:
                confirm(self.app, model.RADIO_CONFIRM, "\n\n".join(consequences), "Apply", lambda: apply_now(changes))
            else:
                apply_now(changes)

        apply.connect("clicked", clicked)
        refresh()

    # Channels
    def draw_channels(self) -> None:
        channels = (self.named or {}).get("channels") or []
        if not channels:
            self.not_loaded()
            return
        self.content.append(hint(model.CHANNELS_HINT))
        for channel in channels:
            role = int(channel.get("role", 0))
            card = config_card(f"Channel {channel.get('index', 0)}")
            card.append(text(model.channel_name(channel), "body-large"))
            card.append(text(model.channel_role_line(channel), "body-small", theme.TEXT_MUTED if role == 0 else theme.TEXT_SECONDARY, wrap=True))
            if role != 0:
                label, why = model.channel_key(channel)
                key = text(label, "body-medium", theme.TEXT_SECONDARY, wrap=True)
                key.set_margin_top(theme.dp(4))
                card.append(key)
                card.append(hint(why))
                mqtt = model.mqtt_line(channel)
                if mqtt:
                    line = text(mqtt, "body-small", theme.TEXT_SECONDARY)
                    line.set_margin_top(theme.dp(4))
                    card.append(line)
            edit = full(outlined_button("Edit", lambda c=channel: self.edit_channel(c)))
            edit.set_sensitive(self.can_send)
            card.append(edit)
            self.content.append(card)

    def edit_channel(self, channel: dict) -> None:
        index = int(channel.get("index", 0))
        sheet = Sheet(self.app, f"Channel {index}")
        draft = {"role": int(channel.get("role", 0))}
        name = bound_field("Channel name", channel.get("name", ""), None, model.CHANNEL_NAME_MAX)
        sheet.body.append(name)
        if index == 0:
            sheet.body.append(text(model.role_label(1), "body-medium"))
            sheet.body.append(hint(model.CHANNEL_ZERO))
        else:
            role_button = full(outlined_button(model.role_label(draft["role"])))
            role_hint = hint(model.role_hint(draft["role"]))

            def picked(code) -> None:
                draft["role"] = code
                role_button.set_label(model.role_label(code))
                role_hint.set_text(model.role_hint(code))

            role_button.connect("clicked", lambda *_: PickerDialog(self.app, "Channel role", model.role_options(channel), draft["role"], picked).present())
            sheet.body.append(role_button)
            sheet.body.append(role_hint)
        uplink = SwitchRow("Send to MQTT", None, detail=model.UPLINK_HINT, active=bool(channel.get("uplink_enabled")))
        downlink = SwitchRow("Receive from MQTT", None, detail=model.DOWNLINK_HINT, active=bool(channel.get("downlink_enabled")))
        sheet.body.append(uplink)
        sheet.body.append(downlink)

        def save_now(body: dict) -> None:
            self.send("/api/channels", body, model.SENT)

        def save() -> None:
            sheet.close()
            new_name = name.text.strip()
            role = int(channel.get("role", 0)) if index == 0 else draft["role"]
            body = model.channel_body(channel, new_name, role, uplink.active, downlink.active)
            if model.channel_needs_asking(channel, new_name, role):
                confirm(self.app, f"Change channel {index}?", model.CHANGE_CHANNEL_BODY, "Change", lambda: save_now(body))
            else:
                save_now(body)

        sheet.button("Cancel", sheet.close)
        sheet.button("Save", save, kind="filled").set_sensitive(self.can_send)
        sheet.present()

    # Position
    def draw_position(self) -> None:
        position = self.section("position")
        if not position:
            self.not_loaded()
            return
        draft = {"gps": bool(position.get("gps_enabled")), "fixed": bool(position.get("fixed_position")), "secs": str(position.get("position_broadcast_secs", 0)),
                 "smart": bool(position.get("position_broadcast_smart_enabled"))}
        gps_card = config_card("GPS")
        sharing = config_card("Sharing")
        sharing.append(hint(model.SHARING_HINT))
        apply = self.apply_button(None, False)

        def refresh(*_) -> dict:
            changes = model.position_changes(position, draft["gps"], draft["fixed"], draft["secs"], draft["smart"])
            bad = not draft["secs"]
            seconds.set_error(model.SECONDS_ERROR if bad else None)
            apply.set_sensitive(self.can_send and bool(changes) and not bad)
            return changes

        gps = SwitchRow("GPS on", lambda on: (draft.__setitem__("gps", on), refresh()), active=draft["gps"])
        fixed = SwitchRow("Fixed position", lambda on: (draft.__setitem__("fixed", on), refresh()), detail=model.FIXED_HINT, active=draft["fixed"])
        seconds = number_field("Every (seconds)", 5, draft["secs"], lambda v: (draft.__setitem__("secs", v), refresh()))
        smart = SwitchRow("Smart sharing", lambda on: (draft.__setitem__("smart", on), refresh()), detail=model.SMART_HINT, active=draft["smart"])
        for row in (gps, fixed, smart):
            row.switch.set_sensitive(self.can_send)
        seconds.entry.set_sensitive(self.can_send)
        gps_card.append(gps)
        gps_card.append(fixed)
        sharing.append(seconds)
        sharing.append(smart)
        apply.connect("clicked", lambda *_: self.send("/api/config/radio", model.section_body("position", refresh()), model.RESTARTS, "position"))
        for widget in (gps_card, sharing, apply, hint(model.APPLY_RESTARTS)):
            self.content.append(widget)
        refresh()

    # Bluetooth
    def draw_bluetooth(self) -> None:
        if self.cover:
            self.content.append(text(model.COVER_NO_BLUETOOTH, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            return
        bluetooth = self.section("bluetooth")
        if not bluetooth:
            self.not_loaded()
            return
        draft = {"enabled": bool(bluetooth.get("enabled")), "mode": int(bluetooth.get("mode", 0)), "pin": model.pin_text(bluetooth)}
        bt_card = config_card("Bluetooth")
        pairing = config_card("Pairing")
        mode_button = full(outlined_button(model.pairing_label(draft["mode"])))
        no_pin = hint(model.NO_PIN_HINT)
        pin = number_field("PIN", 6, draft["pin"], lambda v: (draft.__setitem__("pin", v), refresh()))
        pin.entry.set_visibility(False)
        pin.entry.set_input_purpose(Gtk.InputPurpose.PIN)
        apply = self.apply_button(None, False)

        def refresh(*_) -> dict:
            mode_button.set_label(model.pairing_label(draft["mode"]))
            no_pin.set_visible(draft["mode"] == 2)
            pin.set_visible(draft["mode"] == 1)
            ok = model.pin_ok(draft["mode"], draft["pin"])
            pin.set_error(None if ok else model.PIN_ERROR)
            changes = model.bluetooth_changes(bluetooth, draft["enabled"], draft["mode"], draft["pin"])
            apply.set_sensitive(self.can_send and bool(changes) and ok)
            return changes

        def picked(code) -> None:
            draft["mode"] = code
            refresh()

        enabled = SwitchRow("Bluetooth on", lambda on: (draft.__setitem__("enabled", on), refresh()), detail=model.BLUETOOTH_HINT, active=draft["enabled"])
        enabled.switch.set_sensitive(self.can_send)
        bt_card.append(enabled)
        mode_button.connect("clicked", lambda *_: PickerDialog(self.app, "Pairing", model.pairing_options(), draft["mode"], picked).present())
        mode_button.set_sensitive(self.can_send)
        for widget in (mode_button, no_pin, pin):
            pairing.append(widget)

        def apply_now() -> None:
            self.send("/api/config/radio", model.section_body("bluetooth", refresh()), model.RESTARTS, "bluetooth")

        def clicked(*_) -> None:
            if bluetooth.get("enabled") and not draft["enabled"]:
                confirm(self.app, model.BLUETOOTH_OFF, model.BLUETOOTH_OFF_BODY, "Turn off", apply_now, danger=True)
            else:
                apply_now()

        apply.connect("clicked", clicked)
        for widget in (bt_card, pairing, apply, hint(model.APPLY_RESTARTS)):
            self.content.append(widget)
        refresh()

    # WiFi
    def draw_wifi(self) -> None:
        if self.cover:
            self.content.append(text(model.COVER_NO_WIFI, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            return
        network = self.section("network")
        metadata = (self.named or {}).get("metadata")
        if not network:
            self.not_loaded()
            return
        if metadata and not metadata.get("has_wifi"):
            self.content.append(text(model.NO_WIFI, "body-medium", theme.TEXT_SECONDARY, wrap=True))
            return
        draft = {"enabled": bool(network.get("wifi_enabled")), "ssid": network.get("wifi_ssid") or "", "psk": network.get("wifi_psk") or ""}
        card = config_card("WiFi")
        fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=theme.dp(8))
        apply = self.apply_button(None, False)

        def refresh(*_) -> dict:
            fields.set_visible(draft["enabled"])
            changes = model.wifi_changes(network, draft["enabled"], draft["ssid"], draft["psk"])
            apply.set_sensitive(self.can_send and bool(changes))
            return changes

        enabled = SwitchRow("WiFi on", lambda on: (draft.__setitem__("enabled", on), refresh()), detail=model.WIFI_HINT, active=draft["enabled"])
        enabled.switch.set_sensitive(self.can_send)
        ssid = bound_field("Network name", draft["ssid"], lambda v: (draft.__setitem__("ssid", v), refresh()), model.SSID_MAX)
        password = bound_field("Password", draft["psk"], lambda v: (draft.__setitem__("psk", v), refresh()), model.PSK_MAX, Gtk.InputPurpose.PASSWORD)
        password.entry.set_visibility(False)
        eye = {"shown": False}

        def toggle_password() -> None:
            # Android's trailing icon: the eye while hidden, the crossed eye while shown.
            eye["shown"] = not eye["shown"]
            password.entry.set_visibility(eye["shown"])
            label = "Hide password" if eye["shown"] else "Show password"
            show.set_child(icon("filled-visibility-off" if eye["shown"] else "filled-visibility", 24, theme.TEXT_SECONDARY))
            show.set_tooltip_text(label)
            name_widget(show, label)

        show = icon_button("filled-visibility", toggle_password, colour=theme.TEXT_SECONDARY, tooltip="Show password")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=theme.dp(4))
        password.set_hexpand(True)
        row.append(password)
        show.set_valign(Gtk.Align.CENTER)
        row.append(show)
        for widget in (ssid, row):
            widget.set_sensitive(self.can_send)
            fields.append(widget)
        card.append(enabled)
        card.append(fields)
        apply.connect("clicked", lambda *_: self.send("/api/config/radio", model.section_body("network", refresh()), model.RESTARTS, "network"))
        for widget in (card, apply, hint(model.APPLY_RESTARTS)):
            self.content.append(widget)
        refresh()

    # Restart and reset
    def draw_restart(self) -> None:
        named = self.named or {}
        node = int(named.get("node_num") or 0)
        metadata = named.get("metadata") or {}
        can_shutdown = metadata.get("can_shutdown") is not False

        clock = config_card("Clock")
        clock.append(hint(model.CLOCK_HINT))
        clock.append(full(outlined_button("Set the clock", lambda: self.send("/api/admin/set_clock", {}, model.SENT, back=False))))

        restart = config_card("Restart")
        restart.append(hint(model.RESTART_HINT))
        delay = number_field("Delay (seconds)", 4, "5", lambda _v: None)
        restart.append(delay)

        def ask_restart() -> None:
            secs = model.restart_delay(delay.text)
            confirm(self.app, "Restart your node?", model.restart_body(secs, self.cover), "Restart",
                    lambda: self.send("/api/admin/reboot", {"node_id": node, "delay_secs": secs}, model.restart_sent(secs), back=False))

        restart.append(full(outlined_button("Restart the node", ask_restart)))

        switch_off = config_card("Switch off")
        switch_off.append(hint(model.SWITCH_OFF_HINT if can_shutdown else model.CANNOT_SWITCH_OFF))
        off_button = full(outlined_button("Switch off the node", lambda: confirm(
            self.app, model.SWITCH_OFF_TITLE, model.SWITCH_OFF_BODY, "Switch off",
            lambda: self.send("/api/admin/shutdown", {"delay_secs": 5}, model.SWITCH_OFF_SENT, back=False), danger=True)))
        off_button.set_sensitive(self.can_send and can_shutdown)
        switch_off.append(off_button)

        forget = config_card("Forget heard nodes")
        forget.append(hint(model.FORGET_HINT))
        forget.append(full(outlined_button("Forget heard nodes", lambda: confirm(
            self.app, model.FORGET_TITLE, model.FORGET_BODY, "Forget", lambda: self.send("/api/admin/nodedb_reset", {}, model.SENT, back=False)))))

        erase = config_card("Factory reset")
        erase.append(text(model.ERASE_HINT, "body-small", theme.RED, wrap=True))
        erase_button = full(filled_button("Factory reset", lambda: confirm(
            self.app, model.ERASE_TITLE, model.ERASE_BODY, "Erase",
            lambda: self.send("/api/admin/factory_reset", {"node_id": node}, model.ERASE_SENT, back=False), danger=True)))
        erase_button.add_css_class("red-fill")
        erase.append(erase_button)

        for card in (clock, restart, switch_off, forget, erase):
            self.content.append(card)
        for card in (clock, restart, forget, erase):
            for child in _buttons(card):
                child.set_sensitive(self.can_send)
        delay.entry.set_sensitive(self.can_send)


def _buttons(box: Gtk.Widget):
    child = box.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.Button):
            yield child
        child = child.get_next_sibling()
