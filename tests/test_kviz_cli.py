"""C22a: `bin/mos kviz` (`modulok/kviz/__main__.py`) — csak olvas, a vaultba nem ír, modellt nem hív."""
import argparse
import contextlib
import io
import json
import unittest

from modulok.kviz import __main__ as cli
from modulok.kviz import formatum as FM
from tests.helpers import alg_core, ir, tmpdir
from tests.test_kviz_generalas import GEN, JEGYZET, RP, TUDAS


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, RP, JEGYZET)

    def fut(self, fv, **kw):
        ki, hiba = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(ki), contextlib.redirect_stderr(hiba):
            rc = fv(self.cfg, argparse.Namespace(**kw))
        return rc, ki.getvalue(), hiba.getvalue()

    def forgatokonyv(self):
        p = self.root / "forgatokonyv.json"
        p.write_text(json.dumps({"generalo": GEN, "tudas": TUDAS}), encoding="utf-8")
        return str(p)


class ProbaTest(Alap):
    def test_a_lanc_almodellel_a_kimenetre_ir(self):
        rc, ki, hiba = self.fut(cli.proba, forras=RP, forgatokonyv=self.forgatokonyv(), n=3, karakter_per_kerdes=50)
        self.assertEqual(rc, 0, hiba)
        e = FM.elemez(ki)
        self.assertEqual(e.hibak, [])
        self.assertEqual(len(e.kviz.kerdesek), 3)
        self.assertEqual(e.kviz.modell, "almodell")
        self.assertIn('"tiltott_valasz": 1', hiba)
        self.assertEqual((self.v / RP).read_text(encoding="utf-8"), JEGYZET)           # a forrás érintetlen
        self.assertEqual(sorted(p.name for p in self.v.rglob("*.md")), ["04 - Nevezetes szorzatok.md"])    # semmi nem íródott

    def test_kevés_kerdes_hibakod(self):
        p = self.root / "ures.json"
        p.write_text(json.dumps({"generalo": GEN, "tudas": {}}), encoding="utf-8")
        rc, ki, hiba = self.fut(cli.proba, forras=RP, forgatokonyv=str(p), n=3, karakter_per_kerdes=50)
        self.assertEqual(rc, 1)
        self.assertIn("a kvíz nem készült el", hiba)

    def test_hianyzo_forras(self):
        with self.assertRaises(SystemExit):
            self.fut(cli.proba, forras="nincs.md", forgatokonyv=self.forgatokonyv(), n=3, karakter_per_kerdes=None)


class EllenorizTest(Alap):
    def kviz(self):
        from tests.test_kviz_generalas import kviz
        e, _ = kviz()
        return e.kviz

    def test_ervenyes_kviz_es_sodras(self):
        k = self.kviz()
        ir(self.v, "ATTCHMNTS - quizes/K.md", FM.ir(k))
        rc, ki, _ = self.fut(cli.ellenoriz, jegyzet="ATTCHMNTS - quizes/K.md")
        d = json.loads(ki)
        self.assertEqual((rc, d["kerdes"], d["hibak"], d["sodrodott"]), (0, 3, [], []))
        ir(self.v, RP, JEGYZET.replace("ezt két négyzet különbségének hívjuk", "ez a különbség"))        # a forrás változott
        rc, ki, _ = self.fut(cli.ellenoriz, jegyzet="ATTCHMNTS - quizes/K.md")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(ki)["sodrodott"], ["k2", "k3"])

    def test_hibas_kvizjegyzet(self):
        ir(self.v, "ATTCHMNTS - quizes/R.md", "# Semmi\n")
        rc, ki, _ = self.fut(cli.ellenoriz, jegyzet="ATTCHMNTS - quizes/R.md")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(ki)["hibak"][0]["fajta"], "nincs_kerdes")


if __name__ == "__main__":
    unittest.main()
