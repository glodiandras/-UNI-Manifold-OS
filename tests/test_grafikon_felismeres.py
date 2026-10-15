"""A ```plot blokk determinisztikus felismerése (C35a): LaTeX / TikZ → javaslat, a bizonytalanság kimondása,
mérési kapu a C18 `grafikon` aranyhalmazán. Álgyökér nem kell: a felismerés nem olvas konfigurációt és vaultot."""
import json
import sys
import unittest
from pathlib import Path

from tests.helpers import REPO

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from grafikon import felismeres as R  # noqa: E402
from grafikon import formatum as F  # noqa: E402
from grafikon import meres  # noqa: E402

ARANY = json.loads((REPO / "modulok" / "eval" / "grafikon" / "arany.json").read_text(encoding="utf-8"))


def abra(keplet):
    j = R.felismer(keplet)
    return j, j.abra


class FuggvenyTest(unittest.TestCase):
    def test_aranyhalmaz_minden_kepletre_biztos_es_helyes(self):
        for k in ARANY["kepletek"]:
            j = R.felismer(k["keplet"])
            self.assertEqual(j.bizonyossag, R.BIZTOS, (k["id"], j.ok))
            self.assertEqual(j.fajta, "fuggveny", k["id"])
            self.assertTrue(meres._kif_egyezik(j, k["vart"]["kifejezes"]), (k["id"], j.blokk))
            self.assertTrue(meres._korut_ok(j), k["id"])
            self.assertTrue(meres._lefedes(j, k["vart"]), (k["id"], j.blokk))

    def test_mero_kapu(self):
        a = meres.meres_arany(ARANY)
        self.assertEqual((a["osszes"], a["biztos_helyes"], a["biztos_rossz"]), (15, 15, 0))
        k = meres.meres_kiegeszito()
        self.assertEqual(k["biztos_rossz"], 0, [t for t in k["tetelek"] if t["kapott"] != t["vart"]])
        self.assertEqual(k["tevedes"] + k["bizonytalan_biztos_helyett"], 0)

    def test_nev_es_cimke_es_valtozo(self):
        j, a = abra(r"f(x) = 2x + 1")
        self.assertEqual(a.elemek, (F.Fuggveny("2x + 1", "f"),))
        j, a = abra(r"f(t) = t^2")
        self.assertEqual(a.elemek, (F.Fuggveny("x^2", "f"),))           # a deklarált változó x-re nevezve
        self.assertEqual(j.bizonyossag, R.BIZTOS)
        _, a = abra(r"y = x^2")
        self.assertIsNone(a.elemek[0].cimke)

    def test_jegyzetbeli_cimke_elhagyva(self):
        """C35b: az `f: y = …` / `g_1: f(x) = …` jegyzet-jelölés címkéje elhagyható, a definíció felismerhető (a g03-típus)."""
        j, a = abra(r"f: y = -x^2")
        self.assertEqual((j.bizonyossag, a.elemek[0].kifejezes), (R.BIZTOS, "-x^2"))
        j, a = abra(r"g_1: f(x) = 2x + 1")
        self.assertEqual((j.bizonyossag, a.elemek[0].kifejezes), (R.BIZTOS, "2x + 1"))
        j, a = abra(r"f: y = (x + 5)^2 = x^2 + 10x + 25")
        self.assertEqual((j.bizonyossag, a.elemek[0].kifejezes), (R.BIZONYTALAN, "(x + 5)^2"))      # az egyenlőség-lánc: van referencia
        self.assertIn("lánc", j.ok)
        for nem in (r"f: \mathbb{R} \to \mathbb{R}", r"Tétel: y = x", r"A: x^2 = 4"):          # nem címke: a viselkedés változatlan
            self.assertNotEqual(R.felismer(nem).bizonyossag, R.BIZTOS, nem)

    def test_szep_alak(self):
        self.assertEqual(abra(r"y = \sin 2x")[1].elemek[0].kifejezes, "sin(2*x)")
        self.assertEqual(abra(r"y = \frac{x+1}{2}")[1].elemek[0].kifejezes, "(x+1)/2")
        self.assertEqual(abra(r"y = |x| - 3")[1].elemek[0].kifejezes, "abs(x) - 3")

    def test_tartomany_a_kepletbol(self):
        _, a = abra(r"y=x^2, x\in[-2,3]")
        self.assertEqual(a.x_tartomany, ("-2", "3"))
        _, a = abra(r"f(x)=x^2,\quad 0\le x\le 4")
        self.assertEqual(a.x_tartomany, ("0", "4"))
        j, a = abra(r"f(x)=\ln x, x>0")
        self.assertEqual((a.x_tartomany, j.bizonyossag), (("0", "10"), R.BIZTOS))

    def test_ablak_ertelmezesi_tartomany_es_trig(self):
        _, a = abra(r"y = \sqrt{x+3} - 2")
        self.assertEqual(a.x_tartomany, ("-3", "5"))
        _, a = abra(r"y = \sin x")
        self.assertEqual(a.x_tartomany, ("-2*pi", "2*pi"))
        j, a = abra(r"y = \log_2 x")
        self.assertEqual((a.x_tartomany[0], j.bizonyossag), ("0", R.BIZTOS))
        lo, hi = (float(v) for v in a.y_tartomany)
        self.assertGreater(lo, -20)                                      # a tartomány széli elszálló érték nem nyújtja meg

    def test_tobb_fuggveny_egy_kepletben(self):
        j, a = abra(r"f(x) = x^2, g(x) = x + 1")
        self.assertEqual([e.cimke for e in a.elemek], ["f", "g"])
        self.assertEqual(j.bizonyossag, R.BIZTOS)


