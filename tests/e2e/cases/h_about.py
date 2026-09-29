# SPDX-License-Identifier: GPL-3.0-or-later
"""About (AboutScreen.kt): the title, the version in orange, Android's subtitle, then
Transports, Encryption, Build and License in Android's words and order; the rows that name
Android's own machinery name this edition's."""
SCENARIO = "mesh-only"

ROWS = ("Transports", "Meshtastic", "The LoRa back cover over I2C", "Iridium 9603N", "RockBLOCK on USB-C", "RockBLOCK 9704", "USB serial (JSPR)",
        "Cellular SMS", "The phone's SIM, through ModemManager", "Encryption", "Algorithm", "AES-256-GCM", "Wire format", "[12B nonce][ciphertext+tag]",
        "SMS format", "Base64-encoded wire format", "Compatible with", "MeshSat Pi transform pipeline", "Build", "Package", "net.meshsat.Bridge",
        "Edition", "Debian package", "Build type", "release", "Bridge", "Toolkit", "GTK 4, libadwaita", "License", "GNU General Public License v3.0",
        "Part of the MeshSat project: meshsat.net")


def case_the_sections_in_androids_words(ctx):
    ctx.app.open("about")
    ctx.tree.wait_text("MeshSat Linux", timeout=10)
    ctx.tree.wait_text("Mobile gateway for Meshtastic mesh + Iridium satellite + SMS")
    texts = ctx.tree.texts()
    assert any(t.startswith("v") and "(" in t for t in texts), "no version line"
    at = -1
    for words in ROWS:
        assert words in texts, f"missing: {words!r}"
        found = texts.index(words, at + 1) if words in texts[at + 1:] else texts.index(words)
        assert found > at, f"{words!r} is out of Android's order"
        at = found
    assert not ctx.tree.has_text("trademark"), "a sentence Android does not have"
    ctx.shot("about")
