#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The far end of a live test: a Meshtastic radio on a serial port (a T-Deck on the laptop),
driven with the meshtastic Python package. One process owns the port at a time.

  e2e-farend.py send --port /dev/ttyACM0 --text "e2e 4f2a"
  e2e-farend.py listen --port /dev/ttyACM0 --out heard.jsonl --seconds 120
  e2e-farend.py nodes --port /dev/ttyACM0

`listen` writes every text it hears as one JSON line ({"t", "from", "text"}) until the
seconds are up or the process is ended; the runner (tools/e2e-run.sh) starts it before a
live case and reads the file after."""
import argparse
import json
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("send", "listen", "nodes"))
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--text", default="")
    parser.add_argument("--out", default="heard.jsonl")
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    try:
        import meshtastic.serial_interface  # noqa: PLC0415
        from pubsub import pub  # noqa: PLC0415
    except ImportError as error:
        print(f"the meshtastic package is needed here: {error}", file=sys.stderr)
        return 2
    iface = meshtastic.serial_interface.SerialInterface(args.port)
    try:
        if args.command == "send":
            iface.sendText(args.text)
            time.sleep(2)
            print(f"sent {args.text!r} from {iface.myInfo.my_node_num:08x}")
            return 0
        if args.command == "nodes":
            for num, node in (iface.nodes or {}).items():
                user = node.get("user", {})
                print(num, user.get("longName", ""), user.get("shortName", ""), node.get("lastHeard", 0))
            return 0
        handle = open(args.out, "a", encoding="utf-8")

        def on_text(packet, interface=None):
            decoded = packet.get("decoded", {})
            record = {"t": time.time(), "from": packet.get("fromId") or f"!{packet.get('from', 0):08x}", "text": decoded.get("text", ""), "rx_snr": packet.get("rxSnr")}
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            print(json.dumps(record), flush=True)

        pub.subscribe(on_text, "meshtastic.receive.text")
        print(f"listening on {args.port} for {args.seconds} s", flush=True)
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            time.sleep(0.5)
        return 0
    finally:
        iface.close()


if __name__ == "__main__":
    sys.exit(main())
