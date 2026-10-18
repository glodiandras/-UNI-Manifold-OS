"""A Bases-lekérdezés valódi indexen (`core/bazis/lekerdezes.py`, `adat.Tar`, az index Bases-bővítései; C12 4. lépés):
álvault, nem md fájl is sor, globális ÉS nézet-szűrő, limit a rendezés után, csoport-összesítő, hibás sor."""
import os
import time
import unittest
from datetime import datetime
from unittest import mock

from core.bazis.adat import Tar
from core.bazis.lekerdezes import futtat
from core.bazis.modell import betolt
from tests.helpers import tmpdir
from tests.index_segedek import alvault, index_indit, var_ra

FAJLOK = {
    "X03 - Books/Atomic Habits.md": ("---\nTags:\n  - Book\nStatus: Reading\nRating: 4.5\nPages: 320\nAuthor: \"[[James Clear]]\"\n"
                                     "Started: 2026-09-01\ncover: \"[[atomic.jpg]]\"\n---\n# Atomic\n"),
    "X03 - Books/Deep Work.md": "---\nTags:\n  - Book\nStatus: Done\nRating: 4\nPages: 300\nAuthor: \"[[Cal Newport]]\"\n---\n",
    "X03 - Books/Sapiens.md": "---\nTags:\n  - Book\nStatus: Done\nRating: 5\nPages: 500\nAuthor: \"[[Harari]]\"\n---\n",
    "X03 - Books/Books.base": "views:\n  - type: cards\n    name: Books\n    filters:\n      and:\n        - file.tags == [\"Book\"]\n",
    "People/James Clear.md": "---\nBorn: 1986\n---\n",
    "People/Cal Newport.md": "# Cal\n",
    "Projects/Alpha.md": "---\nTags:\n  - Project\nStatus: Active\nHours: 10\n---\n",
    "Projects/Beta.md": "---\nTags:\n  - Project\nStatus: Done\nHours: 4\n---\n",
    "Notes/Inline.md": "Egy inline #Book címke.\n",
    "Notes/Hivatkozo.md": "[[Alpha]] és [[Deep Work]]\n",
    "Notes/Rossz.md": "---\nStatus: Done\nRating: n/a\n---\n",
    "kep/atomic.jpg": b"\xff\xd8\xff\xe0JPEG",
    "doc.pdf": b"%PDF-1.4\n",
    "Blokk.md": "```base\nviews:\n  - type: table\n```\n",
    "Blokk2.md": "```BASE\nviews: []\n```\n```js\nx\n```\n",
}


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, FAJLOK)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.tar = Tar(self.ix)

    def fut(self, szoveg, nezet=None, ez_ut=None, **kw):
        bazis, hibak = betolt(szoveg)
        self.assertFalse(bazis.vegzetes, hibak)
        v = futtat(bazis, self.tar.tabla(), bazis.nezet_keres(nezet), ez_ut, **kw)
        v["betolt_hibak"] = hibak
        return v

    @staticmethod
    def utak(v):
        return [s["ut"] for s in v["sorok"]]

    @staticmethod
    def nevek(v):
        return [s["nev"] for s in v["sorok"]]


