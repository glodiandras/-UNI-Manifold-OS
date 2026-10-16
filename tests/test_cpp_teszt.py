"""C36a: a `teszt` blokk formátuma és a feladat-váz (`core/cpp_teszt.py`) — a formátum egyetlen helye (mint a
`core/pdfkiemeles.py`). A kerítés-felismerés a `core/index/maszk.keritesek`-é, itt csak a blokkok értelmezése áll."""
import unittest

from core import cpp_teszt as T


def blokk(*sorok: str, info: str = "teszt") -> str:
    return "```" + info + "\n" + "\n".join(sorok) + "\n```\n"


class EgyBlokkTest(unittest.TestCase):
    def test_egyszeru_teszt(self):
        t = T.tesztek(blokk("--- bemenet", "5", "1 2 3 4 5", "--- kimenet", "15"))
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0].sorszam, t[0].sor), (1, 1))
        self.assertEqual(t[0].bemenet, "5\n1 2 3 4 5\n")
        self.assertEqual(t[0].kimenet, "15\n")
        self.assertIsNone(t[0].idokorlat_s)
        self.assertIsNone(t[0].cim)
        self.assertIsNone(t[0].hiba)

    def test_cim_a_nyito_sor_vegen(self):
        t = T.tesztek(blokk("--- kimenet", "x", info="teszt Szélső eset: n = 0"))
        self.assertEqual(t[0].cim, "Szélső eset: n = 0")

    def test_idokorlat_formak(self):
        for szoveg, mp in (("2", 2.0), ("2s", 2.0), ("1.5 s", 1.5), ("1,5", 1.5), ("500 ms", 0.5), ("3 mp", 3.0)):
            t = T.tesztek(blokk("--- kimenet", "x", "--- idokorlat", szoveg))
            self.assertIsNone(t[0].hiba, szoveg)
            self.assertAlmostEqual(t[0].idokorlat_s, mp, msg=szoveg)

    def test_idokorlat_hibak(self):
        for szoveg in ("gyors", "0", "-1", "1 perc", "", "2 s 3"):
            t = T.tesztek(blokk("--- kimenet", "x", "--- idokorlat", szoveg))
            self.assertIn("időkorlát", t[0].hiba or "", szoveg)

    def test_a_maximum_fole_nem_mehet(self):
        t = T.tesztek(blokk("--- kimenet", "x", "--- idokorlat", "11"), max_idokorlat_s=10.0)
        self.assertIn("legfeljebb 10", t[0].hiba)
        t = T.tesztek(blokk("--- kimenet", "x", "--- idokorlat", "10"), max_idokorlat_s=10.0)
        self.assertIsNone(t[0].hiba)

    def test_bemenet_nelkul_vagy_ures_bemenettel(self):
        self.assertEqual(T.tesztek(blokk("--- kimenet", "x"))[0].bemenet, "")
        self.assertEqual(T.tesztek(blokk("--- bemenet", "--- kimenet", "x"))[0].bemenet, "")

    def test_a_szakaszok_sorrendje_szabad(self):
        t = T.tesztek(blokk("--- kimenet", "7", "--- bemenet", "3 4"))
        self.assertEqual((t[0].bemenet, t[0].kimenet), ("3 4\n", "7\n"))

    def test_hianyzo_kimenet(self):
        t = T.tesztek(blokk("--- bemenet", "5"))
        self.assertIn("kimenet", t[0].hiba)

    def test_ures_kimenet_szakasz_ervenyes_a_program_semmit_sem_ir(self):
        t = T.tesztek(blokk("--- bemenet", "5", "--- kimenet"))
        self.assertIsNone(t[0].hiba)
        self.assertEqual(t[0].kimenet, "")

    def test_a_szakaszok_vegi_ures_sorok_nem_szamitanak(self):
        t = T.tesztek(blokk("--- bemenet", "5", "", "", "--- kimenet", "15", ""))
        self.assertEqual((t[0].bemenet, t[0].kimenet), ("5\n", "15\n"))

    def test_belso_ures_sor_megmarad(self):
        t = T.tesztek(blokk("--- bemenet", "a", "", "b", "--- kimenet", "x"))
        self.assertEqual(t[0].bemenet, "a\n\nb\n")

    def test_kotojel_a_tartalomban_tartalom(self):
        t = T.tesztek(blokk("--- kimenet", "---", "--- valami", "--- kimenet: x", "-----"))
        self.assertIsNone(t[0].hiba)
        self.assertEqual(t[0].kimenet, "---\n--- valami\n--- kimenet: x\n-----\n")

    def test_az_elso_sor_nem_szakaszjelzo_hiba(self):
        t = T.tesztek(blokk("5", "--- kimenet", "x"))
        self.assertIn("szakaszjelz", t[0].hiba)

    def test_ures_sorok_a_szakaszjelzo_elott_nem_hiba(self):
        t = T.tesztek(blokk("", "--- kimenet", "x"))
        self.assertIsNone(t[0].hiba)

    def test_ketszer_szereplo_szakasz_hiba(self):
        t = T.tesztek(blokk("--- kimenet", "a", "--- kimenet", "b"))
        self.assertIn("kétszer", t[0].hiba)

    def test_szakaszjelzo_nagybetuvel_es_felesleges_szokozzel(self):
        t = T.tesztek(blokk("--- Kimenet  ", "x", "---   BEMENET", "y"))
        self.assertIsNone(t[0].hiba)
        self.assertEqual((t[0].kimenet, t[0].bemenet), ("x\n", "y\n"))

    def test_crlf_sorvegek(self):
        szoveg = blokk("--- bemenet", "5", "--- kimenet", "15").replace("\n", "\r\n")
        t = T.tesztek(szoveg)
        self.assertEqual((t[0].bemenet, t[0].kimenet), ("5\n", "15\n"))

    def test_lezaratlan_kerites_hiba(self):
        t = T.tesztek("```teszt\n--- kimenet\n15\n")
        self.assertIn("nincs lezárva", t[0].hiba)


