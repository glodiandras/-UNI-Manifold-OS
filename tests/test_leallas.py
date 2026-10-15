"""A core leállása alfolyamatban (C29.6, 2. audit T003, T027): a második ⌘Q (SIGTERM) a már futó rendezett leállást is
fokozza; a kezelőszálak és a WS-kapcsolatok nem tarthatják vissza; egy vaulton egyszerre egy core fut.

A core valódi alfolyamat (`python -m core start`), mert a SIGTERM-jelkezelő és az `os._exit` csak a fő szálban él.
Az álgyökér `os.toml`-ja módosított: `[core] kezelo_idokorlat_mp = 2` (a csonka kérések gyorsan lejárnak) és
`[feladatsor] indulasi_szunet_mp = 0`. A próbafeladat (`MOS_PROBA_FELADAT=1`) egy gépi commitot ír, majd `mp` másodpercig
vár — ez a „hosszan futó lépés”."""
import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

from core import snapshot
from tests.helpers import API_TITOK, REPO, alg_core, env, tmpdir


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        toml = self.root / "config" / "os.toml"
        szoveg = toml.read_text(encoding="utf-8")
        szoveg = re.sub(r"(?m)^kezelo_idokorlat_mp = \d+", "kezelo_idokorlat_mp = 2", szoveg, count=1)     # a kulcs az os.toml-ban áll
        szoveg = szoveg.replace("indulasi_szunet_mp = 180", "indulasi_szunet_mp = 0", 1)
        self.assertIn("kezelo_idokorlat_mp = 2", szoveg)
        self.assertIn("indulasi_szunet_mp = 0", szoveg)
        toml.write_text(szoveg, encoding="utf-8")
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        (self.v / "T01").mkdir()
        (self.v / "T01" / "a.md").write_text("# A\n", encoding="utf-8")
        repo.commit("alap", {"Mos-Forras": "kezi"})
        self.p = None
        self.addCleanup(self._takarit)

    def _takarit(self):
        if self.p is not None:
            if self.p.poll() is None:
                self.p.kill()
                self.p.wait()
            for f in (self.p.stdout, self.p.stdin):
                if f and not f.closed:
                    f.close()
        for pid in getattr(self, "_lepes_pidek", []):
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def indit(self):
        self.p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env=env(MOS_ROOT=str(self.root), PYTHONPATH=str(REPO), MOS_PROBA_FELADAT="1"))
        self.kezfogas = json.loads(self.p.stdout.readline())
        self.port = self.kezfogas["port"]

    def k(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        t = r.read()
        return r.status, json.loads(t) if t else None

    def var(self, feltetel, mp=30.0, lepes=0.05):
        t0 = time.monotonic()
        while time.monotonic() - t0 < mp:
            if (v := feltetel()):
                return v
            time.sleep(lepes)
        return None

    def port_zarva(self, mp=15):
        def zarva():
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
            except OSError:
                return True
            return False
        return bool(self.var(zarva, mp))

    def lepes_pid(self):
        """A próbafeladat lépés-folyamata: a core közvetlen gyermeke (`core.probafeladat`)."""
        ki = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True).stdout
        for sor in ki.splitlines():
            reszek = sor.split(None, 2)
            if len(reszek) == 3 and reszek[1] == str(self.p.pid) and "core.probafeladat" in reszek[2]:
                return int(reszek[0])
        return None


