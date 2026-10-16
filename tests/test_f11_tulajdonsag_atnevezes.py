"""03-properties-07: egy tulajdonság kulcsának átnevezése a jegyzetben (`modosit` `atnevez`): csak a kulcs szövege változik,
az érték, a sorrend, a megjegyzések, az idézőjel-fajta és a sortörés érintetlen; az ütközés és az érvénytelen név elutasított."""
import unittest
from types import SimpleNamespace

from core.tulajdonsagok import Tulajdonsagok
from tests.helpers import tmpdir
from tests.vaultgyar import alg_semleges

UT = "Jegyzet.md"


class AtnevezesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)
        self.t = Tulajdonsagok(self.cfg, SimpleNamespace(tipusok={}))

    def at(self, fm, kulcs, uj, **kw):
        return self.t.modosit(UT, fm, "atnevez", kulcs, uj_kulcs=uj, **kw)

    def test_csak_a_kulcs_szovege_valtozik(self):
        fm = "---\n# megjegyzés\ntitle: Cím  # sorvégi\nrating: 5\ntags:\n  - a\n  - b\nnote: |\n  sor1\n  sor2\n---\n"
        r = self.at(fm, "rating", "pontszam")
        self.assertTrue(r["ok"] and r["valtozas"], r)
        self.assertEqual(r["fm_uj"], fm.replace("rating: 5", "pontszam: 5"))
        r = self.at(fm, "tags", "cimkek")                                    # többsoros lista: az elemek maradnak
        self.assertEqual(r["fm_uj"], fm.replace("tags:", "cimkek:"))
        r = self.at(fm, "note", "megjegyzes")                                # blokk-skalár
        self.assertEqual(r["fm_uj"], fm.replace("note: |", "megjegyzes: |"))

    def test_idezojel_sortores_bom_megmarad(self):
        fm = '---\r\n"a b": 1\r\n\'c d\': 2\r\nplain: 3\r\n---\r\n'
        self.assertEqual(self.at(fm, "a b", "x y")["fm_uj"], fm.replace('"a b"', '"x y"'))
        self.assertEqual(self.at(fm, "c d", "e f")["fm_uj"], fm.replace("'c d'", "'e f'"))
        self.assertEqual(self.at(fm, "plain", "plain2")["fm_uj"], fm.replace("plain:", "plain2:"))
        bom = "﻿---\ntitle: x\n---\n"
        self.assertEqual(self.at(bom, "title", "cim")["fm_uj"], "﻿---\ncim: x\n---\n")

    def test_yaml_foglalt_szavak_idezve(self):
        fm = "---\ntitle: x\n---\n"
        r = self.at(fm, "title", "yes")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["fm_uj"], '---\n"yes": x\n---\n')                 # a bare `yes` boolean kulcs lenne

    def test_ures_ertek_es_sorrend(self):
        fm = "---\nsource:\nrating: 3\n---\n"
        r = self.at(fm, "source", "forras")
        self.assertEqual(r["fm_uj"], "---\nforras:\nrating: 3\n---\n")

    def test_utkozes_nincs_kulcs_ervenytelen_nev(self):
        fm = "---\nrating: 5\nscore: 3\n---\n"
        r = self.at(fm, "rating", "score")
        self.assertFalse(r["ok"])
        self.assertEqual(r["problemak"][0]["kod"], "duplikalt_kulcs")
        self.assertEqual(r["problemak"][0]["kulcs"], "rating")                 # a hiba az átnevezett sor alatt látszik
        self.assertEqual(r["problemak"][0]["kulcs"], "rating")                  # a hiba az átnevezett sor alatt látszik
        self.assertEqual(self.at(fm, "nincs", "x")["problemak"][0]["kod"], "nincs_kulcs")
        self.assertEqual(self.at(None, "nincs", "x")["problemak"][0]["kod"], "nincs_kulcs")
        for rossz in ("", "1x", "a:b", "a#b", None, 5, "x" * 81):
            self.assertEqual(self.at(fm, "rating", rossz)["problemak"][0]["kod"], "kulcs_nev", rossz)

    def test_ugyanaz_a_nev_nem_valtozas_es_az_eset_atirhato(self):
        fm = "---\nrating: 5\n---\n"
        r = self.at(fm, "rating", "rating")
        self.assertTrue(r["ok"] and not r["valtozas"])
        self.assertEqual(self.at("---\nx: 1\n---\n", "x", "it's")["problemak"][0]["kod"], "kulcs_nev")   # aposztróf nem kulcs-karakter
        r = self.at(fm, "rating", "Rating")                                  # a YAML kulcsok kis-nagybetű-érzékenyek: engedett
        self.assertEqual(r["fm_uj"], "---\nRating: 5\n---\n")

    def test_hibas_yaml_es_duplikalt_forras_elutasitott(self):
        self.assertFalse(self.at("---\na: [1\n---\n", "a", "b")["ok"])
        self.assertFalse(self.at("---\na: 1\na: 2\n---\n", "a", "b")["ok"])

    def test_gepi_iras_nem_nyulhat_a_status_hoz(self):
        t = Tulajdonsagok(self.cfg, SimpleNamespace(tipusok={}))
        fm = "---\nStatus: Open\nx: 1\n---\n"
        r = t.modosit(UT, fm, "atnevez", "Status", uj_kulcs="Allapot", forras="gep")
        self.assertTrue(r["ok"] or r["problemak"][0]["kod"] == "status_gep")   # a védelem csak a séma szerint éles
        self.assertIsNone(t.modosit(UT, fm, "atnevez", "x", uj_kulcs="y", forras="gep").get("hiba"))

    def test_http_alak_az_uj_kulccsal(self):
        # a kötés: a `modosit` kulcsszavas `uj_kulcs`-szal hívható, a régi műveletek változatlanok
        fm = "---\nrating: 5\n---\n"
        self.assertEqual(self.t.modosit(UT, fm, "torol", "rating")["fm_uj"], "---\n---\n")
        self.assertEqual(self.t.modosit(UT, fm, "beallit", "rating", 6, "number")["fm_uj"], "---\nrating: 6\n---\n")


if __name__ == "__main__":
    unittest.main()
