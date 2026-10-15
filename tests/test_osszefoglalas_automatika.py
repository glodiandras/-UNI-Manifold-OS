"""C26a: az automatikus mód tiszta döntései (`modulok/osszefoglalas/automatika.py`) — órát, ütemezőt, modellt nem használnak."""
import unittest

from modulok.osszefoglalas import automatika as AU
from tests.test_osszefoglalas_lanc import JEGYZET

UT = "T03 - Az ókori Róma/Elmélet/08 - A polgárháborúk kora és Caesar.md"
CSEND = 11 * 60
B = AU.Beallitas(min_hossz=100)


def allapot(**kw):
    kw = {"ut": UT, "md": JEGYZET, "csend_mp": CSEND, **kw}
    return AU.Allapot(**kw)


class Dontes(unittest.TestCase):
    def test_uj_jegyzet_csend_utan_fut(self):
        d = AU.dont(allapot(), B)
        self.assertTrue(d.fusson)
        self.assertEqual(d.ok, "uj")

    def test_tiz_perc_csend_kell(self):
        self.assertEqual(AU.dont(allapot(csend_mp=9 * 60 + 59), B).ok, "meg_valtozik")
        self.assertTrue(AU.dont(allapot(csend_mp=10 * 60), B).fusson)

    def test_sorrend_es_kizarasok(self):
        self.assertEqual(AU.dont(allapot(kapcsolo_be=False), B).ok, "kapcsolo_ki")
        self.assertEqual(AU.dont(allapot(ut="ATTCHMNTS - cards/X — kártyák.md"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(ut="T/ATTCHMNTS - summaries/X — összefoglaló.md"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(ut="T/jegyzet.canvas"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(ut=".obsidian/x.md"), B).ok, "nem_tartalmi")
        self.assertEqual(AU.dont(allapot(tiltva=True), B).ok, "tiltva")
        self.assertEqual(AU.dont(allapot(md="# Rövid\n\nPár szó."), B).ok, "rovid")
        # a kapcsoló mindent megelőz, a csend a változás mértéke előtt jön
        self.assertEqual(AU.dont(allapot(kapcsolo_be=False, tiltva=True, csend_mp=0), B).ok, "kapcsolo_ki")
        self.assertEqual(AU.dont(allapot(csend_mp=0, alap=AU.mondatok(JEGYZET)), B).ok, "meg_valtozik")

    def test_valtozatlan_vagy_keves_modositas_nem_fut(self):
        alap = AU.mondatok(JEGYZET)
        d = AU.dont(allapot(alap=alap), B)
        self.assertEqual((d.fusson, d.ok), (False, "nem_valtozott_eleg"))
        kicsi = JEGYZET.replace("(Kr. e. 48)", "(Kr. e. 47)")                # egy szám egy mondatban
        d = AU.dont(allapot(md=kicsi, alap=alap), B)
        self.assertFalse(d.fusson)
        self.assertLess(d.valtozas.tavolsag, 0.3)

    def test_erosen_modosult_tavolsag_alapjan(self):
        alap = AU.mondatok(JEGYZET)
        ujra = ("# Más\n\n## Teljesen más\n\nEz a jegyzet teljesen más tartalmú lett, semmi nem maradt az eredeti mondatokból.\n"
                "Az új tartalom hosszabb is, hogy a mondathalmaz távolsága nagy legyen az eredetihez képest, és ez önmagában "
                "elég a döntéshez.\n")
        d = AU.dont(allapot(md=ujra, alap=alap), AU.Beallitas(min_hossz=50, uj_karakter=10000))
        self.assertTrue(d.fusson)
        self.assertEqual(d.ok, "erosen_modosult")
        self.assertGreater(d.valtozas.tavolsag, 0.9)

    def test_erosen_modosult_uj_karakter_alapjan(self):
        alap = AU.mondatok(JEGYZET)
        hosszu_uj = " ".join(f"Új mondat száma {i} a jegyzet végén, hosszan fejtegetve a témát." for i in range(14))
        md = JEGYZET.replace("## Füzet", "## Új rész\n\n" + hosszu_uj + "\n\n## Füzet")
        d = AU.dont(allapot(md=md, alap=alap), AU.Beallitas(min_hossz=100, kuszob=0.99, uj_karakter=600))
        self.assertTrue(d.fusson)
        self.assertGreaterEqual(d.valtozas.uj_karakter, 600)
        self.assertLess(d.valtozas.tavolsag, 0.99)

    def test_mar_kesz_nem_fut_ujra(self):
        uj = allapot(kesz_ujjlenyomat=AU.forras_ujjlenyomat(JEGYZET))
        self.assertEqual(AU.dont(uj, B).ok, "mar_kesz")
        self.assertTrue(AU.dont(allapot(kesz_ujjlenyomat="mas"), B).fusson)

    def test_ujjlenyomat_tartalmi(self):
        a = AU.forras_ujjlenyomat(JEGYZET)
        self.assertEqual(a, AU.forras_ujjlenyomat(JEGYZET.replace("\n\n", "\n\n\n").replace("**", "")))
        self.assertNotEqual(a, AU.forras_ujjlenyomat(JEGYZET.replace("Crassust", "Brutust")))

    def test_mondatok_kodot_es_gep_irta_szakaszt_nem_nezi(self):
        md = JEGYZET + "\n## Gyakorlás\n\n![[Valami — kártyák]]\n\n## Kitöltések\n\nGép írta sor van itt.\n"
        self.assertEqual(AU.mondatok(md), AU.mondatok(JEGYZET))

    def test_tavolsag_ures_es_azonos(self):
        self.assertEqual(AU.valtozas(None, "").tavolsag, 0.0)
        v = AU.valtozas(AU.mondatok(JEGYZET), JEGYZET)
        self.assertEqual((v.tavolsag, v.uj_karakter), (0.0, 0))
        self.assertEqual(AU.valtozas(None, JEGYZET).tavolsag, 1.0)

    def test_beallitas_az_os_tomlbol(self):
        from core import config
        b = AU.beallitas(config.load())
        self.assertEqual((b.csend_perc, b.kuszob, b.min_hossz, b.uj_karakter), (10, 0.3, 400, 600))


if __name__ == "__main__":
    unittest.main()
