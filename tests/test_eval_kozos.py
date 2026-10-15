"""C18: a közös pontozó-segédek (`modulok/eval/kozos`)."""
import unittest

from tests import eval_segedek  # noqa: F401  (a modulok/eval a sys.path-ra kerül)

from kozos import bm25, idezet, kimenet, latex, matek, tavolsag


class TavolsagTest(unittest.TestCase):
    def test_levenshtein_es_aranyok(self):
        self.assertEqual(tavolsag.levenshtein("kitten", "sitting"), 3)
        self.assertEqual(tavolsag.levenshtein([], ["a"]), 1)
        self.assertEqual(tavolsag.wer("A köztársaság ostromlott erőddé vált.", "a köztársaság ostromlott erőddé vált"), 0.0)
        self.assertAlmostEqual(tavolsag.wer("egy kettő három négy", "egy kettő négy"), 0.25)
        self.assertGreater(tavolsag.cer("történetében", "történelmében"), 0)
        self.assertEqual(tavolsag.cer("", ""), 0.0)

    def test_hosszu_szoveg_cer_a_szakaszos_uton_is_pontos(self):
        v = " ".join(f"szó{i}" for i in range(400))
        k = v.replace("szó7 ", "szo7 ").replace("szó200 ", "")
        teljes = tavolsag.levenshtein(" ".join(tavolsag.szavak(v)), " ".join(tavolsag.szavak(k)))
        self.assertAlmostEqual(tavolsag.cer(v, k), teljes / len(" ".join(tavolsag.szavak(v))), places=6)

    def test_illesztes_szakaszai(self):
        m = tavolsag.illesztes(list("abcd"), list("abxd"))
        self.assertEqual([s[0] for s in m], ["egyezik", "csere", "egyezik"])

    def test_irasjel_f1(self):
        v = "Sulla meghalt. Ezután zavaros idők jöttek, de Pompeius feltűnt."
        self.assertEqual(tavolsag.irasjel_f1(v, v), 1.0)
        self.assertLess(tavolsag.irasjel_f1(v, "Sulla meghalt ezután zavaros idők jöttek de Pompeius feltűnt"), 0.01)
        self.assertLess(tavolsag.irasjel_f1(v, "Sulla meghalt. Ezután zavaros idők jöttek de Pompeius feltűnt"), 1.0)

    def test_hajtas_es_tovek(self):
        self.assertEqual(tavolsag.hajt("Űrhajó ÁRVÍZ"), "urhajo arviz")
        self.assertTrue(tavolsag.tovek("diszkriminánsa") & tavolsag.tovek("A diszkrimináns előjele"))


class LatexTest(unittest.TestCase):
    def test_kinyeres(self):
        s = "A képlet $x_{1,2}=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}$, és\n$$D = b^2 - 4ac$$\nvalamint \\(a^2\\) és \\[c=1\\]"
        self.assertEqual(len(latex.kepletek(s)), 4)
        self.assertEqual(latex.kepletek("ára 5$ és 7$ volt")[0:0], [])
        self.assertEqual(latex.kepletek("```latex\na=1 \\\\ b=2\n```"), ["a=1", "b=2"])

    def test_normalizalas_csak_irasmodot_egyseget(self):
        a = "x_{1,2} = \\dfrac{-b \\pm \\sqrt{b^{2} - 4ac}}{2a}"
        b = "x_{1,2}=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}"
        self.assertEqual(latex.normalizal(a), latex.normalizal(b))
        self.assertEqual(latex.normalizal("\\left(a+b\\right)^{2}"), "(a+b)^2")
        self.assertEqual(latex.normalizal("a \\cdot b"), latex.normalizal("a \\times b"))
        self.assertEqual(latex.normalizal("\\sin^2\\alpha+\\cos^2\\alpha=1"), latex.normalizal("sin²α" .replace("sin", "\\sin") + "+\\cos^{2}\\alpha = 1"))
        self.assertNotEqual(latex.normalizal("a^2+b^2"), latex.normalizal("a^2-b^2"))        # előjel nem vész el
        self.assertNotEqual(latex.normalizal("x^{12}"), latex.normalizal("x^1 2".replace(" ", "")) + "!")

    def test_elirt_keplet_bukik(self):
        jo = "\\Delta l = \\alpha \\cdot l_0 \\cdot \\Delta T"
        self.assertEqual(latex.hasonlosag(jo, "\\Delta l=\\alpha\\cdot l_{0}\\cdot\\Delta T"), 1.0)
        self.assertLess(latex.hasonlosag(jo, "\\Delta l = a \\cdot l_0 + \\Delta T"), 0.9)
        self.assertGreater(latex.cer(jo, "\\Delta l = a \\cdot l_0 + \\Delta T"), 0.1)

    def test_legjobb_jelolt(self):
        h, melyik = latex.legjobb("a^2+b^2=c^2", ["x=1", "a^{2}+b^{2}=c^{2}", "a+b=c"])
        self.assertEqual((h, melyik), (1.0, "a^{2}+b^{2}=c^{2}"))
        self.assertEqual(latex.legjobb("D=b^2-4ac", ["x=\\frac{1}{2},\\ D=b^2-4ac"])[0], 1.0)   # részként is megvan
        self.assertEqual(latex.legjobb("a=1", []), (0.0, None))


