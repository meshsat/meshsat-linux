# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup > Advanced > Diagnostics, "Share the Bridge on this network": this edition's own row,
with no Android counterpart. The Bridge answers every client without a password (standalone
mode), so the package lets only this device reach it (meshsat-share, one nftables table); the
switch opens the Bridge's port to the network the phone is on, after a question, through
pkexec. Here: the words, the line under the switch, and the port and the addresses to open,
found the way meshsat-share finds them."""
import ipaddress
import re

TITLE = "Share the Bridge on this network"
LOCAL = "Only this phone can open the Bridge."
NO_NETWORK = "Shared, but this phone is on no network right now."
QUESTION = "Share the Bridge on this network?"
QUESTION_BODY = ("Anyone on this network can then open the Bridge without a password: read and send messages, start an SOS, "
                 "change every setting and spend satellite credit. Share it only on a network you trust, and switch it off when you are done.")
SHARE = "Share"
NOT_NOW = "Not now"
# The switch did not take (the password was not given, or the rules could not be loaded): what
# is true now.
NOT_SHARED = "The Bridge was not shared."
STILL_SHARED = "The Bridge is still shared."

DEFAULT_PORT = 6050
# Shared, the Bridge still answers a reset on the mobile data connection's interfaces and to
# any address outside these ranges (meshsat-share's CELLULAR and PRIVATE4), so an address on
# them is never one to open.
CELLULAR = ("wwan", "wwp", "rmnet", "ccmni", "mhi", "ppp")
PRIVATE4 = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
_PRIVATE = tuple(ipaddress.ip_network(n) for n in PRIVATE4)


def subtitle(shared: bool, addresses: list, port: int) -> str:
    """The line under the switch."""
    if not shared:
        return LOCAL
    if not addresses:
        return NO_NETWORK
    return "Open " + " or ".join(f"http://{a}:{port}" for a in addresses) + " in a browser on the same network."


def not_changed(wanted_on: bool) -> str:
    """The toast when switching on or off did not happen."""
    return NOT_SHARED if wanted_on else STILL_SHARED


def bridge_port(env_text: str) -> int:
    """MESHSAT_PORT of /etc/meshsat/bridge.env as the Bridge gets it (systemd's EnvironmentFile:
    the last assignment wins, quotes come off; strconv.Atoi takes a sign and leading zeros);
    6050 when it is absent or not a port, as the Bridge falls back. meshsat-share reads it the
    same way, so the port shown is the port it opens."""
    value = None
    for line in env_text.splitlines():
        key, sep, rest = line.strip().partition("=")
        if sep and key.rstrip() == "MESHSAT_PORT":
            value = rest.strip()
    if value is None:
        return DEFAULT_PORT
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    value = value.removeprefix("+")
    value = value.lstrip("0") or ("0" if value else "")
    if not re.fullmatch(r"[0-9]{1,5}", value):
        return DEFAULT_PORT
    port = int(value)
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def lan_addresses(ip_output: str, virtual=()) -> list:
    """The addresses a browser on this phone's network opens the Bridge at, from the lines of
    `ip -4 -o addr show scope global`: private ones, on an interface that is neither the mobile
    data connection nor one of `virtual` (the kernel's own: bridges, containers, tunnels)."""
    out = []
    for line in ip_output.splitlines():
        fields = line.split()
        if len(fields) < 4 or "inet" not in fields[2:-1]:
            continue
        iface = fields[1].split("@")[0]
        if iface.startswith(CELLULAR) or iface in virtual:
            continue
        address = fields[fields.index("inet", 2) + 1].split("/")[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.version == 4 and any(ip in net for net in _PRIVATE) and address not in out:
            out.append(address)
    return out
