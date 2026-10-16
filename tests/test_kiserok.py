"""`core/kiserok.py`: a kísérő- (gépi) mappák egyetlen forrása (F3-DESIGN §7.2, §8). A `[vault] kisero_elotag` átírása az automatikát, a
hasonló jegyzeteket, a gépi írás célmappáit, a téma-felismerést, az asszisztens kizárásait és a séma kísérő-osztályait együtt viszi."""
import unicodedata
import unittest
from datetime import date
from pathlib import Path

from core import atirat, automatika, gepi_iras, kartya_api, kiserok, kviz_api, osszefoglalas_api, videolanc
from core.asszisztens.beallitasok import beallitasok
from core.index.hibrid import hasonlo
from core.tulajdonsagok import Sema, Tulajdonsagok
from core.vaultio import Invalid, Vault
from modulok.kartya import formatum as kartya_fm
from modulok.kviz import formatum as kviz_fm
from modulok.osszefoglalas import formatum as ossz_fm
from modulok.ytdlp import egyezes, elhelyezes
from tests.helpers import tmpdir
from tests.vaultgyar import alg_semleges

ALAP = {"kartya": "Manifold - Cards", "kviz": "Manifold - Quizzes", "osszefoglalas": "Manifold - Summaries",
        "fuzet": "Manifold - Photos", "video": "Manifold - Videos"}
GEN = {"kartya": "Gen - Cards", "kviz": "Gen - Quizzes", "osszefoglalas": "Gen - Summaries", "fuzet": "Gen - Photos",
       "video": "Gen - Videos"}


class Cfg:
    """Minimális konfig: `section(*kulcsok)` egy beágyazott szótárból (a `kiserok` csak ezt hívja)."""

    def __init__(self, **szakaszok):
        self.data = szakaszok

    def section(self, *kulcsok):
        n = self.data
        for k in kulcsok:
            n = n.get(k, {})
        return n


