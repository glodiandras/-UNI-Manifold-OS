"""F7 Developer nézet: mentett beállítás + az indító ⌥-kattintásának munkamenet-kényszere (a mentett érték nem változik)."""
import unittest
from unittest import mock

from core import fejleszto, termek_beallitasok as b
from core.utvonalak import HttpError
from tests.helpers import REPO, tmpdir
from tests.multi_user import munkater, termek_cfg, termek_telepites


class FejlesztoModTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.v, _ = munkater(self.t.name, "Synthetic notes")
        self.cfg = termek_cfg(self.root, self.home, self.v)

    def test_alapbol_ki_es_a_beallitas_mentheto(self):
        v = b.olvas(self.cfg)
        self.assertFalse(v["ertek"]["fejleszto"]["mod"])
        self.assertNotIn("fejleszto_kenyszer", v)
        uj = b.ir(self.cfg, v["rev"], {"fejleszto": {"mod": True}})
        self.assertTrue(uj["ertek"]["fejleszto"]["mod"])
        ujra = termek_cfg(self.root, self.home, self.v)
        self.assertTrue(b.olvas(ujra)["ertek"]["fejleszto"]["mod"])                   # új folyamat is látja
        b.ir(ujra, b.olvas(ujra)["rev"], {"fejleszto": {"mod": False}})
        self.assertFalse(b.olvas(termek_cfg(self.root, self.home, self.v))["ertek"]["fejleszto"]["mod"])

    def test_nem_logikai_ertek_es_ismeretlen_kulcs_elutasitott(self):
        rev = b.olvas(self.cfg)["rev"]
        for rossz in ({"fejleszto": {"mod": "igen"}}, {"fejleszto": {"mod": 1}}, {"fejleszto": {"masik": True}}, {"fejleszto": True}):
            with self.subTest(rossz=rossz), self.assertRaises(HttpError) as e:
                b.ir(self.cfg, rev, rossz)
            self.assertEqual(e.exception.code, 400)

    def test_az_indito_kenyszere_a_munkamenetre_be_a_mentett_erteket_nem_irja_at(self):
        with mock.patch.dict("os.environ", {fejleszto.NEZET_ENV: "1"}):
            v = b.olvas(self.cfg)
            self.assertTrue(v["ertek"]["fejleszto"]["mod"])
            self.assertTrue(v["fejleszto_kenyszer"])
            b.ir(self.cfg, v["rev"], {"megjelenes": {"csend": True}})                     # más mentése nem rögzíti a kényszert
        ujra = b.olvas(termek_cfg(self.root, self.home, self.v))
        self.assertFalse(ujra["ertek"]["fejleszto"]["mod"])
        self.assertTrue(ujra["ertek"]["megjelenes"]["csend"])

    def test_kenyszer_csak_pontosan_1_ertekre(self):
        for ertek in ("0", "", "true", "yes"):
            self.assertFalse(fejleszto.nezet_kenyszer({fejleszto.NEZET_ENV: ertek}))
        self.assertTrue(fejleszto.nezet_kenyszer({fejleszto.NEZET_ENV: "1"}))
        self.assertFalse(fejleszto.nezet_kenyszer({}))

    def test_az_indito_option_kattintasa_pontosan_ezt_a_kornyezeti_valtozot_allitja(self):
        """Swift-oldali szerződés (forrás-olvasás: a natív indító fordítása külön teszt): ⌥ lenyomva → setenv a core indítása előtt."""
        forras = (REPO / "shell" / "Sources" / "InditoAblak.swift").read_text(encoding="utf-8")
        self.assertIn(f'setenv("{fejleszto.NEZET_ENV}", "1", 1)', forras)
        self.assertIn("NSEvent.modifierFlags.contains(.option)", forras)
        self.assertLess(forras.index("setenv(\"MOS_FEJLESZTOI_NEZET\""), forras.index("onMegnyit(vault)\n    }\n    private func optionJegyez"))
        magfolyamat = (REPO / "shell" / "Sources" / "CoreProcess.swift").read_text(encoding="utf-8")
        self.assertIn("var env = alap", magfolyamat)                                       # a core a héj környezetét örökli
        self.assertNotIn(fejleszto.NEZET_ENV, magfolyamat)                                 # a folyamat-környezet szűrése nem dobja el

    def test_a_teszt_horgok_kapcsoloja_fuggetlen_a_nezettol(self):
        self.assertFalse(fejleszto.kapcsolo("MOS_PROBA_FELADAT", {fejleszto.NEZET_ENV: "1", "MOS_PROBA_FELADAT": "1"}))


if __name__ == "__main__":
    unittest.main()
