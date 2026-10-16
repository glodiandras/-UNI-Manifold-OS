"""Az index (C06): építés, inkrementális frissítés, `torolve` jel (L57), induláskori stat-vizsgálat, a
fájlfigyelő (FSEvents és a lekérdező tartalék), és a saját vs. külső írás megkülönböztetése."""
import json
import os
import time
import unittest

from core import vaultio
from core.index import tar
from core.index.feloldas import graf, graf_kanonikus
from tests import csak_darwin
from tests.helpers import tmpdir
from tests.index_segedek import ALAP, ELTERES, NFD, alvault, index_indit, var_ra


class _Alap(unittest.TestCase):
    fajlok = None

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name, self.fajlok)

    def indit(self):
        ix, ev = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        return ix, ev

    def sor(self, ix, rp):
        c = tar.nyit(ix.db_ut)
        try:
            return c.execute("SELECT * FROM fajl WHERE ut = ?", (rp,)).fetchone()
        finally:
            c.close()


class IndexTest(_Alap):
    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_epites_allapot_fa_jegyzet(self):
        ix, ev = self.indit()
        a = ix.allapot()
        self.assertTrue(a["kesz"])
        self.assertIsNone(a["hiba"])
        self.assertEqual(a["fajlok"], len(graf(self.v)["files"]))
        self.assertEqual(ev[-1]["tipus"], "index")
        fa = ix.fa()
        self.assertIn("A", fa["mappak"])
        self.assertIn(".rejtett-mappa", fa["mappak"])
        self.assertNotIn(".obsidian", fa["mappak"])
        self.assertIn({"ut": "kep.png", "tipus": "kep"}, [{k: f[k] for k in ("ut", "tipus")} for f in fa["fajlok"]])
        j = ix.jegyzet("Cél.md")
        self.assertEqual(j["aliasok"], ["Célpont"])
        self.assertEqual(j["blokkok"], [{"azon": "blokk", "sor": 7, "kezdo_sor": 7}])
        self.assertEqual(j["cimkek"], [{"cimke": "Math/Algebra", "forras": "fm", "sor": None}])
        linkek = ix.jegyzet("Linkek.md")["linkek"]
        self.assertEqual({L["cel_nyers"]: L["cel"] for L in linkek}["Ütőér"], "Ütőér.md")
        with self.assertRaises(vaultio.NotFound):
            ix.jegyzet("nincs.md")
        self.assertEqual(ix.jegyzet("Rossz.canvas")["canvas_hiba"][:9], "Expecting")

    def test_visszahivatkozasok(self):
        ix, _ = self.indit()
        v = {f["ut"]: f for f in ix.visszahivatkozasok("Cél.md")["forrasok"]}
        self.assertEqual(set(v), {"Linkek.md", "Tabla.md", "Vegyes.md", "Ütőér.md", "Vaszon.canvas",
                                  ".rejtett-mappa/Latszik.md"})
        nn = [L for L in v["Linkek.md"]["linkek"] if L["tulajdonsag"] == "NN"]
        self.assertEqual(len(nn), 1)
        self.assertIn("[[Cél]]", nn[0]["kornyezet"])
        self.assertEqual(v["Vaszon.canvas"]["linkek"][0]["csomopont"], "1")

    def test_valtozatlan_hash_nincs_ujraelemzes(self):
        ix, ev = self.indit()
        elotte = self.sor(ix, "Cél.md")["indexelve"]
        n = len(ev)
        os.utime(self.v / "Cél.md", ns=(time.time_ns(), time.time_ns() + 10**9))
        ix.frissit(["Cél.md"])
        self.assertEqual(self.sor(ix, "Cél.md")["indexelve"], elotte)
        self.assertEqual(len([e for e in ev[n:] if e["tipus"] == "vault_valtozas"]), 0)

    def test_torles_jeloles_es_visszaeledes(self):
        ix, ev = self.indit()
        fid = self.sor(ix, "Cél X.md")["id"]
        (self.v / "Cél X.md").unlink()
        ix.frissit(["Cél X.md"])
        r = self.sor(ix, "Cél X.md")
        self.assertIsNotNone(r["torolve"])                                     # L57: jelölés, nem törlés
        with self.assertRaises(vaultio.NotFound):
            ix.jegyzet("Cél X.md")
        self.assertIn("Cél X.md", ev[-1]["torolt"])
        tabla = {L["cel_nyers"]: L["cel"] for L in ix.jegyzet("Tabla.md")["linkek"]}
        self.assertIsNone(tabla["Cél X\\"])                                    # a feloldás frissült
        (self.v / "Cél X.md").write_text("vissza")
        ix.frissit(["Cél X.md"])
        self.assertEqual(self.sor(ix, "Cél X.md")["id"], fid)
        self.assertIsNone(self.sor(ix, "Cél X.md")["torolve"])
        self.assertEqual({L["cel_nyers"]: L["cel"] for L in ix.jegyzet("Tabla.md")["linkek"]}["Cél X\\"], "Cél X.md")

    def test_mappa_torlese(self):
        ix, _ = self.indit()
        import shutil
        shutil.rmtree(self.v / "A")
        ix.frissit(["A"])
        self.assertNotIn("A", ix.fa()["mappak"])
        self.assertFalse(any(f["ut"].startswith("A/") for f in ix.fa()["fajlok"]))
        self.assertEqual(graf_kanonikus(ix.graf()), graf_kanonikus(graf(self.v)))

    def test_indulaskori_stat_vizsgalat(self):
        ix, _ = self.indit()
        ix.leallit()
        (self.v / "Cél.md").write_text("# Új\n[[Cél X]]\n")
        (self.v / "Tabla.md").unlink()
        (self.v / "Uj.md").write_text("[[Cél]]")
        ix2, ev = self.indit()
        self.assertEqual(ix2.jegyzet("Cél.md")["fejezetek"][0]["szoveg"], "Új")
        self.assertIsNotNone(self.sor(ix2, "Tabla.md")["torolve"])
        self.assertIn("Uj.md", {f["ut"] for f in ix2.visszahivatkozasok("Cél.md")["forrasok"]})
        self.assertEqual(graf_kanonikus(ix2.graf()), graf_kanonikus(graf(self.v)))

    def test_valtozatlan_ujrainditas_szamlal(self):
        """Változás nélküli újraindulás után is a valódi darabszám áll az állapotban (a C07 állapotsora mutatja)."""
        ix, _ = self.indit()
        elotte = (ix.allapot()["fajlok"], ix.allapot()["jegyzetek"])
        ix.leallit()
        ix2, _ = self.indit()
        self.assertGreater(elotte[1], 0)
        self.assertEqual((ix2.allapot()["fajlok"], ix2.allapot()["jegyzetek"]), elotte)

    def test_types_json_valtozasa(self):
        (self.v / "T.md").write_text("---\nszam: 12\n---\n")
        ix, _ = self.indit()
        self.assertEqual(ix.jegyzet("T.md")["tulajdonsagok"][0]["tipus"], "number")
        (self.v / ".obsidian" / "types.json").write_text(json.dumps({"types": {"szam": "text"}}))
        ix.frissit([".obsidian/types.json"])
        t = ix.jegyzet("T.md")["tulajdonsagok"][0]
        self.assertEqual((t["tipus"], t["ervenyes"]), ("text", True))


