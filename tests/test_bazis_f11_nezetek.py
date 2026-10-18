"""F11 Bases-sorok (10-bases-01/02/05/07/10/13): angol alapértékek és kódolt hibák, List nézet, groupOrder, az új jegyzet
előtöltése, szerkesztő-segítség, az indexből jövő `file.ctime`. Szintetikus vaultok, a valódi vault nem érintett."""
import ast
import os
import re
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import yaml

from core import vaultio
from core.bazis import fuggvenyek as fn
from core.bazis import modell
from core.bazis.api import Bazisok
from core.bazis.elotoltes import elotoltes
from core.bazis.kifejezes import KifejezesHiba, elemez
from core.bazis.ertekek import FutasHiba
from core.bazis.modell import betolt, modosit
from core.hibakod import angol_uzenet
from core.hibauzenetek import ANGOL
from tests.bazis_segedek import ertek, sor, tabla
from tests.test_bazis_lekerdezes import _Alap

REPO = Path(__file__).resolve().parent.parent
HELYORZO = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
EKEZETES = re.compile("[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")


class AngolAlapertekekTest(unittest.TestCase):
    """10-bases-01 (a): új fájlokban és hiányzó nevekre angol az alapnév; a régi magyar nevű fájl változatlan."""

    def test_uj_base_es_alap_nezet_angol(self):
        self.assertEqual(modell.UJ_SZOVEG, "views:\n  - type: table\n    name: Table\n")
        self.assertEqual(vaultio.UJ_BASE, modell.UJ_SZOVEG)
        b, _ = betolt("")
        self.assertEqual([n.nev for n in b.nezetek], ["Table"])

    def test_uj_nezet_angol_nevei_es_szamozasa(self):
        sz = ""
        for tipus in ("table", "cards", "list", "kanban", "table"):
            sz, hibak, _ = modosit(sz, {"fajta": "nezet_uj", "tipus": tipus})
            self.assertEqual(hibak, [])
        self.assertEqual([(n["type"], n["name"]) for n in yaml.safe_load(sz)["views"]],
                         [("table", "Table"), ("cards", "Cards"), ("list", "List"), ("kanban", "Kanban"), ("table", "Table 2")])

    def test_nev_nelkuli_nezet_angol_sorszamot_kap(self):
        b, _ = betolt("views:\n  - type: table\n  - type: cards\n")
        self.assertEqual([n.nev for n in b.nezetek], ["View 1", "View 2"])

    def test_a_regi_magyar_nevu_fajl_valtozatlan_olvashato_es_marad_az_ujrairaskor(self):
        regi = "views:\n  - type: table\n    name: Táblázat\n"
        b, hibak = betolt(regi)
        self.assertEqual((hibak, b.nezetek[0].nev), ([], "Táblázat"))
        uj, hibak, _ = modosit(regi, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 5})
        self.assertEqual(hibak, [])
        self.assertEqual(yaml.safe_load(uj)["views"][0]["name"], "Táblázat")

    def test_alap_oszlopfejlecek_angolok_a_core_ben_es_jelzettek(self):
        from core.bazis.lekerdezes import FAJL_NEV
        self.assertFalse([v for v in FAJL_NEV.values() if EKEZETES.search(v)])
        self.assertEqual(FAJL_NEV["name"], "File name")


