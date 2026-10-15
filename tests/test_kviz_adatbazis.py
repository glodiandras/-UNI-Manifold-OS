"""C22a: a kvíz táblái a `tanulas.sqlite` 2-es migrációjában (`core/tanulas_db.py`; `docs/C22-TERV.md` 4. fejezet).
Ideiglenes álgyökéren; a valódi `{var}/tanulas.sqlite`-hoz nem nyúl."""
import sqlite3
import unittest
from unittest import mock

from core import mentes, tanulas_db
from tests.helpers import alg_core, tmpdir


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.ut = tanulas_db.ut(self.cfg)

    def verzio(self) -> int:
        c = sqlite3.connect(self.ut)
        try:
            return c.execute("PRAGMA user_version").fetchone()[0]
        finally:
            c.close()


KIT = ("INSERT INTO kviz_kitoltes (kulcs, kviz, mikor, pont, osszes, szazalek, elemzes) "
       "VALUES (?, 'KVIZ-20261004-203015', '2026-10-04T20:30:15Z', 8, 10, 80, '{}')")


class KvizTablakTest(Alap):
    def test_a_tablak_a_2_es_migraciobol_vannak(self):
        with tanulas_db.iro(self.cfg) as c:
            tablak = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"kviz_kitoltes", "kviz_valasz", "kviz_jeloles"} <= tablak)
        self.assertTrue({"kviz_kitoltes", "kviz_valasz", "kviz_jeloles"} <= set(tanulas_db.ismert_tablak()))
        self.assertGreaterEqual(len(tanulas_db.MIGRACIOK), 2)
        self.assertEqual(self.verzio(), len(tanulas_db.MIGRACIOK))

    def test_a_kitoltes_kulcsa_egyedi(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute(KIT, ("k-1",))
        with self.assertRaises(sqlite3.IntegrityError):
            with tanulas_db.iro(self.cfg) as c:
                c.execute(KIT, ("k-1",))

    def test_ellenorzesek(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute(KIT, ("k-1",))
        for sql in ("INSERT INTO kviz_kitoltes (kulcs, kviz, mikor, mod, pont, osszes, szazalek, elemzes) "
                    "VALUES ('k-2', 'K', 't', 'furcsa', 1, 1, 100, '{}')",
                    "INSERT INTO kviz_valasz (kitoltes, kerdes, helyes, tipp, kategoria) VALUES (1, 'k1', 1, 0, 'jo')",
                    "INSERT INTO kviz_valasz (kitoltes, kerdes, helyes, tipp, kategoria) VALUES (99, 'k1', 1, 0, 'tudja')"):
            with self.assertRaises(sqlite3.IntegrityError, msg=sql):
                with tanulas_db.iro(self.cfg) as c:
                    c.execute(sql)

    def test_a_valasz_kulcsa_kitoltes_es_kerdes(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute(KIT, ("k-1",))
            c.execute("INSERT INTO kviz_valasz (kitoltes, kerdes, helyes, tipp, kategoria) VALUES (1, 'k1', 1, 0, 'tudja')")
        with self.assertRaises(sqlite3.IntegrityError):
            with tanulas_db.iro(self.cfg) as c:
                c.execute("INSERT INTO kviz_valasz (kitoltes, kerdes, helyes, tipp, kategoria) VALUES (1, 'k1', 0, 0, 'hiany')")

    def test_a_jeloles_kulcsa_kviz_es_kerdes(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("INSERT INTO kviz_jeloles (kviz, kerdes, mikor) VALUES ('K', 'k1', 't')")
        with self.assertRaises(sqlite3.IntegrityError):
            with tanulas_db.iro(self.cfg) as c:
                c.execute("INSERT INTO kviz_jeloles (kviz, kerdes, mikor) VALUES ('K', 'k1', 't2')")


class MigralasAHasznaltDbnTest(Alap):
    """A C23a-s (1-es) adatbázis a kártyák történetével: a 2-es migráció előtt mentés, a kártyák épen maradnak."""

    def v1_adatbazis(self):
        self.ut.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.ut)
        c.executescript(f"BEGIN;\n{tanulas_db.MIGRACIOK[0]}\nPRAGMA user_version=1;\nCOMMIT;")
        c.execute("INSERT INTO kartya (azon, letrehozva) VALUES ('c-0001', 't')")
        c.commit()
        c.close()

    def test_a_1_esbol_2_esre_mentessel_es_a_kartyak_megmaradnak(self):
        self.v1_adatbazis()
        with tanulas_db.iro(self.cfg) as c:
            self.assertEqual(c.execute("SELECT azon FROM kartya").fetchall()[0][0], "c-0001")
            c.execute(KIT, ("k-1",))
        self.assertEqual(self.verzio(), len(tanulas_db.MIGRACIOK))
        masolatok = sorted(self.cfg.path("backup").glob(f"{mentes.MIGRACIO_NEV}-tanulas-v1-*.sqlite"))     # A3-06: migrációs másolat
        self.assertEqual(len(masolatok), 1)
        c = sqlite3.connect(f"file:{masolatok[0]}?mode=ro", uri=True)
        try:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 1)         # a migráció ELŐTTI állapot
            self.assertEqual(c.execute("SELECT azon FROM kartya").fetchall(), [("c-0001",)])
        finally:
            c.close()

    def test_a_mentes_hibaja_megallitja_a_2_es_migraciot(self):
        self.v1_adatbazis()
        with mock.patch.object(mentes, "migracio_elott", side_effect=OSError("tele a lemez")):
            with self.assertRaises(sqlite3.DatabaseError):
                with tanulas_db.iro(self.cfg):
                    pass
        self.assertEqual(self.verzio(), 1)
        c = sqlite3.connect(self.ut)
        try:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'kviz_kitoltes'").fetchone()[0], 0)
        finally:
            c.close()

    def test_az_olvaso_a_regi_adatbazist_nem_migralja(self):
        self.v1_adatbazis()
        with tanulas_db.olvaso(self.cfg, min_verzio=2) as c:
            self.assertIsNone(c)                                 # a 2-es táblákat igénylő olvasó nem kap kapcsolatot
        self.assertEqual(self.verzio(), 1)


if __name__ == "__main__":
    unittest.main()
