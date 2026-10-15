"""A napi terv a dolgozatig (C28a): determinisztikus, a hiány arányában, csökkenő hozammal (`hₜ / (1 + kₜ)`)."""
import unittest
from datetime import date

from core.felkeszultseg import terv
from core.felkeszultseg.keplet import Beallitas
from core.felkeszultseg.terv import Tema

B = Beallitas()
MA = date(2026, 10, 1)


def terv_(temak, dolgozat=date(2026, 10, 5), ma=MA, **kw):
    return terv.napi_terv(temak, ma, dolgozat, B, **{"napi_perc": 45, "szelet_perc": 15, "max_nap": 21, **kw})


def osszes(t):
    ki = {}
    for n in t.napok:
        for sz in n.szeletek:
            ki[sz.tema_ut] = ki.get(sz.tema_ut, 0) + sz.perc
    return ki


class NapokTest(unittest.TestCase):
    def test_ma_tol_a_dolgozat_elotti_napig_a_dolgozat_napja_nelkul(self):
        t = terv_([Tema("a", "A", 0.3)])
        self.assertEqual([n.nap for n in t.napok], ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"])
        self.assertIsNone(t.uzenet)

    def test_dolgozat_ma_vagy_lezart_nincs_terv(self):
        t = terv_([Tema("a", "A", 0.3)], dolgozat=MA)
        self.assertEqual((t.napok, t.uzenet), ([], "A dolgozat ma van."))
        t = terv_([Tema("a", "A", 0.3)], dolgozat=date(2026, 9, 30))
        self.assertEqual((t.napok, t.uzenet), ([], "A dolgozat már lezárult."))

    def test_max_nap_a_dolgozat_elotti_napokra_vag(self):
        t = terv_([Tema("a", "A", 0.3)], dolgozat=date(2026, 11, 20), max_nap=3)
        self.assertEqual([n.nap for n in t.napok], ["2026-11-17", "2026-11-18", "2026-11-19"])
        self.assertIn("3", t.uzenet)

    def test_nincs_tema(self):
        t = terv_([])
        self.assertEqual(t.napok, [])
        self.assertIn("téma", t.uzenet)


class KiosztasTest(unittest.TestCase):
    def test_a_szeletek_osszege_a_napi_koltsegvetes(self):
        t = terv_([Tema("a", "A", 0.2), Tema("b", "B", 0.5), Tema("c", "C", None)])
        self.assertEqual([n.perc for n in t.napok], [45, 45, 45, 45])
        self.assertEqual(sum(osszes(t).values()), 180)

    def test_hiany_aranyos_csokkeno_hozammal(self):
        # cél 0,85: A hiánya 0,8, B-é 0,4 → 6 szeleten 4 : 2
        t = terv_([Tema("a", "A", 0.05), Tema("b", "B", 0.45)], dolgozat=date(2026, 10, 3))
        self.assertEqual(osszes(t), {"a": 60, "b": 30})

    def test_tanulatlan_tema_teljes_hianyt_kap(self):
        t = terv_([Tema("a", "A", 0.84), Tema("b", "B", None)], dolgozat=date(2026, 10, 2))
        ossz = osszes(t)
        self.assertGreater(ossz["b"], ossz.get("a", 0))

    def test_a_cel_folotti_tema_nem_kap_idot_ha_van_hianyos(self):
        t = terv_([Tema("a", "A", 0.95), Tema("b", "B", 0.3)])
        self.assertNotIn("a", osszes(t))

    def test_naponta_temankent_csoportositva_es_a_gyenge_tobbszor_jon(self):
        t = terv_([Tema("a", "A", 0.05), Tema("b", "B", 0.45)], dolgozat=date(2026, 10, 3))
        self.assertEqual(len(t.napok), 2)
        for n in t.napok:
            self.assertEqual(len({sz.tema_ut for sz in n.szeletek}), len(n.szeletek))     # témánként egy sor
        self.assertTrue(all(any(sz.tema_ut == "a" for sz in n.szeletek) for n in t.napok))

    def test_dontetlen_alacsonyabb_szam_majd_nev(self):
        t1 = terv_([Tema("a", "A", 0.5), Tema("b", "B", 0.5)], dolgozat=date(2026, 10, 2))
        t2 = terv_([Tema("b", "B", 0.5), Tema("a", "A", 0.5)], dolgozat=date(2026, 10, 2))
        self.assertEqual(t1, t2)                                   # a bemenet sorrendje nem számít
        self.assertEqual(t1.napok[0].szeletek[0].tema_ut, "a")

    def test_determinisztikus(self):
        temak = [Tema("a", "A", 0.2), Tema("b", "B", 0.5), Tema("c", "C", None)]
        self.assertEqual(terv_(temak), terv_(temak))

    def test_a_szelet_oka_a_hianyt_es_a_szamot_mondja(self):
        t = terv_([Tema("a", "A", 0.41), Tema("b", "B", None)], dolgozat=date(2026, 10, 2))
        oka = {sz.tema_ut: sz.ok for n in t.napok for sz in n.szeletek}
        self.assertIn("41%", oka["a"])
        self.assertEqual(oka["b"], "nincs adat")


class AtismetlesTest(unittest.TestCase):
    def test_nincs_hiany_egy_atismetles_az_utolso_napon(self):
        t = terv_([Tema("a", "A", 0.95), Tema("b", "B", 0.9)])
        self.assertEqual([n.nap for n in t.napok if n.szeletek], ["2026-10-04"])
        sz = t.napok[-1].szeletek[0]
        self.assertEqual((sz.tema_ut, sz.perc), (None, 15))
        self.assertIn("Átismétlés", sz.tema)
        self.assertIn("célszint", t.uzenet)


if __name__ == "__main__":
    unittest.main()


class KozosKeretTest(unittest.TestCase):
    def test_tobb_dolgozat_egy_keret_es_mert_adat_nelkul(self):
        vizsgak = [('a', date(2026, 10, 7), [Tema('a.md', 'A', None)]),
                   ('b', date(2026, 10, 9), [Tema('b.md', 'B', 0.2)])]
        ki = terv.kozos_terv(vizsgak, date(2026, 10, 3), B, napi_perc=45, szelet_perc=15, max_nap=21,
                             foglalt={'2026-10-03': 30})
        percek = {}
        for ered in ki.values():
            for n in ered.napok:
                percek[n.nap] = percek.get(n.nap, 0) + n.perc
        self.assertEqual(percek['2026-10-03'], 15)
        self.assertTrue(all(p <= 45 for p in percek.values()))
        self.assertTrue(ki['a'].napok and ki['b'].napok)
        self.assertTrue(all('%' not in s.ok for n in ki['a'].napok for s in n.szeletek))
