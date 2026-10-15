"""C24a: levezetés-ellenőrzés modell nélkül (`modulok/matek`): a sorelemző, az ekvivalencia-szemantika, a C18
`matek_ellenorzo` halmaza (10 hibás + 10 helyes levezetés) és egy teljes út a homokozón át.

A logika folyamaton belül fut (gyors); élesben ugyanez a homokozó gyermekében. A sorelemző szabályai ezen a
20 levezetésen készültek: a C18-számok regressziós korlátok, nem független mérés (K98: saját jegyzeten)."""
import json
import sys
import unittest

from tests.helpers import REPO, alg_core, tmpdir

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

import matek  # noqa: E402
from matek import levezetes as L  # noqa: E402
from matek import sorelemzo as SE  # noqa: E402

ARANY = json.loads((MODULOK / "eval" / "matek" / "arany.json").read_text(encoding="utf-8"))


def itelet(sorok, **kw):
    return L.ellenoriz(sorok, **kw)


class SorelemzoTest(unittest.TestCase):
    def test_egymasba_agyazott_abszolut_ertek_es_log_alap(self):
        s = SE.elemez_sor(r"|5-|x||=3")
        self.assertEqual(s.fajta, "egyenlet")
        self.assertEqual(str(s.agak[0][0].bal), "Abs(Abs(x) - 5)")
        s = SE.elemez_sor(r"\log_3\frac{(x+8)(x-2)}{x+4}=1")
        self.assertEqual(str(s.agak[0][0].bal), "log((x - 2)*(x + 8)/(x + 4))/log(3)")
        s = SE.elemez_sor(r"\log_2\big(8(x-2)\big)=\log_2(2x+8)")
        self.assertEqual(s.fajta, "egyenlet")

    def test_megoldaslista_pm_es_tizedesvesszo(self):
        s = SE.elemez_sor(r"x_{1,2}=\frac{5\pm 7}{4}")
        self.assertEqual((s.fajta, [str(v) for v in s.ertekek], s.valtozo), ("megoldas", ["3", "-1/2"], "x"))
        s = SE.elemez_sor(r"x_1=12,\ x_2=1{,}75")
        self.assertEqual([str(v) for v in s.ertekek], ["12", "7/4"])

    def test_szoveges_kototszavak(self):
        s = SE.elemez_sor(r"x=0 \text{ vagy } 2x^2-5x-3=0")
        self.assertEqual((s.fajta, len(s.agak)), ("vagy", 2))
        s = SE.elemez_sor(r"\text{A kikötés } (x>0) \text{ miatt } x=-3 \text{ nem megoldás, így } x=1")
        self.assertEqual((s.fajta, [str(v) for v in s.ertekek]), ("megoldas", ["1"]))
        self.assertEqual([(str(k.bal), k.op, str(k.jobb)) for k in s.kikotesek], [("x", ">", "0")])
        s = SE.elemez_sor(r"3^x=2 \quad (3^x=-\tfrac13 \text{ nem lehet, mert } 3^x>0)")
        self.assertEqual(s.fajta, "egyenlet")

    def test_nem_talalgat(self):
        for sor in (r"\text{Tudjuk, hogy } x=2", r"\int x\,dx", r"x \approx 1{,}73", r"f'(x)=2x", r"2x=4 \text{ és } y"):
            self.assertEqual(SE.elemez_sor(sor).fajta, "nem_elemezheto", sor)

    def test_kifejezes_folytatas_es_lanc(self):
        self.assertEqual(SE.elemez_sor("(a+b)^2").fajta, "kifejezes")
        self.assertEqual(SE.elemez_sor("=a^2+2ab+b^2").fajta, "folytatas")
        self.assertEqual(SE.elemez_sor("a = b = c").fajta, "lanc")


class AranyTest(unittest.TestCase):
    """A C18 `matek_ellenorzo` halmaza modell nélkül (C24a kész-feltétele: a felismert első hibák száma)."""

    def test_a_tiz_hibas_levezetes_elso_hibaja(self):
        felismert = pontos = 0
        for h in ARANY["levezetesek"]:
            r = itelet([s["latex"] for s in h["sorok"]])
            felismert += r["elso_hiba"] is not None
            pontos += bool(r["elso_hiba"] and r["elso_hiba"]["sor"] == h["hibas_sor"])
        self.assertEqual((felismert, pontos), (10, 10))           # mérve 2026-10-04: 10/10, mind a pontos sorban

    def test_a_tiz_helyes_kontroll_nem_riaszt(self):
        for f in ARANY["feladatok"]:
            if f.get("lepesek"):
                r = itelet([s["latex"] for s in f["lepesek"]])
                self.assertEqual(r["allapot"], "rendben", (f["id"], r))


