"""F11 keresés-bővítés (08-search-02/03/07/08/11, 03-properties-16): `[kulcs:érték]`, `match-case:`/`ignore-case:`,
`task*:`, `section:`, `*részszó`/`substring:`. A régi lekérdezések eredménye változatlan (kompatibilitás)."""
import unittest

from core.index import kereses
from core.index.hibrid import kereso, normal
from tests.helpers import tmpdir
from tests.index_segedek import alvault, index_indit

FAJLOK = {
    ".obsidian/app.json": "{}",
    "Alap.md": ("---\nstatus: Kész\ntags: [math, History/Hu]\nrating: 5\ndone: true\naliases: []\nresult:\n---\n"
                "Előszó a lakóház felújításról.\n# Első\nAlma szöveg Körte.\n## Alcím\nBarack itt.\n# Második\n"
                "Alma és barack nincs együtt.\n- [ ] vegyél almát\n- [x] mosogass barackot\n- [/] félig kész alma\n"),
    "Masik.md": "---\nStatus: Folyamatban\nrating: 3\ntags: math\n---\n# Cím\nAlma Barack.\n- [ ] Alma feladat\n",
    "Nagy.md": "KISBETŰS Szöveg és szöveg. Tiszta lakóház.\n```\n# nem címsor\n- [ ] kódban feladat\n```\n- [ ] kívül [x]\n",
    "Idezet.md": "Szó [[wikilink]] és tömb[0] meg [x] jelölő.\n",
}