class SzuresTest(_Alap):
    def test_books_alak_a_file_tags_az_inline_cimket_is_latja(self):
        v = self.fut(FAJLOK["X03 - Books/Books.base"])
        self.assertEqual(self.nevek(v), ["Atomic Habits", "Deep Work", "Inline", "Sapiens"])
        self.assertEqual((v["nezet"]["tipus"], v["nezet"]["nev"], v["osszes"], v["levagva"]), ("cards", "Books", 4, False))
        self.assertEqual(v["nezet"]["beallitas"]["filters"], {"and": ['file.tags == ["Book"]']})

    def test_a_sorhalmaz_minden_fajl_nem_csak_a_jegyzet(self):
        v = self.fut("views:\n  - type: table\n    order: [file.name, file.ext, file.size]\n")
        self.assertEqual(len(v["sorok"]), len(self.tar.tabla().sorok))
        self.assertIn("doc.pdf", self.nevek(v))
        self.assertIn("atomic.jpg", self.nevek(v))
        self.assertIn("Books", self.nevek(v))                                    # a `.base` is sor
        v = self.fut('filters: file.ext == "jpg"\nviews:\n  - type: table\n')
        self.assertEqual(self.utak(v), ["kep/atomic.jpg"])
        v = self.fut('views:\n  - type: table\n    filters: file.ext == "pdf" || file.ext == "base"\n')
        self.assertEqual(self.utak(v), ["X03 - Books/Books.base", "doc.pdf"])

    def test_nem_jegyzet_sornak_nincs_tulajdonsaga(self):
        v = self.fut('views:\n  - type: table\n    order: [file.name, Status, file.size]\n    filters: file.ext == "jpg"\n')
        self.assertEqual(v["sorok"][0]["cellak"][1:], [None, 8])

    def test_globalis_es_nezet_szuro_egyutt(self):
        sz = ('filters: file.inFolder("X03 - Books")\nviews:\n  - type: table\n    name: Kész\n    filters: Status == "Done"\n'
              '  - type: table\n    name: Mind\n')
        self.assertEqual(self.nevek(self.fut(sz, "Kész")), ["Deep Work", "Sapiens"])
        self.assertEqual(self.nevek(self.fut(sz, "Mind")), ["Atomic Habits", "Books", "Deep Work", "Sapiens"])

    def test_szuro_logika(self):
        sz = ('views:\n  - type: table\n    filters:\n      or:\n        - file.hasTag("project")\n        - and:\n'
              '            - file.inFolder("X03 - Books")\n            - Rating >= 4.5\n        - not:\n            - file.ext == "md"\n'
              '            - file.ext == "base"\n')
        self.assertEqual(self.nevek(self.fut(sz)), ["Alpha", "Atomic Habits", "atomic.jpg", "Beta", "doc.pdf", "Sapiens"])

    def test_szuro_fordítasi_hiba_nem_mutat_sort_es_hibat_jelez(self):
        v = self.fut('views:\n  - type: table\n    filters: "nincs_fn(1)"\n')
        self.assertEqual(v["sorok"], [])
        self.assertEqual([h["hely"] for h in v["betolt_hibak"]], ["views[0].filters"])

    def test_szuro_futasi_hibaja_kihagyja_a_sort_es_szamol(self):
        v = self.fut('filters: Status == "Done" && Rating.round() >= 4\nviews:\n  - type: table\n    order: [file.name, Rating]\n')
        self.assertEqual(self.nevek(v), ["Deep Work", "Sapiens"])
        self.assertEqual(len(v["hibak"]), 1)
        self.assertEqual((v["hibak"][0]["hely"], v["hibak"][0]["db"]), ("filters", 2))     # Beta (nincs Rating), Rossz (szöveg)
        self.assertIn("Rating.round() >= 4", v["hibak"][0]["uzenet"])

    def test_this_a_megadott_fajl(self):
        sz = "views:\n  - type: table\n    filters: file.hasLink(this.file)\n"
        self.assertEqual(self.nevek(self.fut(sz, ez_ut="Projects/Alpha.md")), ["Hivatkozo"])
        self.assertEqual(self.nevek(self.fut(sz, ez_ut="Notes/Hivatkozo.md")), [])
        self.assertEqual(self.nevek(self.fut(sz)), [])
        # a még nem indexelt fájl is lehet `this`
        self.assertEqual(self.nevek(self.fut('views:\n  - type: table\n    filters: file.folder == this.file.folder\n',
                                             ez_ut="Projects/Uj.md")), ["Alpha", "Beta"])


