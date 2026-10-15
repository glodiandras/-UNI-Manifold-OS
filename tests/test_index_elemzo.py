"""A jegyzet- és canvas-elemző (C06): frontmatter típusokkal, fejezetek, blokkok, linkek, címkék, feladatok,
képletek, kódblokkok — mind a legacy kódmaszk után."""
import unittest

from core.index import elemzo
from core.index.feloldas import jegyzet_celok

MINTA = """---
Tags:
  - Math/Algebra
aliases: [Alg, "Algebra 1"]
YEAR: 2020
datum: 2026-01-02
ido: 2026-01-02T10:30
kesz: yes
igaz: true
ora: 10:30
NN:
  - "[[09 - Tisza]]"
---
# Cím #
Szöveg [[Cél#Fej|al]] és ![[kep.png|300]] meg [[a\\|b]] `[[kod]]` #fő/al #123 #x-y_z ^blk1
- [ ] tennivaló 📅 2026-10-01 [scheduled:: 2026-09-30]
  - [x] kész ✅ 2026-09-01
Képlet $x^2$ és $$\\int f$$ de nem 5$ és $6
```plot
y=x
# nem fejezet #nemcimke
- [ ] nem feladat
```
[md](Jegyzet%20X.md#fej) [[Blokk#^b1]] ![[Kép]]
Bekezdés
folytatás
^kulon
## Második
"""


class ElemzoTest(unittest.TestCase):
    def setUp(self):
        self.j = elemzo.elemez(MINTA, {"YEAR": "number", "kesz": "checkbox"})

    def test_frontmatter_tipusok(self):
        t = {x.kulcs: x for x in self.j.tulajdonsagok}
        self.assertEqual(list(t), ["Tags", "aliases", "YEAR", "datum", "ido", "kesz", "igaz", "ora", "NN"])
        self.assertEqual((t["Tags"].tipus, t["Tags"].ertek), ("tags", ["Math/Algebra"]))
        self.assertEqual(t["aliases"].tipus, "aliases")
        self.assertEqual((t["YEAR"].tipus, t["YEAR"].ertek), ("number", 2020))
        self.assertEqual((t["datum"].tipus, t["datum"].ertek), ("date", "2026-01-02"))      # nem datetime-objektum
        self.assertEqual(t["ido"].tipus, "datetime")
        self.assertEqual((t["kesz"].tipus, t["kesz"].ertek, t["kesz"].ervenyes), ("checkbox", "yes", False))
        self.assertEqual((t["igaz"].tipus, t["igaz"].ertek), ("checkbox", True))
        self.assertEqual(t["ora"].ertek, "10:30")                                          # nem hatvanas szám
        self.assertEqual(t["NN"].tipus, "multitext")
        self.assertEqual(self.j.aliasok, ["Alg", "Algebra 1"])
        self.assertIsNone(self.j.fm_hiba)

    def test_frontmatter_hiba_nem_nyelodik_el(self):
        j = elemzo.elemez("---\na: [1, 2\nb: c\n---\ntörzs [[X]]\n")
        self.assertIsNotNone(j.fm_hiba)
        self.assertEqual(j.tulajdonsagok, [])
        self.assertEqual([L.cel for L in j.linkek], ["X"])
        self.assertIsNotNone(elemzo.elemez("---\n- lista\n---\n").fm_hiba)
        self.assertIsNone(elemzo.elemez("---\n---\nx").fm_hiba)

    def test_fejezetek_kodon_kivul(self):
        self.assertEqual([(f["szint"], f["szoveg"], f["sor"]) for f in self.j.fejezetek],
                         [(1, "Cím", 14), (2, "Második", 28)])

    def test_linkek_es_a_graf_listaja_azonos(self):
        self.assertEqual([L.cel for L in self.j.linkek], jegyzet_celok(MINTA))
        L = {L.cel: L for L in self.j.linkek}
        self.assertEqual((L["09 - Tisza"].tulajdonsag, L["09 - Tisza"].sor), ("NN", 12))
        self.assertEqual((L["Cél"].alcel, L["Cél"].alias, L["Cél"].sor, L["Cél"].oszlop), ("Fej", "al", 15, 7))
        self.assertTrue(L["kep.png"].beagyazas)
        self.assertEqual(L["kep.png"].alias, "300")
        self.assertEqual((L["a\\"].alias, L["Blokk"].alcel), ("b", "^b1"))
        self.assertTrue(L["Kép"].beagyazas)
        md = L["Jegyzet X.md"]                                  # C31 (36. döntés): URL-dekódolva
        self.assertEqual((md.fajta, md.alcel, md.alias), ("md", "fej", "md"))
        self.assertNotIn("kod", L)

    def test_cimkek(self):
        self.assertEqual([(c["cimke"], c["forras"]) for c in self.j.cimkek],
                         [("Math/Algebra", "fm"), ("fő/al", "szoveg"), ("x-y_z", "szoveg")])

    def test_blokkok(self):
        self.assertEqual([(b["azon"], b["sor"], b["kezdo_sor"]) for b in self.j.blokkok],
                         [("blk1", 15, 15), ("kulon", 27, 24)])

    def test_feladatok_datummal(self):
        f = self.j.feladatok
        self.assertEqual(len(f), 2)
        self.assertEqual((f[0]["sor"], f[0]["allapot"], f[0]["datumok"]),
                         (16, " ", {"hatarido": "2026-10-01", "utemezve": "2026-09-30"}))
        self.assertEqual((f[1]["allapot"], f[1]["behuzas"], f[1]["datumok"]), ("x", 2, {"kesz": "2026-09-01"}))

    def test_kepletek_es_kodblokk(self):
        self.assertEqual([(k["forras"], k["blokk"], k["sor"]) for k in self.j.kepletek],
                         [("x^2", False, 18), ("\\int f", True, 18)])
        self.assertEqual(self.j.kodblokkok, [{"nyelv": "plot", "sor_kezd": 19, "sor_veg": 23}])

    def test_canvas(self):
        j = elemzo.elemez_canvas({"nodes": [{"id": "1", "file": "a.md", "subpath": "#H"},
                                            {"id": "2", "text": "[[B|b]] `[[C]]`"}, {"id": "3", "label": "Csoport"}]},
                                 None)
        self.assertEqual([(L.cel, L.fajta, L.alcel, L.alias, L.csomopont) for L in j.linkek],
                         [("a.md", "canvas_fajl", "H", None, "1"), ("B", "canvas_szoveg", None, "b", "2")])
        self.assertIn("Csoport", j.tartalom)
        self.assertEqual(elemzo.elemez_canvas(None, "hiba").canvas_hiba, "hiba")


