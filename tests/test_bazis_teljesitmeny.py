"""A Bases méretezése (C12) funkcionálisan: helyesség és ARÁNY — nem falióra (T008, 2. audit). 2000 szintetikus jegyzeten a
nagy nézet helyes, a gyorsítótár működik (a meleg lekérdezés a hideg alatt marad), és az egyszerű nézet nem lassabb a
nagynál. Az abszolút ms-kapuk (< 300 ms, hideg < 1500 ms) a perf-készletben vannak (`tests/perf_bazis.py`,
`bin/mos perf`): a falióra-kapu a funkcionális készletben terhelés alatt hamisan bukott (a K32 mérés közben 366 ms)."""
import statistics
import time
import unittest

from core.bazis.api import Bazisok
from tests.bazis_teljesitmeny_segedek import NAGY_BAZIS, szintetikus
from tests.helpers import alg_core, tmpdir
from tests.index_segedek import index_indit


class BazisMeretTest(unittest.TestCase):
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

    def test_az_adathalmaz_merete(self):
        self.assertGreaterEqual(self.ix.allapot()["fajlok"], 2000)

    def test_a_nagy_nezet_helyes(self):
        v, _ = self.lekerdez()
        self.assertEqual(v["hibak"], [])
        self.assertGreater(len(v["sorok"]), 1500)

    def test_a_meleg_lekerdezes_gyorsabb_a_hidegnel(self):
        """Arány: a hideg lekérdezés a `Tabla` építését is fizeti, a meleg nem — a gyorsítótár működik. A medián 5 meleg
        mérésből; a viszony független a gép pillanatnyi sebességétől."""
        from core.bazis.adat import Tar
        self.b.tar = Tar(self.ix)
        _, hideg = self.lekerdez()
        meleg = statistics.median(self.lekerdez()[1] for _ in range(5))
        self.assertLess(meleg, hideg, f"meleg (medián) {meleg:.0f} ms, hideg {hideg:.0f} ms")

    def test_az_egyszeru_nezet_nem_lassabb_a_nagynal(self):
        self.lekerdez()
        nagy = statistics.median(self.lekerdez()[1] for _ in range(5))
        egyszeru = statistics.median(
            self.lekerdez("views:\n  - type: table\n    order: [file.name, Status]\n")[1] for _ in range(5))
        self.assertLess(egyszeru, nagy * 2, f"egyszerű {egyszeru:.0f} ms, nagy {nagy:.0f} ms")

    def test_a_visszalinkek_terkepe_csak_kerésre_epul(self):
        self.lekerdez()
        self.assertIsNone(self.b.tar.tabla()._visszalinkek)
        v, _ = self.lekerdez("views:\n  - type: table\n    order: [file.name, file.backlinks]\n"
                             "    filters: file.ext == \"md\"\n    limit: 50\n")
        self.assertIsNotNone(self.b.tar.tabla()._visszalinkek)
        self.assertEqual(len(v["sorok"]), 50)


if __name__ == "__main__":
    unittest.main()