class KodoltHibakTest(unittest.TestCase):
    """10-bases-01 (c): minden motorhiba `kod` + `param` + angol tartalék; a kód katalógusban van, a paraméterek egyeznek."""

    def test_katalogus_minden_literal_kodra(self):
        """Statikus ellenőrzés: a core/bazis alatt minden literális hibakód szerepel az ANGOL szótárban, a `{param}`-ok
        egyeznek a megadott kulcsokkal, és az angol mondat ékezetmentes magyar szó nélkül."""
        kivetelek = {"FutasHiba", "KifejezesHiba", "MuveletHiba", "IdokeretHiba", "ErtekKeretHiba", "SzuroHiba"}
        talalt = 0
        for p in (REPO / "core" / "bazis").glob("*.py"):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                nev = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                kod = param = None
                if nev in kivetelek and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    kod = n.args[0].value
                    idx = 1 if nev in ("FutasHiba", "MuveletHiba") else 2 if nev == "KifejezesHiba" else None
                    param = n.args[idx] if idx is not None and len(n.args) > idx else \
                        next((k.value for k in n.keywords if k.arg == "param"), None)
                elif nev in ("hiba", "hiba_kivetelbol"):
                    kw = {k.arg: k.value for k in n.keywords}
                    if isinstance(kw.get("kod"), ast.Constant):
                        kod, param = kw["kod"].value, kw.get("param")
                if kod is None:
                    continue
                talalt += 1
                with self.subTest(fajl=p.name, sor=n.lineno, kod=kod):
                    self.assertIn(kod, ANGOL)
                    kulcsok = {k.value for k in param.keys if isinstance(k, ast.Constant)} if isinstance(param, ast.Dict) else set()
                    if isinstance(param, ast.Dict) or param is None:
                        self.assertFalse(set(HELYORZO.findall(ANGOL[kod])) - kulcsok - {"hely"} if kod != "bazis.kifejezes.hely" else set())
        self.assertGreater(talalt, 80)

    def test_az_angol_tartalek_nem_tartalmaz_ekezetes_magyar_szoveget(self):
        for kod, szoveg in ANGOL.items():
            if kod.startswith("bazis."):
                with self.subTest(kod=kod):
                    self.assertIsNone(EKEZETES.search(szoveg), szoveg)

    def test_kifejezeshiba_kod_param_es_angol_szoveg(self):
        for forras, kod, param in [("(a", "bazis.kifejezes.hianyzik", {"mit": ")"}), ("", "bazis.kifejezes.ures", {}),
                                   ('"abc', "bazis.kifejezes.lezaratlan_szoveg", {}), ("a +", "bazis.kifejezes.varatlan", {"mit": "end of expression"}),
                                   ("#", "bazis.kifejezes.varatlan_karakter", {"c": "'#'"}), ("1a", "bazis.kifejezes.szam_utan_betu", {}),
                                   ("nincs_fn(1)", None, None)]:
            with self.subTest(forras):
                if kod is None:
                    from core.bazis.kiertekelo import fordit_szoveg
                    with self.assertRaises(KifejezesHiba) as r:
                        fordit_szoveg(forras)
                    kod, param = "bazis.kifejezes.ismeretlen_fuggveny", {"nev": "nincs_fn"}
                else:
                    with self.assertRaises(KifejezesHiba) as r:
                        elemez(forras)
                self.assertEqual((r.exception.kod, r.exception.param), (kod, param))
                self.assertEqual(r.exception.uzenet, angol_uzenet(kod, param))
                self.assertIsNone(EKEZETES.search(r.exception.uzenet))

    def test_futashiba_kod_param(self):
        esetek = [("[] + 1", "bazis.futas.nem_osszeadhato", {"a": "list", "b": "number"}),
                  ("nincs.x.y()", None, None), ("number(\"x\")", "bazis.futas.number_alakitas", {"ertek": "'x'"}),
                  ("date(1)", "bazis.futas.szoveg_kell", {"nev": "date", "tipus": "number"}),
                  ("(1).toFixed(200)", "bazis.futas.tofixed_pontossag", {}),
                  ('"a".sum()', "bazis.futas.nincs_metodus", {"tipus": "text", "nev": "sum"})]
        for kif, kod, param in esetek:
            if kod is None:
                continue
            with self.subTest(kif), self.assertRaises(FutasHiba) as r:
                ertek(kif)
            self.assertEqual((r.exception.kod, r.exception.param), (kod, param))
            self.assertEqual(r.exception.uzenet, angol_uzenet(kod, param))

    def test_hibak_listaja_hordoz_kodot_es_parametert(self):
        b, hibak = betolt("views:\n  - type: table\n    filters: 'a == '\nformulas:\n  x: '1 +'\nsummaries:\n  s: '(('\n")
        egy = {h["hely"]: h for h in hibak}
        self.assertEqual(egy["views[0].filters"]["kod"], "bazis.modell.szuro_utasitas")
        self.assertEqual(egy["views[0].filters"]["param"]["szoveg"], "a == ")
        self.assertIn("Unexpected", egy["views[0].filters"]["uzenet"])
        self.assertEqual(egy["formulas.x"]["kod"], "bazis.modell.keplet_hiba")
        self.assertEqual(egy["summaries.s"]["kod"], "bazis.modell.osszesito_hiba")
        for h in hibak:
            self.assertIsNone(EKEZETES.search(h["uzenet"]), h)
        _, hibak = betolt("views:\n  - type: [table\n")
        self.assertEqual((hibak[0]["hely"], hibak[0]["kod"]), ("yaml", "bazis.modell.yaml_hiba"))

    def test_muvelet_hiba_kodolt(self):
        _, hibak, _ = modosit("views:\n  - name: A\n", {"fajta": "nezet_torol", "nezet": 7})
        self.assertEqual((hibak[0]["kod"], hibak[0]["param"]), ("bazis.modell.nincs_nezet", {"nezet": "7"}))
        self.assertEqual(hibak[0]["uzenet"], "There is no such view: 7")
        _, hibak, _ = modosit("", {"fajta": "?"})
        self.assertEqual(hibak[0]["kod"], "bazis.modell.ismeretlen_muvelet")

    def test_katalogus_angol_kulonbseg_az_app_szotarral(self):
        """Az app `hiba.bazis.*` kulcsai (ha vannak) azonosak a core angol szövegével."""
        import json
        for p in (REPO / "app/src/lib/i18n/en").glob("*.json"):
            for k, v in json.loads(p.read_text()).items():
                if k.startswith("hiba.bazis."):
                    with self.subTest(kulcs=k):
                        self.assertEqual(ANGOL.get(k[5:]), v)


