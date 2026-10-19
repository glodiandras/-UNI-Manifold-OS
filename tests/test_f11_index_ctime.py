"""F11 (`07-explorer-01`, core half): the file tree API reports the real birth time (`ctime`) or null.

Never mtime, never the POSIX `st_ctime` (inode change time). Index schema v6 adds `fajl.ctime_ns`; the v5 -> v6
migration keeps hashes and mtimes, and the next sync fills only the NULL `ctime_ns` cells with a plain UPDATE."""
import os
import types
import unittest
from unittest import mock

from core.index import indexelo, tar
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit

FAJLOK = {
    "Alpha.md": "# Alpha\n[[Beta]]\n",
    "Dir/Beta.md": "# Beta\ntext\n",
    "pic.png": b"\x89PNG\r\n",
}


def _birth(p) -> float:
    return os.stat(p).st_birthtime


def _van_birthtime() -> bool:
    return hasattr(os.stat_result, "st_birthtime")


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _root, self.vault = alg_core(self._t.name)
        for rp, t in FAJLOK.items():
            ir(self.vault, rp, t, "wb" if isinstance(t, bytes) else "w")

    def indit(self):
        ix, _ev = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        return ix

    @staticmethod
    def fa_ctime(ix) -> dict:
        return {f["ut"]: f["ctime"] for f in ix.fa()["fajlok"]}

    def sorok(self, ix) -> dict:
        c = tar.nyit(ix.db_ut)
        try:
            return {r["ut"]: dict(r) for r in c.execute("SELECT * FROM fajl WHERE torolve IS NULL")}
        finally:
            c.close()


class SzuletesiIdoTest(_Alap):
    def setUp(self):
        if not _van_birthtime():
            self.skipTest("[indokolt] this platform/filesystem exposes no st_birthtime")
        super().setUp()

    def test_friss_index_ctime_egyezik_a_fajl_szuletesi_idejevel(self):
        ix = self.indit()
        fa = ix.fa()["fajlok"]
        self.assertEqual({f["ut"] for f in fa}, set(FAJLOK))
        for f in fa:
            self.assertIsInstance(f["ctime"], float, f["ut"])
            self.assertAlmostEqual(f["ctime"], _birth(self.vault / f["ut"]), delta=1.0, msg=f["ut"])
            self.assertIn("mtime", f)
        self.assertAlmostEqual(ix.jegyzet("Alpha.md")["ctime"], _birth(self.vault / "Alpha.md"), delta=1.0)

    def test_modositas_utan_a_ctime_nem_valtozik(self):
        ix = self.indit()
        elotte = self.fa_ctime(ix)
        sor_elotte = self.sorok(ix)["Alpha.md"]
        (self.vault / "Alpha.md").write_text("# Alpha\n[[Beta]]\nmore text, so size and mtime differ\n", encoding="utf-8")
        self.assertTrue(ix.frissit(["Alpha.md"]))
        self.assertTrue(ix.var(10))
        sor_utana = self.sorok(ix)["Alpha.md"]
        self.assertNotEqual(sor_utana["hash"], sor_elotte["hash"])        # the change really was re-indexed
        self.assertEqual(self.fa_ctime(ix), elotte)
        self.assertEqual(sor_utana["ctime_ns"], sor_elotte["ctime_ns"])

    def test_v5_index_migracio_kitolti_a_ctime_t_es_alkalmazza_a_v7_kommentmaszkot(self):
        ix = self.indit()
        db = ix.db_ut
        elotte = self.sorok(ix)
        ix.leallit()
        # Rebuild the exact v5 shape: no ctime_ns column, user_version = 5 (real stat/hash rows preserved).
        c = tar.nyit(db, iro=True)
        c.execute("ALTER TABLE fajl DROP COLUMN ctime_ns")
        c.execute("PRAGMA user_version = 5")
        c.close()

        c = tar.nyit(db, iro=True)                                         # migration 5 -> 6 -> 7
        try:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 7)
            self.assertEqual(tar.VERZIO, 7)
            sorok = {r["ut"]: dict(r) for r in c.execute("SELECT * FROM fajl")}
            for ut, r in sorok.items():
                self.assertIsNone(r["ctime_ns"], ut)
                self.assertEqual(r['indexelve'], elotte[ut]['indexelve'], ut)
                if ut.endswith('.md'):
                    self.assertEqual((r['hash'], r['mtime_ns']), (None, None), ut)
                else:
                    self.assertEqual((r['hash'], r['mtime_ns']), (elotte[ut]['hash'], elotte[ut]['mtime_ns']), ut)
            tar.migral(c)                                                  # idempotent
        finally:
            c.close()

        hivasok = []
        eredeti = indexelo.Index._fajl_ir

        def figyelt(self_, *a, **kw):
            hivasok.append(a[0])
            return eredeti(self_, *a, **kw)

        with mock.patch.object(indexelo.Index, "_fajl_ir", figyelt):
            ix2 = self.indit()
            utana = self.sorok(ix2)
            fa = self.fa_ctime(ix2)
        self.assertEqual(set(hivasok), {'Alpha.md', 'Dir/Beta.md'}, "only the v7-invalidated Markdown is re-analysed")
        for ut in FAJLOK:
            self.assertIsNotNone(utana[ut]["ctime_ns"], ut)
            self.assertAlmostEqual(fa[ut], _birth(self.vault / ut), delta=1.0, msg=ut)
            self.assertEqual((utana[ut]["hash"], utana[ut]["mtime_ns"]),
                             (elotte[ut]["hash"], elotte[ut]["mtime_ns"]), ut)
            if not ut.endswith('.md'):
                self.assertEqual(utana[ut]['indexelve'], elotte[ut]['indexelve'], ut)

    def test_friss_index_ctime_backfill_nem_elemezi_ujra_a_fajlokat(self):
        ix = self.indit()
        db, elotte = ix.db_ut, self.sorok(ix)
        ix.leallit()
        c = tar.nyit(db, iro=True)
        c.execute('UPDATE fajl SET ctime_ns = NULL')
        c.close()
        with mock.patch.object(indexelo.Index, '_fajl_ir', side_effect=AssertionError('ctime backfill must not re-analyse')):
            ix2 = self.indit()
            utana = self.sorok(ix2)
            self.assertIsNone(ix2.allapot()['hiba'])
        for ut in FAJLOK:
            self.assertIsNotNone(utana[ut]['ctime_ns'], ut)
            self.assertEqual((utana[ut]['hash'], utana[ut]['mtime_ns'], utana[ut]['indexelve']),
                             (elotte[ut]['hash'], elotte[ut]['mtime_ns'], elotte[ut]['indexelve']), ut)