class RendezesTest(_Alap):
    BAZIS = "filters: file.inFolder(\"X03 - Books\") && file.ext == \"md\"\nviews:\n  - type: table\n    order: [file.name, Rating, Status]\n"

    def test_alap_rendezes_fajlnev(self):
        self.assertEqual(self.nevek(self.fut(self.BAZIS)), ["Atomic Habits", "Deep Work", "Sapiens"])

    def test_sort_csokkeno_es_tobb_kulcs(self):
        sz = self.BAZIS + "    sort:\n      - property: Status\n        direction: ASC\n      - property: Rating\n        direction: DESC\n"
        self.assertEqual(self.nevek(self.fut(sz)), ["Sapiens", "Deep Work", "Atomic Habits"])
        sz = self.BAZIS + "    sort:\n      - property: Rating\n        direction: DESC\n"
        self.assertEqual(self.nevek(self.fut(sz)), ["Sapiens", "Atomic Habits", "Deep Work"])
        sz = self.BAZIS + "    sort:\n      - property: file.name\n        direction: DESC\n"
        self.assertEqual(self.nevek(self.fut(sz)), ["Sapiens", "Deep Work", "Atomic Habits"])

    def test_az_ures_ertek_a_legkisebb(self):
        sz = "views:\n  - type: table\n    filters: file.inFolder(\"Projects\") || file.name == \"Rossz.md\"\n    sort:\n      - property: Hours\n"
        self.assertEqual(self.nevek(self.fut(sz)), ["Rossz", "Beta", "Alpha"])
        sz += "        direction: DESC\n"
        self.assertEqual(self.nevek(self.fut(sz)), ["Alpha", "Beta", "Rossz"])

    def test_limit_a_rendezes_utan(self):
        sz = self.BAZIS + "    limit: 2\n    sort:\n      - property: Rating\n        direction: DESC\n"
        v = self.fut(sz)
        self.assertEqual(self.nevek(v), ["Sapiens", "Atomic Habits"])
        self.assertEqual(v["osszes"], 2)
        for rossz in ("0", "-1", "x"):
            self.assertEqual(len(self.fut(self.BAZIS + f"    limit: {rossz}\n")["sorok"]), 3, rossz)

    def test_rendezes_kepletre_es_hibas_rendezo_ertekre(self):
        sz = ('formulas:\n  fordit: "0 - Rating"\n' + self.BAZIS + "    sort:\n      - property: formula.fordit\n")
        self.assertEqual(self.nevek(self.fut(sz)), ["Sapiens", "Atomic Habits", "Deep Work"])

    def test_max_sor_levag(self):
        v = self.fut("views:\n  - type: table\n", max_sor=5)
        self.assertEqual((len(v["sorok"]), v["levagva"], v["osszes"] > 5), (5, True, True))