class ListaNezetTest(_Alap):
    """10-bases-02: `type: list` ismert nézettípus, a lekérdezés a táblázatéval azonos adatot ad."""

    def test_list_ismert_tipus_figyelmeztetes_nelkul(self):
        b, hibak = betolt("views:\n  - type: list\n    name: L\n    markers: numbers\n    separator: ' | '\n")
        self.assertEqual((hibak, b.figyelmeztetesek), ([], []))
        self.assertEqual((b.nezetek[0].tipus, b.nezetek[0].ismert), ("list", True))

    def test_lekerdezes_lista_nezetre(self):
        v = self.fut('views:\n  - type: list\n    filters: file.inFolder("X03 - Books")\n    order: [file.name, Status]\n')
        self.assertEqual((v["nezet"]["tipus"], v["nezet"]["eredeti_tipus"], v["figyelmeztetesek"]), ("list", "list", []))
        self.assertEqual([n["tipus"] for n in v["nezetek"]], ["list"])
        self.assertEqual(self.nevek(v)[:2], ["Atomic Habits", "Books"])

    def test_ismeretlen_kulcsok_a_list_nezetben_megmaradnak_az_ujrairaskor(self):
        sz = "views:\n  - type: list\n    name: L\n    markers: numbers\n    indentProperties: true\n    separator: ', '\n"
        uj, hibak, _ = modosit(sz, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 3})
        self.assertEqual(hibak, [])
        n = yaml.safe_load(uj)["views"][0]
        self.assertEqual((n["markers"], n["indentProperties"], n["separator"], n["limit"]), ("numbers", True, ", ", 3))
        # a nézet típusa váltható és vissza
        uj, hibak, _ = modosit(uj, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "type", "ertek": "table"})
        uj, hibak, _ = modosit(uj, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "type", "ertek": "list"})
        self.assertEqual(yaml.safe_load(uj)["views"][0]["markers"], "numbers")


