"""Perf-készlet (T008, 2. audit): az index késleltetése — falióra-kapu. NEM része az alap készletnek (nem `test*.py`):
`bin/mos perf`, tétlen gépen. A funkcionális megfelelője: `tests/test_index_api.py::test_kulso_modositas_latszik`."""
import statistics
import time
import unittest

from tests.index_segedek import var_ra
from tests.test_index_api import IndexApiAlap


class IndexKesleltetesPerf(IndexApiAlap):
    def test_kulso_modositas_200_ms_alatt_latszik(self):
        idok = []
        for i in range(10):
            szo = f"zebra{i}kulso"
            t0 = time.perf_counter()
            (self.v / "Cél X.md").write_text(f"# Cél X\n{szo}\n")
            self.assertTrue(var_ra(lambda: self.get("/api/vault/kereses", q=szo)[1].get("osszes") == 1, 5, 0.005))
            idok.append((time.perf_counter() - t0) * 1000)
        self.assertLess(max(idok), 200, f"medián {statistics.median(idok):.0f} ms, max {max(idok):.0f} ms")


if __name__ == "__main__":
    unittest.main()
