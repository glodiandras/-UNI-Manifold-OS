"""C35a: a grafikon-műveletek a CAS-homokozóban (`grafikon.felismeres`, `grafikon.elemzes`). A jegyzet sorai nem
megbízható bemenet (CLAUDE.md 46. döntés): a SymPy csak a homokozó gyermekében értelmezi őket. A belépési pontok
(`modulok/grafikon/muveletek.py`) folyamaton belül gyorsan tesztelhetők; a határt a valódi `sandbox-exec` alatt
futó rész (csak macOS) próbálja."""
import json
import sys
import unittest

from tests.helpers import REPO, alg_core, tmpdir

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from grafikon import felismeres as R  # noqa: E402
from grafikon import formatum as F  # noqa: E402
from grafikon import jegyzet as J  # noqa: E402
from grafikon import muveletek as M  # noqa: E402
from homokozo import Homokozo, proba  # noqa: E402

MACOS = sys.platform == "darwin"

JEGYZET = (
    "# Függvények\n\nA parabola:\n\n$$f(x) = x^2 - 4x + 5$$\n\n"
    "```plot\ny = x^2\n```\n\nEgyenlet: $2x+1=0$, majd $y = 2x + 1$ egyenes.\n"
)


class MuveletTest(unittest.TestCase):
    """A gyermek belépési pontja: JSON be, JSON ki."""

    def test_felismeres_json_alak(self):
        r = M.felismeres("y = x^2 + 2")
        self.assertEqual((r["fajta"], r["bizonyossag"]), ("fuggveny", "biztos"))
        self.assertEqual(r["blokk"], R.felismer("y = x^2 + 2").blokk)
        self.assertEqual(r["abra"]["elemek"][0], {"fajta": "fuggveny", "kifejezes": "x^2 + 2", "cimke": None})
        self.assertEqual(json.loads(json.dumps(r, ensure_ascii=False)), r)         # JSON-ható, veszteség nélkül

    def test_elemzes_json_alak(self):
        r = M.elemzes("x^2 - 4", ["-3", "3"])
        self.assertEqual([p["x"] for p in r["zerushelyek"]], ["-2", "2"])
        self.assertEqual(r["szelsoertekek"][0]["tipus"], "minimum")
        self.assertEqual(json.loads(json.dumps(r, ensure_ascii=False)), r)
        self.assertEqual(M.elemzes("x +", ["-3", "3"])["allapot"], "hiba")

    def test_felismeres_nincs_es_bizonytalan_is_valasz(self):
        self.assertEqual(M.felismeres("2x + 1 = 0")["bizonyossag"], "nincs")
        r = M.felismeres(r"x^2 + y^2 = 1")
        self.assertEqual(r["bizonyossag"], "bizonytalan")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["abra"])
        self.assertEqual(r["blokk"], "")

    def test_abra_szotar_minden_elemfajta(self):
        a = F.elemez('x in [-4, 4]\ny = x^2 "f"\nx = 3*cos(t), y = 2*sin(t), t in [0, 2*pi]\ny >= x\n'
                     'pont (2, 1) "p"\n# m\nvalami')
        s = F.abra_szotar(a)
        self.assertEqual(s["x_tartomany"], ["-4", "4"])
        self.assertIsNone(s["y_tartomany"])
        self.assertEqual([e["fajta"] for e in s["elemek"]],
                         ["fuggveny", "parameteres", "egyenlotlenseg", "pont", "megjegyzes", "ismeretlen"])
        self.assertEqual(s["elemek"][1]["tartomany"], ["0", "2*pi"])
        self.assertEqual(s["hibak"], [[7, "ismeretlen vagy hibás sor"]])

    def test_ismeretlen_tipus_es_tul_hosszu_bemenet_hiba(self):
        with self.assertRaises(ValueError):
            M.felismeres("x" * 5000)
        with self.assertRaises(TypeError):
            M.felismeres(12)


