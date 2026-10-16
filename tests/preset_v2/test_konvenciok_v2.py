"""A fejlesztő v2-konvenciói a `v2-kompat` presettel, a kísérőmappákon és a sémán át: az F3 előtt a `tests/test_config.py`
(`SemaConfigTeszt`), `test_kviz_formatum.py`, `test_kviz_generalas.py`, `test_osszefoglalas_formatum.py`,
`test_osszefoglalas_lanc.py` és `test_video_integralas.py` tesztjei, itt a presetre kifejezetten kérve."""
import unittest

from core import kiserok, tulajdonsagok
from core.tulajdonsagok import Tulajdonsagok
from modulok.kviz import formatum as kf
from modulok.kviz import generalas as kviz_gen
from modulok.osszefoglalas import formatum as FM
from modulok.osszefoglalas import lanc as L
from tests import test_kviz_formatum as TK
from tests import test_video_integralas as TV
from tests.preset_v2 import PRESET, csak_sajat, v2_cfg


class SemaConfigV2(unittest.TestCase):
    """Áthelyezve a `tests/test_config.py` `SemaConfigTeszt.test_valodi_config_semaja_feloldodik_es_betoltheto`-jából: a séma
    a preset sémafájlja (`config/presets/v2-kompat.schema.json`), a feloldási láncon át."""

    def test_a_preset_semaja_feloldodik_es_betoltheto(self):
        cfg = v2_cfg()
        self.assertEqual(kiserok.sema_fajl(cfg), cfg.root / "config" / "presets" / f"{PRESET}.schema.json")
        sema = tulajdonsagok.Sema.betolt(cfg)
        self.assertEqual(sema.mezosorrend, ["Tags", "Source", "Status", "NN", "Canvas"])
        self.assertEqual(sema.mod, "szigoru")
        self.assertTrue(sema.status_gazdai)
        self.assertIn("History", sema.tags)
        self.assertEqual({o["nev"] for o in sema.osztalyok}, {"kviz", "kartya", "osszefoglalo", "konyv-jegyzet"})

    def test_a_kisero_osztalyok_elotagja_a_kiserokbol_jon(self):
        sema = tulajdonsagok.Sema.betolt(v2_cfg())
        self.assertEqual(sema.osztaly("ATTCHMNTS - quizes/x.md")["nev"], "kviz")
        self.assertEqual(sema.osztaly("ATTCHMNTS - cards/x.md")["nev"], "kartya")
        self.assertEqual(sema.osztaly("ATTCHMNTS - summaries/x.md")["nev"], "osszefoglalo")
        self.assertEqual(sema.osztaly("Books/x.md")["nev"], "konyv-jegyzet")
        self.assertEqual(sema.osztaly("Manifold - Quizzes/x.md")["nev"], "normal")        # a semleges alap itt nem kísérő


class KvizSemaV2(unittest.TestCase):
    """Áthelyezve a `tests/test_kviz_formatum.py` `SemaKapuTest`-jéből."""

    def test_az_iro_kimenete_atmegy_a_kviz_sema_osztalyon(self):
        """A C22b `uj` művelete `osztaly: "kviz"`-zal ír: az író frontmatterének hibátlannak kell lennie."""
        tul = Tulajdonsagok(v2_cfg(), None)
        szoveg = kf.ir(TK.minta())
        fm = szoveg[:szoveg.index("---\n", 4) + 4]
        ut = kiserok.kisero_mappa(v2_cfg(), "kviz") + "/" + kf.fajlnev(TK.minta()) + ".md"
        self.assertEqual(ut.split("/")[0], "ATTCHMNTS - quizes")
        r = tul.elemez(ut, fm)
        self.assertEqual(r["osztaly"], "kviz")
        self.assertEqual(r["problemak"], [], r["problemak"])


class KvizBeallitasV2(unittest.TestCase):
    """Áthelyezve a `tests/test_kviz_generalas.py` `BeallitasTest.test_az_os_toml_szakasza_ervenyes_es_egyezik_az_alapokkal`-ából."""

    def test_az_os_toml_szakasza_ervenyes_es_egyezik_az_alapokkal(self):
        b = kviz_gen.beallitas(v2_cfg())
        self.assertEqual(b, kviz_gen.Beallitas())                      # az `os.toml` a legacy alapértékeit hordozza
        self.assertEqual(v2_cfg().section("kviz")["mappa"], "ATTCHMNTS - quizes")
        self.assertEqual(kiserok.kisero_mappa(v2_cfg(), "kviz"), "ATTCHMNTS - quizes")


