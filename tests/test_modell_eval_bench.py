"""`mos eval` (álaranyhalmaz, álmodelles worker), `mos bench` gyermeke (álháttér), a regiszter és a CLI."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from core.modell import beallitas as B
from core.modell import bench, eval as ev
from core.modell.kalibracio import Tabla
from core.modell.router import Router
from core.modell.worker import Gazda, Szerver, _handler
from tests.helpers import REPO, alg_core, tmpdir
from tests.modell_segedek import AlAktivitas, AlHatter, al_betolto, beallitas

FELADAT = '''
VERZIO = "proba-v1"
ROUTER_FELADAT = "szoveg"

def tetelek(cfg):
    for i in range(4):
        yield {"id": f"t{i}", "keres": {"messages": [{"role": "user", "content": f"kérdés {i}"}], "max_tokens": 100},
               "vart": "qwen35_2b: válasz" if i % 2 == 0 else "más"}

def pontoz(rekordok):
    jo = sum(1 for r in rekordok if r["valasz"] == r["vart"])
    return {"pontszam": jo / len(rekordok) if rekordok else 0.0, "helyes": jo}
'''


class EvalTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)
        d = self.cfg.path("modulok") / "eval" / "proba"
        d.mkdir(parents=True)
        (d / "feladat.py").write_text(FELADAT, encoding="utf-8")
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)
        self.tabla = Tabla(self.b.router_db)
        self.addCleanup(self.tabla.close)
        self.g = Gazda(self.b, al_betolto(self.b), AlAktivitas(), self.tabla, tick_mp=0.02, naplo=lambda s: None)
        self.srv = Szerver(("127.0.0.1", 0), _handler(self.g))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.u = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close(), self.g.utemezo.leall()))

    def test_futas_folytathato_ertekeles_rogzites(self):
        out = ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, limit=2, log=lambda s: None)
        self.assertEqual(len(out.read_text().splitlines()), 2)
        n_gen = len([e for e in AlHatter.naplo if e[0] == "general"])
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)          # folytatja, nem ismétel
        rek = [json.loads(s) for s in out.read_text().splitlines()]
        self.assertEqual([r["id"] for r in rek], ["t0", "t1", "t2", "t3"])
        self.assertEqual(len([e for e in AlHatter.naplo if e[0] == "general"]) - n_gen, 2)
        ert = ev.ertekel(self.cfg, "qwen35_2b", "proba")
        self.assertEqual((ert["pontszam"], ert["aranyhalmaz_verzio"], ert["router_feladat"]), (0.5, "proba-v1", "szoveg"))
        ev.rogzit(self.cfg, ert, kalibralt=False)
        self.assertEqual(self.tabla.tabla("szoveg")[0]["kalibralt"], 0)
        self.assertEqual(self.tabla.kalibralt_sorrend("szoveg"), [])
        ev.rogzit(self.cfg, ert, kalibralt=True)
        self.assertEqual(Router(self.b, self.tabla).valaszt("szoveg", 5.0).modell.nev, "qwen35_2b")

    def generalasok(self) -> int:
        return len([e for e in AlHatter.naplo if e[0] == "general"])

    def feladat_fajl(self):
        return self.cfg.path("modulok") / "eval" / "proba" / "feladat.py"

    def test_verziovaltas_nem_general_ujra_es_a_pontozas_az_aktualis_vart_hasznalja(self):
        """T046 (C29.8): a sorkulcs a kérés ujjlenyomata (id + beallitas), nem az arany verziója: a K27 jóváhagyása (a `-vazlat`
        levétele) vagy egy javított `vart` nem tesz elavulttá egyetlen generált sort sem; az értékelés a pontozáskor az
        AKTUÁLIS arany `vart`-ját olvassa, és rögzíti a használt verziót."""
        out = ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba")["pontszam"], 0.5)
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba", limit=1)["n"], 1)     # a --limit az értékelésre is hat
        n_gen = self.generalasok()
        self.feladat_fajl().write_text(FELADAT.replace("proba-v1", "proba-v2").replace('"más"', '"qwen35_2b: válasz"'),
                                       encoding="utf-8")                                   # új verzió + javított `vart`
        ert = ev.ertekel(self.cfg, "qwen35_2b", "proba")
        self.assertEqual((ert["n"], ert["aranyhalmaz_verzio"]), (4, "proba-v2"))           # ma: n == 0 (a régi sorok nem számítanak)
        self.assertEqual(ert["pontszam"], 1.0)                                             # az új `vart` szerint (a sorban a régi áll)
        self.assertEqual(ert["sor_verziok"], {"proba-v1": 4})                              # a sorok generálási verziója: adat
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        self.assertEqual(self.generalasok(), n_gen)                                        # nem generál újra
        self.assertEqual(len(out.read_text().splitlines()), 4)

    def test_tetelhalmaz_es_kerdes_valtozasa_igen_ujragenerál(self):
        """A kulcs az ujjlenyomat: a megszűnt tétel sora nem számít, a megváltozott kérésű (prompt) tétel újragenerálódik."""
        out = ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        self.feladat_fajl().write_text(FELADAT.replace("range(4)", "range(3)"), encoding="utf-8")
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba")["n"], 3)               # a t3 sora kimarad
        n_gen = self.generalasok()
        self.feladat_fajl().write_text(FELADAT.replace("kérdés {i}", "másik kérdés {i}"), encoding="utf-8")
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba")["n"], 0)               # a kérés ujjlenyomata más
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        self.assertEqual(self.generalasok() - n_gen, 4)
        self.assertEqual(len(out.read_text().splitlines()), 8)
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba")["n"], 4)

    def test_csak_ertekel_nem_inditja_a_workert_es_nem_general(self):
        """Az új sorrend újrapontozása: `mos eval … --csak-ertekel --rogzit` worker nélkül, a meglévő sorokon értékel és rögzít."""
        import contextlib
        import io
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        self.feladat_fajl().write_text(FELADAT.replace("proba-v1", "proba-v2"), encoding="utf-8")        # a K27 jóváhagyása
        n_gen = self.generalasok()

        class _Tilos:
            def __init__(self, *a, **k):
                raise AssertionError("a --csak-ertekel nem indíthat workert")
        ki = io.StringIO()
        with mock.patch.object(ev.config, "load", return_value=self.cfg), mock.patch.object(ev.kliens, "Folyamat", _Tilos), \
                contextlib.redirect_stdout(ki):
            kod = ev.main(["qwen35_2b", "proba", "--csak-ertekel", "--rogzit"])
        self.assertEqual(kod, 0, ki.getvalue())
        self.assertEqual(self.generalasok(), n_gen)
        sor = self.tabla.tabla("szoveg")
        self.assertEqual((len(sor), sor[0]["aranyhalmaz_verzio"], sor[0]["pontszam"]), (1, "proba-v2", 0.5))
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            ev.main(["qwen35_2b", "proba", "--csak-ertekel", "--kimenet", "x", "--rogzit"])   # a --rogzit szabályai változatlanok

    def test_ujrapontozas_kalibralt_jel_nelkul_nem_veszi_le_a_jelet(self):
        """Az `--rogzit` `--kalibralt` nélkül a már kalibrált (azonos aranyverziójú) sor jelét megtartja; a `--kalibralt-le`
        kifejezetten leveszi; a két kapcsoló együtt nem adható."""
        import contextlib
        import io
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        self.feladat_fajl().write_text(FELADAT.replace("proba-v1", "proba-v2"), encoding="utf-8")        # a K27 jóváhagyása
        self.tabla.rogzit("szoveg", "qwen35_2b", 0.9, "proba-v2", kalibralt=True)

        def fut(*extra):
            ki = io.StringIO()
            with mock.patch.object(ev.config, "load", return_value=self.cfg), contextlib.redirect_stdout(ki):
                return ev.main(["qwen35_2b", "proba", "--csak-ertekel", "--rogzit", *extra]), ki.getvalue()
        kod, kimenet = fut()
        self.assertEqual(kod, 0, kimenet)
        sor = self.tabla.tabla("szoveg")[0]
        self.assertEqual((sor["kalibralt"], sor["pontszam"]), (1, 0.5))          # az új pontszám, a jel megmaradt
        self.assertEqual(self.tabla.kalibralt_sorrend("szoveg")[0]["pontszam"], 0.5)
        kod, _ = fut("--kalibralt-le")
        self.assertEqual(kod, 0)
        self.assertEqual(self.tabla.tabla("szoveg")[0]["kalibralt"], 0)
        self.assertEqual(self.tabla.kalibralt_sorrend("szoveg"), [])
        kod, _ = fut("--kalibralt")
        self.assertEqual((kod, self.tabla.tabla("szoveg")[0]["kalibralt"]), (0, 1))
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            fut("--kalibralt", "--kalibralt-le")

    def test_beallitas_valtozasa_utan_ujramer_es_csak_az_uj_sorokat_ertekeli(self):
        """C18.1: a folytatás a verzió ÉS a kérés-ujjlenyomat szerint; a régi sorok a fájlban maradnak."""
        out = ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        rek = [json.loads(s) for s in out.read_text().splitlines()]
        self.assertEqual(rek[0]["keres_beallitas"], {"tipus": "chat", "max_tokens": 100, "temperature": 0.0,
                                                     "gondolkodas": False})          # a regiszterből (qwen35_*)
        ert = ev.ertekel(self.cfg, "qwen35_2b", "proba")
        self.assertEqual((ert["n"], ert["ervenyes"], ert["ervenyesseg"]["levagott"]), (4, True, 0))
        uj = {"repetition_penalty": 1.1, "repetition_context_size": 64}
        n_gen = len(AlHatter.beallitasok)
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None, felulir=uj)
        self.assertEqual(len(AlHatter.beallitasok) - n_gen, 4)                      # mind újramérve
        self.assertEqual((AlHatter.beallitasok[-1]["repetition_penalty"],
                          AlHatter.beallitasok[-1]["repetition_context_size"]), (1.1, 64))   # a worker átadja
        self.assertEqual(len(out.read_text().splitlines()), 8)
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba", felulir=uj)["n"], 4)
        self.cfg.data.setdefault("meres", {})["feladat"] = {"proba": {"max_tokens_szorzo": 2}}   # a regiszter is
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba")["n"], 0)
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba")["ervenyesseg"]["hianyzo"], 4)

    def test_a_sor_es_az_ertekeles_a_csucsmemoriat_es_a_betoltest_hordozza(self):
        """T045 (C29.8, a K28 előfeltétele): a sor a worker mérését (csúcs GB, betöltés ténye és ideje), az értékelés `futas`-a a
        maximumot; a `--rogzit` figyelmeztet, ha a mért csúcs meghaladja a regiszterbelit."""
        out = ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        rek = [json.loads(s) for s in out.read_text().splitlines()]
        self.assertEqual([r["memoria"]["csucs_gb"] for r in rek], [3.5] * 4)               # ma: a sorban nincs memoria
        self.assertEqual([r["memoria"]["betoltve"] for r in rek], [True, False, False, False])
        ert = ev.ertekel(self.cfg, "qwen35_2b", "proba")
        f = ert["futas"]
        self.assertEqual((f["csucs_gb_max"], f["betoltesek"], f["regiszter_csucs_gb"]), (3.5, 1, 2.7))
        self.assertGreaterEqual(f["betoltes_mp_ossz"], 0.0)
        fig = ev.csucs_figyelmeztetes(self.cfg, ert)                                         # 3,5 > 2,7 + 0,2
        self.assertIn("3.5", fig)
        self.assertIn("2.7", fig)
        sor = ev.rogzit(self.cfg, ert, kalibralt=False)
        self.assertIn("csúcs", sor["megjegyzes"])
        ok = json.loads(json.dumps(ert))
        ok["futas"]["csucs_gb_max"] = 2.85                                                   # a tűréshatáron belül (+0,2 GB)
        self.assertIsNone(ev.csucs_figyelmeztetes(self.cfg, ok))
        ok["futas"]["csucs_gb_max"] = None                                                   # nem mérhető háttér
        self.assertIsNone(ev.csucs_figyelmeztetes(self.cfg, ok))
        regi = {k: v for k, v in ert.items() if k != "futas"}                                # a mérés előtti értékelés
        self.assertIsNone(ev.csucs_figyelmeztetes(self.cfg, regi))

    def test_levagott_futas_ervenytelen_es_nem_kalibralhato(self):
        """C18.1: a levágott futás `ervenyes: false`; a --rogzit csak naplósort ír, a --kalibralt hibát ad."""
        f = self.cfg.path("modulok") / "eval" / "proba" / "feladat.py"
        f.write_text(FELADAT.replace('"max_tokens": 100', '"max_tokens": 8'), encoding="utf-8")   # az álháttér 64-et ad
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        ert = ev.ertekel(self.cfg, "qwen35_2b", "proba")
        self.assertEqual((ert["ervenyes"], ert["ervenyesseg"]["levagott"], ert["pontszam"]), (False, 4, 0.5))
        sor = ev.rogzit(self.cfg, ert, kalibralt=False)
        self.assertEqual(sor["ervenyes"], 0)
        self.assertTrue(sor["megjegyzes"].startswith("érvénytelen (C18.1): ÉRVÉNYTELEN: levágott 4/4"))
        self.assertEqual(self.tabla.tabla("szoveg"), [])
        with self.assertRaisesRegex(ValueError, "kalibrált"):
            ev.rogzit(self.cfg, ert, kalibralt=True)

    def test_rogzites_csak_teljes_halmazon(self):
        """C19 (T050): a `--limit`-es vagy tételválasztásos értékelés nem kerülhet a kalibrációs táblába, a CLI sem engedi."""
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        reszleges = ev.ertekel(self.cfg, "qwen35_2b", "proba", limit=2)
        self.assertEqual((reszleges["ervenyes"], reszleges["teljes"], reszleges["tetelszam"]), (True, False, 4))
        with self.assertRaisesRegex(ValueError, "teljes"):
            ev.rogzit(self.cfg, reszleges, kalibralt=False)
        self.assertEqual(self.tabla.tabla("szoveg"), [])
        self.assertTrue(ev.ertekel(self.cfg, "qwen35_2b", "proba")["teljes"])
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            ev.main(["qwen35_2b", "proba", "--limit", "2", "--rogzit", "--csak-ertekel"])

    def test_kalibralt_jel_vazlat_verziora_hiba(self):
        """C19 (T050): `-vazlat` aranyhalmazon mért sor nem kaphat kalibrált jelet (sem a CLI-n, sem a táblában)."""
        self.feladat_fajl().write_text(FELADAT.replace("proba-v1", "proba-v1-vazlat"), encoding="utf-8")
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        ert = ev.ertekel(self.cfg, "qwen35_2b", "proba")
        with self.assertRaisesRegex(ValueError, "vázlat"):
            ev.rogzit(self.cfg, ert, kalibralt=True)
        self.assertEqual(ev.rogzit(self.cfg, ert, kalibralt=False)["kalibralt"], 0)       # jel nélkül rögzíthető
        with self.assertRaisesRegex(ValueError, "vázlat"):
            self.tabla.rogzit("szoveg", "qwen35_2b", 0.9, "proba-v1-vazlat", kalibralt=True)

    def test_a_router_csak_az_aktualis_halmazverzio_kalibralt_sorat_fogadja_el(self):
        """C19 (T050): a worker routere a kalibrált sort csak az aranyhalmaz aktuális verziójával fogadja el."""
        from core.modell import halmaz
        ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None)
        ev.rogzit(self.cfg, ev.ertekel(self.cfg, "qwen35_2b", "proba"), kalibralt=True)
        verziok = halmaz.Verziok(self.cfg.path("modulok"))
        self.assertEqual(verziok("szoveg"), "proba-v1")
        self.assertIsNone(verziok("osztalyozas"))                                         # nincs aranyhalmaza
        r = Router(self.b, self.tabla, verziok=verziok)
        self.assertEqual(r.valaszt("szoveg", 5.0).modell.nev, "qwen35_2b")
        self.feladat_fajl().write_text(FELADAT.replace("proba-v1", "proba-v2"), encoding="utf-8")
        from core.modell.router import RoutingHiba
        with self.assertRaisesRegex(RoutingHiba, "aktuális"):
            r.valaszt("szoveg", 5.0)
        self.assertIsNotNone(gazda := Gazda(self.b, al_betolto(self.b), AlAktivitas(), self.tabla,
                                            verziok=verziok, tick_mp=0.02, naplo=lambda s: None))
        self.addCleanup(gazda.utemezo.leall)
        self.assertIs(gazda.router.verziok, verziok)

    def test_kimenet_es_tetelvalasztas(self):
        ki = self.cfg.path("tmp") / "eval-proba"
        out = ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None, kimenet=ki, tetel_idk=["t3", "t1"])
        self.assertEqual(out, ki / "qwen35_2b" / "proba.jsonl")
        self.assertEqual([json.loads(s)["id"] for s in out.read_text().splitlines()], ["t1", "t3"])
        self.assertFalse((self.cfg.path("runs") / "eval" / "qwen35_2b" / "proba.jsonl").exists())
        self.assertEqual(ev.ertekel(self.cfg, "qwen35_2b", "proba", kimenet=ki, tetel_idk=["t1", "t3"])["n"], 2)
        with self.assertRaisesRegex(ValueError, "ismeretlen tétel"):
            ev.futtat(self.cfg, "qwen35_2b", "proba", self.u, log=lambda s: None, tetel_idk=["nincs"])

    def test_cli_a_proba_kapcsolok_mellett_nem_rogzit(self):
        for extra in (["--kimenet", "x"], ["--beallit", "repetition_penalty=1.1"], ["--tetel", "t1"]):
            with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                ev.main(["qwen35_2b", "proba", "--rogzit", *extra])
        self.assertEqual(ev._beallit(["repetition_penalty=1.1", "gondolkodas=false"]),
                         {"repetition_penalty": 1.1, "gondolkodas": False})
        with self.assertRaisesRegex(ValueError, "KULCS=ÉRTÉK"):
            ev._beallit(["max_token=5"])

    def test_hianyzo_feladat(self):
        with self.assertRaisesRegex(FileNotFoundError, "C18"):
            ev.feladat_modul(self.cfg, "nincs")


class KeresBeallitasTest(unittest.TestCase):
    """C18.1: a mérés kérés-beállítása a regiszterből (feladat-alap < modell < modell.feladat < --beallit)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.keres = {"messages": [{"role": "user", "content": "x"}], "max_tokens": 1200}

    def test_a_valodi_regiszter_gondolkodo_modelljei(self):
        b = B.betolt(self.cfg, {})
        gondolkodo = sorted(n for n, m in b.modellek.items() if m.gondolkodo)
        self.assertEqual(gondolkodo, ["ministral3_3b_reasoning", "ministral3_8b_reasoning",
                                      "qwen3_4b_thinking_2507", "seed_coder_8b_reasoning"])      # K231: a lassú gondolkodók kivezetve
        k = ev.keres_beallitas(b, b.modell("qwen3_4b_thinking_2507"), "kod", self.keres)
        # kod: 1200 + 3000 gondolkodási token (a C36b kattintásra válaszolás kerete)
        self.assertEqual((k["max_tokens"], k["temperature"], "gondolkodas" in k), (4200, 0.0, False))
        self.assertNotIn("ocr_kezi", b.modell("paddleocr_vl_16").feladat)               # K32: több képet nem fogad
        for nev in ("qwen35_9b", "qwen35_4b", "qwen35_2b", "qwen35_08b"):
            self.assertIs(ev.keres_beallitas(b, b.modell(nev), "szoveg", self.keres)["gondolkodas"], False)
        self.assertEqual(b.meres["ervenyes_kuszob"], 0.10)
        self.assertEqual(ev.keres_beallitas(b, b.modell("bge_m3"), "beagyazas", {"tipus": "embed", "input": ["a"]}),
                         {"tipus": "embed", "input": ["a"]})                      # nem chat: érintetlen

    def test_feloldasi_sorrend_es_ismeretlen_kulcs(self):
        self.cfg.data["meres"] = {"feladat": {"ocr_kezi": {"repetition_penalty": 1.05, "temperature": 0.0}}}
        self.cfg.data["modellek"]["glm_ocr"]["max_tokens_szorzo"] = 2
        self.cfg.data["modellek"]["glm_ocr"]["meres"] = {"ocr_kezi": {"repetition_penalty": 1.2}}
        b = B.betolt(self.cfg, {})
        m = b.modell("glm_ocr")
        k = ev.keres_beallitas(b, m, "ocr_kezi", self.keres)
        self.assertEqual((k["max_tokens"], k["repetition_penalty"]), (2400, 1.2))
        k = ev.keres_beallitas(b, m, "ocr_kezi", self.keres, {"repetition_penalty": 1.1, "repetition_context_size": 64})
        self.assertEqual((k["repetition_penalty"], k["repetition_context_size"]), (1.1, 64))
        self.assertNotIn("repetition_penalty", ev.keres_beallitas(b, m, "ocr_keplet", self.keres))
        self.assertNotEqual(ev.ujjlenyomat(m, k), ev.ujjlenyomat(m, ev.keres_beallitas(b, m, "ocr_kezi", self.keres)))
        with self.assertRaisesRegex(ValueError, "ismeretlen mérés-kulcs"):
            ev.keres_beallitas(b, m, "ocr_kezi", self.keres, {"top_p": 0.9})
        self.cfg.data["modellek"]["glm_ocr"]["meres"] = {"ocr_kezi": {"top_p": 0.9}}
        with self.assertRaisesRegex(ValueError, "ismeretlen mérés-kulcs"):
            B.betolt(self.cfg, {})


