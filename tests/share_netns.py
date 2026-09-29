# SPDX-License-Identifier: GPL-3.0-or-later
"""meshsat-share's rules as the kernel applies them, for tests/test_share_package.py. Runs as
root of a user namespace, in a network namespace of its own that stands for the phone:

  unshare --user --map-root-user --net python3 tests/share_netns.py WORK SCRIPT

A second network namespace behind two veth pairs is the network: eth0 is the Wi-Fi (private
and public addresses, IPv4 and IPv6), eth1 the mobile data connection (wwan0 on the phone's
side). The Bridge (6050, and 7050 for a port set in bridge.env), the node's API (4403) and its
web client (9443) are echo servers; each probe is a connection from the network, or from the
phone itself. SCRIPT is meshsat-share with its flag, bridge.env and lock in WORK; WORK/bin has
a logger that writes to WORK/log. Prints what happened, as JSON. Nothing outside the two
namespaces is touched: they end with this process."""
import json
import os
import socket
import subprocess
import sys
import threading
import time

work, script = sys.argv[1], sys.argv[2]
flag = os.path.join(work, "share-on-network")
PATH = os.path.join(work, "bin") + ":/usr/sbin:/sbin:/usr/bin:/bin"
NO_NFT = os.path.join(work, "bin") + ":/usr/bin:/bin"


def sh(*args):
    subprocess.run(list(args), check=True, capture_output=True, env=dict(os.environ, PATH=PATH))


def share(verb, path=PATH):
    run = subprocess.run(["sh", script, verb], capture_output=True, text=True, env=dict(os.environ, PATH=path))
    return {"code": run.returncode, "err": run.stderr.strip()}


def echo(listener):
    while True:
        conn, _ = listener.accept()

        def serve(c=conn):
            with c:
                while True:
                    data = c.recv(64)
                    if not data:
                        return
                    c.sendall(data)

        threading.Thread(target=serve, daemon=True).start()


# A connection per probe, from its source address: open (the echo came back), reset, timeout.
CLIENT = """
import json, socket, sys
out = []
for dst, port, src in json.loads(sys.argv[1]):
    s = socket.socket(socket.AF_INET6 if ":" in dst else socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.bind((src, 0))
        s.connect((dst, port))
        s.sendall(b"x")
        out.append("open" if s.recv(1) == b"x" else "closed")
    except ConnectionRefusedError:
        out.append("reset")
    except socket.timeout:
        out.append("timeout")
    except OSError as error:
        out.append(type(error).__name__)
    finally:
        s.close()
print(json.dumps(out))
"""

# A browser that has the shared Bridge open while it is switched off: the next packet it sends.
HOLD = """
import os, socket, sys, time
ready, go = sys.argv[1], sys.argv[2]
s = socket.create_connection(("192.168.77.1", 6050), timeout=3, source_address=("192.168.77.2", 0))
s.sendall(b"a")
first = s.recv(1)
open(ready, "w").close()
deadline = time.time() + 15
while not os.path.exists(go) and time.time() < deadline:
    time.sleep(0.05)
try:
    s.sendall(b"b")
    second = s.recv(1)
    print("open" if first == b"a" and second == b"b" else "closed")
except ConnectionResetError:
    print("reset" if first == b"a" else "never open")
except socket.timeout:
    print("timeout")
except OSError as error:
    print(type(error).__name__)
"""

PROBES = {"wifi 6050": ("192.168.77.1", 6050, "192.168.77.2"), "wifi 4403": ("192.168.77.1", 4403, "192.168.77.2"),
          "wifi 9443": ("192.168.77.1", 9443, "192.168.77.2"), "wifi 7050": ("192.168.77.1", 7050, "192.168.77.2"),
          "public 6050": ("198.51.100.1", 6050, "198.51.100.2"), "ula 6050": ("fd77::1", 6050, "fd77::2"),
          "ula 4403": ("fd77::1", 4403, "fd77::2"), "global6 6050": ("2001:db8:77::1", 6050, "2001:db8:77::2"),
          "mobile 6050": ("10.64.0.1", 6050, "10.64.0.2")}
MINE = {"lo 6050": ("127.0.0.1", 6050, "127.0.0.1"), "lo6 6050": ("::1", 6050, "::1"), "own address 6050": ("192.168.77.1", 6050, "192.168.77.1"),
        "lo 4403": ("127.0.0.1", 4403, "127.0.0.1"), "lo 9443": ("127.0.0.1", 9443, "127.0.0.1")}

