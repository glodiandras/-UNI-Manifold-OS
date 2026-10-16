"""A termék alapértékei semlegesek (F3-DESIGN §7.2): a fejlesztő konvenciói (`ATTCHMNTS - …`, `X01 - Napló & To-Do`, tantárgy-betűk és
-szótárak, `D13 - …` téma-mappák, szigorú séma) csak a `v2-kompat` presetben élnek (`tests/preset_v2/`). Itt: preset nélküli álgyökér,
semleges álvault (`tests/vaultgyar.py`) — nincs sémasértés, nincs kísérő-varázslat, a napi jegyzet a `Daily/` alatt jön létre."""
import json
import unittest
from datetime import date
from types import SimpleNamespace

from core import automatika, kartya_feladat, kiserok, naplo, naptar, pdfkiemeles, vaultio
from core.asszisztens.beallitasok import ALAP as ASSZ_ALAP, beallitasok
from core.tulajdonsagok import Sema, Tulajdonsagok
from modulok.fuzet import katalogus, modszer
from modulok.ytdlp import egyezes, integralas
from tests.helpers import REPO, ir, tmpdir
from tests.index_segedek import index_indit
from tests.vaultgyar import JEGYZETEK, alg_semleges

# a fejlesztő saját neveiből: egyik sem szerepelhet a szállított alapértékek között
TILTOTT = ("ATTCHMNTS", "X01", "AI01", "AI02", "AI03", "Prjct", "Napló & To-Do", "ropdolgozat", "Notebooks - digitalized", "Rendezetlen",
           "D13", "zanza", "Zanza", "quizes")


