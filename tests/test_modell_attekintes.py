"""A vezérlő Modellek szakaszának adata (C19, T051): `GET /api/vezerlo/modellek` — feladatonként a sorok, a kalibrált jel,
az aktuális aranyverzió és a router döntése a két keretre; csak olvas."""
import unittest

from core.modell import attekintes, beallitas as B
from core.modell.kalibracio import Tabla
from tests.helpers import alg_core, tmpdir

FELADAT = 'VERZIO = "szoveg-v2"\nROUTER_FELADAT = "szoveg"\ndef tetelek(cfg):\n    return []\ndef pontoz(r):\n    return {"pontszam": 0.0}\n'


class AttekintesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        d = self.cfg.path("modulok") / "eval" / "szoveg"
        d.mkdir(parents=True)
        (d / "feladat.py").write_text(FELADAT, encoding="utf-8")
        t = Tabla(B.betolt(self.cfg, {}).router_db)
        t.rogzit("szoveg", "gemma4_12b", 0.6, "szoveg-v2", kalibralt=True, snapshot="a" * 40)
        t.rogzit("szoveg", "qwen35_4b", 0.45, "szoveg-v2", kalibralt=True)
        t.rogzit("szoveg", "gemma4_e2b", 0.4, "szoveg-v1")
        t.rogzit("matek", "qwen35_9b", 0.9, "matek-v1", kalibralt=True)                 # nincs aktuális aranya: nem routol
        t.close()

    def test_feladatonkent_sorok_jel_es_dontes(self):
        a = attekintes.attekintes(self.cfg)
        self.assertEqual(a["keretek"], {"munka": 5.0, "tavol": 9.0})
        f = {x["feladat"]: x for x in a["feladatok"]}
        sz = f["szoveg"]
        self.assertEqual(sz["aktualis_verzio"], "szoveg-v2")
        self.assertEqual([(s["modell"], s["kalibralt"], s["aktualis"], s["keret"]) for s in sz["sorok"]],
                         [("gemma4_12b", True, True, "tavol"), ("qwen35_4b", True, True, "munka"),
                          ("gemma4_e2b", False, False, "munka")])
        self.assertEqual(sz["sorok"][0]["snapshot"], "a" * 12)
        self.assertEqual(sz["dontes"]["munka"]["modell"], "qwen35_4b")                 # D5: munka közben a keretbe férő
        self.assertEqual(sz["dontes"]["tavol"]["modell"], "gemma4_12b")
        self.assertIsNone(f["matek"]["dontes"]["munka"]["modell"])
        self.assertIn("aktuális", f["matek"]["dontes"]["munka"]["indok"])
        self.assertIn("ocr_kezi", f)                                                     # a router-feladat sor nélkül is látszik
        self.assertEqual(f["ocr_kezi"]["sorok"], [])


if __name__ == "__main__":
    unittest.main()
