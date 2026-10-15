"""C35a: a Python és a TypeScript közös vektorai (`modulok/grafikon/vektorok/*.json`). A felület (`plot/kifejezes.ts`,
`plot/forras.ts`) a kifejezést és a blokkot saját elemzővel olvassa (azonnal, hálózat nélkül); a vektorok rögzítik, hogy
ugyanazt az értéket, ugyanazt az ábrát adja, mint a Python-oldal (`kozos.matek.elemez`, `formatum`). A fájlokat a
`bin/mos grafikon vektorok --ir` állítja elő; ez a teszt az elsodródást fogja meg (SymPy-frissítés, a formátum változása)."""
import json
import math
import sys
import unittest

from tests.helpers import REPO

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from grafikon import formatum as F  # noqa: E402
from grafikon import vektorok as V  # noqa: E402

MAPPA = MODULOK / "grafikon" / "vektorok"


def egyezik(a, b, tol=1e-12) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return math.isclose(a, b, rel_tol=tol, abs_tol=1e-300)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(egyezik(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(egyezik(x, y, tol) for x, y in zip(a, b))
    return a == b


class VektorTest(unittest.TestCase):
    def test_a_vektorfajlok_naprakeszek(self):
        uj = V.general()
        for nev, tartalom in uj.items():
            fajl = MAPPA / f"{nev}.json"
            self.assertTrue(fajl.exists(), f"hiányzik: {fajl} (bin/mos grafikon vektorok --ir)")
            self.assertTrue(egyezik(json.loads(fajl.read_text(encoding="utf-8")), tartalom),
                            f"elsodródott: {nev}.json (bin/mos grafikon vektorok --ir)")

    def test_a_kifejezes_vektor_alakja_es_lefedettsege(self):
        v = json.loads((MAPPA / "kifejezes.json").read_text(encoding="utf-8"))
        kif = {t["kifejezes"] for t in v["tetelek"]}
        for kell in ("-x^2", "2^-x", "x^(1/3)", "root(x,3)", "sqrt(x)", "abs(x)", "log(x, 2)", "ln(x)", "lg(x)",
                     "e^(-x^2)", "(x+1)(x-1)", "2sin(x)", "sin(x)^2", "tan(x)", "(x^2-1)/(x-1)", "atan(x)"):
            self.assertIn(kell, kif)
        self.assertGreaterEqual(len({t["kifejezes"] for t in v["tetelek"]}), 55)
        self.assertTrue(any(t["ertek"] is None for t in v["tetelek"]))               # tartományon kívüli pontok
        for t in v["tetelek"]:
            self.assertTrue(t["ertek"] is None or math.isfinite(t["ertek"]), t)

    def test_az_aranytetelek_kifejezese_a_felismero_kimenete(self):
        v = json.loads((MAPPA / "kifejezes.json").read_text(encoding="utf-8"))
        arany = [t for t in v["tetelek"] if t.get("forras", "").startswith("arany:")]
        self.assertEqual(len({t["forras"] for t in arany}), 15)

    def test_paratlan_gyok_valos(self):
        v = json.loads((MAPPA / "kifejezes.json").read_text(encoding="utf-8"))
        gy = {(t["kifejezes"], t["x"]): t["ertek"] for t in v["tetelek"]}
        self.assertAlmostEqual(gy[("root(x,3)", -8.0)], -2.0, places=12)
        self.assertAlmostEqual(gy[("x^(2/3)", -8.0)], 4.0, places=12)
        self.assertIsNone(gy[("sqrt(x)", -1.0)])
        self.assertIsNone(gy[("log(x)", 0.0)])

    def test_a_hibas_listak_besorolasa(self):
        """`hibas_mindketto`: az `elemez` is elutasítja; `hibas_csak_ts`: a felület szigorúbb (D-4)."""
        from kozos import matek
        v = json.loads((MAPPA / "kifejezes.json").read_text(encoding="utf-8"))
        for kif in v["hibas_mindketto"]:
            with self.assertRaises(matek.MatekHiba, msg=kif):
                matek.elemez(kif)
        for kif in v["hibas_csak_ts"]:
            matek.elemez(kif)                         # a Python elfogadja (a felület szándékosan nem)

    def test_a_forras_vektor_korutja_es_alakja(self):
        v = json.loads((MAPPA / "forras.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(v["tetelek"]), 30)
        for t in v["tetelek"]:
            a = F.elemez(t["szoveg"])
            self.assertEqual(F.abra_szotar(a), t["abra"], t["szoveg"])
            self.assertEqual(F.szerializal(a), t["kanonikus"], t["szoveg"])
            self.assertEqual(F.szerializal(F.elemez(t["kanonikus"])), t["kanonikus"], "fixpont")

    def test_a_forras_vektor_fedi_a_formatum_szeleit(self):
        v = json.loads((MAPPA / "forras.json").read_text(encoding="utf-8"))
        osszes = " ".join(t["szoveg"] for t in v["tetelek"])
        for kell in ("x in [", "y in [", "pont (", "t in [", ">=", "<=", "# ", '\\"', "−", "≤"):
            self.assertIn(kell, osszes, kell)
        hibasak = [t for t in v["tetelek"] if t["abra"]["hibak"]]
        self.assertGreaterEqual(len(hibasak), 4)
        self.assertTrue(any(len(t["szoveg"]) > F.MAX_SOR for t in v["tetelek"]))        # plafon: túl hosszú sor
        self.assertTrue(any(len(t["abra"]["elemek"]) >= F.MAX_ELEM for t in v["tetelek"]))   # plafon: 64 elem

    def test_az_aranytetelek_blokkja_a_forras_vektorban(self):
        v = json.loads((MAPPA / "forras.json").read_text(encoding="utf-8"))
        arany = [t for t in v["tetelek"] if t.get("forras", "").startswith("arany:")]
        self.assertEqual(len(arany), 15)
        for t in arany:
            self.assertEqual(t["abra"]["hibak"], [], t["forras"])
            self.assertEqual(len(t["abra"]["elemek"]), 1)


if __name__ == "__main__":
    unittest.main()
