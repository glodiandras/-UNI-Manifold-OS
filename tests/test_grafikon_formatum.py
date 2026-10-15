"""A ```plot blokk formátuma (C35a): elemzés, kanonikus szerializálás, körút, a jegyzetből kivágás (kódmaszk)."""
import random
import sys
import unittest

from tests.helpers import REPO

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from grafikon import formatum as F  # noqa: E402

MINTA = '''# példa
y in [-2, 10]
x in [-4, 4]
y = x^2 + 2  "f \\"x\\""   # sorvégi megjegyzés
x = 3*cos(t), y = 2*sin(t), t in [0, 2*pi]
y >= x^2
pont (2, 1) "min"
valami ismeretlen
'''


class ElemzesTest(unittest.TestCase):
    def test_minden_elemfajta(self):
        a = F.elemez(MINTA)
        self.assertEqual(a.x_tartomany, ("-4", "4"))
        self.assertEqual(a.y_tartomany, ("-2", "10"))
        self.assertEqual(a.elemek, (
            F.Megjegyzes("példa"),
            F.Fuggveny("x^2 + 2", 'f "x"'),
            F.Parameteres("3*cos(t)", "2*sin(t)", "t", ("0", "2*pi")),
            F.Egyenlotlenseg("x^2", ">="),
            F.Pont("2", "1", "min"),
            F.Ismeretlen("valami ismeretlen"),
        ))
        self.assertEqual([s for s, _ in a.hibak], [8])

    def test_kanonikus_alak(self):
        self.assertEqual(F.szerializal(F.elemez(MINTA)), "\n".join([
            "x in [-4, 4]", "y in [-2, 10]", "# példa", 'y = x^2 + 2 "f \\"x\\""',
            "x = 3*cos(t), y = 2*sin(t), t in [0, 2*pi]", "y >= x^2", 'pont (2, 1) "min"', "valami ismeretlen"]))

    def test_korut_fixpont(self):
        a = F.elemez(MINTA)
        s = F.szerializal(a)
        self.assertEqual(F.elemez(s), a)
        self.assertEqual(F.szerializal(F.elemez(s)), s)

    def test_korut_veletlen_abrakra(self):
        v = random.Random(7)
        kif = ["x", "x^2 + 2", "sin(2*x)", "log(x, 2)", "abs(x) - 3", "sqrt(3*x^2 + 1)", "2^(2 - x) + 5", "(x+1)/(x-1)"]
        for _ in range(200):
            elemek = []
            for _ in range(v.randint(0, 6)):
                cimke = v.choice([None, "f", 'a "b" c', "g(x)", "x\\y"])
                elemek.append(v.choice([
                    F.Fuggveny(v.choice(kif), cimke),
                    F.Parameteres(v.choice(kif).replace("x", "t"), "2*sin(t)", "t", ("0", "2*pi"), cimke),
                    F.Egyenlotlenseg(v.choice(kif), v.choice(["<", "<=", ">", ">="]), cimke),
                    F.Pont(str(v.randint(-9, 9)), "1/2", cimke),
                    F.Megjegyzes("megj"),
                    F.Ismeretlen("valami más"),
                ]))
            a = F.Abra(v.choice([None, ("-4", "4")]), v.choice([None, ("0", "2*pi")]), tuple(elemek))
            s = F.szerializal(a)
            self.assertEqual(F.elemez(s), a, s)
            self.assertEqual(F.szerializal(F.elemez(s)), s)

    def test_obsidianban_sima_szoveg(self):
        b = F.blokk(F.elemez("y = x^2\nx in [-1, 1]"))
        self.assertEqual(b, "```plot\nx in [-1, 1]\ny = x^2\n```\n")
        self.assertNotIn("---", b)                       # nincs YAML-fejléc

    def test_ures_blokk(self):
        self.assertEqual(F.blokk(F.Abra()), "```plot\n```\n")
        self.assertEqual(F.elemez(""), F.Abra())

    def test_hibas_sorok_megmaradnak_hibaval(self):
        a = F.elemez("y = \nx in [1]\ny = x$\nx in [0, 1]\nx in [2, 3]\n")
        self.assertEqual(a.x_tartomany, ("0", "1"))
        self.assertEqual(sum(isinstance(e, F.Ismeretlen) for e in a.elemek), 4)
        self.assertEqual(len(a.hibak), 4)

    def test_tulzott_zarojel_es_plafon(self):
        self.assertIsInstance(F.elemez("y = (x").elemek[0], F.Ismeretlen)
        a = F.elemez("\n".join(f"y = x + {i}" for i in range(F.MAX_ELEM + 3)))
        self.assertEqual(sum(isinstance(e, F.Fuggveny) for e in a.elemek), F.MAX_ELEM)
        self.assertEqual(len(a.hibak), 3)
        self.assertEqual(F.elemez("y = x + " + "1" * (F.MAX_SOR + 5)).hibak[0][0], 1)
        self.assertTrue(F.elemez("x" * (F.MAX_BLOKK + 1)).hibak)

    def test_unicode_jelek(self):
        a = F.elemez("y ≥ x − 1")
        self.assertEqual(a.elemek, (F.Egyenlotlenseg("x - 1", ">="),))

    def test_a_kifejezes_nem_fut(self):
        a = F.elemez("y = __import__('os')")             # idézőjel és aláhúzás-minta: nem kifejezés-jel
        self.assertIsInstance(a.elemek[0], F.Ismeretlen)


class BlokkokTest(unittest.TestCase):
    def test_kivag_es_hely(self):
        t = "Cím\n\n$$y=x^2$$\n\n```plot\ny = x^2\n```\n\nzár\n"
        [b] = F.blokkok(t)
        self.assertEqual((b.kezdo_sor, b.veg_sor, b.lezart), (5, 7, True))
        self.assertEqual(t[b.kezdo:b.veg], "```plot\ny = x^2\n```\n")
        self.assertEqual(b.forras, "y = x^2\n")
        self.assertEqual(b.abra.elemek, (F.Fuggveny("x^2"),))

    def test_kodmaszk(self):
        t = "````md\n```plot\ny=1\n```\n````\n\n~~~plot\ny=2\n~~~\n\n```python\n```plot\n```\n"
        self.assertEqual(F.blokkok(t), [])               # más kódblokkban álló példa nem tartalom

    def test_frontmatter_kimarad(self):
        t = "---\nTags: x\n---\n```plot\ny = x\n```\n"
        self.assertEqual(len(F.blokkok(t)), 1)
        self.assertEqual(F.blokkok("---\n```plot\ny = x\n```\n---\n"), [])

    def test_lezaratlan_es_crlf(self):
        [b] = F.blokkok("a\r\n```plot\r\ny = x\r\n")
        self.assertFalse(b.lezart)
        self.assertEqual(b.abra.elemek, (F.Fuggveny("x"),))
        [c] = F.blokkok("```Plot title\r\ny = x\r\n```\r\n")
        self.assertTrue(c.lezart)
        self.assertEqual(c.veg_sor, 3)

    def test_tobb_blokk(self):
        t = "```plot\ny=x\n```\ntext\n```plot\ny=-x\n```\n"
        self.assertEqual([b.kezdo_sor for b in F.blokkok(t)], [1, 5])


if __name__ == "__main__":
    unittest.main()