class CsoportTest(_Alap):
    SZ = ("filters: file.inFolder(\"X03 - Books\") && file.ext == \"md\"\nviews:\n  - type: table\n    order: [file.name, Rating, Pages]\n"
          "    groupBy:\n      property: Status\n      direction: ASC\n    summaries:\n      Rating: Average\n      Pages: Sum\n")

    def test_csoportok_es_csoport_osszesitok(self):
        v = self.fut(self.SZ)
        self.assertEqual(self.nevek(v), ["Deep Work", "Sapiens", "Atomic Habits"])
        cs = v["csoportok"]
        self.assertEqual([(c["cimke"], c["tol"], c["db"], c["huzhato"]) for c in cs], [("Done", 0, 2, True), ("Reading", 2, 1, True)])
        self.assertEqual(cs[0]["osszesitok"], {"Rating": {"nev": "Average", "ertek": 4.5}, "Pages": {"nev": "Sum", "ertek": 800}})
        self.assertEqual(cs[1]["osszesitok"]["Rating"]["ertek"], 4.5)
        self.assertEqual(v["osszesitok"], {"Rating": {"nev": "Average", "ertek": 4.5}, "Pages": {"nev": "Sum", "ertek": 1120}})

    def test_csoport_csokkeno_es_az_ures_ertek_csoportja(self):
        v = self.fut('filters: file.inFolder("X03 - Books") || file.name == "Inline.md"\nviews:\n  - type: table\n'
                     "    groupBy:\n      property: Status\n      direction: DESC\n")
        self.assertEqual([c["cimke"] for c in v["csoportok"]], ["Reading", "Done", ""])
        self.assertEqual(v["csoportok"][2]["kulcs"], None)
        self.assertEqual(self.nevek(v)[-2:], ["Books", "Inline"])                  # az üres csoport: .base és Inline

    def test_csoport_kepletre_nem_huzhato(self):
        v = self.fut('formulas:\n  hosszu: "Pages > 310"\nviews:\n  - type: kanban\n    filters: file.hasTag("book") && file.ext == "md"\n'
                     "    groupBy:\n      property: formula.hosszu\n")
        self.assertEqual([(c["cimke"], c["huzhato"]) for c in v["csoportok"]], [("false", False), ("true", False)])

    def test_osszesitok_tipusonkent(self):
        sz = ("filters: file.inFolder(\"X03 - Books\") && file.ext == \"md\"\nviews:\n  - type: table\n"
              "    order: [file.name, Rating, Started, Status, Author]\n    summaries:\n      Rating: Median\n"
              "      Started: Latest\n      Status: Unique\n      Author: Filled\n      file.name: Empty\n")
        o = self.fut(sz)["osszesitok"]
        self.assertEqual((o["Rating"]["ertek"], o["Status"]["ertek"], o["Author"]["ertek"], o["file.name"]["ertek"]),
                         (4.5, 2, 3, 0))
        self.assertEqual(o["Started"]["ertek"], {"t": "datum", "iso": "2026-09-01", "ido": False})

    def test_egyedi_osszesito_es_ismeretlen(self):
        sz = ("summaries:\n  tobb: 'values.filter(value > 4).length'\n  hibas: 'values.nincs()'\nviews:\n  - type: table\n"
              "    filters: file.inFolder(\"X03 - Books\") && file.ext == \"md\"\n    order: [file.name, Rating, Pages]\n"
              "    summaries:\n      Rating: tobb\n      Pages: Nincs\n")
        v = self.fut(sz)
        self.assertEqual(v["osszesitok"]["Rating"], {"nev": "tobb", "ertek": 2})
        self.assertEqual(v["osszesitok"]["Pages"]["ertek"]["t"], "hiba")
        self.assertTrue(any("Unknown summary: Nincs" in f["uzenet"] and f["kod"] == "bazis.api.ismeretlen_osszesito" for f in v["figyelmeztetesek"]))
        self.assertEqual([h["hely"] for h in v["betolt_hibak"]], ["summaries.hibas"])