class CsoportSorrendTest(_Alap):
    """10-bases-05: `groupOrder` – felsorolt sorrend, üres csoport, rejtett csoport, `null` = nincs érték."""

    def csoportok(self, order=None, extra=""):
        go = "" if order is None else "    groupOrder: " + order + "\n"
        v = self.fut('views:\n  - type: table\n    filters: file.inFolder("X03 - Books") && file.ext == "md"\n'
                     '    order: [file.name, Status]\n    groupBy:\n      property: Status\n      direction: ASC\n' + go + extra)
        return v

    def test_kulcs_nelkul_minden_csoport_a_groupby_sorrendjeben(self):
        v = self.csoportok()
        self.assertEqual([c["cimke"] for c in v["csoportok"]], ["Done", "Reading"])
        self.assertEqual(v["rejtett_csoportok"], [])

    def test_a_felsorolt_sorrend_a_csoportokat_atrendezi(self):
        v = self.csoportok('["Reading", "Done"]')
        self.assertEqual([(c["cimke"], c["db"]) for c in v["csoportok"]], [("Reading", 1), ("Done", 2)])
        self.assertEqual(self.nevek(v), ["Atomic Habits", "Deep Work", "Sapiens"])
        tol = [(c["cimke"], c["tol"]) for c in v["csoportok"]]
        self.assertEqual(tol, [("Reading", 0), ("Done", 1)])

    def test_a_fel_nem_sorolt_csoport_rejtett_a_sorai_nem_latszanak(self):
        v = self.csoportok('["Done"]')
        self.assertEqual([c["cimke"] for c in v["csoportok"]], ["Done"])
        self.assertEqual(self.nevek(v), ["Deep Work", "Sapiens"])
        self.assertEqual(v["rejtett_csoportok"], [{"kulcs": "Reading", "cimke": "Reading", "db": 1}])
        self.assertEqual(v["osszes"], 2)

    def test_az_ures_lista_minden_csoportot_elrejt(self):
        v = self.csoportok("[]")
        self.assertEqual((v["csoportok"], v["sorok"], v["osszes"]), ([], [], 0))
        self.assertEqual({c["cimke"] for c in v["rejtett_csoportok"]}, {"Done", "Reading"})

    def test_sor_nelkuli_felsorolt_csoport_ures_csoportkent_latszik(self):
        v = self.csoportok('["Reading", "Backlog", "Done"]')
        self.assertEqual([(c["cimke"], c["db"]) for c in v["csoportok"]], [("Reading", 1), ("Backlog", 0), ("Done", 2)])

    def test_null_az_ures_ertek_csoportja(self):
        v = self.fut('views:\n  - type: table\n    filters: file.ext == "md" && (file.name == "Rossz.md" || file.name == "Inline.md" || file.name == "Sapiens.md")\n'
                     '    order: [file.name, Rating]\n    groupBy:\n      property: Rating\n    groupOrder: [5, null]\n')
        self.assertEqual([(c["kulcs"], c["db"]) for c in v["csoportok"]][:1], [(5, 1)])
        self.assertIn(None, [c["kulcs"] for c in v["csoportok"]])
        # a „n/a” szöveges értékű Rossz.md nincs a felsoroltak közt: rejtett
        self.assertEqual([c["cimke"] for c in v["rejtett_csoportok"]], ["n/a"])

    def test_nem_lista_groupOrder_figyelmeztetes_es_minden_csoport(self):
        b, hibak = betolt("views:\n  - type: table\n    groupOrder: abc\n")
        self.assertEqual(hibak, [])
        self.assertEqual([f["kod"] for f in b.figyelmeztetesek], ["bazis.modell.csoportrend_lista"])
        self.assertIsNone(b.nezetek[0].csoport_sorrend())

    def test_group_order_irasa_a_meglevo_muveleten_at_es_visszaolvasas(self):
        sz = "views:\n  - type: table\n    groupBy:\n      property: Status\n    sort:\n      - property: file.name\n"
        uj, hibak, _ = modosit(sz, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "groupOrder", "ertek": ["Reading", None, "Done"]})
        self.assertEqual(hibak, [])
        n = yaml.safe_load(uj)["views"][0]
        self.assertEqual(n["groupOrder"], ["Reading", None, "Done"])
        self.assertEqual(n["sort"], [{"property": "file.name"}])
        self.assertEqual(betolt(uj)[0].nezetek[0].csoport_sorrend(), ["Reading", None, "Done"])
        uj2, hibak, _ = modosit(uj, {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "groupOrder", "ertek": []})
        self.assertEqual(yaml.safe_load(uj2)["views"][0]["groupOrder"], [])


