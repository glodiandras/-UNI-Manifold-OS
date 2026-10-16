"""A tantárgy-betűk nevei a `v2-kompat` presetből (`[pdf.nevek]` + `[pdf.tags]`): az F3 előtt a kódban élő `fuzet.modszer.TANTARGYAK` /
`fuzet.katalogus.TANTARGYAK` és a `ytdlp.integralas.TARGY_TERKEP` ikerlisták, amelyeket a termék már nem szállít (üres `[pdf.nevek]`)."""
import unittest

from modulok.fuzet import katalogus, modszer
from modulok.ytdlp import integralas
from tests.preset_v2 import v2_cfg

# az F2 `integralas.TARGY_TERKEP` értékei (a preset `[pdf.nevek]`-je ezek fölé a „Magyar nyelvtan” és az „Angol nyelv” nevet is adja)
F2_TARGY_TERKEP = {"Történelem": "T", "Irodalom": "I", "Magyar nyelv": "N", "Nyelvtan": "N", "Matematika": "M", "Fizika": "F",
                   "Digitális kultúra": "D", "Angol": "E"}
# az F2 `fuzet.modszer.TANTARGYAK` (betű → a kanonikus név, a `[pdf.nevek]` első eleme)
F2_TANTARGYAK = {"M": "Matematika", "F": "Fizika", "T": "Történelem", "I": "Irodalom", "N": "Magyar nyelvtan",
                 "D": "Digitális kultúra", "E": "Angol nyelv"}


class NevekV2(unittest.TestCase):
    def setUp(self):
        self.nevek = dict(v2_cfg().section("pdf").get("nevek") or {})
        self.cimkek = dict(v2_cfg().section("pdf").get("tags") or {})

    def test_a_kanonikus_nevek_az_f2_listaval_egyeznek(self):
        self.assertEqual({b: l[0] for b, l in self.nevek.items()}, F2_TANTARGYAK)

    def test_a_videoforras_targy_terkepe_az_f2_terkep_felett(self):
        terkep = integralas.targy_terkep(self.cimkek, self.nevek)
        for nev, betu in F2_TARGY_TERKEP.items():
            self.assertEqual(terkep.get(nev), betu, nev)
        self.assertEqual(integralas.targy_betu({"targy": "Digitális kultúra"}, self.cimkek, self.nevek), "D")
        self.assertEqual(integralas.targy_betu({"targy": "Mathematics"}, self.cimkek, self.nevek), "M")      # a `[pdf.tags]` címkéje is
        self.assertIsNone(integralas.targy_betu({"targy": "Kémia"}, self.cimkek, self.nevek))

    def test_a_fuzetlanc_a_modell_valaszabol_ismeri_fel_a_betut(self):
        for valasz, betu in (("Magyar nyelvtan", "N"), ("matematika", "M"), ("Történelem 8.", "T"), ("angol nyelv", "E"),
                             ("Digitális kultúra", "D")):
            self.assertEqual(modszer.targy_betu(valasz, self.cimkek, self.nevek), betu, valasz)
        self.assertIsNone(modszer.targy_betu("Kémia", self.cimkek, self.nevek))
        self.assertTrue(modszer.ismert_targy({"fejezetek": [], "tantargy": "Fizika"}, self.cimkek, self.nevek))
        self.assertFalse(modszer.ismert_targy({"fejezetek": [], "tantargy": "Kémia"}, self.cimkek, self.nevek))

    def test_a_katalogus_tantargy_nevei(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="mos-teszt-") as d:
            (Path(d) / "M01 - Algebra" / "Elmélet").mkdir(parents=True)
            (Path(d) / "M01 - Algebra" / "Elmélet" / "01 - Függvények.md").write_text("# Függvények\n", encoding="utf-8")
            kat = katalogus.Katalogus.vaultbol(d, cimkek=self.cimkek, nevek=self.nevek)
        self.assertEqual(kat.nevek, self.nevek)
        self.assertTrue(kat.fejezetek)                                           # az `M` betű a névlistából fejezetet ad


if __name__ == "__main__":
    unittest.main()
