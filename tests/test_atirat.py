"""C16: a médiafájl átirata — a VTT-elemző, a melléklet-mappa keresése (L44, PB07) és a `/api/media/atirat`."""
import unittest
import unicodedata

from core import atirat, vaultio
from tests.helpers import alg_core, ir, tmpdir

GEPI = "WEBVTT\n\nNOTE manifold-asr\nmotor: faster-whisper\n\n1\n00:00:01.000 --> 00:00:18.000\nMi jut eszedbe?\n\n" \
       "2\n00:00:18.000 --> 00:00:22.000\nElőször az égtáj.\n"


class ElemzoTest(unittest.TestCase):
    def test_idoformak(self):
        self.assertEqual(atirat.ido("00:00:01.000"), 1.0)
        self.assertEqual(atirat.ido("01:02:03.5"), 3723.5)
        self.assertEqual(atirat.ido("12:40.250"), 760.25)
        self.assertEqual(atirat.ido("00:01,5"), 1.5)                  # SRT-szerű vessző
        for rossz in ("", "1:2", "00:61.000", "00:00:61.000", "abc", "00:00:01"):
            self.assertIsNone(atirat.ido(rossz), rossz)

    def test_cuek(self):
        szoveg = ("﻿WEBVTT - fejléc\r\n\r\nSTYLE\r\n::cue { color: red }\r\n\r\nNOTE egy\r\nmegjegyzés\r\n\r\n"
                  "a\r\n00:00:05.000 --> 00:00:07.500 align:start position:10%\r\n<v Tanár>Első <c.sarga>sor</c>\r\n"
                  "második &amp; sor\r\n\r\n00:00:01.000 --> 00:00:02.000\r\nKorábbi\r\n\r\n"
                  "00:00:09.000 --> 00:00:08.000\r\nfordított idő\r\n\r\n00:00:10.000 --> 00:00:11.000\r\n\r\n"
                  "hibás --> sor\r\nszöveg\r\n")
        self.assertEqual(atirat.elemez(szoveg), [
            {"k": 1.0, "v": 2.0, "szoveg": "Korábbi"},
            {"k": 5.0, "v": 7.5, "szoveg": "Első sor második & sor"},
        ])

    def test_ures(self):
        self.assertEqual(atirat.elemez(""), [])
        self.assertEqual(atirat.elemez("WEBVTT\n"), [])