class OszlopTest(_Alap):
    def test_oszlop_leirok(self):
        sz = ("formulas:\n  dupla: Pages * 2\nproperties:\n  Rating:\n    displayName: Értékelés\n  formula.dupla:\n    displayName: Dupla\n"
              "views:\n  - type: table\n    filters: file.name == \"Atomic Habits.md\"\n"
              "    order: [file.name, file.mtime, Rating, Started, Tags, Status, formula.dupla, file.tags]\n"
              "    columnSize:\n      file.name: 250\n      Rating: 90\n")
        v = self.fut(sz)
        self.assertEqual([(o["id"], o["nev"], o["ter"], o["tipus"], o["szerkesztheto"], o["szelesseg"]) for o in v["oszlopok"]], [
            ("file.name", "File name", "file", "text", False, 250), ("file.mtime", "Modified", "file", "datetime", False, None),
            ("Rating", "Értékelés", "note", "number", True, 90), ("Started", "Started", "note", "date", True, None),
            ("Tags", "Tags", "note", "tags", True, None), ("Status", "Status", "note", "text", True, None),
            ("formula.dupla", "Dupla", "formula", "formula", False, None), ("file.tags", "Tags", "file", "tags", False, None)])
        self.assertEqual([o["alap_nev"] for o in v["oszlopok"]], [True, True, False, True, True, True, False, True])
        c = v["sorok"][0]["cellak"]
        self.assertEqual(c[0], {"t": "link", "cel": "X03 - Books/Atomic Habits.md", "ut": "X03 - Books/Atomic Habits.md", "nev": "Atomic Habits"})
        self.assertEqual((c[2], c[3], c[4], c[5], c[6]), (4.5, {"t": "datum", "iso": "2026-09-01", "ido": False},
                                                          {"t": "lista", "e": ["Book"]}, "Reading", 640))
        self.assertEqual(c[7], {"t": "lista", "e": [{"t": "cimke", "v": "#Book"}]})
        self.assertEqual(c[1]["t"], "datum")
        self.assertTrue(c[1]["ido"])

    def test_link_cella_feloldott_utat_ad(self):
        v = self.fut('views:\n  - type: table\n    filters: file.name == "Atomic Habits.md"\n    order: [Author, cover]\n')
        self.assertEqual(v["sorok"][0]["cellak"], [{"t": "link", "cel": "James Clear", "ut": "People/James Clear.md", "nev": "James Clear"},
                                                  {"t": "link", "cel": "atomic.jpg", "ut": "kep/atomic.jpg", "nev": "atomic.jpg"}])

    def test_hibas_kepelt_hibacella_a_tobbi_nem_serul(self):
        sz = ('formulas:\n  rossz: "Rating.round() * 2"\n  jo: "Pages + 1"\n  ismeretlen: "nincs_fn(1)"\nviews:\n  - type: table\n'
              '    filters: file.inFolder("X03 - Books") && file.ext == "md" || file.name == "Rossz.md"\n'
              '    order: [file.name, formula.rossz, formula.jo, formula.ismeretlen]\n')
        v = self.fut(sz)
        sor = {s["nev"]: s["cellak"] for s in v["sorok"]}
        self.assertEqual(sor["Deep Work"][1:3], [8, 301])
        self.assertEqual(sor["Rossz"][1]["t"], "hiba")
        self.assertIsNone(sor["Rossz"][2])
        self.assertEqual(sor["Atomic Habits"][3]["t"], "hiba")
        self.assertEqual([h["hely"] for h in v["betolt_hibak"]], ["formulas.ismeretlen"])

    def test_alap_oszlop_a_fajlnev(self):
        v = self.fut(FAJLOK["X03 - Books/Books.base"])
        self.assertEqual([o["id"] for o in v["oszlopok"]], ["file.name"])


class KepTest(_Alap):
    def test_borito(self):
        sz = ('views:\n  - type: cards\n    image: note.cover\n    filters: file.hasTag("book")\n')
        v = self.fut(sz)
        k = {s["nev"]: s.get("kep") for s in v["sorok"]}
        self.assertEqual(k["Atomic Habits"], {"t": "ut", "ut": "kep/atomic.jpg"})
        self.assertNotIn("kep", [s for s in v["sorok"] if s["nev"] == "Sapiens"][0])

    def test_hex_szin_url_es_nem_kep(self):
        for ertek, vart in [('"#ff8800"', {"t": "szin", "v": "#ff8800"}),
                            ('"https://x.hu/a.png"', {"t": "kulso", "url": "https://x.hu/a.png"}),
                            ('image("[[atomic.jpg]]")', {"t": "ut", "ut": "kep/atomic.jpg"}),
                            ('"doc.pdf"', None), ('"nincs.png"', None), ("5", None)]:
            sz = f"formulas:\n  k: '{ertek}'\nviews:\n  - type: cards\n    image: formula.k\n    filters: file.name == \"Sapiens.md\"\n"
            self.assertEqual(self.fut(sz)["sorok"][0].get("kep"), vart, ertek)


