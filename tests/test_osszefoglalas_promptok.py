"""C26b: a kalibrált és az éles összefoglaló-prompt egyetlen szövegforrása (`modulok/osszefoglalas/promptok.py`): a C18 `szoveg`
aranyhalmaz összefoglaló-tételének promptja bájtra azonos a C19 kalibrációja idején mérttel (az ujjlenyomat nem változhat)."""
import hashlib
import unittest

from modulok.eval.szoveg import feladat as SZ
from modulok.osszefoglalas import promptok as P


class PromptTest(unittest.TestCase):
    # a refaktor (C26b) előtt a `feladat.PROMPT_OSSZ.format(szoveg=…)` sha1-je erre a mintára
    REGI_SHA1 = "93c30d8e8a4e55431bcd336c092aae14bee2df22"

    def test_az_eval_prompt_bajtra_a_kalibralt(self):
        p = SZ.prompt_ossz("PÉLDA SZÖVEG\nmásodik sor")
        self.assertEqual(hashlib.sha1(p.encode()).hexdigest(), self.REGI_SHA1)
        self.assertEqual(p, P.jegyzet_prompt("PÉLDA SZÖVEG\nmásodik sor"))

    def test_a_tetelek_a_kozos_promptot_hasznaljak(self):
        t = next(x for x in SZ.tetelek(None) if x["id"] == "ossz-j01")
        szoveg = SZ.forras_szoveg("j01")
        self.assertEqual(t["keres"]["messages"][0]["content"], P.jegyzet_prompt(szoveg))

    def test_darab_prompt_ugyanaz_a_szabaly_a_darabra_szabva(self):
        d = P.darab_prompt(4, "Caesar", "[Fejezet]\nSzöveg.")
        j = P.jegyzet_prompt("[Fejezet]\nSzöveg.")
        # a két prompt csak a tárgyban (jegyzet / jegyzetrészlet), az állítások számában és a fejlécben tér el
        for szabaly in ("SZÓ SZERINTI idézetet", "legfeljebb 40 szó", "Csak azt állítsd, ami a jegyzetben áll.",
                        '[{"allitas": "…", "idezet": "…"}]'):
            self.assertIn(szabaly, d)
            self.assertIn(szabaly, j)
        self.assertIn("jegyzetrészletet magyarul, 4 állításban", d)
        self.assertIn("JEGYZET (Caesar):\n[Fejezet]", d)
        self.assertTrue(d.endswith("Szöveg."))

    def test_prompt_verzio_van(self):
        self.assertRegex(P.PROMPT_VERZIO, r"^ossz-\d+$")


if __name__ == "__main__":
    unittest.main()
