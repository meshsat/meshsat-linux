# SPDX-License-Identifier: GPL-3.0-or-later
"""The end-to-end test driver: the app as a process under test, its widget tree over AT-SPI,
the scripted or live Bridge, and the report. Runs on the phone (or any Linux with GTK 4 and a
Wayland compositor), never on a machine without them."""


class HarnessError(Exception):
    """The harness itself could not do its part (no compositor, no a11y bus, a timeout on the
    bus): the case is not a verdict on the app."""


class BridgeError(Exception):
    """The Bridge did not do its part."""


class BenchError(Exception):
    """The bench did not do its part (a radio that did not hear, a T-Deck that is off)."""
