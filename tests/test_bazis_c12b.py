"""A C12b core-bővítései: a `.base` fájl-szintű adatai a lekérdezésben (szűrő-szöveg, képletek, elérhető tulajdonságok),
a teljes forrás cseréje (`forras_csere`: megjegyzések megmaradnak, csak az új hiba akadályoz), a szűrő-szöveg kerek útja."""
import unittest

from core.bazis.modell import betolt, modosit, szuro_szoveg
from tests.test_bazis_lekerdezes import FAJLOK, _Alap


class FajlAdatTest(_Alap):
    SZOVEG = (
        "filters:\n  and:\n    - file.ext == \"md\"\n    - 'Status != \"x\"'\n"
        "formulas:\n  dupla: Rating * 2\n"
        "summaries:\n  Sajat: values.sum()\n"
        "views:\n  - type: table\n    name: T\n    filters: Rating > 3\n    order:\n      - file.name\n      - formula.dupla\n"
    )

    def test_a_szuro_es_a_kepletek_szovegkent_jonnek(self):
        v = self.fut(self.SZOVEG)
        f = v["fajl"]
        self.assertEqual(f["szuro_nezet"], "Rating > 3")
        self.assertIn("file.ext == \"md\"", f["szuro"])
        self.assertTrue(f["szuro"].startswith("and:"))
        self.assertEqual(f["kepletek"], {"dupla": "Rating * 2"})
        self.assertEqual(f["osszesitok"], ["Sajat"])

    def test_a_szuro_szoveg_visszaolvashato(self):
        nyers = betolt(self.SZOVEG)[0].nyers
        szoveg = szuro_szoveg(nyers["filters"])
        uj, hibak, _ = modosit("views:\n  - type: table\n", {"fajta": "szuro_beallit", "hol": "globalis", "yaml": szoveg})
        self.assertEqual(hibak, [])
        self.assertEqual(betolt(uj)[0].nyers["filters"], nyers["filters"])

    def test_nincs_szuro_ures_szoveg(self):
        v = self.fut("views:\n  - type: table\n")
        self.assertEqual((v["fajl"]["szuro"], v["fajl"]["szuro_nezet"]), ("", ""))
        self.assertEqual(v["fajl"]["kepletek"], {})

    def test_az_elerheto_tulajdonsagok_file_note_formula(self):
        v = self.fut(self.SZOVEG)
        el = {e["id"]: e for e in v["fajl"]["elerheto"]}
        self.assertEqual(el["file.name"]["ter"], "file")
        self.assertEqual(el["file.tags"]["tipus"], "tags")
        self.assertEqual(el["Rating"]["ter"], "note")
        self.assertEqual(el["Rating"]["tipus"], "number")
        self.assertEqual(el["formula.dupla"]["ter"], "formula")
        sorrend = [e["id"] for e in v["fajl"]["elerheto"] if e["ter"] == "note"]
        self.assertLess(sorrend.index("Status"), sorrend.index("Born"))     # a gyakoribb elöl áll

    def test_a_tulajdonsag_lista_a_tablan_korlatos(self):
        t = self.tar.tabla()
        self.assertLessEqual(len(t.tulajdonsag_lista(2)), 2)
        self.assertEqual(dict(t.tulajdonsag_lista())["Pages"], "number")


class ForrasCsereTest(unittest.TestCase):
    REGI = "views:\n  - type: table\n    name: A\n"

    def test_a_megjegyzes_es_a_kulcssorrend_megmarad(self):
        uj = "# A könyvek nézete\nviews:\n  - type: table   # táblázat\n    name: B\nfoo: 1\n"
        szoveg, hibak, valtozas = modosit(self.REGI, {"fajta": "forras_csere", "szoveg": uj})
        self.assertEqual((szoveg, hibak, valtozas), (uj, [], "source"))

    def test_a_yaml_hiba_mindig_akadaly(self):
        szoveg, hibak, _ = modosit(self.REGI, {"fajta": "forras_csere", "szoveg": "views: [\n"})
        self.assertEqual(szoveg, self.REGI)
        self.assertEqual(hibak[0]["hely"], "yaml")
        # a már hibás fájlon a YAML-hiba akkor is jelzett marad, ha ugyanaz
        _, hibak2, _ = modosit("views: [\n", {"fajta": "forras_csere", "szoveg": "views: [\n"})
        self.assertEqual(hibak2[0]["hely"], "yaml")

    def test_uj_szuro_hiba_akadaly_a_regi_hiba_nem(self):
        hibas = "filters: a ==\nviews:\n  - type: table\n"
        szoveg, hibak, _ = modosit(self.REGI, {"fajta": "forras_csere", "szoveg": hibas})
        self.assertEqual(szoveg, self.REGI)
        self.assertTrue(hibak)
        # a már hibás fájl más részének javítása nem akad el a régi hibán
        javitott = hibas.replace("type: table", "type: cards")
        szoveg2, hibak2, _ = modosit(hibas, {"fajta": "forras_csere", "szoveg": javitott})
        self.assertEqual((szoveg2, hibak2), (javitott, []))

    def test_hianyzo_szoveg(self):
        for rossz in (None, 5):
            szoveg, hibak, _ = modosit(self.REGI, {"fajta": "forras_csere", "szoveg": rossz})
            self.assertEqual(szoveg, self.REGI)
            self.assertEqual(hibak[0]["hely"], "muvelet")


if __name__ == "__main__":
    unittest.main()
