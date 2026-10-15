"""Router-döntések, kalibrációs tábla, hőfigyelés (álmodell nélkül is: ezek tiszta döntések)."""
import sqlite3
from pathlib import Path
import unittest

from core.modell import beallitas as B
from core.modell.ho import Ho
from core.modell.kalibracio import Tabla
from core.modell.router import Router, RoutingHiba
from tests.helpers import alg_core, tmpdir


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)
        self.b = B.betolt(self.cfg, {})
        self.t = Tabla(self.b.router_db)
        self.addCleanup(self.t.close)
        self.r = Router(self.b, self.t)


class KalibracioTest(Alap):
    def test_uresen_indul_sema_es_naplo(self):
        self.assertEqual(self.t.tabla(), [])
        db = sqlite3.connect(self.b.router_db)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
        self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.t.rogzit("szoveg", "qwen35_4b", 0.7, "C18-v1")
        self.t.rogzit("szoveg", "qwen35_4b", 0.8, "C18-v2", kalibralt=True)
        self.assertEqual([(r["pontszam"], r["aranyhalmaz_verzio"], r["kalibralt"]) for r in self.t.tabla("szoveg")],
                         [(0.8, "C18-v2", 1)])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM kalibracio_naplo").fetchone()[0], 2)
        db.close()

    def test_ervenytelen_meres_csak_a_naploba(self):
        """C18.1: az érvénytelen mérés nem írja felül a kalibrációs sort, és nem kaphat kalibrált jelet."""
        self.t.rogzit("szoveg", "qwen35_4b", 0.7, "v1", kalibralt=True)
        sor = self.t.rogzit("szoveg", "qwen35_4b", 0.1, "v1", megjegyzes="érvénytelen", ervenyes=False)
        self.assertEqual(sor["ervenyes"], 0)
        self.assertEqual([(r["pontszam"], r["ervenyes"]) for r in self.t.tabla("szoveg")], [(0.7, 1)])
        with self.assertRaisesRegex(ValueError, "kalibrált"):
            self.t.rogzit("szoveg", "qwen35_4b", 0.9, "v1", kalibralt=True, ervenyes=False)
        db = sqlite3.connect(self.b.router_db)
        self.assertEqual(db.execute("SELECT pontszam, ervenyes FROM kalibracio_naplo ORDER BY sor").fetchall(),
                         [(0.7, 1), (0.1, 0)])
        db.close()
        self.assertEqual(Router(self.b, self.t).valaszt("szoveg", 5.0).modell.nev, "qwen35_4b")

    def test_rogzites_jel_nelkul_megtartja_a_kalibralt_jelet(self):
        """Lelet 3: a `kalibralt=None` (alap) nem veszi le a jóváhagyott jelet; a `False` kifejezetten leveszi; a naplósor a
        tényleges állapotot rögzíti; más aranyverzión vagy érvénytelen mérésnél a jel nem öröklődik."""
        self.t.rogzit("szoveg", "qwen35_4b", 0.7, "v1", kalibralt=True)
        sor = self.t.rogzit("szoveg", "qwen35_4b", 0.75, "v1")                                  # megtart
        self.assertEqual((sor["kalibralt"], sor["pontszam"]), (1, 0.75))
        self.assertIn("megmaradt", sor["megjegyzes"])
        self.assertEqual([(r["pontszam"], r["kalibralt"]) for r in self.t.kalibralt_sorrend("szoveg")], [(0.75, 1)])
        sor = self.t.rogzit("szoveg", "qwen35_4b", 0.9, "v2")                                   # más verzió: nem örököl
        self.assertEqual(sor["kalibralt"], 0)
        self.assertEqual(self.t.kalibralt_sorrend("szoveg"), [])
        self.t.rogzit("szoveg", "qwen35_4b", 0.8, "v2", kalibralt=True)                         # felvesz
        self.assertEqual(self.t.rogzit("szoveg", "qwen35_4b", 0.1, "v2", ervenyes=False)["kalibralt"], 0)   # érvénytelen
        self.assertEqual([r["kalibralt"] for r in self.t.tabla("szoveg")], [1])                 # a sor érintetlen
        sor = self.t.rogzit("szoveg", "qwen35_4b", 0.82, "v2", kalibralt=False)                 # kifejezett levétel
        self.assertEqual(sor["kalibralt"], 0)
        self.assertEqual(self.t.kalibralt_sorrend("szoveg"), [])
        db = sqlite3.connect(self.b.router_db)
        self.assertEqual([r[0] for r in db.execute("SELECT kalibralt FROM kalibracio_naplo ORDER BY sor")], [1, 1, 0, 1, 0, 0])
        db.close()
        sor = self.t.rogzit("szoveg", "qwen35_2b", 0.5, "v1-vazlat")                            # vázlaton soha nem kalibrált
        self.assertEqual(sor["kalibralt"], 0)

    def test_2_es_migracio_a_regi_sorokat_elavultnak_jeloli(self):
        from core.modell import kalibracio as K
        ut = self.b.router_db.parent / "regi.sqlite"
        db = sqlite3.connect(ut)
        db.executescript("BEGIN;" + K._SEMA + "PRAGMA user_version=1; COMMIT;")
        db.execute("INSERT INTO kalibracio VALUES ('szoveg','qwen35_4b',0.5,'2026-10-03','v1-vazlat',1,'mos eval, n=40')")
        db.execute("INSERT INTO kalibracio_naplo (feladat, modell, pontszam, datum, aranyhalmaz_verzio, kalibralt, "
                   "megjegyzes) VALUES ('szoveg','qwen35_4b',0.5,'2026-10-03','v1-vazlat',1,'mos eval, n=40')")
        db.commit()
        db.close()
        t = K.Tabla(ut)
        self.addCleanup(t.close)
        sor = t.tabla("szoveg")[0]
        self.assertEqual((sor["ervenyes"], sor["megjegyzes"]), (0, "elavult (C18.1): mos eval, n=40"))
        self.assertEqual(t.kalibralt_sorrend("szoveg"), [])                 # a régi kalibrált sor sem routol
        db = sqlite3.connect(ut)
        self.assertEqual(db.execute("SELECT ervenyes, megjegyzes FROM kalibracio_naplo").fetchall(),
                         [(0, "elavult (C18.1): mos eval, n=40")])
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
        db.close()

    def test_3_as_migracio_snapshot_es_elotte_masolat(self):
        """C19 (T141): a 3-as migráció a `snapshot` oszlopot adja; a meglévő adatbázis migrációja előtt az `elotte` (a 33.
        döntés állapotmásolata) fut, és ha hibát dob, a migráció elmarad. A `megnyit(cfg)` a `{backup}` alá másol."""
        from core.modell import kalibracio as K
        ut = self.b.router_db.parent / "v2.sqlite"
        db = sqlite3.connect(ut)
        db.executescript("BEGIN;" + K._SEMA + "PRAGMA user_version=1; COMMIT;")
        db.executescript("BEGIN;" + K._MIGRACIO_2 + "PRAGMA user_version=2; COMMIT;")
        db.close()
        with self.assertRaises(OSError):
            K.Tabla(ut, elotte=lambda v: (_ for _ in ()).throw(OSError("nincs hely")))
        db = sqlite3.connect(ut)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)        # elmaradt
        db.close()
        hivas = []
        t = K.Tabla(ut, elotte=hivas.append)
        self.addCleanup(t.close)
        self.assertEqual(hivas, [2])
        sor = t.rogzit("szoveg", "qwen35_4b", 0.5, "v1", snapshot="a" * 40)
        self.assertEqual((sor["snapshot"], t.tabla("szoveg")[0]["snapshot"]), ("a" * 40, "a" * 40))
        t2 = K.Tabla(ut, elotte=hivas.append)                                      # már 3-as: nincs újabb másolat
        t2.close()
        self.assertEqual(hivas, [2])
        self.t.close()
        for vege in ("", "-wal", "-shm"):
            Path(str(self.b.router_db) + vege).unlink(missing_ok=True)
        db = sqlite3.connect(self.b.router_db)
        db.executescript("BEGIN;" + K._SEMA + "PRAGMA user_version=1; COMMIT;")
        db.executescript("BEGIN;" + K._MIGRACIO_2 + "PRAGMA user_version=2; COMMIT;")
        db.close()
        t3 = K.megnyit(self.cfg)
        t3.close()
        self.assertTrue(list(self.cfg.path("backup").glob("mos-migracio-router-v2-*.sqlite")))

    def test_verzio_kotelezo(self):
        with self.assertRaises(ValueError):
            self.t.rogzit("szoveg", "qwen35_4b", 0.7, "")