def _szovegek(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _szovegek(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _szovegek(v)
    elif isinstance(x, str):
        yield x


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)


class KonfigTest(Alap):
    def test_nincs_fejleszto_konvencio_a_konfigban(self):
        for sz in _szovegek({k: v for k, v in self.cfg.data.items() if not k.startswith("_")}):
            for t in TILTOTT:
                self.assertNotIn(t, sz, f"fejlesztői név az alapértékek között: {sz!r}")

    def test_a_szallitott_fajlok_tiszta(self):
        for rel in ("config/os.toml", "config/schema-default.json"):
            szoveg = (REPO / rel).read_text(encoding="utf-8")
            for t in ("ATTCHMNTS", "X01 -", "AI01", "AI02", "Prjct", "ropdolgozat", "Notebooks - digitalized"):
                # a megjegyzésekben sem: a v2-konvenciók helye a preset
                self.assertNotIn(t, szoveg, f"{rel}: {t}")

    def test_kisero_alapok(self):
        self.assertEqual(self.cfg.section("vault")["kisero_elotag"], "Manifold - ")
        self.assertEqual(kiserok.kisero_mappak(self.cfg), {"kartya": "Manifold - Cards", "kviz": "Manifold - Quizzes",
                                                           "osszefoglalas": "Manifold - Summaries", "fuzet": "Manifold - Photos",
                                                           "video": "Manifold - Videos"})
        self.assertEqual(self.cfg.section("kviz")["mappa"], "Manifold - Quizzes")        # a felület `allando.ts`-e ennek tükre

    def test_a_szotarak_uresek(self):
        c = self.cfg
        self.assertEqual((c.section("pdf", "tags"), c.section("pdf", "nevek")), ({}, {}))
        self.assertEqual((c.section("naptar", "szotar", "targyak"), c.section("naptar", "szotar", "csoportok")), ({}, {}))
        self.assertEqual(c.section("asszisztens", "tantargy_nevek"), {})
        for kulcs in ("higienia_arva_kizart", "emlites_kizart", "kartya_kizart"):
            self.assertEqual(c.section("asszisztens")[kulcs], [], kulcs)
        self.assertEqual((c.section("video")["kizart_mappak"], c.section("video")["tema_minta"]), ([], ""))
        self.assertEqual(c.section("fuzet")["mappak"], [])
        self.assertNotIn("ropdolgozat", c.section("naptar", "szotar")["dolgozat"])
        self.assertNotIn("ropi", c.section("naptar", "szotar")["dolgozat"])

    def test_a_kodbeli_ikrek_is_uresek(self):
        self.assertEqual((naptar.TARGYAK, naptar.CSOPORTOK), ({}, {}))
        self.assertEqual(naptar.targy("Matek témazáró", naptar.targyak_cfg(self.cfg)), [])
        self.assertEqual(ASSZ_ALAP["tantargy_nevek"], {})
        self.assertEqual(beallitasok(self.cfg)["tantargy_nevek"], {})
        self.assertEqual(integralas.targy_terkep(), {})
        self.assertIsNone(integralas.targy_betu({"targy": "Történelem"}))
        self.assertIsNone(modszer.targy_betu("Matematika"))
        self.assertFalse(hasattr(katalogus, "TANTARGYAK") or hasattr(modszer, "TANTARGYAK"))
        self.assertIsNone(pdfkiemeles.cimke(self.cfg, "M01 - Algebra/a.pdf"))
        self.assertIsNone(kiserok.subject_of(self.cfg, "M01 - Algebra/a.md"))

    def test_naplo_alapja(self):
        self.assertEqual(self.cfg.section("naplo")["ut"], "[Daily]/YYYY-MM-DD")
        self.assertEqual(naplo.napi_ut(self.cfg, date(2026, 10, 2)), "Daily/2026-10-02.md")
        self.assertEqual(naplo.ALAP_UT, self.cfg.section("naplo")["ut"])


class KisereVarazslatNelkulTest(Alap):
    def test_a_fejleszto_mappai_nem_kiserok(self):
        elotag = automatika.kisero_elotag(self.cfg)
        self.assertEqual(elotag, "Manifold - ")
        for ut in ("ATTCHMNTS - cards/x.md", "X01 - Napló & To-Do/a.md", "D13 - CS50/a.md", "Books/a.md"):
            self.assertTrue(automatika.tartalmi_ut(ut, elotag), ut)
        for ut in ("Manifold - Cards/x.md", "A/Manifold - Quizzes/x.md", "Manifold - Summaries/x.md"):
            self.assertFalse(automatika.tartalmi_ut(ut, elotag), ut)
        f = automatika.Fogyaszto("teszt", "t", kuszob=0.2, csend_perc=10, min_hossz=100)
        self.assertEqual(automatika.dont(f, "Manifold - Cards/x.md", "h", 0, 1e6, None, lambda u: "")[0], "szuro")

    def test_az_asszisztens_kizarasai_csak_a_sablon_es_a_kiserok(self):
        b = beallitasok(self.cfg)
        for kulcs in ("higienia_arva_kizart", "emlites_kizart", "kartya_kizart"):
            self.assertEqual(sorted(b[kulcs]), ["Manifold - ", "_Template/"], kulcs)

    def test_nincs_alapertelmezett_tema_konvencio(self):
        for nev in ("D13 - CS50", "Manifold - Cards", "_Template"):
            (self.v / nev).mkdir(exist_ok=True)
        kw = egyezes.index_beallitas(self.cfg)
        temak = egyezes.temak(self.v, kw["tema_minta"], kw["kizart_mappak"])
        self.assertEqual(temak, sorted(["Archive", "D13 - CS50", "Daily", "Projects", "Reading"]))     # minden látható gyökérmappa
        self.assertEqual(kw["tema_minta"].groups, 0)

    def test_az_automatikus_kartya_szuro_tantargyi_terkep_nelkul_semmit_nem_enged(self):
        szuro = kartya_feladat.automatikus_szuro(self.cfg)
        for ut in ("Projects/Website redesign.md", "Reading/Deep Work.md", "M01 - Algebra/a.md"):
            self.assertFalse(szuro(ut), ut)                                            # a tantárgy-betűk a munkatér sajátjai
        self.assertTrue(kartya_feladat.kezi_szuro(self.cfg)("Projects/Website redesign.md"))     # kézzel bármi tartalmi jegyzet


class SemaTest(Alap):
    def test_nincs_sermes_a_semleges_vaulton(self):
        t = Tulajdonsagok(self.cfg, SimpleNamespace(tipusok={}))
        self.assertEqual((t.sema.mod, t.sema.status_gazdai), ("ki", True))       # a Status gazdai védelme a `ki` módban is él (T127)
        for rp, szoveg in JEGYZETEK.items():
            fm = vaultio_fm(szoveg)
            e = t.elemez(rp, fm)
            self.assertEqual((e["problemak"], e["tanacsok"]), ([], []), rp)
            self.assertEqual(t.h1_problemak(rp, szoveg), [], rp)
        self.assertEqual(t.uj_jegyzet_ellenorzes("Projects/x.md", "---\nicon: x\ncover: y\nfoo: 1\n---\n")["sertesek"], [])

    def test_a_szallitott_sema_semleges(self):
        adat = json.loads((self.root / "config" / "schema-default.json").read_text(encoding="utf-8"))
        self.assertEqual((adat["mezosorrend"], adat["tags_ertekkeszlet"], adat["status_ertekkeszlet"], adat["status_gazdai"]),
                         ([], None, None, True))
        self.assertEqual([o["kisero"] for o in adat["kivetel_osztalyok"]], ["kviz", "kartya", "osszefoglalas"])
        self.assertTrue(all("utvonal_elotag" not in o for o in adat["kivetel_osztalyok"]))     # nincs külön lista: a kiserok adja
        sema = Sema.betolt(self.cfg)
        self.assertEqual({o["nev"] for o in sema.osztalyok}, {"kviz", "kartya", "osszefoglalo"})

    def test_nincs_v2_sema_a_fajtaban(self):
        self.assertFalse((REPO / "config" / "vault-sema.json").exists())                     # a séma a presetbe költözött
        self.assertTrue((REPO / "config" / "presets" / "v2-kompat.schema.json").is_file())


def vaultio_fm(szoveg: str):
    """A jegyzet frontmatter-blokkja (a `---` sorokkal), vagy None."""
    from core.index.maszk import FM_RE
    m = FM_RE.match(szoveg)
    return m.group(0) if m else None


class NaploTest(Alap):
    def test_a_napi_jegyzet_a_daily_alatt_jon_letre(self):
        v = vaultio.Vault(self.cfg)
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        app = SimpleNamespace(vault=v, index=ix)
        r = naplo.megnyit_vagy_letrehoz(app, "2026-10-02")
        self.assertEqual((r["ut"], r["letrejott"]), ("Daily/2026-10-02.md", True))
        self.assertTrue((self.v / "Daily" / "2026-10-02.md").is_file())
        self.assertEqual(sorted(p.name for p in (self.v / "Daily").iterdir()), ["2026-10-01.md", "2026-10-02.md"])
        ir(self.v, "Daily/2026-10-03.md", "a felhasználó szövege\n")
        self.assertEqual(naplo.megnyit_vagy_letrehoz(app, "2026-10-03")["letrejott"], False)


class KalibracioRogzitesTest(unittest.TestCase):
    """F3-DESIGN §8: a `--rogzit` a termékben elutasított (a kódfa `os.toml`-ja a csomag része, írásvédett); a hordozható mód változatlan."""

    JELENTES = {"allapot": "javasolt"}

    def test_a_termekben_elutasitott_az_irasa_elott(self):
        from core.felkeszultseg import kalibracio
        cfg = SimpleNamespace(elrendezes="termek", source="/nincs/ilyen/os.toml")
        with self.assertRaisesRegex(ValueError, "termékben"):
            kalibracio.config_ir(cfg, self.JELENTES)

    def test_hordozhato_modban_a_konfig_helyet_kerdezi(self):
        from core.felkeszultseg import kalibracio
        cfg = SimpleNamespace(elrendezes="hordozhato", source="/nincs/ilyen/os.toml")
        with self.assertRaisesRegex(ValueError, "helye ismeretlen"):
            kalibracio.config_ir(cfg, self.JELENTES)


if __name__ == "__main__":
    unittest.main()
