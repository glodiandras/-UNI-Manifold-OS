"""Két valódi core-alfolyamat egy telepítésen, két munkatéren (F3-DESIGN §4, §9 WP3): különálló állapot-fák és zárak, a
másik core titka 403, a másik vault útja elutasítva, ugyanazon a vaulton (kis-nagybetűs útváltozattal is) a második core
`foglalt` 75, közös modell-worker (egy `worker.pid` az `{install_run}`-ban), és a másolatként felismert munkatér új
azonosítóval indul (a gyökerek az új azonosítóra rögzülnek)."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import unittest
import urllib.parse

from core import server
from core.modell import kliens
from tests.helpers import REPO, tmpdir
from tests.multi_user import elso_sor, install, munkater, termek_cfg, termek_env, termek_telepites

TITOK_A = "titok-a-0123456789abcdef"
TITOK_B = "titok-b-0123456789abcdef"


class KetCoreTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root, self.home = termek_telepites(self._t.name)
        self.va, self.ida = munkater(self._t.name, "Jegyzet A")
        self.vb, self.idb = munkater(self._t.name, "Jegyzet B")
        (self.va / "a.md").write_text("# A\n", encoding="utf-8")
        (self.vb / "titok.md").write_text("# B titka\n", encoding="utf-8")
        self.pa, self.ka = self._indit(self.va, TITOK_A)
        self.pb, self.kb = self._indit(self.vb, TITOK_B)

    def _indit(self, vault, titok):
        p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=termek_env(self.root, self.home, vault, MOS_API_TITOK=titok))
        self.addCleanup(self._leallit, p)
        sor = elso_sor(p)
        self.assertTrue(sor, "a core nem adott kézfogást")
        return p, json.loads(sor)

    @staticmethod
    def _leallit(p):
        if p.poll() is None:
            p.stdin.close()
            try:
                p.wait(40)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for f in (p.stdin, p.stdout):
            if f and not f.closed:
                f.close()

    @staticmethod
    def _k(port: int, ut: str, titok: str) -> tuple[int, dict | str]:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        try:
            c.request("GET", ut, headers={"Host": f"127.0.0.1:{port}", "X-Manifold": titok})
            r = c.getresponse()
            torzs = r.read().decode("utf-8", "replace")
        finally:
            c.close()
        try:
            return r.status, json.loads(torzs)
        except ValueError:
            return r.status, torzs

    def test_kulon_allapot_fak_es_zarak(self):
        for k, v, id, p in ((self.ka, self.va, self.ida, self.pa), (self.kb, self.vb, self.idb, self.pb)):
            self.assertEqual((k["elrendezes"], k["munkater_id"], k["vault"]), ("termek", id, os.path.realpath(v)))
            self.assertEqual(server.zar_foglalt(v / ".manifold" / "var" / "run" / "core.lock"),
                             {"foglalt": True, "pid": p.pid, "vault": str(v)})
            self.assertTrue((v / ".manifold" / "var" / "feladatok.sqlite").is_file(), "a munkatér saját állapota")
        orok = sorted((install(self.home) / "run" / "vaults").glob("*.lock"))
        self.assertEqual(len(orok), 2)
        self.assertEqual(sorted(server.zar_foglalt(o)["pid"] for o in orok), sorted([self.pa.pid, self.pb.pid]))
        self.assertFalse((self.root / "var").exists(), "a csak olvasható kódfába semmi nem kerül")

    def test_a_masik_core_titka_403(self):
        self.assertEqual(self._k(self.ka["port"], "/api/allapot", TITOK_A)[0], 200)
        self.assertEqual(self._k(self.ka["port"], "/api/allapot", TITOK_B)[0], 403)
        self.assertEqual(self._k(self.kb["port"], "/api/allapot", TITOK_A)[0], 403)
        self.assertEqual(self._k(self.kb["port"], "/api/allapot", TITOK_B)[0], 200)

    def test_a_masik_vault_utja_elutasitva(self):
        self.assertEqual(self._k(self.ka["port"], "/api/vault/fajl?ut=a.md", TITOK_A)[0], 200)
        for ut in ("../Jegyzet B/titok.md", str(self.vb / "titok.md")):
            kod, torzs = self._k(self.ka["port"], "/api/vault/fajl?ut=" + urllib.parse.quote(ut), TITOK_A)
            self.assertIn(kod, (400, 403, 404), ut)
            self.assertNotIn("B titka", json.dumps(torzs, ensure_ascii=False))

    def test_ugyanaz_a_vault_kis_nagy_betuvel_is_foglalt(self):
        valtozat = self.va.parent / self.va.name.upper()
        for v in ((valtozat,) if valtozat.is_dir() else ()) + (self.va,):
            p = subprocess.run([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, input=b"", capture_output=True,
                               env=termek_env(self.root, self.home, v), timeout=90)
            self.assertEqual(p.returncode, server.CORE_ZAR_KILEPES, p.stderr.decode(errors="replace"))
            self.assertEqual(json.loads(p.stdout.splitlines()[0]), {"foglalt": True, "pid": self.pa.pid, "vault": str(self.va)})

    def test_kozos_worker(self):
        cfga = termek_cfg(self.root, self.home, self.va)
        f = kliens.Folyamat(cfga, env={"HOME": str(self.home), "MOS_SETTINGS": "", "MOS_ROOT": str(self.root)})
        self.addCleanup(f.leallit)
        f.biztosit(timeout=60)
        pidf = install(self.home) / "run" / "worker.pid"
        pid = int(pidf.read_text().split()[0])
        self.assertEqual(pid, f.proc.pid)
        for k, titok in ((self.ka, TITOK_A), (self.kb, TITOK_B)):
            kod, d = self._k(k["port"], "/api/modell", titok)
            self.assertEqual(kod, 200, d)
            self.assertEqual((d["worker"] or {}).get("pid"), pid, "mindkét core ugyanazt a workert látja")
        self.assertTrue((install(self.home) / "logs" / "worker.log").is_file())


class MasolatTest(unittest.TestCase):
    """A másolt munkatér (a régi mappa is ugyanazt az azonosítót hordozza) új azonosítóval nyílik: a kézfogás és a rögzített
    gyökerek (pl. a belső mentés `{backup_gyoker}/{workspace_id}` mappája) már az újat használják."""

    def test_masolat_uj_azonositoval_indul(self):
        with tmpdir() as t:
            root, home = termek_telepites(t)
            va, ida = munkater(t, "Eredeti")
            self._fut_es_leall(root, home, va)                 # bekerül a regiszterbe; az állapotmentés a saját mappájába
            mentesek = install(home) / "backups"
            eredeti = sorted(x.name for x in (mentesek / ida).iterdir())
            masolat = va.parent / "Masolat"
            shutil.copytree(va, masolat, ignore=shutil.ignore_patterns("var"))
            p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=termek_env(root, home, masolat))
            try:
                uj = json.loads(elso_sor(p))["munkater_id"]
                self.assertNotEqual(uj, ida)
                self.assertIn(f'"{uj}"', (masolat / ".manifold" / "workspace.toml").read_text(encoding="utf-8"))
                self.assertIn(f'"{ida}"', (va / ".manifold" / "workspace.toml").read_text(encoding="utf-8"))
            finally:
                KetCoreTest._leallit(p)
            # a kilépési mentés a másolat új azonosítójú mappájába ment (a rögzített `MOS_BACKUP` az újra állt), a régié érintetlen
            self.assertEqual({d.name for d in mentesek.iterdir()}, {ida, uj})
            self.assertTrue(list((mentesek / uj).glob("mos-allapot-*")))
            self.assertEqual(sorted(x.name for x in (mentesek / ida).iterdir()), eredeti)

    @staticmethod
    def _fut_es_leall(root, home, v):
        p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=termek_env(root, home, v))
        try:
            json.loads(elso_sor(p))
        finally:
            KetCoreTest._leallit(p)


if __name__ == "__main__":
    unittest.main()