class FigyeloTest(_Alap):
    def valtozas(self, ev, n, rp, mp=5):
        self.assertTrue(var_ra(lambda: any(e["tipus"] == "vault_valtozas" and rp in e["utak"] + e["torolt"]
                                           for e in ev[n:]), mp), f"nincs esemény: {rp}")
        return [e for e in ev[n:] if e["tipus"] == "vault_valtozas" and rp in e["utak"] + e["torolt"]][0]

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_fsevents_kulso_iras_torles_atnevezes(self):
        ix, ev = self.indit()
        self.assertEqual(ix.allapot()["figyelo"], "fsevents")
        n = len(ev)
        (self.v / "Cél X.md").write_text("# Cél X\nkülső szerkesztés zebracsík\n")
        e = self.valtozas(ev, n, "Cél X.md")
        self.assertIn("Cél X.md", e["kulso"])
        self.assertEqual(ix.kereses("zebracsik")["talalatok"][0]["ut"], "Cél X.md")
        n = len(ev)
        (self.v / "A" / "Jegyzet.md").rename(self.v / "A" / "Átnevezett.md")
        self.valtozas(ev, n, "A/Átnevezett.md")
        self.assertTrue(var_ra(lambda: self.sor(ix, "A/Jegyzet.md")["torolve"] is not None))
        n = len(ev)
        (self.v / "Cél X.md").unlink()
        self.assertIn("Cél X.md", self.valtozas(ev, n, "Cél X.md")["torolt"])

    def test_vaulton_kivulre_mutato_symlink_nem_kerul_az_indexbe(self):
        """T098: az index bejárása a fájlra mutató symlinket követte (`read_bytes`): egy vaultba tett symlink a felhasználó
        bármely olvasható fájljának szövegét a keresésbe és a beágyazásba vitte (az `/api/vault/fajl` elutasította)."""
        kint = self.v.parent / "kulso-titkos.md"
        kint.write_text("# kint\nTITKOS-KULSO-SZOVEG\n", encoding="utf-8")
        os.symlink(kint, self.v / "kulso.md")
        os.symlink(self.v / "Cél.md", self.v / "belso.md")                     # vaulton belülre mutató: marad
        ix, ev = self.indit()
        self.assertEqual(ix.kereses("TITKOS-KULSO-SZOVEG")["osszes"], 0)
        halmaz = ix.fajl_halmaz()
        self.assertNotIn("kulso.md", halmaz)
        self.assertIn("belso.md", halmaz)
        # az FSEvents-ből később jövő symlink sem olvasható
        os.symlink(kint, self.v / "kesobb.md")
        ix.frissit(["kesobb.md"])
        self.assertNotIn("kesobb.md", ix.fajl_halmaz())
        self.assertEqual(ix.kereses("TITKOS-KULSO-SZOVEG")["osszes"], 0)
        from core.index import feloldas
        self.assertNotIn("kulso.md", [rp for rp, _ in feloldas.bejaras(self.v)])

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_sajat_iras_nem_kulso(self):
        ix, ev = self.indit()
        va = vaultio.Vault(self.cfg, publish=lambda e, **k: ix.sajat_iras(e["ut"], e["hash"]) if e["tipus"] == "vault_iras" else None,
                           sajat=ix.vart_iras)       # mint az `App._vault_esemeny`: csak a vault_iras az indexé (a pillanat_hiba nem)
        d = va.read("Cél X.md")
        n = len(ev)
        va.write({"ut": "Cél X.md", "tartalom": d["tartalom"] + "saját mentés\n", "alap": d["hash"]})
        self.assertEqual(ix.kereses("\"saját mentés\"")["osszes"], 1)             # a válasz után már látszik
        e = self.valtozas(ev, n, "Cél X.md")
        self.assertEqual(e["kulso"], [])
        # a késő FSEvents sem lehet külső (T085: szentinel az alvás helyett): az FSEvents-folyam sorrendtartó, ezért egy
        # valóban külső fájl eseményének megérkezése után a saját mentés minden korábbi eseménye is megjött
        n2 = len(ev)
        (self.v / "Szentinel.md").write_text("# külső\n")
        self.assertIn("Szentinel.md", self.valtozas(ev, n2, "Szentinel.md")["kulso"])
        self.assertFalse(any("Cél X.md" in e.get("kulso", []) for e in ev[n:] if e["tipus"] == "vault_valtozas"))
        va.create({"nev": "Friss"})
        self.assertEqual(ix.jegyzet("Friss.md")["fejezetek"][0]["szoveg"], "Friss")

    def test_lekerdezo_tartalek(self):
        self.cfg.data["index"] = {**self.cfg.section("index"), "figyelo": "lekerdezes", "lekerdezes_mp": 0.1}
        ix, ev = self.indit()
        self.assertEqual(ix.allapot()["figyelo"], "lekerdezes")
        n = len(ev)
        (self.v / "Uj.md").write_text("[[Cél]]")
        self.assertIn("Uj.md", self.valtozas(ev, n, "Uj.md")["kulso"])


