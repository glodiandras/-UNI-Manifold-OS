"""C35a: a CAS-jellemzők (`modulok/grafikon/jellemzok.py`): zérushely, szélsőérték, aszimptota egy függvény ablakán.

A logika folyamaton belül fut (gyors); élesben ugyanez a homokozó gyermekében (`grafikon.elemzes`). Az aranyhalmaz
15 tételén a **modell pontozója** (`modulok/eval/grafikon/feladat.py`) dönt: az elemző kimenete a modell válaszának
alakjába van átírva (`meres.valasz_alak`), így a mérés ugyanaz, mint a modellé — a szabály: darabszám és 0,01 tűrés."""
import importlib.util
import json
import sys
import time
import unittest

from tests.helpers import REPO

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from grafikon import jellemzok as E  # noqa: E402
from grafikon import felismeres as R  # noqa: E402
from grafikon import meres  # noqa: E402


def _arany_modul():
    spec = importlib.util.spec_from_file_location("mos_eval_grafikon_teszt", MODULOK / "eval" / "grafikon" / "feladat.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FELADAT = _arany_modul()


def ablak_szoveg(s: str) -> list[str]:
    a, b = s.strip("[]").split(",")
    return [a.strip(), b.strip()]


def sorszamok(eredmeny, kulcs):
    return [p["x"] for p in eredmeny[kulcs]]


class AranyTest(unittest.TestCase):
    def test_a_15_aranytetel_a_modell_pontozoja_szerint_teljes_pontot_kap(self):
        for k in FELADAT.ARANY["kepletek"]:
            vart = k["vart"]
            j = R.felismer(k["keplet"])
            self.assertEqual(j.bizonyossag, R.BIZTOS, (k["id"], j.ok))
            kif = j.abra.elemek[0].kifejezes
            e = E.elemez(kif, ablak_szoveg(vart["ablak"]))
            self.assertEqual(e["allapot"], "ok", (k["id"], e))
            pont = FELADAT.pontoz_egyet(vart, json.dumps(meres.valasz_alak(e, kif)))
            self.assertEqual(pont["pont"], 1.0, (k["id"], pont, e))

    def test_a_szelsoertek_tipusa_is_egyezik(self):
        """A modell-pontozó a `tipus`-t nem nézi; a CAS-oldal igen."""
        for k in FELADAT.ARANY["kepletek"]:
            vart = k["vart"]
            kif = R.felismer(k["keplet"]).abra.elemek[0].kifejezes
            e = E.elemez(kif, ablak_szoveg(vart["ablak"]))
            self.assertEqual(sorted((float(eval_szam(p["x"])), p["tipus"]) for p in e["szelsoertekek"]),
                             sorted((float(eval_szam(p["x"])), p["tipus"]) for p in vart["szelsoertekek"]), k["id"])


def eval_szam(szoveg: str) -> float:
    import sympy as sp
    from kozos import matek
    return float(sp.N(matek.elemez(szoveg), 20))


class AlakTest(unittest.TestCase):
    def test_json_alak_veges_szamok(self):
        e = E.elemez("x^3 - 3*x", ["-3", "3"])
        self.assertEqual(json.loads(json.dumps(e, ensure_ascii=False)), e)
        self.assertEqual(e["zerushelyek"][0], {"x": "-sqrt(3)", "ertek": -1.7320508075688772})
        self.assertEqual(e["szelsoertekek"][0],
                         {"x": "-1", "y": "2", "x_ertek": -1.0, "y_ertek": 2.0, "tipus": "maximum"})
        self.assertFalse(e["numerikus"])
        self.assertEqual(e["aszimptotak"], [])

    def test_az_ablak_szoveg_vagy_szam(self):
        a = E.elemez("sin(x)", ["-2*pi", "2*pi"])
        b = E.elemez("sin(x)", [-7, 7])
        self.assertEqual(len(a["zerushelyek"]), 5)
        self.assertEqual(len(b["zerushelyek"]), 5)

    def test_hibas_bemenet_hibat_ad_nem_dob(self):
        for kif in ("a*x + 1", "x^2 + y", "x +", "", "x" * 400):
            e = E.elemez(kif, ["-1", "1"])
            self.assertEqual(e["allapot"], "hiba", kif)
            self.assertTrue(e["uzenet"])
        for ablak in (["1", "1"], ["2", "1"], ["a", "3"], ["-1"], None):
            e = E.elemez("x", ablak)
            self.assertEqual(e["allapot"], "hiba", ablak)


class JellemzokTest(unittest.TestCase):
    def test_reciprok_fuggoleges_es_vizszintes_aszimptota(self):
        e = E.elemez("1/x", ["-4", "4"])
        self.assertEqual([a["egyenlet"] for a in e["aszimptotak"]], ["x=0", "y=0"])
        self.assertEqual([a["tipus"] for a in e["aszimptotak"]], ["fuggoleges", "vizszintes"])
        self.assertEqual((e["zerushelyek"], e["szelsoertekek"]), ([], []))

    def test_racionalis_ket_polus(self):
        e = E.elemez("x/(x^2-1)", ["-3", "3"])
        self.assertEqual([a["egyenlet"] for a in e["aszimptotak"]], ["x=-1", "x=1", "y=0"])
        self.assertEqual(sorszamok(e, "zerushelyek"), ["0"])
        self.assertEqual(e["szelsoertekek"], [])

    def test_tangens_polusai_az_ablakban(self):
        e = E.elemez("tan(x)", ["-pi", "pi"])
        self.assertEqual([a["egyenlet"] for a in e["aszimptotak"]], ["x=-pi/2", "x=pi/2"])
        self.assertEqual(sorszamok(e, "zerushelyek"), ["-pi", "0", "pi"])

    def test_toresi_pont_szelsoertek(self):
        e = E.elemez("abs(x-2)+1", ["-3", "7"])
        self.assertEqual([(p["x"], p["y"], p["tipus"]) for p in e["szelsoertekek"]], [("2", "1", "minimum")])

    def test_az_ablak_vegpontja_nem_szelsoertek_de_zerushely_lehet(self):
        e = E.elemez("x^2", ["0", "3"])
        self.assertEqual(sorszamok(e, "zerushelyek"), ["0"])
        self.assertEqual(e["szelsoertekek"], [])

    def test_inflexio_nem_szelsoertek(self):
        e = E.elemez("x^3", ["-2", "2"])
        self.assertEqual(sorszamok(e, "zerushelyek"), ["0"])
        self.assertEqual(e["szelsoertekek"], [])

    def test_harang_maximum_es_vizszintes_aszimptota(self):
        e = E.elemez("exp(-x^2)", ["-3", "3"])
        self.assertEqual([(p["x"], p["y"], p["tipus"]) for p in e["szelsoertekek"]], [("0", "1", "maximum")])
        self.assertEqual([a["egyenlet"] for a in e["aszimptotak"]], ["y=0"])

    def test_periodikus_negy_pi_tavolsag(self):
        e = E.elemez("sin(x)", ["0", "4*pi"])
        self.assertEqual(sorszamok(e, "zerushelyek"), ["0", "pi", "2*pi", "3*pi", "4*pi"])
        self.assertEqual([(p["x"], p["tipus"]) for p in e["szelsoertekek"]],
                         [("pi/2", "maximum"), ("3*pi/2", "minimum"), ("5*pi/2", "maximum"), ("7*pi/2", "minimum")])
        self.assertEqual(e["aszimptotak"], [])

    def test_transzcendens_zerushely_numerikus_es_jelolt(self):
        e = E.elemez("x - cos(x)", ["-3", "3"])
        self.assertEqual(len(e["zerushelyek"]), 1)
        self.assertAlmostEqual(e["zerushelyek"][0]["ertek"], 0.7390851332151607, places=8)
        self.assertTrue(e["numerikus"])
        self.assertEqual(e["szelsoertekek"], [])           # az x - cos(x) szigorúan növő (a deriváltja csak érint nullát)
        self.assertTrue(any("közelítő" in f for f in e["figyelmeztetesek"]))

    def test_paratlan_gyok_valos_a_negativ_oldalon_is(self):
        """D-5: a ∛x a negatív oldalon is létezik; a SymPy főága komplex lenne."""
        e = E.elemez("root(x,3)", ["-8", "8"])
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual(len(e["zerushelyek"]), 1)
        self.assertAlmostEqual(e["zerushelyek"][0]["ertek"], 0.0, places=8)
        self.assertEqual(e["szelsoertekek"], [])
        e = E.elemez("root(x,3) - 1", ["-8", "8"])
        self.assertAlmostEqual(e["zerushelyek"][0]["ertek"], 1.0, places=8)
        self.assertEqual(len(e["zerushelyek"]), 1)

    def test_ertelmezesi_tartomany_szele_nem_aszimptota_ha_veges(self):
        e = E.elemez("sqrt(x)", ["-2", "4"])
        self.assertEqual(sorszamok(e, "zerushelyek"), ["0"])
        self.assertEqual((e["szelsoertekek"], e["aszimptotak"]), ([], []))
        self.assertIn("0", e["ertelmezes"])

    def test_ferde_aszimptota_kulon_listaban(self):
        """A `aszimptotak` a golden szabály szerint csak `x=…`/`y=…`; a ferde külön mezőben, a két irányban azonosak egyek."""
        e = E.elemez("x + 1/x", ["-4", "4"])
        self.assertEqual([a["egyenlet"] for a in e["aszimptotak"]], ["x=0"])
        self.assertEqual([a["egyenlet"] for a in e["ferde_aszimptotak"]], ["y=x"])
        self.assertEqual([(p["x"], p["y"], p["tipus"]) for p in e["szelsoertekek"]],
                         [("-1", "-2", "maximum"), ("1", "2", "minimum")])
        e = E.elemez("sqrt(3*x^2+1)", ["-4", "4"])
        self.assertEqual(e["aszimptotak"], [])
        self.assertEqual(sorted(a["egyenlet"] for a in e["ferde_aszimptotak"]), ["y=-sqrt(3)*x", "y=sqrt(3)*x"])

    def test_az_egyenes_es_a_torott_vonal_nem_aszimptotaja_onmagának(self):
        for kif in ("2x + 1", "x", "abs(x)", "abs(x) - 3", "2abs(x)"):
            e = E.elemez(kif, ["-4", "4"])
            self.assertEqual(e["ferde_aszimptotak"], [], kif)
            self.assertEqual(e["aszimptotak"], [], kif)

    def test_patologikus_kifejezes_nem_log(self):
        t = time.monotonic()
        e = E.elemez("tan(x^3)*exp(sin(x^2)) + log(x^5 + 7)", ["-1", "1.5"], lepes_idokorlat_s=0.5)
        self.assertLess(time.monotonic() - t, 60)
        self.assertIn(e["allapot"], ("ok", "reszleges"))
        json.dumps(e)
        if e["allapot"] == "reszleges":
            self.assertTrue(e["figyelmeztetesek"])


if __name__ == "__main__":
    unittest.main()