class GeneracioTest(_Alap):
    def test_a_tabla_gyorsitotarazott_es_irasra_ujraolvas(self):
        t1 = self.tar.tabla()
        self.assertIs(self.tar.tabla(), t1)
        g = self.ix.generacio
        (self.v / "Uj.md").write_text("---\nStatus: Uj\n---\n", encoding="utf-8")
        self.assertTrue(self.ix.frissit(["Uj.md"]))
        self.assertGreater(self.ix.generacio, g)
        t2 = self.tar.tabla()
        self.assertIsNot(t2, t1)
        self.assertIn("Uj.md", t2.ut_szerint)
        self.assertNotIn("Uj.md", t1.ut_szerint)

    def test_csak_stat_valtozas_is_novel_a_generaciot(self):
        g = self.ix.generacio
        p = self.v / "doc.pdf"
        os.utime(p, (1_700_000_000, 1_700_000_000))
        self.assertTrue(self.ix.frissit(["doc.pdf"]))
        self.assertGreater(self.ix.generacio, g)
        v = self.fut('views:\n  - type: table\n    order: [file.mtime]\n    filters: file.name == "doc.pdf"\n')
        self.assertEqual(v["sorok"][0]["cellak"][0]["iso"][:4], "2023")
        g = self.ix.generacio
        self.assertTrue(self.ix.frissit(["doc.pdf"]))                        # nincs változás: nincs új generáció
        self.assertEqual(self.ix.generacio, g)

    def test_torles_es_tipusvaltas_is_novel(self):
        g = self.ix.generacio
        (self.v / "doc.pdf").unlink()
        self.assertTrue(self.ix.frissit(["doc.pdf"]))
        self.assertGreater(self.ix.generacio, g)
        self.assertNotIn("doc.pdf", self.tar.tabla().ut_szerint)
        g = self.ix.generacio
        (self.v / ".obsidian" / "types.json").write_text('{"types": {"Rating": "text"}}', encoding="utf-8")
        self.assertTrue(self.ix.frissit([".obsidian/types.json"]))
        self.assertGreater(self.ix.generacio, g)
        self.assertEqual(self.tar.tabla().tulajdonsag_tipus("Rating"), "text")

    def test_ctime_az_indexbol_nem_a_fajlrendszerbol_es_nem_mtime(self):
        """10-bases-13: a `file.ctime` az index `ctime_ns` oszlopa; lekérdezéskor nincs `os.stat`, és ismeretlenre `null`."""
        SZ = 'views:\n  - type: table\n    order: [file.ctime]\n    filters: file.name == "doc.pdf"\n'
        with self.ix.olvaso() as c:
            ns = c.execute("SELECT ctime_ns FROM fajl WHERE ut = 'doc.pdf'").fetchone()[0]
        with mock.patch("os.stat", side_effect=AssertionError("a Bases nem stat-ol soronként")):
            v = self.fut(SZ)
        if ns:
            self.assertEqual(v["sorok"][0]["cellak"][0]["iso"], datetime.fromtimestamp(ns / 1e9).isoformat(timespec="seconds"))
        else:
            self.assertIsNone(v["sorok"][0]["cellak"][0])
        # ismeretlen születési idő: üres érték, soha nem az mtime
        sor = self.tar.tabla().ut_szerint["doc.pdf"]
        sor.ctime_ns = None
        v = self.fut(SZ)
        self.assertIsNone(v["sorok"][0]["cellak"][0])