class SigtermLeallasTest(Alap):
    def test_a_masodik_kilepes_a_futo_rendezett_leallast_is_fokozza(self):
        """T003: stdin-zárás (rendezett leállás: a lépés végét várja) → SIGTERM → a lépést azonnal leállítja és ≤ 12 s
        alatt kilép; a lépés folyamatcsoportja nem él tovább. Eddig a második SIGTERM hatástalan volt (a 60 s-os lépés
        végéig, kb. 45 s)."""
        self.indit()
        kod, d = self.k("POST", "/api/feladatok", {"tipus": "proba", "parameterek": {"darab": 1, "mp": 60}})
        self.assertEqual(kod, 201, d)
        pid = self.var(self.lepes_pid)
        self.assertIsNotNone(pid, "a próbafeladat lépése nem indult el")
        self._lepes_pidek = [pid]
        self.p.stdin.close()                                    # az első ⌘Q: rendezett leállás
        # a lépés végét várja, a HTTP-port addig nyitva: a feladatsor „lezárva” jele mutatja, hogy elkezdődött
        self.assertTrue(self.var(lambda: self.k("GET", "/api/allapot")[1]["feladatsor"]["lezarva"]),
                        "a rendezett leállás nem kezdődött el")
        self.assertIsNone(self.p.poll(), "a lépés végéig a core nem állhat le")
        t0 = time.monotonic()
        self.p.send_signal(signal.SIGTERM)                      # a második ⌘Q
        self.p.wait(timeout=12)
        self.assertLess(time.monotonic() - t0, 12)
        with self.assertRaises(ProcessLookupError):
            os.killpg(pid, 0)                                   # a lépés folyamatcsoportja nem él


class KezeloIdokorlatTest(Alap):
    def test_csonka_torzs_nem_tartja_vissza_a_leallast(self):
        """T003: egy félbehagyott HTTP-törzs eddig korlát nélkül tartotta a kezelőszálat (`block_on_close`)."""
        self.indit()
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(f"POST /api/aktivitas HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Manifold: {API_TITOK}\r\n"
                  "Content-Length: 100\r\n\r\n{".encode())       # a törzs 1 bájtja a 100-ból
        self.assertEqual(self.k("GET", "/health")[0], 200)      # a csonka kérés kezelőszála már él
        t0 = time.monotonic()
        self.p.stdin.close()
        self.assertEqual(self.p.wait(timeout=30), 0)
        self.assertLess(time.monotonic() - t0, 25)
        s.close()

    def test_csonka_fejlec_nem_tartja_vissza_a_leallast(self):
        self.indit()
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n".encode())     # a fejléc nincs lezárva
        self.assertEqual(self.k("GET", "/health")[0], 200)
        t0 = time.monotonic()
        self.p.stdin.close()
        self.assertEqual(self.p.wait(timeout=30), 0)
        self.assertLess(time.monotonic() - t0, 25)
        s.close()

    def test_nem_olvaso_ws_kliens_nem_tartja_vissza_a_leallast(self):
        self.indit()
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall((f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: mos.{API_TITOK}\r\n\r\n").encode())
        self.assertIn(b"101", s.recv(1024))
        t0 = time.monotonic()
        self.p.stdin.close()                                    # a kliens többé nem olvas, nem küld
        self.assertEqual(self.p.wait(timeout=20), 0)
        self.assertLess(time.monotonic() - t0, 15)
        s.close()


class EgypeldanyosZarTest(Alap):
    def test_a_masodik_core_foglalt_kezfogassal_kilep(self):
        """T027: a `{run}/core.lock` miatt két core nem fut ugyanazon a vaulton; a második géppel olvasható sort ír."""
        self.indit()
        masodik = subprocess.run([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, input=b"", capture_output=True,
                                 env=env(MOS_ROOT=str(self.root), PYTHONPATH=str(REPO)), timeout=60)
        self.assertEqual(masodik.returncode, 75, masodik.stderr.decode("utf-8", "replace")[-800:])
        sor = json.loads(masodik.stdout.decode("utf-8").splitlines()[0])
        self.assertEqual(sor, {"foglalt": True, "pid": self.p.pid, "vault": str(self.v)})
        self.assertEqual(self.k("GET", "/health")[0], 200)      # az első core élő maradt
        self.p.stdin.close()
        self.assertEqual(self.p.wait(timeout=20), 0)
        # a leállás után a zár szabad: új core indulhat
        self.p.stdout.close()
        self.indit()
        self.assertGreater(self.port, 0)


if __name__ == "__main__":
    unittest.main()