class TobbBlokkTest(unittest.TestCase):
    def test_sorszam_es_sor_csak_a_teszt_blokkokat_szamolja(self):
        szoveg = ("# Feladat\n\nSzöveg.\n\n```cpp\nint x;\n```\n\n"
                  "```teszt\n--- kimenet\n1\n```\n\nKözben szöveg.\n\n"
                  "```teszt\n--- bemenet\n2\n```\n\n"
                  "```teszt Harmadik\n--- kimenet\n3\n```\n")
        t = T.tesztek(szoveg)
        self.assertEqual([x.sorszam for x in t], [1, 2, 3])
        self.assertEqual([x.sor for x in t], [9, 16, 21])
        self.assertIsNone(t[0].hiba)
        self.assertIn("kimenet", t[1].hiba)             # hibás blokk is bekerül a listába (nem fut, a panelen hiba)
        self.assertEqual(t[2].cim, "Harmadik")

    def test_nem_teszt_nyelv_nem_szamit(self):
        szoveg = blokk("--- kimenet", "x", info="cpp") + blokk("--- kimenet", "x", info="tesztek") \
            + blokk("--- kimenet", "x", info="teszt2") + blokk("--- kimenet", "x", info="")
        self.assertEqual(T.tesztek(szoveg), [])

    def test_a_hosszabb_kerites_belsejeben_allo_teszt_nem_szamit(self):
        szoveg = "````md\n```teszt\n--- kimenet\n1\n```\n````\n"
        self.assertEqual(T.tesztek(szoveg), [])

    def test_a_tilde_kerites_is_jo(self):
        t = T.tesztek("~~~teszt\n--- kimenet\n1\n~~~\n")
        self.assertEqual(len(t), 1)
        self.assertIsNone(t[0].hiba)

    def test_idezetben_es_callout_ban_a_kerites_eloirata_levalik(self):
        szoveg = "> [!note]\n> ```teszt\n> --- bemenet\n> 5\n> --- kimenet\n> 15\n> ```\n"
        t = T.tesztek(szoveg)
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0].bemenet, t[0].kimenet), ("5\n", "15\n"))
        self.assertIsNone(t[0].hiba)

    def test_listaelemben_a_behuzas_levalik(self):
        szoveg = "- elem\n  ```teszt\n  --- bemenet\n  5\n  --- kimenet\n  15\n  ```\n"
        t = T.tesztek(szoveg)
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0].bemenet, t[0].kimenet), ("5\n", "15\n"))

    def test_frontmatter_utan_a_sorszamok_a_fajl_soraira_mutatnak(self):
        szoveg = "---\nTags:\nSource:\n---\n\n# C\n\n```teszt\n--- kimenet\n1\n```\n"
        t = T.tesztek(szoveg)
        self.assertEqual(t[0].sor, 8)

    def test_a_frontmatterben_allo_kerites_nem_teszt(self):
        szoveg = "---\nkod: |\n  ```teszt\n  --- kimenet\n  1\n  ```\n---\n\nSzöveg\n"
        self.assertEqual(T.tesztek(szoveg), [])

    def test_ures_szoveg(self):
        self.assertEqual(T.tesztek(""), [])
        self.assertEqual(T.tesztek("nincs itt semmi\n"), [])