class AlapTest(unittest.TestCase):
    def test_alapok_konfig_nelkul(self):
        self.assertEqual(kiserok.ALAP_ELOTAG, "Manifold - ")
        self.assertEqual(kiserok.kisero_elotag(None), "Manifold - ")
        self.assertEqual(kiserok.kisero_mappak(None), ALAP)
        self.assertEqual({f: kiserok.alap_mappa(f) for f in kiserok.FAJTAK}, ALAP)
        with self.assertRaises(KeyError):
            kiserok.kisero_mappa(None, "nincs")

    def test_a_szallitott_kulcsok_alapja_az_elotagot_koveti(self):
        cfg = Cfg(vault={"kisero_elotag": "Gen - "}, kartya={"mappa": ALAP["kartya"]}, kviz={"mappa": ALAP["kviz"]},
                  osszefoglalas={"mappa": ALAP["osszefoglalas"]}, fuzet={"cel_mappa": ALAP["fuzet"]},
                  video={"vault_mappa": ALAP["video"]}, media={"video_mappa": ALAP["video"]})
        self.assertEqual(kiserok.kisero_elotag(cfg), "Gen - ")
        self.assertEqual(kiserok.kisero_mappak(cfg), GEN)

    def test_ures_kulcs_is_az_alap(self):
        cfg = Cfg(vault={"kisero_elotag": "Gen - "}, kartya={"mappa": ""}, kviz={"mappa": "/"})
        self.assertEqual(kiserok.kisero_mappa(cfg, "kartya"), "Gen - Cards")
        self.assertEqual(kiserok.kisero_mappa(cfg, "kviz"), "Gen - Quizzes")

    def test_kifejezett_feluliras_nyer(self):
        cfg = Cfg(vault={"kisero_elotag": "Gen - "}, kartya={"mappa": "Flashcards/"}, fuzet={"cel_mappa": "Img"})
        self.assertEqual(kiserok.kisero_mappa(cfg, "kartya"), "Flashcards")          # záró perjel nélkül
        self.assertEqual(kiserok.kisero_mappa(cfg, "fuzet"), "Img")
        self.assertEqual(kiserok.kisero_mappa(cfg, "kviz"), "Gen - Quizzes")        # a többi az előtagot követi

    def test_a_video_ket_kulcsa(self):
        self.assertEqual(kiserok.kisero_mappa(Cfg(media={"video_mappa": "Clips"}), "video"), "Clips")
        self.assertEqual(kiserok.kisero_mappa(Cfg(video={"vault_mappa": "Movies"}, media={"video_mappa": "Clips"}), "video"), "Movies")

    def test_nfc(self):
        nfd = unicodedata.normalize("NFD", "Kísérő - ")
        cfg = Cfg(vault={"kisero_elotag": nfd})
        self.assertEqual(kiserok.kisero_elotag(cfg), unicodedata.normalize("NFC", nfd))
        self.assertTrue(kiserok.tartalmi_elotaggal("M/a.md", nfd))
        self.assertFalse(kiserok.tartalmi_elotaggal(unicodedata.normalize("NFD", "Kísérő - cards/x.md"), unicodedata.normalize("NFC", nfd)))

    def test_tartalmi_ut_es_kisero_ut(self):
        cfg = Cfg(vault={"kisero_elotag": "Gen - "})
        self.assertTrue(kiserok.tartalmi_ut(cfg, "Projects/a.md"))
        self.assertFalse(kiserok.tartalmi_ut(cfg, "Gen - Cards/a.md"))
        self.assertFalse(kiserok.tartalmi_ut(cfg, "Projects/Gen - Quizzes/a.md"))     # bármely mélységben
        self.assertTrue(kiserok.tartalmi_ut(cfg, "Manifold - Cards/a.md"))             # az alap itt nem kísérő
        self.assertFalse(kiserok.tartalmi_ut(cfg, ".obsidian/a.md"))
        self.assertFalse(kiserok.tartalmi_ut(cfg, "Projects/a.canvas"))
        self.assertTrue(kiserok.kisero_ut("A/Gen - Cards/x", "Gen - "))
        self.assertFalse(kiserok.kisero_ut("A/Genesis/x", "Gen - "))

    def test_subject_of(self):
        cfg = Cfg(pdf={"tags": {"M": "Mathematics", "T": "History"}})
        self.assertEqual(kiserok.subject_of(cfg, "M01 - Algebra/a.pdf"), "Mathematics")
        self.assertEqual(kiserok.subject_of(cfg, "t02 - Rome/b.md"), "History")
        self.assertIsNone(kiserok.subject_of(cfg, "Z01 - Other/b.md"))
        self.assertIsNone(kiserok.subject_of(cfg, "M-root.md"))                         # a gyökérben álló jegyzetnek nincs tantárgya
        self.assertIsNone(kiserok.subject_of(Cfg(), "M01 - Algebra/a.pdf"))             # üres térkép: nincs tantárgy
        self.assertIsNone(kiserok.subject_of(None, "M01 - Algebra/a.pdf"))

    def test_tema_minta_alap(self):
        import re
        m = re.compile(kiserok.tema_minta_alap(Cfg(vault={"kisero_elotag": "Gen - "})))
        for jo in ("Projects", "Reading list", "2026 plans"):
            self.assertTrue(m.match(jo), jo)
        for rossz in ("Gen - Cards", "_Template", ".obsidian"):
            self.assertFalse(m.match(rossz), rossz)
        self.assertEqual(m.groups, 0)                                                  # nincs tárgy-betű, nincs sorszám-konvenció


