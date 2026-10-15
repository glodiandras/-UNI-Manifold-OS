"""A Bases-kiértékelő (`core/bazis/kiertekelo.py`, C12 2. lépés): a „Kényszerítések” tábla minden sora kifejezésként,
névfeloldás, `this`, rollup, képletek (körkörös hivatkozás, hibaelszigetelés, memó), fordítási hibák."""
import math
import unittest

from core.bazis import ertekek as e
from core.bazis.ertekek import Cimke, Datum, Fajl, FutasHiba, Idotartam, Link
from core.bazis.kiertekelo import Kor, KepletTar, fordit_szoveg, futtat
from core.bazis.kifejezes import KifejezesHiba
from tests.bazis_segedek import MOST, ertek, sor, tabla


def D(s: str) -> Datum:
    return e.datum_szovegbol(s)


KONYV = sor("X03 - Books/Atomic Habits.md",
            {"Status": "Reading", "Author": "[[James Clear]]", "Rating": 4.5, "Pages": 320, "my prop": "szóközös",
             "image-property": "[[borito.jpg]]", "Due": ("date", "2026-10-01"), "Done": False,
             "Authors": ["[[James Clear]]", "[[Másik Szerző]]"], "Tags": ("tags", ["Book"]),
             "Ures": None, "Lista": ["a", "b"], "Projekt": "[[Projekt Egy]]", "NN": ["[[Rész 1]]", "[[Rész 2]]"]},
            cimkek=["Book"], linkek=["James Clear", "Projekt Egy"])
MASIK = sor("X03 - Books/Másik.md", {"Status": "Done", "Rating": 3, "Projekt": "[[Projekt Egy]]"}, cimkek=["Book", "x"],
            linkek=["Projekt Egy"])
SOROK = [KONYV, MASIK,
         sor("People/James Clear.md", {"Born": 1986}),
         sor("People/Másik Szerző.md"),
         sor("Projekt Egy.md", {"Status": "Active", "Ora": 10}),
         sor("Rész 1.md", {"Ora": 3}), sor("Rész 2.md", {"Ora": 4}),
         sor("Hivatkozo.md", linkek=["Atomic Habits"]),
         sor("borito.jpg", tipus="kep")]
T = tabla(SOROK)


def E(kif, s=KONYV, **kw):
    return ertek(kif, s, T, **kw)