class SzemantikaTest(unittest.TestCase):
    def test_egyenlotlenseg_es_elojelfordulas(self):
        self.assertEqual(itelet(["2x-3>5", "2x>8", "x>4"])["allapot"], "rendben")
        r = itelet(["-2x>4", "x>-2"])
        self.assertEqual((r["allapot"], r["elso_hiba"]["sor"]), ("hiba", 2))
        self.assertEqual(itelet(["-2x>4", "x<-2"])["allapot"], "rendben")
        self.assertEqual(itelet([r"x^2-5x+6\le 0", r"(x-2)(x-3)\le 0", r"2\le x\le 3"])["allapot"], "rendben")

    def test_egyenlotlenseg_ertelmezesi_tartomannyal(self):
        self.assertEqual(itelet([r"\frac{x+1}{x-2}\ge 0", r"x\le -1 \text{ vagy } x>2"])["allapot"], "rendben")
        r = itelet([r"\frac{x+1}{x-2}\ge 0", r"x\le -1 \text{ vagy } x\ge 2"])   # x = 2 nincs a tartományban
        self.assertEqual((r["allapot"], r["elso_hiba"]["sor"]), ("hiba", 2))

    def test_atmenet_fajtak(self):
        r = itelet([r"\sqrt{x+2}=x", r"x+2=x^2", r"x^2-x-2=0", r"x_1=2,\ x_2=-1", r"x=2"])
        self.assertEqual([a["itelet"] for a in r["atmenetek"]], ["bovulo", "ekvivalens", "ekvivalens", "szures"])
        self.assertEqual(r["allapot"], "rendben")
        r = itelet([r"\sqrt{x+2}=x", r"x+2=x^2", r"x^2-x-2=0", r"x_1=2,\ x_2=-1"])
        self.assertEqual((r["elso_hiba"]["sor"], r["elso_hiba"]["fajta"]), (4, "hamis_gyok_maradt"))

    def test_kikotes_a_feladat_szovegebol(self):
        self.assertEqual(itelet(["x^2=4", "x=2"])["elso_hiba"]["fajta"], "megoldas_elveszett")
        self.assertEqual(itelet(["x^2=4", "x=2"], kikotesek=["x>0"])["allapot"], "rendben")

    def test_kifejezes_lanc(self):
        self.assertEqual(itelet(["(a+b)^2", "=a^2+2ab+b^2"])["allapot"], "rendben")
        r = itelet(["(a+b)^2", "=a^2+ab+b^2"])
        self.assertEqual((r["mod"], r["elso_hiba"]["sor"], r["elso_hiba"]["fajta"]), ("kifejezes", 2, "nem_azonos"))
        self.assertEqual(itelet(["(a+b)^2 = a^2+2ab+b^2", "= b^2+2ab+a^2"])["mod"], "kifejezes")

    def test_nem_elemezheto_sor_atugrasa_bizonytalan_hellyel(self):
        r = itelet(["2x+3=7", r"\text{Tudjuk, hogy } 2x=4", "x=3"])
        self.assertEqual(r["atmenetek"][0]["itelet"], "nem_elemezheto")
        self.assertEqual((r["elso_hiba"]["sor"], r["elso_hiba"]["bizonytalan"]), (3, True))
        self.assertEqual(itelet(["2x+3=7", r"\int x\,dx", "x=2"])["allapot"], "reszben_ellenorizve")

    def test_tobb_ismeretlen_es_egy_sor_nem_ellenorizheto(self):
        self.assertEqual(itelet(["x+y=3", "x=3-y"])["allapot"], "nem_ellenorizheto")
        self.assertEqual(itelet(["x=2"])["allapot"], "nem_ellenorizheto")

    def test_a_vegeredmeny_csak_kerésre(self):
        sorok = [r"2x^3-5x^2-3x=0", r"2x^2-5x-3=0", r"x_1=3,\ x_2=-\tfrac12"]
        r = itelet(sorok)
        self.assertNotIn("vegeredmeny", r)
        self.assertIn(r["elso_hiba"]["uzenet"], L.UZENET.values())       # az üzenet nem nevez meg gyököt
        self.assertNotIn("0", json.dumps(r["elso_hiba"], ensure_ascii=False).replace('"sor": 2', ""))
        self.assertEqual(itelet(sorok, vegeredmeny=True)["vegeredmeny"], {"valtozo": "x", "halmaz": "{-1/2, 0, 3}"})

    def test_jegyzet_sorai(self):
        szoveg = "# Feladat\n\n$$\n\\begin{aligned}\n2x+3 &= 7 \\\\\n2x &= 4\n\\end{aligned}\n$$\n- $x=2$\n> $x=2$"
        self.assertEqual(matek.jegyzet_sorai(szoveg, 3, 11), ["2x+3  = 7", "2x  = 4", "x=2", "x=2"])


@unittest.skipUnless(sys.platform == "darwin", "[indokolt] a homokozó a macOS sandbox-exec-jére épül")
class HomokozonAtTest(unittest.TestCase):
    def test_levezetes_mertekegyseg_es_megoldashalmaz_a_homokozoban(self):
        from homokozo import Homokozo
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = alg_core(t.name)
        hk = Homokozo(cfg)
        r = matek.levezetes_ellenorzese(["2x+3=7", "2x=10", "x=5"], homokozo=hk)
        self.assertEqual((r["allapot"], r["elso_hiba"]["sor"]), ("hiba", 2))
        self.assertEqual(matek.egyseg_ellenorzese(r"v = 72\,\text{km/h} = 20\,\text{m/s}", homokozo=hk)["allapot"],
                         "rendben")
        self.assertEqual(matek.megoldashalmaz("x^2=9", homokozo=hk)["halmaz"], "{-3, 3}")
        rossz = Homokozo(cfg, sandbox_exec=str(t.name) + "/nincs")
        r = matek.levezetes_ellenorzese(["2x+3=7", "x=2"], homokozo=rossz)
        self.assertEqual(r["allapot"], "nem_ellenorizheto")
        self.assertIn("homokozo_hiba", r["ok"])
