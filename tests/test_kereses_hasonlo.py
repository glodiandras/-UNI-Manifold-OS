"""C25c: a hasonló jegyzetek a vektortárból, modell nélkül (`core/index/hibrid/hasonlo.py`, `Vektortar.jegyzet_hasonlosag`,
`GET /api/kereses/hasonlo`, `POST /api/kereses/hasonlosag`). Álvaulton, álbeágyazóval épített tárral; a lekérdezés a
beágyazót nem hívja."""
import unittest

from core import kereses_api
from core.index.hibrid import frissites, hasonlo, vektortar
from core.vaultio import Invalid, NotFound
from tests.helpers import ir, tmpdir
from tests.hibrid_segedek import FAJLOK, FM, AlBeagyazo
from tests.index_segedek import alvault, index_indit

SPARTA = "T02 - Hellász/Elmélet/07 - Spárta.md"
HADSEREG = "T02 - Hellász/Elmélet/09 - Spárta hadserege.md"
KISERO = "ATTCHMNTS - cards/07 - Spárta — kártyák.md"
ATHEN = "T02 - Hellász/Elmélet/08 - Athén.md"

SAJAT = {
    **FAJLOK,
    HADSEREG: FM + "# Spárta hadserege\nA spártai hopliták falanxban harcoltak; a fiúkat hétévesen katonának nevelték. "
                   "[[07 - Spárta]]\n",
    KISERO: "A spártai nevelés kemény volt: a fiúkat hétévesen elvették a családtól.\n",
}


class _AlApp:
    def __init__(self, cfg, index):
        self.cfg, self.index = cfg, index


class HasonloTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, SAJAT)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)

    def epit(self):
        b = AlBeagyazo()
        t = vektortar.Vektortar(kereses_api.tar_ut(self.cfg))
        self.addCleanup(t.close)
        frissites.frissit(self.ix._olvaso, t, b)
        return t, b

    def test_tar_nelkul_kimondja(self):
        r = hasonlo.hasonlok(self.ix._olvaso, None, SPARTA)
        self.assertEqual((r["allapot"], r["talalatok"]), ("nincs_tar", []))
        sz = kereses_api.szolgalat(_AlApp(self.cfg, self.ix))
        self.assertIsNone(sz.tar())                         # a fájl hiánya nem hiba, és a tárat nem hozza létre
        self.assertFalse(kereses_api.tar_ut(self.cfg).exists())

    def test_hasonlok_kiserok_es_onmaga_nelkul(self):
        t, b = self.epit()
        hivas = len(b.hivasok)
        r = hasonlo.hasonlok(self.ix._olvaso, t, SPARTA, 3)
        self.assertEqual((r["allapot"], r["elavult"]), ("ok", False))
        utak = [x["ut"] for x in r["talalatok"]]
        self.assertEqual(utak[0], HADSEREG)
        self.assertNotIn(SPARTA, utak)
        self.assertNotIn(KISERO, utak)
        self.assertLessEqual(len(utak), 3)
        self.assertEqual([x["pont"] for x in r["talalatok"]], sorted((x["pont"] for x in r["talalatok"]), reverse=True))
        elso = r["talalatok"][0]
        self.assertEqual((elso["kimeno"], elso["bejovo"]), (False, True))      # a hadsereg-jegyzet linkeli a Spártát
        self.assertEqual(len(b.hivasok), hivas)                                 # a lekérdezés modellt nem hív

    def test_vektor_nelkuli_es_elavult_jegyzet(self):
        t, _ = self.epit()
        ir(self.v, "Uj.md", "# Új\nmég nincs vektora\n")
        self.assertTrue(self.ix.frissit(["Uj.md"]))
        self.assertEqual(hasonlo.hasonlok(self.ix._olvaso, t, "Uj.md")["allapot"], "nincs_vektor")
        ir(self.v, SPARTA, FAJLOK[SPARTA] + "\nÚj bekezdés.\n")
        self.assertTrue(self.ix.frissit([SPARTA]))
        r = hasonlo.hasonlok(self.ix._olvaso, t, SPARTA)
        self.assertEqual((r["allapot"], r["elavult"]), ("ok", True))

    def test_nem_jegyzet_es_hibak(self):
        t, _ = self.epit()
        ir(self.v, "doc.pdf", b"%PDF", "wb")
        self.assertTrue(self.ix.frissit(["doc.pdf"]))
        self.assertEqual(hasonlo.hasonlok(self.ix._olvaso, t, "doc.pdf")["allapot"], "nem_jegyzet")
        with self.assertRaises(NotFound):
            hasonlo.hasonlok(self.ix._olvaso, t, "nincs.md")
        with self.assertRaises(Invalid):
            hasonlo.hasonlok(self.ix._olvaso, t, "")
        with self.assertRaises(Invalid):
            hasonlo.hasonlosag(self.ix._olvaso, t, SPARTA, "nem lista")
        with self.assertRaises(Invalid):
            hasonlo.hasonlosag(self.ix._olvaso, t, SPARTA, ["x.md"] * (hasonlo.MAX_CEL + 1))

    def test_hasonlosag_a_c30b_nek(self):
        t, _ = self.epit()
        r = hasonlo.hasonlosag(self.ix._olvaso, t, SPARTA, [HADSEREG, ATHEN, "nincs.md"])
        p = r["pontok"]
        self.assertEqual(r["allapot"], "ok")
        self.assertGreater(p[HADSEREG], p[ATHEN])
        self.assertIsNone(p["nincs.md"])
        lista = {x["ut"]: x["pont"] for x in hasonlo.hasonlok(self.ix._olvaso, t, SPARTA, 10)["talalatok"]}
        self.assertEqual(lista[HADSEREG], p[HADSEREG])                         # a két hívás ugyanazt a mértéket adja

    def test_python_motorral_ugyanaz(self):
        t, _ = self.epit()
        tp = vektortar.Vektortar(kereses_api.tar_ut(self.cfg), csak_olvas=True, motor="python")
        self.addCleanup(tp.close)
        a, b = t.jegyzet_hasonlosag(SPARTA), tp.jegyzet_hasonlosag(SPARTA)
        self.assertEqual(set(a), set(b))
        for u in a:
            self.assertAlmostEqual(a[u], b[u], places=4)


if __name__ == "__main__":
    unittest.main()
