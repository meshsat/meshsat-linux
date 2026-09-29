# SPDX-License-Identifier: GPL-3.0-or-later
"""The welcome (ui/screens/Onboarding.kt:64-126): shown once, before the app asks for anything.
Android's headline, body, section title and button are kept word for word; the reasons name what
MeshSat for Linux uses (Android's name permissions that are Android's own), and the footer the
phone's settings instead of Android's."""

LOCKUP_NAME = "MeshSat"
HEADLINE = "Keeping people connected when the network is not."
BODY = ("This phone becomes a gateway. With a MeshSat node it sends and receives over the mesh radio and by "
        "satellite, and by SMS while there is a mobile signal.")
ASKS = "What the app asks for, and why"
# (icon, title, why). Android: "Nearby devices" (its Bluetooth permission's name); its Location
# sentence goes on with "Android also asks for it before an app may look for Bluetooth radios.";
# "SMS, later" is left out: Linux asks for nothing to send an SMS.
REASONS = (("outlined-bluetooth", "Bluetooth", "To find your MeshSat node and talk to it over Bluetooth."),
           ("outlined-location-on", "Location", "Your position for an SOS and the map."),
           ("outlined-notifications", "Notifications", "Incoming messages, the satellite signal in the status bar, and an SOS in progress."))
CONTINUE = "Continue"
FOOTER = "You can change any of these later in the phone's settings for MeshSat."