class OsszefoglalasV2(unittest.TestCase):
    """Áthelyezve a `tests/test_osszefoglalas_formatum.py` `HorgonyNev.test_kisero_nev_utkozes`-ből és a
    `tests/test_osszefoglalas_lanc.py` `Alap.test_beallitas_az_os_tomlbol`-ból."""

    def test_kisero_nev_utkozes(self):
        mappa = kiserok.kisero_mappa(v2_cfg(), "osszefoglalas")
        utak = ["A/Mértani sorozat.md", "B/Más.md"]
        self.assertEqual(FM.kisero_nev("A/Mértani sorozat.md", utak), "Mértani sorozat — összefoglaló")
        self.assertEqual(FM.kisero_ut("A/Mértani sorozat.md", utak, mappa), "ATTCHMNTS - summaries/Mértani sorozat — összefoglaló.md")
        dupla = utak + ["C/Mértani sorozat.md"]
        self.assertEqual(FM.kisero_nev("A/Mértani sorozat.md", dupla), "Mértani sorozat (A) — összefoglaló")
        # a mappa-szint: a mappa útja `.md`-vel
        self.assertEqual(FM.kisero_nev("T03/Elmélet.md", utak), "Elmélet — összefoglaló")

    def test_beallitas_az_os_tomlbol(self):
        cfg = v2_cfg()
        b = L.beallitas(cfg)
        self.assertEqual(b.mappa, "ATTCHMNTS - summaries")
        self.assertEqual(L.profil(cfg).idezet_max_szo, 45)


@csak_sajat
class CelmappaV2(TV.IntegralasTest):
    """Áthelyezve a `tests/test_video_integralas.py` `IntegralasTest.test_celmappa_ellenorzes`-éből: a téma-mappa mintája a presetből
    jön (`<Betű><két szám> - <cím>`, a `…00 - ` vizuális mappa nem téma; a betű a `[pdf.tags]` egyik tárgya)."""

    def test_celmappa_ellenorzes(self):
        from core.videolanc import TemamappaHiba, temamappa_ellenoriz, tema_minta
        minta = tema_minta(self.cfg)
        tags = dict(self.cfg.section("pdf").get("tags") or {"D": "Informatics"})
        tags.setdefault("D", "Informatics")
        self.assertEqual(temamappa_ellenoriz(self.v, " D13 - CS50 ", tags, minta), "D13 - CS50")
        self.assertEqual(temamappa_ellenoriz(self.v, "T05 - A reformkor", {"T": "History"}, minta), "T05 - A reformkor")
        (self.v / "D14 - fajl").write_text("x")
        (self.v / "D15 - Kis").mkdir()
        for rossz in ("", "D13", "CS50", "D13 - CS50/Média", "../D13 - CS50", "D00 - Visual", "X01 - Napló", "AI01 - Workflow System",
                      "D13 - CS#50", "D13 - [CS50]", ".D13 - CS50", "d13 - cs50", "D14 - fajl", "D15 - KIS", "D13 - " + "x" * 200, 13):
            with self.subTest(rossz=rossz), self.assertRaises(TemamappaHiba):
                temamappa_ellenoriz(self.v, rossz, tags, minta)
        with self.assertRaises(ValueError):
            self.lanc(tema_mappa="D13 - CS50/Média")
        # a core mintája a téma-felismerés (egyezes `tema_minta`) szűkítése: amit elfogad, azt a duplikátum-szűrés témaként látja
        from modulok.ytdlp import egyezes
        kw = egyezes.index_beallitas(self.cfg)
        self.assertTrue(kw["tema_minta"].match("D13 - CS50"))
        (self.v / "D00 - Visual").mkdir()                                       # a `…00 - ` a tárgy vizuális mappája: nem téma
        (self.v / self.CS).mkdir()
        temak = egyezes.temak(self.v, kw["tema_minta"], kw["kizart_mappak"])
        self.assertIn(self.CS, temak)
        self.assertNotIn("D00 - Visual", temak)


if __name__ == "__main__":
    unittest.main()
