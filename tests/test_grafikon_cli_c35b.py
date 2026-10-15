"""C35b-mag: a `bin/mos grafikon` új parancsai (terv, beiras, automatikus, tiltolista, modell-ellenorzes) — olvasó/próba módú CLI —,
a homokozó új `grafikon.egyezes` művelete és a közös beállítások. A CAS-homokozó helyett hamis (folyamaton belüli) példány megy."""
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

from core import automatika as A
from core import config, plot_allapot
from tests.grafikon_segedek import FM, F, HamisHomokozo, M
from tests.helpers import REPO, alg_core, ir, tmpdir

from grafikon import __main__ as CLI  # noqa: E402
from homokozo import gyerek  # noqa: E402

JEGYZET = FM + "# T\n\nA függvények vizsgálata az analízis alapfeladata, a grafikon sokat segít a megértésben.\n\n$$y = x^2 - 4$$\n"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "T01/A.md", JEGYZET)
        os.utime(self.v / "T01/A.md", (1.0, 1.0))                                       # rég módosult: a csend letelt
        env = mock.patch.dict(os.environ, {"MOS_ROOT": str(self.root), "HOME": str(self.root.parent / "home")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("MOS_FELADAT", None)

    def fut(self, *argv, hk=None):
        ki, hiba = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(ki), contextlib.redirect_stderr(hiba):
            kod = CLI.main(list(argv), hk=hk or HamisHomokozo(), stdin=io.StringIO(""))
        return kod, ki.getvalue(), hiba.getvalue()


class Parancsok(Alap):
    def test_terv_csak_olvas(self):
        kod, ki, _ = self.fut("terv", str(self.v / "T01/A.md"))
        self.assertEqual(kod, 0)
        d = json.loads(ki[ki.index("{"):])
        self.assertEqual([(b["utan_sor"], b["fajta"]) for b in d["beszurasok"]], [(12, "fuggveny")])
        self.assertEqual((self.v / "T01/A.md").read_text(encoding="utf-8"), JEGYZET)

    def test_terv_tiltolistat_olvas(self):
        j = json.loads(self.fut("terv", str(self.v / "T01/A.md"))[1])["beszurasok"]
        from grafikon import tiltolista as T
        plot_allapot.Tiltolista(self.cfg).felvesz(T.kulcs_szoveg("y = x^2 - 4"), "T01/A.md")
        d = json.loads(self.fut("terv", str(self.v / "T01/A.md"))[1])
        self.assertEqual((j[0]["fajta"], d["beszurasok"], d["kihagyva"][0]["ok"]), ("fuggveny", [], "tiltolista"))

    def test_automatikus_alapbol_szaraz(self):
        kod, ki, _ = self.fut("automatikus")
        d = json.loads(ki[ki.index("{"):])
        self.assertEqual((kod, [x["ut"] for x in d["dontesek"]], d["jegyzetek"]), (0, ["T01/A.md"], []))
        self.assertEqual(plot_allapot.Automatika(self.cfg).olvas(), {})                  # nem jegyez (a régi állapotfájl nem is íródik)
        self.assertFalse(A.ut(self.cfg).exists())                                        # a közös tár sem jön létre

    def test_eles_iras_csak_a_feladatsorbol(self):
        kod, ki, hiba = self.fut("automatikus", "--eles")
        self.assertEqual((kod, ki), (2, ""))
        self.assertIn("MOS_FELADAT", hiba)
        self.assertEqual((self.v / "T01/A.md").read_text(encoding="utf-8"), JEGYZET)

    def test_automatikus_eles_core_nelkul_nem_ir(self):
        """A feladatsor lépése a core nélkül (nincs MOS_CORE_URL) sem ír: a kliens 503-mal áll meg, a jegyzet érintetlen."""
        os.environ["MOS_FELADAT"] = "F-20261005-100000-1"
        os.environ.pop("MOS_CORE_URL", None)
        from core import gepi_kliens
        with self.assertRaises(gepi_kliens.GepiHiba):
            self.fut("automatikus", "--eles")
        self.assertEqual((self.v / "T01/A.md").read_text(encoding="utf-8"), JEGYZET)

    def test_szaraz_ut_megadva_a_kapott_utakat_listazza(self):
        kod, ki, _ = self.fut("automatikus", "--szaraz", "--ut", "T01/A.md")
        d = json.loads(ki[ki.index("{"):])
        self.assertEqual((kod, d["dontesek"], d["jegyzetek"]), (0, [{"ut": "T01/A.md", "ok": "kapott"}], []))

    def test_modell_hivo_valasztas(self):
        """Éles futásban a modell-ág csak a `modell_ag` kapcsolóval (alapból hamis); kézi/próba futásban a kapcsolóval vagy a kifejezett modellel."""
        cfg = config.load()
        self.assertIsNone(CLI._modell_hivo(cfg, eles=True, modell_ag=True))                # éles + kapcsoló hamis: nincs modell-ág
        self.assertIsNone(CLI._modell_hivo(cfg, eles=False, modell_ag=False))
        self.assertIsNotNone(CLI._modell_hivo(cfg, eles=False, modell_ag=True))
        h = CLI._modell_hivo(cfg, eles=False, modell_ag=False, modell="qwen35_9b")
        self.assertEqual((h.modell, h.mod), ("qwen35_9b", "auto"))
        cfg.data["grafikon"]["automatika"]["modell_ag"] = True
        h = CLI._modell_hivo(cfg, eles=True, modell_ag=False)
        self.assertEqual((h.modell, h.mod), (None, "auto"))                               # éles: a router kalibrált modellje

    def test_eles_proba_kerese_klonra_ir(self):
        """A vezérlő `proba: true` kérése (`--eles --proba`) klónra ír és a tárhoz nem nyúl (a C35b-mag `proba=not eles` hibája)."""
        os.environ["MOS_FELADAT"] = "F-20261005-100000-1"
        beiro = mock.MagicMock()
        beiro.jegyzet.return_value = {"allapot": "nincs_teendo", "beirt": [], "tartalom": JEGYZET, "hash_utan": "h", "fuggoben": 0}
        with mock.patch.object(CLI, "_beiro", return_value=beiro) as b:
            kod, ki, _ = self.fut("automatikus", "--eles", "--proba", "--ut", "T01/A.md")
        self.assertEqual(kod, 0)
        self.assertTrue(b.call_args.kwargs["proba"])
        self.assertFalse(A.ut(self.cfg).exists())

    def test_eles_ut_lepes_a_tarba_jegyez(self):
        os.environ["MOS_FELADAT"] = "F-20261005-100000-1"
        beiro = mock.MagicMock()
        beiro.jegyzet.return_value = {"allapot": "nincs_teendo", "beirt": [], "tartalom": JEGYZET, "hash_utan": "h1", "fuggoben": 0}
        beiro.kliens = mock.MagicMock()
        with mock.patch.object(CLI, "_beiro", return_value=beiro) as b, \
                mock.patch("grafikon.beiras.visszavont_shak", return_value=set()), \
                mock.patch("grafikon.beiras.torles_ellenorzes", return_value=[]):
            kod, ki, _ = self.fut("automatikus", "--eles", "--ut", "T01/A.md")
        self.assertEqual(kod, 0)
        self.assertFalse(b.call_args.kwargs["proba"])
        self.assertIsNone(b.call_args.kwargs["modell"])                                   # a kapcsoló alapból hamis
        sor = A.Tar(self.cfg).sor("grafikon", "T01/A.md")
        self.assertEqual(sor["hash"], "h1")

    def test_tiltolista_es_modell_ellenorzes(self):
        plot_allapot.Tiltolista(self.cfg).felvesz("0123456789abcdef", "T01/A.md")
        d = json.loads(self.fut("tiltolista")[1])
        self.assertEqual([t["kulcs"] for t in d["tiltott"]], ["0123456789abcdef"])
        blokk = self.v / "modell.txt"
        blokk.write_text("```plot\nx in [-4, 4]\ny = 1/x\n```\n", encoding="utf-8")
        kod, ki, _ = self.fut("modell-ellenorzes", r"y = \frac{1}{x}", str(blokk))
        d = json.loads(ki)
        self.assertEqual((kod, d["felismeres"]["bizonyossag"], d["ellenorzes"]["allapot"], d["ellenorzes"]["egyeztetes"]),
                         (0, "bizonytalan", "elfogadva", "referencia"))
        blokk.write_text("semmi sem rajzolható", encoding="utf-8")
        d = json.loads(self.fut("modell-ellenorzes", r"y = \frac{1}{x}", str(blokk))[1])
        self.assertEqual(d["ellenorzes"]["allapot"], "elvetve")


class SzkriptIndulas(unittest.TestCase):
    """A `bin/mos grafikon` a __main__.py-t szkriptként indítja: a `main()` argv nélkül hívódik (sys.argv-ból olvas)."""

    def test_modell_meres_argv_nelkul_a_sys_argv_bol(self):
        hivott = []
        with mock.patch("grafikon.modell_meres.main", side_effect=lambda a, homokozo=None: hivott.append(a) or 0), \
                mock.patch.object(sys, "argv", ["__main__.py", "modell-meres", "--modell", "qwen35_4b", "--keret", "munka"]):
            self.assertEqual(CLI.main(), 0)
        self.assertEqual(hivott, [["--modell", "qwen35_4b", "--keret", "munka"]])


class Egyezes(unittest.TestCase):
    def test_gyerek_regiszter_es_muvelet(self):
        self.assertEqual(gyerek.MUVELETEK["grafikon.egyezes"], ("grafikon.muveletek", "egyezes"))
        self.assertEqual(M.egyezes("1/x", "x^(-1)"), {"egyezik": True})
        self.assertEqual(M.egyezes("x^2", "x^3"), {"egyezik": False})
        for rossz in ("", " ", 5, "x" * 5000):
            with self.assertRaises(ValueError):
                M.egyezes(rossz, "x")
        with self.assertRaises(Exception):
            M.egyezes("__import__('os')", "x")                                          # a fehérlista a gyermekben is tart

    def test_homokozo_vegrehajt(self):
        """A gyermek `vegrehajt`-ja (folyamaton belül, sandbox nélkül): az új művelet ok-állapotot ad, ismeretlen nevet tilt."""
        ok = gyerek.vegrehajt({"muvelet": "hivas", "nev": "grafikon.egyezes", "args": {"vart": "x+x", "kapott": "2*x"}})
        self.assertEqual((ok["allapot"], ok["ertek"]), ("ok", {"egyezik": True}))
        self.assertEqual(gyerek.vegrehajt({"muvelet": "hivas", "nev": "grafikon.nincs", "args": {}})["allapot"], "tiltott")


if __name__ == "__main__":
    unittest.main()
