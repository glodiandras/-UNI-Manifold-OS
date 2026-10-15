"""C25c: a VTT-mondatok és a PDF-lapok szövege a lexikai indexben (`horgony` tábla, 4-es migráció), a találat helye (`mp`,
`oldal`, a felirat médiája), a média-súly, és a PDF-kinyerő (gyorsítótár, kapu, gyermekfolyamat). Álvaulton; a valódi
vaulthoz és var/-hoz nem nyúl, modellt nem tölt."""
import os
import shutil
import sys
import threading
import unittest
from pathlib import Path

from core import atirat
from core.index import indexelo, pdfszoveg, tar
from tests import csak_darwin
from tests.helpers import ir, tmpdir
from tests.index_segedek import alvault, index_indit, var_ra

VIDEO = "ATTCHMNTS - Videos/Kölcsey.mp4"
VTT = "I11 - Romantika/Média/Kölcsey.hu.vtt"
VTT_SZOVEG = ("WEBVTT\n\nNOTE manifold-asr\nmotor: x\n\n"
              "1\n00:00:01.000 --> 00:00:23.000\nTudod, hogy van egy születésnap január 22-én?\n\n"
              "2\n00:00:23.000 --> 00:00:28.000\nSzatmárcsekén ezen a napon\n\n"
              "3\n00:00:28.000 --> 00:00:31.500\nszületett a Himnusz.\n\n"
              "4\n00:01:05.000 --> 00:01:09.000\nA kínzó fájdalom a szentimentalizmushoz utalja a művet.\n")

FAJLOK = {
    ".obsidian/app.json": "{}",
    "Jegyzet.md": "# Himnusz\nA Himnusz Kölcsey verse, a szentimentalizmus nyomaival.\n",
    VIDEO: b"\x00" * 16,
    VTT: VTT_SZOVEG,
    "I11 - Romantika/Média/Kölcsey.md": "# Kölcsey\n",
    "Könyv.pdf": b"%PDF-1.4 hamis\n",
}


class AtiratMondatokTest(unittest.TestCase):
    def test_mondatokka_von_es_ismetlest_kihagy(self):
        cuek = [{"k": 1.0, "v": 2.0, "szoveg": "Első"}, {"k": 2.0, "v": 3.0, "szoveg": "Első"},
                {"k": 3.0, "v": 4.0, "szoveg": "mondat vége."}, {"k": 5.0, "v": 6.0, "szoveg": "Második!"},
                {"k": 7.0, "v": 8.0, "szoveg": "befejezetlen"}]
        self.assertEqual(atirat.mondatok(cuek), [(1.0, "Első mondat vége."), (5.0, "Második!"), (7.0, "befejezetlen")])

    def test_hosszkorlat(self):
        cuek = [{"k": float(i), "v": i + 1.0, "szoveg": f"{i}. " + "szó " * 30} for i in range(10)]
        m = atirat.mondatok(cuek, max_hossz=200)
        self.assertTrue(all(len(s) <= 400 for _, s in m))
        self.assertGreater(len(m), 1)

    def test_kereso_szakaszok(self):
        sz = atirat.kereso_szakaszok(VTT_SZOVEG.encode())
        self.assertEqual(sz, [("Tudod, hogy van egy születésnap január 22-én?\nSzatmárcsekén ezen a napon született a Himnusz.",
                               1.0, 1, [1.0, 23.0]),
                              ("A kínzó fájdalom a szentimentalizmushoz utalja a művet.", 65.0, 3, [65.0])])
        self.assertEqual(atirat.kereso_szakaszok(b"x" * (atirat.MAX_VTT + 1)), [])
        hosszu = atirat.kereso_szakaszok(VTT_SZOVEG.encode(), ablak_max=50)       # a karakterkorlát is ablakot zár
        self.assertEqual([x[2] for x in hosszu], [1, 2, 3])

    def test_felirat_torzs(self):
        self.assertEqual(atirat.felirat_torzs("A.hu.vtt"), ["A", "A.hu"])
        self.assertEqual(atirat.felirat_torzs("A. B.vtt"), ["A. B"])
        self.assertEqual(atirat.felirat_torzs("A.mp4"), [])


class MediaFeliratbolTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, FAJLOK)

    def test_a_reteg_feliratarol_a_videora(self):
        b = atirat.beallitasok(self.cfg)
        self.assertEqual(atirat.media_feliratbol(str(self.v), VTT, [VIDEO], b), VIDEO)
        self.assertIsNone(atirat.media_feliratbol(str(self.v), VTT, [], b))
        self.assertIsNone(atirat.media_feliratbol(str(self.v), "Más/Kölcsey.hu.vtt", [VIDEO], b))

    def test_sajat_mappaban_allo_hang(self):
        ir(self.v, "Hang/Előadás.m4a", b"\x00", "wb")
        ir(self.v, "Hang/Előadás.vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nSzia.\n")
        b = atirat.beallitasok(self.cfg)
        self.assertEqual(atirat.media_feliratbol(str(self.v), "Hang/Előadás.vtt", ["Hang/Előadás.m4a", VIDEO], b),
                         "Hang/Előadás.m4a")


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, FAJLOK)

    def indit(self, **kw):
        ix, ev = index_indit(self.cfg, **kw)
        self.addCleanup(ix.leallit)
        return ix, ev

    def gyorsitotar(self) -> pdfszoveg.Gyorsitotar:
        g = pdfszoveg.Gyorsitotar(Path(self.cfg.path("index")) / "pdf-szoveg.sqlite")
        self.addCleanup(g.close)
        return g


class FeliratIndexTest(_Alap):
    def test_a_felirat_mondata_masodperccel_es_mediaval(self):
        ix, _ = self.indit()
        r = ix.kereses("Szatmárcsekén")
        self.assertEqual([t["ut"] for t in r["talalatok"]], [VTT])
        t = r["talalatok"][0]
        self.assertEqual((t["tipus"], t["media"]), ("felirat", VIDEO))
        self.assertEqual([(s["sor"], s["mp"]) for s in t["talalatok"]], [(2, 23.0)])

    def test_a_valtozott_felirat_ujraindexelodik(self):
        ix, _ = self.indit()
        ir(self.v, VTT, "WEBVTT\n\n00:02:00.000 --> 00:02:03.000\nÚj mondat a balladáról.\n")
        self.assertTrue(ix.frissit([VTT]))
        r = ix.kereses("balladáról")
        self.assertEqual([(s["sor"], s["mp"]) for s in r["talalatok"][0]["talalatok"]], [(1, 120.0)])
        self.assertEqual(ix.kereses("Szatmárcsekén")["talalatok"], [])

    def test_a_jegyzet_megelozi_a_feliratot(self):
        ix, _ = self.indit()
        r = ix.kereses("szentimentalizmus")
        self.assertEqual([t["ut"] for t in r["talalatok"]], ["Jegyzet.md", VTT])
        self.assertNotIn("tipus", r["talalatok"][0])

    def test_a_4es_migracio_a_regi_feliratot_feldolgozza(self):
        ix, _ = index_indit(self.cfg)
        db = ix.db_ut
        ix.leallit()
        c = tar.nyit(db, iro=True)                      # a v3-as állapot: nincs média-szöveg (a táblák sem)
        for t in ("fts_szakasz", "szakasz", "media_szoveg"):
            c.execute(f"DROP TABLE {t}")
        c.execute("PRAGMA user_version = 3")
        c.close()
        ix, _ = self.indit()
        self.assertEqual(len(ix.kereses("Szatmárcsekén")["talalatok"]), 1)


