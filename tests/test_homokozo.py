"""C24a: a CAS-homokozó (`modulok/homokozo`) — a biztonsági próbák (fájl, hálózat, exec, fork, jel, végtelen ciklus,
memória, tiltott import, kimenet-áradat) és az API. A gyermek a valódi `sandbox-exec` alatt fut (csak macOS);
olvasni az álvaultból és a teszt ideiglenes mappájából próbál, írni csak az ideiglenes mappába — és azt sem engedi."""
import shutil
import sys
import unittest
from pathlib import Path

from tests.helpers import REPO, alg_core, ir, tmpdir

MODULOK = REPO / "modulok"
for _ut in (MODULOK / "eval", MODULOK):
    if str(_ut) not in sys.path:
        sys.path.insert(0, str(_ut))

from homokozo import Homokozo, idozito, kod, proba  # noqa: E402

MACOS = sys.platform == "darwin"


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class BiztonsagTest(unittest.TestCase):
    """Egyszer fut le a teljes próbakészlet (egy gyermek, a leállítások után újak), a tesztek az eredményt nézik."""

    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.cfg, cls.root, cls.vault = alg_core(cls._t.name)
        jegyzet = ir(cls.vault, "M01 - Matek/Titkos.md", "titok")
        home = Path(cls._t.name) / "home"
        home.mkdir(exist_ok=True)
        cls.tmp = Path(cls._t.name) / "tmp-iras"
        cls.tmp.mkdir()
        cls.hk = Homokozo(cls.cfg)
        if not cls.hk.sandbox_exec or not Path(cls.hk.sandbox_exec).exists():
            raise AssertionError(f"macOS-en a sandbox-exec kötelező: {cls.hk.sandbox_exec}")
        cls.eredmeny = {r["nev"]: r for r in proba.futtat(cls.hk, cls.vault, home, cls.tmp, jegyzet)}

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def r(self, nev_eleje: str) -> dict:
        talalat = [r for n, r in self.eredmeny.items() if n.startswith(nev_eleje)]
        self.assertEqual(len(talalat), 1, nev_eleje)
        return talalat[0]

    def assertRendben(self, nev_eleje: str, allapot: str | None = None):
        r = self.r(nev_eleje)
        self.assertFalse(r.get("kihagyva"), r)
        self.assertTrue(r["rendben"], r)
        if allapot:
            self.assertEqual(r["allapot"], allapot, r)

    def test_rendes_szamitas_fut(self):
        self.assertRendben("rendes SymPy", "ok")

    def test_fajl_olvasas_es_listazas_tiltott(self):
        self.assertRendben("fájl olvasása", "tiltott")
        self.assertRendben("a vault listázása", "tiltott")
        self.assertRendben("a home listázása", "tiltott")

    def test_fajl_iras_tiltott_es_nem_jon_letre(self):
        self.assertRendben("fájl írása", "tiltott")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_halozat_tiltott(self):
        self.assertRendben("hálózat (TCP)", "tiltott")
        self.assertRendben("hálózat (DNS)")

    def test_exec_fork_jel_tiltott(self):
        self.assertRendben("program indítása")
        self.assertRendben("fork", "tiltott")
        self.assertRendben("jel más folyamatnak", "tiltott")

    def test_tiltott_import_nev_attributum(self):
        self.assertRendben("tiltott import", "tiltott")
        self.assertRendben("tiltott név", "tiltott")
        self.assertRendben("tiltott attribútum", "tiltott")

    def test_vegtelen_ciklus_puha_es_kemeny_korlat(self):
        self.assertRendben("végtelen ciklus", "idotullepes")
        self.assertRendben("C-szintű végtelen", "idotullepes")

    def test_memoria_korlat_a_szulo_rss_figyelesevel(self):
        r = self.r("memória")
        self.assertTrue(r["rendben"], r)
        self.assertEqual(r["allapot"], "memoria")
        self.assertGreater(r["csucs_mb"], 300)

    def test_kimenet_aradat_es_utana_uj_gyermek(self):
        self.assertRendben("kimenet-áradat")
        self.assertRendben("a leállítás után", "ok")

    def test_a_modulok_mas_resze_sem_olvashato(self):
        """A profil csak a homokozó, a matek és a kozos kódját engedi, a többi modul (pl. az arany-adatok) nem."""
        e = self.hk.egy({"muvelet": "kod", "kod": proba._kitores(
            f"__import__('builtins').open({str(MODULOK / 'eval' / 'matek' / 'arany.json')!r}).read()")})
        self.assertEqual(e["allapot"], "tiltott", e)


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class ApiTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)

    def test_tobb_feladat_egy_gyermekben_es_az_eredmeny_json_alakja(self):
        hk = Homokozo(self.cfg)
        kodok = ["import sympy as sp\nx = sp.Symbol('x', real=True)\nEREDMENY = sp.solveset(x**2 - 2, x, sp.S.Reals)",
                 "import sympy as sp\nx = sp.Symbol('x', real=True)\nEREDMENY = sp.solveset(x**2 > 4, x, sp.S.Reals)",
                 "import sympy as sp\nx, y = sp.symbols('x y')\nEREDMENY = sp.solve([x + y - 3, x - y - 1], [x, y])",
                 "import sympy as sp\nEREDMENY = sp.Rational(1, 3) + sp.sqrt(2)",
                 "print('szia')\nEREDMENY = 1",
                 "EREDMENY_NINCS = 1"]
        e = hk.futtat([{"muvelet": "kod", "kod": k} for k in kodok])
        self.assertEqual([x["allapot"] for x in e], ["ok"] * 5 + ["hiba"])
        self.assertEqual(e[0]["ertek"], {"tipus": "halmaz", "elemek": ["-sqrt(2)", "sqrt(2)"]})
        self.assertEqual(e[1]["ertek"]["tipus"], "intervallum")
        self.assertEqual(len(e[1]["ertek"]["darabok"]), 2)
        self.assertEqual(e[2]["ertek"], {"tipus": "par", "ertekek": {"x": "2", "y": "1"}})
        self.assertEqual(e[3]["ertek"], {"tipus": "kifejezes", "ertek": "1/3 + sqrt(2)"})
        self.assertEqual(e[4]["kimenet"], "szia\n")
        self.assertIn("EREDMENY", e[5]["uzenet"])

    def test_hivas_csak_a_regiszterbol(self):
        hk = Homokozo(self.cfg)
        e = hk.futtat([{"muvelet": "hivas", "nev": "os.system", "args": {"command": "ls"}},
                       {"muvelet": "hivas", "nev": "homokozo.alvas", "args": {"mp": 0}},
                       {"muvelet": "mas"}])
        self.assertEqual([x["allapot"] for x in e], ["tiltott", "ok", "tiltott"])

    def test_hianyzo_sandbox_exec_zarva_hibazik(self):
        hk = Homokozo(self.cfg, sandbox_exec=str(Path(self._t.name) / "nincs-ilyen"))
        e = hk.futtat([{"muvelet": "kod", "kod": "EREDMENY = 1"}] * 2)
        self.assertEqual([x["allapot"] for x in e], ["homokozo_hiba"] * 2)
        self.assertIn("elzáratlan futtatás nincs", e[0]["uzenet"])
        self.assertFalse(hk.elerheto()[0])

    def test_hibas_profil_eseten_sem_fut_csupaszon(self):
        hk = Homokozo(self.cfg, sandbox_exec=shutil.which("false") or "/usr/bin/false")
        e = hk.egy({"muvelet": "kod", "kod": "EREDMENY = 1"})
        self.assertEqual(e["allapot"], "homokozo_hiba")

    def test_a_beallitas_a_configbol_jon(self):
        self.cfg.data["homokozo"] = {**self.cfg.section("homokozo"), "memoria_mb": 123}
        self.assertEqual(Homokozo(self.cfg).beall["memoria_mb"], 123)
        self.assertEqual(Homokozo(self.cfg, memoria_mb=55).beall["memoria_mb"], 55)