class OperatorTabla(unittest.TestCase):
    def esetek(self, esetek):
        for kif, vart in esetek:
            with self.subTest(kif):
                v = E(kif)
                if isinstance(vart, float) and math.isnan(vart):
                    self.assertTrue(math.isnan(v))
                else:
                    self.assertEqual(v, vart)
                    self.assertIs(type(v) is bool, type(vart) is bool)

    def test_plusz(self):
        self.esetek([("1 + 2", 3), ('"a" + 1', "a1"), ('"a" + null', "a"), ('null + "a"', "a"),
                     ("null + 1", None), ("1 + null", None), ("null + null", None),
                     ('date("2024-12-01") + "1M"', D("2025-01-01")), ('date("2024-12-01") + duration("1d")', D("2024-12-02")),
                     ('"x" + [1, 2]', "x1,2"), ('1 + 1 + "a"', "2a"), ('"a" + 1 + 1', "a11"),
                     ("Pages + 1", 321), ('Status + "!"', "Reading!"), ("Ures + 1", None), ("Nincs + 1", None)])

    def test_minusz(self):
        self.esetek([("5 - 3", 2), ('date("2024-12-02") - date("2024-12-01")', 86400000),
                     ('date("2024-12-02") - "1d"', D("2024-12-01")), ("null - 1", None), ("Pages - 20", 300)])

    def test_szorzas_osztas_maradek(self):
        self.esetek([("2 * 3", 6), ("7 / 2", 3.5), ("7 % 4", 3), ("1 / 0", math.inf), ("-1 / 0", -math.inf),
                     ("0 / 0", math.nan), ("5 % 0", math.nan), ("duration('1h') * 2", Idotartam(0, 7_200_000))])

    def test_egyenloseg(self):
        self.esetek([("1 == 1", True), ('"a" == "a"', True), ('"a" == "A"', False), ("1 != 2", True),
                     ('[1, 2] == [1, 2]', True), ('[1, 2] == [2, 1]', False), ('file.tags == ["Book"]', True),
                     ('file.tags == ["book"]', True), ('file.tags == ["#Book"]', True), ('file.tags == ["Book", "x"]', False),
                     ('file.tags != ["Book"]', False), ("null == null", True), ("Ures == null", True), ("Nincs == null", True),
                     ('Author == link("James Clear")', True), ('Author == link("[[James Clear]]")', True),
                     ('Author == file("James Clear")', True), ('Author == "James Clear"', False),
                     ('Author == link("Másik Szerző")', False), ('link("Nincs") == link("Nincs")', True),
                     ('link("Nincs") == link("Más")', False), ("Due == date(\"2026-10-01\")", True),
                     ("Due == date(\"2026-10-01 00:00:00\")", True), ("0 == false", False), ('"1" == 1', False),
                     ("Done == false", True), ("Done != false", False),
                     ('Authors.contains(link("Másik Szerző"))', True), ('Authors.contains(file("James Clear"))', True)])

    def test_osszehasonlitas(self):
        self.esetek([("1 < 2", True), ("2 <= 2", True), ("3 > 2", True), ("2 >= 3", False), ('"a" < "b"', True),
                     ('"a" > "b"', False), ("Due < now()", True), ("Due > now()", False),
                     ('1 < "2"', False), ('1 >= "2"', False), ("null < 1", False), ("null >= 1", False),
                     ("1 < null", False), ("null <= null", False), ("true < false", False), ("[1] < [2]", False),
                     ('Due < "2026-12-01"', False), ("Rating > 4", True), ("Rating >= 4.5", True)])

    def test_logikai(self):
        self.esetek([("true && false", False), ("true || false", True), ("!true", False), ("!0", True),
                     ('!""', True), ("![]", False), ("!null", True), ("!Nincs", True), ('!"0"', False),
                     ("1 && 2", 2), ("0 && 2", 0), ("0 || 2", 2), ("1 || 2", 1), ('null || "x"', "x"),
                     ("Ures || Pages", 320), ("Pages && Rating", 4.5), ("false || false", False)])

    def test_roviditett_kiertekeles(self):
        # a második operandus hibás volna, de nem értékelődik
        self.esetek([("false && 1 + []", False), ("true || 1 + []", True),
                     ("null && [].nincs", None)])

    def test_unaris_minusz(self):
        self.esetek([("-Pages", -320), ("-(1 + 2)", -3), ("2 - -3", 5), ("-duration('1d')", Idotartam(0, -86400000))])

    def test_tipushibak(self):
        for kif in ("true + 1", "[1] + 1", "{} + 1", 'link("X") + 1', '"a" - 1', '"a" * 2', "[1] / 2", "{} % 2",
                    "true - true", '-"a"', "-[1]", "2 * duration('1d')", 'date("2024-01-01") * 2', "null * 2", "null / 2"):
            with self.subTest(kif):
                with self.assertRaises(FutasHiba):
                    E(kif)


