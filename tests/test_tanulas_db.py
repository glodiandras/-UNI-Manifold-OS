"""C23a: a tanulási adatbázis közös rétege (`core/tanulas_db.py`) — migráció, WAL, előre-kompatibilitás, a
migráció előtti mentés (33. döntés). Ideiglenes álgyökéren; a valódi `{var}/tanulas.sqlite`-hoz nem nyúl."""
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


class MigralTest(Alap):
    def test_ut_a_konfigbol(self):
        self.assertEqual(self.ut, self.cfg.path("var") / "tanulas.sqlite")

    def test_letrehoz_migral_wal(self):
        with tanulas_db.iro(self.cfg) as c:
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            tablak = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue(set(tanulas_db.ismert_tablak()) <= tablak)
        self.assertEqual(self.verzio(), len(tanulas_db.MIGRACIOK))

    def test_ismetelt_megnyitas_nem_migral_ujra(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("INSERT INTO kartya (azon, letrehozva) VALUES ('c-0001', 't')")
        with tanulas_db.iro(self.cfg) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kartya").fetchone()[0], 1)

    def test_kivetelnel_visszagorget(self):
        with self.assertRaises(RuntimeError):
            with tanulas_db.iro(self.cfg) as c:
                c.execute("INSERT INTO kartya (azon, letrehozva) VALUES ('c-0001', 't')")
                raise RuntimeError("hiba")
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM kartya").fetchone()[0], 0)

    def test_jegy_ellenorzes(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with tanulas_db.iro(self.cfg) as c:
                c.execute("INSERT INTO valasz (kartya, mikor, jegy) VALUES ('c-0001', 't', 5)")

    def test_ujabb_sema_ismert_tablakkal_megy(self):
        with tanulas_db.iro(self.cfg):
            pass
        c = sqlite3.connect(self.ut)
        c.execute("PRAGMA user_version = 9")
        c.commit()
        c.close()
        with tanulas_db.iro(self.cfg) as c:                      # nem dob, nem nyúl a sémához
            c.execute("INSERT INTO kartya (azon, letrehozva) VALUES ('c-0002', 't')")
        self.assertEqual(self.verzio(), 9)

    def test_ujabb_sema_hianyzo_tablaval_hiba(self):
        c = sqlite3.connect(self.ut)
        c.execute("CREATE TABLE mas (x)")
        c.execute("PRAGMA user_version = 9")
        c.commit()
        c.close()
        with self.assertRaises(sqlite3.DatabaseError):
            with tanulas_db.iro(self.cfg):
                pass


class OlvasoTest(Alap):
    def test_nincs_fajl_nem_hoz_letre(self):
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertIsNone(c)
        self.assertFalse(self.ut.exists())

    def test_csak_olvas(self):
        with tanulas_db.iro(self.cfg):
            pass
        with tanulas_db.olvaso(self.cfg) as c:
            with self.assertRaises(sqlite3.OperationalError):
                c.execute("INSERT INTO kartya (azon, letrehozva) VALUES ('x', 't')")


class MigracioElottiMentesTest(Alap):
    """33. döntés (A3-06): egy használt (≥ 1) adatbázis sémaváltása előtt a `mentes.migracio_elott` másolata; a hibája megállítja."""
    UJ = tanulas_db.MIGRACIOK + ["CREATE TABLE kviz_proba (x TEXT);"]

    def test_uj_fajlnal_nincs_mentes(self):
        with mock.patch.object(mentes, "migracio_elott") as m, mock.patch.object(mentes, "allapot_masolat") as a:
            with tanulas_db.iro(self.cfg):
                pass
        m.assert_not_called()
        a.assert_not_called()

    def test_hasznalt_db_migracioja_elott_migracios_masolat(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("INSERT INTO kartya (azon, letrehozva) VALUES ('c-0001', 't')")
        regi_verzio = len(tanulas_db.MIGRACIOK)
        with mock.patch.object(tanulas_db, "MIGRACIOK", self.UJ), mock.patch.object(mentes, "allapot_masolat") as a:
            with tanulas_db.iro(self.cfg):
                pass
        a.assert_not_called()                      # nem a közös állapotmásolat: nincs `.tmp` törlés, nincs közös rotáció
        self.assertEqual(self.verzio(), regi_verzio + 1)
        masolatok = sorted(self.cfg.path("backup").glob(f"{mentes.MIGRACIO_NEV}-tanulas-v{regi_verzio}-*.sqlite"))
        self.assertEqual(len(masolatok), 1)
        c = sqlite3.connect(f"file:{masolatok[0]}?mode=ro", uri=True)
        try:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], regi_verzio)     # a migráció ELŐTTI állapot
            self.assertEqual(c.execute("SELECT azon FROM kartya").fetchall(), [("c-0001",)])
        finally:
            c.close()

    def test_mas_allapotfajl_masolat_hibaja_nem_allitja_meg(self):
        """A3-06 (c): a közös állapotmásolat hibája (más fájl) nem akadályozza a tanulás migrációját."""
        with tanulas_db.iro(self.cfg):
            pass
        with mock.patch.object(tanulas_db, "MIGRACIOK", self.UJ), \
                mock.patch.object(mentes, "allapot_masolat", side_effect=OSError("másik fájl hibája")):
            with tanulas_db.iro(self.cfg):
                pass
        self.assertEqual(self.verzio(), len(tanulas_db.MIGRACIOK) + 1)

    def test_mentes_hibaja_megallitja_a_migraciot(self):
        with tanulas_db.iro(self.cfg):
            pass
        with mock.patch.object(tanulas_db, "MIGRACIOK", self.UJ), \
                mock.patch.object(mentes, "migracio_elott", side_effect=OSError("tele a lemez")):
            with self.assertRaises(sqlite3.DatabaseError) as cm:
                with tanulas_db.iro(self.cfg):
                    pass
        self.assertIn("tele a lemez", str(cm.exception))
        self.assertEqual(self.verzio(), len(tanulas_db.MIGRACIOK))

    def test_a_migracios_masolat_rotacioja_nem_a_kozos(self):
        """Több migráció: a másolatok fájlonként a `megtartott_migracio` rotációjában élnek (nem 10 közös mentés után futnak ki)."""
        with tanulas_db.iro(self.cfg):
            pass
        for i in range(3):
            uj = tanulas_db.MIGRACIOK + [f"CREATE TABLE kviz_proba{j} (x TEXT);" for j in range(i + 1)]
            with mock.patch.object(tanulas_db, "MIGRACIOK", uj):
                with tanulas_db.iro(self.cfg):
                    pass
            for _ in range(12):                         # közben sok közös állapotmásolat készül
                mentes.allapot_masolat(self.cfg)
        self.assertGreaterEqual(len(list(self.cfg.path("backup").glob(f"{mentes.MIGRACIO_NEV}-tanulas-v*.sqlite"))), 1)


class MigracioZarTest(Alap):
    """A3-06 (ALACSONY mellékág): a core és a `bin/mos kartya` CLI két folyamat — a migrációt fájlzár védi."""
    UJ = tanulas_db.MIGRACIOK + ["CREATE TABLE kviz_proba (x TEXT);"]

    def test_a_migracio_megvarja_a_masik_folyamat_zarat(self):
        import fcntl
        import threading
        with tanulas_db.iro(self.cfg):
            pass
        zar = tanulas_db.migracio_zar_ut(self.cfg)
        alap = len(tanulas_db.MIGRACIOK)              # a szál ideiglenesen felülírja a MIGRACIOK-ot: előre rögzítjük
        kesz = threading.Event()

        def migral():
            with mock.patch.object(tanulas_db, "MIGRACIOK", self.UJ):
                with tanulas_db.iro(self.cfg):
                    pass
            kesz.set()

        zar.parent.mkdir(parents=True, exist_ok=True)
        with open(zar, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)              # a „másik folyamat” a zárat tartja
            sz = threading.Thread(target=migral, daemon=True)
            sz.start()
            self.assertFalse(kesz.wait(0.5))            # várakozik, nem migrál
            self.assertEqual(self.verzio(), alap)
            fcntl.flock(fh, fcntl.LOCK_UN)
        self.assertTrue(kesz.wait(10))
        sz.join(5)
        self.assertEqual(self.verzio(), alap + 1)

    def test_ket_folyamat_egyszerre_migral(self):
        """Két (négy) folyamat egyszerre migrál: a zár után a verziót újraolvassák, nem futnak „table already exists”-be."""
        import os
        import subprocess
        import sys
        from pathlib import Path
        with tanulas_db.iro(self.cfg):
            pass
        kod = ("from unittest import mock\nfrom core import config, tanulas_db\ncfg = config.load()\n"
               "uj = tanulas_db.MIGRACIOK + ['CREATE TABLE kviz_proba (x TEXT);']\n"
               "with mock.patch.object(tanulas_db, 'MIGRACIOK', uj):\n    with tanulas_db.iro(cfg):\n        pass\n")
        env = {**os.environ, "MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"),
               "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        folyamatok = [subprocess.Popen([sys.executable, "-c", kod], env=env, stderr=subprocess.PIPE, text=True) for _ in range(4)]
        kimenetek = [(f.wait(60), f.stderr.read()) for f in folyamatok]
        self.assertEqual([k[0] for k in kimenetek], [0, 0, 0, 0], kimenetek)
        self.assertEqual(self.verzio(), len(tanulas_db.MIGRACIOK) + 1)


if __name__ == "__main__":
    unittest.main()
