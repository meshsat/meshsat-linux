# SPDX-License-Identifier: GPL-3.0-or-later
"""About (ui/screens/AboutScreen.kt:31-133) in Android's order and words, with the rows that name
Android's own machinery replaced by this edition's: the node over the LoRa back cover or over
Bluetooth, the RockBLOCK on USB-C, the phone's SIM through ModemManager, and the Bridge and the
toolkit in place of Android's two SDK rows (Linux words by design)."""

TITLE = "MeshSat Linux"
SUBTITLE = "Mobile gateway for Meshtastic mesh + Iridium satellite + SMS"
LICENSE = "GNU General Public License v3.0"
PROJECT = "Part of the MeshSat project: meshsat.net"


def version_line(version: str, build: str | None) -> str:
    """Android: v${VERSION_NAME} (${VERSION_CODE}); the build stamp stands in for the code."""
    return f"v{version} ({build or 'source'})"


def sections(mode: str, provenance: dict, node_pipe: bool = False) -> list:
    """[(title, [(label, value)])] in Android's order."""
    mesh = "BLE (Bluetooth Low Energy)" if mode == "bluetooth" else "The LoRa back cover over I2C"
    sbd = "The MeshSat node's BLE pipe" if mode == "bluetooth" and node_pipe else "RockBLOCK on USB-C"
    return [
        ("Transports", [("Meshtastic", mesh), ("Iridium 9603N", sbd), ("RockBLOCK 9704", "USB serial (JSPR)"),
                        ("Cellular SMS", "The phone's SIM, through ModemManager")]),
        ("Encryption", [("Algorithm", "AES-256-GCM"), ("Wire format", "[12B nonce][ciphertext+tag]"), ("SMS format", "Base64-encoded wire format"),
                        ("Compatible with", "MeshSat Pi transform pipeline")]),
        ("Build", [("Package", "net.meshsat.Bridge"), ("Edition", "Debian package"), ("Build type", "release"),
                   ("Bridge", provenance.get("bridge") or "-"), ("Toolkit", "GTK 4, libadwaita")]),
    ]