class NincsSzuletesiIdoTest(_Alap):
    """Platform independent: a stat without birthtime gives NULL, never mtime or st_ctime."""

    def test_segedfuggveny_fajtai(self):
        van_ns = types.SimpleNamespace(st_birthtime_ns=1_700_000_000_123_456_789, st_birthtime=1.0)
        self.assertEqual(indexelo._szuletesi_ns(van_ns), 1_700_000_000_123_456_789)
        csak_float = types.SimpleNamespace(st_birthtime=1_700_000_000.5)
        self.assertEqual(indexelo._szuletesi_ns(csak_float), 1_700_000_000_500_000_000)
        nincs = types.SimpleNamespace(st_mtime_ns=5, st_mtime=5.0, st_ctime_ns=7, st_ctime=7.0)
        self.assertIsNone(indexelo._szuletesi_ns(nincs))

    def test_ha_a_stat_nem_ad_birthtime_ot_az_ertek_none_es_nem_mtime(self):
        with mock.patch.object(indexelo, "_szuletesi_ns", lambda st: None):
            ix = self.indit()
            fa = ix.fa()["fajlok"]
            self.assertEqual({f["ut"] for f in fa}, set(FAJLOK))
            for f in fa:
                self.assertIsNone(f["ctime"], f["ut"])
                self.assertIsNotNone(f["mtime"], f["ut"])
                self.assertNotEqual(f["ctime"], f["mtime"], f["ut"])
            self.assertIsNone(ix.jegyzet("Alpha.md")["ctime"])
            for r in self.sorok(ix).values():
                self.assertIsNone(r["ctime_ns"])


if __name__ == "__main__":
    unittest.main()
