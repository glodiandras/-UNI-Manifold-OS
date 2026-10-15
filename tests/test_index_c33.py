"""C33 — az index megbízhatósága és teljesítménye (2. audit T070, T171, T172, T173, T175, T176), álvaulton.

- T171: a sérült `vault.sqlite` félrekerül (`serult-<idő>.sqlite`) és az index újraépül (indításkor és menet közben is).
- T172: a nyilvános `olvaso()` egy olvasó-tranzakció; a kiszervezett modulok ezt használják.
- T173: a csak mappát érintő változás generációt és `vault_valtozas {mappak}` eseményt ad.
- T070: a tartalmi mentés nem növeli a szerkezeti generációt (a gráf gyorsítótára és ETag-je marad); a Bases `Tabla`
  inkrementálisan frissül; a nehéz olvasók közös zára.
- T176: a saját írás egy nagy külső köteg alatt elsőbbséget kap (a szeletek között), nem a köteg végét várja.
- T175: a vault eltűnése / visszatérése tétlenségben is jelzés (`index` esemény, az `elerheto` horog).
"""
import os
import shutil
import sqlite3
import threading
import time
import unittest
from pathlib import Path

from core.bazis.adat import Tar
from core.index import indexelo, tar
from tests.helpers import ir, tmpdir
from tests.index_segedek import alvault, index_indit, var_ra

KICSI = {".obsidian/app.json": "{}", "A.md": "# A\n[[B]]\n", "B.md": "# B\n#cimke\n", "C/D.md": "---\nTags: x\n---\nd\n"}


class Alap(unittest.TestCase):
    fajlok = KICSI

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, self.fajlok)
        # determinisztikus: a figyelő gyakorlatilag nem jelez (a teszt maga jelez az indexnek)
        self.cfg.data["index"] = {**self.cfg.section("index"), "figyelo": "lekerdezes", "lekerdezes_mp": 3600}

    def indit(self, **kw):
        ix, ev = index_indit(self.cfg, **kw)
        self.addCleanup(ix.leallit)
        return ix, ev


class SerultIndexTest(Alap):
    def test_az_indulaskor_serult_index_felrekerul_es_ujraepul(self):
        db = Path(self.cfg.path("index")) / "vault.sqlite"
        db.parent.mkdir(parents=True, exist_ok=True)
        db.write_bytes(b"ez nem SQLite-adatbazis" * 200)
        ix, _ = self.indit()
        a = ix.allapot()
        self.assertTrue(a["felretett"].startswith("serult-"), a)
        self.assertIsNone(a["hiba"])
        self.assertEqual(a["jegyzetek"], 3)
        self.assertTrue((db.parent / a["felretett"]).exists())
        self.assertEqual(ix.jegyzet("A.md")["linkek"][0]["cel"], "B.md")

    def test_a_menet_kozben_serultnek_bizonyult_index_ujraepul(self):
        ix, ev = self.indit()
        eredeti = ix._koteg
        hivas = []

        def egyszer_serult(koteg):
            if not hivas:
                hivas.append(1)
                raise sqlite3.DatabaseError("database disk image is malformed")
            return eredeti(koteg)
        ix._koteg = egyszer_serult
        ir(self.v, "Uj.md", "# Új\n")
        ix.frissit(["Uj.md"])
        self.assertTrue(var_ra(lambda: ix.allapot()["felretett"] is not None, 10))
        self.assertTrue(any(e["tipus"] == "index" for e in ev))
        # az újraépített index a lemez állapotát adja (az új fájllal együtt)
        self.assertTrue(var_ra(lambda: "Uj.md" in ix.fajl_halmaz(), 10))
        self.assertEqual(len(list(Path(self.cfg.path("index")).glob("serult-*.sqlite"))), 1)

    def test_az_ujraepites_alatt_kiadott_olvaso_nem_kerul_vissza(self):
        """F5 (2026-10-14): az újraépítés alatt kiadott olvasó kapcsolat a félretett (`serult-*`) fájlra mutat; visszaadáskor
        záródik, a készletből nem kap senki régi találatot."""
        ix, ev = self.indit()
        eredeti = ix._koteg
        hivas = []

        def egyszer_serult(koteg):
            if not hivas:
                hivas.append(1)
                raise sqlite3.DatabaseError("database disk image is malformed")
            return eredeti(koteg)
        with ix.olvaso() as regi:
            ix._koteg = egyszer_serult
            ir(self.v, "Uj.md", "# Új\n")
            ix.frissit(["Uj.md"])
            self.assertTrue(var_ra(lambda: ix.allapot()["felretett"] is not None, 10))
            self.assertTrue(var_ra(lambda: "Uj.md" in ix.fajl_halmaz(), 10))
        with self.assertRaises(sqlite3.ProgrammingError):
            regi.execute("SELECT 1")                                    # a régi kapcsolat zárva
        for _ in range(3):
            with ix.olvaso() as c:
                self.assertIsNot(c, regi)
                self.assertEqual(c.execute("SELECT count(*) FROM fajl WHERE ut = 'Uj.md' AND torolve IS NULL").fetchone()[0], 1)

    def test_a_keszlet_uritese_utan_a_kiadott_kapcsolat_zarodik(self):
        ix, _ = self.indit()
        with ix.olvaso() as c1:
            ix._pool_urit()
        with self.assertRaises(sqlite3.ProgrammingError):
            c1.execute("SELECT 1")
        with ix.olvaso() as c2:
            pass
        with ix.olvaso() as c3:
            self.assertIs(c3, c2)                                       # az új generáció kapcsolata visszakerül

    def test_a_serult_hiba_felismerese(self):
        self.assertTrue(tar.serult_hiba(sqlite3.DatabaseError("file is not a database")))
        self.assertFalse(tar.serult_hiba(sqlite3.OperationalError("database is locked")))
        self.assertFalse(tar.serult_hiba(OSError("x")))


