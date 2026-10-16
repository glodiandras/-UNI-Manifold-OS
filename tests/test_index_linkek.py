"""A link-segédek (`core/index/linkek.py`) és az index link-API-ja (C10): rövid cél, fejezet- és blokk-horgony,
a nyers szövegen dolgozó link-találatok (a gráf link-halmazával azonosak), beágyazás-szelet, aliasok, és
hogy az új feloldás-API ugyanazt adja, mint a C06 gráfja (L42)."""
import unittest

from core.index import feloldas, linkek
from core.index.feloldas import Feloldo
from core.vaultio import Invalid, NotFound
from tests.index_segedek import ALAP, alvault, index_indit
from tests.helpers import tmpdir


class RovidCelTest(unittest.TestCase):
    def setUp(self):
        self.f = Feloldo(["A/Jegyzet.md", "B/Jegyzet.md", "Cél.md", "C/kep.png", "AB/Jegyzet.md", "D/E/Mély.md"])

    def test_egyedi_nev_rovid(self):
        self.assertEqual(linkek.rovid_cel(self.f, "Cél.md", "A/x.md"), "Cél")
        self.assertEqual(linkek.rovid_cel(self.f, "C/kep.png", "x.md"), "kep.png")
        self.assertEqual(linkek.rovid_cel(self.f, "D/E/Mély.md", "x.md"), "Mély")

    def test_kozeli_azonos_alapnev_a_forras_mappajabol_rovid(self):
        self.assertEqual(linkek.rovid_cel(self.f, "B/Jegyzet.md", "B/Forrás.md"), "Jegyzet")

    def test_kétertelmunel_utvonal(self):
        self.assertEqual(linkek.rovid_cel(self.f, "B/Jegyzet.md", "C/x.md"), "B/Jegyzet")
        self.assertEqual(linkek.rovid_cel(self.f, "AB/Jegyzet.md", "C/x.md"), "AB/Jegyzet")

    def test_mindig_a_celra_oldodik(self):
        for ut in ("A/Jegyzet.md", "B/Jegyzet.md", "AB/Jegyzet.md", "Cél.md"):
            for forras in ("A/x.md", "B/x.md", "x.md", "Q/x.md"):
                szoveg = linkek.rovid_cel(self.f, ut, forras)
                self.assertEqual(self.f.resolve(szoveg, forras)[0], ut, (ut, forras, szoveg))


class HorgonyTest(unittest.TestCase):
    FEJ = [(1, "Cím", 1), (2, "Első **fontos** rész", 3), (3, "Mély", 5), (2, "Másik: rész", 8), (1, "Vég", 12)]

    def test_fejezet_szakasza(self):
        self.assertEqual(linkek.fejezet_tartomany(self.FEJ, 14, "Cím"), (1, 11))
        self.assertEqual(linkek.fejezet_tartomany(self.FEJ, 14, "Első fontos rész"), (3, 7))
        self.assertEqual(linkek.fejezet_tartomany(self.FEJ, 14, "Mély"), (5, 7))
        self.assertEqual(linkek.fejezet_tartomany(self.FEJ, 14, "Vég"), (12, 14))

    def test_egyeztetes_kisbetu_szokoz_jelek(self):
        self.assertEqual(linkek.fejezet_tartomany(self.FEJ, 14, "  első   FONTOS rész "), (3, 7))
        self.assertEqual(linkek.fejezet_tartomany(self.FEJ, 14, "Másik rész"), (8, 11))      # a `:` szóközzé válik
        self.assertIsNone(linkek.fejezet_tartomany(self.FEJ, 14, "Nincs ilyen"))

    def test_egymasba_agyazott_ut(self):
        self.assertEqual(linkek.fejezet_tartomany(self.FEJ, 14, "Első fontos rész#Mély"), (5, 7))
        self.assertIsNone(linkek.fejezet_tartomany(self.FEJ, 14, "Másik rész#Mély"))

    def test_blokk_listaelem_gyerekekkel(self):
        sorok = ["- a ^id", "  - b", "  - c", "", "  - d", "- e", "szöveg"]
        self.assertEqual(linkek.blokk_tartomany(sorok, 1, 1), (1, 5))
        self.assertEqual(linkek.blokk_tartomany(["bekezdés ^x", "másik"], 1, 1), (1, 1))
        self.assertEqual(linkek.blokk_tartomany(sorok, 6, 6), (6, 6))