class IdezetTest(unittest.TestCase):
    FORRAS = ("## Caesar\n\nCaesar **Kr. e. 49-ben** átlépte a Rubicont, és ezzel polgárháborút indított. "
              "Pompeius Görögországba menekült, ahol Pharszalosznál vereséget szenvedett.\n\n"
              "- A szenátus Caesart örökös diktátorrá választotta.\n- Kr. e. 44-ben összeesküvők megölték.")

    def test_pontos_es_kozelito_talalat(self):
        f = idezet.Forras(self.FORRAS)
        r = f.keres("Caesar Kr. e. 49-ben átlépte a Rubicont")                 # a ** jelölés nem számít
        self.assertTrue(r["talalt"])
        self.assertEqual(r["hasonlosag"], 1.0)
        self.assertIn("Rubicont", self.FORRAS[r["hely"][0]:r["hely"][1]])
        self.assertTrue(f.keres("Pompeius Görögországba menekült, ahol Pharszalosnál vereséget szenvedet")["talalt"])

    def test_kitalalt_idezet_nincs_meg(self):
        f = idezet.Forras(self.FORRAS)
        self.assertFalse(f.keres("Caesar Kr. e. 52-ben legyőzte Vercingetorixot Alesiánál")["talalt"])
        self.assertFalse(f.keres("")["talalt"])
        self.assertFalse(f.keres("Pompeius Egyiptomba menekült, ahol megölték a király emberei")["talalt"])

    def test_lefedes(self):
        f = idezet.Forras(self.FORRAS)
        kulcs = f.keres("A szenátus Caesart örökös diktátorrá választotta")["szo"]
        self.assertTrue(idezet.lefedi(f.keres("Caesart örökös diktátorrá választotta")["szo"], kulcs))
        self.assertFalse(idezet.lefedi(f.keres("átlépte a Rubicont")["szo"], kulcs))
        self.assertFalse(idezet.lefedi(None, kulcs))


