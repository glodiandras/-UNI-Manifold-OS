"""A v2 kísérő-előtag (`ATTCHMNTS - `, `v2-kompat` preset) a döntésekben és a hasonló jegyzetekben: az F3 előtt a
`tests/test_automatika.py`, `test_grafikon_automatika.py`, `test_osszefoglalas_automatika.py` és `test_kereses_hasonlo.py`
tesztjei, itt a presetre kifejezetten kérve. (A semleges alap — `Manifold - ` — tesztje: `tests/test_alapertekek_semleges.py`.)"""
import unittest
from unittest import mock

from core import automatika as A
from core.index.hibrid import hasonlo
from tests import test_automatika as TA
from tests import test_grafikon_automatika as TG
from tests import test_kereses_hasonlo as TH
from tests import test_osszefoglalas_automatika as TO
from tests.preset_v2 import V2_ELOTAG, alg_core_v2, csak_sajat, v2_cfg


class ElotagTest(unittest.TestCase):
    def test_a_preset_elotagja(self):
        self.assertEqual(A.kisero_elotag(v2_cfg()), V2_ELOTAG)
        for ut in ("ATTCHMNTS - cards/x.md", "T01/ATTCHMNTS - quizes/x.md", "M/ATTCHMNTS - summaries/x.md"):
            self.assertFalse(A.tartalmi_ut(ut, V2_ELOTAG), ut)
        self.assertTrue(A.tartalmi_ut("M/a.md", V2_ELOTAG))


@csak_sajat
class DontesV2(TA.DontesTest):
    """Áthelyezve a `tests/test_automatika.py` `DontesTest.test_sorrend`-jéből."""

    def test_sorrend(self):
        self.assertEqual(A.dont(self.F, "ATTCHMNTS - cards/x.md", "h", 0, 1e6, None, lambda u: "", V2_ELOTAG)[0], "szuro")
        self.assertEqual(self.dont({"tiltva": "x"})[0], "tiltva")
        self.assertEqual(self.dont({"hash": TA.h(TA.SZOVEG)})[0], "elbiralt")
        self.assertEqual(self.dont(mtime=9_500.0)[0], "csend")                   # 10 percen belül változott
        self.assertEqual(self.dont()[1].ok, "uj")
        self.assertEqual(self.dont(md="Rövid.")[0], "rovid")
        alap = {"alap": __import__("json").dumps(sorted(A.mondatok(TA.SZOVEG))), "ujjlenyomat": "x"}
        self.assertEqual(self.dont(alap, md=TA.SZOVEG + "\n\nEgy új mondat itt.")[0], "nem_eleg")
        kesz = {**alap, "ujjlenyomat": A.forras_ujjlenyomat(TA.SZOVEG)}
        self.assertEqual(self.dont(kesz)[0], "mar_kesz")


@csak_sajat
class GrafikonDontesV2(TG.Dontes):
    """Áthelyezve a `tests/test_grafikon_automatika.py` `Dontes.test_sorrend_es_kizarasok`-ából (a preset elotagjával)."""

    def dont(self, md=TG.FM + TG.SZOVEG, sor=None, mtime=0.0, most=TG.CSEND, ut=TG.UT, hash_="uj"):
        return TG.OA.dont(self.f, ut, hash_, mtime, most, sor, lambda u: md, TG.OA.kisero_elotag(self.cfg))

    def test_sorrend_es_kizarasok(self):
        self.assertEqual(TG.OA.kisero_elotag(self.cfg), V2_ELOTAG)
        for kw, st in (({"ut": "T01/ATTCHMNTS - cards/X — kártyák.md"}, "szuro"),
                       ({"ut": ".obsidian/x.md"}, "szuro"),
                       ({"md": TG.FM + "# T\n\nCsak szöveg, képlet nélkül, elég hosszan, hogy ne a rövidség döntsön róla.\n"}, "nem_kell"),
                       ({"md": "$y=x$"}, "rovid"),
                       ({"mtime": TG.CSEND - 9 * 60 + 1}, "csend"),
                       ({"sor": {"tiltva": "x"}}, "tiltva")):
            self.assertEqual(self.dont(**kw)[0], st, kw)
        self.assertEqual(self.dont(mtime=TG.CSEND - 10 * 60)[0], "jelolt")


@csak_sajat
class OsszefoglalasDontesV2(TO.Dontes):
    """Áthelyezve a `tests/test_osszefoglalas_automatika.py` `Dontes.test_sorrend_es_kizarasok`-ából: a tiszta döntés (előtag nélküli
    függvény) a preset előtagjával szűr."""

    def setUp(self):
        p = mock.patch.object(TO.AU, "tartalmi_ut", lambda ut: A.tartalmi_ut(ut, V2_ELOTAG))
        p.start()
        self.addCleanup(p.stop)

    def test_sorrend_es_kizarasok(self):
        AU, B, allapot = TO.AU, TO.B, TO.allapot
        self.assertEqual(AU.dont(allapot(kapcsolo_be=False), B).ok, "kapcsolo_ki")
        self.assertEqual(AU.dont(allapot(ut="ATTCHMNTS - cards/X — kártyák.md"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(ut="T/ATTCHMNTS - summaries/X — összefoglaló.md"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(ut="T/jegyzet.canvas"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(ut=".obsidian/x.md"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(tiltva=True), B).ok, "tiltva")
        self.assertEqual(AU.dont(allapot(md="# Rövid\n\nPár szó."), B).ok, "rovid")
        # a kapcsoló mindent megelőz, a csend a változás mértéke előtt jön
        self.assertEqual(AU.dont(allapot(kapcsolo_be=False, tiltva=True, csend_mp=0), B).ok, "kapcsolo_ki")
        self.assertEqual(AU.dont(allapot(csend_mp=0, alap=AU.mondatok(TO.JEGYZET)), B).ok, "meg_valtozik")


@csak_sajat
class HasonloV2(TH.HasonloTest):
    """Áthelyezve a `tests/test_kereses_hasonlo.py` `HasonloTest.test_hasonlok_kiserok_es_onmaga_nelkul`-ából: a `KISERO` jegyzet
    (`ATTCHMNTS - cards/…`) a preset előtagja szerint kimarad."""

    def test_hasonlok_kiserok_es_onmaga_nelkul(self):
        self.assertEqual(A.kisero_elotag(self.cfg), V2_ELOTAG)
        t, b = self.epit()
        hivas = len(b.hivasok)
        r = hasonlo.hasonlok(self.ix._olvaso, t, TH.SPARTA, 3, A.kisero_elotag(self.cfg))
        self.assertEqual((r["allapot"], r["elavult"]), ("ok", False))
        utak = [x["ut"] for x in r["talalatok"]]
        self.assertEqual(utak[0], TH.HADSEREG)
        self.assertNotIn(TH.SPARTA, utak)
        self.assertNotIn(TH.KISERO, utak)
        self.assertLessEqual(len(utak), 3)
        self.assertEqual([x["pont"] for x in r["talalatok"]], sorted((x["pont"] for x in r["talalatok"]), reverse=True))
        elso = r["talalatok"][0]
        self.assertEqual((elso["kimeno"], elso["bejovo"]), (False, True))      # a hadsereg-jegyzet linkeli a Spártát
        self.assertEqual(len(b.hivasok), hivas)                                 # a lekérdezés modellt nem hív


if __name__ == "__main__":
    unittest.main()
