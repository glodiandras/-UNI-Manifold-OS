"""A felkészülési jegyzet témái (`Source` + `NN` jegyzet-linkjei, C28a) a vault valós alakjaival, és a kvíz-adatforrás
illesztője (a C22 köti rá a saját tárolóját)."""
import unittest
from datetime import datetime, timedelta, timezone

from core.felkeszultseg import forrasok, temak

UT = "X01 - Napló & To-Do/2026-09/Dolgozatok/2026-09-18 - Matematika.md"
DIGEST = "M07 - Tankönyvek/11 - Matematika.pdf"


def link(cel, tulajdonsag="Source", alcel=None, nyers=None):
    return {"fajta": "wikilink", "cel_nyers": nyers or (cel or "?"), "cel": cel, "alcel": alcel, "alias": None,
            "tulajdonsag": tulajdonsag, "beagyazas": False}


def jegyzet(*linkek, ut=UT):
    return {"ut": ut, "linkek": list(linkek)}


T1 = "M06 - Exponenciális/Elmélet/11 - Számok n-edik gyöke.md"
T2 = "M06 - Exponenciális/Elmélet/12 - Az n-edik gyökvonás azonosságai.md"


class TemakTest(unittest.TestCase):
    def kinyer(self, j, felk=()):
        return temak.kinyer(j, set(felk))

    def test_temajegyzet_linkek_source_bol(self):
        t = self.kinyer(jegyzet(link(T1), link(T2)))
        self.assertEqual(t.temak, (T1, T2))
        self.assertFalse(t.onmaga)
        self.assertEqual(t.forrasok, ())

    def test_pdf_horgonyok_forrasok_a_temak_az_nn_bol(self):
        """A vault valós alakja (2026-09-18 - Matematika): a Source a PDF oldalai, a témák az NN-ben."""
        linkek = [link(DIGEST, alcel=f"page={n}") for n in range(18, 29)] + [link(T1, "NN"), link(T2, "NN")]
        t = self.kinyer(jegyzet(*linkek))
        self.assertEqual(t.temak, (T1, T2))
        self.assertEqual(len(t.forrasok), 1)
        f = t.forrasok[0]
        self.assertEqual((f.ut, f.tipus, f.oldalak), (DIGEST, "pdf", "18–28"))

    def test_oldaltartomanyok_tordelve(self):
        t = self.kinyer(jegyzet(*[link(DIGEST, alcel=f"page={n}") for n in (31, 32, 33, 34, 40)]))
        self.assertEqual(t.forrasok[0].oldalak, "31–34, 40")

    def test_kep_forras(self):
        t = self.kinyer(jegyzet(link("ATTCHMNTS - photos/Német szavak - 100-104.jpg")))
        self.assertEqual(t.forrasok[0].tipus, "kep")
        self.assertEqual(t.temak, (UT,))
        self.assertTrue(t.onmaga)

    def test_ures_source_a_jegyzet_maga_a_tema(self):
        t = self.kinyer(jegyzet())
        self.assertEqual(t.temak, (UT,))
        self.assertTrue(t.onmaga)

    def test_csak_pdf_nn_nelkul_a_jegyzet_maga_a_tema(self):
        t = self.kinyer(jegyzet(*[link(DIGEST, alcel=f"page={n}") for n in range(79, 91)]))
        self.assertTrue(t.onmaga)
        self.assertEqual(t.forrasok[0].oldalak, "79–90")

    def test_duplikatum_onhivatkozas_es_masik_felkeszulesi_jegyzet_kiszurve(self):
        masik = "X01 - Napló & To-Do/2026-09/Dolgozatok/2026-09-14 - Matematika.md"
        t = self.kinyer(jegyzet(link(T1), link(T1, "NN"), link(UT), link(masik)), felk={UT, masik})
        self.assertEqual(t.temak, (T1,))

    def test_mas_tulajdonsag_linkje_nem_tema(self):
        t = self.kinyer(jegyzet(link(T1, "Canvas"), link(T2, None)))
        self.assertEqual(t.temak, (UT,))

    def test_kis_nagybetu_tolerans_a_tulajdonsag_kulcson(self):
        self.assertEqual(self.kinyer(jegyzet(link(T1, "source"), link(T2, "nn"))).temak, (T1, T2))

    def test_feloldatlan_link_nem_tema_de_jelezve(self):
        t = self.kinyer(jegyzet(link(None, nyers="Nincs ilyen"), link(T1)))
        self.assertEqual(t.temak, (T1,))
        self.assertEqual(t.feloldatlan, ["Nincs ilyen"])

    def test_a_sorrend_a_jegyzeteke_es_az_nn_a_source_utan_ha_igy_all(self):
        t = self.kinyer(jegyzet(link(T2, "NN"), link(T1, "Source")))
        self.assertEqual(t.temak, (T2, T1))

    def test_nem_md_nem_kep_nem_pdf_tipus_egyeb(self):
        t = self.kinyer(jegyzet(link("X/Valami.canvas"), link(T1)))
        self.assertEqual(t.temak, (T1,))
        self.assertEqual([f.tipus for f in t.forrasok], ["egyeb"])


