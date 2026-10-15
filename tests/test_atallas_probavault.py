"""C31 (2. és 7. pont): az átállás próbavault-generátora álkönyvtárban — a kötelező anyag megvan, a 2.0 formátumai
érvényesek, és az ELLENORZO.md JS-paritás táblája a 2.0 kiértékelőjének valódi eredménye (`TZ=Europe/Budapest`)."""
import json
import os
import sys
import time
import unittest
from pathlib import Path

from core.bazis.ertekek import szovegge
from core.index import feloldas
from tests.bazis_segedek import ertek, sor
from tests.helpers import tmpdir

sys.path.insert(0, str(Path(__file__).resolve().parent / "kezi"))
import atallas_probavault as apv  # noqa: E402


class ProbavaultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.cel = Path(cls._t.name) / "c31"
        cls.ki = apv.general(cls.cel)
        cls.fo = cls.cel / apv.FO

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_mennyiseg_es_vaultok(self):
        self.assertGreaterEqual(self.ki["fo"]["jegyzet"], 30)
        self.assertEqual(self.ki["fo"]["canvas"], 5)
        self.assertGreaterEqual(self.ki["fo"]["plot"], 2)
        self.assertEqual(len(self.ki["k11"]["bazisok"]), 5)
        self.assertEqual(self.ki["k42"], ["AB/J.md", "B/J.md", "A/x.md", "C/x.md"])
        for v in (apv.FO, "2 - K04 Link-próba", "4 - K11 Bases", "5 - K42 Forrás-mappa"):
            self.assertTrue((self.cel / v / ".obsidian" / "app.json").is_file(), v)
        e = (self.cel / "ELLENORZO.md").read_text(encoding="utf-8")
        for kulcs in ("K04", "K10", "K11", "K12", "K15", "K17", "K25", "K42", "T155", "T156", "T157", "T158", "T160"):
            self.assertIn(kulcs, e, kulcs)
        self.assertIn("`{{DATE}}` cserélődik", e)

    def test_canvasok_ervenyes_json_canvas(self):
        for p in self.fo.rglob("*.canvas"):
            j, hiba = feloldas.canvas_olvas(p)
            self.assertIsNone(hiba, p.name)
            self.assertTrue(j["nodes"])

    def test_kiseroek_a_2_0_elemzoivel_visszaolvashatok(self):
        from modulok.kartya import formatum as kartya
        from modulok.kviz import formatum as kviz
        from modulok.osszefoglalas import formatum as ossz
        k = kartya.elemez((self.fo / "ATTCHMNTS - cards/01 - Mértani sorozat — kártyák.md").read_text(encoding="utf-8"))
        self.assertEqual(len(kartya.ervenyes(k)), 2)
        q = next((self.fo / "ATTCHMNTS - quizes").glob("*.md"))
        self.assertEqual(len(kviz.elemez(q.read_text(encoding="utf-8")).kviz.kerdesek), 1)
        o = ossz.elemez((self.fo / "ATTCHMNTS - summaries/01 - Mértani sorozat — összefoglaló.md").read_text(encoding="utf-8"))
        self.assertEqual(len(o.osszefoglalo.allitasok), 1)

    def test_a_feloldasi_esetek_a_2_0_szerint(self):
        g = feloldas.graf(self.fo)
        out = g["out"]
        self.assertIn("Feloldás/Hosszabb mappa neve/cél.md", out["Feloldás/Források/Kis-nagybetű.md"])
        self.assertNotIn("Feloldás/Források/Szegmens.md", out)                     # [[x/A]]: a 2.0-ban feloldatlan
        md = out["Linkek/md-linkek.md"]
        self.assertIn("Linkek/Cél X.md", md)
        self.assertIn("Linkek/a%23b.md", md)

    def test_js_paritas_tabla_a_kiertekelo_eredmenye(self):
        regi = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Budapest"
        time.tzset()
        try:
            for nev, vart in apv.JS_VART.items():
                if nev == "*":
                    continue
                txt = (self.fo / f"JS-paritás/{nev}.md").read_text(encoding="utf-8")
                fm = dict(sor_.split(": ", 1) for sor_ in txt.split("---\n")[1].strip().splitlines())
                s = sor(f"JS-paritás/{nev}.md", {"Kezd": ("date", fm["Kezd"]), "Veg": ("date", fm["Veg"]),
                                                  "a": ("number", int(fm["a"])), "b": ("number", int(fm["b"])),
                                                  "a-b": ("number", int(fm["a-b"])), "Tized": ("number", 0.1)})
                self.assertEqual(ertek("(Veg - Kezd) / 3600000", s), vart["orak"], nev)
                self.assertEqual(ertek("a-b", s), vart["kotojel"], nev)
                self.assertEqual(szovegge(ertek('Kezd.format("YYYY-MM-DD Z ZZ")', s)), vart["zona"], nev)
                self.assertEqual(ertek("Tized.toFixed(30)", s), apv.JS_VART["*"]["tized_30"])
        finally:
            if regi is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = regi
            time.tzset()

    def test_nem_ures_celba_nem_ir(self):
        with self.assertRaises(SystemExit):
            apv.general(self.cel)
        self.assertEqual(json.loads((self.fo / ".obsidian" / "templates.json").read_text(encoding="utf-8")),
                         {"folder": "_Template"})


if __name__ == "__main__":
    unittest.main()
