"""A fejlesztő tantárgy-szótára a `v2-kompat` presettel (`[naptar.szotar.targyak]`, `csoportok`): az F3 előtt a `tests/test_naptar.py`
`SzabalyTest.test_tantargy_szohatar` / `test_esemeny_fajta` tesztjei a beépített szótárral, itt a presetből feloldva. A termék
szótára üres (`tests/test_alapertekek_semleges.py`)."""
import unittest

from core import naptar
from tests.preset_v2 import v2_cfg


class NaptarSzotarV2(unittest.TestCase):
    def setUp(self):
        self.t = naptar.targyak_cfg(v2_cfg())

    def test_a_preset_szotara(self):
        self.assertEqual(set(self.t["Matematika"]), {"matematika", "matek", "mat", "math", "maths"})
        self.assertEqual(self.t.csoportok, {"magyar": ["Irodalom", "Nyelvtan"]})
        self.assertEqual(len(self.t), 12)

    def test_tantargy_szohatar(self):
        self.assertEqual(naptar.targy("Matek röpdolgozat", self.t), ["Matematika"])         # a `ropdolgozat` a preset szava
        self.assertEqual(naptar.targy("Materiál beszerzés", self.t), [])                   # a „mat” nem a „materiál”-ban
        self.assertEqual(naptar.targy("Magyar", self.t), ["Irodalom", "Nyelvtan"])
        self.assertEqual(naptar.targy("Német - Röpdolgozat", self.t), ["Német"])

    def test_esemeny_fajta(self):
        sz = naptar.szotar(v2_cfg())
        self.assertEqual(naptar.esemeny_fajta("Német - Röpdolgozat", "hatarido", self.t, sz), "dolgozat")
        self.assertEqual(naptar.esemeny_fajta("Bánk bán beadandó", "hatarido", self.t, sz), "hatarido")
        self.assertIsNone(naptar.esemeny_fajta("Dolgozatra készülés", "tanulas", self.t, sz))
        self.assertEqual(naptar.esemeny_fajta("Matek", "hatarido", self.t, sz), "dolgozat")  # tantárgy, határidő-szó nélkül
        self.assertEqual(naptar.esemeny_fajta("Ropi", "hatarido", self.t, sz), "dolgozat")   # a preset számonkérés-szava


if __name__ == "__main__":
    unittest.main()
