"""A `.base` hivatkozásai az átnevezéshez (`core/bazis/hivatkozas.py`, C12b 11. lépés) — tiszta függvények, fájl nélkül.

Amit ezek a tesztek őriznek:
  - mi hivatkozás: `link()`, `file()`, `.hasLink()`, `.linksTo()` literálja, a literálban álló `[[…]]`; az út-literál
    szűk fehérlistája (`file.path ==`, `file.inFolder()`, `file.folder ==`); a névre szűrők csak figyelmeztetnek;
  - az átírás csak a literált cseréli, minden más bájt (megjegyzés, kulcssorrend, CRLF) érintetlen, a skalár stílusa
    megmarad, ha az új érték tartja; blokk-skalárban álló érintett hivatkozás blokkoló;
  - a ```` ```base ```` blokk (idézetben, CRLF-fel is) a jegyzet pozícióira képeződik vissza;
  - a `celok` a referencia-próbának ugyanazt a sorrendet adja előtte és utána.
"""
import time
import unittest

from core import atnevezes
from core.bazis import hivatkozas
from core.index.feloldas import Feloldo


def keszit(fajlok, lek):
    fo_e = Feloldo(fajlok)
    fo_u = Feloldo([x for x in fajlok if x not in lek] + list(lek.values()))
    return fo_e, fo_u


def atir(szoveg, fajta, fajlok, lek, forras="Nézet.base", mappa=None):
    """→ (az új szöveg, az eredmény). A `forras` az átnevezés előtti út, az új út a leképezésből."""
    fo_e, fo_u = keszit(fajlok, lek)
    s2 = lek.get(forras, forras)
    er = hivatkozas.cserek_keszit(
        szoveg, fajta, forras, s2, lek, fo_e, fo_u,
        lambda cel, vart: atnevezes.Atnevezes._uj_cel(None, fo_u, cel, vart, s2, "wiki"), mappa)
    return hivatkozas._csere(szoveg, er.cserek), er


def fajtak(szoveg, fajta="base"):
    return [(h.fajta, h.cel) for h in hivatkozas.kivon(szoveg, fajta)]


FAJLOK = ["Cél.md", "Más.md", "Nézet.base"]
LEK = {"Cél.md": "Új név.md"}


