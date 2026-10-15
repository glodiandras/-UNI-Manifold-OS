"""A felkészültség képlete (C28a, `docs/C28-TERV.md`): tiszta függvények — kézzel számolt értékek, az újranormálás,
a „mért tudás nélkül nincs szám” szabály, a kilátás, a sávok. I/O nélkül."""
import unittest

from core.felkeszultseg import keplet
from core.felkeszultseg.keplet import Beallitas, TemaJel
from tests.helpers import alg_core, tmpdir

B = Beallitas()


def kozel(t, a, b, hely=6):
    t.assertAlmostEqual(a, b, places=hely)


class OsszetevokTest(unittest.TestCase):
    def test_kartya_atlag_es_bizalom(self):
        sz = keplet.tema_szam(TemaJel(kartya=(0.9, 0.7, 0.8)), B)
        k = {o.nev: o for o in sz.osszetevok}["kartya"]
        kozel(self, k.ertek, 0.8)
        kozel(self, k.bizalom, 3 / 5)
        self.assertEqual(k.adat["db"], 3)

    def test_uj_kartya_nulla_es_szamit(self):
        """Az új (még nem tanult) kártya felidézése 0: a hívó 0-t ad, az átlagba beleszámít."""
        sz = keplet.tema_szam(TemaJel(kartya=(1.0, 1.0, 0.0, 0.0, 0.0), uj_kartya=3), B)
        k = {o.nev: o for o in sz.osszetevok}["kartya"]
        kozel(self, k.ertek, 0.4)
        self.assertEqual(k.adat["uj"], 3)

    def test_kviz_idoben_csokkeno_suly(self):
        # két eredmény: friss 10/10 és a felezési idővel korábbi 0/10 → a régi fele súlyú
        sz = keplet.tema_szam(TemaJel(kviz=((0.0, 10, 10), (B.kviz_felezes_nap, 0, 10))), B)
        q = {o.nev: o for o in sz.osszetevok}["kviz"]
        kozel(self, q.ertek, 10 / (10 + 0.5 * 10))
        kozel(self, q.bizalom, min(1.0, (10 + 5) / B.kviz_n0))

    def test_kviz_osszes_nulla_kihagyva(self):
        sz = keplet.tema_szam(TemaJel(kviz=((0.0, 0, 0),)), B)
        q = {o.nev: o for o in sz.osszetevok}["kviz"]
        self.assertIsNone(q.ertek)
        self.assertEqual(q.bizalom, 0.0)

    def test_frissesseg_felezes(self):
        sz = keplet.tema_szam(TemaJel(kartya=(0.8,) * 5, utolso_tanulas_nap=B.felezes_nap), B)
        f = {o.nev: o for o in sz.osszetevok}["frissesseg"]
        kozel(self, f.ertek, 0.5)
        self.assertEqual(f.bizalom, 1.0)

    def test_frissesseg_jel_nelkul_nincs_bizalom(self):
        sz = keplet.tema_szam(TemaJel(kartya=(0.8,) * 5), B)
        f = {o.nev: o for o in sz.osszetevok}["frissesseg"]
        self.assertIsNone(f.ertek)
        self.assertEqual(f.bizalom, 0.0)

    def test_ido_telit(self):
        sz = keplet.tema_szam(TemaJel(kartya=(0.8,) * 5, tanult_perc=B.cel_perc * 3), B)
        t = {o.nev: o for o in sz.osszetevok}["ido"]
        kozel(self, t.ertek, 1.0)
        sz = keplet.tema_szam(TemaJel(kartya=(0.8,) * 5, tanult_perc=B.cel_perc / 2), B)
        kozel(self, {o.nev: o for o in sz.osszetevok}["ido"].ertek, 0.5)


