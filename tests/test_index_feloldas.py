"""A link-feloldás és a gráf (C06, L42; C10.6): az Obsidian-sorrend, a régi selftest 14–15 esete, a
kis-nagybetűtől független menet és a szegmenshatár (13. döntés), a maszk, és a paritás új alakja: a
gráf a régi szabálytól **pontosan a dokumentált eltérésekben** tér el (`tests/legacy_szabaly.py`: a régi szabály
befagyasztott másolata). A másolat hűségét a régi eszköztárral a kézi kapu őrzi (`tests/kezi/graf_paritas.py`, `MOS_LEGACY`).
"""
import unittest

from core.index import feloldas
from core.index.feloldas import Feloldo, graf, graf_kanonikus, jegyzet_celok, mask_code
from tests import legacy_szabaly
from tests.helpers import tmpdir
from tests.index_segedek import ELTERES, NFD, alvault, index_indit


class FeloldoTest(unittest.TestCase):
    def setUp(self):
        self.f = Feloldo(["A/Jegyzet.md", "B/Jegyzet.md", "Cél.md", "X01 - Napló/2026-09-12.md",
                          "AI02 - Log/2026-09-12.md", "kep.png", "AB/Jegyzet.md"])

    def cel(self, t, src="C/x.md"):
        return self.f.resolve(t, src)[0]

    def test_azonos_alapnev_a_forras_mappaja_nyer(self):          # legacy selftest 15
        self.assertEqual(self.cel("Jegyzet", "B/Forrás.md"), "B/Jegyzet.md")
        self.assertEqual(self.cel("2026-09-12", "X01 - Napló/00 - Index.md"), "X01 - Napló/2026-09-12.md")
        self.assertEqual(self.cel("Jegyzet", "C/x.md"), "A/Jegyzet.md")         # a rövidebb, majd a kisebb út
        self.assertTrue(self.f.resolve("Jegyzet", "C/x.md")[2])                 # többértelmű

    def test_escapelt_alias_es_ut_alakok(self):                     # legacy selftest 14
        self.assertEqual(self.cel("Cél\\"), "Cél.md")
        self.assertEqual(self.cel("B/Jegyzet"), "B/Jegyzet.md")
        self.assertEqual(self.cel("/A/Jegyzet"), "A/Jegyzet.md")
        self.assertEqual(self.cel("A\\Jegyzet"), "A/Jegyzet.md")
        self.assertEqual(self.cel(" Cél "), "Cél.md")
        self.assertEqual(self.cel("kep.png"), "kep.png")
        self.assertEqual(self.cel("kep.PNG"), "kep.png")                         # kis-nagybetűtől független (C10.6)
        self.assertIsNone(self.cel(""))
        self.assertIsNone(self.cel("Z/Jegyzet"))

    def test_inkrementalis_hozzaadas_es_elvetel(self):
        self.f.elvesz("A/Jegyzet.md")
        self.assertEqual(self.cel("Jegyzet", "C/x.md"), "B/Jegyzet.md")
        self.f.elvesz("B/Jegyzet.md")
        self.assertEqual(self.cel("Jegyzet", "C/x.md"), "AB/Jegyzet.md")
        self.f.elvesz("AB/Jegyzet.md")
        self.assertIsNone(self.cel("Jegyzet"))
        self.f.hozzaad("D/Jegyzet.md")
        self.assertEqual(self.cel("Jegyzet"), "D/Jegyzet.md")

    def test_kodmaszk_es_celok(self):
        t = "a `[[K]]` b\n```\n[[K2]]\n```\n[[V]] [x](y.md#z) [w](https://q) ![[E|3]] [[F#h]]"
        self.assertEqual(len(mask_code(t)), len(t))
        self.assertEqual(jegyzet_celok(t), ["V", "E", "F", "y.md"])

    def test_celkulcs(self):
        self.assertEqual(feloldas.celkulcs(" A\\B\\ "), "b")                      # kisbetűs: az újrafeloldás kulcsa
        self.assertEqual(feloldas.celkulcs("/x/Y.md"), "y.md")
        self.assertEqual(feloldas.celkulcs("Ütőér"), "ütőér")


