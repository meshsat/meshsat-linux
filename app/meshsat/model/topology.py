# SPDX-License-Identifier: GPL-3.0-or-later
"""The mesh as it was actually heard (ui/screens/TopologyScreen.kt): a link is drawn only where a
node reported the other in a NeighborInfo packet (the Bridge's /api/neighbors), or where this
Bridge's own radio heard a node directly (0 hops, from /api/nodes). Nothing is inferred from
silence, and a node with no link is shown on its own. Pure: the graph, its words, and the
force layout the screen animates."""
import math

from . import words

FRESH_S = 15 * 60  # a node or a link heard within this window is recent; older ones are muted

EMPTY_CONNECTED = ("Your node is listening.", "Nodes appear here once they transmit on the mesh.")
EMPTY_DISCONNECTED = ("Your node is not connected.", "Connect your MeshSat node in Setup to see how the mesh is linked.")
HINT = "Pinch to zoom, drag to move."
NO_REPORTS = "Links appear when nodes share who they hear. This needs Neighbor Info turned on in the nodes' module settings."
NOT_CONNECTED = "Your node is not connected, so this is what it heard last."
LEGEND_NOTE = "A line is drawn only where a node said it hears the other, or where your node heard it directly. A node shows up once it transmits."
RESET = "Reset view"


def num_of(value) -> int:
    """A node's number from "!a1b3c2ec", "a1b3c2ec" or a number; 0 for anything else."""
    if isinstance(value, int):
        return value
    text = str(value or "").strip().lstrip("!")
    try:
        return int(text, 16)
    except ValueError:
        return 0


def node_id(num: int) -> str:
    return f"!{num & 0xFFFFFFFF:08x}"


def _hearing(hearer: int, heard: int, snr, at: float, fresh: bool, by_our_radio: bool) -> dict:
    return {"hearer": hearer, "heard": heard, "snr": float(snr or 0.0), "at": at, "fresh": fresh, "by_our_radio": by_our_radio}


def reports_of(neighbors) -> list:
    """The Bridge's /api/neighbors in one shape, whatever its source: (reporter, neighbor, snr,
    received at, broadcast interval). Live: one record per reporter with its neighbours;
    from the database: one row per neighbour."""
    body = neighbors.get("neighbors") if isinstance(neighbors, dict) else neighbors
    out = []
    for record in body or []:
        if not isinstance(record, dict):
            continue
        if isinstance(record.get("neighbors"), list):  # live
            received = words.stamp_epoch(record.get("last_updated")) or 0.0
            interval = int(record.get("node_broadcast_interval_secs") or 0)
            for n in record["neighbors"]:
                out.append((int(record.get("node_id") or 0), int(n.get("node_id") or 0), n.get("snr", 0.0), received, interval))
        else:  # database rows
            received = words.stamp_epoch(record.get("created_at")) or float(record.get("last_rx_time") or 0)
            out.append((int(record.get("node_id") or 0), int(record.get("neighbor_node_id") or 0), record.get("snr", 0.0), received, int(record.get("broadcast_interval") or 0)))
    return out