class MellekletTest(unittest.TestCase):
    VIDEO = "ATTCHMNTS - Videos/A Nyugat.mp4"

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.V = vaultio.Vault(self.cfg, publish=lambda e, **k: None)
        ir(self.v, self.VIDEO, b"\x00" * 16, "wb")

    def test_videomappa_a_teruleti_retegbol(self):
        ir(self.v, "A01 - Más/Média/Más.md", "# más\n")
        ir(self.v, "I23 - A Nyugat/Média/A Nyugat.md", "# A Nyugat\n")
        ir(self.v, "I23 - A Nyugat/Média/A Nyugat.en.vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nWest\n")
        ir(self.v, "I23 - A Nyugat/Média/A Nyugat.hu.vtt", GEPI)
        d = atirat.atirat(self.V, self.VIDEO)
        self.assertEqual((d["vtt"], d["nyelv"], d["gepi"], d["leiro"]),
                         ("I23 - A Nyugat/Média/A Nyugat.hu.vtt", "hu", True, "I23 - A Nyugat/Média/A Nyugat.md"))
        self.assertEqual([c["szoveg"] for c in d["cuek"]], ["Mi jut eszedbe?", "Először az égtáj."])
        self.assertIsNone(d["figyelmeztetes"])

    def test_kiadoi_felirat_es_info_json_jelolo(self):
        ir(self.v, "T07 - Árpád-kor/Média/A Nyugat.info.json", "{}")
        ir(self.v, "T07 - Árpád-kor/Média/A Nyugat.vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nKiadói\n")
        d = atirat.atirat(self.V, self.VIDEO)
        self.assertEqual((d["vtt"], d["nyelv"], d["gepi"], d["leiro"]),
                         ("T07 - Árpád-kor/Média/A Nyugat.vtt", None, False, None))

    def test_nfd_nevek(self):
        nfd = lambda s: unicodedata.normalize("NFD", s)
        ir(self.v, nfd("T07 - Árpád-kor/Média/A Nyugat.md"), "# x\n")
        ir(self.v, nfd("T07 - Árpád-kor/Média/A Nyugat.hu.vtt"), GEPI)
        d = atirat.atirat(self.V, self.VIDEO)
        self.assertEqual(d["vtt"], "T07 - Árpád-kor/Média/A Nyugat.hu.vtt")
        self.assertEqual(len(d["cuek"]), 2)

    def test_nincs_melleklet(self):
        d = atirat.atirat(self.V, self.VIDEO)
        self.assertEqual((d["vtt"], d["cuek"], d["leiro"]), (None, [], None))

    def test_sajat_mappa_a_videomappan_kivul(self):
        ir(self.v, "Xn - Forrás/Felvétel.m4a", b"\x00", "wb")
        ir(self.v, "Xn - Forrás/Felvétel.vtt", "WEBVTT\n\n00:01.000 --> 00:02.000\nhang\n")
        ir(self.v, "Más/Média/Felvétel.md", "# idegen\n")          # a saját mappa nyer, nem a réteg
        d = atirat.atirat(self.V, "Xn - Forrás/Felvétel.m4a")
        self.assertEqual((d["vtt"], d["leiro"], d["cuek"][0]["szoveg"]), ("Xn - Forrás/Felvétel.vtt", None, "hang"))

    def test_rossz_ut(self):
        with self.assertRaises(vaultio.Invalid):
            atirat.atirat(self.V, "Jegyzet.md")
        with self.assertRaises(vaultio.NotFound):
            atirat.atirat(self.V, "ATTCHMNTS - Videos/Nincs.mp4")
        with self.assertRaises(vaultio.Invalid):
            atirat.atirat(self.V, "../kint.mp4")

    def test_vaulton_kivulre_mutato_symlink_felirat_nem_olvashato(self):
        """T098: az átirat a `.vtt` symlinket ellenőrzés nélkül olvasta — egy vaultba tett symlink a felhasználó bármely
        olvasható fájlját (`KIVULI-VTT-TITOK`) az átiratba vitte."""
        import os
        kint = self.v.parent / "kivuli.vtt"
        kint.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nKIVULI-VTT-TITOK\n", encoding="utf-8")
        ir(self.v, "I23 - A Nyugat/Média/A Nyugat.md", "# A Nyugat\n")
        os.symlink(kint, self.v / "I23 - A Nyugat/Média/A Nyugat.hu.vtt")
        d = atirat.atirat(self.V, self.VIDEO)
        self.assertEqual(d["cuek"], [])
        self.assertIn("symlink", d["figyelmeztetes"])
        self.assertNotIn("TITOK", str(d))

    def test_vaulton_beluli_symlink_felirat_olvashato(self):
        import os
        ir(self.v, "I23 - A Nyugat/Média/A Nyugat.md", "# A Nyugat\n")
        ir(self.v, "I23 - A Nyugat/Média/eredeti.vtt", GEPI)
        os.symlink(self.v / "I23 - A Nyugat/Média/eredeti.vtt", self.v / "I23 - A Nyugat/Média/A Nyugat.hu.vtt")
        self.assertEqual(len(atirat.atirat(self.V, self.VIDEO)["cuek"]), 2)

    def test_ures_felirat_figyelmeztet(self):
        ir(self.v, "I23 - A Nyugat/Média/A Nyugat.md", "# A Nyugat\n")
        ir(self.v, "I23 - A Nyugat/Média/A Nyugat.hu.vtt", "WEBVTT\n")
        d = atirat.atirat(self.V, self.VIDEO)
        self.assertEqual(d["cuek"], [])
        self.assertIn("nincs olvasható cue", d["figyelmeztetes"])


if __name__ == "__main__":
    unittest.main()