class ForrasTest(_Alap):
    def test_bazis_forrasok_a_base_fajlok_es_a_base_blokkos_jegyzetek(self):
        self.assertEqual([(f["ut"], f["tipus"]) for f in self.ix.bazis_forrasok()],
                         [("Blokk.md", "md"), ("Blokk2.md", "md"), ("X03 - Books/Books.base", "base")])
        self.assertTrue(all(f["hash"] for f in self.ix.bazis_forrasok()))

    def test_bazis_sorok_alak(self):
        gen, sorok = self.ix.bazis_sorok()
        self.assertEqual(gen, self.ix.generacio)
        r = {s[1]: s for s in sorok}["X03 - Books/Atomic Habits.md"]
        _, ut, lemez, tip, meret, mtime, tul, cim, lnk, alias, ctime = r
        self.assertEqual((tip, [t[0] for t in tul][:3], cim), ("md", ["Tags", "Status", "Rating"], ["Book"]))
        self.assertEqual({L["cel_nyers"]: L["cel"] for L in lnk}, {"James Clear": "People/James Clear.md", "atomic.jpg": "kep/atomic.jpg"})


class KeretTest(unittest.TestCase):
    """T040/T041 (C29.8): a Bases-lekérdezés teljes időkerete, a megszakítható elavult kérés és az értékkeret; a lekérdezés
    leállítása `IdokeretHiba`/`ErtekKeretHiba` (nem a soronkénti `FutasHiba`, amelyet a sorok lenyelnek)."""
    LASSU = "filters: '/(a|aa)+$/.matches(Cim)'\n"

    def sorok(self, n):
        from tests.bazis_segedek import sor
        return [sor(f"N/{i:03d}.md", {"Cim": "a" * 60 + "b"}) for i in range(n)]

    def fut(self, szoveg, sorok, **kw):
        from tests.bazis_segedek import tabla
        bazis, hibak = betolt(szoveg)
        self.assertFalse(bazis.vegzetes, hibak)
        return futtat(bazis, tabla(sorok), bazis.nezetek[0], **kw)

    def test_teljes_idokeret(self):
        from core.bazis.ertekek import IdokeretHiba
        t0 = time.monotonic()
        with self.assertRaises(IdokeretHiba):
            self.fut(self.LASSU, self.sorok(40), hatarido_mp=0.6)          # soronként 0,25 s regex-időkorlát: összkeret nélkül 10 s
        self.assertLess(time.monotonic() - t0, 2.5)

    def test_megszakitott_kerelem_azonnal_all(self):
        from core.bazis.ertekek import IdokeretHiba
        t0 = time.monotonic()
        with self.assertRaises(IdokeretHiba) as cm:
            self.fut(self.LASSU, self.sorok(40), megszakitva=lambda: True)
        self.assertTrue(cm.exception.megszakitva)
        self.assertLess(time.monotonic() - t0, 1.0)

    def test_ertek_keret_a_repeat_kozott_es_a_cellakban(self):
        from core.bazis.ertekek import ErtekKeretHiba
        sz = ("formulas:\n  x: '\"x\".repeat(1000000)'\nviews:\n  - type: table\n    order:\n      - formula.x\n")
        with self.assertRaises(ErtekKeretHiba):
            self.fut(sz, self.sorok(20), ertek_keret=4_000_000)                # soronként 1 MB: az 5. soron betelik
        v = self.fut(sz, self.sorok(2))                                         # az alapkeret mellett elfér
        self.assertEqual(len(v["sorok"]), 2)

    def test_nagyon_koran_datum_rendezheto(self):
        """T041: a `0001-01-01` dátum `.timestamp()`-je `ValueError` volt a rendezésben (500)."""
        from tests.bazis_segedek import sor
        sorok = [sor("N/b.md", {"datum": ("date", "2026-01-01")}), sor("N/a.md", {"datum": ("date", "0001-01-01")})]
        v = self.fut("views:\n  - type: table\n    sort:\n      - property: datum\n        direction: ASC\n", sorok)
        self.assertEqual([s["ut"] for s in v["sorok"]], ["N/a.md", "N/b.md"])


if __name__ == "__main__":
    unittest.main()