class KivonasTest(unittest.TestCase):
    def test_link_tipusu_helyek(self):
        sz = ("filters:\n"
              "  and:\n"
              "    - file.hasLink(link(\"Cél\"))\n"
              "    - 'file.hasLink(\"Más\")'\n"
              "    - NN.contains(file(\"Cél.md\"))\n"
              "formulas:\n"
              "  k: link(\"[[Más|név]]\")\n"
              "  l: this.file.linksTo(\"Cél\")\n"
              "  m: 'x + \"[[Cél#Fej|alias]]\"'\n")
        self.assertEqual(fajtak(sz), [("link", "Cél"), ("link", "Más"), ("link", "Cél.md"), ("link", "Más"),
                                      ("link", "Cél"), ("link", "Cél")])

    def test_literalban_allo_wikilink_barhol(self):
        sz = 'filters: \'Kapcsolat == "[[Cél]] és ![[Más#x]]"\'\n'
        self.assertEqual(fajtak(sz), [("link", "Cél"), ("link", "Más")])

    def test_a_sima_szoveg_literal_nem_hivatkozas(self):
        sz = 'filters: \'Tags.contains("Cél") && Cím == "Más"\'\n'
        self.assertEqual(fajtak(sz), [])

    def test_kulso_cim_es_ures_nem_hivatkozas(self):
        sz = 'formulas:\n  a: link("https://x.hu/a")\n  b: link("")\n  c: link("  ")\n'
        self.assertEqual(fajtak(sz), [])

    def test_bare_link_horgonnyal_es_cso(self):
        sz = 'formulas:\n  a: link("Cél#Fejezet")\n  b: link("Más|név")\n'
        self.assertEqual(fajtak(sz), [("link", "Cél"), ("link", "Más")])

    def test_ut_literal_feherlista(self):
        sz = ("filters:\n"
              "  and:\n"
              "    - file.path == \"A/B.md\"\n"
              "    - file.path != \"C.md\"\n"
              "    - file.inFolder(\"Mappa\")\n"
              "    - file.folder == \"Mappa/Alá\"\n"
              "    - '\"D.md\" == file.path'\n")
        self.assertEqual(fajtak(sz), [("ut", "A/B.md"), ("ut", "C.md"), ("mappa", "Mappa"), ("mappa", "Mappa/Alá"),
                                      ("ut", "D.md")])

    def test_nem_fehérlistas_ut_kifejezes_figyelmeztetes(self):
        sz = ("filters:\n"
              "  and:\n"
              "    - file.name == \"Cél.md\"\n"
              "    - file.basename.lower() == \"cél\"\n"
              "    - file.path.startsWith(\"Mappa/\")\n"
              "    - file.name.contains(\"él\")\n"
              "    - file.folder.endsWith(\"x\")\n"
              "    - file.name.matches(/^C/i)\n"
              "    - '/^C/.matches(file.basename)'\n")
        hv = hivatkozas.kivon(sz, "base")
        self.assertEqual([(h.fajta, h.muvelet, h.tul, h.cel) for h in hv], [
            ("figy", "==", "name", "Cél.md"), ("figy", "==", "basename", "cél"),
            ("figy", "startsWith", "path", "Mappa/"), ("figy", "contains", "name", "él"),
            ("figy", "endsWith", "folder", "x"), ("figy", "regex", "name", "^C"), ("figy", "regex", "basename", "^C")])

    def test_hibas_yaml_es_hibas_kifejezes_kimarad(self):
        self.assertEqual(fajtak("filters: [\n"), [])
        self.assertEqual(fajtak('filters: \'link("Cél"\'\n'), [])
        self.assertEqual(fajtak(""), [])
        self.assertEqual(fajtak("- lista\n"), [])

    def test_a_nezet_tulajdonsagnevei_nem_kifejezesek(self):
        sz = 'views:\n  - type: table\n    name: "link(\\"Cél\\")"\n    order:\n      - file.name\n'
        self.assertEqual(fajtak(sz), [])

    def test_nezet_szuroje_es_osszesito(self):
        sz = ('summaries:\n  sajat: values.filter(value.hasLink("Cél")).length\n'
              'views:\n  - type: table\n    filters:\n      or:\n        - file.hasLink("Más")\n')
        self.assertEqual(sorted(c for _, c in fajtak(sz)), ["Cél", "Más"])

    def test_md_blokk(self):
        sz = ("# Cím\n\n```base\nfilters: file.hasLink(\"Cél\")\n```\n\n```python\nlink(\"Más\")\n```\n"
              "~~~base\nformulas:\n  x: link(\"Más\")\n~~~\n")
        self.assertEqual(fajtak(sz, "md"), [("link", "Cél"), ("link", "Más")])

    def test_md_blokk_a_frontmatter_utan_es_nyito_nelkul(self):
        sz = "---\ntitle: x\n---\n```base\nfilters: file.hasLink(\"Cél\")\n```\n"
        self.assertEqual(fajtak(sz, "md"), [("link", "Cél")])
        self.assertEqual(fajtak("Szöveg\n", "md"), [])
        self.assertEqual(fajtak("```base\n```\n", "md"), [])

    def test_ismeretlen_fajta(self):
        self.assertEqual(hivatkozas.kivon("filters: link(\"Cél\")\n", "canvas"), [])

    def test_celok_a_szovegsorrendben(self):
        sz = "formulas:\n  b: link(\"Más\")\n  a: link(\"Cél\")\n"
        self.assertEqual(hivatkozas.celok("X.base", sz.encode()), ["Más", "Cél"])
        self.assertEqual(hivatkozas.celok("X.canvas", sz.encode()), [])
        self.assertEqual(hivatkozas.celok("X.md", b"szoveg"), [])
        self.assertEqual(hivatkozas.celok("X.md", b"```base\nfilters: file.hasLink(\"Cl\")\n```\n"), ["Cl"])