class KisNagybetuEsSzegmensTest(unittest.TestCase):
    """C10.6 (13. döntés): kis-nagybetűtől független feloldás, a pontos találat előnyével; szegmenshatár."""

    def setUp(self):
        self.f = Feloldo(["Cél.md", "A/Jegyzet.md", "B/jegyzet.md", "yx/A.md", "Mappa/Ütőér.md", "kep.PNG",
                          "X/Readme.md", "Y/README"])

    def cel(self, t, src="C/x.md"):
        return self.f.resolve(t, src)[0]

    def test_kis_nagybetutol_fuggetlen(self):
        self.assertEqual(self.cel("cél"), "Cél.md")
        self.assertEqual(self.cel("CÉL"), "Cél.md")
        self.assertEqual(self.cel("cél.MD"), "Cél.md")
        self.assertEqual(self.cel("kep.png"), "kep.PNG")
        self.assertEqual(self.cel("mappa/ÜTŐÉR"), "Mappa/Ütőér.md")
        self.assertEqual(self.cel("/MAPPA/ütőér"), "Mappa/Ütőér.md")
        self.assertIsNone(self.cel("Cel"))                                       # az ékezet számít
        self.assertIsNone(self.cel("Utoer"))

    def test_a_pontos_talalat_elonyt_kap(self):
        # két fájl csak kis-nagybetűben tér el: a pontosan egyező nyer, a forrás mappájától függetlenül
        self.assertEqual(self.cel("Jegyzet", "B/Forrás.md"), "A/Jegyzet.md")
        self.assertEqual(self.cel("jegyzet", "A/Forrás.md"), "B/jegyzet.md")
        self.assertFalse(self.f.resolve("Jegyzet", "B/Forrás.md")[2])
        # ha egyik sem pontos: a forrás mappája, azután a rövidebb út dönt, és többértelmű
        self.assertEqual(self.f.resolve("JEGYZET", "B/Forrás.md"), ("B/jegyzet.md", "jegyzet.md", True))
        self.assertEqual(self.f.resolve("JEGYZET", "C/x.md")[0], "A/Jegyzet.md")
        # a pontos `.md`-tartalék megelőzi a kisbetűs, kiterjesztés nélküli egyezést
        self.assertEqual(self.cel("Readme"), "X/Readme.md")
        self.assertEqual(self.cel("README"), "Y/README")
        self.assertEqual(self.cel("readme"), "Y/README")

    def test_szegmenshatar(self):
        self.assertIsNone(self.cel("x/A"))                                       # nem a `yx/A.md`
        self.assertIsNone(self.cel("X/a"))
        self.assertEqual(self.cel("yx/A"), "yx/A.md")
        self.assertEqual(self.cel("YX/a"), "yx/A.md")
        f = Feloldo(["yx/A.md", "x/A.md", "q/x/A.md"])
        self.assertEqual(f.resolve("x/A", "C/x.md"), ("x/A.md", "A.md", False))  # a teljes út egyezése
        f = Feloldo(["yx/A.md", "q/x/A.md", "r/x/A.md"])
        self.assertEqual(f.resolve("x/A", "r/n.md"), ("r/x/A.md", "A.md", True))  # a `yx/A.md` nem jelölt

    def test_inkrementalis(self):
        self.f.elvesz("A/Jegyzet.md")
        self.assertEqual(self.cel("Jegyzet"), "B/jegyzet.md")
        self.f.elvesz("B/jegyzet.md")
        self.assertIsNone(self.cel("jegyzet"))
        self.assertNotIn("jegyzet.md", self.f.by_low)
        self.f.hozzaad("D/JEGYZET.md")
        self.assertEqual(self.cel("Jegyzet"), "D/JEGYZET.md")


class GrafTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name)

    def test_bejaras_a_legacy_szabalyaval(self):
        utak = [rp for rp, _ in feloldas.bejaras(self.v)]
        self.assertIn(".rejtett-mappa/Latszik.md", utak)
        for kimarad in (".trash/Kidobott.md", "node_modules/x/Y.md", ".rejtett.md", ".obsidian/app.json"):
            self.assertNotIn(kimarad, utak)
        self.assertIn("Ütőér.md", utak)                                          # NFC, a lemezen NFD
        self.assertTrue(any(n == NFD + ".md" for _, n in feloldas.bejaras(self.v)))

    def test_graf_elei(self):
        g = graf(self.v)
        self.assertEqual(g["out"]["X01 - Napló/00 - Index.md"], {"X01 - Napló/2026-09-12.md"})
        self.assertIn("Cél.md", g["out"]["Tabla.md"])
        self.assertIn("Ütőér.md", g["out"]["Linkek.md"])
        self.assertIn("Linkek.md", g["out"]["Linkek.md"])                         # önhurok
        self.assertNotIn("Kódban", g["unresolved"])
        self.assertIn("nincs ilyen", g["unresolved"])
        self.assertNotIn("Cél%20X.md", g["unresolved"])                           # C31 (36.): az md-link dekódolva
        self.assertIn("Cél X.md", g["out"]["Linkek.md"])
        self.assertEqual(g["out"]["Vaszon.canvas"], {"Cél.md", "A/Jegyzet.md"})
        self.assertEqual({x[0] for x in g["canvas_hiba"]}, {"Rossz.canvas", "Bajt.canvas"})
        self.assertEqual(g["tobbertelmu"]["Jegyzet.md"], 4)     # A/Forrás 1 + C/Hivo 3

    def test_az_index_grafja_azonos_a_lemezevel(self):
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        self.assertEqual(graf_kanonikus(ix.graf()), graf_kanonikus(graf(self.v)))

    def test_inkrementalis_graf_azonos_a_teljes_ujraepitessel(self):
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        (self.v / "C" / "Jegyzet.md").write_text("[[Cél]]")                       # új azonos alapnév a hívó mappájában
        (self.v / "Cél X.md").unlink()
        (self.v / "A" / "Jegyzet.md").rename(self.v / "A" / "Jegyzet2.md")
        (self.v / "nincs ilyen.md").write_text("most már van")
        (self.v / "B").rename(self.v / "B2")
        ix.frissit(["C/Jegyzet.md", "Cél X.md", "A/Jegyzet.md", "A/Jegyzet2.md", "nincs ilyen.md", "B", "B2"])
        self.assertEqual(graf_kanonikus(ix.graf()), graf_kanonikus(graf(self.v)))


