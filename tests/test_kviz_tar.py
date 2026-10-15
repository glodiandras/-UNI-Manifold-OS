"""C22a: a kvíz eredményei a `tanulas.sqlite`-ban (`modulok/kviz/tar.py`) — idempotens mentés, előzmények, jelölések, a
kvízmodell mérése. Ideiglenes álgyökéren; a valódi `{var}/tanulas.sqlite`-hoz nem nyúl."""
import dataclasses
import json
import sqlite3
import unittest
from datetime import datetime, timezone

from core import tanulas_db
from modulok.kviz import ertekeles as E
from modulok.kviz import tar
from tests.helpers import alg_core, tmpdir
from tests.test_kviz_ertekeles import kviz, rossz

MIKOR = datetime(2026, 10, 4, 18, 30, 15, 999, tzinfo=timezone.utc)


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.k = kviz()

    def valaszok(self, rossz_k2=True):
        k = self.k
        return [{"kerdes": "k1", "valasz": k.kerdesek[0].helyes, "tipp": False, "ms": 1200},
                {"kerdes": "k2", "valasz": rossz(k, 1) if rossz_k2 else k.kerdesek[1].helyes, "tipp": False},
                {"kerdes": "k3", "valasz": k.kerdesek[2].helyes, "tipp": True}]

    def ment(self, kulcs="u-1", mikor=MIKOR, mod="teljes", valaszok=None, jelolesek=frozenset()):
        e = E.kitoltes_ertekel(self.k, valaszok or self.valaszok(), mod, tar.kitoltesek(self.cfg, self.k.azon), jelolesek)
        return tar.kitoltes_ment(self.cfg, kulcs, self.k, self.k.forras + ".md", e, mikor)


class MentesTest(Alap):
    def test_mentes_es_visszaolvasas(self):
        e, uj = self.ment()
        self.assertTrue(uj)
        ki = tar.kitoltesek(self.cfg, self.k.azon)
        self.assertEqual(len(ki), 1)
        self.assertEqual((ki[0]["mod"], ki[0]["mikor"]), ("teljes", "2026-10-04T18:30:15+00:00"))      # másodpercre vágva, UTC
        self.assertEqual(ki[0]["osszegzes"], e["osszegzes"])
        self.assertEqual([(x["kerdes"], x["helyes"]) for x in ki[0]["eredmenyek"]], [("k1", True), ("k2", False), ("k3", True)])
        with tanulas_db.olvaso(self.cfg) as c:
            sor = c.execute("SELECT * FROM kviz_kitoltes").fetchone()
            self.assertEqual((sor["kviz"], sor["forras"], sor["modell"], sor["pont"], sor["osszes"], sor["szazalek"]),
                             (self.k.azon, self.k.forras, "org/kis", 2, 3, 67))
            self.assertEqual(sor["kviz_ut"], self.k.forras + ".md")
            self.assertEqual(len(sor["szoveg_hash"]), 64)
            v = c.execute("SELECT kerdes, valasz, helyes, tipp, kategoria, ms, szakasz FROM kviz_valasz ORDER BY kerdes").fetchall()
            self.assertEqual([tuple(x) for x in v], [("k1", 1, 1, 0, "tudja", 1200, "Elméleti alapok"),
                                                    ("k2", rossz(self.k, 1), 0, 0, "tevkepzet", None, "Szorzattá alakítás"),
                                                    ("k3", 0, 1, 1, "szerencses", None, "Szorzattá alakítás")])
            self.assertEqual(json.loads(sor["elemzes"])["osszegzes"], e["osszegzes"])

    def test_ugyanaz_a_kulcs_nem_duplikal(self):
        e1, uj1 = self.ment("u-1")
        e2, uj2 = self.ment("u-1", valaszok=[{"kerdes": "k1", "valasz": 0}])          # az újraküldés más tartalommal is a régit adja
        self.assertEqual((uj1, uj2), (True, False))
        self.assertEqual(e1, e2)
        self.assertEqual(len(tar.kitoltesek(self.cfg, self.k.azon)), 1)
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kviz_valasz").fetchone()[0], 3)
        self.assertEqual(tar.kitoltes_kulccsal(self.cfg, "u-1", self.k.azon), e1)
        self.assertIsNone(tar.kitoltes_kulccsal(self.cfg, "nincs", self.k.azon))
        self.assertIsNone(tar.kitoltes_kulccsal(self.cfg, "u-1", "KVIZ-20261004-203015-aaaaaa"))     # A3-04: másik kvíz kulcsa

    def test_masik_kviz_kulcsa_foglalt(self):
        self.ment("u-1")
        masik = dataclasses.replace(self.k, azon="KVIZ-20261004-203015-aaaaaa")
        e = E.kitoltes_ertekel(masik, self.valaszok())
        with self.assertRaises(tar.KulcsFoglalt):
            tar.kitoltes_ment(self.cfg, "u-1", masik, "ATTCHMNTS - quizes/M.md", e)
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kviz_kitoltes").fetchone()[0], 1)

    def test_az_elozmeny_idorendben_a_trendhez(self):
        self.ment("u-1", datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc))
        e2, _ = self.ment("u-2", datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc), valaszok=self.valaszok(rossz_k2=False))
        self.assertEqual(e2["trend"]["elozo_szazalek"], 67)
        self.assertEqual(e2["trend"]["javult"], 1)                                      # a k2 most jó, az előzőben rossz volt
        ki = tar.kitoltesek(self.cfg, self.k.azon)
        self.assertEqual([x["osszegzes"]["szazalek"] for x in ki], [67, 100])
        self.assertEqual(tar.utolso(self.cfg, self.k.azon)["osszegzes"]["szazalek"], 100)

    def test_kulonbozo_kvizek_nem_keverednek(self):
        self.ment()
        self.assertEqual(tar.kitoltesek(self.cfg, "KVIZ-20250101-000000"), [])
        self.assertIsNone(tar.utolso(self.cfg, "KVIZ-20250101-000000"))

    def test_olvasas_nem_hoz_letre_fajlt(self):
        self.assertEqual(tar.kitoltesek(self.cfg, self.k.azon), [])
        self.assertEqual(tar.jelolesek(self.cfg, self.k.azon), {})
        self.assertIsNone(tar.kitoltes_kulccsal(self.cfg, "u-1", self.k.azon))
        self.assertEqual(tar.modell_statisztika(self.cfg), {})
        self.assertFalse(tanulas_db.ut(self.cfg).exists())

    def test_a_regi_1_es_adatbazison_az_olvasas_ures(self):
        ut = tanulas_db.ut(self.cfg)
        ut.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(ut)
        c.executescript(f"BEGIN;\n{tanulas_db.MIGRACIOK[0]}\nPRAGMA user_version=1;\nCOMMIT;")
        c.close()
        self.assertEqual(tar.kitoltesek(self.cfg, self.k.azon), [])
        c = sqlite3.connect(ut)
        self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 1)             # az olvasó nem migrált
        c.close()