class ElotoltesTest(unittest.TestCase):
    """10-bases-07: a „New” előtöltése csak egyértelmű konjunktív feltételekből."""

    def el(self, sz, nezet=0):
        b, hibak = betolt(sz)
        self.assertEqual(hibak, [])
        return elotoltes(b, b.nezetek[nezet])

    def test_egyenloseg_tag_es_mappa(self):
        r = self.el('filters: file.hasTag("book")\nviews:\n  - type: table\n    filters:\n      and:\n'
                    '        - \'Status == "Reading"\'\n        - note.Pages == 300\n        - \'file.inFolder("Books/Read")\'\n'
                    '        - \'note["Done"] == true\'\n')
        self.assertEqual(r["mappa"], "Books/Read")
        self.assertEqual(r["cimkek"], ["book"])
        self.assertEqual(r["tulajdonsagok"], [{"kulcs": "Status", "ertek": "Reading", "tipus": "text"},
                                              {"kulcs": "Pages", "ertek": 300, "tipus": "number"},
                                              {"kulcs": "Done", "ertek": True, "tipus": "checkbox"}])
        self.assertEqual(r["nem_egyertelmu"], [])

    def test_fordított_sorrend_es_file_folder(self):
        r = self.el('views:\n  - type: table\n    filters:\n      - \'"Reading" == Status\'\n      - \'file.folder == "Inbox"\'\n')
        self.assertEqual((r["mappa"], [t["kulcs"] for t in r["tulajdonsagok"]]), ("Inbox", ["Status"]))

    def test_or_not_es_nem_literal_kimarad(self):
        r = self.el('views:\n  - type: table\n    filters:\n      or:\n        - \'Status == "a"\'\n        - \'Status == "b"\'\n')
        self.assertEqual(r["tulajdonsagok"], [])
        r = self.el('views:\n  - type: table\n    filters:\n      and:\n        - not:\n            - \'Status == "a"\'\n'
                    '        - \'Author == this.file.name\'\n        - \'file.hasTag("a", "b")\'\n        - \'Status != "x"\'\n')
        self.assertEqual((r["tulajdonsagok"], r["cimkek"], r["mappa"]), ([], [], None))

    def test_ellentmondo_kulcs_nem_toltodik_elo(self):
        r = self.el('filters: \'Status == "a"\'\nviews:\n  - type: table\n    filters: \'Status == "b"\'\n')
        self.assertEqual((r["tulajdonsagok"], r["nem_egyertelmu"]), ([], ["Status"]))
        r = self.el('filters: \'file.inFolder("A")\'\nviews:\n  - type: table\n    filters: \'file.inFolder("B")\'\n')
        self.assertEqual((r["mappa"], r["nem_egyertelmu"]), (None, ["file.folder"]))

    def test_a_valaszban_a_fajl_elotoltes_mezo(self):
        with mock.patch.object(Bazisok, "__init__", lambda self: None):
            pass
        from core.bazis.lekerdezes import futtat
        b, _ = betolt('views:\n  - type: kanban\n    groupBy:\n      property: Status\n    filters: \'Status == "x"\'\n')
        v = futtat(b, tabla([sor("a.md", {"Status": "x"})]), b.nezetek[0])
        self.assertEqual(v["fajl"]["elotoltes"]["tulajdonsagok"], [{"kulcs": "Status", "ertek": "x", "tipus": "text"}])


