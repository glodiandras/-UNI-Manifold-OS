"""F5: a persisted v4 index adopts relative-link semantics without editing notes."""
import json
import unittest
from unittest import mock

from core.index import feloldas, tar
from tests.fresh_install import lenyomat
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit


class F5IndexMigracioTest(unittest.TestCase):
    def test_v4_relativ_linkek_ujraoldodnak_restartkor_a_tobbi_cache_megmarad(self):
        with tmpdir() as t:
            cfg, root, vault = alg_core(t)
            fajlok = {
                "Dir/Source.md": '[[ ./Target ]] [[..\\Other\\Note]] [markdown](./Target.md)\n',
                "Dir/Board.canvas": json.dumps({"nodes": [{"id": "text", "type": "text", "text": "[[./Target]]"}], "edges": []}),
                "Dir/Target.md": "# Target\n",
                "Other/Note.md": "# Other note\n",
                "Ordinary.md": "[[Dir/Target]]\n",
            }
            for ut, tartalom in fajlok.items():
                ir(vault, ut, tartalom)
            eredeti = lenyomat(vault, kihagy=())
            felold = feloldas.Feloldo.resolve

            def regi_resolve(self, cel, forras):
                # The previous v4 resolver left explicit relative targets unresolved.
                if feloldas._elokeszit(cel).startswith(("./", "../")):
                    return None, None, False
                return felold(self, cel, forras)

            with mock.patch.object(feloldas.Feloldo, "resolve", regi_resolve):
                ix, _ = index_indit(cfg)
                db = ix.db_ut
                try:
                    self.assertTrue(all(r["cel"] is None for r in ix.jegyzet("Dir/Source.md")["linkek"]))
                finally:
                    ix.leallit()

            # Recreate the structurally identical prior cache version, preserving real stat/hash rows.
            c = tar.nyit(db, iro=True)
            c.execute("PRAGMA user_version = 4")
            elotte = {r["ut"]: (r["hash"], r["mtime_ns"]) for r in c.execute("SELECT ut, hash, mtime_ns FROM fajl")}
            c.close()
            c = tar.nyit(db, iro=True)
            try:
                self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], tar.VERZIO)
                utana = {r["ut"]: (r["hash"], r["mtime_ns"]) for r in c.execute("SELECT ut, hash, mtime_ns FROM fajl")}
                for ut in ("Dir/Source.md", "Dir/Board.canvas"):
                    self.assertEqual(utana[ut], (None, None), ut)
                for ut in ("Dir/Target.md", "Other/Note.md", "Ordinary.md"):
                    self.assertEqual(utana[ut], elotte[ut], ut)
            finally:
                c.close()

            ix, _ = index_indit(cfg)
            try:
                celok = [r["cel"] for r in ix.jegyzet("Dir/Source.md")["linkek"]]
                self.assertEqual(celok, ["Dir/Target.md", "Other/Note.md", "Dir/Target.md"])
                self.assertEqual([r["cel"] for r in ix.jegyzet("Ordinary.md")["linkek"]], ["Dir/Target.md"])
                self.assertEqual(ix.feloldas("Dir/Source.md", ["./Target"])[0]["ut"], "Dir/Target.md")
                self.assertEqual(lenyomat(vault, kihagy=()), eredeti)
            finally:
                ix.leallit()

            # Opening an already upgraded cache does not invalidate its fresh rows again.
            c = tar.nyit(db, iro=True)
            try:
                friss = {r["ut"]: (r["hash"], r["mtime_ns"]) for r in c.execute("SELECT ut, hash, mtime_ns FROM fajl")}
                tar.migral(c)
                ujra = {r["ut"]: (r["hash"], r["mtime_ns"]) for r in c.execute("SELECT ut, hash, mtime_ns FROM fajl")}
                self.assertEqual(ujra, friss)
                self.assertTrue(all(h is not None and m is not None for h, m in friss.values()))
            finally:
                c.close()


if __name__ == "__main__":
    unittest.main()