class MasAlakokTest(unittest.TestCase):
    def test_parameteres(self):
        j, a = abra(r"x = 3\cos t, \; y = 2\sin t, \; t \in [0, 2\pi]")
        self.assertEqual((j.fajta, j.bizonyossag), ("parameteres", R.BIZTOS))
        self.assertEqual(a.elemek, (F.Parameteres("3*cos(t)", "2*sin(t)", "t", ("0", "2*pi")),))
        j, a = abra(r"x(s) = s^2, y(s) = s^3, -1 \le s \le 1")
        self.assertEqual(a.elemek[0], F.Parameteres("t^2", "t^3", "t", ("-1", "1")))   # a paraméter t-re nevezve

    def test_parameteres_tartomany_nelkul_bizonytalan(self):
        j, a = abra(r"x=\cos t, y=\sin t")
        self.assertEqual(j.bizonyossag, R.BIZONYTALAN)
        self.assertIn("tartománya hiányzik", j.ok)
        self.assertEqual(a.elemek[0].tartomany, ("0", "2*pi"))

    def test_egyenlotlenseg(self):
        j, a = abra(r"y \ge x^2 - 1")
        self.assertEqual((j.fajta, j.bizonyossag), ("egyenlotlenseg", R.BIZTOS))
        self.assertEqual(a.elemek, (F.Egyenlotlenseg("x^2 - 1", ">="),))
        self.assertEqual(abra(r"x^2 \le y")[1].elemek, (F.Egyenlotlenseg("x^2", ">="),))   # megfordítva
        self.assertEqual(abra(r"y < -x + 3")[1].elemek[0].relacio, "<")
        j = R.felismer(r"-1 \le y \le 3")
        self.assertNotEqual(j.bizonyossag, R.BIZTOS)
        self.assertEqual(R.felismer(r"x > 2").bizonyossag, R.NINCS)

    def test_pgfplots(self):
        j, a = abra(r"\begin{tikzpicture}\begin{axis}[xmin=-3, xmax=3]\addplot[domain=-3:3]{x^2};"
                    r"\addlegendentry{parabola}\end{axis}\end{tikzpicture}")
        self.assertEqual((j.fajta, j.bizonyossag), ("tikz", R.BIZTOS))
        self.assertEqual(a.elemek, (F.Fuggveny("x^2", "parabola"),))
        self.assertEqual(a.x_tartomany, ("-3", "3"))
        j, a = abra(r"\begin{axis}\addplot[domain=0:2*pi, variable=t] ({cos(deg(t))},{sin(deg(t))});\end{axis}")
        self.assertEqual(a.elemek[0], F.Parameteres("cos(t)", "sin(t)", "t", ("0", "2*pi")))
        self.assertEqual(j.bizonyossag, R.BIZTOS)

    def test_pgf_fokban_szamolt_trig_bizonytalan(self):
        j, _ = abra(r"\begin{axis}\addplot[domain=0:360]{sin(x)};\end{axis}")
        self.assertEqual(j.bizonyossag, R.BIZONYTALAN)
        self.assertIn("fokban", j.ok)

    def test_tikz_draw_plot(self):
        j, a = abra(r"\begin{tikzpicture}\draw[domain=-1:2] plot (\x,{\x*\x});\end{tikzpicture}")
        self.assertEqual((j.bizonyossag, a.elemek, a.x_tartomany), (R.BIZTOS, (F.Fuggveny("x*x"),), ("-1", "2")))

    def test_pgf_adatpont_nem_kepelt(self):
        j = R.felismer(r"\begin{axis}\addplot table {adat.dat};\end{axis}")
        self.assertNotEqual(j.bizonyossag, R.BIZTOS)
        self.assertIsNone(j.abra)