class RouterTest(Alap):
    def test_ures_tabla_hiba(self):
        with self.assertRaisesRegex(RoutingHiba, "nincs kalibrált modell"):
            self.r.valaszt("szoveg", 5.0)

    def test_nem_kalibralt_kimarad(self):
        self.t.rogzit("szoveg", "qwen35_9b", 0.9, "v1", kalibralt=False)
        self.t.rogzit("szoveg", "qwen35_4b", 0.6, "v1", kalibralt=True)
        self.assertEqual(self.r.valaszt("szoveg", 9.0).modell.nev, "qwen35_4b")

    def test_a_legjobb_keretbe_fero(self):
        self.t.rogzit("szoveg", "gemma4_12b", 0.9, "v1", kalibralt=True)
        self.t.rogzit("szoveg", "qwen35_4b", 0.6, "v1", kalibralt=True)
        self.t.rogzit("szoveg", "qwen35_2b", 0.4, "v1", kalibralt=True)
        self.assertEqual(self.r.valaszt("szoveg", 9.0).modell.nev, "gemma4_12b")
        d = self.r.valaszt("szoveg", 5.0)
        self.assertEqual(d.modell.nev, "qwen35_4b")                 # a gyengébbel fut (tavolra_var: nincs)
        self.assertFalse(d.var_tavolra)

    def test_tavolra_var_ha_a_feladat_igy_kéri(self):
        self.t.rogzit("ocr_kezi", "qwen35_9b", 0.9, "v1", kalibralt=True)
        self.t.rogzit("ocr_kezi", "qwen3_vl_4b", 0.5, "v1", kalibralt=True)
        d = self.r.valaszt("ocr_kezi", 5.0)                          # os.toml: [router.feladat.ocr_kezi] tavolra_var
        self.assertTrue(d.var_tavolra)
        self.assertIsNone(d.modell)
        self.assertEqual(self.r.valaszt("ocr_kezi", 9.0).modell.nev, "qwen35_9b")

    def test_csak_tavolba_fero_var_semmibe_fero_hiba(self):
        self.t.rogzit("matek", "qwen35_9b", 0.9, "v1", kalibralt=True)
        self.assertTrue(self.r.valaszt("matek", 5.0).var_tavolra)
        kicsi = Router(B.betolt(self.cfg, {"MANIFOLD_MODELL_KERET_GB": "2"}), self.t)   # a felülírás a távolt is köti
        with self.assertRaisesRegex(RoutingHiba, "egyik"):
            kicsi.valaszt("matek", 2.0)

    def test_masodik_velemeny_masik_csaladbol(self):
        """C24b: `kizart_csalad` — a kizárt család modelljei kimaradnak; ha más nem marad: `NincsMasikCsalad` (a RoutingHiba
        alosztálya, a worker 409-cel adja)."""
        from core.modell.router import NincsMasikCsalad
        self.t.rogzit("matek_cas", "qwen35_9b", 0.9, "v1", kalibralt=True)
        self.t.rogzit("matek_cas", "qwen35_4b", 0.8, "v1", kalibralt=True)
        self.assertEqual(self.r.valaszt("matek_cas", 9.0).modell.nev, "qwen35_9b")
        with self.assertRaises(NincsMasikCsalad):
            self.r.valaszt("matek_cas", 9.0, kizart_csalad="qwen")
        self.t.rogzit("matek_cas", "ministral3_8b_reasoning", 0.76, "v1", kalibralt=True)
        d = self.r.valaszt("matek_cas", 9.0, kizart_csalad="qwen")
        self.assertEqual(d.modell.nev, "ministral3_8b_reasoning")
        self.assertEqual(self.r.valaszt("matek_cas", 9.0, kizart_csalad="mistral").modell.nev, "qwen35_9b")
        self.assertTrue(self.r.valaszt("matek_cas", 5.0, kizart_csalad="qwen").var_tavolra)     # 7,9 GB: csak távol

    def test_minden_szoveges_modellnek_van_csaladja(self):
        """C24b: a `csalad` kötelező minden `szoveg`-képességű modellnél (a második vélemény ebből zár ki)."""
        hianyzik = [m.nev for m in self.b.modellek.values() if "szoveg" in m.kepessegek and not m.csalad]
        self.assertEqual(hianyzik, [])
        self.assertEqual(self.b.modell("qwen35_9b").csalad, self.b.modell("qwen35_4b").csalad)
        self.assertNotEqual(self.b.modell("qwen35_9b").csalad, self.b.modell("ministral3_8b_reasoning").csalad)

    def test_regiszterbol_kikerult_modell_nem_fut(self):
        self.t.rogzit("szoveg", "nincs_ilyen", 0.99, "v1", kalibralt=True)
        self.t.rogzit("szoveg", "qwen35_2b", 0.3, "v1", kalibralt=True)
        self.assertEqual(self.r.valaszt("szoveg", 5.0).modell.nev, "qwen35_2b")


