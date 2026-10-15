"""Perf-készlet (T008, 2. audit): a Bases teljesítménye (C12) — 2000 szintetikus jegyzeten a melegen futó `lekerdez` <
300 ms (cél: ≤ 80 ms); falióra-kapu. NEM része az alap készletnek (nem `test*.py`): `bin/mos perf`, tétlen gépen. A
funkcionális megfelelője: `tests/test_bazis_teljesitmeny.py` (helyesség és arány); a valódi vaulton a
`tests/kezi/bazis_meres.py` mér."""
import time
import unittest

from core.bazis.api import Bazisok
from tests.bazis_teljesitmeny_segedek import NAGY_BAZIS, szintetikus
from tests.helpers import alg_core, tmpdir
from tests.index_segedek import index_indit

KORLAT_MS = 300
CEL_MS = 80


class BazisPerf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cfg, _, v = alg_core(cls._t.name)
        szintetikus(v, 2000)
        cls.ix, _ = index_indit(cfg)
        cls.b = Bazisok(cfg, cls.ix)

    @classmethod
    def tearDownClass(cls):
        cls.ix.leallit()
        cls._t.cleanup()

    def lekerdez(self, szoveg=NAGY_BAZIS):
        t0 = time.perf_counter()
        v = self.b.lekerdez({"szoveg": szoveg})
        return v, (time.perf_counter() - t0) * 1000

    def test_meleg_lekerdezes_a_korlat_alatt(self):
        self.lekerdez()                                              # hideg: a `Tabla` építése
        ido = sorted(self.lekerdez()[1] for _ in range(5))
        v, _ = self.lekerdez()
        self.assertEqual(v["hibak"], [])
        self.assertGreater(len(v["sorok"]), 1500)
        self.assertLess(ido[2], KORLAT_MS, f"a medián {ido[2]:.0f} ms (cél: ≤ {CEL_MS} ms) — {ido}")
        self.assertLess(v["ido_ms"], KORLAT_MS)

    def test_hideg_lekerdezes_is_gyors(self):
        from core.bazis.adat import Tar
        self.b.tar = Tar(self.ix)
        v, ido = self.lekerdez()
        self.assertLess(ido, 1500, f"hideg: {ido:.0f} ms")

    def test_egyszeru_nezet_gyors(self):
        self.lekerdez()
        _, ido = self.lekerdez("views:\n  - type: table\n    order: [file.name, Status]\n")
        self.assertLess(ido, KORLAT_MS)

    def test_a_visszalinkek_terkepe_csak_kerésre_epul(self):
        self.lekerdez()
        self.assertIsNone(self.b.tar.tabla()._visszalinkek)
        v, ido = self.lekerdez("views:\n  - type: table\n    order: [file.name, file.backlinks]\n"
                               "    filters: file.ext == \"md\"\n    limit: 50\n")
        self.assertIsNotNone(self.b.tar.tabla()._visszalinkek)
        self.assertLess(ido, KORLAT_MS)
        self.assertEqual(len(v["sorok"]), 50)


if __name__ == "__main__":
    unittest.main()
