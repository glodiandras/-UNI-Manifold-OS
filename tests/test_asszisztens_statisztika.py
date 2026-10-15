"""Az Asszisztens elfogadási statisztikája (C30a; CHATKALAUZ C30 5. pont, T064): a `has_asszisztens` tábla a `pos.sqlite`
4-es migrációjában, a tracker egyetlen írójával, a Tracker- és az Asszisztens-kapcsoló alatt, útvonal és szöveg nélkül;
a küszöb a döntésekből; egy gombos törlés. Álgyökéren, a valódi `var/`-hoz nem nyúl."""
import sqlite3
import unittest
from datetime import datetime, timedelta

from core import szemelyes_db, tracker, vezerlo
from core.asszisztens import statisztika
from core.asszisztens.statisztika import Statisztika
from core.utvonalak import HttpError
from tests.helpers import alg_core, tmpdir

MIKOR = datetime(2026, 10, 4, 10, 0)


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.ido = MIKOR
        self.tr = tracker.Tracker(self.cfg, mikor=lambda: self.ido)
        self.st = Statisztika(self.cfg, self.tr)

    def pos(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.tr.ut())
        c.row_factory = sqlite3.Row
        self.addCleanup(c.close)
        return c

    def sorok(self) -> list[tuple]:
        return [tuple(r) for r in self.pos().execute(
            "SELECT nap, fajta, dontes, db FROM has_asszisztens ORDER BY nap, fajta, dontes")]


class MigracioTest(Alap):
    def test_a_4_es_migracio_hozza_a_tablat(self):
        self.assertGreaterEqual(szemelyes_db.VERZIO, 4)
        self.assertIn("has_asszisztens", szemelyes_db.ISMERT_TABLAK)
        self.assertIn("has_asszisztens", tracker._HAS_TABLAK)
        self.assertTrue(self.st.rogzit("emlites", "elfogad")["fogadva"])
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], szemelyes_db.VERZIO)

    def test_nincs_ut_es_szoveg_oszlop(self):
        self.st.rogzit("emlites", "elfogad")
        oszlopok = [r[1] for r in self.pos().execute("PRAGMA table_info(has_asszisztens)")]
        self.assertEqual(oszlopok, ["nap", "fajta", "dontes", "db"])

    def test_3_as_fajlbol_migral_es_az_adat_megmarad(self):
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.tr.ut())
        for sql in szemelyes_db.MIGRACIOK[:3]:
            c.executescript(sql)
        c.execute("PRAGMA user_version = 3")
        c.execute("INSERT INTO has_parancs (nap, parancs, forras, db) VALUES ('2026-10-01', 'a.b', 'paletta', 5)")
        c.commit()
        c.close()
        self.st.rogzit("szokas", "elutasit")
        p = self.pos()
        self.assertEqual(p.execute("PRAGMA user_version").fetchone()[0], szemelyes_db.VERZIO)
        self.assertEqual(p.execute("SELECT db FROM has_parancs").fetchone()[0], 5)

    def test_olvasas_v3_fajlbol_ures_es_nem_migral(self):
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.tr.ut())
        for sql in szemelyes_db.MIGRACIOK[:3]:
            c.executescript(sql)
        c.execute("PRAGMA user_version = 3")
        c.commit()
        c.close()
        o = self.st.osszesit()
        self.assertEqual(o["fajtak"]["emlites"]["db"], 0)
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], 3)


class KapcsoloTest(Alap):
    def test_tracker_kikapcsolva_nem_ir_es_nem_hoz_letre_fajlt(self):
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        r = self.st.rogzit("emlites", "elfogad")
        self.assertEqual((r["fogadva"], r["ok"]), (False, "tracker_ki"))
        self.assertFalse(self.tr.ut().exists())

    def test_asszisztens_kikapcsolva_nem_ir_es_nem_hoz_letre_fajlt(self):
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False})
        r = self.st.rogzit("emlites", "elfogad")
        self.assertEqual((r["fogadva"], r["ok"]), (False, "asszisztens_ki"))
        self.assertFalse(self.tr.ut().exists())

    def test_kikapcsolt_kapcsolonal_az_olvasas_sem_hoz_letre_fajlt(self):
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        self.assertEqual(self.st.osszesit()["kapcsolo"], {"asszisztens": True, "tracker": False})
        self.assertFalse(self.tr.ut().exists())


