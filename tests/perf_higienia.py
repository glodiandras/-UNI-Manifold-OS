"""A higiénia-riport mérése 3000 jegyzetes szintetikus vaulton (C30a; `bin/mos perf`, tétlen gépen).

A vault a `bazis_teljesitmeny_segedek.szintetikus` jegyzeteit kapja, plusz beültetett hibákat (törött link,
hibás képlet, hiányzó média, séma-sértés). Hideg hívás, majd 5 meleg; a medián a mérés."""
import statistics
import time
import unittest

from core import higienia
from core.tulajdonsagok import Tulajdonsagok
from tests.bazis_teljesitmeny_segedek import szintetikus
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit

KORLAT_MS = 1500
CEL_MS = 500
DB = 3000


class HigieniaPerf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cfg, _, v = alg_core(cls._t.name)
        szintetikus(v, DB)
        for i in range(0, DB, 10):          # beültetett hibák
            ir(v, f"Hibas/H{i}.md", f"---\nTags:\n  - Ismeretlen\n---\n[[Nincs {i}]] $\\frac{{a}}{{b$ ![[nincs{i}.png]]\n")
        cls.ix, _ = index_indit(cfg)
        cls.h = higienia.Higienia(cfg, cls.ix, Tulajdonsagok(cfg, cls.ix))

    @classmethod
    def tearDownClass(cls):
        cls.ix.leallit()
        cls._t.cleanup()

    def test_teljes_riport(self):
        t0 = time.perf_counter()
        r = self.h.riport()
        hideg = (time.perf_counter() - t0) * 1000
        ido = []
        for _ in range(5):
            t0 = time.perf_counter()
            self.h.riport()
            ido.append((time.perf_counter() - t0) * 1000)
        med = statistics.median(ido)
        print(f"\nhigienia: {r['jegyzetek']} jegyzet, {r['osszesites']['ossz']} tétel; hideg {hideg:.0f} ms, "
              f"meleg medián {med:.0f} ms (min {min(ido):.0f}, max {max(ido):.0f}); cél ≤ {CEL_MS} ms")
        self.assertGreaterEqual(r["osszesites"]["hibas_keplet"], DB // 10)
        self.assertLess(med, KORLAT_MS, f"a riport lassú: {med:.0f} ms, cél ≤ {CEL_MS} ms")


if __name__ == "__main__":
    unittest.main()