def build(nodes: list, me: str | None, neighbors, now: float) -> dict:
    """The topology: nodes (me first, then by number), links (one per pair, either way) and
    hearings (newest first), as Android's buildTopology."""
    my_num = num_of(me)
    by_num = {num_of(n.get("user_id") or n.get("num")): n for n in nodes if num_of(n.get("user_id") or n.get("num"))}
    hearings = []
    latest_report = {}
    # What the nodes themselves reported. The window follows the sender's broadcast interval,
    # which is hours, so a report is not called old just because it is from this morning.
    for reporter, neighbor, snr, received, interval in reports_of(neighbors):
        if not reporter or not neighbor or reporter == neighbor:
            continue
        window = max(FRESH_S, 2 * interval)
        hearings.append(_hearing(reporter, neighbor, snr, received, now - received < window, False))
        latest_report[reporter] = max(latest_report.get(reporter, 0.0), received)
    # What our radio heard directly: a node 0 hops away that has been heard.
    if my_num:
        for num, n in by_num.items():
            if num == my_num:
                continue
            hops = n.get("hops_away")
            heard_at = float(n.get("last_heard") or 0)
            if (hops in (None, 0)) and heard_at > 0:
                hearings.append(_hearing(my_num, num, n.get("snr", 0.0), heard_at, now - heard_at < FRESH_S, True))
    # One row per hearer and heard node.
    unique, seen = [], set()
    for h in hearings:
        key = (h["hearer"], h["heard"], h["by_our_radio"])
        if key not in seen:
            seen.add(key)
            unique.append(h)
    hearings = unique
    pairs = {}
    for h in hearings:
        pair = (min(h["hearer"], h["heard"]), max(h["hearer"], h["heard"]))
        pairs.setdefault(pair, []).append(h)
    links = [{"a": a, "b": b, "hearings": hs, "fresh": any(x["fresh"] for x in hs)} for (a, b), hs in pairs.items()]
    ids = []
    for num in ([my_num] if my_num else []) + list(by_num) + [x for h in hearings for x in (h["hearer"], h["heard"])]:
        if num and num not in ids:
            ids.append(num)
    ids.sort(key=lambda num: (num != my_num, num))
    topo_nodes = []
    for num in ids:
        info = by_num.get(num)
        last_seen = max(float((info or {}).get("last_heard") or 0), latest_report.get(num, 0.0))
        topo_nodes.append({
            "num": num,
            "label": ((info or {}).get("short_name") or "").strip() or node_id(num)[-4:],
            "name": ((info or {}).get("long_name") or "").strip() or node_id(num),
            "is_me": num == my_num,
            "last_seen": last_seen,
            "info": info,
        })
    hearings.sort(key=lambda h: h["at"], reverse=True)
    return {"nodes": topo_nodes, "links": links, "hearings": hearings, "reports": bool(latest_report)}


def is_fresh(last_seen: float, now: float) -> bool:
    return last_seen > 0 and now - last_seen < FRESH_S


def empty(topology: dict) -> bool:
    """Silence is not an empty mesh: until another node transmits, the screen says so."""
    return not any(not n["is_me"] for n in topology["nodes"])


def stats(topology: dict, now: float) -> list:
    """The three figures above the list: (label, value)."""
    others = [n for n in topology["nodes"] if not n["is_me"]]
    recent = sum(1 for n in others if is_fresh(n["last_seen"], now))
    direct = [h["snr"] for h in topology["hearings"] if h["by_our_radio"] and h["fresh"]]
    average = f"{words.fixed(sum(direct) / len(direct))} dB" if direct else "-"
    return [("Heard in 15 min", f"{recent} of {len(others)}"), ("Links", str(len(topology["links"]))), ("Average SNR, heard directly", average)]


def names(topology: dict) -> dict:
    return {n["num"]: ("Your node" if n["is_me"] else n["name"]) for n in topology["nodes"]}


def hearing_lines(topology: dict, now: float) -> list:
    """"Who hears whom": (text, detail, fresh) per hearing."""
    shown = names(topology)
    out = []
    for h in topology["hearings"]:
        detail = f"SNR {words.fixed(h['snr'])} dB, {words.ago(h['at'], now)}" + ("" if h["by_our_radio"] else ", as it reported")
        out.append((f"{shown.get(h['hearer'], node_id(h['hearer']))} hears {shown.get(h['heard'], node_id(h['heard']))}", detail, h["fresh"]))
    return out


