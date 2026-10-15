"""A szigorú kihagyás-kapu (`MOS_SZIGORU=1`, T086 — 2. audit): a chatzáró és a kapufutásban a kihagyás bukás, kivéve az
`[indokolt]` előtagú okút (a gép adottsága), és a futás végén a kihagyott osztályok névsora kiíródik (a NAPLO-ba).
A kapu a `tests/__init__.py`-ban él; itt alfolyamatban, egy kis, beégetett készleten próbáljuk ki."""
import subprocess
import sys
import unittest

from tests.helpers import REPO, env

KOD = r"""
import sys, unittest
import tests                               # a kapu itt kapcsol be (MOS_SZIGORU=1 mellett)

class Rendben(unittest.TestCase):
    def test_fut(self):
        pass

    @unittest.skip("nincs lefordított app/dist")
    def test_indokolatlan(self):
        pass

class Gep(unittest.TestCase):
    def test_indokolt(self):
        self.skipTest("[indokolt] nincs APFS-klón ezen a köteten")

SZAMOK = {"mind": [Rendben, Gep], "csak_indokolt": [Gep], "tiszta": [Rendben]}[sys.argv[1]]
s = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in SZAMOK)
if sys.argv[1] == "tiszta":
    s = unittest.TestSuite([Rendben("test_fut")])
r = unittest.TextTestRunner(verbosity=0).run(s)
sys.exit(not r.wasSuccessful())
"""


class SzigoruTeszt(unittest.TestCase):
    def _fut(self, melyik: str, szigoru: bool) -> subprocess.CompletedProcess:
        e = env(PYTHONPATH=str(REPO), **({"MOS_SZIGORU": "1"} if szigoru else {}))
        return subprocess.run([sys.executable, "-B", "-c", KOD, melyik], capture_output=True, text=True, cwd=REPO, env=e,
                              timeout=60)

    def test_szigoru_modban_az_indokolatlan_kihagyas_bukas_es_kiirja_a_nevsort(self):
        p = self._fut("mind", szigoru=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("FAILED", p.stderr)
        self.assertIn("MOS_SZIGORU", p.stderr)
        self.assertRegex(p.stderr, r"indokolatlan.*Rendben\.test_indokolatlan")
        self.assertIn("nincs lefordított app/dist", p.stderr)
        self.assertRegex(p.stderr, r"indokolt.*Gep\.test_indokolt")

    def test_szigoru_modban_az_indokolt_kihagyas_nem_buktat(self):
        p = self._fut("csak_indokolt", szigoru=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("1 kihagyás, ebből 0 indokolatlan", p.stderr)

    def test_szigoru_mod_nelkul_a_kihagyas_nem_buktat_es_nincs_jelentes(self):
        p = self._fut("mind", szigoru=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("MOS_SZIGORU", p.stderr)

    def test_szigoru_modban_kihagyas_nelkul_zold(self):
        p = self._fut("tiszta", szigoru=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("0 kihagyás", p.stderr)


if __name__ == "__main__":
    unittest.main()