class AliasEsSzigetelesTest(_Alap):
    """C29.8 (T037): egy szám-/logikai alias és egy kivételt dobó fájl nem görgeti vissza a köteget és a hidegépítést."""

    fajlok = {**ALAP, "Szam.md": "---\naliases: [1984, true, 1.5]\n---\n# S\n"}

    def test_szam_alias_nem_rontja_el_a_hidegepitest(self):
        ix, _ = self.indit()
        self.assertIsNone(ix.allapot()["hiba"])                                 # ma: AttributeError, üres index
        halmaz = ix.fajl_halmaz()
        self.assertIn("Szam.md", halmaz)
        self.assertIn("Cél.md", halmaz)
        self.assertEqual(ix.allapot()["fajlok"], len(halmaz))
        self.assertEqual(ix.jegyzet("Szam.md")["aliasok"], ["1984", "true", "1.5"])

    def test_egy_hibas_fajl_elszigetelve_marad(self):
        from unittest import mock
        from core.index import elemzo
        eredeti = elemzo.elemez

        def elemez(txt, *a, **k):
            if "ROSSZ-JEGYZET" in txt:
                raise ValueError("szándékos elemzési hiba")
            return eredeti(txt, *a, **k)

        (self.v / "Rossz.md").write_text("# R ROSSZ-JEGYZET [[Cél]]\n", encoding="utf-8")
        with mock.patch.object(elemzo, "elemez", elemez):
            ix, _ = self.indit()                                               # a hidegépítés nem gördül vissza
            self.assertIsNone(ix.allapot()["hiba"])
            halmaz = ix.fajl_halmaz()
            self.assertIn("Cél.md", halmaz)
            self.assertIn("Rossz.md", halmaz)                                   # a fában marad
            sor = self.sor(ix, "Rossz.md")
            self.assertTrue(sor["fm_hiba"].startswith("indexelési hiba: ValueError"))
            self.assertEqual(ix.jegyzet("Rossz.md")["fejezetek"], [])           # származtatott sor nincs
            self.assertEqual([h["ut"] for h in ix.allapot()["elemzesi_hibak"]], ["Rossz.md"])
            self.assertEqual(ix.kereses("Cél")["osszes"] > 0, True)             # a keresés él
            # későbbi köteg: egy jó és egy rossz változás együtt
            (self.v / "Jo.md").write_text("# J\n", encoding="utf-8")
            (self.v / "Rossz2.md").write_text("# R2 ROSSZ-JEGYZET\n", encoding="utf-8")
            ix.frissit(["Jo.md", "Rossz2.md"])
            self.assertIn("Jo.md", ix.fajl_halmaz())
            self.assertIn("Rossz2.md", ix.fajl_halmaz())
            self.assertEqual(sorted(h["ut"] for h in ix.allapot()["elemzesi_hibak"]), ["Rossz.md", "Rossz2.md"])
            # a kijavított fájl kikerül a hibák közül, a törölt is
            (self.v / "Rossz2.md").write_text("# R2 rendben\n", encoding="utf-8")
            (self.v / "Rossz.md").unlink()
            ix.frissit(["Rossz2.md", "Rossz.md"])
            self.assertEqual(ix.allapot()["elemzesi_hibak"], [])
            self.assertEqual([f["szoveg"] for f in ix.jegyzet("Rossz2.md")["fejezetek"]], ["R2 rendben"])


