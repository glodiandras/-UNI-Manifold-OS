"""A Bases-kifejezések elemzője (`core/bazis/kifejezes.py`, C12 1. lépés): precedencia, literálok, hibák, pozíciók."""
import unittest

from core.bazis import kifejezes as k
from core.bazis.kifejezes import KifejezesHiba, elemez


def alak(c) -> str:
    """A fa zárójelezett, összehasonlítható szöveges alakja."""
    if isinstance(c, k.Szam):
        return repr(c.ertek)
    if isinstance(c, k.Szoveg):
        return repr(c.ertek)
    if isinstance(c, k.Logikai):
        return "igaz" if c.ertek else "hamis"
    if isinstance(c, k.Null):
        return "null"
    if isinstance(c, k.ListaL):
        return "[" + ",".join(alak(e) for e in c.elemek) + "]"
    if isinstance(c, k.ObjektumL):
        return "{" + ",".join(f"{a}:{alak(v)}" for a, v in c.parok) + "}"
    if isinstance(c, k.RegexL):
        return f"/{c.minta}/{c.zaszlok}"
    if isinstance(c, k.Nev):
        return c.nev
    if isinstance(c, k.Tag):
        return f"{alak(c.obj)}.{c.nev}"
    if isinstance(c, k.Index):
        return f"{alak(c.obj)}[{alak(c.kulcs)}]"
    if isinstance(c, k.Hivas):
        return f"{alak(c.fn)}({','.join(alak(a) for a in c.argok)})"
    if isinstance(c, k.Unaris):
        return f"({c.muvelet}{alak(c.operandus)})"
    if isinstance(c, k.Binaris):
        return f"({alak(c.bal)} {c.muvelet} {alak(c.jobb)})"
    raise AssertionError(c)


def hiba(szoveg: str) -> KifejezesHiba:
    with unittest.TestCase().assertRaises(KifejezesHiba) as e:
        elemez(szoveg)
    return e.exception


class LiteralTest(unittest.TestCase):
    def test_szamok(self):
        for sz, v in [("0", 0), ("42", 42), ("3.14", 3.14), ("1e3", 1000.0), ("2.5e-1", 0.25)]:
            c = elemez(sz)
            self.assertIsInstance(c, k.Szam)
            self.assertEqual(c.ertek, v)
        self.assertIsInstance(elemez("42").ertek, int)
        self.assertIsInstance(elemez("4.0").ertek, float)

    def test_szoveg_es_escape(self):
        self.assertEqual(elemez('"ab"').ertek, "ab")
        self.assertEqual(elemez("'ab'").idezo, "'")
        self.assertEqual(elemez(r'"a\"b\\c\n\t"').ertek, 'a"b\\c\n\t')
        self.assertEqual(elemez(r'"é"').ertek, "é")
        self.assertEqual(elemez(r"'it\'s'").ertek, "it's")
        self.assertEqual(elemez('"ékezet űő"').ertek, "ékezet űő")

    def test_kulcsszavak(self):
        self.assertEqual(alak(elemez("true")), "igaz")
        self.assertEqual(alak(elemez("false")), "hamis")
        self.assertEqual(alak(elemez("null")), "null")

    def test_lista_es_objektum(self):
        self.assertEqual(alak(elemez("[1, 2, [3]]")), "[1,2,[3]]")
        self.assertEqual(alak(elemez("[]")), "[]")
        self.assertEqual(alak(elemez("[1,2,]")), "[1,2]")
        self.assertEqual(alak(elemez('{"a": 1, b: 2, 3: x}')), "{a:1,b:2,3:x}")
        self.assertEqual(alak(elemez("{}")), "{}")

    def test_regex(self):
        c = elemez(r"/a\/b[/]c/gi")
        self.assertIsInstance(c, k.RegexL)
        self.assertEqual((c.minta, c.zaszlok), (r"a\/b[/]c", "gi"))
        self.assertEqual(alak(elemez(r'"a:b".replace(/:/g, "-")')), "'a:b'.replace(/:/g,'-')")

    def test_perjel_osztas_ha_operandus_utan_all(self):
        self.assertEqual(alak(elemez("a / b / c")), "((a / b) / c)")
        self.assertEqual(alak(elemez("(a) / 2")), "(a / 2)")
        self.assertEqual(alak(elemez("x[0] / 2")), "(x[0] / 2)")
        self.assertEqual(alak(elemez("f() / 2")), "(f() / 2)")
        self.assertIsInstance(elemez("/ab/").minta, str)
        self.assertEqual(alak(elemez("a + /x/")), "(a + /x/)")


class NevTest(unittest.TestCase):
    def test_nevelerek(self):
        self.assertEqual(alak(elemez("file.name")), "file.name")
        self.assertEqual(alak(elemez('note["my prop"]')), "note['my prop']")
        self.assertEqual(alak(elemez("a.b.c[0].d")), "a.b.c[0].d")
        self.assertEqual(alak(elemez("formula.ppu")), "formula.ppu")

    def test_ekezetes_nev(self):
        self.assertEqual(alak(elemez("Évszám + 1")), "(Évszám + 1)")

    def test_kotojel_ket_betu_kozott_az_azonosito_resze(self):
        self.assertEqual(alak(elemez("image-property")), "image-property")
        self.assertEqual(alak(elemez("a - b")), "(a - b)")
        self.assertEqual(alak(elemez("a-1")), "(a - 1)")
        self.assertEqual(alak(elemez('now()-"7d"')), "(now() - '7d')")

    def test_szam_modszer(self):
        self.assertEqual(alak(elemez("5.isEmpty()")), "5.isEmpty()")
        self.assertEqual(alak(elemez("(2.5).round()")), "2.5.round()")
        self.assertEqual(alak(elemez("123.toString()")), "123.toString()")


