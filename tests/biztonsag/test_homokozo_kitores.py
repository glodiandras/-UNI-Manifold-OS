"""F9 security audit §1: sandbox escape probes for the code workbench (F10, `modulok/kod`, `kod_futtat.sb`), in the REAL
`sandbox-exec` (macOS only; elsewhere an `[indokolt]` skip).

`tests/test_kod_ellenorzes.ElszigetelesTest` already proves: no read of a file outside, no TCP to 127.0.0.1, no subprocess, no
folder listing. These probes add what an attacker would try next, each in Python and in JavaScript (the embedded runtimes): read a
note in the VAULT, read a file in HOME, write into the vault, into the install folder (`{install}`), into HOME, into /tmp, into
the code tree; escape the work folder with a symlink or a hard link created inside it; DNS and UDP; reach the core's HTTP port;
`/dev/tcp`-style shells. The program prints OK only if every attempt failed; and afterwards nothing exists at the targets."""
from __future__ import annotations

import os
import socket
import threading
import unittest
from pathlib import Path

from tests.test_kod_ellenorzes import MACOS, OK_SKIP, _Alap, teszt


@unittest.skipUnless(MACOS, OK_SKIP)
class HomokozoKitoresTest(_Alap):

    def setUp(self):
        self.vault = self.t / "work" / "Manifold"
        self.vault.mkdir(parents=True, exist_ok=True)
        (self.vault / "Privat.md").write_text("VAULT-SECRET\n", encoding="utf-8")
        self.home = self.t / "home"
        (self.home / ".ssh").mkdir(parents=True, exist_ok=True)
        (self.home / ".ssh" / "id_test").write_text("HOME-SECRET\n", encoding="utf-8")
        self.install = self.home / "Library" / "Application Support" / "Manifold"
        self.install.mkdir(parents=True, exist_ok=True)
        self.celok = [self.vault / "pwned.md", self.install / "pwned.txt", self.home / "pwned.txt",
                      Path("/private/tmp") / f"mos-f9-pwned-{os.getpid()}.txt", self.t / "work" / "os" / "pwned.txt"]
        for c in self.celok:
            self.addCleanup(lambda c=c: c.unlink(missing_ok=True))
        # a listening socket the program must not reach (stands in for the core's HTTP port)
        self.szerver = socket.socket()
        self.szerver.bind(("127.0.0.1", 0))
        self.szerver.listen(1)
        self.szerver.settimeout(0.2)
        self.kapcsolodott = threading.Event()
        self._fut = True

        def figyel():
            while self._fut:
                try:
                    c, _ = self.szerver.accept()
                    self.kapcsolodott.set()
                    c.close()
                except OSError:
                    pass
        self.figyelo = threading.Thread(target=figyel, daemon=True)
        self.figyelo.start()
        self.addCleanup(self._zar)
        self.port = self.szerver.getsockname()[1]

    def _zar(self):
        self._fut = False
        self.figyelo.join(2)
        self.szerver.close()

    def _ok(self, nyelv: str, forras: str):
        if not self.elerheto(nyelv):
            self.skipTest(f"[indokolt] no {nyelv} runtime on this machine")
        _, esem = self.fut(nyelv, forras, [teszt(1, "", "OK\n")])
        t = self.szakasz(esem, "teszt")
        self.assertTrue(t, esem)
        self.assertEqual(t[0]["teszt"]["allapot"], "atment", t[0]["teszt"])
        for c in self.celok:
            self.assertFalse(c.exists(), f"the sandboxed program created {c}")
        self.assertFalse(self.kapcsolodott.is_set(), "the sandboxed program reached a local TCP port")

    def test_python(self):
        celok = [str(c) for c in self.celok]
        self._ok("python", f"""import os, socket
fails = []
def probe(name, fn):
    try:
        fn()
        fails.append(name)
    except Exception:
        pass
probe("vault read", lambda: open({str(self.vault / 'Privat.md')!r}).read())
probe("home read", lambda: open({str(self.home / '.ssh' / 'id_test')!r}).read())
probe("vault list", lambda: os.listdir({str(self.vault)!r}))
for c in {celok!r}:
    probe("write " + c, lambda c=c: open(c, "w").write("x"))
probe("mkdir install", lambda: os.mkdir({str(self.install / 'd')!r}))
def link_escape():
    os.symlink({str(self.vault / 'Privat.md')!r}, "l.md")
    data = open("l.md").read()
    if "VAULT-SECRET" not in data:
        raise OSError("no data")
probe("symlink read", link_escape)
def hardlink_escape():
    os.link({str(self.vault / 'Privat.md')!r}, "h.md")
probe("hardlink", hardlink_escape)
probe("tcp core", lambda: socket.create_connection(("127.0.0.1", {self.port}), timeout=1))
probe("tcp v6", lambda: socket.create_connection(("::1", {self.port}), timeout=1))
probe("dns", lambda: socket.getaddrinfo("example.com", 443))
def udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.sendto(b"x", ("8.8.8.8", 53))
probe("udp", udp)
probe("exec", lambda: os.execv("/bin/sh", ["sh", "-c", "echo x > /private/tmp/mos-f9-exec"]))
probe("fork", lambda: os.fork() or None)
print("OK" if not fails else "LEAK " + ";".join(fails))
""")

    def test_javascript(self):
        celok = [str(c) for c in self.celok]
        self._ok("javascript", f"""const fs = require('fs'); const net = require('net'); const dgram = require('dgram');
const cp = require('child_process');
const fails = [];
function probe(name, fn) {{ try {{ fn(); fails.push(name); }} catch (e) {{}} }}
probe('vault read', () => fs.readFileSync({str(self.vault / 'Privat.md')!r}, 'utf8'));
probe('home read', () => fs.readFileSync({str(self.home / '.ssh' / 'id_test')!r}, 'utf8'));
probe('vault list', () => fs.readdirSync({str(self.vault)!r}));
for (const c of {celok!r}) probe('write ' + c, () => fs.writeFileSync(c, 'x'));
probe('symlink read', () => {{ fs.symlinkSync({str(self.vault / 'Privat.md')!r}, 'l.md');
  if (!fs.readFileSync('l.md', 'utf8').includes('VAULT-SECRET')) throw new Error('no'); }});
probe('hardlink', () => fs.linkSync({str(self.vault / 'Privat.md')!r}, 'h.md'));
probe('exec', () => cp.execFileSync('/bin/sh', ['-c', 'echo x']));
probe('spawn', () => {{ const r = cp.spawnSync('/usr/bin/true'); if (r.error) throw r.error; }});
let pending = 3;
function done() {{ if (--pending === 0) console.log(fails.length ? 'LEAK ' + fails.join(';') : 'OK'); }}
const s = net.connect({{ host: '127.0.0.1', port: {self.port} }});
s.on('connect', () => {{ fails.push('tcp core'); s.destroy(); done(); }});
s.on('error', () => done());
require('dns').lookup('example.com', (err) => {{ if (!err) fails.push('dns'); done(); }});
const u = dgram.createSocket('udp4');
u.on('error', () => {{ try {{ u.close(); }} catch (e) {{}} done(); }});
u.send(Buffer.from('x'), 53, '8.8.8.8', (err) => {{ if (!err) fails.push('udp'); try {{ u.close(); }} catch (e) {{}} if (err) return; done(); }});
""")