class OlvasoTest(Alap):
    def test_az_olvaso_tranzakcio_es_a_kapcsolat_visszakerul(self):
        ix, _ = self.indit()
        with ix.olvaso() as c:
            self.assertTrue(c.in_transaction)
            c.execute("SELECT count(*) FROM fajl").fetchone()
        self.assertFalse(c.in_transaction)
        with ix.olvaso(tranzakcio=False) as c2:
            self.assertFalse(c2.in_transaction)
        self.assertIs(indexelo.Index._olvaso, indexelo.Index.olvaso)       # a régi név álnév

    def test_a_nehez_olvasok_kozos_zara_ujrabelepo(self):
        ix, _ = self.indit()
        with ix.olvaso(nehez=True):
            self.assertEqual(ix.graf_api()["csucsok"][:1], ["A.md"])     # ugyanabban a szálban újra beléphet


class MappaValtozasTest(Alap):
    def test_az_ures_mappa_megjelenese_es_eltunese_esemeny_es_generacio(self):
        ix, ev = self.indit()
        g0 = ix.generacio
        (self.v / "Ures mappa").mkdir()
        self.assertTrue(ix.frissit(["Ures mappa"]))
        self.assertGreater(ix.generacio, g0)
        self.assertIn("Ures mappa", ix.fa()["mappak"])
        utolso = [e for e in ev if e["tipus"] == "vault_valtozas"][-1]
        self.assertEqual(utolso["mappak"], ["Ures mappa"])
        g1 = ix.generacio
        (self.v / "Ures mappa").rmdir()
        self.assertTrue(ix.frissit(["Ures mappa"]))
        self.assertGreater(ix.generacio, g1)
        self.assertNotIn("Ures mappa", ix.fa()["mappak"])
        self.assertEqual([e for e in ev if e["tipus"] == "vault_valtozas"][-1]["mappak"], ["Ures mappa"])

    def test_valtozatlan_mappa_nem_esemeny(self):
        ix, ev = self.indit()
        g0 = ix.generacio
        n = len(ev)
        self.assertTrue(ix.frissit(["C"]))                        # a meglévő mappa újrabejárása: nincs változás
        self.assertEqual(ix.generacio, g0)
        self.assertEqual(len(ev), n)


class SzerkezetiGeneracioTest(Alap):
    def test_a_tartalmi_mentes_nem_erventelenit_a_link_valtozas_igen(self):
        ix, _ = self.indit()
        b0, e0 = ix.graf_valasz()
        sz0 = ix.szerkezet_generacio
        ir(self.v, "B.md", "# B\n#cimke\nmég egy mondat\n")
        self.assertTrue(ix.frissit(["B.md"]))
        self.assertEqual(ix.szerkezet_generacio, sz0)
        b1, e1 = ix.graf_valasz()
        self.assertIs(b1, b0)                                     # ugyanaz a gyorsítótárazott válasz
        self.assertEqual(e1, e0)
        ir(self.v, "B.md", "# B\n#cimke\n[[A]]\n")
        self.assertTrue(ix.frissit(["B.md"]))
        self.assertGreater(ix.szerkezet_generacio, sz0)
        b2, e2 = ix.graf_valasz()
        self.assertNotEqual(e2, e0)
        self.assertIn(b'"B.md", "A.md"', b2)
        # a címke változása a graf-metát érinti: szerkezeti
        sz1 = ix.szerkezet_generacio
        ir(self.v, "B.md", "# B\n#masik\n[[A]]\n")
        self.assertTrue(ix.frissit(["B.md"]))
        self.assertGreater(ix.szerkezet_generacio, sz1)

    def test_valtozasnaplo(self):
        ix, _ = self.indit()
        g0 = ix.generacio
        ir(self.v, "A.md", "# A\n[[B]]\núj\n")
        self.assertTrue(ix.frissit(["A.md"]))
        most, utak = ix.valtozasok_ota(g0)
        self.assertEqual((most, utak), (ix.generacio, {"A.md"}))
        ir(self.v, "Uj.md", "x\n")
        self.assertTrue(ix.frissit(["Uj.md"]))
        self.assertIsNone(ix.valtozasok_ota(g0)[1])                # új fájl: ismeretlen hatókör (teljes újraolvasás)
        self.assertEqual(ix.valtozasok_ota(ix.generacio)[1], set())
        self.assertIsNone(ix.valtozasok_ota(-50)[1])               # a napló nem fedi le