class LemezenAlloNevTest(_Alap):
    """C29.8 (T038): az index figyelője a lemezen álló PONTOS névvel dolgozik (kis-nagybetűs átnevezés, NFD név)."""

    fajlok = {**ALAP, "Jegyzetek/A.md": "# A\n"}

    def _kis_nagybetu_erzekeny_fs(self) -> bool:
        p = self.v / "Kis-Nagy-Proba"
        p.write_text("x")
        try:
            return not (self.v / "kis-nagy-proba").exists()
        finally:
            p.unlink()

    def test_kis_nagybetus_atnevezes_nem_hagy_szellemsort(self):
        if self._kis_nagybetu_erzekeny_fs():
            self.skipTest("kis-nagybetű-érzékeny kötet: a kis-nagybetűs átnevezés itt két külön fájl, nincs szellemsor")
        for sorrend in (("Jegyzetek/A.md", "Jegyzetek/a.md"), ("Jegyzetek/a.md", "Jegyzetek/A.md")):
            with self.subTest(sorrend=sorrend):
                self.setUp()
                ix, _ = self.indit()
                os.rename(self.v / "Jegyzetek/A.md", self.v / "Jegyzetek/a.md")
                ix.frissit(list(sorrend))
                self.assertIsNotNone(self.sor(ix, "Jegyzetek/A.md")["torolve"])         # ma: két élő sor újraindulásig
                self.assertIsNone(self.sor(ix, "Jegyzetek/a.md")["torolve"])
                halmaz = ix.fajl_halmaz()
                self.assertIn("Jegyzetek/a.md", halmaz)
                self.assertNotIn("Jegyzetek/A.md", halmaz)
                ix.leallit()

    def test_nfd_nev_lemez_utja_nem_valt_nfc_re(self):
        ix, _ = self.indit()
        nfd = NFD + ".md"
        self.assertEqual(self.sor(ix, "Ütőér.md")["lemez_ut"], nfd)
        os.utime(self.v / nfd, ns=(time.time_ns(), time.time_ns() + 10**9))
        ix.frissit(["Ütőér.md"])                                                       # az FSEvents NFC-s útja
        self.assertEqual(self.sor(ix, "Ütőér.md")["lemez_ut"], nfd)                    # ma: NFC-re vált
        (self.v / nfd).write_text("# Ütőér\n[[Cél]] új\n", encoding="utf-8")
        ix.frissit(["Ütőér.md"])
        self.assertEqual(self.sor(ix, "Ütőér.md")["lemez_ut"], nfd)
        self.assertEqual(ix.lemez_ut("Ütőér.md"), nfd)