class SzamTest(unittest.TestCase):
    def test_kezzel_szamolt_pelda(self):
        """6 kártya átlag 0,8 (c=1) · egy 3/4-es friss kvíz (c=0,4) · 3 napja tanult · 40 perc."""
        jel = TemaJel(kartya=(0.8,) * 6, kviz=((0.0, 3, 4),), utolso_tanulas_nap=3, tanult_perc=40)
        sz = keplet.tema_szam(jel, B)
        f, t = 0.5 ** (3 / B.felezes_nap), 40 / B.cel_perc
        szamlalo = B.suly_kartya * 1 * 0.8 + B.suly_kviz * 0.4 * 0.75 + B.suly_frissesseg * f + B.suly_ido * t
        nevezo = B.suly_kartya + B.suly_kviz * 0.4 + B.suly_frissesseg + B.suly_ido
        kozel(self, sz.szam, szamlalo / nevezo)
        self.assertGreater(sz.szam, 0.7)
        self.assertLess(sz.szam, 0.8)
        kozel(self, sz.bizonyitek, nevezo / (B.suly_kartya + B.suly_kviz + B.suly_frissesseg + B.suly_ido))

    def test_csak_kartya_ujranormalas(self):
        """Ami nincs mérve (kvíz, frissesség, idő), az nem húzza le: csak a kártya számít."""
        sz = keplet.tema_szam(TemaJel(kartya=(0.6,) * 5), B)
        kozel(self, sz.szam, 0.6)

    def test_mert_tudas_nelkul_nincs_szam(self):
        """A tanult idő és a frissesség önmagában nem tudás: nincs szám, de az összetevők látszanak."""
        sz = keplet.tema_szam(TemaJel(utolso_tanulas_nap=1, tanult_perc=120), B)
        self.assertIsNone(sz.szam)
        self.assertEqual(sz.ok, "nincs_mert_tudas")
        self.assertEqual({o.nev for o in sz.osszetevok}, {"kartya", "kviz", "frissesseg", "ido"})

    def test_ures_jel_nincs_szam(self):
        sz = keplet.tema_szam(TemaJel(), B)
        self.assertIsNone(sz.szam)
        self.assertEqual(sz.bizonyitek, 0.0)

    def test_kuszob_alatti_kartyaszam_nincs_szam(self):
        """Egyetlen kártya: wK·cK = 0,4·0,2 = 0,08 < 0,15."""
        self.assertIsNone(keplet.tema_szam(TemaJel(kartya=(1.0,)), B).szam)
        self.assertIsNotNone(keplet.tema_szam(TemaJel(kartya=(1.0, 1.0)), B).szam)

    def test_a_proxik_sulya_nem_haladja_meg_a_mertet(self):
        """Két rosszul tudott kártya (c=0,4 → mért súly 0,16) mellé 60 perc és tegnapi tanulás: a proxik súlya 0,25 helyett 0,16."""
        sz = keplet.tema_szam(TemaJel(kartya=(0.2, 0.2), utolso_tanulas_nap=1, tanult_perc=60), B)
        m = B.suly_kartya * 0.4
        skala = m / (B.suly_frissesseg + B.suly_ido)
        f = 0.5 ** (1 / B.felezes_nap)
        vart = (m * 0.2 + skala * B.suly_frissesseg * f + skala * B.suly_ido * 1.0) / (m + skala * (B.suly_frissesseg + B.suly_ido))
        kozel(self, sz.szam, vart)
        self.assertLess(sz.szam, 0.6)                    # a mért 0,2-t a proxik nem emelik „közepesre” (korlát nélkül 0,67 lenne)
        o = {x.nev: x for x in sz.osszetevok}
        kozel(self, o["frissesseg"].bizalom, skala)
        self.assertEqual(o["frissesseg"].adat["korlatozva"], round(skala, 4))

    def test_elegendo_mert_adatnal_a_proxik_nem_korlatozottak(self):
        sz = keplet.tema_szam(TemaJel(kartya=(0.8,) * 6, utolso_tanulas_nap=1, tanult_perc=60), B)
        o = {x.nev: x for x in sz.osszetevok}
        self.assertEqual((o["frissesseg"].bizalom, o["ido"].bizalom), (1.0, 1.0))
        self.assertNotIn("korlatozva", o["ido"].adat)

    def test_a_szam_0_es_1_kozott_marad(self):
        for jel in (TemaJel(kartya=(0.0,) * 9), TemaJel(kartya=(1.0,) * 9, kviz=((0.0, 9, 9),), utolso_tanulas_nap=0,
                                                         tanult_perc=999)):
            sz = keplet.tema_szam(jel, B).szam
            self.assertGreaterEqual(sz, 0.0)
            self.assertLessEqual(sz, 1.0)

    def test_tobb_jo_adat_nem_rontja_monoton(self):
        gyenge = keplet.tema_szam(TemaJel(kartya=(0.5,) * 6), B).szam
        jobb = keplet.tema_szam(TemaJel(kartya=(0.7,) * 6), B).szam
        self.assertGreater(jobb, gyenge)

    def test_suly_a_configbol(self):
        b = Beallitas(suly_kartya=0.0, suly_kviz=1.0, suly_frissesseg=0.0, suly_ido=0.0, min_bizonyitek=0.1)
        sz = keplet.tema_szam(TemaJel(kartya=(0.1,) * 9, kviz=((0.0, 9, 10),)), b)
        kozel(self, sz.szam, 0.9)

    def test_osszetevok_rendje_es_nyers_adat(self):
        sz = keplet.tema_szam(TemaJel(kartya=(0.5, 0.5), kviz=((2.0, 1, 2),), utolso_tanulas_nap=4, tanult_perc=12), B)
        self.assertEqual([o.nev for o in sz.osszetevok], ["kartya", "kviz", "frissesseg", "ido"])
        self.assertEqual([o.suly for o in sz.osszetevok], [B.suly_kartya, B.suly_kviz, B.suly_frissesseg, B.suly_ido])
        self.assertEqual(sz.osszetevok[2].adat["nap"], 4)
        self.assertEqual(sz.osszetevok[3].adat["perc"], 12)


