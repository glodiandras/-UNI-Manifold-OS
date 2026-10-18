"""A `.base` modell (`core/bazis/modell.py`, C12 3. lépés): betöltés, hibák, szerializálás, módosítások."""
import unittest
from unittest import mock

import yaml

from core.bazis import modell
from core.bazis.kiertekelo import Kor
from core.bazis.modell import betolt, modosit, szerializal, szuro_fa, szuro_fordit, tulajdonsag_id
from tests.bazis_segedek import MOST, sor, tabla

BOOKS = '''views:
  - type: cards
    name: Books
    filters:
      and:
        - file.tags == ["Book"]
    imageFit: contain
    cardSize: 420
'''

DOKUMENTACIO = '''filters:
  or:
    - file.hasTag("tag")
    - and:
        - file.hasTag("book")
        - file.hasLink("Textbook")
    - not:
        - file.hasTag("book")
        - file.inFolder("Required Reading")
formulas:
  formatted_price: 'if(price, price.toFixed(2) + " dollars")'
  ppu: "(price / age).toFixed(2)"
properties:
  status:
    displayName: Status
  formula.formatted_price:
    displayName: "Price"
  file.ext:
    displayName: Extension
summaries:
  customAverage: 'values.mean().round(3)'
views:
  - type: table
    name: "My table"
    limit: 10
    groupBy:
      property: note.age
      direction: DESC
    filters:
      and:
        - 'status != "done"'
        - or:
            - "formula.ppu > 5"
            - "price > 2.1"
    order:
      - file.name
      - file.ext
      - note.age
      - formula.ppu
      - formula.formatted_price
    summaries:
      formula.ppu: Average
'''


def hibahelyek(hibak):
    return sorted(h["hely"] for h in hibak)