class MigracioTest(_Alap):
    """C10.6: a 2-es migráció után az 1-es sémájú index minden szöveges fájlt újraelemez és újra felold. C29.8: a 3-as
    (T037, T039, T041) ugyanígy — a setext fejezet és az idézet-horgony szabálya a régi sorokra is érvényes lesz."""

    fajlok = ELTERES

    def test_az_1es_index_ujraepul_az_uj_szaballyal(self):
        ix, _ = index_indit(self.cfg)
        db = ix.db_ut
        ix.leallit()
        c = tar.nyit(db, iro=True)                  # visszaállítjuk az 1-es állapotot: régi maszk, régi feloldás
        fid = c.execute("SELECT id FROM fajl WHERE ut = 'Elteres.md'").fetchone()[0]
        c.execute("INSERT INTO link(forras_id, sorrend, fajta, cel_nyers, kulcs, cel) VALUES (?, 99, 'wiki', 'Tilde', 'Tilde', NULL)",
                  (fid,))
        c.execute("UPDATE link SET cel = NULL, kulcs = 'Cél' WHERE cel_nyers = 'cél'")
        c.execute("UPDATE fajl SET torolve = 1.0 WHERE ut = 'Cél X.md'")
        c.execute("PRAGMA user_version = 1")
        c.close()
        ix, _ = self.indit()
        c = tar.nyit(ix.db_ut)
        try:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], tar.VERZIO)
            self.assertEqual(tar.VERZIO, 5)
            self.assertEqual(c.execute("SELECT count(*) FROM link WHERE cel_nyers = 'Tilde'").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT kulcs, cel FROM link WHERE cel_nyers = 'cél'").fetchall()[0][:],
                             ("cél", "Cél.md"))
            self.assertEqual(c.execute("SELECT count(*) FROM link WHERE kulcs != lower(kulcs)").fetchone()[0], 0)
        finally:
            c.close()
        self.assertEqual(graf_kanonikus(ix.graf()), graf_kanonikus(graf(self.v)))
        self.assertIsNone(self.sor(ix, "Cél X.md")["torolve"])                     # a fájl él: a jel a szinkronnal lekerül

    def test_a_2es_index_a_3as_migracio_utan_ujraelemez(self):
        """C29.8 (T039): a v2-es index sorai (setext fejezet nélkül, az idézet-horgony az utolsó sorra) a v3 után újraépülnek."""
        ix, _ = index_indit(self.cfg)
        db = ix.db_ut
        ix.leallit()
        (self.v / "Setext.md").write_text("Cím\n===\n> a\n> b ^k1\n", encoding="utf-8")
        ix, _ = index_indit(self.cfg)                                   # felveszi az új fájlt (a mostani szabállyal)
        ix.leallit()
        c = tar.nyit(db, iro=True)                                      # visszaállítjuk a v2-es állapotot: régi (hibás) sorok
        fid = c.execute("SELECT id FROM fajl WHERE ut = 'Setext.md'").fetchone()[0]
        c.execute("DELETE FROM fejezet WHERE fajl_id = ?", (fid,))
        c.execute("UPDATE blokk SET kezdo_sor = sor WHERE fajl_id = ?", (fid,))
        c.execute("PRAGMA user_version = 2")
        c.close()
        ix, _ = self.indit()
        c = tar.nyit(ix.db_ut)
        try:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], tar.VERZIO)
            self.assertEqual(c.execute("SELECT szint, szoveg, sor FROM fejezet WHERE fajl_id = ?", (fid,)).fetchall()[0][:],
                             (1, "Cím", 1))
            self.assertEqual(c.execute("SELECT azon, sor, kezdo_sor FROM blokk WHERE fajl_id = ?", (fid,)).fetchall()[0][:],
                             ("k1", 4, 3))
        finally:
            c.close()

    def test_ujabb_sema_hiba(self):
        ix, _ = index_indit(self.cfg)
        db = ix.db_ut
        ix.leallit()
        c = tar.nyit(db, iro=True)
        c.execute(f"PRAGMA user_version = {tar.VERZIO + 1}")
        c.close()
        with self.assertRaises(tar.SemaHiba):
            tar.nyit(db, iro=True)


if __name__ == "__main__":
    unittest.main()
