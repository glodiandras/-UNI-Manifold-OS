"""F10: the five AI modes with a language parameter (`modulok/kod/ai.py`, `ai_futas.py`) and the D9 gate.

- the decision: a calibrated model of the language's own key runs for real; without it only a **trial** (`proba: true`):
  the `[kod] proba_modell`, else the calibrated C++ (`kod`) model; nothing → `kod.nincs_kalibralt`. A real request the
  worker reports as a trial is refused. The worker request carries `feladat` (real) or `model` + `proba` (trial);
- C++ keeps the measured C36b prompt byte for byte;
- a full run with a fake model: the model's code is compiled and tested only in the real sandbox, the result is labelled.
No real model is loaded."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from core import config
from core import kod_nyelvek as KN
from modulok.cpp import ai as CA
from modulok.kod import ai
from modulok.kod.ai_futas import AIFutas, Hiba
from tests.helpers import alg_gyoker, tmpdir
from tests.kod_segedek import KodCfg

MACOS = sys.platform == "darwin" and os.access("/usr/bin/sandbox-exec", os.X_OK)
VALODI = config.load()
PY = KN.profil("python")

JEGYZET = """---
Tags:
---
# Sum
Read n, then n integers; print their sum.

```teszt One
--- bemenet
3
1 2 3
--- kimenet
6
```
```teszt Two
--- bemenet
2
5 5
--- kimenet
10
```
![[Megoldas.py]]
"""
HIBAS = "n = int(input())\nxs = list(map(int, input().split()))\nprint(sum(xs[1:n]))\n"
JO = "n = int(input())\nxs = list(map(int, input().split()))\nprint(sum(xs[:n]))\n"


class _Router(AIFutas):
    """The router answers from a table (no worker)."""
    TABLA: dict = {}

    def _valaszt(self, feladat):
        return self.TABLA.get(feladat)


def _futas(cfg, profil, tabla, **kw):
    f = _Router(cfg, profil, **kw)
    f.TABLA = tabla
    return f


class DontesTest(unittest.TestCase):
    def setUp(self):
        self.alap = config.load()

    def test_kalibralt_nyelv_elesben(self):
        d = _futas(self.alap, PY, {"kod_python": {"modell": "m_py", "indok": "a legjobb"}})._dontes()
        self.assertEqual((d["modell"], d["proba"], d["feladat"]), ("m_py", False, "kod_python"))

    def test_kalibralatlan_nyelv_proba_modellel(self):
        cfg = KodCfg(self.alap, {"proba_modell": "proba_m"})
        d = _futas(cfg, PY, {"kod": {"modell": "m_cpp"}})._dontes()
        self.assertEqual((d["modell"], d["proba"]), ("proba_m", True))

    def test_kalibralatlan_nyelv_a_cpp_modell_probakent(self):
        d = _futas(KodCfg(self.alap), KN.profil("java"), {"kod": {"modell": "m_cpp"}})._dontes()
        self.assertEqual((d["modell"], d["proba"], d["feladat"]), ("m_cpp", True, "kod_java"))

    def test_semmi_nincs_kalibralt_hiba(self):
        for nyelv in ("python", "cpp"):
            with self.subTest(nyelv=nyelv), self.assertRaises(Hiba) as cm:
                _futas(KodCfg(self.alap), KN.profil(nyelv), {})._dontes()
            self.assertEqual(cm.exception.kod, "kod.nincs_kalibralt")
            self.assertEqual(cm.exception.param["kulcs"], KN.profil(nyelv).kalibracios_kulcs)

    def test_cpp_kalibralatlanul_csak_proba(self):
        d = _futas(KodCfg(self.alap, {"proba_modell": "p"}), KN.profil("cpp"), {})._dontes()
        self.assertTrue(d["proba"])

    def _worker(self, dontes, esemenyek):
        kuldott = {}

        def folyam(u, body, timeout=0):
            kuldott.update(body)
            return (e for e in esemenyek)               # a generator (the engine closes it)
        m = mock.Mock()
        m.modell.return_value = object()
        with mock.patch("core.kereses_modell.chat_folyam", folyam), \
                mock.patch("core.modell.beallitas.betolt", return_value=m), \
                mock.patch("core.modell.eval.keres_beallitas", lambda b, mo, f, k: dict(k)):
            f = AIFutas(self.alap, PY, worker_url="http://127.0.0.1:1")
            szoveg, nev = f._worker_hiv({"messages": [], "max_tokens": 10}, dontes, lambda n: None)
        return szoveg, nev, kuldott

    def test_eles_keres_feladattal_proba_keres_modellel(self):
        _, _, body = self._worker({"modell": "m", "proba": False, "feladat": "kod_python"},
                                  [{"tipus": "token", "szoveg": "a"}, {"tipus": "vege", "modell": "m", "proba": False}])
        self.assertEqual(body["feladat"], "kod_python")
        self.assertNotIn("model", body)
        szoveg, _, body = self._worker({"modell": "p", "proba": True, "feladat": "kod_python"},
                                       [{"tipus": "token", "szoveg": "b"}, {"tipus": "vege", "modell": "p", "proba": True}])
        self.assertEqual((body["model"], body["proba"]), ("p", True))
        self.assertNotIn("feladat", body)
        self.assertEqual(szoveg, "b")

    def test_a_worker_proba_futasa_eles_kerest_nem_ad(self):
        with self.assertRaises(Hiba) as cm:
            self._worker({"modell": "m", "proba": False, "feladat": "kod_python"},
                         [{"tipus": "token", "szoveg": "x"}, {"tipus": "vege", "modell": "m", "proba": True}])
        self.assertEqual(cm.exception.kod, "kod.nincs_kalibralt")


class PromptTest(unittest.TestCase):
    def test_cpp_a_mert_prompt_valtozatlan(self):
        for mod in KN.AI_MODOK:
            self.assertEqual(ai.prompt(KN.profil("cpp"), mod, "F", "int main(){}", None), CA.prompt(mod, "F", "int main(){}", None))
            self.assertEqual(ai.keres(KN.profil("cpp"), mod, "F", "x"), CA.keres(mod, "F", "x"))

    def test_nyelvi_prompt_nevezi_a_nyelvet_es_keritest(self):
        for nyelv in ("python", "javascript", "typescript", "java", "go", "rust", "swift", "c"):
            p = KN.profil(nyelv)
            s = ai.prompt(p, "megoldas", "Task", "x = 1", None)
            self.assertIn(p.ai_nyelv, s)
            self.assertIn("```" + p.kerites[0], s)
            self.assertNotIn("C++17", s)

    def test_valasz_elemzes(self):
        self.assertEqual(ai.hiba_valasz(PY, "The slice starts at 1.\nERROR: 3 index")["sor"], 3)
        self.assertEqual(ai.hiba_valasz(PY, "x\nERROR: 2 valami")["fajta"], "egyeb")
        t = ai.tipp_valasz(PY, "1. DIRECTION: look at the sum\n2. ALGORITHM: add all\n3. LOCATION: line 3 skips the first")
        self.assertEqual((t["sorrend_ok"], t["hely_sor"]), (True, 3))
        m = ai.megoldas_valasz(PY, "Fixed.\n```python\nprint(1)\n```\n")
        self.assertEqual(m["kod"], "print(1)\n")
        v = ai.teszt_valasz(PY, "```input\n1\n7\n```\n```input\n0\n\n```\n```python\nn=int(input())\nprint(n)\n```\n")
        self.assertEqual(len(v["bemenetek"]), 2)
        self.assertIn("print(n)", v["referencia"])
        s = ai.stressz_valasz(PY, "```python generator\nimport sys\n```\n```python reference\nprint(0)\n```\n")
        self.assertIn("sys", s["generator"])
        self.assertIn("print(0)", s["referencia"])


@unittest.skipUnless(MACOS, "[indokolt] nincs sandbox-exec (csak macOS)")
class AIFutasTest(unittest.TestCase):
    """A full request with a fake model: the code runs only in the real sandbox; the result is labelled."""

    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.t = Path(os.path.realpath(cls._t.name))
        root = alg_gyoker(str(cls.t)).resolve()
        cls.cfg = KodCfg(config.load({"MOS_ROOT": str(root), "HOME": str(cls.t / "home"),
                                      "MOS_RUNTIME": str(VALODI.path("runtime"))}))
        (cls.t / "Feladat.md").write_text(JEGYZET, encoding="utf-8")
        (cls.t / "Megoldas.py").write_text(HIBAS, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def fut(self, mod, valasz, proba=True, **kw):
        esem = []
        dontes = {"modell": "m", "proba": proba, "feladat": "kod_python", "indok": "teszt"}
        promptok = []

        def hivo(keres, d, jelzes):
            promptok.append(keres["messages"][0]["content"])
            return valasz, d["modell"]
        f = AIFutas(self.cfg, PY, esemeny=esem.append, dontes=lambda: dontes, modell_hivo=hivo)
        r = f.fut(mod, self.t / "Megoldas.py", self.t / "Feladat.md", **kw)
        return r, esem, promptok

    @staticmethod
    def egy(esem, nev):
        return [e for e in esem if e["szakasz"] == nev]

    def test_megoldas_ellenorizve_homokozoban_proba_jelolessel(self):
        r, esem, promptok = self.fut("megoldas", f"Use the whole list.\n```python\n{JO}```\n", megerosit=True)
        self.assertTrue(r["ok"], esem)
        self.assertTrue(r["proba"])
        e = self.egy(esem, "eredmeny")[0]
        self.assertTrue(e["proba"])
        self.assertTrue(e["ellenorzott"])
        self.assertEqual((e["atment_db"], e["ossz"]), (2, 2))
        self.assertEqual(self.egy(esem, "modell")[0]["kalibracios_kulcs"], "kod_python")
        self.assertIn("Python 3", promptok[0])
        self.assertIn("wrong output", promptok[0])                       # the evidence of the failing test
        self.assertNotIn("![[Megoldas.py]]", promptok[0])                  # the embedding is not sent
        self.assertEqual((self.t / "Megoldas.py").read_text(), HIBAS)       # the engine never writes the source

    def test_hibas_javaslat_nem_ellenorzott(self):
        r, esem, _ = self.fut("megoldas", "```python\nprint(0)\n```\n", megerosit=True, proba=False)
        e = self.egy(esem, "eredmeny")[0]
        self.assertFalse(e["ellenorzott"])
        self.assertFalse(e["proba"])

    def test_megoldas_megerosites_nelkul(self):
        r, esem, promptok = self.fut("megoldas", "x")
        self.assertEqual(r["kod"], "kod.megerosites_kell")
        self.assertEqual(promptok, [])

    def test_hiba_mod_sorral(self):
        r, esem, _ = self.fut("hiba", "The slice skips the first number.\nERROR: 3 index")
        e = self.egy(esem, "eredmeny")[0]
        self.assertEqual((e["sor"], e["fajta"]), (3, "index"))
        self.assertEqual(self.egy(esem, "ellenorzes")[0]["atment_db"], 0)

    def test_teszt_mod_ellenorzott_referenciaval(self):
        valasz = f"```input\n1\n9\n```\n```input\n3\n1 1 1\n```\n```python\n{JO}```\n"
        r, esem, _ = self.fut("teszt", valasz)
        e = self.egy(esem, "eredmeny")[0]
        self.assertTrue(e["ellenorzott"])
        self.assertEqual([x["vart"] for x in e["esetek"]], ["9\n", "3\n"])
        self.assertEqual([x["allapot"] for x in e["esetek"]], ["elteres", "elteres"])
        self.assertIn("```teszt", e["esetek"][0]["blokk"])

    def test_stressz_ellenpelda(self):
        gen = "import random, sys\nr = random.Random(int(sys.argv[1]))\nn = r.randint(1, 4)\nprint(n)\nprint(*[r.randint(1, 9) for _ in range(n)])\n"
        r, esem, _ = self.fut("stressz", f"```python generator\n{gen}```\n```python reference\n{JO}```\n")
        e = self.egy(esem, "eredmeny")[0]
        self.assertIsNotNone(e["ellenpelda"], e)
        self.assertTrue(e["ellenorzott"])


if __name__ == "__main__":
    unittest.main()