class KilatasTest(unittest.TestCase):
    def test_a_kilatas_a_felidezes_csokkenesevel_nem_nagyobb(self):
        most = keplet.tema_szam(TemaJel(kartya=(0.95,) * 6, utolso_tanulas_nap=1), B).szam
        kilatas = keplet.tema_szam(TemaJel(kartya=(0.7,) * 6, utolso_tanulas_nap=8), B).szam
        self.assertLessEqual(kilatas, most)


class DolgozatSzamTest(unittest.TestCase):
    def test_atlag_a_szammal_rendelkezo_temakon(self):
        ertek, van, ossz = keplet.dolgozat_szam([0.8, None, 0.4])
        kozel(self, ertek, 0.6)
        self.assertEqual((van, ossz), (2, 3))

    def test_egy_tema_sem_szamolt(self):
        self.assertEqual(keplet.dolgozat_szam([None, None]), (None, 0, 2))
        self.assertEqual(keplet.dolgozat_szam([]), (None, 0, 0))

    def test_szintek(self):
        self.assertEqual(keplet.szint(0.80, B), "jo")
        self.assertEqual(keplet.szint(0.7999, B), "kozepes")
        self.assertEqual(keplet.szint(0.60, B), "kozepes")
        self.assertEqual(keplet.szint(0.5999, B), "gyenge")
        self.assertEqual(keplet.szint(None, B), "nincs_adat")


class BeallitasTest(unittest.TestCase):
    def test_az_os_toml_alapertekei(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, _ = alg_core(t.name)
        b = Beallitas.cfg_bol(cfg)
        self.assertEqual(b, Beallitas())            # az os.toml és a kód alapértékei egyeznek
        self.assertFalse(b.kalibralt)

    def test_felulirhato_es_hibas_ertek_az_alapra_esik(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, root, _ = alg_core(t.name)
        szoveg = (root / "config" / "os.toml").read_text(encoding="utf-8")
        szoveg = szoveg.replace("suly_kartya = 0.40", "suly_kartya = 0.5").replace("cel = 0.85", 'cel = "sok"')
        (root / "config" / "os.toml").write_text(szoveg, encoding="utf-8")
        from core import config
        cfg2 = config.load({"MOS_ROOT": str(root), "HOME": str(root.parent / "home")})
        b = Beallitas.cfg_bol(cfg2)
        self.assertEqual(b.suly_kartya, 0.5)
        self.assertEqual(b.cel, Beallitas().cel)


if __name__ == "__main__":
    unittest.main()
