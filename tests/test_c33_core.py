"""C33 — a core megbízhatósági és teljesítmény-javításai álgyökéren (2. audit T069, T070, T171, T175, T177).

- T175: az I/O-hiba (EACCES, ENOSPC, EFBIG, eltűnt vault) magyar, abszolút út nélküli 507/503, `lemez_hiba` jellel.
- T070: a gráf és a graf-meta ETag/304-gyel; a Bases-válasz a `Tabla` építésének idejét külön adja (T179).
- T177: a kicsinyített képek gyorsítótárának takarítása (árva, kor, méret) és a rögzített zártömb.
- T069/T171: a doctor a kapu és az index állapotát jelzi.
"""
import errno
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from core import doctor, kepek, vaultio
from tests.helpers import API_TITOK, REPO, alg_core, ir, tmpdir
from tests.test_core_api import _Szerver


class LemezHibaTest(unittest.TestCase):
    def test_az_errno_kod_es_magyar_uzenet_ut_nelkul(self):
        with tmpdir() as t:
            v = Path(t) / "Manifold"
            v.mkdir()
            for nev, kod in (("ENOSPC", 507), ("EFBIG", 507), ("EACCES", 503), ("EROFS", 503), ("EIO", 503)):
                e = OSError(getattr(errno, nev), os.strerror(getattr(errno, nev)), f"{v}/Titkos/.x.md.1234.manifold-tmp")
                k, d = vaultio.lemez_hiba(e, v)
                self.assertEqual((k, d["errno"], d["lemez_hiba"]), (kod, nev, True))
                self.assertNotIn(str(v), d["hiba"])
                self.assertNotIn("Errno", d["hiba"])
            k, d = vaultio.lemez_hiba(OSError(errno.ENOENT, "x"), Path(t) / "nincs-ilyen-vault")
            self.assertEqual(k, 503)
            self.assertFalse(d["vault_elerheto"])
            self.assertIn("nincs-ilyen-vault", d["hiba"])          # csak a mappa neve, nem az út
            self.assertNotIn(t, d["hiba"])


class SzerverLemezHibaTest(_Szerver):
    def test_irasvedett_mappa_503_magyarul_ut_nelkul_es_a_fajl_erintetlen(self):
        ir(self.v, "Zart/Jegyzet.md", "eredeti\n")
        kod, d = self.k("GET", "/api/vault/fajl?ut=Zart/Jegyzet.md")
        self.assertEqual(kod, 200)
        os.chmod(self.v / "Zart", 0o555)
        self.addCleanup(os.chmod, self.v / "Zart", 0o755)
        kod, d = self.k("PUT", "/api/vault/fajl", {"ut": "Zart/Jegyzet.md", "tartalom": "új\n", "alap": d["hash"]})
        self.assertEqual(kod, 503, d)
        self.assertTrue(d["lemez_hiba"])
        self.assertEqual(d["errno"], "EACCES")
        self.assertNotIn(str(self.v), d["hiba"])
        self.assertNotIn("PermissionError", d["hiba"])
        self.assertEqual((self.v / "Zart" / "Jegyzet.md").read_text(), "eredeti\n")
        self.assertEqual([p.name for p in (self.v / "Zart").iterdir()], ["Jegyzet.md"])     # nem maradt tmp

    def test_az_eltunt_vault_503_lemez_hibaval(self):
        masik = self.v.parent / "Manifold-el"
        os.rename(self.v, masik)
        self.addCleanup(os.rename, masik, self.v)
        kod, d = self.k("GET", "/api/vault/fajl?ut=A.md")
        self.assertEqual(kod, 503, d)
        self.assertTrue(d["lemez_hiba"])
        self.assertNotIn(str(self.v.parent), d["hiba"])