class KodSzuroTest(unittest.TestCase):
    """A Python-szintű első védvonal (a homokozó nélkül, folyamaton belül)."""

    def test_tiltott_szerkezetek(self):
        for k in ("import os", "from os import path", "import sympy.utilities._compilation", "x = ().__class__",
                  "__import__('os')", "eval('1')", "open('/etc/passwd')", "getattr(1, 'real')", "class A: pass",
                  "import sympy as sp\nsp.simplify = None", "def _f(): pass", "from sympy import *",
                  "f = lambda _x: _x", "x" * (kod.MAX_KOD + 1)):
            with self.assertRaises(kod.Tiltott, msg=k):
                kod.ellenoriz(k)

    def test_engedett_kod_fut(self):
        ertek, kimenet = kod.futtat("import sympy as sp\nfrom fractions import Fraction\nimport math\n"
                                    "x = sp.Symbol('x')\nprint(math.floor(2.5))\nEREDMENY = sp.factor(x**2 - 1)")
        self.assertEqual(kod.szerializal(ertek), {"tipus": "kifejezes", "ertek": "(x - 1)*(x + 1)"})
        self.assertEqual(kimenet, "2\n")

    def test_szerializalas(self):
        import sympy as sp
        x = sp.Symbol("x", real=True)
        self.assertEqual(kod.szerializal(sp.S.EmptySet), {"tipus": "halmaz", "elemek": []})
        self.assertEqual(kod.szerializal([1, 2]), {"tipus": "halmaz", "elemek": ["1", "2"]})
        self.assertEqual(kod.szerializal(x > 2)["tipus"], "intervallum")
        self.assertEqual(kod.szerializal(sp.true), {"tipus": "logikai", "ertek": True})
        self.assertEqual(kod.szerializal(sp.ImageSet(sp.Lambda(x, 2 * sp.pi * x), sp.S.Integers))["tipus"], "egyeb")


class IdozitoTest(unittest.TestCase):
    def test_beagyazott_korlat_es_a_kulso_visszaall(self):
        import signal
        import time
        with idozito.korlatozva(5):
            with self.assertRaises(idozito.Idotullepes):
                with idozito.korlatozva(0.1):
                    time.sleep(1)
            maradek, _ = signal.getitimer(signal.ITIMER_REAL)
            self.assertGreater(maradek, 3)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0)