class SzerkesztoSegitsegTest(_Alap):
    """10-bases-10: a függvénylista a regisztrációból, lekérdezés nélkül, a meglévő végponton."""

    def test_fuggveny_lista_alak_es_arity(self):
        lista = fn.fuggveny_lista()
        egy = {(f["tipus"], f["nev"]): f for f in lista}
        self.assertEqual((egy[("list", "filter")]["min"], egy[("global", "date")]["max"]), (None, 1))        # a lusta metódus nem ellenőrzött
        self.assertEqual((egy[("file", "hasTag")]["min"], egy[("file", "hasTag")]["max"]), (1, None))
        self.assertEqual((egy[("string", "contains")]["min"], egy[("string", "contains")]["max"]), (1, 1))
        self.assertEqual(len(lista), len(fn.GLOBALIS) + sum(len(v) for v in fn.METODUSOK.values()) + sum(len(v) for v in fn.LUSTA_METODUSOK.values()))
        self.assertEqual(lista, sorted(lista, key=lambda f: (f["nev"].casefold(), f["tipus"])))
        self.assertTrue(all(set(f) == {"nev", "tipus", "min", "max"} for f in lista))

    def test_lekerdez_segitseg_nem_futtat_lekerdezest(self):
        a = Bazisok(self.cfg, self.ix)
        v = a.lekerdez({"segitseg": True})
        self.assertTrue(v["ok"])
        self.assertIn(("global", "date"), {(f["tipus"], f["nev"]) for f in v["fuggvenyek"]})
        self.assertNotIn("sorok", v)


class SzuletesiIdoIndexbolTest(_Alap):
    """10-bases-13: `file.ctime` az index `ctime_ns` oszlopából; ismeretlen = null; nincs mtime-helyettesítés."""

    def ctime_cella(self, fajl="doc.pdf"):
        v = self.fut(f'views:\n  - type: table\n    order: [file.ctime, file.mtime]\n    filters: file.name == "{fajl}"\n')
        return v["sorok"][0]["cellak"]

    def test_az_ertek_az_indexbol_jon(self):
        with self.ix.olvaso() as c:
            ns = c.execute("SELECT ctime_ns FROM fajl WHERE ut = 'doc.pdf'").fetchone()[0]
        self.assertTrue(ns, "a szintetikus index kitölti a születési időt, ha a rendszer ismeri")
        cellak = self.ctime_cella()
        self.assertEqual(cellak[0]["iso"], datetime.fromtimestamp(ns / 1e9).isoformat(timespec="seconds"))

    def test_nincs_fajlrendszer_hivas_lekerdezeskor(self):
        igazi = os.stat

        def stat(p, *a, **kw):
            if str(p).endswith("doc.pdf"):
                raise AssertionError("a Bases nem stat-olja a sorok fájljait")
            return igazi(p, *a, **kw)
        with mock.patch("os.stat", side_effect=stat):
            self.ctime_cella()

    def test_ismeretlen_szuletesi_ido_ures_nem_mtime(self):
        self.tar.tabla().ut_szerint["doc.pdf"].ctime_ns = None
        cellak = self.ctime_cella()
        self.assertIsNone(cellak[0])
        self.assertEqual(cellak[1]["t"], "datum")                                    # az mtime külön oszlop, érintetlen

    def test_szuro_es_rendezes_ismeretlen_ctime_mellett_nem_hibas(self):
        self.tar.tabla().ut_szerint["doc.pdf"].ctime_ns = None
        v = self.fut('views:\n  - type: table\n    filters: file.ctime < now() + "1d"\n    sort:\n      - property: file.ctime\n')
        self.assertNotIn("doc.pdf", self.utak(v))                                      # az üres ctime nem felel meg a feltételnek
        self.assertEqual(v["hibak"], [])

    def test_mentes_utan_az_inkrementalis_frissites_megorzi_a_valos_ctime_t(self):
        (self.v / "Notes" / "Inline.md").write_text("Egy inline #Book címke.\nmásik sor\n", encoding="utf-8")
        self.assertTrue(self.ix.frissit(["Notes/Inline.md"]))
        t = self.tar.tabla()
        with self.ix.olvaso() as c:
            ns = c.execute("SELECT ctime_ns FROM fajl WHERE ut = 'Notes/Inline.md'").fetchone()[0]
        self.assertEqual(t.ut_szerint["Notes/Inline.md"].ctime_ns, ns)

    def test_tabla_ctime_egysegteszt(self):
        t = tabla([sor("a.md", ctime=datetime(2026, 8, 1, 10, 0, 0)), sor("b.md")])
        self.assertEqual(t.ctime(t.ut_szerint["a.md"]).ertek, datetime(2026, 8, 1, 10, 0, 0))
        self.assertIsNone(t.ctime(t.ut_szerint["b.md"]))


if __name__ == "__main__":
    unittest.main()