class GrafEtagTest(_Szerver):
    def elokeszit(self):
        ir(self.v, "A.md", "# A\n[[B]]\n")
        ir(self.v, "B.md", "# B\n")

    def test_valtozatlan_szerkezetre_304_valtozasra_uj_etag(self):
        import http.client
        self.assertTrue(_var(lambda: self.k("GET", "/api/vault/index")[1].get("kesz")))

        def kerd(ut, etag=None):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            h = {"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, **({"If-None-Match": etag} if etag else {})}
            c.request("GET", ut, headers=h)
            r = c.getresponse()
            return r.status, r.getheader("ETag"), r.read()
        for ut in ("/api/vault/graf", "/api/vault/graf-meta"):
            kod, etag, torzs = kerd(ut)
            self.assertEqual(kod, 200)
            self.assertTrue(etag)
            kod2, etag2, torzs2 = kerd(ut, etag)
            self.assertEqual((kod2, etag2, torzs2), (304, etag, b""))
        _, etag, _ = kerd("/api/vault/graf")
        kod, d = self.k("GET", "/api/vault/fajl?ut=B.md")
        kod, _ = self.k("PUT", "/api/vault/fajl", {"ut": "B.md", "tartalom": "# B\ntöbb szöveg\n", "alap": d["hash"]})
        self.assertEqual(kod, 200)
        self.assertEqual(kerd("/api/vault/graf", etag)[0], 304)        # tartalmi mentés: a szerkezet változatlan
        kod, d = self.k("GET", "/api/vault/fajl?ut=B.md")
        self.k("PUT", "/api/vault/fajl", {"ut": "B.md", "tartalom": "# B\n[[A]]\n", "alap": d["hash"]})
        kod, uj, torzs = kerd("/api/vault/graf", etag)
        self.assertEqual(kod, 200)
        self.assertNotEqual(uj, etag)
        self.assertIn(["B.md", "A.md"], json.loads(torzs)["elek"])

    def test_a_bazis_valasz_a_tabla_idejet_kulon_adja(self):
        self.assertTrue(_var(lambda: self.k("GET", "/api/vault/index")[1].get("kesz")))
        kod, d = self.k("POST", "/api/vault/bazis/lekerdez", {"szoveg": "views:\n  - type: table\n    name: T\n"})
        self.assertEqual(kod, 200, d)
        self.assertIn("tabla_ms", d)
        self.assertEqual(d["tabla_mod"], "teljes")
        kod, d = self.k("POST", "/api/vault/bazis/lekerdez", {"szoveg": "views:\n  - type: table\n    name: T\n"})
        self.assertEqual(d["tabla_mod"], "meleg")


def _var(f, mp=10.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < mp:
        if f():
            return True
        time.sleep(0.05)
    return False


class KepekTakaritasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, self.v = alg_core(self._t.name)
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("nincs Pillow")
        self.Image = Image

    def kep(self, nev, w=1200):
        p = self.v / nev
        self.Image.new("RGB", (w, w // 2), (200, 30, 40)).save(p, "JPEG")
        return p

    def test_arva_es_meretkorlat_lru(self):
        a, b, c = self.kep("a.jpg"), self.kep("b.jpg"), self.kep("c.jpg")
        for p in (a, b, c):
            ki, tipus = kepek.kicsinyitett(self.cfg, p, "image/jpeg", 400)
            self.assertNotEqual(ki, p)
            self.assertTrue(ki.with_suffix(".forras").exists())
        mappa = Path(self.cfg.path("vault_kepek"))
        self.assertEqual(len(list(mappa.rglob("*.jpg"))), 3)
        a.unlink()                                                # az `a` forrása eltűnt: árva
        r = kepek.takarit(self.cfg)
        self.assertEqual((r["arva"], r["torolve"]), (1, 1))
        self.assertEqual(len(list(mappa.rglob("*.jpg"))), 2)
        self.assertEqual(len(list(mappa.rglob("*.forras"))), 2)
        # a `b` a legrégebben használt: a méretkorlát (kb. egy bejegyzésnyi) azt viszi
        regi = time.time() - 3600
        for f in list(mappa.rglob("*.jpg")) + list(mappa.rglob("*.forras")):
            os.utime(f, (regi, regi))
        kepek.kicsinyitett(self.cfg, c, "image/jpeg", 400)        # találat: a `c` friss lesz
        egy = max(f.stat().st_size for f in mappa.rglob("*.jpg"))
        r = kepek.takarit(self.cfg, max_mb=(egy + 10) / 1024 / 1024)
        maradt = list(mappa.rglob("*.jpg"))
        self.assertEqual(len(maradt), 1)
        self.assertEqual(maradt[0].with_suffix(".forras").read_text().rsplit("|", 1)[-1], str(c))

    def test_kor_szerinti_torles_es_a_kiseret_nelkuli_regi_bejegyzes(self):
        p = self.kep("d.jpg")
        ki, _ = kepek.kicsinyitett(self.cfg, p, "image/jpeg", 400)
        ki.with_suffix(".forras").unlink()                        # C33 előtti bejegyzés: nincs kísérő → nem árva
        self.assertEqual(kepek.takarit(self.cfg)["torolve"], 0)
        regi = time.time() - 100 * 86400
        os.utime(ki, (regi, regi))
        jpg_mtime = ki.stat().st_mtime
        kepek.kicsinyitett(self.cfg, p, "image/jpeg", 400)        # a találat a kép mtime-ját (az ETag részét) nem érinti
        self.assertEqual(ki.stat().st_mtime, jpg_mtime)
        self.assertEqual(kepek.takarit(self.cfg)["torolve"], 1)

    def test_a_zartomb_rogzitett_meretu(self):
        z = {kepek._zar(f"{i:040x}") for i in range(5000)}
        self.assertLessEqual(len(z), len(kepek._ZARTOMB))


class DoctorKapuIndexTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)

    def eredmeny(self, fn):
        ki = []
        fn(self.cfg, lambda a, n, u: ki.append((a, n, u)))
        return ki

    def test_kapu_nincs_bukott_es_rendben(self):
        self.assertEqual(self.eredmeny(doctor._kapu)[0][0], doctor.INFO)
        runs = self.cfg.path("runs")
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "kapu-20261008-100000.json").write_text(json.dumps(
            {"ido": "2026-10-08T10:00:00", "head": "abc", "rendben": False,
             "eredmenyek": [{"nev": "apfs_proba", "rendben": False}]}))
        a, _, u = self.eredmeny(doctor._kapu)[0]
        self.assertEqual(a, doctor.FIGYELEM)
        self.assertIn("BUKOTT", u)
        self.assertIn("apfs_proba", u)
        head = doctor._kodtar_git(self.cfg.root, "rev-parse", "HEAD")        # (az álgyökér a munkafa var/tmp-jében él)
        (runs / "kapu-20261008-110000.json").write_text(json.dumps(
            {"ido": "2026-10-08T11:00:00", "head": head, "rendben": True, "eredmenyek": []}))
        a, _, u = self.eredmeny(doctor._kapu)[0]
        self.assertEqual(a, doctor.OK, u)
        (runs / "kapu-20261008-120000.json").write_text(json.dumps(
            {"ido": "2026-10-08T12:00:00", "head": "0" * 40, "rendben": True, "eredmenyek": []}))
        a, _, u = self.eredmeny(doctor._kapu)[0]
        if head:                                                    # ismeretlen (régi) HEAD: a kapu régebbi a HEAD-nél
            self.assertEqual(a, doctor.FIGYELEM, u)
            self.assertIn("régebbi a HEAD-nél", u)

    def test_index_hiany_ep_es_serult(self):
        self.assertEqual(self.eredmeny(doctor._index)[0][0], doctor.INFO)
        from core.index import tar
        db = self.cfg.path("index") / "vault.sqlite"
        tar.nyit(db, iro=True).close()
        a, _, u = self.eredmeny(doctor._index)[-1]
        self.assertEqual((a, u.startswith("ép")), (doctor.OK, True))
        db.write_bytes(b"nem adatbazis" * 500)
        for kiseret in ("-wal", "-shm"):
            Path(str(db) + kiseret).unlink(missing_ok=True)
        (db.parent / "serult-20261008-100000.sqlite").write_bytes(b"x")
        ki = self.eredmeny(doctor._index)
        self.assertEqual(ki[0][0], doctor.INFO)                    # a félretett sérült index
        self.assertEqual(ki[-1][0], doctor.FIGYELEM)
        self.assertIn("újraépíti", ki[-1][2])


class KapuFuttatoTest(unittest.TestCase):
    def test_lista_es_ismeretlen_proba(self):
        p = subprocess.run([sys.executable, "-B", str(REPO / "tests" / "kezi" / "kapu.py"), "--lista"], capture_output=True,
                           text=True, cwd=REPO)
        self.assertEqual(p.returncode, 0)
        self.assertIn("apfs_proba", p.stdout.split())
        p = subprocess.run([sys.executable, "-B", str(REPO / "tests" / "kezi" / "kapu.py"), "nincs_ilyen_proba"],
                           capture_output=True, text=True, cwd=REPO)
        self.assertEqual(p.returncode, 2)

    def test_a_vedett_lista_egyetlen_forrasbol_jon(self):
        """Lelet 9: a futtató `VEDETT` listája és a doctor `KAPU_VEDETT`-je ugyanaz az objektum (nincs két kézzel másolt lista)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("kapu_vedett_teszt", REPO / "tests" / "kezi" / "kapu.py")
        elozo = list(sys.path)
        try:
            modul = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modul)
        finally:
            sys.path[:] = elozo
        self.assertIs(modul.VEDETT, doctor.KAPU_VEDETT)
        self.assertIn("core/server.py", modul.VEDETT)

    def test_az_osszesites_a_runs_ala_kerul_a_bukott_proba_1(self):
        """Egy ál-próba (a `tests/kezi` mintájára) bukik: a futtató 1-gyel lép ki, és a riport a `{runs}/kapu-*.json`-ban."""
        with tmpdir() as t:
            cfg, root, _ = alg_core(t)
            mappa = Path(t) / "kezi"
            mappa.mkdir()
            (mappa / "alproba_bukik.py").write_text("import sys\nprint('HIBA: szándékos')\nsys.exit(1)\n", encoding="utf-8")
            env = {**os.environ, "MOS_RUNS": str(cfg.path("runs")), "MOS_KAPU_MAPPA": str(mappa)}
            p = subprocess.run([sys.executable, "-B", str(REPO / "tests" / "kezi" / "kapu.py"), "alproba_bukik"],
                               capture_output=True, text=True, cwd=REPO, env=env, timeout=60)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            riport = sorted(cfg.path("runs").glob("kapu-*.json"))
            self.assertEqual(len(riport), 1)
            d = json.loads(riport[0].read_text())
            self.assertFalse(d["rendben"])
            self.assertEqual(d["eredmenyek"][0]["zaro_sor"], "HIBA: szándékos")
            self.assertFalse(d["teljes"])


if __name__ == "__main__":
    unittest.main()