class VazTest(unittest.TestCase):
    def test_feladat_vaz_szerkezete(self):
        v = T.feladat_vaz("Összeg", "Informatics")
        self.assertTrue(v.startswith("---\nTags:\n  - Informatics\n---\n\n# Összeg\n"))
        self.assertIn("![[Összeg.cpp]]", v)
        self.assertIn("```teszt", v)

    def test_a_vaz_semleges_angol_es_nem_ir_a_fejleszto_semajat(self):
        """F11: a felhasználó jegyzetébe nem kerül `NN`/`Canvas`/`Source`/`Status` kulcs és magyar szöveg (séma nélkül)."""
        for tag in (None, "Informatics"):
            v = T.feladat_vaz("X", tag)
            for kulcs in ("NN:", "Canvas:", "Source:", "Status:"):
                self.assertNotIn(kulcs, v, msg=kulcs)
            for szo in ("Feladat", "Megoldás", "Bemenet és kimenet", "Írd", "Példa"):
                self.assertNotIn(szo, v, msg=szo)
            for szo in ("## Task", "## Input and output", "## Tests", "## Solution", "Example"):
                self.assertIn(szo, v, msg=szo)

    def test_cimke_es_sema_nelkul_nincs_frontmatter(self):
        v = T.feladat_vaz("X", None)
        self.assertTrue(v.startswith("# X\n"))
        self.assertEqual(len(T.tesztek(v)), 1)

    def test_a_munkater_semajanak_kulcsai_kerulnek_a_fejlecbe(self):
        v = T.feladat_vaz("X", "Informatics", mezok=["Tags", "Source", "Status"])
        self.assertTrue(v.startswith("---\nTags:\n  - Informatics\nSource:\nStatus:\n---\n\n# X\n"))
        v = T.feladat_vaz("X", None, mezok=["Source", "Kulcs: rossz", "NN", "NN"])      # az érvénytelen kulcs kimarad, a kettős egyszer
        self.assertTrue(v.startswith("---\nSource:\nNN:\n---\n"), v)
        v = T.feladat_vaz("X", "Informatics", mezok=["Source"])                          # a címke a séma nélkül is bekerül
        self.assertTrue(v.startswith("---\nTags:\n  - Informatics\nSource:\n---\n"), v)

    def test_a_cimke_nyersen_nem_kerul_a_fejlecbe(self):
        v = T.feladat_vaz("X", "a\nStatus: done")
        self.assertNotIn("\nStatus: done", v)
        self.assertEqual(v.count("\nStatus"), 0)

    def test_minden_nyelv_vaza_a_sajat_kiterjesztesu_forrast_agyazza_be(self):
        from core import kod_nyelvek as KN
        for p in KN.PROFILOK:
            with self.subTest(nyelv=p.azonosito):
                v = T.feladat_vaz("Összeg", None, p.azonosito)
                self.assertIn(f"![[Összeg{p.kiterjesztesek[0]}]]", v)
                self.assertEqual(KN.beagyazott_forrasok(v), [f"Összeg{p.kiterjesztesek[0]}"])
                self.assertEqual(len(T.tesztek(v)), 1)
                self.assertIsNotNone(KN.forras_vaz(p.azonosito))
        self.assertIsNone(KN.forras_vaz("cobol"))

    def test_a_vaz_peldateszt_ervenyes_es_a_ures_megoldas_buktatja(self):
        t = T.tesztek(T.feladat_vaz("X", None))
        self.assertEqual(len(t), 1)
        self.assertIsNone(t[0].hiba)
        self.assertEqual(t[0].kimenet.strip(), "7")                 # a példa: 3 + 4; az üres `main` nem ezt írja ki

    def test_a_cpp_vaz(self):
        v = T.cpp_vaz()
        self.assertIn("#include <bits/stdc++.h>", v)
        self.assertIn("int main()", v)
        self.assertTrue(v.endswith("\n"))

    def test_a_cpp_fajlnev_a_jegyzet_neve(self):
        self.assertEqual(T.cpp_nev("Összeg"), "Összeg.cpp")


class BeagyazasTest(unittest.TestCase):
    def test_az_elso_beagyazott_cpp_a_kod_es_kepletek_maszkja_utan(self):
        szoveg = ("Szöveg\n\n```md\n![[Kod.cpp]]\n```\n\nEz `![[Inline.cpp]]` is kód.\n\n"
                  "![[Megoldas.cpp]]\n\n![[Mas.cpp]]\n![[kep.png]]\n")
        self.assertEqual(T.beagyazott_cpp(szoveg), ["Megoldas.cpp", "Mas.cpp"])

    def test_alias_es_horgony_nem_tartozik_a_nevhez(self):
        self.assertEqual(T.beagyazott_cpp("![[Mappa/Sorok.cpp|megoldás]]\n"), ["Mappa/Sorok.cpp"])

    def test_sima_link_nem_beagyazas(self):
        self.assertEqual(T.beagyazott_cpp("[[Megoldas.cpp]]\n"), [])


if __name__ == "__main__":
    unittest.main()