class BetoltTest(unittest.TestCase):
    def test_books_alak(self):
        b, hibak = betolt(BOOKS)
        self.assertEqual(hibak, [])
        self.assertEqual(len(b.nezetek), 1)
        n = b.nezetek[0]
        self.assertEqual((n.nev, n.tipus, n.eredeti_tipus, n.ismert, n.index), ("Books", "cards", "cards", True, 0))
        self.assertEqual(n.kulcs("imageFit"), "contain")
        self.assertEqual(n.kulcs("cardSize"), 420)
        self.assertEqual(n.oszlopok(), ["file.name"])               # nincs `order`: a fájlnév

    def test_dokumentacio_peldaja_hibatlan(self):
        b, hibak = betolt(DOKUMENTACIO)
        self.assertEqual(hibak, [])
        n = b.nezetek[0]
        self.assertEqual(n.oszlopok(), ["file.name", "file.ext", "note.age", "formula.ppu", "formula.formatted_price"])
        self.assertEqual(n.csoport(), ("note.age", "DESC"))
        self.assertEqual(n.kulcs("limit"), 10)
        self.assertEqual(b.megjelenes("formula.formatted_price"), "Price")
        self.assertEqual(b.megjelenes("file.ext"), "Extension")
        self.assertIsNone(b.megjelenes("file.name"))

    def test_ures_szoveg_alap_tablazat(self):
        for sz in ("", "  \n", "{}\n", "views: []\n", "views:\n"):
            b, hibak = betolt(sz)
            self.assertEqual(hibak, [], sz)
            self.assertEqual([(n.tipus, n.nev) for n in b.nezetek], [("table", "Table")], sz)

    def test_ismeretlen_nezettipus_tablazat_figyelmeztetessel(self):
        b, hibak = betolt("views:\n  - type: map\n    name: Térkép\n  - type: list\n  - type: table\n")
        self.assertEqual(hibak, [])
        self.assertEqual([(n.tipus, n.eredeti_tipus, n.ismert) for n in b.nezetek],
                         [("table", "map", False), ("list", "list", True), ("table", "table", True)])
        self.assertEqual(hibahelyek(b.figyelmeztetesek), ["views[0]"])
        self.assertEqual(b.nezetek[1].nev, "View 2")                       # az alapnév angol (10-bases-01)

    def test_kanban_es_board_alias(self):
        b, _ = betolt("views:\n  - type: kanban\n  - type: board\n    name: B\n")
        self.assertEqual([(n.tipus, n.ismert) for n in b.nezetek], [("kanban", True), ("kanban", True)])

    def test_yaml_hiba_vegzetes(self):
        b, hibak = betolt("views:\n  - type: [table\n")
        self.assertTrue(b.vegzetes)
        self.assertEqual(hibahelyek(hibak), ["yaml"])

    def test_yaml_alias_es_tul_melyen_agyazott_yaml_vegzetes_hiba(self):
        """T041 (C29.8): a `.base` betöltője sem enged YAML-aliast (billion laughs), és a mély beágyazás hiba, nem kivétel."""
        b, hibak = betolt("a: &x [1]\nb: *x\n")
        self.assertTrue(b.vegzetes)
        self.assertEqual(hibahelyek(hibak), ["yaml"])
        self.assertIn("alias", hibak[0]["uzenet"])
        b, hibak = betolt("views: " + "[" * 1000 + "]" * 1000 + "\n")
        self.assertTrue(b.vegzetes)
        self.assertEqual(hibahelyek(hibak), ["yaml"])
        b, hibak = betolt("a: &x [1]\nviews:\n  - type: table\n")                # a horgony önmagában inert
        self.assertFalse(b.vegzetes, hibak)

    def test_nem_objektum_gyoker(self):
        b, hibak = betolt("- a\n- b\n")
        self.assertTrue(b.vegzetes)
        self.assertEqual(hibahelyek(hibak), ["yaml"])

    def test_szerkezeti_hibak(self):
        for sz, hely in [("formulas: [a]\n", "formulas"), ("properties: x\n", "properties"), ("summaries: 3\n", "summaries"),
                         ("views: x\n", "views"), ("views:\n  - nem objektum\n", "views[0]")]:
            _, hibak = betolt(sz)
            self.assertEqual(hibahelyek(hibak), [hely], sz)

    def test_szuro_hibak_a_helyukkel(self):
        _, hibak = betolt('filters:\n  and:\n    - price >\n    - nincs_fn(1)\nviews:\n  - type: table\n    filters: 3\n')
        self.assertEqual(hibahelyek(hibak), ["filters.and[0]", "filters.and[1]", "views[0].filters"])

    def test_keplet_hibak(self):
        _, hibak = betolt('formulas:\n  a: "1 +"\n  b: "formula.c"\n  c: "formula.b"\n  d: "nincs(1)"\n  e: "1"\n')
        self.assertEqual(hibahelyek(hibak), ["formulas.a", "formulas.b", "formulas.c", "formulas.d"])

    def test_osszesito_hiba(self):
        _, hibak = betolt('summaries:\n  x: "values.nincs()"\n  y: "values.length"\n')
        self.assertEqual(hibahelyek(hibak), ["summaries.x"])

    def test_nem_szoveg_kulcsok_szoveggye_alakulnak(self):
        b, _ = betolt("1: a\nviews:\n  - type: table\n")
        self.assertIn("1", b.nyers)

    def test_nezet_keres(self):
        b, _ = betolt("views:\n  - name: A\n  - name: Bé\n")
        self.assertEqual(b.nezet_keres(None).nev, "A")
        self.assertEqual(b.nezet_keres(1).nev, "Bé")
        self.assertEqual(b.nezet_keres("bé").nev, "Bé")
        self.assertIsNone(b.nezet_keres(5))
        self.assertIsNone(b.nezet_keres("nincs"))

    def test_nezet_rendezes(self):
        b, _ = betolt("views:\n  - sort:\n      - property: file.name\n        direction: DESC\n      - property: Rating\n"
                      "      - nem: jó\n      - 3\n")
        self.assertEqual(b.nezetek[0].rendezes(), [("file.name", "DESC"), ("Rating", "ASC")])


class AzonositoTest(unittest.TestCase):
    def test_tulajdonsag_id(self):
        for s, v in [("file.name", ("file", "name")), ("note.age", ("note", "age")), ("formula.x", ("formula", "x")),
                     ("status", ("note", "status")), ("a.b", ("note", "a.b")), ("formula.a.b", ("formula", "a.b")),
                     ("file", ("note", "file"))]:
            self.assertEqual(tulajdonsag_id(s), v, s)
            self.assertEqual(tulajdonsag_id(modell.id_szovegbe(*v)), v)


