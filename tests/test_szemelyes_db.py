"""A személyes adatbázis közös rétege (`core/szemelyes_db.py`): a migrációk és az előre-kompatibilitás — ideiglenes
álgyökéren, a valódi `{szemelyes}/pos.sqlite`-hoz soha nem nyúl (T007, 2. audit)."""
import contextlib
import io
import sqlite3
import unittest
from unittest import mock

from core import mentes, szemelyes_db
from tests.helpers import alg_core, alg_gyoker, tmpdir


def szemelyes_cfg(tmp: str, nev: str):
    """Álgyökér, amelynek `{szemelyes}` mappája a megadott (akár `#`, `?`, `%` jelet tartalmazó) nevű → (config, mappa)."""
    from pathlib import Path
    from core import config
    root = alg_gyoker(tmp)
    mappa = Path(tmp) / "szulo" / nev
    cfg = config.load({"MOS_ROOT": str(root), "HOME": str(Path(tmp) / "home"), "MOS_SZEMELYES": str(mappa)})
    return cfg, mappa


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)

    def verzio(self) -> int:
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        try:
            return c.execute("PRAGMA user_version").fetchone()[0]
        finally:
            c.close()

    def verzio_be(self, v: int) -> None:
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        c.execute(f"PRAGMA user_version = {v}")
        c.commit()
        c.close()


class MigralTest(Alap):
    def test_uj_fajl_a_legfrissebb_semara_migral(self):
        with szemelyes_db.iro(self.cfg):
            pass
        self.assertEqual(self.verzio(), szemelyes_db.VERZIO)

    def test_ismert_tablak_a_migraciokbol_szarmaznak(self):
        for t in ("forras_rekord", "import_futas", "naptar", "tr_aktiv", "has_parancs", "emlekezteto", "naptar_javaslat",
                  "has_asszisztens"):
            self.assertIn(t, szemelyes_db.ISMERT_TABLAK)

    def test_ujabb_sema_ismert_tablakkal_nem_dob_es_nem_nyul_a_verziohoz(self):
        """A séma csak bővül (L56): egy újabb verzió az ismert táblákat nem bontja, ezért egy régebbi kód is írhat
        a saját tábláiba — a tracker nem dobhatja el csendben az eseményeket egy újabb `user_version` miatt."""
        with szemelyes_db.iro(self.cfg):
            pass
        self.verzio_be(szemelyes_db.VERZIO + 6)
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("INSERT INTO has_parancs (nap, parancs, forras, db) VALUES ('2026-10-04', 'x.y', 'paletta', 1)")
        self.assertEqual(self.verzio(), szemelyes_db.VERZIO + 6)
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        self.addCleanup(c.close)
        self.assertEqual(c.execute("SELECT count(*) FROM has_parancs").fetchone()[0], 1)

    def test_ujabb_sema_hianyzo_tablaval_dob(self):
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("DROP TABLE has_szunet")
        self.verzio_be(szemelyes_db.VERZIO + 1)
        with self.assertRaisesRegex(sqlite3.DatabaseError, "újabb.*has_szunet"):
            with szemelyes_db.iro(self.cfg):
                pass

    def test_ujabb_sema_tabla_nelkul_dob(self):
        szemelyes_db.ut(self.cfg).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        c.execute("PRAGMA user_version = 9")
        c.commit()
        c.close()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "újabb"):
            with szemelyes_db.iro(self.cfg):
                pass
        self.assertEqual(self.verzio(), 9)

    def test_olvaso_nem_hoz_letre_fajlt(self):
        with szemelyes_db.olvaso(self.cfg) as c:
            self.assertIsNone(c)
        self.assertFalse(szemelyes_db.ut(self.cfg).exists())