class AuditKapukTest(unittest.TestCase):
    """C29.8a (2. audit): az index kapui — alias-típusok, mély YAML, idézet-/táblázat-horgony, setext fejezet, YAML-alias
    tilalom, üres és BOM-os frontmatter. Mindegyik teszt a javítás ELŐTT bukott a régi kódon."""

    # ---- T037
    def test_szam_bool_float_alias_szoveg_lesz(self):
        j = elemzo.elemez("---\naliases: [1984, true, 1.5, szöveg]\n---\n# C\n")
        self.assertEqual(j.aliasok, ["1984", "true", "1.5", "szöveg"])
        self.assertEqual(elemzo.elemez("---\naliases: 1984\n---\n").aliasok, ["1984"])
        self.assertEqual(elemzo.elemez("---\nalias: false\n---\n").aliasok, ["false"])

    def test_melyen_egymasba_agyazott_frontmatter_hiba_nem_kivetel(self):
        fm = "a: " + "[" * 1000 + "]" * 1000
        t, hiba = elemzo.frontmatter(fm)
        self.assertEqual(t, [])
        self.assertIsInstance(hiba, str)
        j = elemzo.elemez("---\n" + fm + "\n---\ntörzs [[X]]\n")
        self.assertIsNotNone(j.fm_hiba)
        self.assertIn("X", [L.cel for L in j.linkek])          # a törzs elemzése nem esik el (a `[[[…` a frontmatterben is link-alak)

    # ---- T039
    def test_idezet_horgony_a_blokk_elejetol(self):
        j = elemzo.elemez("# C\n\n> a\n> b ^k1\n\nzáró\n")
        self.assertEqual([(b["azon"], b["sor"], b["kezdo_sor"]) for b in j.blokkok], [("k1", 4, 3)])
        # a listaelem-ág változatlan: az idézetben álló listaelem egy elem marad
        j = elemzo.elemez("> - elem ^k2\n")
        self.assertEqual([(b["azon"], b["kezdo_sor"]) for b in j.blokkok], [("k2", 1)])

    def test_pdf_kiemeles_blokk_horgonya_az_elso_idezet_sor(self):
        from core import pdfkiemeles
        sorok = pdfkiemeles.blokk("k-1a2b3c", 3, "szöveg", [[0.1, 0.2, 0.3, 0.1]], "X.pdf")
        j = elemzo.elemez("## 3. oldal\n" + "\n".join(sorok) + "\n")
        self.assertEqual([(b["azon"], b["sor"], b["kezdo_sor"]) for b in j.blokkok], [("k-1a2b3c", 4, 3)])

    def test_tablazat_horgony_a_tablazat_elejetol(self):
        j = elemzo.elemez("| a | b |\n|---|---|\n| 1 | 2 |\n\n^t1\n")
        self.assertEqual([(b["azon"], b["sor"], b["kezdo_sor"]) for b in j.blokkok], [("t1", 5, 1)])
        j = elemzo.elemez("szöveg\n\n| a |\n|---|\n| 1 | ^t2\n")
        self.assertEqual([(b["azon"], b["kezdo_sor"]) for b in j.blokkok], [("t2", 3)])

    def test_setext_fejezet(self):
        j = elemzo.elemez("Cím\n===\nszöveg\n\nAlcím\n---\n\n---\n")
        self.assertEqual([(f["szint"], f["szoveg"], f["sor"]) for f in j.fejezetek], [(1, "Cím", 1), (2, "Alcím", 5)])
        j = elemzo.elemez("# Atx\nszöveg\n\nSetext\n======\n\n## Atx2\n")
        self.assertEqual([(f["szint"], f["szoveg"], f["sor"]) for f in j.fejezetek],
                         [(1, "Atx", 1), (1, "Setext", 4), (2, "Atx2", 7)])          # sorrendben, ATX és setext együtt

    def test_setext_negativ_esetek(self):
        for txt in ("---\na: 1\n---\nszöveg\n",          # a frontmatter záró `---`-je
                    "szöveg\n\n---\nmásik\n",            # hr üres sor után
                    "- a\n---\n", "> q\n---\n", "| a |\n---\n",   # lista, idézet, táblázat után
                    "```\nTitle\n===\n```\n",            # kódkerítésben
                    "1. a\n---\n"):
            self.assertEqual(elemzo.elemez(txt).fejezetek, [], repr(txt))
        self.assertEqual([(f["szint"], f["szoveg"]) for f in elemzo.elemez("# H\n---\n").fejezetek], [(1, "H")])

    # ---- T041
    def test_yaml_alias_tiltott(self):
        j = elemzo.elemez("---\na: &x [1]\nb: *x\n---\n# C\n")
        self.assertIsNotNone(j.fm_hiba)
        self.assertEqual(j.tulajdonsagok, [])
        # a horgony önmagában inert: marad
        j = elemzo.elemez("---\na: &x [1]\n---\n")
        self.assertIsNone(j.fm_hiba)
        self.assertEqual([t.kulcs for t in j.tulajdonsagok], ["a"])

    def test_yaml_alias_bomba_azonnal_hiba(self):
        sorok = ["a0: &a0 [" + ", ".join(["x"] * 9) + "]"]
        for i in range(1, 6):
            sorok.append(f"a{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 9) + "]")
        j = elemzo.elemez("---\n" + "\n".join(sorok) + "\n---\n")
        self.assertIsNotNone(j.fm_hiba)
        self.assertEqual(j.tulajdonsagok, [])

    # ---- T130
    def test_ures_es_bom_os_frontmatter(self):
        j = elemzo.elemez("---\n---\n# C\n")
        self.assertEqual((j.fm_nyers, j.fm_hiba), ("", None))
        self.assertEqual([(f["szoveg"], f["sor"]) for f in j.fejezetek], [("C", 3)])
        j = elemzo.elemez("\ufeff---\naliases: [A]\n---\n# C\n")
        self.assertEqual((j.fm_nyers, j.aliasok), ("aliases: [A]", ["A"]))
        # a szóközös nyitó nem frontmatter (K79)
        self.assertIsNone(elemzo.elemez("--- \na: 1\n---\n").fm_nyers)


if __name__ == "__main__":
    unittest.main()