class JelolesTest(Alap):
    def test_jeloles_be_ki_es_nem_szamit_a_pontba(self):
        tar.jelol(self.cfg, self.k.azon, "k3", True, "félreérthető")
        j = tar.jelolesek(self.cfg, self.k.azon)
        self.assertEqual(set(j), {"k3"})
        self.assertEqual(j["k3"]["megjegyzes"], "félreérthető")
        e, _ = self.ment(jelolesek=set(j))
        self.assertEqual((e["osszegzes"]["pont"], e["osszegzes"]["osszes"]), (1, 2))
        tar.jelol(self.cfg, self.k.azon, "k3", False)
        self.assertEqual(tar.jelolesek(self.cfg, self.k.azon), {})

    def test_ismetelt_jeloles_felulirja_a_megjegyzest(self):
        tar.jelol(self.cfg, self.k.azon, "k1", True, "a")
        tar.jelol(self.cfg, self.k.azon, "k1", True, "b")
        self.assertEqual(tar.jelolesek(self.cfg, self.k.azon)["k1"]["megjegyzes"], "b")

    def test_a_megjegyzes_hossza_korlatos(self):
        tar.jelol(self.cfg, self.k.azon, "k1", True, "x" * 5000)
        self.assertEqual(len(tar.jelolesek(self.cfg, self.k.azon)["k1"]["megjegyzes"]), 500)


class ModellStatisztikaTest(Alap):
    def test_a_jelolesek_a_modell_pontossagat_merik(self):
        self.ment()
        tar.jelol(self.cfg, self.k.azon, "k3", True)
        st = tar.modell_statisztika(self.cfg)["org/kis"]
        self.assertEqual((st["kviz"], st["kitoltes"], st["megvalaszolt"], st["hibasnak_jelolt"]), (1, 1, 3, 1))
        self.assertEqual(st["pontossag_jelolesek_szerint"], round(1 - 1 / 3, 3))

    def test_jelolt_de_meg_nem_valaszolt_kerdes_nem_szamit(self):
        self.ment()
        tar.jelol(self.cfg, self.k.azon, "k9", True)
        self.assertEqual(tar.modell_statisztika(self.cfg)["org/kis"]["hibasnak_jelolt"], 0)


if __name__ == "__main__":
    unittest.main()