def node_rows(topology: dict, now: float) -> list:
    """"Nodes": your node first, then the most recently heard. Each: (num, title, id line,
    detail, ago or "", tone of the dot and the ago)."""
    rows = []
    direct = {h["heard"]: h["snr"] for h in topology["hearings"] if h["by_our_radio"]}
    for n in sorted(topology["nodes"], key=lambda x: (not x["is_me"], -x["last_seen"])):
        info = n["info"] or {}
        fresh = is_fresh(n["last_seen"], now)
        id_line = node_id(n["num"])
        if info.get("hw_model") or info.get("hw_model_name"):
            id_line += "  " + words.hardware_name(info.get("hw_model"), info.get("hw_model_name", ""))
        details = []
        if not n["is_me"]:
            hops = int(info.get("hops_away") or 0)
            if n["num"] in direct:
                details.append(f"Heard directly, SNR {words.fixed(direct[n['num']])} dB")
                if int(info.get("rssi") or 0) != 0:
                    details.append(f"RSSI {int(info['rssi'])} dBm")
            elif hops > 0:
                details.append(f"{words.count(hops, 'hop')} away")
        battery = info.get("battery_level")
        if isinstance(battery, int):
            if 0 <= battery <= 100:
                details.append(f"Battery {battery}%")
            elif battery > 100:
                details.append("On USB power")
        rows.append({"num": n["num"], "title": f"{n['name']} (your node)" if n["is_me"] else n["name"], "id_line": id_line, "detail": ", ".join(details),
                     "ago": "" if n["is_me"] else words.ago(n["last_seen"], now), "tone": "primary" if n["is_me"] else ("green" if fresh else "muted")})
    return rows


def legend() -> list:
    return [("dot", "Your node", "primary"), ("dot", "Heard in the last 15 min", "green"), ("dot", "Not heard for 15 min or more", "muted"),
            ("line", "Recent link", "fresh"), ("line", "Older link", "old")]


# The force layout: nodes push each other apart, real links pull their ends together, and a weak
# pull to the centre keeps unlinked nodes on screen. 90 steps, the temperature falling to 0.
STEPS = 90


def start_positions(n: int) -> list:
    return [[120.0 * math.cos(2 * math.pi * i / max(n, 1)), 120.0 * math.sin(2 * math.pi * i / max(n, 1))] for i in range(n)]


def edges_of(topology: dict) -> list:
    index = {n["num"]: i for i, n in enumerate(topology["nodes"])}
    return [(index[l["a"]], index[l["b"]], l["fresh"]) for l in topology["links"] if l["a"] in index and l["b"] in index]


def simulate(positions: list, edges: list, temperature: float) -> None:
    """One step of Android's simulateForces, in place."""
    n = len(positions)
    if n < 2:
        return
    forces = [[0.0, 0.0] for _ in range(n)]
    repulsion, spring, gravity = 8000.0, 0.02, 0.01
    for i in range(n):
        for j in range(i + 1, n):
            dx = positions[i][0] - positions[j][0]
            dy = positions[i][1] - positions[j][1]
            dist = max(math.hypot(dx, dy), 1.0)
            force = repulsion / (dist * dist)
            fx, fy = force * dx / dist, force * dy / dist
            forces[i][0] += fx
            forces[i][1] += fy
            forces[j][0] -= fx
            forces[j][1] -= fy
    for i, j, _fresh in edges:
        if not (0 <= i < n and 0 <= j < n) or i == j:
            continue
        dx = positions[j][0] - positions[i][0]
        dy = positions[j][1] - positions[i][1]
        dist = max(math.hypot(dx, dy), 1.0)
        force = spring * dist
        fx, fy = force * dx / dist, force * dy / dist
        forces[i][0] += fx
        forces[i][1] += fy
        forces[j][0] -= fx
        forces[j][1] -= fy
    for i in range(n):
        forces[i][0] -= gravity * positions[i][0]
        forces[i][1] -= gravity * positions[i][1]
        fx, fy = forces[i]
        magnitude = max(math.hypot(fx, fy), 0.001)
        cap = min(magnitude, temperature * 10.0)
        positions[i][0] = min(max(positions[i][0] + cap * fx / magnitude, -300.0), 300.0)
        positions[i][1] = min(max(positions[i][1] + cap * fy / magnitude, -300.0), 300.0)


def temperature(step: int) -> float:
    return 5.0 * (1.0 - step / STEPS)


def fit(positions: list, width: float, height: float, pad: float) -> tuple:
    """(scale, mid x, mid y) that fit the layout in the canvas, as Android's fit."""
    xs = [p[0] for p in positions] or [0.0]
    ys = [p[1] for p in positions] or [0.0]
    span_x = max(max(xs) - min(xs), 1.0)
    span_y = max(max(ys) - min(ys), 1.0)
    scale = min(max(min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y), 0.2), 3.0)
    return scale, (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
