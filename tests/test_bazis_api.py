"""A Bases végpontjai (`core/bazis/api.py`, C12 5. lépés): HTTP-n át a szerver szálon; a végpontok nem írnak."""
import hashlib
import os
import threading
import time
import unittest

from core import vaultio
from core.bazis.api import Bazisok
from core.index import indexelo
from tests import csak_darwin
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import alvault, index_indit
from tests.test_core_api import _Szerver
from tests.test_bazis_lekerdezes import FAJLOK

BOOKS = FAJLOK["X03 - Books/Books.base"]


def lenyomat(gyoker) -> dict:
    return {str(p.relative_to(gyoker)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(gyoker.rglob("*")) if p.is_file() and ".obsidian" not in p.parts}


class ApiTest(_Szerver):
    def elokeszit(self):
        for rp, t in FAJLOK.items():
            ir(self.v, rp, t, "wb" if isinstance(t, bytes) else "w")

    def setUp(self):
        super().setUp()
        t0 = time.time()
        while time.time() - t0 < 30 and not self.k("GET", "/api/vault/index")[1].get("kesz"):
            time.sleep(0.05)
        self.elotte = lenyomat(self.v)

    def tearDown(self):
        self.assertEqual(lenyomat(self.v), self.elotte, "a Bases-végpontok nem írhatnak a vaultba")

    def lekerdez(self, szoveg, **kw):
        return self.k("POST", "/api/vault/bazis/lekerdez", {"szoveg": szoveg, **kw})

    def test_lekerdez_books_alak(self):
        st, v = self.lekerdez(BOOKS)
        self.assertEqual(st, 200)
        self.assertTrue(v["ok"])
        self.assertEqual([s["nev"] for s in v["sorok"]], ["Atomic Habits", "Deep Work", "Inline", "Sapiens"])
        self.assertEqual(v["nezet"]["tipus"], "cards")
        self.assertEqual([n["nev"] for n in v["nezetek"]], ["Books"])
        for kulcs in ("oszlopok", "csoportok", "osszesitok", "osszes", "levagva", "hibak", "figyelmeztetesek", "ido_ms",
                      "generacio"):
            self.assertIn(kulcs, v)
        self.assertEqual(v["sorok"][0], {"ut": "X03 - Books/Atomic Habits.md", "nev": "Atomic Habits", "md": True,
                                         "cellak": [{"t": "link", "cel": "X03 - Books/Atomic Habits.md",
                                                     "ut": "X03 - Books/Atomic Habits.md", "nev": "Atomic Habits"}]})

    def test_ures_szoveg_alap_tablazat(self):
        st, v = self.lekerdez("")
        self.assertEqual((st, v["ok"], v["nezet"]["tipus"]), (200, True, "table"))
        self.assertEqual([o["id"] for o in v["oszlopok"]], ["file.name"])
        self.assertEqual(v["osszes"], len(FAJLOK))                     # minden fájl sor (a `.obsidian` nem)

    def test_nezet_valasztas_sorszam_nev_es_ismeretlen(self):
        sz = "views:\n  - type: table\n    name: A\n    limit: 1\n  - type: cards\n    name: Bé\n    limit: 2\n"
        self.assertEqual(self.lekerdez(sz, nezet=1)[1]["nezet"]["nev"], "Bé")
        self.assertEqual(self.lekerdez(sz, nezet="bé")[1]["nezet"]["nev"], "Bé")
        self.assertEqual(len(self.lekerdez(sz)[1]["sorok"]), 1)
        st, v = self.lekerdez(sz, nezet="nincs")
        self.assertEqual((st, v["nezet"]["nev"]), (200, "A"))
        self.assertTrue(any("There is no such view" in f["uzenet"] and f["kod"] == "bazis.api.nincs_nezet" for f in v["figyelmeztetesek"]))
        self.assertEqual(self.lekerdez(sz, nezet=9)[1]["nezet"]["nev"], "A")

    def test_ez_a_this(self):
        sz = "views:\n  - type: table\n    filters: file.hasLink(this.file)\n"
        self.assertEqual([s["nev"] for s in self.lekerdez(sz, ez="Projects/Alpha.md")[1]["sorok"]], ["Hivatkozo"])
        self.assertEqual(self.lekerdez(sz)[1]["sorok"], [])

    def test_max_sor_levag(self):
        st, v = self.lekerdez("", max_sor=3)
        self.assertEqual((st, len(v["sorok"]), v["levagva"]), (200, 3, True))

    def test_yaml_hiba_200_ok_hamis(self):
        st, v = self.lekerdez("views:\n  - type: [table\n")
        self.assertEqual((st, v["ok"], v["sorok"], [h["hely"] for h in v["hibak"]]), (200, False, [], ["yaml"]))

    def test_szuro_es_keplet_hibak_a_valaszban(self):
        sz = "formulas:\n  rossz: '1 +'\nviews:\n  - type: table\n    filters: 'price >'\n"
        st, v = self.lekerdez(sz)
        self.assertEqual((st, v["ok"], v["sorok"]), (200, True, []))
        self.assertEqual(sorted(h["hely"] for h in v["hibak"]), ["formulas.rossz", "views[0].filters"])

    def test_hibas_keresek_400(self):
        for t in ({}, {"szoveg": 5}, {"szoveg": None}, {"szoveg": "", "nezet": [1]}, {"szoveg": "", "nezet": True},
                  {"szoveg": "", "max_sor": 0}, {"szoveg": "", "max_sor": "x"}, {"szoveg": "", "max_sor": 10_001},
                  {"szoveg": "", "ez": "../kint.md"}, {"szoveg": "", "ez": ".obsidian/app.json"}):
            self.assertEqual(self.k("POST", "/api/vault/bazis/lekerdez", t)[0], 400, t)

    def test_ismeretlen_metodus_es_ut(self):
        self.assertEqual(self.k("GET", "/api/vault/bazis/lekerdez")[0], 404)
        self.assertEqual(self.k("PUT", "/api/vault/bazis/lekerdez", {})[0], 404)
        self.assertEqual(self.k("POST", "/api/vault/bazis/nincs", {})[0], 404)
        self.assertEqual(self.k("POST", "/api/vault/bazis/lekerdez", fejlec={"X-Manifold": "0"})[0], 403)

    def test_modosit_tiszta(self):
        t = {"szoveg": BOOKS, "muvelet": {"fajta": "nezet_beallit", "nezet": 0, "kulcs": "limit", "ertek": 2}}
        st, v = self.k("POST", "/api/vault/bazis/modosit", t)
        self.assertEqual((st, v["ok"], v["hibak"], v["valtozas"]), (200, True, [], "view limit"))
        self.assertEqual(v["szoveg_uj"], BOOKS + "    limit: 2\n")
        st, v2 = self.lekerdez(v["szoveg_uj"])                     # az új szöveg közvetlenül lekérdezhető
        self.assertEqual(len(v2["sorok"]), 2)

    def test_modosit_hibas_szuro_nem_valtoztat(self):
        t = {"szoveg": BOOKS, "muvelet": {"fajta": "szuro_beallit", "hol": 0, "yaml": "price >"}}
        st, v = self.k("POST", "/api/vault/bazis/modosit", t)
        self.assertEqual((st, v["ok"], v["szoveg_uj"]), (200, False, BOOKS))
        self.assertEqual([h["hely"] for h in v["hibak"]], ["views[0].filters"])

    def test_modosit_hibas_keres_400(self):
        for t in ({}, {"szoveg": BOOKS}, {"muvelet": {}}, {"szoveg": 3, "muvelet": {}}, {"szoveg": BOOKS, "muvelet": 5}):
            self.assertEqual(self.k("POST", "/api/vault/bazis/modosit", t)[0], 400, t)
        st, v = self.k("POST", "/api/vault/bazis/modosit", {"szoveg": BOOKS, "muvelet": {"fajta": "nincs"}})
        self.assertEqual((st, v["ok"], v["hibak"][0]["hely"]), (200, False, "muvelet"))

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_ujraolvas_a_vault_valtozasa_utan(self):
        sz = 'views:\n  - type: table\n    filters: file.hasTag("uj")\n'
        self.assertEqual(self.lekerdez(sz)[1]["sorok"], [])
        ir(self.v, "Uj.md", "---\nTags:\n  - uj\n---\n")
        t0 = time.time()
        while time.time() - t0 < 10:
            v = self.lekerdez(sz)[1]
            if v["sorok"]:
                break
            time.sleep(0.05)
        self.assertEqual([s["nev"] for s in v["sorok"]], ["Uj"])
        self.elotte = lenyomat(self.v)


class NincsKeszTest(unittest.TestCase):
    def test_az_index_nelkul_503_alapu_hiba(self):
        with tmpdir() as t:
            cfg, _, _ = alg_core(t)
            ix = indexelo.Index(cfg)
            with self.assertRaises(indexelo.NemKesz):
                Bazisok(cfg, ix).lekerdez({"szoveg": ""})


class SzuletesiIdoTest(unittest.TestCase):
    """C29.6 (T025): az `atomi_csere` új inode-ot ad, de a mentett jegyzet születési ideje (`file.ctime`, az Obsidian
    „Created time”) megmarad — a C12 eleinte az ellenkezőjét rögzítette (a mentés ideje lett a születési idő)."""

    def test_mentes_megorzi_a_szuletesi_idot(self):
        if not hasattr(os.stat_result, "st_birthtime"):
            self.skipTest("[indokolt] nincs st_birthtime ezen a rendszeren")
        with tmpdir() as t:
            cfg, _, v = alg_core(t)
            ir(v, "A.md", "# A\n")
            V = vaultio.Vault(cfg)
            r = V.read("A.md")
            elotte = os.stat(v / "A.md")
            time.sleep(1.1)
            V.write({"ut": "A.md", "tartalom": "# A\n\nmás\n", "alap": r["hash"]})
            utana = os.stat(v / "A.md")
            self.assertNotEqual(utana.st_ino, elotte.st_ino)                  # a csere új inode
            self.assertAlmostEqual(utana.st_birthtime, elotte.st_birthtime, delta=1e-5)
            self.assertGreater(utana.st_mtime, elotte.st_mtime)


class KeretEsMegszakitasTest(unittest.TestCase):
    """T040/T041 (C29.8): a Bases-végpont a teljes időkeretet és az értékkeretet `ok: false` + `hibak` válasszal adja (nem
    500-zal), az elavult kérést megszakítja, és a szélsőséges értékek (0001-es dátum, YAML-alias) sem ejtik el."""
    LASSU = "filters: '/(a|aa)+$/.matches(Cim)'\n"

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        fajlok = {f"N/{i:03d}.md": f"---\nCim: {'a' * 60}b\ndatum: 2026-01-01\n---\n# N\n" for i in range(40)}
        fajlok["Kor.md"] = "---\ndatum: 0001-01-01\n---\n# K\n"
        self.cfg, self.v = alvault(self._t.name, fajlok)
        self.cfg.data.setdefault("index", {})["bazis_idokeret_mp"] = 0.6
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.b = Bazisok(self.cfg, self.ix)

    def test_teljes_idokeret_ok_hamis(self):
        t0 = time.monotonic()
        v = self.b.lekerdez({"szoveg": self.LASSU})                       # ma: soronként 0,25 s, összesen ~10 s, ok: True
        self.assertLess(time.monotonic() - t0, 3)
        self.assertFalse(v["ok"])
        self.assertEqual(v["hibak"][0]["hely"], "idokeret")
        self.assertFalse(v["megszakitva"])

    def test_elavult_kerelem_megszakad(self):
        self.b.idokeret = 30
        eredmeny = {}
        a = threading.Thread(target=lambda: eredmeny.update(a=self.b.lekerdez({"szoveg": self.LASSU, "kerdes": 1, "azon": "x"})))
        t0 = time.monotonic()
        a.start()
        time.sleep(0.4)
        eredmeny["b"] = self.b.lekerdez({"szoveg": "", "kerdes": 2, "azon": "x"})      # ugyanarra a nézetre újabb kérés
        a.join(10)
        self.assertFalse(a.is_alive())
        self.assertLess(time.monotonic() - t0, 3)                          # nem a 40 × 0,25 s
        self.assertFalse(eredmeny["a"]["ok"])
        self.assertTrue(eredmeny["a"]["megszakitva"])
        self.assertTrue(eredmeny["b"]["ok"])
        # másik nézet kérése nem szakítja meg
        self.assertTrue(self.b.lekerdez({"szoveg": "", "kerdes": 1, "azon": "y"})["ok"])

    def test_ertek_keret_ok_hamis(self):
        sz = "formulas:\n  x: '\"x\".repeat(1000000)'\nviews:\n  - type: table\n    order:\n      - formula.x\n"
        v = self.b.lekerdez({"szoveg": sz})                                # 41 sor × 1 MB > 16 MiB
        self.assertFalse(v["ok"])
        self.assertEqual(v["hibak"][0]["hely"], "ertekkeret")

    def test_szelsoseges_ertekek_nem_kivetel(self):
        sz = "views:\n  - type: table\n    sort:\n      - property: datum\n        direction: ASC\n"
        v = self.b.lekerdez({"szoveg": sz})                                # ma: ValueError (a 0001-01-01 timestamp-je)
        self.assertTrue(v["ok"])
        self.assertEqual(v["sorok"][0]["ut"], "Kor.md")
        v = self.b.lekerdez({"szoveg": "a: &x [1]\nb: *x\n"})              # YAML-alias
        self.assertFalse(v["ok"])
        self.assertEqual(v["hibak"][0]["hely"], "yaml")
        for rossz in ({"kerdes": "1", "azon": "x"}, {"kerdes": True}, {"azon": 5}, {"azon": "x" * 300}):
            with self.assertRaises(vaultio.Invalid):
                self.b.lekerdez({"szoveg": "", **rossz})


if __name__ == "__main__":
    unittest.main()