class RogzitTest(Alap):
    def test_fehertlista(self):
        for fajta, dontes in (("ismeretlen", "elfogad"), ("emlites", "talan"), ("", "elfogad"), (None, None), (3, "x")):
            with self.assertRaises(HttpError) as e:
                self.st.rogzit(fajta, dontes)
            self.assertEqual(e.exception.code, 400)
        self.assertFalse(self.tr.ut().exists())

    def test_napi_szamlalo_es_fajtankent(self):
        for _ in range(3):
            self.st.rogzit("emlites", "elfogad")
        self.st.rogzit("emlites", "elutasit")
        self.st.rogzit("szokas", "elutasit")
        self.ido = MIKOR + timedelta(days=1)
        self.st.rogzit("emlites", "elfogad")
        self.assertEqual(self.sorok(), [("2026-10-04", "emlites", "elfogad", 3), ("2026-10-04", "emlites", "elutasit", 1),
                                        ("2026-10-04", "szokas", "elutasit", 1), ("2026-10-05", "emlites", "elfogad", 1)])

    def test_osszesites_arany_es_ablak(self):
        self.st.rogzit("emlites", "elfogad")
        self.st.rogzit("emlites", "elutasit")
        self.st.rogzit("emlites", "elutasit")
        self.ido = MIKOR + timedelta(days=40)                    # az ablakon (30 nap) kívül
        o = self.st.osszesit()
        self.assertEqual(o["fajtak"]["emlites"], {"elfogad": 0, "elutasit": 0, "db": 0, "arany": None,
                                                  "kuszob": {"szint": "alap", "szorzo": 1.0}, "hasonlosag_kuszob": 0.55})
        self.assertNotIn("hasonlosag_kuszob", o["fajtak"]["szokas"])      # csak a linkjavaslat hasonlósági küszöbe
        self.ido = MIKOR + timedelta(days=5)
        o = self.st.osszesit()
        self.assertEqual((o["fajtak"]["emlites"]["elfogad"], o["fajtak"]["emlites"]["elutasit"]), (1, 2))
        self.assertAlmostEqual(o["fajtak"]["emlites"]["arany"], 1 / 3, places=3)
        self.assertEqual(o["ablak_nap"], 30)


