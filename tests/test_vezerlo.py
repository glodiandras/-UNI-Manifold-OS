"""A Manifold-OS vezérlő core-oldala (C17): rendszerállapot, kapcsolók, a feladat változásai és visszavonása a
próbafeladattal — valódi core a szálon, álgyökéren, álvaulton (a valódi vaulthoz és var/-hoz nem nyúl)."""
import os
import signal
import sys
import time
import unittest

from core import frame, snapshot, tasks, vezerlo
from tests.helpers import REPO, alg_core, tmpdir
from tests.test_core_api import _Szerver


class KapcsolokTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)

    def test_alapbol_mindketto_be(self):
        self.assertEqual(vezerlo.kapcsolok(self.cfg), {"asszisztens": True, "tracker": True})

    def test_tartos_reszleges_irás_es_hibak(self):
        self.assertEqual(vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False}), {"asszisztens": False, "tracker": True})
        self.assertEqual(vezerlo.kapcsolok(self.cfg), {"asszisztens": False, "tracker": True})   # újraolvasva is
        self.assertEqual(vezerlo.kapcsolo_ir(self.cfg, {"tracker": False}), {"asszisztens": False, "tracker": False})
        for rossz in ({}, {"nincs": True}, {"asszisztens": "igen"}, {"tracker": 1}, [True]):
            with self.assertRaises(ValueError, msg=str(rossz)):
                vezerlo.kapcsolo_ir(self.cfg, rossz)
        self.assertEqual(vezerlo.kapcsolok(self.cfg), {"asszisztens": False, "tracker": False})

    def test_serult_fajl_az_alapra_esik(self):
        (self.cfg.path("state") / "kapcsolok.json").write_text("{nem json", encoding="utf-8")
        self.assertEqual(vezerlo.kapcsolok(self.cfg), {"asszisztens": True, "tracker": True})
        (self.cfg.path("state") / "kapcsolok.json").write_text('{"asszisztens": "x", "tracker": false}', encoding="utf-8")
        self.assertEqual(vezerlo.kapcsolok(self.cfg), {"asszisztens": True, "tracker": False})

    def test_az_asszisztens_kapcsolo_a_feladatsort_nem_erinti(self):
        """80(a): a kapcsoló az asszisztenst kapcsolja; az automatikus feladat (a vektorindex) és a kézi is a kapun át megy tovább."""
        class Kapu:
            utolso_ok = ""

            def __init__(self):
                self.hivas = []

            def admit(self, t):
                self.hivas.append(t.id)
                return True
        kapu = Kapu()
        auto = tasks.TaskType("auto", "a", lambda *a: ([], "", []), automatikus=True)
        kezi = tasks.TaskType("kezi", "k", lambda *a: ([], "", []))
        admit = vezerlo.admit_lanc(self.cfg, kapu)
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False})
        self.assertTrue(admit(auto) and admit(kezi))
        self.assertEqual(kapu.hivas, ["auto", "kezi"])


class ModellzarTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        from pathlib import Path
        self.zar = Path(self._t.name) / "modell.lock"

    def test_ures_szabad(self):
        self.assertTrue(vezerlo._modellzar(self.zar)["szabad"])             # nincs fájl
        self.zar.write_text("", encoding="utf-8")
        self.assertTrue(vezerlo._modellzar(self.zar)["szabad"])

    def test_elo_birtokos(self):
        self.zar.write_text(f"pid {os.getpid()} · mlx-community/x · 14:03:11", encoding="utf-8")
        d = vezerlo._modellzar(self.zar)
        self.assertFalse(d["szabad"])
        self.assertEqual((d["pid"], d["repo"], d["ido"]), (os.getpid(), "mlx-community/x", "14:03:11"))

    def test_elavult_bejegyzes_szabad(self):
        import subprocess
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        self.zar.write_text(f"pid {p.pid} · repo · 01:02:03", encoding="utf-8")
        d = vezerlo._modellzar(self.zar)
        self.assertTrue(d["szabad"] and d["elavult"])


