#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Real touch gestures on the phone's own touchscreen (as root), for screenshots of what only a
# finger opens: touch.py swipe x1 y1 x2 y2 [ms] | tap x y | info     (screen pixels, 720x1440)
import sys, time
import evdev
from evdev import ecodes as e

def device():
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        if "touch" in d.name.lower():
            return d
    sys.exit("no touchscreen")

d = device()
caps = dict(d.capabilities(absinfo=True)[e.EV_ABS])
xmax, ymax = caps[e.ABS_MT_POSITION_X].max, caps[e.ABS_MT_POSITION_Y].max

def scale(x, y):
    return int(x * xmax / 719), int(y * ymax / 1439)

def down(x, y, tid=4242):
    x, y = scale(x, y)
    for t, c, v in ((e.EV_ABS, e.ABS_MT_SLOT, 0), (e.EV_ABS, e.ABS_MT_TRACKING_ID, tid), (e.EV_ABS, e.ABS_MT_POSITION_X, x), (e.EV_ABS, e.ABS_MT_POSITION_Y, y),
                    (e.EV_KEY, e.BTN_TOUCH, 1), (e.EV_ABS, e.ABS_X, x), (e.EV_ABS, e.ABS_Y, y)):
        if t == e.EV_ABS and c in (e.ABS_X, e.ABS_Y) and c not in caps:
            continue
        d.write(t, c, v)
    d.write(e.EV_SYN, e.SYN_REPORT, 0)

def move(x, y):
    x, y = scale(x, y)
    d.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
    d.write(e.EV_ABS, e.ABS_MT_POSITION_X, x)
    d.write(e.EV_ABS, e.ABS_MT_POSITION_Y, y)
    if e.ABS_X in caps:
        d.write(e.EV_ABS, e.ABS_X, x); d.write(e.EV_ABS, e.ABS_Y, y)
    d.write(e.EV_SYN, e.SYN_REPORT, 0)

def up():
    d.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
    d.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, -1)
    d.write(e.EV_KEY, e.BTN_TOUCH, 0)
    d.write(e.EV_SYN, e.SYN_REPORT, 0)

cmd = sys.argv[1] if len(sys.argv) > 1 else "info"
if cmd == "info":
    print(d.path, d.name, "x max", xmax, "y max", ymax)
elif cmd == "tap":
    x, y = int(sys.argv[2]), int(sys.argv[3])
    down(x, y); time.sleep(0.08); up()
elif cmd == "swipe":
    x1, y1, x2, y2 = (int(v) for v in sys.argv[2:6])
    ms = int(sys.argv[6]) if len(sys.argv) > 6 else 350
    steps = 24
    down(x1, y1); time.sleep(0.03)
    for i in range(1, steps + 1):
        move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
        time.sleep(ms / 1000 / steps)
    time.sleep(0.05); up()