class JegyzetKivagasTest(unittest.TestCase):
    """A kivágás a szülőben fut (csak reguláris kifejezés, SymPy nélkül); a felismerés kifejezésenként a gyermekben."""

    def test_jeloltek_sorrendben_es_a_kodblokk_kimarad(self):
        j = J.jeloltek(JEGYZET)
        self.assertEqual([k for _, k in j], ["f(x) = x^2 - 4x + 5", "2x+1=0", "y = 2x + 1"])
        self.assertEqual([JEGYZET.count("\n", 0, i) + 1 for i, _ in j], [5, 11, 11])

    def test_hely_adatok_sor_veg_sor_es_blokk_kovetkezik(self):
        j = J.jeloltek(JEGYZET)
        h = J.hely(JEGYZET, j[0][0], j[0][1], F.blokkok(JEGYZET))
        self.assertEqual(h, {"sor": 5, "veg_sor": 5, "blokk_kovetkezik": True})
        h = J.hely(JEGYZET, j[2][0], j[2][1], F.blokkok(JEGYZET))
        self.assertEqual(h, {"sor": 11, "veg_sor": 11, "blokk_kovetkezik": False})

    def test_a_felismero_ugyanazt_adja_mint_a_kivagas_plusz_felismeres(self):
        ki = R.felismer_jegyzet(JEGYZET)
        self.assertEqual([(j.sor, j.forras_keplet) for j in ki], [(5, "f(x) = x^2 - 4x + 5"), (11, "y = 2x + 1")])

    def test_a_jegyzet_modul_nem_importal_sympyt(self):
        """A szülő-oldali kivágás sympy nélkül fut: a modul forrása nem hivatkozik rá."""
        forras = (MODULOK / "grafikon" / "jegyzet.py").read_text(encoding="utf-8")
        self.assertNotIn("sympy", forras)


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class HomokozoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.cfg, _, _ = alg_core(cls._t.name)
        cls.hk = Homokozo(cls.cfg)
        if not cls.hk.sandbox_exec:
            raise AssertionError("macOS-en a sandbox-exec kötelező")

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_felismeres_a_homokozoban_egyezik_a_folyamaton_beluli_eredmennyel(self):
        e = self.hk.egy({"muvelet": "hivas", "nev": "grafikon.felismeres", "args": {"keplet": "y = x^2 + 2"}})
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual(e["ertek"], M.felismeres("y = x^2 + 2"))
        self.assertEqual(e["ertek"]["bizonyossag"], "biztos")

    def test_elemzes_a_homokozoban_egyezik_a_folyamaton_beluli_eredmennyel(self):
        args = {"kifejezes": "x^3 - 3*x", "ablak": ["-3", "3"], "lepes_idokorlat_s": 3.0}
        e = self.hk.egy({"muvelet": "hivas", "nev": "grafikon.elemzes", "args": args}, idokorlat_s=20)
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual(e["ertek"], M.elemzes(**args))

    def test_tobb_keplet_egy_gyermekben(self):
        kepletek = ["y = \\sin 2x", "f(x) = \\sqrt{x+3} - 2", "2x+1=0"]
        e = self.hk.futtat([{"muvelet": "hivas", "nev": "grafikon.felismeres", "args": {"keplet": k}}
                            for k in kepletek])
        self.assertEqual([x["allapot"] for x in e], ["ok"] * 3)
        self.assertEqual([x["ertek"]["bizonyossag"] for x in e], ["biztos", "biztos", "nincs"])

    def test_mas_modulok_adatai_tovabbra_sem_olvashatok(self):
        """A profil a `grafikon` kódját engedi (a felismerő és a mérő ezt tölti), az aranyhalmazt és a többi modult nem."""
        for ut in (MODULOK / "eval" / "grafikon" / "arany.json", MODULOK / "kartya" / "formatum.py"):
            e = self.hk.egy({"muvelet": "kod", "kod": proba._kitores(
                f"__import__('builtins').open({str(ut)!r}).read()")})
            self.assertEqual(e["allapot"], "tiltott", (ut, e))

    def test_a_grafikon_nem_importalhato_nem_megbizhato_kodbol(self):
        e = self.hk.egy({"muvelet": "kod", "kod": "import grafikon\nEREDMENY = 1"})
        self.assertEqual(e["allapot"], "tiltott", e)

    def test_ismeretlen_grafikon_muvelet_tiltott(self):
        e = self.hk.egy({"muvelet": "hivas", "nev": "grafikon.felismer_jegyzet", "args": {"szoveg": "x"}})
        self.assertEqual(e["allapot"], "tiltott", e)


if __name__ == "__main__":
    unittest.main()