class MigracioElottTest(Alap):
    """33. döntés: „VACUUM INTO másolat … minden migráció előtt” (C29.7b): a meglévő `pos.sqlite` léptetése előtt a
    felhasználó adatáról (az 1-es naptár-tábláktól kezdve) másolat készül a `{backup}` alá; új fájlnál, friss sémánál és a
    folyamat második hívásánál nem. A másolat hibája nem akasztja a migrációt."""

    def setUp(self):
        super().setUp()
        szemelyes_db._MASOLT.clear()
        self.backup = self.cfg.path("backup")

    def _v1(self) -> None:
        szemelyes_db.ut(self.cfg).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        c.executescript(szemelyes_db.MIGRACIOK[0] + "\nPRAGMA user_version=1;")
        c.execute("INSERT INTO naptar (azon, nev, kategoria, kategoria_forras) VALUES ('n1', 'Studying', 'tanulas', 'javaslat')")
        c.commit()
        c.close()

    def _masolatok(self):
        return sorted(self.backup.glob("mos-migracio-pos-*.sqlite")) if self.backup.is_dir() else []

    def test_v1_migracio_elott_masolat_keszul_a_regi_tartalommal(self):
        self._v1()
        with szemelyes_db.iro(self.cfg):
            pass
        self.assertEqual(self.verzio(), szemelyes_db.VERZIO)
        m = self._masolatok()
        self.assertEqual(len(m), 1, m)
        self.assertRegex(m[0].name, r"^mos-migracio-pos-v1-\d{8}-\d{6}\.sqlite$")
        c = sqlite3.connect(m[0])
        self.addCleanup(c.close)
        self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 1, "a másolat a migráció ELŐTTI állapot")
        self.assertEqual(c.execute("SELECT nev FROM naptar").fetchall(), [("Studying",)])
        self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name = 'tr_aktiv'").fetchone())
        self.assertFalse(list(self.backup.glob("*.tmp")), "nem marad félkész másolat")

    def test_uj_fajl_friss_sema_es_ismetlodo_hivas_nem_masol(self):
        with szemelyes_db.iro(self.cfg):                      # új fájl: nincs mit védeni
            pass
        self.assertEqual(self._masolatok(), [])
        szemelyes_db._MASOLT.clear()
        with szemelyes_db.iro(self.cfg):                      # friss séma
            pass
        self.assertEqual(self._masolatok(), [])
        self._v1_felulir()
        szemelyes_db._MASOLT.clear()                          # egy új folyamat: régebbi sémájú fájlt talál
        with szemelyes_db.iro(self.cfg):
            pass
        with szemelyes_db.iro(self.cfg):                      # a második hívás ugyanabban a folyamatban
            pass
        self.assertEqual(len(self._masolatok()), 1)

    def _v1_felulir(self) -> None:
        szemelyes_db.ut(self.cfg).unlink()
        self._v1()

    def test_a_masolat_hibaja_nem_akasztja_a_migraciot(self):
        self._v1()
        ki = io.StringIO()
        with mock.patch.object(mentes, "migracio_elott", side_effect=OSError("tele a lemez")), contextlib.redirect_stderr(ki):
            with szemelyes_db.iro(self.cfg):
                pass
        self.assertEqual(self.verzio(), szemelyes_db.VERZIO, "a migráció a másolat nélkül is lefut")
        self.assertIn("tele a lemez", ki.getvalue())

    def test_rotacio_a_legujabb_n_masolatot_tartja(self):
        self.backup.mkdir(parents=True)
        for i in range(7):
            (self.backup / f"mos-migracio-pos-v1-2025010{i + 1}-000000.sqlite").write_bytes(b"regi")
        self._v1()
        with szemelyes_db.iro(self.cfg):
            pass
        nevek = [p.name for p in self._masolatok()]
        self.assertEqual(len(nevek), 5, nevek)
        self.assertNotIn("mos-migracio-pos-v1-20250101-000000.sqlite", nevek)
        self.assertTrue(any(n > "mos-migracio-pos-v1-2026" for n in nevek), "az új másolat megmaradt")

    def test_nem_az_allapot_masolat_mappajaba_es_azt_nem_bantja(self):
        self._v1()
        keszul = self.backup / "mos-allapot-20261004-100000.tmp"
        keszul.mkdir(parents=True)
        (keszul / "feladatok.sqlite").write_bytes(b"felkesz")
        with szemelyes_db.iro(self.cfg):
            pass
        self.assertTrue((keszul / "feladatok.sqlite").is_file(),
                        "a migráció előtti másolat nem törölheti egy másik szál készülő állapotmásolatát")


class KodoltUriTest(unittest.TestCase):
    """T108 (2. audit): a `{szemelyes}` útja `#`, `?` vagy `%` jelet is tartalmazhat. A kódolatlan URI-ban a `#` utáni
    rész (a `?mode=ro` is) a fragmentbe esik, az SQLite az út elejét nyitja alapértelmezett, **írható** módban, és
    kóbor, üres fájlt hoz létre; az olvasó így nem a valódi adatbázist látja."""

    NEVEK = ("a#b", "a?b", "a%20b", "a b", "100%")

    def test_olvaso_a_valodi_adatbazist_latja_es_nem_hoz_letre_koborfajlt(self):
        for nev in self.NEVEK:
            with self.subTest(nev=nev), tmpdir() as tmp:
                cfg, mappa = szemelyes_cfg(tmp, nev)
                with szemelyes_db.iro(cfg) as c:
                    c.execute("INSERT INTO has_parancs (nap, parancs, forras, db) VALUES ('2026-10-04', 'x.y', 'paletta', 3)")
                szulo = mappa.parent
                elotte = sorted(p.name for p in szulo.iterdir())
                with szemelyes_db.olvaso(cfg) as c:
                    self.assertIsNotNone(c, "az olvasó nem találta a pos.sqlite-ot")
                    self.assertEqual(c.execute("SELECT db FROM has_parancs").fetchone()[0], 3)
                self.assertEqual(sorted(p.name for p in szulo.iterdir()), elotte, "kóbor fájl keletkezett")
                self.assertEqual(sorted(p.name for p in mappa.iterdir() if not p.name.endswith(("-shm", "-wal"))),
                                 ["pos.sqlite"])


if __name__ == "__main__":
    unittest.main()