MOST = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


class KvizForrasTest(unittest.TestCase):
    def setUp(self):
        self._mentett = dict(forrasok._FORRASOK)
        forrasok._FORRASOK.clear()
        self.addCleanup(lambda: (forrasok._FORRASOK.clear(), forrasok._FORRASOK.update(self._mentett)))

    def test_regisztracio_nelkul_ures(self):
        self.assertEqual(forrasok.kviz_eredmenyek(None, MOST - timedelta(days=21), MOST), ([], []))

    def test_regisztralt_forras_eredmenyei_ablakra_szurve_nfc_temaval(self):
        mind = [forrasok.KvizEredmeny("Téma", MOST - timedelta(days=2), 3, 4),
                forrasok.KvizEredmeny("Téma", MOST - timedelta(days=40), 1, 4),
                forrasok.KvizEredmeny("Téma", MOST + timedelta(days=1), 4, 4)]
        forrasok.regisztral_kviz_forras("c22", lambda cfg, tol, ig: mind)
        ki, hibak = forrasok.kviz_eredmenyek(None, MOST - timedelta(days=21), MOST)
        self.assertEqual([(e.helyes, e.osszes) for e in ki], [(3, 4)])
        self.assertEqual(hibak, [])

    def test_hibas_forras_nem_viszi_el_a_tobbit(self):
        def rossz(cfg, tol, ig):
            raise RuntimeError("elromlott")
        forrasok.regisztral_kviz_forras("a", rossz)
        forrasok.regisztral_kviz_forras("b", lambda cfg, tol, ig: [forrasok.KvizEredmeny("T", MOST, 1, 2)])
        ki, hibak = forrasok.kviz_eredmenyek(None, MOST - timedelta(days=1), MOST + timedelta(days=1))
        self.assertEqual(len(ki), 1)
        self.assertEqual(len(hibak), 1)
        self.assertIn("elromlott", hibak[0])

    def test_ervenytelen_elem_kihagyva(self):
        forrasok.regisztral_kviz_forras("x", lambda cfg, tol, ig: [
            forrasok.KvizEredmeny("T", MOST, 5, 4),                      # több helyes, mint kérdés
            forrasok.KvizEredmeny("T", MOST, 1, 0),                      # nincs kérdés
            forrasok.KvizEredmeny("T", datetime(2026, 10, 4, 12, 0), 1, 2),   # időzóna nélkül
            forrasok.KvizEredmeny("T", MOST, 2, 4)])
        ki, hibak = forrasok.kviz_eredmenyek(None, MOST - timedelta(days=1), MOST + timedelta(days=1))
        self.assertEqual([(e.helyes, e.osszes) for e in ki], [(2, 4)])
        self.assertEqual(len(hibak), 1)


if __name__ == "__main__":
    unittest.main()