class BizonytalanTest(unittest.TestCase):
    def megall(self, keplet, bizonyossag, reszlet):
        j = R.felismer(keplet)
        self.assertEqual(j.bizonyossag, bizonyossag, (keplet, j.ok))
        self.assertIn(reszlet, j.ok, keplet)
        self.assertTrue(j.ok)
        if bizonyossag != R.BIZTOS and j.abra is None:
            self.assertEqual(j.blokk, "")
        return j

    def test_szakadas_es_aszimptota(self):
        self.megall(r"y = \frac{1}{x}", R.BIZONYTALAN, "szakadás")
        self.megall(r"y = \tan x", R.BIZONYTALAN, "aszimptota")
        self.megall(r"y = \frac{x+1}{x-1}", R.BIZONYTALAN, "aszimptota")

    def test_implicit_parameter_szakaszonkent(self):
        self.megall(r"x^2 + y^2 = 1", R.BIZONYTALAN, "implicit")
        self.megall(r"y = ax + b", R.BIZONYTALAN, "paramétert")
        self.megall(r"f(x) = \begin{cases} x & x>0 \\ -x & x\le 0 \end{cases}", R.BIZONYTALAN, "szakaszonként")

    def test_konstans_es_lanc(self):
        self.megall(r"y = 3", R.BIZONYTALAN, "konstans")
        self.megall(r"y = x^2 = 4", R.BIZONYTALAN, "lánc")

    def test_ismeretlen_fuggveny_es_kiegeszites(self):
        self.megall(r"y = g(x) + 1", R.BIZONYTALAN, "nem elemezhető")
        j = self.megall(r"f(x) = x^2, \; f:\mathbb{R}\to\mathbb{R}", R.BIZONYTALAN, "kiegészítés")
        self.assertIsNotNone(j.abra)

    def test_nem_grafikon_alapanyag(self):
        for k in (r"2x + 1 = 0", r"f(2) = 5", r"f'(x) = 2x", r"\sin^2 x + \cos^2 x = 1", r"x = 3", r"a^2+b^2=c^2",
                  r"\frac{a}{b}", "", r"x"):
            j = R.felismer(k)
            self.assertEqual(j.bizonyossag, R.NINCS, (k, j.ok))
            self.assertEqual(j.blokk, "")
            self.assertTrue(j.ok)

    def test_tamado_vagy_hibas_bemenet_nem_dob(self):
        for k in (r"y = \frac{1}{", r"y = " + "9" * 400, r"y = 9^9^9^9", r"y = __import__('os').system('x')",
                  r"y = x" + "+x" * 400, r"\addplot", r"\begin{tikzpicture}", "y = \\sqrt{", "y = (((((x"):
            j = R.felismer(k)
            self.assertIn(j.bizonyossag, (R.BIZONYTALAN, R.NINCS), k)
            self.assertTrue(j.ok)

    def test_biztos_csak_hibatlanul_elemezheto_ablakkal(self):
        for k in (r"y = \sqrt{-x^2 - 1}",):                              # sehol nem értelmezett
            j = R.felismer(k)
            self.assertNotEqual(j.bizonyossag, R.BIZTOS, k)

    def test_kulcs_stabil_es_irasmodtol_fuggetlen(self):
        self.assertEqual(R.kulcs(r"y = \dfrac{x}{2}"), R.kulcs(r"y=\frac{x}{2}"))
        self.assertNotEqual(R.kulcs("y = x"), R.kulcs("y = 2x"))
        self.assertEqual(R.felismer("y = x").kulcs, R.kulcs("y = x"))


class JegyzetTest(unittest.TestCase):
    JEGYZET = (
        "# Függvények\n\nA parabola:\n\n$$f(x) = x^2 - 4x + 5$$\n\n"
        "```plot\ny = x^2\n```\n\nEgyenlet: $2x+1=0$, majd $y = 2x + 1$ egyenes.\n\n"
        "```math\ny = \\sin 2x\n```\n\n"
        "\\begin{tikzpicture}\\begin{axis}\\addplot[domain=-1:1]{x^3};\\end{axis}\\end{tikzpicture}\n"
    )

    def test_sorok_es_blokk_kovetkezik(self):
        ki = R.felismer_jegyzet(self.JEGYZET)
        self.assertEqual([j.fajta for j in ki], ["fuggveny", "fuggveny", "fuggveny", "tikz"])
        self.assertEqual([j.sor for j in ki][:2], [5, 11])
        self.assertTrue(ki[0].blokk_kovetkezik)                          # alatta már van plot blokk
        self.assertFalse(ki[1].blokk_kovetkezik)
        self.assertTrue(all(j.bizonyossag == R.BIZTOS for j in ki))
        self.assertEqual(len(R.felismer_jegyzet(self.JEGYZET, mindet=True)), 5)   # + a szám-egyenlet

    def test_ures_jegyzet(self):
        self.assertEqual(R.felismer_jegyzet(""), [])
        self.assertEqual(R.felismer_jegyzet("nincs képlet"), [])

    def test_nem_ir_vaultot_es_nem_toltmodellt(self):
        from grafikon import felismeres as m
        forras = Path(m.__file__).read_text(encoding="utf-8")
        for tiltott in ("vaultio", "gepi_kliens", "gepi_iras", "requests", "urllib", "socket", "mlx"):
            self.assertNotIn("import " + tiltott, forras)


if __name__ == "__main__":
    unittest.main()