class NevfeloldasTest(unittest.TestCase):
    def test_tulajdonsagok(self):
        for kif, vart in [("Status", "Reading"), ("note.Status", "Reading"), ('note["Status"]', "Reading"),
                          ("Rating", 4.5), ("status", "Reading"), ("note.status", "Reading"), ("RATING", 4.5),
                          ('note["my prop"]', "szóközös"), ("image-property", Link("borito.jpg", None, "borito.jpg")),
                          ("Nincs", None), ("note.Nincs", None), ("Nincs.x.y", None), ("Ures.x", None),
                          ("Lista[1]", "b"), ("Lista.length", 2), ('Tags', ["Book"]), ('Tags.contains("Book")', True)]:
            with self.subTest(kif):
                self.assertEqual(E(kif), vart)

    def test_a_tulajdonsag_tipusa(self):
        self.assertEqual(E("Due"), D("2026-10-01"))
        self.assertEqual(E("Due.year"), 2026)
        self.assertEqual(E("Author").ut, "People/James Clear.md")
        self.assertEqual(E("Authors").__len__(), 2)
        self.assertEqual(E("Author.asFile().properties.Born"), 1986)
        self.assertEqual(E("Authors.map(value.asFile().name)"), ["James Clear.md", "Másik Szerző.md"])

    def test_nem_jegyzet_sorban_nincs_tulajdonsag(self):
        kep = SOROK[-1]
        self.assertIsNone(ertek("Status", kep, T))
        self.assertEqual(ertek("file.ext", kep, T), "jpg")
        self.assertEqual(ertek("file.size", kep, T), 100)

    def test_sor_nelkuli_kornyezet(self):
        self.assertEqual(ertek("1 + 2"), 3)
        self.assertIsNone(ertek("Status"))
        self.assertIsNone(ertek("file.name"))
        self.assertIsNone(ertek("note.x"))

    def test_helyi_valtozo_elfedi_a_tulajdonsagot(self):
        self.assertEqual(E("[1].map(value)"), [1])
        s = sor("x.md", {"value": "tul"})
        self.assertEqual(ertek("value", s, tabla([s])), "tul")
        self.assertEqual(ertek("[1].map(value)", s, tabla([s])), [1])

    def test_sulyozott_kulcsok_pontos_elso(self):
        s = sor("x.md", {"a": 1, "A": 2})
        t = tabla([s])
        self.assertEqual((ertek("a", s, t), ertek("A", s, t)), (1, 2))


class ThisTest(unittest.TestCase):
    def ez(self, ut):
        return T.fajl(ut)

    def test_this_a_megadott_fajl(self):
        ez = self.ez("People/James Clear.md")
        self.assertEqual(E("this.file.name", ez=ez), "James Clear.md")
        self.assertEqual(E("this.file.folder", ez=ez), "People")
        self.assertEqual(E("this.note.Born", ez=ez), 1986)
        self.assertEqual(E('file.inFolder(this.file.folder)', ez=self.ez("X03 - Books/Másik.md")), True)

    def test_szerzo_egyenlo_this(self):
        ez = self.ez("People/James Clear.md")
        self.assertTrue(E("Author == this", ez=ez))
        self.assertTrue(E("Authors.contains(this)", ez=ez))
        self.assertFalse(E("Author == this", ez=self.ez("People/Másik Szerző.md")))

    def test_visszahivatkozasok_panel_mintaja(self):
        self.assertTrue(E("file.hasLink(this.file)", s=T.ut_szerint["Hivatkozo.md"], ez=self.ez("X03 - Books/Atomic Habits.md")))
        self.assertFalse(E("file.hasLink(this.file)", s=MASIK, ez=self.ez("X03 - Books/Atomic Habits.md")))

    def test_this_nelkul_ures(self):
        self.assertIsNone(E("this"))
        self.assertIsNone(E("this.file.name"))
        self.assertTrue(E("this == null"))


class RollupTest(unittest.TestCase):
    def test_rollup_uj_szintaxis_nelkul(self):
        self.assertEqual(E("Projekt.asFile().properties.Status"), "Active")
        self.assertEqual(E("Projekt.asFile().properties.Ora * 2"), 20)
        self.assertEqual(E("list(NN).map(value.asFile().properties.Ora).reduce(acc + value, 0)"), 7)
        self.assertEqual(E("NN.map(value.asFile().properties.Ora).sort()"), [3, 4])
        self.assertEqual(E("file.backlinks.map(value.name)"), ["Hivatkozo.md"])
        self.assertEqual(E("file.backlinks.filter(value.name.startsWith(\"H\")).length"), 1)
        self.assertEqual(E('file("Projekt Egy").backlinks.map(value.name).sort()'), ["Atomic Habits.md", "Másik.md"])

    def test_rollup_a_tabla_sorain_at_mas_jegyzet_tulajdonsagai_eleresek(self):
        self.assertEqual(E('file("Rész 2").properties.Ora'), 4)
        self.assertEqual(E('file("Nincs").properties.Ora'), None)

    def test_nincs_link_nincs_hiba(self):
        s = sor("y.md", {"NN": None})
        self.assertEqual(ertek("list(NN).map(value.asFile().properties.Ora).reduce(acc + value, 0)", s, tabla([s])), 0)


