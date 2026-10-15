"""C24a: fizika — mértékegység- és dimenzió-ellenőrzés (`modulok/matek/egyseg.py`), folyamaton belül."""
import sys
import unittest

from tests.helpers import REPO

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from matek import egyseg as E  # noqa: E402


def ell(sor, **kw):
    return E.ellenoriz(sor, **kw)


class EgysegTest(unittest.TestCase):
    def test_egyseg_kifejezesek(self):
        self.assertEqual(E.egyseg("km/h"), (E.R(5, 18), {"L": 1, "T": -1}))
        self.assertEqual(E.egyseg(r"kg\cdot m/s^2")[1], E.ERO)
        self.assertEqual(E.egyseg(r"\frac{m}{s^2}")[1], {"L": 1, "T": -2})
        self.assertEqual(E.egyseg("N m")[1], E.ENERGIA)
        self.assertEqual(E.egyseg("kWh")[0], 3600000)
        self.assertEqual(E.egyseg("1/s")[1], {"T": -1})
        for rossz in ("xyz", "m^x", "°C"):
            with self.assertRaises(E.EgysegHiba, msg=rossz):
                E.egyseg(rossz)

    def test_atvaltas_helyes_es_hibas(self):
        self.assertEqual(ell(r"v = 72\,\text{km/h} = 20\,\text{m/s}")["allapot"], "rendben")
        r = ell(r"v = 72\,\text{km/h} = 72\,\text{m/s}")
        self.assertEqual((r["allapot"], r["elso_hiba"]["tag"], r["elso_hiba"]["fajta"]), ("hiba", 3, "ertek_elteres"))
        self.assertEqual(ell(r"h = 1{,}5\,\text{km} = 1500\,\text{m}")["elso_hiba"], None)
        self.assertEqual(ell(r"\Delta t = 2\,\text{min} = 120\,\text{s}")["allapot"], "rendben")

    def test_dimenzio_elteres(self):
        r = ell(r"F = ma = 2\,\text{kg}\cdot 3\,\text{m/s} = 6\,\text{N}")
        self.assertEqual((r["elso_hiba"]["tag"], r["elso_hiba"]["fajta"]), (3, "dimenzio_elteres"))
        self.assertEqual(ell(r"F = ma = 2\,\text{kg}\cdot 3\,\text{m/s^2} = 6\,\text{N}")["allapot"], "rendben")

    def test_szimbolikus_keplet_osszeadandok_es_fuggveny_argumentum(self):
        r = ell(r"s = v t + \frac{a}{2} t^2")
        self.assertEqual(r["allapot"], "rendben")
        self.assertEqual(r["feltetelezett"], {"a": "m/s^2", "s": "m", "t": "s", "v": "m/s"})
        self.assertEqual(ell(r"s = v t + \frac{a}{2} t")["elso_hiba"]["fajta"], "osszeg_dimenzio")
        j = {"x": "m", "A": "m", "omega": "1/s"}
        self.assertEqual(ell(r"x = A \sin(\omega t)", jelolesek=j)["allapot"], "rendben")
        self.assertEqual(ell(r"x = A \sin(\omega)", jelolesek=j)["elso_hiba"]["fajta"], "argumentum_dimenzio")

    def test_valtozo_es_egyseg_szetvalasztasa(self):
        r = ell("2t = 4")                                        # 2·t (idő), nem 2 tonna
        self.assertEqual(r["tagok"][0]["dimenzio"], "s")
        r = ell(r"m = 2\,\text{t} = 2000\,\text{kg}")              # \text-ben: tonna
        self.assertEqual(r["allapot"], "rendben")                 # m alapból kg; 2 t = 2000 kg
        self.assertEqual(ell(r"m = 2\,\text{t} = 200\,\text{kg}")["elso_hiba"]["fajta"], "ertek_elteres")
        self.assertEqual(ell("v_0 = 5 m/s")["allapot"], "rendben")   # szóközzel: egység

    def test_nem_talalgat(self):
        r = ell("p = m v")
        self.assertEqual(r["allapot"], "reszben_ellenorizve")
        self.assertIn("ismeretlen jel", r["tagok"][0]["ok"])
        self.assertEqual(ell("p = m v", jelolesek={"p": "kg*m/s"})["allapot"], "rendben")
        self.assertEqual(ell(r"T = 20\,\text{°C} = 293\,\text{K}")["allapot"], "nem_ellenorizheto")
        self.assertEqual(ell("p = m v", alap_jelolesek=False)["allapot"], "nem_ellenorizheto")
        self.assertEqual(ell("v")["allapot"], "nem_ellenorizheto")