class PdfIndexTest(_Alap):
    def test_a_gyorsitotarbol_az_oldalra(self):
        g = self.gyorsitotar()
        st = (self.v / "Könyv.pdf").stat()
        g.ir("Könyv.pdf", st.st_size, st.st_mtime_ns, lapok=["Előszó\nmásodik sor", "", "A Himnusz keletkezése\nKölcsey"])
        ix, _ = self.indit()
        # a szöveg az első szinkron után, külön kötegben kerül az FTS-be (a hidegépítés nem vár rá)
        self.assertTrue(var_ra(lambda: ix.kereses("keletkezése")["talalatok"], 5))
        r = ix.kereses("keletkezése")
        t = r["talalatok"][0]
        self.assertEqual((t["ut"], t["tipus"]), ("Könyv.pdf", "pdf"))
        self.assertEqual([(s["sor"], s["oldal"]) for s in t["talalatok"]], [(3, 3)])
        self.assertEqual(ix.allapot()["pdf_szoveg"]["osszes"], 1)
        self.assertEqual(ix.allapot()["pdf_szoveg"]["kesz"], 1)

    def test_kapu_nelkul_nincs_kinyeres(self):
        ix, _ = self.indit()
        self.assertIsNone(ix.pdf_kinyero)
        self.assertEqual(ix.allapot()["pdf_szoveg"]["kesz"], 0)

    def test_a_kinyero_a_kapu_utan_tolt(self):
        hivasok = []
        nyitva = threading.Event()

        def al_kinyer(pdf, sandbox, idokorlat, leallit=None):
            hivasok.append(Path(pdf).name)
            return {"lapok": ["első lap", "A Himnusz keletkezése"], "csonka": False}
        eredeti = pdfszoveg.kinyer
        pdfszoveg.kinyer = al_kinyer
        self.addCleanup(setattr, pdfszoveg, "kinyer", eredeti)
        ix, ev = self.indit(pdf_kapu=nyitva.is_set)
        ix.pdf_kinyero.kapu_varakozas = 0.02
        self.assertEqual(ix.kereses("keletkezése")["talalatok"], [])
        self.assertEqual(hivasok, [])                       # a kapu zárva (D8, aktív használat): nem nyer ki
        self.assertTrue(var_ra(lambda: ix.allapot()["pdf_szoveg"]["varakozik"] == 1, 2))
        nyitva.set()
        self.assertTrue(var_ra(lambda: ix.kereses("keletkezése")["talalatok"], 5))
        self.assertEqual(hivasok, ["Könyv.pdf"])
        t = ix.kereses("keletkezése")["talalatok"][0]
        self.assertEqual(t["talalatok"][0]["oldal"], 2)
        self.assertTrue(var_ra(lambda: any(e.get("tipus") == "pdf_szoveg" for e in ev), 2))
        self.assertTrue(var_ra(lambda: ix.allapot()["pdf_szoveg"]["kesz"] == 1, 2))
        # újraindítás: a gyorsítótárból jön, nem nyer ki újra; a vault.sqlite újraépítése sem
        ix.leallit()
        os.remove(ix.db_ut)
        ix2, _ = self.indit(pdf_kapu=nyitva.is_set)
        self.assertTrue(var_ra(lambda: ix2.kereses("keletkezése")["talalatok"], 5))
        self.assertEqual(hivasok, ["Könyv.pdf"])

    def test_a_hibas_pdf_nem_kerul_ujra_sorra(self):
        g = self.gyorsitotar()
        st = (self.v / "Könyv.pdf").stat()
        g.ir("Könyv.pdf", st.st_size, st.st_mtime_ns, hiba="a PDF nem nyitható meg")
        ix, _ = self.indit(pdf_kapu=lambda: False)
        self.assertTrue(var_ra(lambda: ix.allapot()["pdf_szoveg"]["kesz"] == 1, 2))
        self.assertEqual(ix.allapot()["pdf_szoveg"]["varakozik"], 0)

    def test_a_valtozott_pdf_ujra_kinyerodik(self):
        hivasok = []

        def al_kinyer(pdf, sandbox, idokorlat, leallit=None):
            hivasok.append(Path(pdf).read_bytes())
            return {"lapok": [f"változat {len(hivasok)}"], "csonka": False}
        eredeti = pdfszoveg.kinyer
        pdfszoveg.kinyer = al_kinyer
        self.addCleanup(setattr, pdfszoveg, "kinyer", eredeti)
        ix, _ = self.indit(pdf_kapu=lambda: True)
        self.assertTrue(var_ra(lambda: ix.kereses('"változat 1"')["talalatok"], 5))
        ir(self.v, "Könyv.pdf", b"%PDF-1.4 uj valtozat, hosszabb\n", "wb")
        self.assertTrue(ix.frissit(["Könyv.pdf"]))
        self.assertTrue(var_ra(lambda: ix.kereses('"változat 2"')["talalatok"], 5))
        self.assertEqual(ix.kereses('"változat 1"')["talalatok"], [])

    def test_a_torolt_pdf_kikerul_a_sorbol(self):
        ix, _ = self.indit(pdf_kapu=lambda: False)
        self.assertTrue(var_ra(lambda: ix.allapot()["pdf_szoveg"]["varakozik"] == 1, 2))
        os.remove(self.v / "Könyv.pdf")
        self.assertTrue(ix.frissit(["Könyv.pdf"]))
        self.assertEqual(ix.allapot()["pdf_szoveg"]["varakozik"], 0)

    def test_szakaszok(self):
        self.assertEqual(pdfszoveg.szakaszok(["a\nb", "", "c"]), [("a\nb", 1, 1, None), ("c", 3, 3, None)])
        self.assertEqual(pdfszoveg.szakaszok([]), [])

    def test_a_kerdes_lapon_belul_teljesul_es_a_jegyzetek_pontja_valtozatlan(self):
        ix0, _ = self.indit()
        jegyzet_elotte = ix0.kereses("szentimentalizmus")["talalatok"][0]
        ix0.leallit()
        g = self.gyorsitotar()
        st = (self.v / "Könyv.pdf").stat()
        g.ir("Könyv.pdf", st.st_size, st.st_mtime_ns, lapok=["Kölcsey a szentimentalizmus költője", "Himnusz"])
        ix, _ = self.indit()
        self.assertTrue(var_ra(lambda: ix.allapot()["pdf_szoveg"]["kesz"] == 1, 5))
        self.assertEqual(ix.kereses("szentimentalizmus")["talalatok"][0], jegyzet_elotte)   # a jegyzet bm25-je nem változik
        self.assertNotIn("Könyv.pdf", [t["ut"] for t in ix.kereses("Kölcsey Himnusz")["talalatok"]])   # két külön lapon
        r = ix.kereses("szentimentalizmus Kölcsey")
        self.assertEqual([(t["ut"], {(s["sor"], s.get("oldal")) for s in t["talalatok"]}) for t in r["talalatok"]],
                         [("Jegyzet.md", {(2, None)}), ("Könyv.pdf", {(1, 1)})])       # a jegyzet elöl (média-súly)
        self.assertEqual(ix.kereses("path:Könyv")["talalatok"][0]["tipus"], "pdf")             # név/út szerint is


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("sandbox-exec"), "sandbox-exec (macOS) kell")
class GyermekTest(unittest.TestCase):
    """A valódi gyermekfolyamat a sandbox-exec profil alatt, egy generált PDF-en (PyMuPDF-fel)."""

    def setUp(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("nincs PyMuPDF")
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.pdf = Path(self._t.name) / "Próba könyv.pdf"
        doc = pymupdf.open()
        for s in ("Elso oldal szovege", "Masodik oldal: Kölcsey es a Himnusz"):
            doc.new_page().insert_text((72, 72), s)
        doc.save(str(self.pdf))
        doc.close()

    @csak_darwin("sandbox-exec")
    def test_lapok_es_elzaras(self):
        r = pdfszoveg.kinyer(self.pdf, shutil.which("sandbox-exec"), 60)
        self.assertEqual(r, {"lapok": ["Elso oldal szovege", "Masodik oldal: Kölcsey es a Himnusz"], "csonka": False})

    def test_hibas_pdf(self):
        rossz = Path(self._t.name) / "rossz.pdf"
        rossz.write_bytes(b"%PDF-1.4 nem pdf")
        r = pdfszoveg.kinyer(rossz, shutil.which("sandbox-exec"), 60)
        self.assertIn("hiba", r)

    def test_sandbox_nelkul_zarva_hibazik(self):
        with self.assertRaises(pdfszoveg.KornyezetHiba):
            pdfszoveg.kinyer(self.pdf, None, 60)
        with self.assertRaises(pdfszoveg.KornyezetHiba):
            pdfszoveg.kinyer(self.pdf, "/nincs/sandbox-exec", 60)


if __name__ == "__main__":
    unittest.main()