class HivasTest(unittest.TestCase):
    def test_hivasok(self):
        self.assertEqual(alak(elemez("now()")), "now()")
        self.assertEqual(alak(elemez('if(price, "x", "y")')), "if(price,'x','y')")
        self.assertEqual(alak(elemez('file.hasTag("a", "b")')), "file.hasTag('a','b')")
        self.assertEqual(alak(elemez("[1,2].reduce(acc + value, 0)")), "[1,2].reduce((acc + value),0)")
        self.assertEqual(alak(elemez("a.b(1)(2)")), "a.b(1)(2)")
        self.assertEqual(alak(elemez("f(1,)")), "f(1)")

    def test_hivas_poziciok(self):
        s = 'if(a, link("X"), "y")'
        c = elemez(s)
        self.assertEqual((c.kezd, c.veg), (0, len(s)))
        harmadik = c.argok[1].argok[0]
        self.assertIsInstance(harmadik, k.Szoveg)
        self.assertEqual(s[harmadik.kezd:harmadik.veg], '"X"')


class PrecedenciaTest(unittest.TestCase):
    def test_precedencia(self):
        for forras, vart in [
            ("a || b && c", "(a || (b && c))"),
            ("a && b == c", "(a && (b == c))"),
            ("a == b < c", "(a == (b < c))"),
            ("a < b + c", "(a < (b + c))"),
            ("a + b * c", "(a + (b * c))"),
            ("(a + b) * c", "((a + b) * c)"),
            ("a - b - c", "((a - b) - c)"),
            ("a * b % c", "((a * b) % c)"),
            ("!a == b", "((!a) == b)"),
            ("-a.b", "(-a.b)"),
            ("!a.b()", "(!a.b())"),
            ("a != b || c >= d && e <= f", "((a != b) || ((c >= d) && (e <= f)))"),
            ("2 * -3", "(2 * (-3))"),
            ("!!a", "(!(!a))"),
        ]:
            self.assertEqual(alak(elemez(forras)), vart, forras)

    def test_szuro_peldak_a_dokumentaciobol(self):
        for forras in ['status != "done"', "formula.ppu > 5", "price > 2.1", 'file.hasTag("book")',
                       'if(price, price.toFixed(2) + " dollars")', "(price / age).toFixed(2)",
                       'file.mtime > now() - "1 week"', "values.mean().round(3)",
                       'values.filter(value.isType("number")).reduce(if(acc == null || value > acc, value, acc), null)',
                       'file.tags == ["Book"]', 'NN.contains(link("Cél"))', 'date("2024-12-01") + "1M" + "4h"']:
            elemez(forras)


class HibaTest(unittest.TestCase):
    def test_hibak_helye(self):
        for forras, hely in [("a +", 3), ("(a", 2), ("a b", 2), ('"abc', 0), ("a.", 2), ("f(1", 3), ("#", 0),
                             ("1a", 1), ("{a 1}", 3), ("[1", 2), ("a ]", 2), ("/ab", 0), ("", 0), ("   ", 0)]:
            self.assertEqual(hiba(forras).hely, hely, forras)

    def test_uzenet_magyar_es_helyet_mond(self):
        self.assertIn("hiányzik", str(hiba("(a")))
        self.assertIn("karakternél", str(hiba("a +")))
        self.assertEqual(hiba("").uzenet, "üres kifejezés")

    def test_nem_szoveg(self):
        with self.assertRaises(KifejezesHiba):
            elemez(None)                                                     # type: ignore[arg-type]

    def test_melysegkorlat(self):
        elemez("(" * 100 + "a" + ")" * 100)
        with self.assertRaises(KifejezesHiba):
            elemez("(" * 300 + "a" + ")" * 300)
        with self.assertRaises(KifejezesHiba):
            elemez("!" * 300 + "a")
        with self.assertRaises(KifejezesHiba):
            elemez(" + ".join(["a"] * 400))         # a bal oldali lánc magassága is korlátos
        with self.assertRaises(KifejezesHiba):
            elemez("[" * 300 + "]" * 300)


class PozicioTest(unittest.TestCase):
    def test_szoveg_literal_tartomanya_az_idezojellel(self):
        s = 'file.name == "A \\" B" && x.hasLink(\'[[C]]\')'
        c = elemez(s)
        lit = [n for n in k.bejar(c) if isinstance(n, k.Szoveg)]
        self.assertEqual([s[n.kezd:n.veg] for n in lit], ['"A \\" B"', "'[[C]]'"])

    def test_bejar_sorrend_es_mely(self):
        c = elemez("a + b * 2")
        self.assertEqual([type(n).__name__ for n in k.bejar(c)], ["Binaris", "Nev", "Binaris", "Nev", "Szam"])
        self.assertEqual(c.mely, 3)


if __name__ == "__main__":
    unittest.main()
