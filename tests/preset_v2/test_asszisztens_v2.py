"""Az Asszisztens beállításai a `v2-kompat` presettel: a fejlesztő saját, a termék által már nem szállított értékei
(`[asszisztens] tantargy_nevek`, a `*_kizart` útelőtagok). A termék semleges alapja: `tests/test_alapertekek_semleges.py`."""
import unittest

from core import kiserok
from core.asszisztens.beallitasok import beallitasok
from tests.preset_v2 import V2_ELOTAG, v2_cfg

V2_KIZART = ["X01 - Napló & To-Do/", "AI02 - Log/", "_Template/", V2_ELOTAG]


class AsszisztensV2(unittest.TestCase):
    def test_a_tantargy_nevek_a_presetbol(self):
        self.assertEqual(beallitasok(v2_cfg())["tantargy_nevek"],
                         {"History": "történelem", "Literature": "irodalom", "Mathematics": "matematika", "Physics": "fizika",
                          "Informatics": "informatika", "Grammar": "nyelvtan", "English": "angol"})

    def test_a_kizart_utelotagok_a_presetbol(self):
        b = beallitasok(v2_cfg())
        for k in ("higienia_arva_kizart", "emlites_kizart", "kartya_kizart"):
            self.assertEqual(b[k], V2_KIZART, k)
        self.assertEqual(kiserok.kisero_elotag(v2_cfg()), V2_ELOTAG)


if __name__ == "__main__":
    unittest.main()