class KimenetTest(unittest.TestCase):
    def test_json_keritesben_szovegben_es_csonkan(self):
        self.assertEqual(kimenet.json_kinyer('Íme:\n```json\n[{"a": 1}]\n```\nkész'), [{"a": 1}])
        self.assertEqual(kimenet.json_kinyer('A válasz: {"k": "x } y"} vége'), {"k": "x } y"})
        self.assertEqual(kimenet.json_kinyer('[{"a": 1}, {"a": 2}, {"a": '), [{"a": 1}, {"a": 2}])
        self.assertIsNone(kimenet.json_kinyer("nincs benne semmi"))
        self.assertIsNone(kimenet.json_kinyer(None))
        self.assertEqual(kimenet.json_kinyer('<think>{"rossz": 1}</think>{"jo": 2}'), {"jo": 2})

    def test_lista_es_burok(self):
        self.assertEqual(kimenet.lista_kinyer('{"kartyak": [{"kerdes": "k"}, "szemét"]}'), [{"kerdes": "k"}])
        self.assertEqual(kimenet.lista_kinyer('{"kerdes": "k"}', ("kerdes",)), [{"kerdes": "k"}])
        self.assertEqual(kimenet.lista_kinyer("semmi"), [])

    def test_zarosor_az_utolso(self):
        s = "Levezetés…\nVÉGEREDMÉNY: x = 2\nJavítás.\n**Végeredmény:** x = 3"
        self.assertEqual(kimenet.zarosor(s, "VÉGEREDMÉNY"), "x = 3")
        self.assertIsNone(kimenet.zarosor("nincs ilyen sor", "VÉGEREDMÉNY"))
        self.assertEqual(kimenet.mezo("TÁRGY: Fizika\nFEJEZET: F05", "FEJEZET"), "F05")

    def test_gondolkodas_blokk_mindket_jelolessel(self):
        """A 2026-10-04-i előpróba: a ministral3_8b_reasoning `[THINK]…[/THINK]`-ja után a zárósor nem látszott."""
        ministral = "[THINK]Okay… ÍTÉLET: HELYES? Nem.\nSo step (3) is wrong.[/THINK]ÍTÉLET: HIBA 3"
        self.assertEqual(kimenet.tisztit(ministral), "ÍTÉLET: HIBA 3")
        self.assertEqual(kimenet.zarosor(ministral, "ÍTÉLET"), "HIBA 3")
        self.assertEqual(kimenet.zarosor("<think>ÍTÉLET: HELYES</think>\nÍTÉLET: HIBA 5", "ÍTÉLET"), "HIBA 5")
        self.assertEqual(kimenet.zarosor("gondolat…\n[/THINK]ÍTÉLET: HELYES", "ÍTÉLET"), "HELYES")      # nyitó jel nélkül
        self.assertIsNone(kimenet.zarosor("[THINK]a végéig nem ér véget, ÍTÉLET sincs", "ÍTÉLET"))


