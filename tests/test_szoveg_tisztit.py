"""A megjelenített kivonat Markdown-tisztítása (C32b): feladatjelölő, link, kiemelés, kód, idézet, táblázat; a bemenet nem változik."""
import unittest

from core import ma, szoveg_tisztit


class SzovegTisztit(unittest.TestCase):
    def e(self, szoveg):
        return szoveg_tisztit.egyszeru(szoveg)

    def test_feladatjelolo(self):
        self.assertEqual(self.e("- [ ] matek\n- [x] fizika\n* [X] töri\n- sima elem\n1. első"),
                         "☐ matek ☑ fizika ☑ töri sima elem első")

    def test_wikilink_alias_ut_fejezet(self):
        self.assertEqual(self.e("Lásd [[Mappa/Jegyzet|ez]] és [[Mappa/Másik.md#Fej]], [[#Saját fejezet]], [[X#^blokk]]."),
                         "Lásd ez és Másik, Saját fejezet, X.")

    def test_md_link_beagyazas_labjegyzet(self):
        self.assertEqual(self.e("[szöveg](https://pelda.hu/x) ![[kep.png]] ![alt](a.png) állítás[^1] [kód](<a b.md>)"),
                         "szöveg állítás kód")

    def test_kiemelesek(self):
        self.assertEqual(self.e("**vastag** __vastag2__ *dőlt* _dőlt2_ ~~áthúzott~~ ==kiemelt== `kód`"),
                         "vastag vastag2 dőlt dőlt2 áthúzott kiemelt kód")

    def test_szavon_belul_alahuzas_es_szorzas_marad(self):
        self.assertEqual(self.e("snake_case_név 2*3*4 és a * b"), "snake_case_név 2*3*4 és a * b")

    def test_cimsor_vonal_kod_komment_kiesik(self):
        self.assertEqual(self.e("# Cím\nelső\n---\n```py\nx = 1\n```\n<!-- rejtett -->\n%% megj %%\n## Alcím\nmásodik"),
                         "első második")

    def test_idezet_callout_tabla_blokkid(self):
        self.assertEqual(self.e("> idézet\n> [!note]- Cím\n> tartalom\n| a | b |\n|---|---|\n| 1 | 2 |\nvég ^abc123"),
                         "idézet Cím tartalom a · b 1 · 2 vég")

    def test_a_feladat_metaadat_es_cimke_marad(self):
        self.assertEqual(self.e("- [ ] beadandó #suli 📅 2026-10-09"), "☐ beadandó #suli 📅 2026-10-09")

    def test_crlf_es_ures(self):
        self.assertEqual(self.e("a\r\n\r\nb"), "a b")
        self.assertEqual(self.e(""), "")

    def test_a_kivonat_a_tisztitot_hasznalja_es_vagja(self):
        self.assertEqual(ma._kivonat("# Napló\n\n- [x] **kész** a [[Jegyzet|házi]]\n"), "☑ kész a házi")
        self.assertTrue(ma._kivonat("- " + "[[Szó|szó]] " * 200).endswith("…"))


if __name__ == "__main__":
    unittest.main()
