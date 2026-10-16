"""F9: the test levels (`tests/szintek.py`, `bin/mos test --szint <name>`) stay complete and loadable.

Every module a level names exists and loads at least one test (a renamed test cannot silently drop out of a release gate); the
DoD table covers PLAN §12 points 1–15, each with at least one automated test; `bin/mos` routes `--szint` to the runner."""
import io
import unittest
from contextlib import redirect_stdout

from tests import szintek
from tests.helpers import REPO


class SzintekTest(unittest.TestCase):
    def test_minden_szint_betoltheto_es_nem_ures(self):
        for nev, modulok in szintek.SZINTEK.items():
            for m in modulok:
                with self.subTest(szint=nev, modul=m):
                    s = szintek.betolt_nev(m)
                    hibak = [t for t in _bejar(s) if type(t).__name__ in ("_FailedTest", "ModuleImportFailure")]
                    self.assertEqual(hibak, [], f"{m} does not import")
                    self.assertGreater(s.countTestCases(), 0, f"{m} has no tests")

    def test_a_kert_szintek_megvannak(self):
        self.assertTrue({"fresh-install", "multi-user", "migracio", "biztonsag", "mentes", "dod"} <= set(szintek.SZINTEK))

    def test_dod_minden_pontja_automatizalt_teszttel(self):
        self.assertEqual(sorted(szintek.DOD), list(range(1, 16)))
        for n, (cim, mods, _kezi) in szintek.DOD.items():
            self.assertTrue(cim and mods, n)
            self.assertTrue(set(mods) <= set(szintek.SZINTEK["dod"]), n)

    def test_bin_mos_szint_kapcsolo_es_lista(self):
        mos = (REPO / "bin" / "mos").read_text(encoding="utf-8")
        self.assertIn('= --szint ]; then shift; exec "$(python_kereses)" -B -m tests.szintek', mos)
        ki = io.StringIO()
        with redirect_stdout(ki):
            self.assertEqual(szintek.main(["lista"]), 0)
        for nev in szintek.SZINTEK:
            self.assertIn(f"{nev}:", ki.getvalue())
        self.assertEqual(szintek.main(["nincs-ilyen"]), 2)


def _bejar(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            yield from _bejar(t)
        else:
            yield t
