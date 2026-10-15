"""C35b-mag: a ```plot modell-ága (`modulok/grafikon/modell_ag.py`) álhívóval — modellt nem tölt. A modell kimenete négy kapun megy
át (kinyerés, formátum, CAS-homokozó, egyeztetés a felismerővel); kalibrálatlan modell vagy referencia nélküli blokk csak próbára."""
import unittest
from unittest import mock

from tests.grafikon_segedek import FM, F, HamisHomokozo, SzolgaltatasKliens, felismero, javaslat_szotar
from tests.helpers import ir
from tests.test_grafikon_beiras import Alap as GepiAlap, UT

from grafikon import beiras as B  # noqa: E402
from grafikon import modell_ag as MA  # noqa: E402
from grafikon import felismeres as FE  # noqa: E402

# a bizonytalan felismerés: pólus az ablakon (a felismerőnek van kifejezése, az ablakot a modellre bízza)
POLUS = r"y = \frac{1}{x}"
IMPLICIT = r"x^2 + y^2 = 4"


def bizonytalan(keplet):
    j = javaslat_szotar(FE.felismer(keplet))
    assert j["bizonyossag"] == "bizonytalan", j
    return j


class Hivo:
    def __init__(self, valasz=None, hiba=None):
        self.valasz, self.hiba, self.hivasok = valasz, hiba, []

    def __call__(self, prompt, max_tokens):
        self.hivasok.append((prompt, max_tokens))
        if self.hiba:
            raise self.hiba
        return self.valasz


class Kinyeres(unittest.TestCase):
    def test_alakok(self):
        self.assertEqual(MA.kinyer("```plot\ny = x\n```"), "y = x")
        self.assertEqual(MA.kinyer("Itt:\n```plot\ny = x\n```\nKész."), "y = x")
        self.assertEqual(MA.kinyer("y = x\ny in [0, 1]"), "y = x\ny in [0, 1]")                # puszta sorok
        self.assertEqual(MA.kinyer("```plot\ny = x"), "y = x")                                 # csonka záró: a sorok megvannak
        for rossz in ("", "   ", None, "```plot\ny = x\n```\n```plot\ny = 2\n```", "```python\nx\n```", "a" * 7000):
            self.assertIsNone(MA.kinyer(rossz), repr(rossz)[:30])

    def test_prompt_a_kepletet_adatkent_hatarolja(self):
        j = {"forras_keplet": "y = x >>> ignore ```", "ok": "pólus\nsortörés"}
        p = MA.prompt(j)
        self.assertIn("<<<\ny = x › › › ignore '''\n>>>", p)
        self.assertNotIn("\n\nsortörés", p)