class MatekTest(unittest.TestCase):
    def test_elemzes_latexbol(self):
        self.assertEqual(matek.elemez("\\frac{1}{2}+\\dfrac{1}{3}"), matek.elemez("5/6"))
        self.assertEqual(matek.elemez("\\sqrt{16}"), 4)
        self.assertEqual(matek.elemez("\\sqrt[3]{27}"), 3)
        self.assertEqual(matek.elemez("2^{3}"), 8)
        self.assertEqual(matek.elemez("\\log_2 8"), 3)
        self.assertEqual(matek.elemez("\\log_{2}(8)"), 3)
        self.assertEqual(matek.elemez("1{,}5"), matek.elemez("3/2"))
        self.assertEqual(matek.elemez("2,5"), matek.elemez("5/2"))
        self.assertEqual(matek.elemez("4,57%"), matek.elemez("0.0457"))
        self.assertEqual(matek.elemez("5!"), 120)
        self.assertTrue(matek.kifejezes_egyezik(matek.elemez("2x+1"), matek.elemez("1+2*x")))

    def test_feherlista_elutasit(self):
        for rossz in ("__import__('os').system('true')", "x.__class__", "open('a')", "lambda: 1", "eval(1)",
                      "9**9**9**9", "1" * 20, "os", "a; b", "x[0]", ""):
            with self.assertRaises(matek.MatekHiba, msg=rossz):
                matek.elemez(rossz)

    def test_szam(self):
        v = {"tipus": "szam", "ertek": "57/1247", "tures": 0.005}
        self.assertTrue(matek.ekvivalens(v, "P \\approx 0{,}0457")[0])
        self.assertTrue(matek.ekvivalens(v, "\\frac{57}{1247}")[0])
        self.assertTrue(matek.ekvivalens(v, "4,57%")[0])
        self.assertFalse(matek.ekvivalens(v, "0,05")[0])
        self.assertFalse(matek.ekvivalens(v, None)[0])
        self.assertFalse(matek.ekvivalens(v, "0,0457; 0,5")[0])                 # több jelölt felsorolása nem ér pontot
        self.assertTrue(matek.ekvivalens({"tipus": "szam", "ertek": "7", "egysegek": ["m^2", "m²"]}, "T = 7 m^2")[0])

    def test_halmaz_es_hamis_gyok(self):
        v = {"tipus": "halmaz", "ertekek": ["-1/2", "0", "3"]}
        self.assertTrue(matek.ekvivalens(v, "x_1 = 3; x_2 = 0; x_3 = -\\frac{1}{2}")[0])
        self.assertTrue(matek.ekvivalens(v, "\\{-0{,}5;\\ 0;\\ 3\\}")[0])
        self.assertFalse(matek.ekvivalens(v, "x = 0; x = 3")[0])
        egy = {"tipus": "halmaz", "ertekek": ["6"]}
        self.assertTrue(matek.ekvivalens(egy, "x = 6")[0])
        self.assertFalse(matek.ekvivalens(egy, "x_1 = 6; x_2 = 30")[0])         # a hamis gyököt megtartó válasz bukik
        self.assertTrue(matek.ekvivalens({"tipus": "halmaz", "ertekek": ["2", "-2"]}, "x_{1,2} = \\pm 2")[0])
        self.assertTrue(matek.ekvivalens({"tipus": "halmaz", "ertekek": []}, "nincs megoldás")[0])
        self.assertFalse(matek.ekvivalens({"tipus": "halmaz", "ertekek": []}, "x = 1")[0])

    def test_intervallum(self):
        v = {"tipus": "intervallum", "ertek": "(2, oo)"}
        for jo in ("x > 2", "]2; +\\infty[", "(2; ∞)", "x \\in ]2; \\infty["):
            self.assertTrue(matek.ekvivalens(v, jo)[0], jo)
        self.assertFalse(matek.ekvivalens(v, "x \\geq 2")[0])                   # a végpont zártsága számít
        u = {"tipus": "intervallum", "ertek": "(-oo, -1) U [3, oo)"}
        self.assertTrue(matek.ekvivalens(u, "x < -1 vagy x \\geq 3")[0])
        self.assertTrue(matek.ekvivalens({"tipus": "intervallum", "ertek": "[1, 3)"}, "1 \\leq x < 3")[0])
        self.assertTrue(matek.ekvivalens({"tipus": "intervallum", "ertek": "[1, 3)"}, "3 > x \\geq 1")[0])
        self.assertFalse(matek.ekvivalens(u, "valami más")[0])

    def test_kifejezes_es_par(self):
        self.assertTrue(matek.ekvivalens({"tipus": "kifejezes", "ertek": "(x-1)*(x+1)"}, "f(x) = x^2 - 1")[0])
        self.assertFalse(matek.ekvivalens({"tipus": "kifejezes", "ertek": "(x-1)*(x+1)"}, "x^2 + 1")[0])
        p = {"tipus": "par", "ertekek": {"x": "4", "y": "4"}}
        self.assertTrue(matek.ekvivalens(p, "x = 4; y = 4")[0])
        self.assertTrue(matek.ekvivalens(p, "(4; 4)")[0])
        self.assertFalse(matek.ekvivalens(p, "x = 4; y = 2")[0])

    def test_megoldashalmaz(self):
        import sympy as sp
        self.assertEqual(matek.megoldashalmaz("2x + 3 = 7"), sp.FiniteSet(2))
        self.assertNotEqual(matek.megoldashalmaz("x^2 = 4"), matek.megoldashalmaz("x = 2"))


class Bm25Test(unittest.TestCase):
    def test_rangsor(self):
        b = bm25.Bm25()
        b.hozzaad("masodfoku", "masodfoku egyenlet megoldokeplet diszkriminans".split())
        b.hozzaad("hotan", "hotagulas homerseklet gaz nyomas".split())
        b.hozzaad("trig", "szinusz koszinusz tetel haromszog".split())
        self.assertEqual(b.rangsor("a diszkriminans es a megoldokeplet".split())[0][0], "masodfoku")
        self.assertEqual(b.rangsor(["ismeretlen"]), [])


if __name__ == "__main__":
    unittest.main()