class AtirasTest(unittest.TestCase):
    def test_link_literal_barelink_marad_barelink(self):
        sz = 'filters: file.hasLink(link("Cél"))\n'
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(uj, 'filters: file.hasLink(link("Új név"))\n')
        self.assertEqual((er.db, er.blokkolok), (1, []))

    def test_stilus_megmarad_es_minden_mas_bajt(self):
        sz = ("# megjegyzés\n"
              "filters:\n"
              "  and:   # egy\n"
              "    - file.hasLink(link(\"Cél\"))   # kettő\n"
              "    - 'file.hasLink(\"Cél\")'\n"
              "    - \"file.hasLink(link(\\\"Cél\\\"))\"\n"
              "formulas:\n"
              "  k: link('Cél')\n"
              "views:\n"
              "  - type: table\r\n"
              "    name: \"Táblázat\"\n")
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(uj, sz.replace("Cél", "Új név"))           # csak a literálok változnak: stílus, megjegyzés, CRLF
        self.assertEqual(er.db, 4)

    def test_wikilink_a_literalban_alias_es_horgony_marad(self):
        sz = 'formulas:\n  a: \'"[[Cél#Fej|alias]] és [[ Cél ]] ![[Más]]"\'\n'
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(uj, 'formulas:\n  a: \'"[[Új név#Fej|alias]] és [[ Új név ]] ![[Más]]"\'\n')
        self.assertEqual(er.db, 2)

    def test_nem_erintett_nem_valtozik(self):
        sz = 'filters: file.hasLink(link("Más")) && file.hasLink("Nincs ilyen")\n'
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual((uj, er.cserek, er.blokkolok), (sz, [], []))

    def test_elrablas_az_utvonalas_alak_kell(self):
        fajlok = ["Cél.md", "A/Cél.md", "Nézet.base"]
        sz = 'filters: file.hasLink(link("Cél"))\nformulas:\n  x: link("A/Cél")\n'
        uj, er = atir(sz, "base", fajlok, {"Cél.md": "B/Cél.md"})
        self.assertEqual(uj, 'filters: file.hasLink(link("B/Cél"))\nformulas:\n  x: link("A/Cél")\n')
        self.assertEqual(er.db, 1)

    def test_a_base_sajat_mozgasa_is_elrablast_okozhat(self):
        # a `.base` másik mappába költözik, ahol a `Cél` (szegmens-végződés) egy másik fájlra oldódna
        fajlok = ["X/Cél.md", "A/Cél.md", "X/Nézet.base"]
        sz = 'filters: file.hasLink(link("Cél"))\n'
        uj, er = atir(sz, "base", fajlok, {"X/Nézet.base": "Z/Nézet.base"}, forras="X/Nézet.base")
        self.assertEqual((uj, er.blokkolok), ('filters: file.hasLink(link("X/Cél"))\n', []))

    def test_folyam_gyujtemenyben_az_idezett_alak_marad_ervenyes(self):
        sz = "filters: [file.hasLink(link(\"Cél\")), \"x == 1\"]\n"
        uj, er = atir(sz, "base", FAJLOK, {"Cél.md": "Kovács, János.md"})
        self.assertEqual(er.blokkolok, [])
        self.assertEqual(fajtak(uj), [("link", "Kovács, János")])
        self.assertIn("'file.hasLink(link(\"Kovács, János\"))'", uj)

    def test_idezojel_a_nevben(self):
        sz = 'filters: file.hasLink(link("Cél"))\n'
        uj, er = atir(sz, "base", FAJLOK, {"Cél.md": "Az 'új' név.md"})
        self.assertEqual(er.blokkolok, [])
        self.assertEqual(fajtak(uj), [("link", "Az 'új' név")])

    def test_blokk_skalar_blokkol(self):
        sz = 'filters: |\n  file.hasLink(link("Cél"))\n'
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(uj, sz)
        self.assertEqual(len(er.blokkolok), 1)
        self.assertIn("blokk-skalár", er.blokkolok[0])
        sz2 = 'formulas:\n  x: >-\n    link("Cél")\n'
        self.assertEqual(len(atir(sz2, "base", FAJLOK, LEK)[1].blokkolok), 1)

    def test_blokk_skalar_nem_erintett_nem_blokkol(self):
        sz = 'filters: |\n  file.hasLink(link("Más"))\n'
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual((uj, er.blokkolok), (sz, []))

    def test_cimkezett_skalar_blokkol(self):
        sz = 'filters: !!str file.hasLink(link("Cél"))\n'
        self.assertEqual(len(atir(sz, "base", FAJLOK, LEK)[1].blokkolok), 1)

    def test_az_egyszeru_hosszu_sima_skalar_tobb_soron(self):
        sz = 'filters: file.hasLink(\n  link("Cél"))\n'
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(er.blokkolok, [])
        self.assertEqual(fajtak(uj), [("link", "Új név")])

    def test_ut_literal_fajlnal(self):
        sz = 'filters:\n  or:\n    - file.path == "Cél.md"\n    - file.path != "Más.md"\n    - \'"Cél.md" == file.path\'\n'
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(uj, sz.replace('"Cél.md"', '"Új név.md"'))
        self.assertEqual(er.db, 2)

    def test_ut_literal_nfd_felvitel_is_atirodik(self):
        import unicodedata
        sz = 'filters: file.path == "%s"\n' % unicodedata.normalize("NFD", "Cél.md")
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(uj, 'filters: file.path == "Új név.md"\n')

    def test_mappa_literal_csak_mappamozgatasnal(self):
        sz = ('filters:\n  and:\n    - file.inFolder("Tan")\n    - file.folder == "Tan/Alá"\n'
              '    - file.inFolder("Tanár")\n    - file.inFolder("/Tan/")\n')
        lek = {"Tan/a.md": "Új/a.md", "Tan/Alá/b.md": "Új/Alá/b.md"}
        fajlok = ["Tan/a.md", "Tan/Alá/b.md", "Nézet.base"]
        uj, er = atir(sz, "base", fajlok, lek, mappa=("Tan", "Új"))
        self.assertEqual(uj, sz.replace('("Tan")', '("Új")').replace('"Tan/Alá"', '"Új/Alá"').replace('"/Tan/"', '"/Új/"'))
        self.assertEqual(er.db, 3)
        uj2, er2 = atir(sz, "base", fajlok, lek)                 # fájlmozgatásnál a mappa-literál érintetlen
        self.assertEqual((uj2, er2.cserek), (sz, []))

    def test_nev_alapu_szuro_csak_figyelmeztet(self):
        sz = ('filters:\n  and:\n    - file.name == "Cél.md"\n    - file.basename == "Cél"\n'
              '    - file.name.startsWith("Cé")\n    - file.name.matches(/^C/)\n    - file.basename == "Más"\n'
              '    - file.path.contains("él")\n')
        uj, er = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual((uj, er.cserek, er.blokkolok), (sz, [], []))
        self.assertEqual(len(er.figyelmeztetesek), 5)            # a `Más` nem érintett: a fájl neve nem változik
        f = er.figyelmeztetesek[0]
        self.assertEqual((f["ut"], f["hely"]), ("Nézet.base", "filters.and[0]"))
        self.assertIn("Cél.md", f["uzenet"])

    def test_figyelmeztetes_csak_ha_a_nev_valoban_valtozik(self):
        sz = 'filters: file.name.startsWith("Cél")\n'
        _, er = atir(sz, "base", FAJLOK, {"Cél.md": "Cél másképp.md"})      # az új név is `Cél`-lel kezdődik
        self.assertEqual(er.figyelmeztetesek, [])
        _, er = atir(sz, "base", FAJLOK, {"Cél.md": "Más név.md"})
        self.assertEqual(len(er.figyelmeztetesek), 1)

    def test_md_blokk_atirasa_es_a_tobbi_bajt(self):
        sz = ("# Cím\r\nSzöveg [[Cél]]\r\n\r\n```base\r\nfilters: file.hasLink(link(\"Cél\"))\r\nviews:\r\n"
              "  - type: table\r\n```\r\n\r\nUtána `link(\"Cél\")`\r\n")
        uj, er = atir(sz, "md", FAJLOK, LEK, forras="Jegyzet.md")
        self.assertEqual(uj, sz.replace('link("Cél"))\r\nviews', 'link("Új név"))\r\nviews'))
        self.assertEqual(er.db, 1)
        self.assertEqual(hivatkozas.celok("Jegyzet.md", uj.encode()), ["Új név"])

    def test_md_blokk_idezetben(self):
        sz = ("> [!note]\n> ```base\n> filters:\n>   and:\n>     - file.hasLink(link(\"Cél\"))\n> ```\n\nvége\n")
        self.assertEqual(fajtak(sz, "md"), [("link", "Cél")])
        uj, er = atir(sz, "md", FAJLOK, LEK, forras="Jegyzet.md")
        self.assertEqual(uj, sz.replace('"Cél"', '"Új név"'))

    def test_md_blokk_a_frontmatter_utan_es_lezaratlanul(self):
        sz = "---\ntitle: x\n---\n```base\nfilters: file.hasLink(link(\"Cél\"))\n"
        uj, er = atir(sz, "md", FAJLOK, LEK, forras="Jegyzet.md")
        self.assertEqual(uj, sz.replace('"Cél"', '"Új név"'))

    def test_md_blokk_lista_elemben(self):
        sz = "- elem\n  ```base\n  filters: file.hasLink(link(\"Cél\"))\n  ```\n"
        uj, er = atir(sz, "md", FAJLOK, LEK, forras="Jegyzet.md")
        self.assertEqual(uj, sz.replace('"Cél"', '"Új név"'))

    def test_a_blokkon_kivuli_szoveg_nem_valtozik(self):
        sz = '```python\nfile.hasLink(link("Cél"))\n```\n'
        self.assertEqual(atir(sz, "md", FAJLOK, LEK, forras="Jegyzet.md")[0], sz)

    def test_a_proba_celjai_atiras_utan_a_vartak(self):
        sz = 'filters: file.hasLink(link("Cél")) && file.hasLink(link("Más"))\n'
        uj, _ = atir(sz, "base", FAJLOK, LEK)
        self.assertEqual(hivatkozas.celok("X.base", uj.encode()), ["Új név", "Más"])