class UjjlenyomatKepTest(unittest.TestCase):
    """T046 (C29.8): a kérés ujjlenyomata a képek TARTALOM-hash-ét hordozza (az út nem számít); a szöveges kérés ujjlenyomata a régi alak."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.m = B.betolt(self.cfg, {}).modell("qwen35_2b")
        self.mappa = Path(self._t.name)
        self.keres = {"messages": [{"role": "user", "content": "x"}], "max_tokens": 100}

    def kep(self, nev: str, tartalom: bytes) -> str:
        p = self.mappa / nev
        p.write_bytes(tartalom)
        return str(p)

    def test_kep_tartalma_szamit_az_utja_nem(self):
        a, b = self.kep("a.jpg", b"AAAA"), self.kep("b.jpg", b"AAAA")
        c = self.kep("c.jpg", b"AAAB")
        k = lambda *u: {**self.keres, "images": list(u)}                     # noqa: E731
        self.assertEqual(ev.ujjlenyomat(self.m, k(a)), ev.ujjlenyomat(self.m, k(b)))
        self.assertNotEqual(ev.ujjlenyomat(self.m, k(a)), ev.ujjlenyomat(self.m, k(c)))       # ma: a kép nem számít
        self.assertNotEqual(ev.ujjlenyomat(self.m, k(a, c)), ev.ujjlenyomat(self.m, k(c, a)))     # a sorrend igen
        (self.mappa / "a.jpg").write_bytes(b"MAS")                                              # ugyanaz az út, más tartalom
        self.assertNotEqual(ev.ujjlenyomat(self.m, k(a)), ev.ujjlenyomat(self.m, k(b)))

    def test_szoveges_keres_ujjlenyomata_valtozatlan_es_hianyzo_kep_hiba(self):
        regi = hashlib.sha256(json.dumps({"repo": self.m.repo, "keres": self.keres}, ensure_ascii=False,
                                         sort_keys=True).encode("utf-8")).hexdigest()[:16]
        self.assertEqual(ev.ujjlenyomat(self.m, self.keres), regi)                  # a szöveges feladatok sorai érvényesek maradnak
        self.assertEqual(ev.ujjlenyomat(self.m, {**self.keres, "images": []}), regi)
        with self.assertRaisesRegex(FileNotFoundError, "kép"):
            ev.ujjlenyomat(self.m, {**self.keres, "images": [str(self.mappa / "nincs.jpg")]})


class BenchTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)

    def test_gyermek_a_betoltovel_mer(self):
        b = beallitas(self.cfg)
        csucs = {"v": 0.0}
        par = {"ablak_szoveg": "videó", "jegyzet_cim": "Jegyzet", "jegyzet_reszlet": "részlet", "y": 1}
        with mock.patch.dict(os.environ, {"MOS_ROOT": str(self.root)}):
            bt = al_betolto(b)
            r = bench.gyermek("qwen3_vl_4b", par, "/al/kep.jpg", 50, None, None, None, betolto=bt,
                              csucs=(lambda: csucs.update(v=0.0), lambda: 4.02, lambda: 3.1))
        self.assertEqual((r["csucs_memoria_gb"], r["memoria_betoltes_utan_gb"], r["szoveg"]["vart"]), (4.02, 3.1, "igen"))
        self.assertIn("kep", r)
        self.assertIsNone(bt.modell)                                       # a mérés után kiürít
        self.assertEqual(bt.zar.tartalom(), "")

    def test_minta_par_es_keretellenorzes(self):
        d = self.cfg.path("state") / "Manifold-media" / "itelet"
        d.mkdir(parents=True)
        (d / "n_kotes_minta.json").write_text(json.dumps([{"ablak_szoveg": "a", "jegyzet_cim": "c",
                                                           "jegyzet_reszlet": "r"}]), encoding="utf-8")
        (d / "n_cimkek.json").write_text(json.dumps({"cimkek": [0]}), encoding="utf-8")
        self.assertEqual(bench.minta_par(self.cfg)["y"], 0)
        self.assertIsNone(bench.kep_elokeszit(self.cfg))                   # az álvaultban nincs fotó
        with self.assertRaises(B.RegiszterHiba):
            bench.futtat(self.cfg, ["nincs_ilyen"], log=lambda s: None)


class RegiszterTest(unittest.TestCase):
    def test_a_letoltesi_lista_es_a_regiszter_egyezik(self):
        with open(REPO / "config" / "letoltes.toml", "rb") as f:
            letoltes = tomllib.load(f)["modell"]
        with open(REPO / "config" / "os.toml", "rb") as f:
            reg = tomllib.load(f)["modellek"]
        self.assertEqual(list(letoltes), list(reg))
        for n, m in letoltes.items():
            r = reg[n]
            self.assertEqual((r["repo"], r.get("minta"), r["csucs_gb"], r["futtato"], bool(r.get("konvertalas"))),
                             (m["repo"], m.get("minta"), m["csucs_gb"], m["futtato"], bool(m.get("konvertalas"))), n)
            self.assertEqual(bool(r.get("csucs_mert")), bool(m.get("csucs_mert")), n)
            self.assertEqual(r.get("revizio"), m.get("revizio"), n)                    # C19 (T141): ugyanaz a rögzített commit

    def test_a_betolto_ertekei_a_legacyei(self):
        with open(REPO / "config" / "os.toml", "rb") as f:
            d = tomllib.load(f)
        g = d["modellgazda"]
        self.assertEqual((g["cache_gb"], g["prefill_lepes"], g["min_szabad_szazalek"], g["tartalek_szazalek"],
                          g["helyreallas_mp"], g["tetlen_urites_perc"]), (0.25, 256, 20, 5, 30, 10))   # L31
        self.assertEqual((d["keret"]["munka"], d["keret"]["tavol"]), (5.0, 9.0))                        # L24
        self.assertEqual({k: v["csucs_gb"] for k, v in d["modellek"].items() if v.get("csucs_mert")},
                         {"qwen35_9b": 7.3, "gemma4_12b": 8.5, "qwen3_vl_4b": 4.6})   # L31; K80 (2026-10-07): a 12B és a 4B a 2.0 mérése


class CliTest(unittest.TestCase):
    def test_models_pull_lista_es_list_halozat_nelkul(self):
        env = {**os.environ, "MOS_PYTHON": sys.executable, "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9"}
        p = subprocess.run([str(REPO / "bin" / "mos"), "models", "pull", "--lista", "opcionalis"], capture_output=True,
                           text=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("összesen", p.stdout)
        with tmpdir() as t:
            _, root, _ = alg_core(t)
            p = subprocess.run([str(REPO / "bin" / "mos"), "router", "tabla"], capture_output=True, text=True,
                               env={**env, "MOS_CONFIG": str(root / "config" / "os.toml"),
                                    "MOS_VAR": str(root / "var")}, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("üres", p.stdout)

    def test_models_list_jeloli_az_ervenytelen_vazlat_es_a_regiszteren_kivuli_sorokat(self):
        """Lelet 10: a `bin/mos models list` az érvénytelen és a `-vazlat` verziójú sort nem mutatja valódi pontként, a
        regiszterből kivett modell sorát jelzi."""
        import contextlib
        import io
        from core.modell import __main__ as mm
        from core.modell import kalibracio
        self.assertEqual(mm.kalibracio_jelzes({"feladat": "szoveg", "pontszam": 0.8, "kalibralt": 1, "ervenyes": 1,
                                               "aranyhalmaz_verzio": "v2"}), "szoveg:0.8✓")
        self.assertEqual(mm.kalibracio_jelzes({"feladat": "kviz", "pontszam": 0.5, "kalibralt": 0, "ervenyes": 1,
                                               "aranyhalmaz_verzio": "v1-vazlat"}), "kviz:0.5[vázlat]")
        self.assertEqual(mm.kalibracio_jelzes({"feladat": "kod", "pontszam": 0.4, "kalibralt": 1, "ervenyes": 0,
                                               "aranyhalmaz_verzio": "v1"}), "kod:0.4[érvénytelen]")     # a ✓ sem jár neki
        with tmpdir() as t:
            cfg, _, _ = alg_core(t)
            tabla = kalibracio.Tabla(cfg.path("router_db"))
            tabla.rogzit("szoveg", "qwen35_4b", 0.7, "v2", kalibralt=True)
            tabla.rogzit("kviz", "qwen35_4b", 0.5, "v1-vazlat")
            tabla.rogzit("matek", "phi4_mini_reasoning", 0.6, "v1", kalibralt=True)          # K231: kikerült a regiszterből
            tabla.close()
            ki = io.StringIO()
            with mock.patch.object(mm.config, "load", return_value=cfg), contextlib.redirect_stdout(ki):
                self.assertEqual(mm.lista([]), 0)
        sorok = {s.split()[0]: s for s in ki.getvalue().splitlines() if s.split()[:1]}
        self.assertIn("szoveg:0.7✓", sorok["qwen35_4b"])
        self.assertIn("kviz:0.5[vázlat]", sorok["qwen35_4b"])
        self.assertIn("[nincs a regiszterben]", sorok["phi4_mini_reasoning"])
        self.assertIn("matek:0.6✓", sorok["phi4_mini_reasoning"])


if __name__ == "__main__":
    unittest.main()