class SzerializalTest(unittest.TestCase):
    def test_books_bajtra_azonos(self):
        self.assertEqual(szerializal(yaml.safe_load(BOOKS)), BOOKS)

    def test_dokumentacio_peldaja_ujrairva_egyenlo_szerkezet(self):
        nyers = betolt(DOKUMENTACIO)[0].nyers
        ujra = szerializal(nyers)
        self.assertEqual(betolt(ujra)[0].nyers, nyers)
        self.assertEqual(szerializal(betolt(ujra)[0].nyers), ujra)             # idempotens
        self.assertEqual(list(betolt(ujra)[0].nyers), list(nyers))              # kulcssorrend

    def test_unicode_es_hosszu_sor_nem_tordelodik(self):
        nyers = {"formulas": {"hosszu": "if(Évszám > 1000, " + "x + " * 60 + "\"ékezet\")"}}
        ki = szerializal(nyers)
        self.assertIn("Évszám", ki)
        self.assertEqual(ki.count("\n"), 2)
        self.assertEqual(yaml.safe_load(ki), nyers)

    def test_listak_behuzva(self):
        self.assertEqual(szerializal({"a": [1, {"b": 2}]}), "a:\n  - 1\n  - b: 2\n")

    def test_idezojeles_kifejezesek_visszaolvashatok(self):
        for kif in ('status != "done"', "it's", 'a: b', '- x', '#tag', '"idézett"', 'true', '123', '2026-01-01', ''):
            ki = szerializal({"k": kif})
            self.assertEqual(modell._yaml(ki), {"k": kif}, kif)


class SzuroTest(unittest.TestCase):
    S = [sor("A/x.md", {"Status": "done", "n": 3}, cimkek=["book"]), sor("B/y.md", {"Status": "todo", "n": 7}),
         sor("B/z.md", {"Status": "done", "n": 9})]

    def ertekel(self, nyers):
        fa, h1 = szuro_fa(nyers, "filters")
        f, h2 = szuro_fordit(fa)
        t = tabla(self.S)
        self.assertEqual(h1 + h2, [])
        return [s.ut for s in t.sorok if f(Kor(sor=s, tabla=t, most=MOST))]

    def test_kifejezes_es_logika(self):
        self.assertEqual(self.ertekel(None), ["A/x.md", "B/y.md", "B/z.md"])
        self.assertEqual(self.ertekel('Status == "done"'), ["A/x.md", "B/z.md"])
        self.assertEqual(self.ertekel({"and": ['Status == "done"', "n > 5"]}), ["B/z.md"])
        self.assertEqual(self.ertekel({"or": ['file.hasTag("book")', "n > 8"]}), ["A/x.md", "B/z.md"])
        self.assertEqual(self.ertekel({"not": ['Status == "done"']}), ["B/y.md"])
        self.assertEqual(self.ertekel({"not": ['Status == "done"', "n > 8"]}), ["B/y.md"])          # egyik sem igaz
        self.assertEqual(self.ertekel({"or": ["n > 8", {"and": ['file.inFolder("A")', 'Status == "done"']}]}),
                         ["A/x.md", "B/z.md"])
        self.assertEqual(self.ertekel(["n > 1", "n < 8"]), ["A/x.md", "B/y.md"])                   # lista: implicit `and`
        self.assertEqual(self.ertekel({"and": []}), ["A/x.md", "B/y.md", "B/z.md"])
        self.assertEqual(self.ertekel({"or": []}), [])

    def test_szerkezeti_hibak(self):
        for ny in ({"and": 3}, {"and": [], "or": []}, {"xor": []}, 3, {}, {"and": [{"x": 1}]}):
            _, h = szuro_fa(ny, "f")
            self.assertTrue(h, repr(ny))

    def test_fordítasi_hiba_hamis_es_jelentett(self):
        fa, _ = szuro_fa({"or": ["nincs_fn(1)", "n > 0"]}, "filters")
        f, hibak = szuro_fordit(fa)
        self.assertEqual(hibahelyek(hibak), ["filters.or[0]"])
        t = tabla(self.S)
        # a hibás utasítás hamis, de a `n > 0` ág még igazzá teheti a sort
        self.assertTrue(f(Kor(sor=t.sorok[0], tabla=t, most=MOST)))

    def test_futasi_hiba_szuro_hibaja_a_hellyel(self):
        fa, _ = szuro_fa({"and": ["n > 0", "[] + 1"]}, "filters")
        f, hibak = szuro_fordit(fa)
        self.assertEqual(hibak, [])
        t = tabla(self.S)
        with self.assertRaises(modell.SzuroHiba) as r:
            f(Kor(sor=t.sorok[0], tabla=t, most=MOST))
        self.assertEqual(r.exception.hely, "filters.and[1]")
        self.assertIn("[] + 1", r.exception.uzenet)