class IndexKisNagybetuTest(unittest.TestCase):
    """Az index inkrementális újrafeloldása a kisbetűs kulccsal: a gráf mindig a lemezről számolttal azonos."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, ELTERES)

    def test_uj_fajl_feloldja_a_mas_betuzesu_linket(self):
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        self.assertEqual(graf_kanonikus(ix.graf()), graf_kanonikus(graf(self.v)))
        (self.v / "Hivo.md").write_text("[[új jegyzet]] [[MAPPA/ÚJ JEGYZET]] [[Új Jegyzet]]")
        ix.frissit(["Hivo.md"])
        self.assertNotIn("Hivo.md", ix.graf()["out"])
        (self.v / "Mappa").mkdir()
        (self.v / "Mappa" / "Új Jegyzet.md").write_text("# új")
        ix.frissit(["Mappa/Új Jegyzet.md"])
        self.assertEqual(ix.graf()["out"]["Hivo.md"], {"Mappa/Új Jegyzet.md"})
        self.assertEqual(graf_kanonikus(ix.graf()), graf_kanonikus(graf(self.v)))
        (self.v / "Mappa" / "Új Jegyzet.md").unlink()
        ix.frissit(["Mappa/Új Jegyzet.md"])
        self.assertNotIn("Hivo.md", ix.graf()["out"])
        self.assertEqual(graf_kanonikus(ix.graf()), graf_kanonikus(graf(self.v)))


VART_ELTERESEK = [          # (osztály, forrás, sor, cél, régi találat, új találat)
    ("M+", "Elteres.md", 2, "Cél", None, "Cél.md"),                 # frontmatter: a YAML-ban nincs kódmaszk
    ("K", "Elteres.md", 4, "cél", None, "Cél.md"),
    ("K", "Elteres.md", 4, "CÉL X", None, "Cél X.md"),
    ("K", "Elteres.md", 4, "a/jegyzet", None, "A/Jegyzet.md"),
    ("S", "Elteres.md", 4, "x/A", "yx/A.md", None),
    ("M-", "Elteres.md", 6, "Tilde", None, None),                   # `~~~` kerítés
    ("M-", "Elteres.md", 8, "Dupla", None, None),                   # dupla backtick
    ("M-", "Elteres.md", 8, "1,2", None, None),                     # `$[[1,2],[3,4]]$`
    ("M-", "Elteres.md", 10, "Blokk", None, None),                  # `$$` blokk
    ("M-", "Elteres.md", 15, "Négy2", None, None),                  # négy backtickes kerítés belsejében ```
    ("M+", "Elteres2.md", 3, "Köztes", None, None),                 # a régi regex egy soron belüli ```-t párosított
    ("M-", "Elteres2.md", 6, "Kódban3", None, None),                # … és így a valódi blokk belseje látszott
    ("M-", "Elteres2.md", 10, "Lezáratlan", None, None),            # lezáratlan kerítés a szöveg végéig
    ("K", "Linkek.md", 7, "kep.PNG", None, "kep.png"),
    ("U", "Linkek.md", 8, "Cél X.md", None, "Cél X.md"),             # `[szóköz](Cél%20X.md)`: URL-dekódolva (36. döntés)
]


class MdCelTest(unittest.TestCase):
    """C31 (36. döntés, T072/K47): az md-link célja az Obsidian 1.14.4 md-elemzője szerint (statikus olvasás)."""

    def test_decode_uri_a_js_szerint(self):
        from core.index.feloldas import decode_uri
        self.assertEqual(decode_uri("C%C3%A9l%20X.md"), "Cél X.md")
        self.assertEqual(decode_uri("a%23b%2Fc%3F"), "a%23b%2Fc%3F")        # a fenntartott jelek kódolva maradnak
        self.assertEqual(decode_uri("100%25"), "100%")
        for rossz in ("a%2", "a%zz", "%C3", "%FF%FF", "%C3%28"):
            with self.assertRaises(ValueError, msg=rossz):
                decode_uri(rossz)

    def test_md_cel(self):
        from core.index.feloldas import md_cel, md_reszek
        self.assertEqual(md_cel("Cél%20X.md"), "Cél X.md")
        self.assertEqual(md_cel("<Cél X.md>"), "Cél X.md")
        self.assertEqual(md_cel(" < Cél X.md > "), "Cél X.md")
        self.assertEqual(md_reszek("Cél%20X.md#Fej%20ezet"), ("Cél X.md", "Fej ezet"))
        self.assertEqual(md_reszek("a%23b.md#c"), ("a%23b.md", "c"))           # a `%23` nem horgony-elválasztó
        self.assertEqual(md_cel("a\xa0b.md"), "a b.md")                        # NBSP → szóköz
        for kulso in ("http://x", "https://x", "mailto:a@b", "#fej", "<https://x>", "hibás%zz.md"):
            self.assertIsNone(md_cel(kulso), kulso)

    def test_md_kodol(self):
        from core.index.feloldas import md_cel, md_kodol
        self.assertEqual(md_kodol("Mappa/Cél X.md"), "Mappa/Cél%20X.md")       # az ékezet marad, a szóköz kódolt
        self.assertEqual(md_kodol("a\\b"), "a%5Cb")
        for s in ("Cél X.md", "Árvíztűrő tükör.md", "a%b.md".replace("%", "")):
            self.assertEqual(md_cel(md_kodol(s)), s)


class ElteresTest(unittest.TestCase):
    """Az új szabály a legacytől pontosan a dokumentált eltérésekben tér el (13. döntés) — legacy nélkül is fut."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def elteresek(self, fajlok=None):
        self.cfg, self.v = alvault(self._t.name, fajlok)
        return [(x["osztaly"], x["forras"], x["sor"], x["cel"], x["regi"], x["uj"])
                for x in legacy_szabaly.elteresek(self.v)]

    def test_az_alap_alvaulton_egyetlen_elteres(self):
        self.assertEqual(self.elteresek(), [("K", "Linkek.md", 7, "kep.PNG", None, "kep.png"),
                                            ("U", "Linkek.md", 8, "Cél X.md", None, "Cél X.md")])

    def test_az_elteres_alvaulton_pontosan_a_vart_lista(self):
        self.assertEqual(self.elteresek(ELTERES), VART_ELTERESEK)

    def test_a_graf_kulonbsege_az_elteresekbol_all(self):
        self.elteresek(ELTERES)
        regi, uj = legacy_szabaly.regi_graf(self.v), graf(self.v)
        self.assertEqual(regi["files"], uj["files"])
        self.assertEqual(regi["canvas_hiba"], uj["canvas_hiba"])
        self.assertEqual(uj["out"]["Elteres.md"] - regi["out"]["Elteres.md"], {"Cél X.md", "A/Jegyzet.md"})
        self.assertNotIn("x/A", regi["unresolved"])
        self.assertEqual(uj["unresolved"]["x/A"], 1)
        for cel in ("Tilde", "Dupla", "1,2", "Blokk", "Négy2", "Kódban3", "Lezáratlan", "cél", "kep.PNG"):
            self.assertIn(cel, regi["unresolved"])
            self.assertNotIn(cel, uj["unresolved"])
        self.assertIn("Köztes", uj["unresolved"])
        self.assertNotIn("Köztes", regi["unresolved"])


if __name__ == "__main__":
    unittest.main()