class LinkTobbertelmuTest(unittest.TestCase):
    """T126 (C29.8): a Bases a `link("X")`-et a SOR fájljának mappájából oldja fel, az átnevezés-terv a `.base` útjából — ha a név
    többértelmű, az átnevezés a nézet sorait másképp szűrheti. A K11 döntéséig **figyelmeztetés** (nem blokkol)."""
    FAJLOK2 = ["A/Cél.md", "B/Cél.md", "Nézet.base"]
    SZ = 'filters: file.hasLink(link("Cél"))\n'

    def test_a_base_kontextusaban_feloldott_fajl_atnevezese_figyelmeztet(self):
        uj, er = atir(self.SZ, "base", self.FAJLOK2, {"A/Cél.md": "A/Új.md"})
        self.assertEqual(er.blokkolok, [])                                  # a figyelmeztetés nem blokkol
        self.assertEqual(len(er.figyelmeztetesek), 1)                        # ma: némán átírja
        f = er.figyelmeztetesek[0]
        self.assertEqual((f["ut"], f["hely"]), ("Nézet.base", "filters"))
        self.assertIn("többértelmű", f["uzenet"])
        self.assertIn("A/Cél.md", f["uzenet"])

    def test_a_masik_mappa_fajljanak_atnevezese_nem_ir_at_de_figyelmeztet(self):
        uj, er = atir(self.SZ, "base", self.FAJLOK2, {"B/Cél.md": "B/Z.md"})
        self.assertEqual((uj, er.cserek, len(er.figyelmeztetesek)), (self.SZ, [], 1))          # ma: 0 — a B/ sorok némán elvesztik

    def test_egyertelmu_nev_nem_figyelmeztet(self):
        for fajlok, lek in ((FAJLOK, LEK),                                           # egyetlen Cél
                            (["Cél.md", "A/Cél.md", "Nézet.base"], {"Cél.md": "B/Cél.md"}),    # a teljes út egyezése nyer, útvonalas átírás
                            (self.FAJLOK2 + ["Más.md"], {"Más.md": "Más 2.md"})):    # nem érintett fájl
            _, er = atir(self.SZ, "base", fajlok, lek)
            self.assertEqual(er.figyelmeztetesek, [], (fajlok, lek))

    def test_md_blokk_es_a_mozgo_base_nem_ad_felesleges_figyelmeztetest(self):
        sz = "```base\nfilters: file.hasLink(link(\"Cél\"))\n```\n"
        _, er = atir(sz, "md", self.FAJLOK2 + ["Jegyzet.md"], {"A/Cél.md": "A/Új.md"}, forras="Jegyzet.md")
        self.assertEqual(len(er.figyelmeztetesek), 1)
        _, er = atir(self.SZ, "base", ["X/Cél.md", "A/Cél.md", "X/Nézet.base"], {"X/Nézet.base": "Z/Nézet.base"},
                     forras="X/Nézet.base")                                          # az útvonalas átírás egyértelmű
        self.assertEqual(er.figyelmeztetesek, [])