class KeresesBovitesTest(unittest.TestCase):
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
        return sorted(t["ut"] for t in self.ix.kereses(q)["talalatok"])

    def sorok(self, q, ut):
        for t in self.ix.kereses(q)["talalatok"]:
            if t["ut"] == ut:
                return [(h["sor"], h["szoveg"][h["oszlop"]:h["oszlop"] + h["hossz"]]) for h in t["talalatok"]]
        return None

    # ----------------------------------------------------------------------- 08-search-02, 03-properties-16
    def test_tulajdonsag_letezes_es_ertek(self):
        self.assertEqual(self.utak("[status]"), ["Alap.md", "Masik.md"])                  # a kulcs kis-nagybetűtől független
        self.assertEqual(self.utak("[STATUS:kesz]"), ["Alap.md"])                          # ékezet- és kisbetű-független részszöveg
        self.assertEqual(self.utak("[status:folyamat]"), ["Masik.md"])
        self.assertEqual(self.utak("[rating:5]"), ["Alap.md"])
        self.assertEqual(self.utak("[nincs]"), [])

    def test_tulajdonsag_lista_idezett_regex_vagy_null_logikai(self):
        self.assertEqual(self.utak("[tags:math]"), ["Alap.md", "Masik.md"])                # lista: elemenként; skalár is
        self.assertEqual(self.utak("[tags:history]"), ["Alap.md"])
        self.assertEqual(self.utak("[tags:#history/hu]"), ["Alap.md"])
        self.assertEqual(self.utak('[status:"Kész"]'), ["Alap.md"])
        self.assertEqual(self.utak("[rating:/^[35]$/]"), ["Alap.md", "Masik.md"])          # `]` a regex belsejében nem zár
        self.assertEqual(self.utak("[status:kész OR folyamatban]"), ["Alap.md", "Masik.md"])
        self.assertEqual(self.utak("[result:null]"), ["Alap.md"])                          # üres érték
        self.assertEqual(self.utak("[aliases:null]"), ["Alap.md"])
        self.assertEqual(self.utak("[status:null]"), [])
        self.assertEqual(self.utak("[done:true]"), ["Alap.md"])

    def test_tulajdonsag_kombinalhato_es_tagadhato(self):
        self.assertEqual(self.utak("[rating] alma"), ["Alap.md", "Masik.md"])
        self.assertEqual(self.utak("alma -[tags:history]"), ["Masik.md"])
        self.assertEqual(self.utak("([status:kész] OR [rating:3]) barack"), ["Alap.md", "Masik.md"])
        self.assertEqual(self.utak("[tags:math] file:masik"), ["Masik.md"])
        self.assertEqual(self.utak('section:([tags:math] alma)'), ["Alap.md", "Masik.md"])  # fájl-szintű feltétel al-kifejezésben

    def test_tulajdonsag_hibatur_es_regi_lekerdezes_valtozatlan(self):
        # nem feltétel: sima szó marad (a `[[…]]`, a szó közepi `[`, a lezáratlan, az üres)
        self.assertEqual(self.utak("[[wikilink]]"), ["Idezet.md"])
        self.assertEqual(self.utak("tömb[0]"), ["Idezet.md"])
        self.assertEqual(self.utak('[ezzaratlan'), [])
        self.assertEqual(kereses.elemez("[ezzaratlan"), ("szo", "[ezzaratlan"))
        self.assertEqual(kereses.elemez("[]"), ("szo", "[]"))
        self.assertEqual(kereses.elemez("[[a]]"), ("szo", "[[a]]"))
        self.assertEqual(kereses.elemez("[a:b]"), ("tul", "a", [("szo", "b")]))
        with self.assertRaises(Exception):
            kereses.elemez("[k:/(/]")                                                      # hibás regex ugyanúgy hiba

    # ----------------------------------------------------------------------- 08-search-03
    def test_match_case_es_ignore_case(self):
        self.assertEqual(self.utak("kisbetűs"), ["Nagy.md"])                               # alapból független
        self.assertEqual(self.utak("match-case:KISBETŰS"), ["Nagy.md"])
        self.assertEqual(self.utak("match-case:kisbetűs"), [])
        self.assertEqual(self.utak("match-case:(Szöveg)"), ["Nagy.md"])
        self.assertEqual(self.sorok("match-case:Szöveg", "Nagy.md"), [(1, "Szöveg")])      # a kisbetűs „szöveg” nem találat
        self.assertEqual(self.utak("match-case:szoveg"), [])                               # az ékezet is számít
        self.assertEqual(self.utak("match-case:(Alma Barack)"), ["Alap.md", "Masik.md"])
        self.assertEqual(self.utak("match-case:(Alma Barack) file:masik"), ["Masik.md"])
        self.assertEqual(self.utak("match-case:(alma Barack)"), ["Alap.md"])               # Alap.md-ben van kisbetűs „alma” és „Barack”
        self.assertEqual(self.utak('match-case:"Alma Barack"'), ["Masik.md"])
        self.assertEqual(self.utak("match-case:Alma -match-case:Barack file:masik"), [])
        self.assertEqual(self.utak("match-case:(ignore-case:kisbetűs)"), ["Nagy.md"])      # visszakapcsolás

    def test_match_case_fajlnev_ut_es_regex(self):
        self.assertEqual(self.utak("match-case:(path:masik)"), [])
        self.assertEqual(self.utak("match-case:(path:Masik)"), ["Masik.md"])
        self.assertEqual(self.utak("/kisbetűs/"), [])                                      # a regex alapból érzékeny (változatlan)
        self.assertEqual(self.utak("ignore-case:/kisbetűs/"), ["Nagy.md"])
        self.assertEqual(self.utak("ignore-case:(/KISBETŰS/ -/zzz/)"), ["Nagy.md"])
        self.assertEqual(self.utak("match-case:/Kisbet/"), [])

    # ----------------------------------------------------------------------- 08-search-07
    def test_feladat_operatorok(self):
        self.assertEqual(self.utak("task:alma"), ["Alap.md", "Masik.md"])
        self.assertEqual(self.utak("task-todo:alma"), ["Alap.md", "Masik.md"])
        self.assertEqual(self.utak("task-done:alma"), [])                                  # a `[/]` nem kész
        self.assertEqual(self.utak("task-done:barack"), ["Alap.md"])
        self.assertEqual(self.utak("task-todo:barack"), [])
        self.assertEqual(self.utak("task:(alma feladat)"), ["Masik.md"])
        self.assertEqual(self.utak("task-todo:(vegyél almát)"), ["Alap.md"])
        self.assertEqual(self.utak("task:kódban"), [])                                     # a kódblokkban álló nem feladat
        self.assertEqual(self.utak("task:kívül"), ["Nagy.md"])
        self.assertEqual(self.utak("task:cím"), [])                                        # a feladat szövegén kívül nem keres
        self.assertEqual(self.utak("barack -task:barack"), ["Masik.md"])                  # tagadás: a feladatban nem szereplő

    def test_feladat_talalati_sor_a_feladat_szovege(self):
        self.assertEqual(self.sorok("task-done:barack", "Alap.md"), [(17, "barack")])
        self.assertEqual(self.sorok("task-todo:alma", "Alap.md"), [(16, "almá")])
        self.assertEqual(self.sorok("task:/.*/", "Masik.md"), [(8, "Alma feladat")])

    # ----------------------------------------------------------------------- 08-search-08
    def test_szakasz_operator(self):
        self.assertEqual(self.utak("section:(alma barack)"), ["Alap.md", "Masik.md"])
        # Alap.md: az „Első” szakaszban (alcímmel együtt) van alma és barack; a „Második”-ban is (alma, barack)
        self.assertEqual(self.utak("section:(körte barack)"), ["Alap.md"])                 # az alcím a szülő szakaszához tartozik
        self.assertEqual(self.utak("section:(körte előszó)"), [])                          # a címsor előtti szöveg külön szakasz
        self.assertEqual(self.utak("section:(előszó lakóház)"), ["Alap.md"])
        self.assertEqual(self.utak("section:(status kész)"), [])                           # a frontmatter nem szakasz
        self.assertEqual(self.utak("section:(nem címsor)"), ["Nagy.md"])                   # címsor-tábla nélkül (a kódblokk `#` nem címsor): egész
        self.assertEqual(self.utak("section:(második barack)"), ["Alap.md"])               # a címsor a szakaszához tartozik
        self.assertEqual(self.utak("section:(első második)"), [])                          # különböző szakaszok
        self.assertEqual(self.utak("section:(alcím alma)"), ["Alap.md"])                  # a szülő szakasz az alcímet is tartalmazza
        self.assertEqual(self.utak("section:(második körte)"), [])                         # a „Második” szakasz nem éri el az „Első”-t

    def test_szakasz_talalati_sorok(self):
        s = self.sorok("section:(alma barack)", "Alap.md")
        self.assertIn((11, "Alma"), s)                                                      # az „Első” szakasz egyezései
        self.assertIn((13, "Barack"), s)
        self.assertIn((15, "Alma"), s)                                                      # a „Második” szakaszé
        self.assertNotIn((10, "Előszó"), s)
        t = self.sorok("section:(tag:#math)", "Alap.md")                                    # nincs szó-egyezés: a szakasz első sora jelölődik
        self.assertEqual(t[0], (9, "Előszó a lakóház felújításról."))

    # ----------------------------------------------------------------------- 08-search-11
    def test_reszszo_csupasz_szavakra(self):
        self.assertEqual(self.utak("ház"), [])                                              # alapból szókezdet (változatlan)
        self.assertEqual(self.utak("*ház"), ["Alap.md", "Nagy.md"])                         # lakóház
        self.assertEqual(self.utak("*ház alma"), ["Alap.md"])
        self.assertEqual(self.utak("substring:ház"), ["Alap.md", "Nagy.md"])
        self.assertEqual(self.utak("substring:(ház OR tisz)"), ["Alap.md", "Nagy.md"])
        self.assertEqual(self.utak("substring:(lak ház)"), ["Alap.md", "Nagy.md"])
        self.assertEqual(self.utak('substring:"ház"'), [])                                  # a kifejezés teljes szavakat illeszt
        self.assertEqual(self.sorok("*bet", "Nagy.md"), [(1, "BET")])
        self.assertEqual(self.utak("match-case:(substring:BETŰ)"), ["Nagy.md"])
        self.assertEqual(self.utak("match-case:(substring:betű)"), [])
        self.assertEqual(self.utak("-*ház alma"), ["Masik.md"])

    def test_fts_elofilter_az_uj_operatoroknal(self):
        self.assertEqual(kereses._fts(kereses.elemez("section:(alma barack)")), '("alma"*) AND ("barack"*)')
        self.assertEqual(kereses._fts(kereses.elemez("match-case:Alma")), '"alma"*')
        self.assertIsNone(kereses._fts(kereses.elemez("[status:kész]")))
        self.assertIsNone(kereses._fts(kereses.elemez("*ház")))
        self.assertIsNone(kereses._fts(kereses.elemez("substring:(ház)")))
        self.assertIsNone(kereses._fts(kereses.elemez("substring:(ház alma)")))              # az infix szóhoz nincs előtag-szűrő
        self.assertEqual(kereses._fts(kereses.elemez('substring:("ház a" alma)')), '("haz a")')

    # ----------------------------------------------------------------------- kompatibilitás és hibrid
    def test_regi_lekerdezesek_ugyanazt_adjak(self):
        ELVART = {
            "alma": ["Alap.md", "Masik.md"],
            "alma -barack": [],
            "line:(alma körte)": ["Alap.md"],
            "tag:#math": ["Alap.md", "Masik.md"],
            '"szöveg és"': ["Nagy.md"],
            "path:/^M/": ["Masik.md"],
        }
        for q, v in ELVART.items():
            self.assertEqual(self.utak(q), v, q)

    def test_hibrid_felismeri_az_uj_operatorokat(self):
        for q in ("section:(a b)", "task-todo:alma", "match-case:Alma", "ignore-case:x", "[status:kész]", "*ház", "substring:x"):
            self.assertTrue(normal.operatoros(q), q)
        for q in ("mi a helyzet a házzal", "alma és körte", "2 * 3 szorzás"):
            self.assertFalse(normal.operatoros(q), q)
        self.assertEqual(kereso.szabad_szoveg("section:(alma barack) [status:kész] task:foo *ház"), "alma barack foo ház")
        self.assertEqual(kereso.szabad_szoveg("match-case:(Alma)"), "Alma")

    def test_a_kornyezet_es_a_limit_az_uj_operatoroknal_is_mukodik(self):
        r = self.ix.kereses("section:(alma barack)", 1, 1)
        self.assertEqual(len(r["talalatok"]), 1)
        self.assertTrue(r["legalabb"])
        h = r["talalatok"][0]["talalatok"][0]
        self.assertIn("elotte", h)

    def test_hibrid_kornyezet_atmegy_a_lexikai_agon(self):
        k = kereso.HibridKereso(self.ix._olvaso)
        for q, mod in (("section:(alma barack)", "hibrid"), ("alma", "lexikai")):
            r = k.keres(q, 10, mod, 2)
            hely = next(h for t in r["talalatok"] for h in t["talalatok"])
            self.assertIn("elotte", hely, q)
            self.assertIn("utana", hely, q)
        self.assertNotIn("elotte", next(h for t in k.keres("alma", 10, "lexikai")["talalatok"] for h in t["talalatok"]))


