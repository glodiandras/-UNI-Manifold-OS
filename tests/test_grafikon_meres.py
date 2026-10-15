"""C35a: a mérés (`bin/mos grafikon arany`): a C18 `grafikon` aranyhalmaza és a cloud szintetikus halmaza a homokozón át
(itt hamis homokozóval, amely a gyermek belépési pontjait folyamaton belül hívja; a valódi sandbox csak macOS-en).
A riport az aranyhalmaz-pontozó (`feladat.pontoz_egyet`) mércéjével mér: a CAS-jellemzők ugyanúgy, mint a modellé."""
import sys
import unittest

from tests.helpers import REPO, alg_core, tmpdir
from tests.test_grafikon_burok import HamisHomokozo

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from grafikon import meres  # noqa: E402

MACOS = sys.platform == "darwin"


class RiportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = meres.arany_riport(HamisHomokozo())

    def test_a_felismeres_15_a_15bol_biztos_es_helyes_ablak_lefedessel(self):
        f = self.r["felismeres"]
        self.assertEqual((self.r["osszes"], f["biztos_helyes"], f["biztos_rossz"], f["bizonytalan"], f["nincs"]),
                         (15, 15, 0, 0, 0))
        self.assertEqual(f["lefedes"], 15)

    def test_a_cas_jellemzok_a_modell_pontozoja_szerint_teljes_pontot_kapnak(self):
        j = self.r["jellemzok"]
        self.assertEqual(j["pontszam"], 1.0)
        for kulcs in ("zerushelyek", "szelsoertekek", "aszimptotak", "tipus"):
            self.assertEqual(j[kulcs], 15, kulcs)
        self.assertEqual(j["reszleges"], 0)

    def test_a_szintetikus_halmazon_nincs_tevedes(self):
        k = self.r["kiegeszito"]
        self.assertEqual((k["biztos_rossz"], k["tevedes"], k["bizonytalan_biztos_helyett"]), (0, 0, 0))
        self.assertGreaterEqual(k["biztos_helyes"], 20)

    def test_a_homokozo_es_a_folyamaton_beluli_ut_azonos(self):
        a = self.r["azonossag"]
        self.assertEqual(a["osszes"], 15 + self.r["kiegeszito"]["osszes"])
        self.assertEqual((a["azonos"], a["elteres"]), (a["osszes"], []))

    def test_a_kontextus_a_szovegbeli_kepletekbol(self):
        k = self.r["kontextus"]
        self.assertGreaterEqual(k["tetelek"], 9)                 # a `szoveg`-ben `$…$` képlet áll
        # a g03 `$f: y = (x+5)^2 = x^2+10x+25$` címkés egyenlőség-lánc: tervezetten „bizonytalan”/implicit, a modell-ágra marad
        self.assertEqual(k["hianyzik"], ["g03"])
        self.assertEqual(k["megtalalt"], k["tetelek"] - 1)
        self.assertTrue(all("id" in t and "keplet" in t for t in k["tobblet"]))

    def test_a_szoveg_olvashato_es_tartalmazza_a_szamokat(self):
        s = meres.riport_szoveg(self.r)
        self.assertIn("15/15", s)
        self.assertIn("pontszám", s)
        self.assertIn("RENDBEN", s)


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class ValodiHomokozoTest(unittest.TestCase):
    def test_a_riport_a_valodi_sandbox_alatt_is_teljes(self):
        from homokozo import Homokozo
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = alg_core(t.name)
        r = meres.arany_riport(Homokozo(cfg))
        self.assertEqual(r["felismeres"]["biztos_helyes"], 15)
        self.assertEqual(r["jellemzok"]["pontszam"], 1.0)
        self.assertEqual(r["azonossag"]["elteres"], [])


if __name__ == "__main__":
    unittest.main()
