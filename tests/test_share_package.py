# SPDX-License-Identifier: GPL-3.0-or-later
"""meshsat-share and its place in the package: the script is POSIX sh and reads the Bridge's
port as the app does, the unit runs it before the node and the Bridge, the package installs,
enables and removes it. Where this machine can make network namespaces of its own (nft and
unprivileged user namespaces: the runner, not CI's slim images, which skip it), the rules
themselves: loaded by the script in a private namespace, with veth pairs to a second one that
stands for the network, and tried from there, local and shared (tests/share_netns.py)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(ROOT, "package", "rootfs", "usr", "lib", "meshsat", "bin", "meshsat-share")
INSIDE = os.path.join(ROOT, "tests", "share_netns.py")
UNIT = os.path.join(ROOT, "package", "rootfs", "lib", "systemd", "system", "meshsat-share.service")
SBIN = "/usr/sbin:/sbin:/usr/bin:/bin"
sys.path.insert(0, os.path.join(ROOT, "app"))

from meshsat.model import share  # noqa: E402


def read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def relocated(work: str) -> str:
    """The script with its flag, the Bridge's settings and its lock in `work`: the one change a
    test makes to it."""
    with open(SCRIPT, encoding="utf-8") as handle:
        text = handle.read()
    for old, name in (("/etc/meshsat/share-on-network", "share-on-network"), ("/etc/meshsat/bridge.env", "bridge.env"), ("/run/meshsat-share.lock", "lock")):
        assert old in text, old
        text = text.replace(old, os.path.join(work, name))
    path = os.path.join(work, "meshsat-share")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class SharePackageTest(unittest.TestCase):
    def test_the_script_is_posix_sh(self):
        self.assertTrue(read(SCRIPT).startswith("#!/bin/sh\n"))
        for shell in ("sh", "dash"):
            if shutil.which(shell):
                run = subprocess.run([shell, "-n", SCRIPT], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_the_unit_runs_it_before_the_node_and_the_bridge(self):
        unit = {}
        for line in read(UNIT).splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                unit.setdefault(key, []).extend(value.split())
        self.assertEqual(unit["Type"], ["oneshot"])
        self.assertEqual(unit["RemainAfterExit"], ["yes"])
        self.assertEqual(unit["ExecStart"], ["/usr/lib/meshsat/bin/meshsat-share", "apply"])
        self.assertLessEqual({"meshtasticd.service", "meshsat-bridge.service"}, set(unit["Before"]))
        self.assertIn("nftables.service", unit["After"])
        self.assertIn("meshsat-bridge.service", unit["PartOf"])
        self.assertEqual(unit["WantedBy"], ["multi-user.target"])

    def test_the_package_installs_enables_and_removes_it(self):
        build = read("build-deb.sh")
        self.assertIn('install -D -m 0755 "$HERE/package/rootfs/usr/lib/meshsat/bin/meshsat-share" "$ROOT/usr/lib/meshsat/bin/meshsat-share"', build)
        self.assertIn('install -D -m 0644 "$HERE/package/rootfs/lib/systemd/system/meshsat-share.service" "$ROOT/lib/systemd/system/meshsat-share.service"', build)
        depends = next(line for line in read("package/DEBIAN/control.in").splitlines() if line.startswith("Depends:"))
        self.assertIn(" nftables,", depends)
        self.assertIn(" pkexec,", depends)
        postinst = read("package/DEBIAN/postinst")
        # The rules are in place before the node (meshsat-hardware starts it) and the Bridge start.
        applied = postinst.index("systemctl restart meshsat-share.service")
        self.assertLess(postinst.index("systemctl enable meshsat-share.service"), applied)
        self.assertLess(applied, postinst.index("systemctl start meshsat-hardware.service"))
        self.assertLess(applied, postinst.index("systemctl restart meshsat-bridge.service"))
        prerm = read("package/DEBIAN/prerm").splitlines()
        for verb in ("stop", "disable"):
            line = next(line for line in prerm if line.strip().startswith(f"systemctl {verb} meshsat-bridge.service"))
            self.assertIn("meshsat-share.service", line, f"a remove does not {verb} it")
        postrm = read("package/DEBIAN/postrm")
        self.assertIn("nft delete table inet meshsat", postrm.split("remove|purge)", 1)[1].split(";;", 1)[0])
        self.assertIn("rm -f /etc/meshsat/share-on-network", postrm.split("    purge)", 1)[1].split(";;", 1)[0])
        self.assertNotIn("share-on-network", read("package/DEBIAN/conffiles"))

    def test_the_app_and_the_script_close_the_same_interfaces_and_open_the_same_ranges(self):
        lines = read(SCRIPT).splitlines()
        cellular = next(line for line in lines if line.startswith("CELLULAR=")).split("=", 1)[1].strip("'")
        private = next(line for line in lines if line.startswith("PRIVATE4=")).split("=", 1)[1].strip("'")
        self.assertEqual(tuple(p.strip().strip('"').rstrip("*") for p in cellular.split(",")), share.CELLULAR)
        self.assertEqual(tuple(p.strip() for p in private.split(",")), share.PRIVATE4)

    def test_the_script_reads_the_port_as_the_app_does(self):
        # meshsat-share's bridge_port() and model/share.py's, on the same files.
        function = re.search(r"^bridge_port\(\) \{\n.*?^\}\n", read(SCRIPT), re.S | re.M).group(0)
        cases = ("MESHSAT_PORT=6050\n", "MESHSAT_PORT=7050\n", 'MESHSAT_PORT="7051"\n', "MESHSAT_PORT='7052'\n", "MESHSAT_PORT=7053  \n",
                 "  MESHSAT_PORT = 7054\n", "MESHSAT_PORT=7055\nMESHSAT_PORT=7056\n", "# MESHSAT_PORT=7057\n", "MESHSAT_PORT=07058\n",
                 "MESHSAT_PORT=+7063\n", "MESHSAT_PORT=0\n", "MESHSAT_PORT=65535\n", "MESHSAT_PORT=65536\n", "MESHSAT_PORT=99999999999999999999\n",
                 "MESHSAT_PORT=abc\n", "MESHSAT_PORT=\n", "MESHSAT_PORT=-7062\n", 'MESHSAT_PORT="7061\n', "MESHSAT_PORTX=7059\n", "HUB_API_KEY=\n", "")
        with tempfile.TemporaryDirectory() as work:
            env = os.path.join(work, "bridge.env")
            for text in cases:
                with open(env, "w", encoding="utf-8") as handle:
                    handle.write(text)
                run = subprocess.run(["sh", "-c", f'{function}ENV_FILE="$1"; bridge_port', "sh", env], capture_output=True, text=True)
                self.assertEqual(run.stdout.strip(), str(share.bridge_port(text)), f"{text!r}: {run.stderr}")

    def test_status_needs_no_root_and_the_changes_do(self):
        with tempfile.TemporaryDirectory() as work:
            script = relocated(work)
            status = subprocess.run(["sh", script, "status"], capture_output=True, text=True)
            self.assertEqual((status.returncode, status.stdout), (0, "local\n"))
            open(os.path.join(work, "share-on-network"), "w").close()
            self.assertEqual(subprocess.run(["sh", script, "status"], capture_output=True, text=True).stdout, "shared\n")
            usage = subprocess.run(["sh", script, "share"], capture_output=True, text=True)
            self.assertEqual(usage.returncode, 2)
            self.assertIn("usage: meshsat-share on|off|apply|status", usage.stderr)
            if os.getuid() != 0:
                for verb in ("off", "on", "apply"):
                    run = subprocess.run(["sh", script, verb], capture_output=True, text=True, env=dict(os.environ, PATH=SBIN))
                    self.assertEqual(run.returncode, 1, verb)
                    self.assertIn("run as root", run.stderr)
                self.assertTrue(os.path.exists(os.path.join(work, "share-on-network")), "off without root removed the flag")


def namespaces() -> str | None:
    """Why the rules cannot be tried on this machine, or None when they can."""
    for tool in ("nft", "unshare", "ip"):
        if not shutil.which(tool, path=SBIN):
            return f"no {tool} here"
    try:
        run = subprocess.run(["unshare", "--user", "--map-root-user", "--net", "sh", "-c", "ip link add probe0 type veth peer name probe1 && nft list ruleset"],
                             capture_output=True, text=True, timeout=15, env=dict(os.environ, PATH=SBIN))
    except (OSError, subprocess.SubprocessError) as error:
        return f"no network namespaces here: {error}"
    return None if run.returncode == 0 else f"no network namespaces of our own here: {run.stderr.strip()[-160:]}"


NO_NAMESPACES = namespaces()


@unittest.skipIf(NO_NAMESPACES, NO_NAMESPACES or "")
class ShareRulesTest(unittest.TestCase):
    """The rules as the kernel applies them, in namespaces of this test's own: the machine's
    own firewall is never touched."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        work = cls.dir.name
        script = relocated(work)
        os.makedirs(os.path.join(work, "bin"))
        logger = os.path.join(work, "bin", "logger")
        with open(logger, "w", encoding="utf-8") as handle:
            handle.write(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{work}/log"\n')
        os.chmod(logger, 0o755)
        open(os.path.join(work, "log"), "w").close()
        run = subprocess.run(["unshare", "--user", "--map-root-user", "--net", "python3", INSIDE, work, script],
                             capture_output=True, text=True, timeout=240, env=dict(os.environ, PATH=SBIN))
        if run.returncode != 0:
            raise AssertionError(f"the namespaces did not run: {run.stderr[-1500:]}")
        cls.out = json.loads(run.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_the_network_works_before_any_rule(self):
        self.assertEqual(set(self.out["before"].values()), {"open"}, self.out["before"])

    def test_local_only_this_device_reaches_the_bridge_and_the_node(self):
        self.assertEqual(self.out["apply"]["code"], 0, self.out["apply"])
        local = dict(self.out["local"])
        self.assertEqual(local.pop("wifi 7050"), "open", "a port no rule names (the control) was closed")
        self.assertEqual(set(local.values()), {"reset"}, self.out["local"])
        self.assertEqual(set(self.out["local mine"].values()), {"open"}, self.out["local mine"])
        self.assertIn("tcp dport 6050 reject with tcp reset", self.out["local table"])

    def test_shared_the_bridge_answers_this_network_only(self):
        self.assertEqual(self.out["on"]["code"], 0, self.out["on"])
        self.assertTrue(self.out["shared flag"])
        self.assertEqual(self.out["shared"], {"wifi 6050": "open", "wifi 4403": "reset", "wifi 9443": "reset", "wifi 7050": "open",
                                              "public 6050": "reset", "ula 6050": "open", "ula 4403": "reset", "global6 6050": "reset",
                                              "mobile 6050": "reset"})
        self.assertEqual(set(self.out["shared mine"].values()), {"open"}, self.out["shared mine"])

    def test_off_closes_it_again_and_cuts_a_connection_still_open(self):
        self.assertEqual(self.out["off"]["code"], 0, self.out["off"])
        self.assertFalse(self.out["off flag"])
        self.assertEqual(self.out["held across off"], "reset")
        self.assertEqual(set(self.out["after off"].values()) - {"open"}, {"reset"})
        self.assertEqual([k for k, v in self.out["after off"].items() if v == "open"], ["wifi 7050"], "only the port nothing guards is open")

    def test_the_port_is_the_one_in_the_bridges_settings(self):
        self.assertEqual(self.out["apply 7050"]["code"], 0, self.out["apply 7050"])
        self.assertEqual(self.out["port 7050"]["wifi 7050"], "reset")
        self.assertEqual(self.out["port 7050"]["wifi 6050"], "open")
        self.assertEqual(self.out["port 7050"]["wifi 4403"], "reset")

    def test_without_nft_nothing_changes_and_it_says_why(self):
        self.assertEqual(self.out["on without nft"]["code"], 1)
        self.assertIn("nft not found", self.out["on without nft"]["err"])
        self.assertFalse(self.out["on without nft flag"], "on left the flag without its rules")
        self.assertEqual(self.out["off without nft"]["code"], 1)
        self.assertTrue(self.out["off without nft flag"], "off removed the flag without loading its rules")
        self.assertIn("tcp dport 7050 reject with tcp reset", self.out["table at the end"])

    def test_every_change_is_logged(self):
        log = self.out["log"]
        self.assertIn("local: the Bridge (TCP 6050) and the node's 4403 and 9443 answer this device only", log)
        self.assertIn("shared: the Bridge (TCP 6050) answers this device's network, the node's 4403 and 9443 this device only", log)
        self.assertIn("local: the Bridge (TCP 7050)", log)
        self.assertIn("nft not found", log)


if __name__ == "__main__":
    unittest.main()