class HoTest(Alap):
    def ho(self, **kw):
        c = {**self.b.ho, "alap_minta": 3, "ablak": 3, "kuszob": 0.7, **kw}
        return Ho(c, self.t)

    def test_alapszint_es_tartos_eses(self):
        h = self.ho()
        for tps in (50, 52, 48):
            self.assertFalse(h.minta("m", tps, 64))
        self.assertEqual(self.t.hoalap("m"), 50)
        self.assertFalse(h.minta("m", 30, 64))                       # egy lassú minta nem tartós
        self.assertFalse(h.minta("m", 49, 64))
        self.assertEqual(h.szunetek, 0)
        self.assertTrue(h.minta("m", 31, 64))                        # az ablak mediánja 31 < 0,7 × 50
        self.assertEqual(h.szunetek, 1)
        self.assertFalse(h.minta("m", 31, 64))                       # a szünet után az ablak újraindul

    def test_az_alapszint_a_kontextus_meret_szerint_kulon_all(self):
        """C19: a rövid kérések gyors alapszintje a hosszú kontextusú (pl. kétképes) kérések lassabb, de egyenletes sebességét
        nem minősíti hőesésnek; azonos méretosztályon belül a tartós esés továbbra is szünetet ad."""
        h = self.ho()
        for tps in (200, 210, 205):
            h.minta("glm", tps, 64, prompt_tokenek=300)                 # rövid képlet-kivágás
        for tps in (90, 88, 86, 85, 87, 89):
            self.assertFalse(h.minta("glm", tps, 400, prompt_tokenek=2500))   # füzetoldal: más osztály, nincs szünet
        self.assertEqual(h.szunetek, 0)
        self.assertEqual((self.t.hoalap("glm@9"), self.t.hoalap("glm@12")), (205, 88))
        self.assertFalse(h.minta("glm", 50, 400, prompt_tokenek=2600))
        self.assertTrue(h.minta("glm", 50, 400, prompt_tokenek=2600))    # ugyanabban az osztályban a medián 50 < 0,7 × 88
        self.assertEqual(Ho.kulcs("m"), "m")

    def test_rovid_valasz_nem_minta_es_kikapcsolhato(self):
        h = self.ho()
        for _ in range(10):
            self.assertFalse(h.minta("m", 1.0, 5))
        self.assertIsNone(self.t.hoalap("m"))
        h = self.ho(bekapcsolva=False)
        for _ in range(10):
            self.assertFalse(h.minta("m", 1.0, 64))

    def test_az_alapszint_felfele_kovet(self):
        h = self.ho()
        for tps in (20, 20, 20, 40, 40, 40):
            h.minta("m", tps, 64)
        self.assertEqual(self.t.hoalap("m"), 40)


if __name__ == "__main__":
    unittest.main()