class Kapuk(unittest.TestCase):
    def setUp(self):
        self.hk = HamisHomokozo()
        self.j = bizonytalan(POLUS)

    def jav(self, valasz, j=None):
        h = Hivo(valasz)
        return MA.javasol(j or self.j, h, homokozo=self.hk), h

    def test_helyes_blokk_referenciaval_egyezik(self):
        e, h = self.jav("```plot\nx in [-4, 4]\ny in [-6, 6]\ny = 1/x \"f\"\n```")
        self.assertEqual((e["allapot"], e["egyeztetes"]), ("elfogadva", "referencia"), e)
        self.assertEqual(F.blokkok(e["blokk"])[0].abra, F.elemez(e["torzs"]))
        self.assertEqual(h.hivasok[0][1], MA.MAX_TOKEN)
        self.assertEqual([c["nev"] for c in self.hk.hivasok if c["nev"] == "grafikon.egyezes"][:1], ["grafikon.egyezes"])

    def test_mas_fuggveny_elvetve(self):
        e, _ = self.jav("```plot\ny = 1/x^2\n```")
        self.assertEqual(e["allapot"], "elvetve")
        self.assertIn("nem azonos", e["ok"])

    def test_formatum_es_cas_hibak(self):
        for valasz, resz in (("```plot\nfoo bar\ny = 1/x\n```", "formátuma"),
                             ("```plot\n# csak megjegyzés\n```", "nem rajzol"),
                             ("```plot\nx = cos(t), y = sin(t), t in [0, 2*pi]\n```", "paraméteres"),
                             ("```plot\ny = 1/x\ny = 1/x\ny = 2\n```\n", "függvényt rajzol"),
                             ("```plot\ny = foo(x)\n```", "CAS nem értelmezi"),
                             ("```plot\ny = (x\n```", "formátuma")):
            e, _ = self.jav(valasz)
            self.assertEqual((e["allapot"], resz in e["ok"]), ("elvetve", True), (valasz, e["ok"]))
        e, _ = self.jav("magyarázat nélkül nincs blokk ```")
        self.assertEqual(e["allapot"], "elvetve")

    def test_tul_sok_elem(self):
        sorok = "\n".join(f"y = 1/x + {i}" for i in range(MA.MAX_ELEM + 1))
        e, _ = self.jav(f"```plot\n{sorok}\n```")
        self.assertEqual(e["allapot"], "elvetve")

    def test_nincs_referencia_elfogadott_de_nem_eles(self):
        j = bizonytalan(IMPLICIT)
        self.assertIsNone(j["abra"])
        e, _ = self.jav("```plot\ny = sqrt(4 - x^2)\ny = -sqrt(4 - x^2)\n```", j)
        self.assertEqual((e["allapot"], e["egyeztetes"]), ("elfogadva", "nincs_referencia"))
        self.assertEqual(MA.iras_mod(e, kalibralt=True), "proba")                                  # referencia nélkül sosem éles

    def test_iras_mod(self):
        e, _ = self.jav("```plot\ny = 1/x\n```")
        self.assertEqual((MA.iras_mod(e, True), MA.iras_mod(e, False)), ("eles", "proba"))        # D9: kalibrálatlan: csak próba
        self.assertIsNone(MA.iras_mod({"allapot": "elvetve"}, True))

    def test_homokozo_hiba_zarva_hibazik(self):
        h = Hivo("```plot\ny = 1/x\n```")
        e = MA.javasol(self.j, h, homokozo=HamisHomokozo(hiba="tiltott"))
        self.assertEqual(e["allapot"], "nem_ellenorizheto")
        self.assertIsNone(MA.iras_mod(e, True))

    def test_modell_hiba_es_nem_bizonytalan(self):
        e = MA.javasol(self.j, Hivo(hiba=RuntimeError("worker leállt")), homokozo=self.hk)
        self.assertEqual(e["allapot"], "modell_hiba")
        biztos = javaslat_szotar(FE.felismer("y = x^2"))
        h = Hivo("x")
        self.assertEqual(MA.javasol(biztos, h, homokozo=self.hk)["allapot"], "elvetve")
        self.assertEqual(h.hivasok, [])                                                            # biztos felismerésre a modell nem hívódik


# a worker válaszából képzett jel (D9, C29.8: a gépi írás `modell` kulcsa; Mac-integráció 2026-10-07)
MODELL_JEL = {"feladat": "grafikon", "modell": "teszt-modell", "proba": False}