class VezerloApiTest(_Szerver):
    """A core a szálon; a próbafeladat a klónként szolgáló álvaulton ír (`MOS_PROBA_FELADAT=1`)."""

    def elokeszit(self):
        for k, v in {"MOS_FEJLESZTO": "1", "MOS_PROBA_FELADAT": "1", "PYTHONPATH": str(REPO)}.items():
            vissza = os.environ.get(k)
            os.environ[k] = v
            self.addCleanup(lambda k=k, vissza=vissza: os.environ.pop(k, None) if vissza is None
                            else os.environ.__setitem__(k, vissza))
        (self.v / "T01").mkdir()
        (self.v / "T01" / "a.md").write_text("# A\n", encoding="utf-8")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})

    def proba(self, **p):
        kod, d = self.k("POST", "/api/feladatok", {"tipus": "proba", "parameterek": p})
        self.assertEqual(kod, 201, d)
        return d["id"]

    def test_rendszer_vegpont(self):
        kod, d = self.k("GET", "/api/vezerlo/rendszer")
        self.assertEqual(kod, 200, d)
        self.assertGreater(d["memoria"]["osszes_gb"], 0)
        self.assertGreater(d["memoria"]["core_rss_mb"], 0)
        self.assertTrue(d["modellzar"]["szabad"])
        self.assertEqual(d["worker"], {"fut": False})                       # a vezérlő nem indít workert
        self.assertTrue(d["ssd"]["elerheto"])
        self.assertGreater(d["ssd"]["szabad_gb"], 0)
        self.assertEqual(set(d["mentes"]["tarolok"]), {"vault"})
        self.assertIsNone(d["mentes"]["utolso"])                            # még nincs bundle
        self.assertFalse(d["mentes"]["friss"])
        self.assertEqual(d["kapcsolok"], {"asszisztens": True, "tracker": True})

    def test_kapcsolok_vegpont(self):
        self.assertEqual(self.k("GET", "/api/vezerlo/kapcsolok")[1], {"kapcsolok": {"asszisztens": True, "tracker": True}})
        kod, d = self.k("PUT", "/api/vezerlo/kapcsolok", {"asszisztens": False})
        self.assertEqual((kod, d["kapcsolok"]), (200, {"asszisztens": False, "tracker": True}))
        self.assertEqual(self.k("GET", "/api/vezerlo/kapcsolok")[1]["kapcsolok"]["asszisztens"], False)
        self.assertEqual(self.k("PUT", "/api/vezerlo/kapcsolok", {"nincs": True})[0], 400)
        self.assertEqual(self.k("PUT", "/api/vezerlo/kapcsolok", {"tracker": "ki"})[0], 400)
        self.assertEqual(self.k("PUT", "/api/vezerlo/kapcsolok", {})[0], 400)

    def test_probafeladat_vegig_valtozasok_visszavonas(self):
        fid = self.proba(darab=2, mp=1.1)          # a kör azonosítója másodperc-felbontású: így két külön kör
        self.assertEqual(self.var(fid)["allapot"], "kesz")
        kod, d = self.k("GET", f"/api/feladatok/{fid}/valtozasok")
        self.assertEqual(kod, 200, d)
        self.assertEqual(len(d["korok"]), 2)
        for i, kor in enumerate(d["korok"], 1):
            self.assertTrue(kor["visszavonhato"] and not kor["visszavonva"])
            (c,) = kor["commitok"]
            self.assertEqual(c["fajlok"], [{"ut": f"_Proba/Próbafeladat {fid} - {i}.md", "allapot": "A", "plusz": 10,
                                            "minusz": 0}])
            self.assertEqual(c["tetel"], f"proba-{i}")
        fajl = lambda i: self.v / "_Proba" / f"Próbafeladat {fid} - {i}.md"  # noqa: E731
        self.assertTrue(fajl(1).exists() and fajl(2).exists())
        # a gépi commit hordozza a feladat azonosítóját és a forrást
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Feladat"], fid)
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Forras"], "mos-lepes")
        # visszavonás körönként a meglévő végponton
        kod, v = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": d["korok"][0]["kor"]})
        self.assertEqual(kod, 200, v)
        self.assertFalse(fajl(1).exists())
        self.assertTrue(fajl(2).exists())
        d2 = self.k("GET", f"/api/feladatok/{fid}/valtozasok")[1]
        self.assertEqual([(k["visszavonva"], k["visszavonhato"]) for k in d2["korok"]], [(True, False), (False, True)])
        self.assertEqual(self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": d["korok"][1]["kor"]})[0], 200)
        self.assertFalse(fajl(2).exists())
        self.assertEqual((self.v / "T01" / "a.md").read_text(encoding="utf-8"), "# A\n")   # a többihez nem nyúlt

    def test_visszavonas_kivarja_a_kor_vegi_bundle_zarat(self):
        """Gyökérok (Mac-integráció 2026-10-07): a gépi kör végén az időzített bundle (34. döntés) a kör-zár alatt fut; a
        kör értesítésének „Visszavonás”-a ekkor 409-et kapott. A felhasználói visszavonás a rövid zár-tartást kivárja."""
        import fcntl
        import threading
        fid = self.proba(darab=1, mp=0.1)
        self.assertEqual(self.var(fid)["allapot"], "kesz")
        kor = self.k("GET", f"/api/feladatok/{fid}/valtozasok")[1]["korok"][0]["kor"]
        megfogva, elenged = threading.Event(), threading.Event()

        def bundle():                                       # a bundle-t utánzó rövid zár-tartás egy másik leíróval
            with open(frame.lock_path(self.cfg), "a+") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                megfogva.set()
                elenged.wait(0.5)
                fcntl.flock(fh, fcntl.LOCK_UN)
        sz = threading.Thread(target=bundle, daemon=True)
        sz.start()
        self.addCleanup(sz.join, 5)
        self.assertTrue(megfogva.wait(5))
        kod, v = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": kor})
        self.assertEqual(kod, 200, v)
        self.assertFalse(sz.is_alive())

    def test_leallitott_probafeladat_valtozasa_visszavonhato(self):
        fid = self.proba(darab=1, mp=60)
        t0 = time.time()
        while time.time() - t0 < 15 and not any("Kész: _Proba" in s for s in
                                                self.k("GET", f"/api/feladatok/{fid}")[1].get("sorok", [])):
            time.sleep(0.1)
        kod, d = self.k("POST", f"/api/feladatok/{fid}/leallitas", {"azonnal": True})
        self.assertEqual(kod, 200, d)
        self.assertEqual(self.var(fid)["allapot"], "megallitva")
        # a lépés a leállítás előtt már írt: a változása listázva, a visszavonás működik
        v = self.k("GET", f"/api/feladatok/{fid}/valtozasok")[1]
        self.assertEqual(len(v["korok"]), 1)
        self.assertEqual(self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": v["korok"][0]["kor"]})[0], 200)
        self.assertFalse(list((self.v / "_Proba").glob("*.md")))

    def test_valtozasok_ismeretlen_feladatra_ures(self):
        kod, d = self.k("GET", "/api/feladatok/F-nincs/valtozasok")
        self.assertEqual((kod, d["korok"], d["nincs_tar"]), (200, [], False))

    def test_probafeladat_hibas_parameterek_400(self):
        for p in ({"darab": 0}, {"darab": 99}, {"mp": -1}, {"mp": "x"}):
            kod, d = self.k("POST", "/api/feladatok", {"tipus": "proba", "parameterek": p})
            self.assertEqual(kod, 400, (p, d))

    def test_core_megolese_utan_nem_marad_arva_lepes(self):
        """A kész-kritérium: a futó lépés pidje a DB-ben, az új core indulása leállítja az árva folyamatot."""
        fid = self.proba(darab=1, mp=60)
        t0 = time.time()
        while time.time() - t0 < 15 and not any("Kész: _Proba" in s for s in
                                                self.k("GET", f"/api/feladatok/{fid}")[1].get("sorok", [])):
            time.sleep(0.1)
        import sqlite3
        db = sqlite3.connect(self.cfg.path("feladatok_db"))
        (pid,) = db.execute("SELECT lepes_pid FROM feladat WHERE id=?", (fid,)).fetchone()
        db.close()
        self.assertIsNotNone(pid)
        self.addCleanup(lambda: self._el(pid) and os.killpg(pid, signal.SIGKILL))
        self.assertTrue(self._el(pid))
        # a „core halála” itt a feladatsor eldobása (a szál a tesztprocesszben él): az új sor a DB-ből takarít
        q = tasks.Queue(self.cfg, start_delay=999)
        self.addCleanup(q.close)
        q.arva_var()                                   # Audit 4 (A-javító): az árva-rendezés a kézfogás után, háttérszálon fut
        self.assertFalse(self._el(pid), "az árva lépés leállt")
        # (a feladat végállapotát a külön folyamatos ArvaTest méri: itt a szálon élő eredeti sor is ír a DB-be)

    @staticmethod
    def _el(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return bool(tasks._ps("lstart", pid))


if __name__ == "__main__":
    unittest.main()