class TalalatokTest(unittest.TestCase):
    SZOVEGEK = [
        "[[A]] ![[B#h|3]] [[ C ]] `[[K]]` [x](y.md#z) [w](https://q) [[V\\|alias]] [[lezáratlan\n",
        "---\nSource: \"[[P]]\"\n---\n```\n[[Z]]\n```\n[[Q]]\r\n[[R]]\r[[S]]\n",
        "| [[Cél\\|x]] | [[Cél\\#h\\|y]] |\n",
        "",
    ]

    def test_ugyanaz_a_halmaz_es_sorrend_mint_a_grafnal(self):
        for sz in self.SZOVEGEK:
            nyers = sz.encode("utf-8")
            t = linkek.jegyzet_talalatok(linkek.dekodol(nyers))
            self.assertEqual([x.cel for x in t], feloldas.jegyzet_celok(feloldas.szoveg(nyers)), sz)

    def test_a_cel_szakasz_helye_a_nyers_szovegben(self):
        sz = "x [[ Cél ]] y\r\n[[Név\\|a]]\r\n"
        t = linkek.jegyzet_talalatok(sz)
        self.assertEqual([sz[x.kezd:x.veg] for x in t], [" Cél ", "Név"])      # a `\\` az elválasztóé
        self.assertEqual(linkek.cel_resz(" Cél "), (" ", "Cél", " "))

    def test_kodmaszk(self):
        t = linkek.jegyzet_talalatok("`[[A]]` [[B]]\n```\n[[C]]\n```\n")
        self.assertEqual([x.cel for x in t], ["B"])

    def test_normalizalt_terkep(self):
        n, t = linkek.normalizalt("a\r\nb\rc\nd")
        self.assertEqual(n, "a\nb\nc\nd")
        self.assertEqual([t[i] for i in range(len(n))], [0, 1, 3, 4, 5, 6, 7])
        self.assertEqual(t[-1], 8)

    def test_surrogateescape_koruton(self):
        b = b"[[C\xc3\xa9l]] \xff\xfe"
        self.assertEqual(linkek.kodol(linkek.dekodol(b)), b)

    def test_uj_cel_szoveg_stilus(self):
        self.assertEqual(linkek.uj_cel_szoveg("Cél", "A/Új.md")[0], "Új")
        self.assertEqual(linkek.uj_cel_szoveg("Cél.md", "A/Új.md")[0], "Új.md")
        self.assertEqual(linkek.uj_cel_szoveg("A/Cél", "B/Új.md")[0], "B/Új")
        self.assertEqual(linkek.uj_cel_szoveg("/A/Cél", "B/Új.md")[0], "/B/Új")
        self.assertEqual(linkek.uj_cel_szoveg("Cél\\", "Új.md")[0], "Új")
        self.assertEqual(linkek.uj_cel_szoveg("kep.png", "x/kep2.png")[0], "kep2.png")


class CanvasTest(unittest.TestCase):
    C = '{"nodes":[{"id":"1","type":"file","file":"A/B.md","subpath":"#x"},{"id":"2","type":"text","text":"[[T]] \\"q\\""}],"edges":[]}'

    def test_stringek(self):
        ki = linkek.canvas_stringek(self.C)
        self.assertEqual([(k, e) for _, _, e, k, _ in ki if k in ("file", "text", "subpath")],
                         [("file", "A/B.md"), ("subpath", "#x"), ("text", '[[T]] "q"')])
        for kezd, veg, ertek, _, _ in ki:
            self.assertEqual(self.C[kezd:veg], linkek.json_literal(ertek) if ertek != '[[T]] "q"' else self.C[kezd:veg])
        self.assertEqual(len(linkek.canvas_talalatok(self.C)), 2)


class IndexLinkApiTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        fajlok = dict(ALAP)
        fajlok["Hosszú.md"] = ("---\naliases: [Hosszúság]\n---\n# Cím\nbevezető\n\n## Első\nszöveg ^b1\n\n- elem ^l1\n  - gyerek\n"
                               "- másik\n\n## Második\nvég\n")
        self.cfg, _ = alvault(self._t.name, fajlok)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)

    def test_feloldas_egyezik_a_grafal(self):
        """Minden link nyers céljára az új API ugyanazt oldja fel, mint amit az index a gráfhoz tárolt (L42)."""
        db = 0
        for r in self.ix.link_sorok():
            e = self.ix.feloldas(r["forras"], [r["cel_nyers"] or ""])[0]
            self.assertEqual(e["ut"], r["cel"], (r["forras"], r["cel_nyers"]))
            db += 1
        self.assertGreater(db, 20)

    def test_feloldas_hibak(self):
        self.assertEqual(self.ix.feloldas("A/Forrás.md", ["Jegyzet", "nincs", ""])[0]["ut"], "A/Jegyzet.md")
        self.assertIsNone(self.ix.feloldas("A/Forrás.md", ["nincs"])[0]["ut"])
        with self.assertRaises(Invalid):
            self.ix.feloldas("A/Forrás.md", "nem lista")
        with self.assertRaises(Invalid):
            self.ix.feloldas("../x.md", ["a"])

    def test_link_cel(self):
        self.assertEqual(self.ix.link_cel("Cél.md", "A/x.md")["cel"], "Cél")
        self.assertEqual(self.ix.link_cel("B/Jegyzet.md", "C/x.md")["cel"], "B/Jegyzet")
        self.assertEqual(self.ix.link_cel("kep.png", "C/x.md")["cel"], "kep.png")
        with self.assertRaises(NotFound):
            self.ix.link_cel("nincs.md", "x.md")

    def test_beallitott_relativ_link_a_valodi_indexbol(self):
        self.ix.cfg.data["beallitasok"]["fajlok"]["link_formatum"] = "relativ"
        self.assertEqual(self.ix.link_cel("B/Jegyzet.md", "A/Forrás.md")["cel"], "../B/Jegyzet")
        self.assertEqual(self.ix.feloldas("A/Forrás.md", ["../B/Jegyzet"])[0]["ut"], "B/Jegyzet.md")

    def test_aliasok(self):
        a = self.ix.aliasok()["aliasok"]
        self.assertEqual(a["Hosszú.md"], ["Hosszúság"])
        self.assertEqual(a["Cél.md"], ["Célpont"])
        self.assertNotIn("Cél X.md", a)

    def test_beagyazas_jegyzet_frontmatter_nelkul(self):
        b = self.ix.beagyazas("x.md", "Hosszú")
        self.assertEqual((b["tipus"], b["ut"]), ("jegyzet", "Hosszú.md"))
        self.assertTrue(b["szoveg"].startswith("# Cím\n"))
        self.assertNotIn("aliases", b["szoveg"])

    def test_beagyazas_fejezet_es_blokk(self):
        b = self.ix.beagyazas("x.md", "Hosszú", "Első")
        self.assertEqual(b["szoveg"], "## Első\nszöveg ^b1\n\n- elem ^l1\n  - gyerek\n- másik\n")
        b = self.ix.beagyazas("x.md", "Hosszú", "^b1")
        self.assertEqual(b["szoveg"], "szöveg ^b1")
        b = self.ix.beagyazas("x.md", "Hosszú", "^l1")
        self.assertEqual(b["szoveg"], "- elem ^l1\n  - gyerek")
        b = self.ix.beagyazas("x.md", "Hosszú", "Cím#Második")
        self.assertEqual(b["szoveg"], "## Második\nvég\n")
        b = self.ix.beagyazas("x.md", "Hosszú", "Nincs")
        self.assertTrue(b["alcel_hiba"])
        self.assertEqual(self.ix.beagyazas("x.md", "Hosszú", "^nincs")["szoveg"], "")

    def test_beagyazas_tipusok(self):
        self.assertEqual(self.ix.beagyazas("x.md", "kep.png")["tipus"], "kep")
        self.assertEqual(self.ix.beagyazas("x.md", "doc.pdf", "page=3"),
                         {"tipus": "pdf", "ut": "doc.pdf", "tobbertelmu": False, "alcel": "page=3"})
        self.assertEqual(self.ix.beagyazas("x.md", "Vaszon.canvas")["tipus"], "canvas")
        self.assertEqual(self.ix.beagyazas("x.md", "nincs-ilyen"), {"tipus": "nincs", "cel": "nincs-ilyen"})


if __name__ == "__main__":
    unittest.main()