class BazisInkrementalisTest(Alap):
    def test_tartalmi_valtozasra_inkrementalis_uj_fajlra_teljes(self):
        ix, _ = self.indit()
        t = Tar(ix)
        t1 = t.tabla()
        self.assertEqual(t.utolso_mod, "teljes")
        b_regi = t1.ut_szerint["B.md"]
        a_regi = t1.ut_szerint["A.md"]
        ir(self.v, "B.md", "---\nStatus: kesz\n---\n# B\n#cimke\n")
        self.assertTrue(ix.frissit(["B.md"]))
        t2 = t.tabla()
        self.assertEqual(t.utolso_mod, "inkrementalis")
        self.assertEqual([s.ut for s in t2.sorok], [s.ut for s in t1.sorok])
        self.assertIsNot(t2.ut_szerint["B.md"], b_regi)
        self.assertIs(t2.ut_szerint["A.md"], a_regi)               # a nem változott sor (a számolt értékeivel) marad
        self.assertEqual([k for k, _, _ in t2.ut_szerint["B.md"].tulajdonsagok], ["Status"])
        t.tabla()
        self.assertEqual(t.utolso_mod, "meleg")
        ir(self.v, "E.md", "e\n")
        self.assertTrue(ix.frissit(["E.md"]))
        self.assertIn("E.md", t.tabla().ut_szerint)
        self.assertEqual(t.utolso_mod, "teljes")


class ElsobbsegTest(Alap):
    fajlok = {".obsidian/app.json": "{}", **{f"Sok/J{i:04d}.md": f"# J{i}\n" for i in range(1200)}, "Sajat.md": "eleje\n"}

    def test_a_sajat_iras_nem_varja_meg_a_nagy_kulso_koteget(self):
        ix, _ = self.indit()
        eredeti = ix._fajl_ir

        def lassu(*a, **k):                                      # a nagy köteg így biztosan sokáig tart (~2,4 s)
            time.sleep(0.002)
            return eredeti(*a, **k)
        ix._fajl_ir = lassu
        for i in range(1200):
            (self.v / f"Sok/J{i:04d}.md").write_text(f"# J{i}\nváltozott\n", encoding="utf-8")
        ix.jelez([f"Sok/J{i:04d}.md" for i in range(1200)])
        self.assertTrue(var_ra(lambda: ix._gyujto is not None, 10))      # a szeletelt köteg fut
        (self.v / "Sajat.md").write_text("mentett tartalom\n", encoding="utf-8")
        import hashlib
        t0 = time.monotonic()
        ix.sajat_iras("Sajat.md", hashlib.sha1(b"mentett tartalom\n").hexdigest())
        ido = time.monotonic() - t0
        self.assertIsNotNone(ix._gyujto, "a saját írás csak a köteg végén ment át")
        self.assertLess(ido, 1.5)
        self.assertEqual(ix.kereses("mentett")["talalatok"][0]["ut"], "Sajat.md")     # a válasz után az index látja
        self.assertTrue(var_ra(lambda: ix._gyujto is None, 30))
        # a köteg végén egy összevont esemény (nem szeletenként)


class ElerhetosegTest(Alap):
    def test_a_vault_eltunese_es_visszaterese_tetlensegben_is_jelzes(self):
        jelek = []
        ix, ev = self.indit(elerheto=jelek.append)
        masik = self.v.parent / "Manifold-el"
        os.rename(self.v, masik)
        try:
            ix._elerhetoseg_proba()
            self.assertEqual(jelek, [False])
            self.assertFalse([e for e in ev if e["tipus"] == "index"][-1]["elerheto"])
        finally:
            os.rename(masik, self.v)
        ir(self.v, "Kozben.md", "x\n")
        ix._q.put(("ebreszt", [], None))                          # az író szálon fusson (a próba ott hívódik)
        ix._elerhetoseg_proba()
        self.assertTrue(var_ra(lambda: "Kozben.md" in ix.fajl_halmaz(), 10))
        self.assertEqual(jelek, [False, True])


if __name__ == "__main__":
    unittest.main()
