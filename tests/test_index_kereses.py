"""Keresés (C06): operátorok, ékezet- és kis-nagybetű-függetlenség, OR, tagadás, regex, `line:`, és a
linkeletlen említések."""
import unittest

from core import vaultio
from core.index import kereses
from tests.helpers import tmpdir
from tests.index_segedek import alvault, index_indit

FAJLOK = {
    ".obsidian/app.json": "{}",
    "T18 - Dualizmus/Elmélet/09 - Tisza Kálmán.md": (
        "---\nTags:\n  - History/Hungary\n---\n# Tisza Kálmán\nA miniszterelnök 1875-től kormányzott.\n"
        "Árvíztűrő tükörfúrógép.\n"),
    "T18 - Dualizmus/Elmélet/10 - Véderővita.md": (
        "A véderővita idején Tisza Kálmán megbukott.\nTisza István később.\n[[09 - Tisza Kálmán]] fontos.\n"
        "`Tisza Kálmán kódban`\n#History\n"),
    "M01 - Matek/Függvények.md": "---\ntags: [math, Math/Analízis]\n---\nA függvény értelmezési tartománya. #todo\n",
    "X01 - Napló/2026-09-12.md": "Ma a tisza kálmán jegyzetet írtam. Tiszakálmán nem szó.\n- [ ] határidő 📅 2026-10-01\n",
    "Kép.png": b"\x89PNG",
}


class KeresesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.cfg, cls.v = alvault(cls._t.name, FAJLOK)
        cls.ix, _ = index_indit(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.ix.leallit()
        cls._t.cleanup()

    def utak(self, q):
        return {t["ut"].rsplit("/", 1)[-1] for t in self.ix.kereses(q)["talalatok"]}

    def test_szo_ekezet_es_kisbetu_fuggetlen_szokezdetre(self):
        self.assertEqual(self.utak("arvizturo"), {"09 - Tisza Kálmán.md"})
        self.assertEqual(self.utak("FÜGGV"), {"Függvények.md"})
        self.assertEqual(self.utak("vederovi"), {"10 - Véderővita.md"})           # a fájlnévben és a tartalomban
        self.assertEqual(self.utak("ederovita"), set())                            # szókezdetre illeszt

    def test_kifejezes_es_logika(self):
        self.assertEqual(self.utak('"tisza kalman"'),
                         {"09 - Tisza Kálmán.md", "10 - Véderővita.md", "2026-09-12.md"})
        self.assertEqual(self.utak("tisza -istván"), {"09 - Tisza Kálmán.md", "2026-09-12.md"})
        self.assertEqual(self.utak("(miniszterelnök OR függvény) -path:M01"), {"09 - Tisza Kálmán.md"})
        self.assertEqual(self.utak("tisza OR függvény"),
                         {"09 - Tisza Kálmán.md", "10 - Véderővita.md", "2026-09-12.md", "Függvények.md"})

    def test_operatorok(self):
        self.assertEqual(self.utak("path:napló"), {"2026-09-12.md"})
        self.assertEqual(self.utak("path:/^T18/ tisza"), {"09 - Tisza Kálmán.md", "10 - Véderővita.md"})
        self.assertEqual(self.utak("file:png"), {"Kép.png"})
        self.assertEqual(self.utak("file:/^\\d+ - /"), {"09 - Tisza Kálmán.md", "10 - Véderővita.md"})
        self.assertEqual(self.utak("tag:#history"), {"09 - Tisza Kálmán.md", "10 - Véderővita.md"})
        self.assertEqual(self.utak("tag:math"), {"Függvények.md"})                  # a math/analízis is alatta
        self.assertEqual(self.utak("tag:#math/analízis"), {"Függvények.md"})
        self.assertEqual(self.utak("tag:hungary"), set())                         # csak a gyökértől
        self.assertEqual(self.utak("line:(tisza megbukott)"), {"10 - Véderővita.md"})
        # a „tisza” csak a fájlnévben áll, az „1875” csak a tartalomban: egy sorban nincs együtt (T061: korábban a név is számított)
        self.assertEqual(self.utak("line:(tisza 1875)"), set())
        self.assertEqual(self.utak("line:(kálmán 1875)"), set())
        self.assertEqual(self.utak("line:(miniszterelnök 1875)"), {"09 - Tisza Kálmán.md"})
        self.assertEqual(self.utak("tisza 1875 -line:(tisza 1875)"), {"09 - Tisza Kálmán.md"})

    def test_regex_es_talalati_sorok(self):
        r = self.ix.kereses("/\\d{4}-\\d{2}-\\d{2}/")
        self.assertEqual({t["ut"].rsplit("/", 1)[-1] for t in r["talalatok"]}, {"2026-09-12.md"})
        sor = r["talalatok"][0]["talalatok"][0]
        self.assertEqual((sor["sor"], sor["oszlop"], sor["hossz"]), (2, 17, 10))
        t = self.ix.kereses("megbukott")["talalatok"][0]["talalatok"][0]
        self.assertEqual((t["sor"], t["szoveg"][t["oszlop"]:t["oszlop"] + t["hossz"]]), (1, "megbukott"))

    def test_kornyezet_a_szomszed_sorokkal(self):
        """C11a: `kornyezet=N` → találatonként az előtte és utána álló sorok (a fájl szélén kevesebb); 0-nál nincs."""
        alap = self.ix.kereses('"tisza istván"')["talalatok"][0]["talalatok"][0]
        self.assertNotIn("elotte", alap)                                       # a mai válasz változatlan
        t = self.ix.kereses('"tisza istván"', None, 1)["talalatok"][0]["talalatok"][0]
        self.assertEqual((t["sor"], t["elotte"], t["utana"]),
                         (2, ["A véderővita idején Tisza Kálmán megbukott."], ["[[09 - Tisza Kálmán]] fontos."]))
        t = self.ix.kereses("véderővita", None, 3)["talalatok"][0]["talalatok"][0]   # a fájl első sora: nincs előtte
        self.assertEqual((t["sor"], t["elotte"], len(t["utana"])), (1, [], 3))
        self.assertEqual(self.ix.kereses('"tisza istván"', None, 5)["talalatok"][0]["talalatok"][0]["utana"][-1], "#History")

    def test_hibas_lekerdezes(self):
        for q in ("", "(a", "a)", "/[/", "path:"):
            with self.assertRaises(vaultio.Invalid, msg=q):
                self.ix.kereses(q)

    def test_lexer(self):
        self.assertEqual(kereses.elemez('-"a b" OR path:(x)'.replace("(x)", "x")),
                         ("vagy", [("nem", ("kif", "a b")), ("op", "path", ("szo", "x"))]))

    def test_emlitesek(self):
        e = self.ix.emlitesek("T18 - Dualizmus/Elmélet/09 - Tisza Kálmán.md")
        self.assertEqual(e["nevek"], ["09 - Tisza Kálmán"])
        self.assertEqual(e["forrasok"], [])                  # a névelőtag miatt nincs szöveges említés
        (self.v / "M01 - Matek" / "Alias.md").write_text("---\naliases: [Tisza Kálmán]\n---\n")
        self.ix.frissit(["M01 - Matek/Alias.md"])
        self.addCleanup(lambda: ((self.v / "M01 - Matek" / "Alias.md").unlink(),
                                 self.ix.frissit(["M01 - Matek/Alias.md"])))
        e = self.ix.emlitesek("M01 - Matek/Alias.md")
        talalt = {f["ut"].rsplit("/", 1)[-1]: [t["sor"] for t in f["talalatok"]] for f in e["forrasok"]}
        # a link, a kód, a frontmatter és a saját fájl nem említés; a kisbetűs igen, az egybeírt nem
        self.assertEqual(talalt, {"09 - Tisza Kálmán.md": [5], "10 - Véderővita.md": [1], "2026-09-12.md": [1]})


class RegexIdokorlatTest(unittest.TestCase):
    """H5 (audit): a felhasználói regex időkorláttal fut — a katasztrofális visszalépés nem állítja meg a core-t.
    (A `re`-vel az audit `/(a+)+$/`-e egy 60 `a`-s, nem illeszkedő sorra percekig futna, a GIL-t fogva; a
    `regex` csomag azt felismeri, de a `/(a|aa)+$/`-t nem — az időkorlát ezt fogja meg.)"""

    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.cfg, cls.v = alvault(cls._t.name, {".obsidian/app.json": "{}", "Lassú.md": "a" * 60 + "!\n",
                                                "Gyors.md": "aaa\n"})
        cls.ix, _ = index_indit(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.ix.leallit()
        cls._t.cleanup()

    def test_katasztrofalis_regex_idotullepes(self):
        import time
        for q in ("/(a|aa)+$/", "line:(/(a|aa)+$/)", "Lassú OR /(a|aa)+$/"):
            t0 = time.monotonic()
            with self.assertRaises(vaultio.Invalid, msg=q) as cm:
                self.ix.kereses(q)
            self.assertLess(time.monotonic() - t0, 5, q)
            self.assertIn("túl sokáig", str(cm.exception))

    def test_az_audit_mintaja_mar_gyors(self):
        import time
        t0 = time.monotonic()
        self.assertEqual(self.ix.kereses("/(a+)+$/")["osszes"], 1)        # a Gyors.md „aaa” sora
        self.assertLess(time.monotonic() - t0, 1)

    def test_ertelmes_regex_mukodik(self):
        self.assertEqual({t["ut"] for t in self.ix.kereses("/^a{3}$/")["talalatok"]}, {"Gyors.md"})


if __name__ == "__main__":
    unittest.main()


class LineEsIdokeretTest(unittest.TestCase):
    """C25a: a `line:` csak a sor szövegét nézi (T061); a nem-regex keresés korai leáll a `limit`-nél, és az
    időkeret lejártakor részeredményt ad „legalább” jelzéssel (T152)."""

    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        fajlok = {".obsidian/app.json": "{}",
                  "Integrál/Lap.md": "Semmi köze.\n",
                  "Integrál.md": "Más a tartalom.\n",
                  "Szöveg.md": "Az integrál itt a sorban áll.\n"}
        for i in range(5):
            fajlok[f"Tömeg/Elem{i}.md"] = f"A tömeg {i}. példánya.\n"
        cls.cfg, cls.v = alvault(cls._t.name, fajlok)
        cls.ix, _ = index_indit(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.ix.leallit()
        cls._t.cleanup()

    def utak(self, q, limit=None):
        return {t["ut"] for t in self.ix.kereses(q, limit)["talalatok"]}

    def test_line_nem_illeszt_a_fajl_es_mappanevre(self):
        self.assertEqual(self.utak("integrál"), {"Integrál/Lap.md", "Integrál.md", "Szöveg.md"})   # sima szó: név/út is
        self.assertEqual(self.utak("line:(integrál)"), {"Szöveg.md"})
        self.assertEqual(self.utak("line:integrál"), {"Szöveg.md"})
        self.assertEqual(self.utak('line:("integrál itt")'), {"Szöveg.md"})
        self.assertEqual(self.utak("line:(/integr/)"), {"Szöveg.md"})
        self.assertEqual(self.utak("integrál -line:(integrál)"), {"Integrál/Lap.md", "Integrál.md"})

    def test_korai_leallas_a_limitnel(self):
        r = self.ix.kereses("tömeg", 2)
        self.assertEqual((len(r["talalatok"]), r["legalabb"]), (2, True))
        self.assertGreaterEqual(r["osszes"], 2)
        r = self.ix.kereses("tömeg", 50)
        self.assertEqual((len(r["talalatok"]), r["osszes"], r["legalabb"]), (5, 5, False))

    def test_idokeret_lejartakor_reszeredmeny(self):
        with self.ix._olvaso() as c:
            r = kereses.keres(c, "tömeg", 200, idokorlat=0)
        self.assertTrue(r["legalabb"])
        self.assertLess(len(r["talalatok"]), 5)