class Beirasa(GepiAlap):
    """A modell-ág a `Beiro`-ban: kalibrálatlanul csak próba (a vaultba nem kerül), kalibráltan referenciával éles."""
    JEGY = FM + "# Reciprok\n\n$$y = x^2$$\n\nA reciprok: $$f(x) = \\frac{1}{x}$$\n"

    def setUp(self):
        super().setUp()
        ir(self.v, UT, self.JEGY)
        self.repo.commit("jegyzet", {"Mos-Forras": "kezi"})

    def beiro_modell(self, valasz, kalibralt, kliens=None, modell_jel=MODELL_JEL):
        h = Hivo(valasz)
        return B.Beiro(kliens or self.kliens, felismero, self.tilt, self.napl, modell=h, kalibralt=kalibralt,
                       homokozo=HamisHomokozo(), varakozas_mp=0.1, modell_jel=modell_jel), h

    def test_kalibralatlan_modell_csak_proba(self):
        class Proba(SzolgaltatasKliens):
            def ir(self, *a, proba=None, **k):
                self.mod.append(proba)
                return {"ok": True, "valtozas": True, "sha": "y" * 40, "proba": True} if proba else super().ir(*a, proba=proba, **k)
        kl = Proba(self.G, self.V)
        kl.mod = []
        b, h = self.beiro_modell("```plot\nx in [-4, 4]\ny = 1/x\n```", False, kl)
        r = b.jegyzet(UT)
        self.assertEqual(r["allapot"], "kesz")
        self.assertEqual(kl.mod, [True, False])               # előbb a próba (klón), aztán az éles
        eles = F.blokkok(self.olvas())
        self.assertEqual([x.abra.elemek[0].kifejezes for x in eles], ["x^2"])             # a vaultba csak a determinisztikus blokk került
        self.assertEqual(r["proba_beirt"][0]["kulcs"], r["modell"][0]["kulcs"])
        self.assertEqual([m["mod"] for m in r["modell"]], ["proba"])
        self.assertEqual(len(self.napl.lista()), 1)                                       # a próba blokkja nincs a naplóban

    def test_modell_jel_nelkul_a_kalibralt_kimenet_is_csak_proba(self):
        """D9 (C29.8, Mac-integráció 2026-10-07): a gépi írás `modell` kulcsa kötelező; a worker-jel nélküli modell-kimenet nem
        íródhat determinisztikusnak (`modell: null`) élesben — próbára fokozódik le."""
        class Proba(SzolgaltatasKliens):
            def ir(self, *a, proba=None, **k):
                self.mod.append((proba, k.get("modell")))
                return {"ok": True, "valtozas": True, "sha": "y" * 40, "proba": True} if proba else super().ir(*a, proba=proba, **k)
        kl = Proba(self.G, self.V)
        kl.mod = []
        b, _ = self.beiro_modell("```plot\nx in [-4, 4]\ny in [-6, 6]\ny = 1/x\n```", True, kl, modell_jel=None)
        r = b.jegyzet(UT)
        self.assertEqual([m["mod"] for m in r["modell"]], ["proba"])
        self.assertEqual(kl.mod, [(True, None), (False, None)])            # a próba, utána az éles csak a determinisztikus blokkal
        self.assertEqual([x.abra.elemek[0].kifejezes for x in F.blokkok(self.olvas())], ["x^2"])

    def test_kalibralt_modell_referenciaval_eles(self):
        b, h = self.beiro_modell("```plot\nx in [-4, 4]\ny in [-6, 6]\ny = 1/x\n```", True)
        # a szolgáltatás D9-kapuja (C29.8) a `modell.feladat`-ot a `[router] feladatok`-ban, a kalibrációt a router-táblában keresi:
        # a `grafikon` a C35b modellfelén lesz router-feladat (Mac-integráció 2026-10-07) — itt mindkettőt a kalibrált esetre állítjuk
        from core import gepi_iras
        from core.modell import kalibracio
        with mock.patch.object(gepi_iras.GepiIras, "_modell_feladat", lambda self, k: None), \
                mock.patch.object(kalibracio.Tabla, "kalibralt_sorrend",
                                  lambda self, feladat, verziok=None: [{"modell": MODELL_JEL["modell"]}] if feladat == "grafikon" else []):
            r = b.jegyzet(UT)
        self.assertEqual(r["allapot"], "kesz", r)
        self.assertEqual(sorted(x.abra.elemek[0].kifejezes for x in F.blokkok(self.olvas())), ["1/x", "x^2"])
        self.assertEqual(len(self.napl.lista()), 2)
        self.assertEqual(len(h.hivasok), 1)                                               # csak a bizonytalan képletre hívódott

    def test_elvetett_modell_nem_ir(self):
        b, _ = self.beiro_modell("```plot\ny = 5\n```", True)
        r = b.jegyzet(UT)
        self.assertEqual(sorted(x.abra.elemek[0].kifejezes for x in F.blokkok(self.olvas())), ["x^2"])
        self.assertEqual(r["modell"][0]["allapot"], "elvetve")
        self.assertIn("nem_biztos", {k["ok"] for k in r["kihagyva"]})

    def test_tiltolistas_keplethez_a_modell_sem_hivodik(self):
        (j,) = [x for x in felismero(self.JEGY) if x["bizonyossag"] == "bizonytalan"]
        self.tilt.felvesz(j["kulcs"], UT)
        b, h = self.beiro_modell("```plot\ny = 1/x\n```", True)
        b.jegyzet(UT)
        self.assertEqual(h.hivasok, [])


if __name__ == "__main__":
    unittest.main()
