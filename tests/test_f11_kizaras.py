"""F11 `14-appearance-06` + PLAN §11 "Files & links -> excluded files": the user list of excluded paths.

The list only changes *visibility*: the tree dims the file, search / graph / quick-switcher aliases / unlinked mentions /
hybrid search skip it. The file, its index rows, link resolution, backlinks and snapshots stay as they were. Synthetic vaults only."""
import json
import unicodedata
import unittest

from core import termek_beallitasok as b
from core.asszisztens.emlites import Emlitesek
from core.index import graf_meta, kizaras
from core.index.hibrid import kereso as hibrid_kereso
from core.utvonalak import HttpError
from tests.helpers import ir, tmpdir
from tests.index_segedek import index_indit
from tests.multi_user import munkater, termek_cfg, termek_telepites

FAJLOK = {
    "Public.md": "# Public\nSee [[Secret]] and the unique zebra word.\n",
    "Notes/Open.md": "# Open\n[[Public]] zebra here too\n",
    "Archive/Old.md": "---\naliases: [Ancient]\nTags: [oldtag]\nStatus: done\n---\n# Old\nzebra [[Public]] [[Missing from archive]]\n",
    "Secret.md": "---\naliases: [Hidden alias]\n---\n# Secret\nzebra text\n",
    "Private (draft)/Plan.md": "# Plan\nzebra\n",
    "Mentioner.md": "Today I read about Secret and about Public in one place, Ancient too.\n",
}


class KizarasModulTest(unittest.TestCase):
    def test_elotag_szegmenshatarral_kis_nagybetu_es_nfc_fuggetlenul(self):
        k = kizaras.fordit(["Archive/", "Notes/Draft.md", "Árvíz"])
        self.assertTrue(k.kizart("Archive/Old.md"))
        self.assertTrue(k.kizart("archive/deep/er.md"))
        self.assertFalse(k.kizart("Archive.md"))
        self.assertFalse(k.kizart("Notes/Draft.md.bak"))
        self.assertTrue(k.kizart("Notes/Draft.md"))
        self.assertTrue(k.kizart(unicodedata.normalize("NFD", "Árvíz/x.md")))
        self.assertFalse(k.kizart("Árvízi/x.md"))              # a név eleje nem elég: szegmenshatár kell
        self.assertFalse(kizaras.fordit([]).kizart("Archive/Old.md"))

    def test_regex_az_utvonalon_es_hibas_minta_kimarad(self):
        k = kizaras.fordit([r"/\.draft\.md$/", "/(a+)+$/", "/(/", ""])
        self.assertTrue(k.kizart("X/Note.draft.md"))
        self.assertFalse(k.kizart("X/Note.md"))
        self.assertEqual(k.jel, (r"/\.draft\.md$/",))          # a veszélyes, a fordíthatatlan és az üres minta nem lép be

    def test_ellenorzes_elutasitja_a_veszelyes_hibas_es_tul_nagy_listat(self):
        for rossz in ("", "   ", "/(a+)+$/", "/(/", "a" * 201, "line\nbreak", "../x", 7, None):
            with self.subTest(rossz=rossz), self.assertRaises(kizaras.MintaHiba):
                kizaras.minta_ellenoriz(rossz)
        self.assertEqual(kizaras.lista_ellenoriz([" Archive/ ", "Archive/", "Archive/"]), ["Archive/"])
        with self.assertRaises(kizaras.MintaHiba):
            kizaras.lista_ellenoriz(["x"] * (kizaras.MAX_DB + 1))
        with self.assertRaises(kizaras.MintaHiba):
            kizaras.lista_ellenoriz("Archive/")


class BeallitasTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.v, self.id = munkater(self.t.name, "Notes")
        self.cfg = termek_cfg(self.root, self.home, self.v)

    def ment(self, d):
        return b.ir(self.cfg, b.olvas(self.cfg)["rev"], d)

    def test_alapertek_ures_lista_es_a_lista_megmarad_ujratoltes_utan(self):
        self.assertEqual(b.olvas(self.cfg)["ertek"]["fajlok"]["kizart"], [])
        r = self.ment({"fajlok": {"kizart": ["Archive/", r"/\.tmp$/"]}})
        self.assertEqual(r["ertek"]["fajlok"]["kizart"], ["Archive/", r"/\.tmp$/"])
        ujra = termek_cfg(self.root, self.home, self.v)
        self.assertEqual(b.olvas(ujra)["ertek"]["fajlok"]["kizart"], ["Archive/", r"/\.tmp$/"])
        self.assertEqual(kizaras.hatekony_lista(ujra), ["Archive/", r"/\.tmp$/"])

    def test_hibas_lista_semmit_nem_ir(self):
        regi = (self.v / ".manifold/workspace.toml").read_bytes()
        for rossz in ("Archive/", ["/(a+)+$/"], [1], ["x"] * 201, ["a\nb"], [""]):
            with self.subTest(rossz=rossz), self.assertRaises(HttpError) as e:
                self.ment({"fajlok": {"kizart": rossz}})
            self.assertEqual(e.exception.param["kulcs"], "fajlok.kizart")
            self.assertEqual((self.v / ".manifold/workspace.toml").read_bytes(), regi)

    def test_obsidian_userIgnoreFilters_magva_a_listanak_amig_a_felhasznalo_sajatot_nem_ment(self):
        app = self.v / ".obsidian/app.json"
        app.write_text(json.dumps({"userIgnoreFilters": ["Archive/", "/(a+)+$/", 5, "/\\.tmp$/"]}), encoding="utf-8")
        eredeti = app.read_bytes()
        cfg = termek_cfg(self.root, self.home, self.v)
        self.assertEqual(b.olvas(cfg)["ertek"]["fajlok"]["kizart"], ["Archive/", r"/\.tmp$/"])
        self.assertTrue(kizaras.betolt(cfg).kizart("Archive/x.md"))
        r = b.ir(cfg, b.olvas(cfg)["rev"], {"fajlok": {"kizart": []}})          # a felhasználó törli: az üres lista a saját döntése
        self.assertEqual(r["ertek"]["fajlok"]["kizart"], [])
        self.assertFalse(kizaras.betolt(cfg).kizart("Archive/x.md"))
        self.assertEqual(app.read_bytes(), eredeti)                              # az Obsidian-fájl érintetlen

    def test_betu_nevek(self):
        for jo in ("", "Helvetica Neue", "SF Pro Text", "Source Serif 4", "Noto Sans CJK JP", "Menlo", "Író-Gép_2.0", "A+B"):
            self.assertFalse(b.betu_nev_hiba(jo), jo)
        for rossz in ('"x"', "x;y", "a{b}", "url(http://x)", "x, serif", "a\\b", "a:b", "a/b", " pad", "pad ", "a  b", "x" * 81,
                      "a\nb", "@import", "a'b", 3, None, ["a"]):
            self.assertTrue(b.betu_nev_hiba(rossz), repr(rossz))
        r = self.ment({"megjelenes": {"betu_szoveg": "Helvetica Neue", "betu_mono": "Menlo"}})
        self.assertEqual((r["ertek"]["megjelenes"]["betu_szoveg"], r["ertek"]["megjelenes"]["betu_mono"]), ("Helvetica Neue", "Menlo"))
        for rossz in ('x";}body{display:none', "url(https://example.invalid/f.woff)"):
            with self.subTest(rossz=rossz), self.assertRaises(HttpError):
                self.ment({"megjelenes": {"betu_szoveg": rossz}})
        self.assertEqual(self.ment({"megjelenes": {"betu_szoveg": ""}})["ertek"]["megjelenes"]["betu_szoveg"], "")

    def test_auto_par_kapcsolok_alapbol_be_es_logikaiak(self):
        e = b.olvas(self.cfg)["ertek"]["szerkeszto"]
        self.assertEqual((e["auto_par_zarojel"], e["auto_par_idezojel"], e["auto_par_jeloles"]), (True, True, True))
        r = self.ment({"szerkeszto": {"auto_par_idezojel": False}})
        self.assertFalse(r["ertek"]["szerkeszto"]["auto_par_idezojel"])
        self.assertTrue(r["ertek"]["szerkeszto"]["auto_par_zarojel"])
        with self.assertRaises(HttpError):
            self.ment({"szerkeszto": {"auto_par_jeloles": "no"}})


class ErvenyesitesTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.v, _ = munkater(self.t.name, "Notes")
        for rp, t in FAJLOK.items():
            ir(self.v, rp, t)
        self.cfg = termek_cfg(self.root, self.home, self.v)
        self.ix, self.esemenyek = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.eredeti = {rp: (self.v / rp).read_bytes() for rp in FAJLOK}

    def kizar(self, *mintak):
        return b.ir(self.cfg, b.olvas(self.cfg)["rev"], {"fajlok": {"kizart": list(mintak)}})

    def utak(self, valasz):
        return {t["ut"] for t in valasz["talalatok"]}

    def test_fa_halvanyit_de_nem_rejt_a_fajl_marad(self):
        self.assertFalse(any("kizart" in f for f in self.ix.fa()["fajlok"]))
        self.kizar("Archive/", "Secret.md")
        fa = {f["ut"]: f for f in self.ix.fa()["fajlok"]}
        self.assertEqual({u for u, f in fa.items() if f.get("kizart")}, {"Archive/Old.md", "Secret.md"})
        self.assertEqual(set(fa), set(FAJLOK))                                   # semmi sem tűnt el a fáról / az indexből
        self.assertEqual(set(self.ix.fajl_halmaz()), set(FAJLOK))
        self.assertEqual({rp: (self.v / rp).read_bytes() for rp in FAJLOK}, self.eredeti)

    def test_kereses_kihagyja_es_a_lista_torlese_visszahozza(self):
        self.assertEqual(self.utak(self.ix.kereses("zebra")), {"Public.md", "Notes/Open.md", "Archive/Old.md", "Secret.md", "Private (draft)/Plan.md"})
        self.kizar("Archive/", "Secret.md", "/^Private/")
        v = self.ix.kereses("zebra")
        self.assertEqual(self.utak(v), {"Public.md", "Notes/Open.md"})
        self.assertEqual(v["osszes"], 2)
        self.assertEqual(self.utak(self.ix.kereses("path:Archive")), set())
        self.kizar()
        self.assertEqual(len(self.ix.kereses("zebra")["talalatok"]), 5)

    def test_kereses_limit_a_kizart_talalatok_utan_is_tolt(self):
        self.kizar("Archive/", "Secret.md", "/^Private/")
        v = self.ix.kereses("zebra", 2)
        self.assertEqual(len(v["talalatok"]), 2)

    def test_hibrid_lexikai_kereso_is_kihagyja(self):
        from core.index.kizaras import betolt
        self.kizar("Archive/", "Secret.md")
        kr = hibrid_kereso.HibridKereso(self.ix.olvaso, kizart=betolt(self.cfg))
        for q in ("zebra", "path:Notes zebra", "zebra text"):
            with self.subTest(q=q):
                r = kr.keres(q, 20, "lexikai")
                self.assertFalse({"Archive/Old.md", "Secret.md"} & self.utak(r))
        self.assertIn("Public.md", self.utak(kr.keres("zebra", 20, "lexikai")))

    def test_vault_valasz_jeloltek_es_hasonlo_jegyzetek_kihagyjak(self):
        """AI context builders: the "Ask your vault" candidates and the similar-notes list skip excluded notes."""
        from core.index.hibrid import hasonlo
        from core.index.kizaras import betolt
        kr = hibrid_kereso.HibridKereso(self.ix.olvaso)
        self.assertIn("Secret.md", {j.darab.ut for j in kr.darab_jeloltek("zebra text", 20)})
        self.kizar("Secret.md", "Archive/")
        kr = hibrid_kereso.HibridKereso(self.ix.olvaso, kizart=betolt(self.cfg))
        utak = {j.darab.ut for j in kr.darab_jeloltek("zebra text", 20)}
        self.assertTrue(utak)
        self.assertFalse({"Secret.md", "Archive/Old.md"} & utak)

        class Tar:                                          # a vektortár hamisítványa: minden jegyzet hasonló a Public.md-hez
            def jegyzet_hasonlosag(self, ut):
                return {u: 0.5 for u in FAJLOK}

            def jegyzet_hash(self, ut):
                return None
        hirtelen = hasonlo.hasonlok(self.ix.olvaso, Tar(), "Public.md", 10, kizart=betolt(self.cfg))
        self.assertEqual({t["ut"] for t in hirtelen["talalatok"]}, {"Notes/Open.md", "Private (draft)/Plan.md", "Mentioner.md"})
        mind = hasonlo.hasonlok(self.ix.olvaso, Tar(), "Public.md", 10)
        self.assertIn("Secret.md", {t["ut"] for t in mind["talalatok"]})

    def test_graf_csucs_el_es_gyorsitotar(self):
        g0 = self.ix.graf_api()
        self.assertIn("Secret.md", g0["csucsok"])
        self.assertIn(["Public.md", "Secret.md"], g0["elek"])
        self.assertIn("Missing from archive", g0["feloldatlan"])
        b0, etag0 = self.ix.graf_valasz()
        self.kizar("Archive/", "Secret.md")
        g = self.ix.graf_api()
        self.assertEqual(set(g["csucsok"]), set(FAJLOK) - {"Archive/Old.md", "Secret.md"})
        self.assertEqual(g["elek"], [["Notes/Open.md", "Public.md"]])           # a kizárt végpontú élek nem rajzolódnak
        self.assertNotIn("Missing from archive", g["feloldatlan"])               # a kizárt jegyzet feloldatlan linkje sem
        b1, etag1 = self.ix.graf_valasz()                                        # a gyorsítótár a lista jele szerint érvénytelen
        self.assertNotEqual(etag0, etag1)
        self.assertNotIn(b"Secret.md", b1)
        self.kizar()
        self.assertEqual(self.ix.graf_valasz()[1], etag0)

    def test_graf_meta_cimkek_es_tulajdonsagok_kizartakra_nem(self):
        m = graf_meta.graf_meta(self.ix)
        self.assertIn("Archive/Old.md", m["cimkek"])
        self.kizar("Archive/")
        m = graf_meta.graf_meta(self.ix)
        self.assertNotIn("Archive/Old.md", m["cimkek"])
        self.assertNotIn("Archive/Old.md", m["tulajdonsagok"])
        self.assertNotIn("Archive/Old.md", {u for u, _ in m["feloldatlan_elek"]})

    def test_gyorsvalto_aliasok_kizartra_nincsenek(self):
        self.assertEqual(set(self.ix.aliasok()["aliasok"]), {"Archive/Old.md", "Secret.md"})
        self.kizar("Archive/")
        self.assertEqual(set(self.ix.aliasok()["aliasok"]), {"Secret.md"})

    def test_linkeletlen_emlitesek_forrasa_es_cele(self):
        forrasok = lambda: {x["ut"] for x in self.ix.emlitesek("Secret.md")["forrasok"]}
        self.assertIn("Mentioner.md", forrasok())
        self.kizar("Mentioner.md")
        self.assertNotIn("Mentioner.md", forrasok())                             # a kizárt jegyzet nem javasol említést
        self.kizar()
        motor = Emlitesek(self.cfg, self.ix)
        cel = lambda: {c for c, in ((x["ut"],) for x in self.ix.kimeno_emlitesek("Mentioner.md", motor)["forrasok"])}
        self.assertIn("Secret.md", cel())
        self.assertIn("Archive/Old.md", cel())                                   # az alias-említés (Ancient)
        self.kizar("Secret.md", "Archive/")
        self.assertEqual(cel(), {"Public.md"})                                   # a kizárt jegyzet nem cél (a szótár is újraépül)

    def test_link_feloldas_hatlinkek_es_atnevezes_alap_nem_valtozik(self):
        elotte = self.ix.feloldas("Public.md", ["Secret", "Old", "Ancient"])
        hatlink = self.ix.visszahivatkozasok("Archive/Old.md")
        jegyzet = self.ix.jegyzet("Public.md")
        self.kizar("Archive/", "Secret.md")
        self.assertEqual(self.ix.feloldas("Public.md", ["Secret", "Old", "Ancient"]), elotte)      # a link továbbra is feloldódik
        self.assertTrue(any(e.get("ut") == "Secret.md" for e in self.ix.feloldas("Public.md", ["Secret"])))
        self.assertEqual(self.ix.visszahivatkozasok("Archive/Old.md"), hatlink)
        self.assertEqual(self.ix.jegyzet("Public.md")["linkek"], jegyzet["linkek"])
        self.assertEqual(self.ix.jegyzet("Secret.md")["ut"], "Secret.md")                           # a kizárt jegyzet olvasható marad
        self.assertEqual({rp: (self.v / rp).read_bytes() for rp in FAJLOK}, self.eredeti)

    def test_mentes_index_esemenyt_kuld_csak_ha_a_hatekony_lista_valtozik(self):
        class Busz:
            def __init__(self):
                self.e = []

            def publish(self, e):
                self.e.append(e)

        class App:
            pass

        app = App()
        app.cfg, app.index, app.bus = self.cfg, self.ix, Busz()
        marad = len(self.esemenyek)

        class K:
            def __init__(self, torzs):
                self.app, self._t = app, torzs

            def torzs(self):
                return self._t

        r = _utvonal(app, "PUT", "/api/beallitasok")
        rev = b.olvas(self.cfg)["rev"]
        r(K({"rev": rev, "valtozas": {"fajlok": {"kizart": ["Archive/"]}}}))
        self.assertGreater(len(self.esemenyek), marad)
        self.assertEqual(self.esemenyek[-1]["tipus"], "index")
        marad = len(self.esemenyek)
        r(K({"rev": b.olvas(self.cfg)["rev"], "valtozas": {"megjelenes": {"csend": True}}}))
        self.assertEqual(len(self.esemenyek), marad)

    def test_elonezet_vegpont_darabszam_es_hibak_semmit_sem_ir(self):
        class App:
            pass

        app = App()
        app.cfg, app.index = self.cfg, self.ix

        class K:
            def __init__(self, torzs):
                self.app, self._t = app, torzs

            def torzs(self):
                return self._t

        elonezet = _utvonal(app, "POST", "/api/beallitasok/kizart-elonezet")
        r = elonezet(K({"mintak": ["Archive/", "/(a+)+$/", r"/^Notes\//", "Nothing/", ""]}))
        self.assertEqual(r["osszes"], len(FAJLOK))
        self.assertEqual(r["kizart"], 2)
        self.assertEqual([(m["db"], m["hiba"]) for m in r["mintak"]],
                         [(1, None), (0, "regex_veszelyes"), (1, None), (0, None), (0, "ures")])
        with self.assertRaises(HttpError):
            elonezet(K({"mintak": "Archive/"}))
        with self.assertRaises(HttpError):
            elonezet(K({"mintak": [], "extra": 1}))
        self.assertEqual({rp: (self.v / rp).read_bytes() for rp in FAJLOK}, self.eredeti)


def _utvonal(app, metodus, ut):
    """A `termek_beallitasok.utvonalak` által regisztrált kezelő (a regiszter-hamisítvány nem indít szervert)."""
    talalt = {}

    class R:
        def get(self, u, f):
            talalt[("GET", u)] = f

        def put(self, u, f):
            talalt[("PUT", u)] = f

        def post(self, u, f):
            talalt[("POST", u)] = f

    b.utvonalak(R())
    return talalt[(metodus, ut)]


if __name__ == "__main__":
    unittest.main()