class ModositTest(unittest.TestCase):
    def mod(self, szoveg, **m):
        uj, hibak, valtozas = modosit(szoveg, m)
        self.assertEqual(hibak, [], hibak)
        return uj, valtozas

    def test_nezet_beallit_ismeretlen_kulcs_es_sorrend_megmarad(self):
        sz = BOOKS + "    jovobeli: {a: [1, 2]}\n"
        sz = sz.replace("{a: [1, 2]}", "\n      a:\n        - 1\n        - 2")
        uj, v = self.mod(sz, fajta="nezet_beallit", nezet=0, kulcs="limit", ertek=5)
        self.assertEqual(v, "view limit")
        n = yaml.safe_load(uj)["views"][0]
        self.assertEqual(list(n), ["type", "name", "filters", "imageFit", "cardSize", "jovobeli", "limit"])
        self.assertEqual(n["jovobeli"], {"a": [1, 2]})
        self.assertEqual(n["cardSize"], 420)

    def test_nezet_beallit_torles_es_felulirasa(self):
        uj, _ = self.mod(BOOKS, fajta="nezet_beallit", nezet=0, kulcs="cardSize", ertek=300)
        self.assertEqual(yaml.safe_load(uj)["views"][0]["cardSize"], 300)
        uj, _ = self.mod(uj, fajta="nezet_beallit", nezet=0, kulcs="imageFit", ertek=None)
        self.assertNotIn("imageFit", yaml.safe_load(uj)["views"][0])
        uj, _ = self.mod(uj, fajta="nezet_beallit", nezet=0, kulcs="nem_letezo", ertek=None)      # nincs mit törölni

    def test_alkulcs_egy_oszlop_szelessege(self):
        uj, _ = self.mod(BOOKS, fajta="nezet_beallit", nezet=0, kulcs="columnSize", alkulcs="file.name", ertek=240)
        uj, _ = self.mod(uj, fajta="nezet_beallit", nezet=0, kulcs="columnSize", alkulcs="note.Rating", ertek=90)
        self.assertEqual(yaml.safe_load(uj)["views"][0]["columnSize"], {"file.name": 240, "note.Rating": 90})
        uj, _ = self.mod(uj, fajta="nezet_beallit", nezet=0, kulcs="columnSize", alkulcs="file.name", ertek=None)
        self.assertEqual(yaml.safe_load(uj)["views"][0]["columnSize"], {"note.Rating": 90})
        uj, _ = self.mod(uj, fajta="nezet_beallit", nezet=0, kulcs="columnSize", alkulcs="note.Rating", ertek=None)
        self.assertNotIn("columnSize", yaml.safe_load(uj)["views"][0])

    def test_rendezes_csoport_oszlopok(self):
        uj, _ = self.mod(BOOKS, fajta="nezet_beallit", nezet=0, kulcs="sort",
                         ertek=[{"property": "file.name", "direction": "DESC"}])
        uj, _ = self.mod(uj, fajta="nezet_beallit", nezet=0, kulcs="groupBy", ertek={"property": "Status", "direction": "ASC"})
        uj, _ = self.mod(uj, fajta="nezet_beallit", nezet=0, kulcs="order", ertek=["file.name", "Rating"])
        n = betolt(uj)[0].nezetek[0]
        self.assertEqual((n.rendezes(), n.csoport(), n.oszlopok()),
                         ([("file.name", "DESC")], ("Status", "ASC"), ["file.name", "Rating"]))

    def test_nezet_uj_egyedi_nevvel(self):
        uj, _ = self.mod(BOOKS, fajta="nezet_uj", tipus="table")
        uj, _ = self.mod(uj, fajta="nezet_uj", tipus="table")
        uj, _ = self.mod(uj, fajta="nezet_uj", tipus="kanban")
        uj, _ = self.mod(uj, fajta="nezet_uj", tipus="cards", nev="Books")
        self.assertEqual([(n["type"], n["name"]) for n in yaml.safe_load(uj)["views"]],
                         [("cards", "Books"), ("table", "Table"), ("table", "Table 2"), ("kanban", "Kanban"),
                          ("cards", "Books 2")])

    def test_nezet_uj_ures_fajlban(self):
        uj, _ = self.mod("", fajta="nezet_uj", tipus="cards")
        self.assertEqual([n["type"] for n in yaml.safe_load(uj)["views"]], ["cards"])

    def test_ures_fajlon_masik_muvelet_az_alap_nezetet_is_beirja(self):
        uj, _ = self.mod("", fajta="nezet_beallit", nezet=0, kulcs="limit", ertek=3)
        self.assertEqual(yaml.safe_load(uj)["views"], [{"type": "table", "name": "Table", "limit": 3}])

    def test_nezet_torol_es_mozgat(self):
        sz = "views:\n  - name: A\n  - name: B\n  - name: C\n"
        uj, _ = self.mod(sz, fajta="nezet_mozgat", nezet=2, ujindex=0)
        self.assertEqual([n["name"] for n in yaml.safe_load(uj)["views"]], ["C", "A", "B"])
        uj, _ = self.mod(uj, fajta="nezet_torol", nezet=1)
        self.assertEqual([n["name"] for n in yaml.safe_load(uj)["views"]], ["C", "B"])

    def test_szuro_beallit(self):
        uj, _ = self.mod(BOOKS, fajta="szuro_beallit", hol="globalis", yaml='file.hasTag("x")')
        nyers = yaml.safe_load(uj)
        self.assertEqual(nyers["filters"], 'file.hasTag("x")')
        self.assertEqual(list(nyers), ["views", "filters"])
        uj, _ = self.mod(uj, fajta="szuro_beallit", hol=0, yaml='and:\n  - n > 3\n  - or:\n      - a == "x"\n      - b')
        self.assertEqual(yaml.safe_load(uj)["views"][0]["filters"], {"and": ["n > 3", {"or": ['a == "x"', "b"]}]})
        uj, _ = self.mod(uj, fajta="szuro_beallit", hol="globalis", yaml="")
        self.assertNotIn("filters", yaml.safe_load(uj))

    def test_szuro_beallit_yaml_nelkuli_kifejezesek(self):
        for kif in ('"a" == b', '!completed', 'file.tags == ["Book"]', 'status != "done" && n > 3', "[1, 2].contains(x)",
                    'a == "x" # nem megjegyzés'.replace(" # nem megjegyzés", "")):
            uj, _ = self.mod(BOOKS, fajta="szuro_beallit", hol=0, yaml=kif)
            self.assertEqual(yaml.safe_load(uj)["views"][0]["filters"], kif, kif)

    def test_szuro_hibas_nem_ir(self):
        for yml in ("price >", "nincs_fn(1)", "and: 3", "xor:\n  - a"):
            uj, hibak, _ = modosit(BOOKS, {"fajta": "szuro_beallit", "hol": 0, "yaml": yml})
            self.assertEqual(uj, BOOKS, yml)
            self.assertTrue(hibak, yml)
            self.assertTrue(all(h["hely"].startswith("views[0].filters") for h in hibak), (yml, hibak))

    def test_keplet_beallit_es_torles_takaritassal(self):
        sz = ('formulas:\n  ppu: price / 2\nproperties:\n  formula.ppu:\n    displayName: PPU\nviews:\n  - type: table\n'
              '    order:\n      - file.name\n      - formula.ppu\n    columnSize:\n      formula.ppu: 100\n'
              '    summaries:\n      formula.ppu: Sum\n  - type: cards\n')
        uj, _ = self.mod(sz, fajta="keplet_beallit", nev="uj", kifejezes="formula.ppu * 2")
        self.assertEqual(yaml.safe_load(uj)["formulas"], {"ppu": "price / 2", "uj": "formula.ppu * 2"})
        uj, v = self.mod(uj, fajta="keplet_beallit", nev="ppu", kifejezes="price / 3")
        self.assertEqual(yaml.safe_load(uj)["formulas"]["ppu"], "price / 3")
        uj, v = self.mod(sz, fajta="keplet_beallit", nev="ppu", kifejezes=None)
        n = yaml.safe_load(uj)
        self.assertNotIn("formulas", n)
        self.assertNotIn("properties", n)
        self.assertEqual(n["views"][0]["order"], ["file.name"])
        self.assertNotIn("columnSize", n["views"][0])
        self.assertNotIn("summaries", n["views"][0])
        self.assertEqual(v, "formula deleted")

    def test_keplet_hibas_nem_ir(self):
        for kif, hely in [("1 +", "formulas.x"), ("nincs_fn(1)", "formulas.x"), ("formula.x", "formulas.x")]:
            uj, hibak, _ = modosit(BOOKS, {"fajta": "keplet_beallit", "nev": "x", "kifejezes": kif})
            self.assertEqual(uj, BOOKS, kif)
            self.assertEqual(hibahelyek(hibak), [hely], kif)

    def test_megjelenites_beallit(self):
        uj, _ = self.mod(BOOKS, fajta="megjelenites_beallit", id="file.name", displayName="Cím")
        self.assertEqual(yaml.safe_load(uj)["properties"], {"file.name": {"displayName": "Cím"}})
        uj, _ = self.mod(uj, fajta="megjelenites_beallit", id="file.name", displayName=None)
        self.assertNotIn("properties", yaml.safe_load(uj))

    def test_rossz_muveletek(self):
        for m in [{"fajta": "nincs"}, {}, {"fajta": "nezet_beallit", "nezet": 7, "kulcs": "x", "ertek": 1},
                  {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "", "ertek": 1}, {"fajta": "nezet_torol", "nezet": "0"},
                  {"fajta": "nezet_mozgat", "nezet": 0, "ujindex": 9}, {"fajta": "keplet_beallit", "nev": ""},
                  {"fajta": "keplet_beallit", "nev": "x", "kifejezes": 5}, {"fajta": "megjelenites_beallit", "id": ""},
                  {"fajta": "szuro_beallit", "hol": 5, "yaml": "a"}, {"fajta": "szuro_beallit", "yaml": 5}]:
            uj, hibak, _ = modosit(BOOKS, m)
            self.assertEqual(uj, BOOKS, m)
            self.assertEqual(hibahelyek(hibak), ["muvelet"], m)
        uj, hibak, _ = modosit(BOOKS, "nem objektum")                                  # type: ignore[arg-type]
        self.assertEqual((uj, hibahelyek(hibak)), (BOOKS, ["muvelet"]))

    def test_nem_ertelmezheto_fajl_nem_modosul(self):
        for sz in ("views:\n  - type: [table\n", "- lista\n"):
            uj, hibak, _ = modosit(sz, {"fajta": "nezet_uj"})
            self.assertEqual((uj, hibahelyek(hibak)), (sz, ["yaml"]))

    def test_visszaolvasas_proba(self):
        with mock.patch.object(modell, "szerializal", return_value="views: [\n"):
            uj, hibak, _ = modosit(BOOKS, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 1})
        self.assertEqual((uj, hibahelyek(hibak)), (BOOKS, ["yaml"]))
        with mock.patch.object(modell, "szerializal", return_value="views: []\n"):
            uj, hibak, _ = modosit(BOOKS, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 1})
        self.assertEqual((uj, hibahelyek(hibak)), (BOOKS, ["yaml"]))

    def test_a_korabbi_hiba_nem_akadalyoz(self):
        sz = ('views:\n  - type: table\n    name: Jó\n  - type: table\n    name: Rossz\n    filters: "price >"\n')
        uj, hibak, _ = modosit(sz, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 2})
        self.assertEqual(hibak, [])
        self.assertIn("limit: 2", uj)

    def test_a_bemenet_nem_modosul(self):
        sz = BOOKS
        modosit(sz, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 1})
        self.assertEqual(sz, BOOKS)

    def test_idempotens_ugyanaz_a_muvelet_kétszer(self):
        m = {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 4}
        egyszer, _, _ = modosit(BOOKS, m)
        ketszer, _, _ = modosit(egyszer, m)
        self.assertEqual(egyszer, ketszer)


if __name__ == "__main__":
    unittest.main()
