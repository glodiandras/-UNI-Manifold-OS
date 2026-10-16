"""F7 Health: az ellenőrzések állapotai, a Diagnose-sorok és a „Fix automatically” biztonsági szabályai (szintetikus termék-álgyökéren).

A javítás csak az ellenőrzés által jelenleg ajánlott, visszafordítható/újraépülő műveletet futtatja; a vaulthoz, a modellekhez és
a hálózathoz nem nyúl. A tesztek ál-HOME-ot és ideiglenes mappát használnak."""
import json
import os
import shutil
import sqlite3
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import config, egeszseg, snapshot
from core.utvonalak import HttpError
from tests.helpers import REPO, tmpdir
from tests.test_doctor_termek import halott_pid, termek_epit


def _epit(t):
    k = termek_epit(t)
    shutil.copy(REPO / "config" / "models.toml", k.root / "config" / "models.toml")
    return k


def _sor(jel, kod):
    return next(s for s in jel["ellenorzesek"] if s["kod"] == kod)


class HealthAlapTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)

    def test_minden_ellenorzes_stabil_kodu_es_angol_szoveges_sor(self):
        jel = egeszseg.jelentes(self.k.cfg)
        self.assertEqual([s["kod"] for s in jel["ellenorzesek"]],
                         ["index", "pillanatkep", "zarak", "lemezhely", "modellek", "munkater", "folyamatok", "telepites"])
        for s in jel["ellenorzesek"]:
            with self.subTest(s["kod"]):
                self.assertIn(s["allapot"], egeszseg.ALLAPOTOK)
                self.assertIn(s["uzenet_kod"], egeszseg.SZOVEG)
                self.assertEqual(s["cim"], egeszseg.CIMEK[s["kod"]])
                self.assertNotRegex(s["uzenet"], r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")      # a tartalék angol
                self.assertNotIn("{", s["uzenet"])                              # minden sablonparaméter kitöltve
                json.dumps(s, allow_nan=False)
        self.assertEqual(jel["osszesen"], {a: sum(1 for s in jel["ellenorzesek"] if s["allapot"] == a) for a in egeszseg.ALLAPOTOK})

    def test_a_felhasznalonak_mutatott_core_szovegek_nem_tartalmaznak_fejlesztoi_szot(self):
        import re
        fejlesztoi = re.compile(r"\b(core|worker|git|json|api|pid|sandbox|debug|stderr|traceback|xcode|sqlite|flock|symlink)\b", re.I)
        for forras in (egeszseg.SZOVEG, egeszseg.JAVITAS_KESZ, egeszseg.CIMEK):
            for kod, szoveg in forras.items():
                self.assertIsNone(fejlesztoi.search(szoveg), f"{kod}: {szoveg}")

    def test_a_szoveg_sablonok_helyorzoi_a_parammal_egyeznek(self):
        import re
        for kod, sablon in egeszseg.SZOVEG.items():
            for p in re.findall(r"\{(\w+)\}", sablon):
                self.assertTrue(p.isidentifier(), kod)
        for kod, sablon in egeszseg.JAVITAS_KESZ.items():
            self.assertIn(kod, egeszseg.JAVITASOK)

    def test_friss_munkater_nem_piros_es_nincs_javitas_ajanlat(self):
        jel = egeszseg.jelentes(self.k.cfg)
        self.assertEqual(jel["osszesen"]["hiba"], 0)
        self.assertEqual([s["kod"] for s in jel["ellenorzesek"] if s["javitas"]], [])

    def test_egy_ellenorzes_hibaja_nem_viszi_le_a_tobbit(self):
        def rossz(cfg, app):
            raise RuntimeError("boom")
        tabla = tuple((k, rossz if k == "zarak" else f) for k, f in egeszseg.ELLENORZESEK)
        with mock.patch.object(egeszseg, "ELLENORZESEK", tabla):
            jel = egeszseg.jelentes(self.k.cfg)
        sor = _sor(jel, "zarak")
        self.assertEqual((sor["allapot"], sor["uzenet_kod"]), ("hiba", "ellenorzes.nem_futott"))
        self.assertNotIn("boom", json.dumps(sor))                                # kivétel-szöveg nem szivárog
        self.assertEqual(_sor(jel, "munkater")["allapot"], "ok")

    def test_diagnosztika_egy_sor_reszletekkel_es_ismeretlen_kod_404(self):
        d = egeszseg.diagnosztika(self.k.cfg, None, "lemezhely")
        self.assertEqual([s["kod"] for s in d["ellenorzesek"]], ["lemezhely"])
        self.assertTrue(d["ellenorzesek"][0]["reszletek"])
        with self.assertRaises(HttpError) as e:
            egeszseg.diagnosztika(self.k.cfg, None, "nincs")
        self.assertEqual((e.exception.code, e.exception.kod), (404, "egeszseg.ismeretlen_ellenorzes"))

    def test_ismeretlen_vagy_nem_ajanlott_javitas_elutasitott_es_nem_valtoztat(self):
        elotte = sorted(str(p) for p in self.k.install.rglob("*"))
        for rossz in (None, "rm_rf", "../zar_takarit", 5):
            with self.assertRaises(HttpError) as e:
                egeszseg.javit(self.k.cfg, None, rossz)
            self.assertEqual((e.exception.code, e.exception.kod), (400, "egeszseg.ismeretlen_javitas"))
        for ismert in egeszseg.JAVITASOK:                    # ismert, de most nincs mit javítani
            with self.assertRaises(HttpError) as e:
                egeszseg.javit(self.k.cfg, None, ismert)
            self.assertEqual((e.exception.code, e.exception.kod), (409, "egeszseg.nincs_mit_javitani"))
        self.assertEqual(sorted(str(p) for p in self.k.install.rglob("*")), elotte)

    def test_a_javitasok_listaja_csak_az_ismert_biztonsagos_muveletek(self):
        self.assertEqual(set(egeszseg.JAVITASOK), {"zar_takarit", "git_zar_takarit", "regiszter_takarit", "index_ujraepit", "gyorsitotar_torles"})


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)
        self.db = self.k.cfg.path("index") / "vault.sqlite"
        self.db.parent.mkdir(parents=True, exist_ok=True)

    def test_ep_index_ok_a_fajlok_szamaval(self):
        from core.index import tar
        c = tar.nyit(self.db, iro=True)
        c.close()
        s = _sor(egeszseg.jelentes(self.k.cfg), "index")
        self.assertEqual((s["allapot"], s["uzenet_kod"]), ("ok", "index.ok"))
        self.assertEqual(s["param"], {"fajl": 0})

    def test_serult_index_javitasa_felreteszi_de_nem_torli(self):
        self.db.write_bytes(b"not a database" * 100)
        s = _sor(egeszseg.jelentes(self.k.cfg), "index")
        self.assertEqual((s["allapot"], s["javitas"]), ("figyelem", "index_ujraepit"))
        r = egeszseg.javit(self.k.cfg, None, "index_ujraepit")
        self.assertTrue(r["ok"])
        self.assertFalse(self.db.exists())
        felretett = list(self.db.parent.glob("serult-*.sqlite"))
        self.assertEqual(len(felretett), 1)
        self.assertEqual(felretett[0].read_bytes(), b"not a database" * 100)      # visszafordítható: a fájl megvan
        self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "index")["uzenet_kod"], "index.nincs")

    def test_fut_core_eseten_a_javitas_az_index_sajat_ujraepiteset_hivja(self):
        self.db.write_bytes(b"garbage" * 100)
        hivas = []
        app = SimpleNamespace(index=SimpleNamespace(_serult_ujraepit=lambda e: hivas.append(e)))
        with mock.patch.dict(os.environ, {"MOS_EGESZSEG_SZINKRON": "1"}):
            r = egeszseg.javit(self.k.cfg, app, "index_ujraepit")
        self.assertEqual(len(hivas), 1)
        self.assertTrue(self.db.exists())                                          # a fájlt nem a Health nyúlta meg
        self.assertEqual(r["uzenet_kod"], "index_ujraepit")

    def test_felretett_peldany_info_es_a_sor_reszleteben_latszik(self):
        from core.index import tar
        tar.nyit(self.db, iro=True).close()
        (self.db.parent / "serult-20260101-000000.sqlite").write_bytes(b"x")
        s = _sor(egeszseg.jelentes(self.k.cfg), "index")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["param"]), ("info", "index.felretett", {"db": 1}))
        self.assertIn("serult-20260101-000000.sqlite", json.dumps(s["reszletek"]))


class ZarakTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)
        self.run = self.k.cfg.path("install_run")
        self.run.mkdir(parents=True, exist_ok=True)

    def test_halott_worker_pid_javithato_es_az_atnevezes_visszafordithato(self):
        (self.run / "worker.pid").write_text(f"{halott_pid()} 5555", encoding="utf-8")
        s = _sor(egeszseg.jelentes(self.k.cfg), "zarak")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["javitas"]), ("figyelem", "zarak.elavult", "zar_takarit"))
        egeszseg.javit(self.k.cfg, None, "zar_takarit")
        self.assertFalse((self.run / "worker.pid").exists())
        self.assertIn("5555", (self.run / "worker.pid.elavult").read_text(encoding="utf-8"))
        self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "zarak")["uzenet_kod"], "zarak.ok")

    def test_el_a_pid_nem_javithato(self):
        (self.run / "worker.pid").write_text(f"{os.getpid()} 5555", encoding="utf-8")
        self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "zarak")["uzenet_kod"], "zarak.ok")
        with self.assertRaises(HttpError) as e:
            egeszseg.javit(self.k.cfg, None, "zar_takarit")
        self.assertEqual(e.exception.code, 409)
        self.assertTrue((self.run / "worker.pid").exists())

    def test_foglalt_zar_eseten_nincs_javitas(self):
        import fcntl
        (self.run / "worker.pid").write_text(f"{halott_pid()} 5555", encoding="utf-8")
        with open(self.run / "worker.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            s = _sor(egeszseg.jelentes(self.k.cfg), "zarak")
            self.assertEqual((s["uzenet_kod"], s["javitas"]), ("zarak.foglalt", None))
            with self.assertRaises(HttpError):
                egeszseg.javit(self.k.cfg, None, "zar_takarit")
        self.assertTrue((self.run / "worker.pid").exists())


class PillanatkepTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)
        self.repo = snapshot.repos(self.k.cfg)["vault"]

    def test_nincs_tarolo_info_majd_ep_tarolo_ok(self):
        self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "pillanatkep")["uzenet_kod"], "pillanatkep.nincs")
        self.repo.init()
        s = _sor(egeszseg.jelentes(self.k.cfg), "pillanatkep")
        self.assertIn(s["allapot"], ("ok", "info"))
        self.assertIn(s["uzenet_kod"], ("pillanatkep.ok", "pillanatkep.mentes_regi"))

    def test_elavult_git_zar_felretetele_csak_ha_regi_es_a_kor_zar_szabad(self):
        self.repo.init()
        z = self.repo.git_dir / "index.lock"
        z.write_text("", encoding="utf-8")
        self.assertNotEqual(_sor(egeszseg.jelentes(self.k.cfg), "pillanatkep")["uzenet_kod"], "pillanatkep.elavult_zar")   # friss zár: él
        regi = time.time() - egeszseg.ELAVULT_ZAR_MP - 5
        os.utime(z, (regi, regi))
        s = _sor(egeszseg.jelentes(self.k.cfg), "pillanatkep")
        self.assertEqual((s["uzenet_kod"], s["javitas"]), ("pillanatkep.elavult_zar", "git_zar_takarit"))
        egeszseg.javit(self.k.cfg, None, "git_zar_takarit")
        self.assertFalse(z.exists())
        self.assertEqual(len(list(self.repo.git_dir.glob("index.lock.elavult-*"))), 1)

    def test_hianyzo_git_piros_javitas_nelkul(self):
        self.repo.init()
        with mock.patch("shutil.which", return_value=None):
            s = _sor(egeszseg.jelentes(self.k.cfg), "pillanatkep")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["javitas"]), ("hiba", "pillanatkep.nincs_git", None))


class LemezhelyTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)
        self.cache = self.k.cfg.path("vault_kepek")
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "a").mkdir()
        (self.cache / "a" / "kep.png").write_bytes(b"x" * 2048)
        self.jegyzet = self.k.vault / "note.md"
        self.jegyzet.write_text("# keep me\n", encoding="utf-8")

    def _szabad(self, gb):
        return mock.patch.object(egeszseg, "_szabad", return_value=int(gb * 1e9))

    def test_kevés_hely_figyelem_es_kritikus_hely_hiba(self):
        with self._szabad(3):
            s = _sor(egeszseg.jelentes(self.k.cfg), "lemezhely")
        self.assertEqual((s["allapot"], s["uzenet_kod"]), ("figyelem", "lemezhely.kevesebb"))
        with self._szabad(0.5):
            s = _sor(egeszseg.jelentes(self.k.cfg), "lemezhely")
        self.assertEqual((s["allapot"], s["uzenet_kod"]), ("hiba", "lemezhely.kritikus"))
        with self._szabad(50):
            self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "lemezhely")["allapot"], "ok")

    def test_a_gyorsitotar_torlese_csak_a_kepek_gyorsitotarat_uriti(self):
        with self._szabad(3):
            self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "lemezhely")["javitas"], "gyorsitotar_torles")
            r = egeszseg.javit(self.k.cfg, None, "gyorsitotar_torles")
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assertTrue(self.cache.is_dir())
        self.assertEqual(self.jegyzet.read_text(encoding="utf-8"), "# keep me\n")      # a jegyzethez nem nyúl
        self.assertIn("cleared", r["uzenet"])

    def test_ures_gyorsitotarnal_nincs_javitas_ajanlat(self):
        shutil.rmtree(self.cache / "a")
        with self._szabad(3):
            self.assertIsNone(_sor(egeszseg.jelentes(self.k.cfg), "lemezhely")["javitas"])


class ModellekTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)

    def test_nincs_modell_info_es_a_javitas_nem_toltes(self):
        s = _sor(egeszseg.jelentes(self.k.cfg), "modellek")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["javitas"]), ("info", "modellek.nincs", None))

    def test_elter_revizio_figyelem_javitas_nelkul_mert_a_letoltes_kifejezett_kerest_igenyel(self):
        from core.modell import manifeszt, revizio
        man = manifeszt.betolt(self.k.cfg)
        nev, m = next(iter(man["modell"].items()))
        d = revizio.repo_mappa(self.k.cfg.path("models"), m["repo"]) / "snapshots" / ("a" * 40)
        d.mkdir(parents=True)
        s = _sor(egeszseg.jelentes(self.k.cfg), "modellek")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["javitas"]), ("figyelem", "modellek.hianyos", None))
        self.assertIn(nev, json.dumps(s["reszletek"]))

    def test_ajanlott_modellek_teljesen_telepitve_ok(self):
        from core.modell import manifeszt
        man = manifeszt.betolt(self.k.cfg)

        def kesz(models, nev, m):
            return {"allapot": "kesz", "lemez_bajt": 10, "ellenorizve": None, "revizio": m["revizio"]}
        with mock.patch.object(manifeszt, "telepitettseg", kesz):
            s = _sor(egeszseg.jelentes(self.k.cfg), "modellek")
        self.assertEqual((s["allapot"], s["uzenet_kod"]), ("ok", "modellek.ok"))
        self.assertEqual(s["param"]["osszes"], sum(1 for m in man["modell"].values() if m.get("ajanlott")))

    def test_hianyzo_manifeszt_piros(self):
        (self.k.root / "config" / "models.toml").unlink()
        s = _sor(egeszseg.jelentes(self.k.cfg), "modellek")
        self.assertEqual((s["allapot"], s["uzenet_kod"]), ("hiba", "modellek.manifeszt"))


class MunkaterTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)

    def _regiszter(self, munkaterek):
        (self.k.install / "workspaces.json").write_text(json.dumps({"formatum": 1, "utolso": None, "munkaterek": munkaterek}), encoding="utf-8")

    def test_ervenytelen_regiszter_bejegyzes_javitasa_mentest_keszit_es_csak_a_rosszat_felejti_el(self):
        jo = Path(self.t.name) / "masik"
        jo.mkdir()
        self._regiszter({"b" * 32: {"id": "b" * 32, "vault": str(jo), "nev": "Other"},
                         "c" * 32: {"id": "c" * 32, "vault": str(Path(self.t.name) / "torolt"), "nev": "Gone"}})
        s = _sor(egeszseg.jelentes(self.k.cfg), "munkater")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["javitas"], s["param"]),
                         ("figyelem", "munkater.regiszter_ervenytelen_ut", "regiszter_takarit", {"db": 1}))
        eredeti = (self.k.install / "workspaces.json").read_bytes()
        r = egeszseg.javit(self.k.cfg, None, "regiszter_takarit")
        self.assertEqual(r["param"], {"db": 1})
        reg = json.loads((self.k.install / "workspaces.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(reg["munkaterek"]), ["b" * 32])
        mentes = list(self.k.install.glob("workspaces.json.elozo-*"))
        self.assertEqual(len(mentes), 1)
        self.assertEqual(mentes[0].read_bytes(), eredeti)                  # visszaállítható az eredeti lista
        self.assertTrue(jo.is_dir())
        self.assertTrue((self.k.vault / ".manifold" / "workspace.toml").is_file())
        self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "munkater")["uzenet_kod"], "munkater.ok")

    def test_lecsatolt_kotet_es_a_mostani_munkater_nem_ervenytelen(self):
        self._regiszter({"d" * 32: {"id": "d" * 32, "vault": "/Volumes/ExternalDriveThatIsNotMounted/Notes", "nev": "Ext"}})
        self.assertEqual(_sor(egeszseg.jelentes(self.k.cfg), "munkater")["uzenet_kod"], "munkater.ok")

    def test_hianyzo_workspace_toml_piros_es_nincs_javitas(self):
        (self.k.vault / ".manifold" / "workspace.toml").unlink()
        s = _sor(egeszseg.jelentes(self.k.cfg), "munkater")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["javitas"]), ("hiba", "munkater.workspace_toml", None))
        self.assertIn("workspace.toml", s["nyers"])                     # a doctor szövege csak nyersként, fejlesztőknek

    def test_hianyzo_vault_piros(self):
        shutil.rmtree(self.k.vault)
        s = _sor(egeszseg.jelentes(self.k.cfg), "munkater")
        self.assertEqual((s["allapot"], s["uzenet_kod"]), ("hiba", "munkater.vault_hianyzik"))


class FolyamatokTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.k = _epit(self.t.name)

    def test_futo_core_portja_es_nem_futo_worker(self):
        s = _sor(egeszseg.jelentes(self.k.cfg, SimpleNamespace(port=4321, worker=SimpleNamespace(url=None))), "folyamatok")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["param"]), ("ok", "folyamatok.all", {"port": 4321}))

    def test_futo_worker(self):
        s = _sor(egeszseg.jelentes(self.k.cfg, SimpleNamespace(port=4321, worker=SimpleNamespace(url="http://127.0.0.1:1"))), "folyamatok")
        self.assertEqual(s["uzenet_kod"], "folyamatok.fut")

    def test_beallitott_portol_eltero_port_figyelmeztet(self):
        with mock.patch.dict(os.environ, {"MOS_CORE_PORT": "5000"}):
            s = _sor(egeszseg.jelentes(self.k.cfg, SimpleNamespace(port=4321, worker=SimpleNamespace(url=None))), "folyamatok")
        self.assertEqual((s["allapot"], s["uzenet_kod"]), ("figyelem", "folyamatok.port_eltero"))

    def test_foglalt_beallitott_port_core_nelkul(self):
        import socket
        with socket.socket() as foglal:
            foglal.bind(("127.0.0.1", 0))
            foglal.listen(1)
            port = foglal.getsockname()[1]
            with mock.patch.dict(os.environ, {"MOS_CORE_PORT": str(port)}):
                s = _sor(egeszseg.jelentes(self.k.cfg), "folyamatok")
        self.assertEqual((s["allapot"], s["uzenet_kod"], s["param"]), ("figyelem", "folyamatok.port_foglalt", {"port": port}))


class FeluletParitasTest(unittest.TestCase):
    """A felület szövegtáblái (`app/src/lib/egeszseg/szoveg.ts`) a core kódjait fedik: új ellenőrzés/javítás/részlet-kulcs szöveg nélkül nem maradhat."""
    TS = (REPO / "app" / "src" / "lib" / "egeszseg" / "szoveg.ts").read_text(encoding="utf-8")

    def _kulcsok(self, nev):
        import re
        blokk = re.search(rf"export const {nev}: Record<string, string> = \{{(.*?)\n\}};", self.TS, re.S).group(1)
        return set(re.findall(r"^\s+(\w+): tk\(", blokk, re.M))

    def test_cimek_magyarazatok_es_kezi_lepesek_minden_ellenorzeshez(self):
        kodok = {k for k, _ in egeszseg.ELLENORZESEK}
        for tabla in ("CIM", "TUDJ_MEG", "JAVITAS_KEZI"):
            self.assertEqual(self._kulcsok(tabla), kodok, tabla)
        self.assertEqual(set(egeszseg.CIMEK), kodok)

    def test_javitas_leiras_minden_gepi_javitashoz(self):
        self.assertEqual(self._kulcsok("JAVITAS_LEIRAS"), set(egeszseg.JAVITASOK))
        self.assertEqual(set(egeszseg.JAVITAS_KESZ), set(egeszseg.JAVITASOK))

    def test_minden_reszlet_kulcsnak_van_cimkeje(self):
        import ast
        fa = ast.parse((REPO / "core" / "egeszseg.py").read_text(encoding="utf-8"))
        kulcsok = set()
        for csucs in ast.walk(fa):
            if isinstance(csucs, ast.List):
                for e in csucs.elts:
                    if isinstance(e, ast.Tuple) and len(e.elts) == 2 and isinstance(e.elts[0], ast.Constant) and isinstance(e.elts[0].value, str):
                        kulcsok.add(e.elts[0].value)
        self.assertGreaterEqual(len(kulcsok), 15)
        self.assertEqual(kulcsok - self._kulcsok("RESZLET_CIM"), set())

    def test_a_javitas_ajanlatok_kodjai_csak_az_ismert_javitasok(self):
        import re
        forras = (REPO / "core" / "egeszseg.py").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'javitas="(\w+)"', forras)) - set(egeszseg.JAVITASOK), set())


class VegpontTest(unittest.TestCase):
    def test_a_vegpontok_a_regiszterben_es_a_kezelok_hivjak_a_logikat(self):
        from core import server
        v = server.regiszter_epit().vegpontok()
        for m, u in (("GET", "/api/egeszseg"), ("GET", "/api/egeszseg/diagnosztika"), ("POST", "/api/egeszseg/javitas"), ("GET", "/api/adatvedelem")):
            self.assertIn((m, u, False), v)


if __name__ == "__main__":
    unittest.main()