class RegexIdokorlatTest(unittest.TestCase):
    """T040 (C29.8, a H5 hibaosztálya): a `.base` szűrőjében álló felhasználói regex az átnevezés-tervben időkorlátos
    (`bazis.ertekek.Regex`: `regex` csomag, `concurrent=True`), nem a stdlib `re`, amely a GIL-t fogva percekig futhat."""

    def test_katasztrofalis_regex_a_tervben_gyors(self):
        nev = "a" * 36 + ".md"
        sz = "filters: file.name.matches(/(a|aa)+$/)\n"
        t0 = time.monotonic()
        _, er = atir(sz, "base", [nev, "Nézet.base"], {nev: "Új.md"})
        self.assertLess(time.monotonic() - t0, 1.5)                    # ma ~3,5 s (36 karakternél kétkarakterenként ×2,6)
        self.assertLessEqual(len(er.figyelmeztetesek), 1)              # a motor gyorsaságától függ, hogy időtúllépés-e (óvatos jelzés)

    def test_idotullepes_ovatosan_erintett_es_mintankent_egyszer_fizet(self):
        from unittest import mock
        from core.bazis.ertekek import Regex
        nevek = [f"{i:02d}" + "a" * 40 + ".md" for i in range(12)]
        sz = "filters: file.name.matches(/(a|aa)+$/)\n"
        t0 = time.monotonic()
        with mock.patch.object(Regex, "IDOKORLAT_MP", 0.05):
            _, er = atir(sz, "base", nevek + ["Nézet.base"], {n: f"Új {i}.md" for i, n in enumerate(nevek)})
        self.assertLess(time.monotonic() - t0, 1.5)                    # 12 × időkorlát helyett egyszer
        self.assertEqual(len(er.figyelmeztetesek), 1)                  # az időtúllépés nem eldönthető: óvatosan érintett
        self.assertIn("(a|aa)+$", er.figyelmeztetesek[0]["uzenet"])


if __name__ == "__main__":
    unittest.main()