class KepletTest(unittest.TestCase):
    def kepletek(self, kif, d, s=KONYV):
        return ertek(kif, s, T, kepletek=d)

    def test_alap_es_egymasra_hivatkozas(self):
        k = {"ppu": "(Rating / 2).toFixed(2)", "dupla": "Pages * 2", "negyszeres": "formula.dupla * 2",
             "szoveg": 'formula.negyszeres + " oldal"'}
        self.assertEqual(self.kepletek("formula.ppu", k), "2.25")
        self.assertEqual(self.kepletek("formula.negyszeres", k), 1280)
        self.assertEqual(self.kepletek('formula["szoveg"]', k), "1280 oldal")
        self.assertEqual(self.kepletek("formula.dupla > 600 && formula.negyszeres < 2000", k), True)

    def test_korkoros_hivatkozas_csak_a_korben_allokat_erinti(self):
        k = {"a": "formula.b + 1", "b": "formula.c + 1", "c": "formula.a + 1", "d": "formula.a", "e": "Pages"}
        for n in "abc":
            with self.assertRaises(FutasHiba, msg=n) as r:
                self.kepletek(f"formula.{n}", k)
            self.assertIn("körkörös", r.exception.uzenet)
        with self.assertRaises(FutasHiba) as r:
            self.kepletek("formula.d", k)             # a körre hivatkozó képlet hibás, de nem része a körnek
        self.assertEqual(self.kepletek("formula.e", k), 320)

    def test_onhivatkozas(self):
        with self.assertRaises(FutasHiba):
            self.kepletek("formula.x", {"x": "formula.x + 1"})

    def test_hibas_kepelt_nem_dont_el_a_tobbit(self):
        k = {"rossz": "1 +", "jo": "1 + 1", "fut_hiba": "[] + 1", "ismeretlen": "nincs_fn(1)"}
        self.assertEqual(self.kepletek("formula.jo", k), 2)
        for n in ("rossz", "fut_hiba", "ismeretlen"):
            with self.assertRaises(FutasHiba, msg=n):
                self.kepletek(f"formula.{n}", k)

    def test_hibas_kepletre_hivatkozo_kepelt_is_hibas_az_eredeti_uzenettel(self):
        k = {"rossz": "[] + 1", "tovabb": "formula.rossz + 1"}
        with self.assertRaises(FutasHiba) as r:
            self.kepletek("formula.tovabb", k)
        self.assertIn("nem összeadható", r.exception.uzenet)

    def test_nincs_ilyen_kepelt(self):
        with self.assertRaises(FutasHiba):
            self.kepletek("formula.nincs", {"x": "1"})
        with self.assertRaises(FutasHiba):
            E("formula.nincs")

    def test_kepelt_tiszta_helyi_kornyezetben_fut(self):
        k = {"x": "value"}                             # a `value` itt tulajdonság, nem a lista eleme
        self.assertEqual(self.kepletek("[1, 2].map(formula.x)", k), [None, None])

    def test_soronkent_egyszer_szamolodik(self):
        k = {"r": "random()", "ket_r": "formula.r == formula.r"}
        self.assertTrue(self.kepletek("formula.ket_r", k))
        kt = KepletTar({"r": "random()"})
        kor = Kor(sor=KONYV, tabla=T, kepletek=kt, most=MOST)
        self.assertEqual(kt.ertek(kor, "r"), kt.ertek(kor, "r"))
        self.assertNotEqual(kt.ertek(kor.sorra(MASIK), "r"), kt.ertek(kor, "r"))

    def test_memo_a_hibat_is_megorzi(self):
        kt = KepletTar({"h": "[] + 1"})
        kor = Kor(sor=KONYV, tabla=T, kepletek=kt, most=MOST)
        for _ in range(2):
            with self.assertRaises(FutasHiba):
                kt.ertek(kor, "h")
        self.assertEqual(len(kor.memo), 1)

    def test_kepelt_a_szuroben_es_listaban(self):
        k = {"hosszu": "Pages > 300"}
        self.assertTrue(self.kepletek("formula.hosszu", k))
        self.assertEqual(self.kepletek("formula.hosszu", k, s=MASIK), False)

    def test_note_es_formula_mint_ertek(self):
        self.assertEqual(self.kepletek("formula.keys()", {"a": "1", "b": "2"}), ["a", "b"])
        self.assertEqual(self.kepletek("formula.values()", {"a": "1", "b": "2"}), [1, 2])
        self.assertIn("Status", E("note.keys()"))