class NagyDokumentumTest(unittest.TestCase):
    """Teljesítmény-ellenőrzés: egy nagy jegyzet (sok címsor, feladat, tulajdonság) az új operátorokkal is belefér az időkeretbe."""

    @classmethod
    def setUpClass(cls):
        sorok = ["---", "status: nagy", "tags: [a, b]", "---", "eleje"]
        for i in range(4000):
            sorok += [f"## Fej {i}", f"szöveg {i} alma{' barack' if i % 7 == 0 else ''}", f"- [ ] feladat {i}",
                      f"- [x] kész {i}", ""]
        cls._t = tmpdir()
        cls.cfg, cls.v = alvault(cls._t.name, {".obsidian/app.json": "{}", "Nagy.md": "\n".join(sorok) + "\n"})
        cls.ix, _ = index_indit(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.ix.leallit()
        cls._t.cleanup()

    def test_az_uj_operatorok_gyorsak_nagy_jegyzeten(self):
        import time
        for q in ("section:(alma barack)", "task-done:(kész 3999)", "[status:nagy] task-todo:feladat", "*lma"):
            t0 = time.monotonic()
            r = self.ix.kereses(q, 1000)
            self.assertLess(time.monotonic() - t0, 5.0, q)
            self.assertEqual(len(r["talalatok"]), 1, q)
            self.assertGreaterEqual(len(r["talalatok"][0]["talalatok"]), 1, q)
        r = self.ix.kereses("section:(alma barack)", 1000)
        self.assertEqual(len(r["talalatok"][0]["talalatok"]), kereses.MAX_SOR)               # a megjelenített találatok száma korlátos


if __name__ == "__main__":
    unittest.main()