class EgyForrasTest(unittest.TestCase):
    """Egy átírt kísérő-előtag minden felhasználónál megjelenik; senki nem tart külön listát."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)
        self.cfg.data["vault"]["kisero_elotag"] = "Gen - "

    def test_a_kulcsok_alapja_az_elotagot_koveti(self):
        self.assertEqual(kiserok.kisero_mappak(self.cfg), GEN)
        self.assertEqual(self.cfg.section("kartya")["mappa"], ALAP["kartya"])           # a szállított kulcs változatlan: az előtag viszi

    def test_automatika_es_hasonlo(self):
        elotag = automatika.kisero_elotag(self.cfg)
        self.assertEqual(elotag, "Gen - ")
        self.assertFalse(automatika.tartalmi_ut("Gen - Cards/x.md", elotag))
        self.assertTrue(automatika.tartalmi_ut("Manifold - Cards/x.md", elotag))
        self.assertTrue(hasonlo.kisero("Gen - Quizzes/x.md", elotag))
        self.assertFalse(hasonlo.kisero("Manifold - Quizzes/x.md", elotag))

    def test_api_mappak_es_formatumok(self):
        self.assertEqual(kartya_api.mappa(self.cfg), "Gen - Cards")
        self.assertEqual(kviz_api.mappa(self.cfg), "Gen - Quizzes")
        self.assertEqual(osszefoglalas_api.mappa(self.cfg), "Gen - Summaries")
        self.assertEqual(atirat.beallitasok(self.cfg)["video_mappa"], "Gen - Videos")
        # a formátum-modulok alapja a szállított alap (a konfig nélküli hívó), ugyanabból a forrásból
        self.assertEqual((kartya_fm.ALAP_MAPPA, kviz_fm.ALAP_MAPPA, ossz_fm.ALAP_MAPPA, elhelyezes.ALAP_VIDEO_MAPPA, atirat.ALAP_VIDEO_MAPPA),
                         (ALAP["kartya"], ALAP["kviz"], ALAP["osszefoglalas"], ALAP["video"], ALAP["video"]))
        self.assertEqual((gepi_iras.VIDEO_MAPPA_ALAP, gepi_iras.FUZET_MAPPA_ALAP), (ALAP["video"], ALAP["fuzet"]))

    def test_a_sema_kisero_osztalyai(self):
        sema = Sema.betolt(self.cfg)
        self.assertEqual(sema.osztaly("Gen - Quizzes/x.md")["nev"], "kviz")
        self.assertEqual(sema.osztaly("Gen - Cards/x.md")["nev"], "kartya")
        self.assertEqual(sema.osztaly("Gen - Summaries/x.md")["nev"], "osszefoglalo")
        self.assertEqual(sema.osztaly("Manifold - Cards/x.md")["nev"], "normal")
        self.assertEqual(sema.leiras()["kisero"], GEN)
        self.assertEqual(sema.leiras()["kisero_elotag"], "Gen - ")

    def test_gepi_iras_celmappai(self):
        g = gepi_iras.GepiIras(self.cfg, Vault(self.cfg), Tulajdonsagok(self.cfg, None), varakozas_mp=0.3)
        with self.assertRaises(Invalid) as e:
            g._m_mozgat({"ut": "Elsewhere/film.mp4", "forras": "/x"})
        self.assertIn("`Gen - Videos`", str(e.exception))
        with self.assertRaises(Invalid) as e:
            g._m_mozgat({"ut": "Elsewhere/photo.jpg", "forras": "/x"})
        self.assertIn("`Gen - Photos`", str(e.exception))

    def test_tema_felismeres_es_kizarasok(self):
        for nev in ("Projects", "Gen - Cards", "Manifold - Cards", "_Template"):
            (self.v / nev).mkdir(exist_ok=True)
        kw = egyezes.index_beallitas(self.cfg)
        temak = egyezes.temak(self.v, kw["tema_minta"], kw["kizart_mappak"])
        self.assertIn("Projects", temak)
        self.assertNotIn("Gen - Cards", temak)                                         # a kísérőmappa sosem téma
        self.assertNotIn("_Template", temak)                                           # a sablonmappa sem
        self.assertIn("Manifold - Cards", temak)                                       # az alap itt már nem kísérő
        self.assertIn("Gen - ", kw["kizart_mappak"])
        self.assertEqual(videolanc.temamappak(self.v, videolanc.tema_minta(self.cfg)), sorted(temak))

    def test_asszisztens_kizarasai(self):
        b = beallitasok(self.cfg)
        for kulcs in ("higienia_arva_kizart", "emlites_kizart", "kartya_kizart"):
            self.assertIn("Gen - ", b[kulcs])
            self.assertIn("_Template/", b[kulcs])
            self.assertNotIn("Manifold - ", b[kulcs])

    def test_a_napi_jegyzet_semleges_helye(self):
        from core import naplo
        self.assertEqual(naplo.napi_ut(self.cfg, date(2026, 10, 2)), "Daily/2026-10-02.md")


if __name__ == "__main__":
    unittest.main()