class FordítasHibaTest(unittest.TestCase):
    def test_fordítasi_hibak(self):
        for kif in ("nincs_fn(1)", "1.nincs()", "x.nincs()", "/(/", "if(1)", "if(1,2,3,4)", "(1)(2)", "x[0](1)", "1 +",
                    ""):
            with self.subTest(kif):
                with self.assertRaises(KifejezesHiba):
                    fordit_szoveg(kif)

    def test_hiba_helye(self):
        with self.assertRaises(KifejezesHiba) as r:
            fordit_szoveg("1 + nincs_fn(2)")
        self.assertEqual(r.exception.hely, 4)

    def test_futtat_python_hibaja_futashiba(self):
        def rossz(kor):
            raise ValueError("váratlan")
        with self.assertRaises(FutasHiba):
            futtat(rossz, Kor())

    def test_melyen_beagyazott_nem_dolgozik_ossze(self):
        kif = "[" * 60 + "]" * 60
        self.assertIsNotNone(E(kif))
        hosszu = " + ".join(["1"] * 150)
        self.assertEqual(E(hosszu), 150)

    def test_fordit_szoveg_gyorsitotarazott(self):
        self.assertIs(fordit_szoveg("1 + 2"), fordit_szoveg("1 + 2"))


class DokumentaciosPeldakTest(unittest.TestCase):
    """A `Bases syntax` / `Formulas` / `Functions` oldalak példái."""

    def test_peldak(self):
        s = sor("x.md", {"price": 20, "age": 4, "start_date": ("date", "2026-09-01"), "due_date": ("date", "2026-09-20"),
                         "status": "Todo", "tasks": ["a", "b", "c"], "first_name": "Ada", "last_name": "Lovelace",
                         "impact": 6, "urgency": 5, "effort": 3, "tags": ("tags", ["urgent"])})
        t = tabla([s])
        for kif, vart in [
            ('if(price, price.toFixed(2) + " dollars")', "20.00 dollars"), ("(price / age).toFixed(2)", "5.00"),
            ('start_date + "2w"', D("2026-09-15")), ('if(due_date < now() && status != "Done", "Overdue", "")', "Overdue"),
            ('if(price, "$" + price.toFixed(2), "")', "$20.00"), ("tasks.length", 3),
            ("(impact * urgency) / effort", 10), ('first_name + " " + last_name', "Ada Lovelace"),
            ('tags.contains("urgent")', True), ('due_date.format("YYYY-MM-DD")', "2026-09-20"),
            ('file.name.lower()', "x.md"), ('file.mtime > now() - "7d"', False), ("price > 100", False),
            ("!completed", True), ("price > 0 && age > 0", True), ("urgent || important", None),
            ('values_nincs', None),
        ]:
            with self.subTest(kif):
                self.assertEqual(ertek(kif, s, t), vart)

    def test_summaries_values_kulcsszo_az_egyedi_osszesitohoz(self):
        k = Kor(helyi={"values": [3, 1, 2, None]}, most=MOST)
        from core.bazis.kiertekelo import ertekel
        self.assertEqual(ertekel("values.filter(value.isType(\"number\")).reduce(if(acc == null || value > acc, value, acc), null)", k), 3)
        self.assertEqual(ertekel("values.length", k), 4)


if __name__ == "__main__":
    unittest.main()