# The other machine on the network: a namespace of its own whose one process runs what it is
# told, one JSON line in, one out, so nothing has to enter the namespace from outside.
AGENT = r"""
import json, subprocess, sys
held = {}
for line in sys.stdin:
    req = json.loads(line)
    if req["op"] == "run":
        r = subprocess.run(req["argv"], capture_output=True, text=True, timeout=120)
        out = {"rc": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    elif req["op"] == "spawn":
        held[req["id"]] = subprocess.Popen(req["argv"], stdout=subprocess.PIPE, text=True)
        out = {"rc": 0}
    else:
        stdout, _ = held.pop(req["id"]).communicate(timeout=60)
        out = {"rc": 0, "stdout": stdout}
    print(json.dumps(out), flush=True)
"""
peer = subprocess.Popen(["unshare", "--net", "python3", "-u", "-c", AGENT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=dict(os.environ, PATH=PATH))


def there(op: str, argv=None, ident: str = "") -> dict:
    peer.stdin.write(json.dumps({"op": op, "argv": argv, "id": ident}) + "\n")
    peer.stdin.flush()
    return json.loads(peer.stdout.readline())


def sh_there(*args) -> None:
    answer = there("run", list(args))
    if answer["rc"] != 0:
        raise RuntimeError(f"{args}: {answer['stderr']}")


try:
    mine = os.readlink("/proc/self/ns/net")
    deadline = time.time() + 5
    while os.readlink(f"/proc/{peer.pid}/ns/net") == mine and time.time() < deadline:
        time.sleep(0.02)
    sh("ip", "link", "set", "lo", "up")
    sh("ip", "link", "add", "wlan0", "type", "veth", "peer", "name", "eth0", "netns", str(peer.pid))
    sh("ip", "link", "add", "wwan0", "type", "veth", "peer", "name", "eth1", "netns", str(peer.pid))
    for dev, address in (("wlan0", "192.168.77.1/24"), ("wlan0", "198.51.100.1/24"), ("wlan0", "fd77::1/64"), ("wlan0", "2001:db8:77::1/64"), ("wwan0", "10.64.0.1/24")):
        sh("ip", "addr", "add", address, "dev", dev, *(["nodad"] if ":" in address else []))
    for dev, address in (("eth0", "192.168.77.2/24"), ("eth0", "198.51.100.2/24"), ("eth0", "fd77::2/64"), ("eth0", "2001:db8:77::2/64"), ("eth1", "10.64.0.2/24")):
        sh_there("ip", "addr", "add", address, "dev", dev, *(["nodad"] if ":" in address else []))
    for dev in ("wlan0", "wwan0"):
        sh("ip", "link", "set", dev, "up")
    for dev in ("lo", "eth0", "eth1"):
        sh_there("ip", "link", "set", dev, "up")
    for port in (6050, 4403, 9443, 7050):
        listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("::", port))
        listener.listen(16)
        threading.Thread(target=echo, args=(listener,), daemon=True).start()

    def probe(probes, inside=False):
        names = list(probes)
        command = ["python3", "-c", CLIENT, json.dumps([probes[n] for n in names])]
        stdout = subprocess.run(command, capture_output=True, text=True, timeout=60).stdout if inside else there("run", command)["stdout"]
        return dict(zip(names, json.loads(stdout), strict=True))

    def table():
        return subprocess.run(["nft", "list", "table", "inet", "meshsat"], capture_output=True, text=True, env=dict(os.environ, PATH=PATH)).stdout

    out = {"before": probe(PROBES)}
    out["apply"] = share("apply")
    out["local"], out["local mine"], out["local table"] = probe(PROBES), probe(MINE, inside=True), table()
    out["on"] = share("on")
    out["shared flag"] = os.path.exists(flag)
    out["shared"], out["shared mine"], out["shared table"] = probe(PROBES), probe(MINE, inside=True), table()
    ready, go = os.path.join(work, "ready"), os.path.join(work, "go")
    there("spawn", ["python3", "-c", HOLD, ready, go], "held")
    deadline = time.time() + 10
    while not os.path.exists(ready) and time.time() < deadline:
        time.sleep(0.05)
    out["off"] = share("off")
    open(go, "w").close()
    out["held across off"] = there("wait", None, "held")["stdout"].strip()
    out["off flag"] = os.path.exists(flag)
    out["after off"] = probe(PROBES)
    with open(os.path.join(work, "bridge.env"), "w", encoding="utf-8") as handle:
        handle.write('MESHSAT_MODE=direct\nMESHSAT_PORT="7050"\n')
    out["apply 7050"] = share("apply")
    out["port 7050"] = probe(PROBES)
    os.remove(os.path.join(work, "bridge.env"))
    out["on without nft"] = share("on", NO_NFT)
    out["on without nft flag"] = os.path.exists(flag)
    open(flag, "w").close()
    out["off without nft"] = share("off", NO_NFT)
    out["off without nft flag"] = os.path.exists(flag)
    out["table at the end"] = table()
    with open(os.path.join(work, "log"), encoding="utf-8") as handle:
        out["log"] = handle.read()
    print(json.dumps(out))
finally:
    peer.kill()
    peer.wait()