class KuszobTest(Alap):
    def dontesek(self, fajta, elfogad, elutasit):
        for _ in range(elfogad):
            self.st.rogzit(fajta, "elfogad")
        for _ in range(elutasit):
            self.st.rogzit(fajta, "elutasit")
        return self.st.kuszob(fajta)

    def test_kevés_dontesbol_nincs_kovetkeztetes(self):
        self.assertEqual(self.dontesek("emlites", 0, 9), {"szint": "alap", "szorzo": 1.0})

    def test_alacsony_elfogadas_szigorubb(self):
        self.assertEqual(self.dontesek("emlites", 1, 14), {"szint": "szigoru", "szorzo": 1.5})

    def test_elegendo_elfogadas_alap(self):
        self.assertEqual(self.dontesek("emlites", 5, 5), {"szint": "alap", "szorzo": 1.0})

    def test_nema_ha_szinte_mindent_elutasit(self):
        k = self.dontesek("szokas", 0, 25)
        self.assertEqual(k["szint"], "nema")

    def test_a_nema_az_ablak_kifutasaval_magatol_enged(self):
        self.dontesek("szokas", 0, 25)
        self.ido = MIKOR + timedelta(days=31)
        self.assertEqual(self.st.kuszob("szokas")["szint"], "alap")

    def test_fajtak_fuggetlenek(self):
        self.dontesek("szokas", 0, 25)
        self.assertEqual(self.st.kuszob("emlites")["szint"], "alap")

    def test_a_beallitasbol_jon(self):
        self.cfg.data.setdefault("asszisztens", {}).update({"kuszob_min_db": 3, "kuszob_szigoru_szorzo": 2.0})
        self.assertEqual(self.dontesek("emlites", 0, 3), {"szint": "szigoru", "szorzo": 2.0})

    def test_kikapcsolt_tracker_nem_ad_kuszobot_az_adatbol(self):
        self.dontesek("szokas", 0, 25)
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        self.assertEqual(self.st.kuszob("szokas"), {"szint": "alap", "szorzo": 1.0})

    # -- C30b (K205 (b)): a hasonlósági küszöb a küszöb szorzóján át

    def hasonlosag(self):
        return self.st.osszesit()["fajtak"]["emlites"]["hasonlosag_kuszob"]

    def test_hasonlosag_kuszob_alap(self):
        self.assertEqual(self.hasonlosag(), 0.55)

    def test_hasonlosag_kuszob_a_szorzoval_nő(self):
        self.dontesek("emlites", 1, 14)                              # szigorú, ×1,5
        self.assertEqual(self.hasonlosag(), 0.825)

    def test_hasonlosag_kuszob_felso_plafonja(self):
        self.cfg.data.setdefault("asszisztens", {}).update({"emlites_hasonlosag_kuszob": 0.8, "kuszob_szigoru_szorzo": 2.0})
        self.dontesek("emlites", 1, 14)
        self.assertEqual(self.hasonlosag(), 0.95)

    def test_nema_nincs_hasonlosag_kuszob(self):
        self.dontesek("emlites", 0, 25)
        self.assertIsNone(self.hasonlosag())

    def test_hasonlosag_kuszob_a_beallitasbol_jon_es_kikapcsolt_trackernel_az_alap(self):
        self.cfg.data.setdefault("asszisztens", {})["emlites_hasonlosag_kuszob"] = 0.4
        self.assertEqual(self.hasonlosag(), 0.4)
        self.dontesek("emlites", 1, 14)
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})            # a tracker adatát nem használjuk: az alap
        self.assertEqual(self.hasonlosag(), 0.4)


class TorlesTest(Alap):
    def test_torles_csak_az_asszisztens_tablat_viszi(self):
        self.tr.fogad({"parancsok": [{"id": "a.b", "forras": "paletta"}]})
        self.st.rogzit("emlites", "elfogad")
        r = self.st.torol()
        self.assertEqual(r["torolt"], 1)
        self.assertTrue(r["tisztitva"])
        self.assertEqual(self.sorok(), [])
        self.assertEqual(self.pos().execute("SELECT count(*) FROM has_parancs").fetchone()[0], 1)

    def test_torles_fajl_nelkul_nem_hoz_letre_semmit(self):
        self.assertEqual(self.st.torol(), {"torolt": 0, "tisztitva": True})
        self.assertFalse(self.tr.ut().exists())

    def test_a_tracker_adat_torlese_is_viszi_a_tablat(self):
        self.st.rogzit("emlites", "elfogad")
        self.tr.torles("hasznalat")
        self.assertEqual(self.sorok(), [])

    def test_torles_utan_nincs_nyom_a_fajlban(self):
        self.st.rogzit("emlites", "elutasit")
        self.st.torol()
        nyers = b"".join(p.read_bytes() for p in self.tr.ut().parent.glob("pos.sqlite*"))
        self.assertNotIn(b"elutasit", nyers)


class ForraskodTest(unittest.TestCase):
    def test_nincs_sajat_adatbazis_kapcsolat(self):
        """A statisztika a tracker egyetlen írójával (`Tracker._iro`) ír; saját `sqlite3.connect` nincs."""
        import inspect
        forras = inspect.getsource(statisztika)
        self.assertNotIn("sqlite3.connect", forras)
        self.assertNotIn("DELETE FROM has_parancs", forras)


if __name__ == "__main__":
    unittest.main()
