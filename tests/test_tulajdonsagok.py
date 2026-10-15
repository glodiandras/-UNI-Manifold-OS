"""A tulajdonság-szerkesztő háttere (C11b): a frontmatter bájthű, soronkénti módosítása és a séma-ellenőrzés
(L33, L34, L39). Tiszta szövegműveletek: álvault és git nélkül, csak az álgyökér config-ja kell."""
import re
import unittest
from types import SimpleNamespace

from core import tulajdonsagok
from core.index import elemzo
from core.index.indexelo import NemKesz
from core.index.maszk import FM_RE
from core.utvonalak import HttpError
from tests.helpers import alg_core, tmpdir

NORMAL = """---
Tags:
  - Mathematics
Source:
  - "[[09 - Matematika.pdf#page=125]]"
Status: Completed
NN:
  - "[[02 - A mohácsi csata]]"
Canvas: "[[M03 - Algebra.canvas]]"
---

# Cím
"""


def fm_blokk(szoveg: str) -> str:
    m = FM_RE.match(szoveg)
    return m.group(0)


class Alap(unittest.TestCase):
    def setUp(self):
        self._tmp = tmpdir()
        self.addCleanup(self._tmp.cleanup)
        cfg, _, _ = alg_core(self._tmp.name)
        self.t = tulajdonsagok.Tulajdonsagok(cfg, SimpleNamespace(tipusok={}))

    def mod(self, fm, muvelet="beallit", kulcs="Tags", ertek=None, ut="F01 - Fizika/Jegyzet.md", **k):
        return self.t.modosit(ut, fm, muvelet, kulcs, ertek, **k)


class EloErtekkeszlet(Alap):
    """CX-002 (80(d)): az értékkészlet = séma + a MÁSIK jegyzetekben használt értékek (a szövegbeli `#címke` is címke)."""
    UT = "F01 - Fizika/Jegyzet.md"

    def hasznalat(self, tags=None, status=None):
        self.t.index.ertekkeszlet_hasznalat = lambda: {"tags": tags or {}, "status": status or {}}

    def test_meglevo_cimke_ervenyes_az_utolso_elofordulasig(self):
        tags = {"active-recall": {"db": 16, "utak": ["A.md", "B.md"]}}
        self.hasznalat(tags)
        fm = fm_blokk(NORMAL)
        self.assertTrue(self.mod(fm, ertek=["Active-recall"])["ok"])
        self.assertTrue(self.mod(fm, ertek=["#active-recall"])["ok"])          # az Obsidian címkéje kis-nagybetűtől független
        tags.clear()
        self.assertFalse(self.mod(fm, ertek=["Active-recall"])["ok"])

    def test_a_jegyzet_sajat_erteke_nem_legitimalja_onmagat(self):
        self.hasznalat({"sajat": {"db": 1, "utak": [self.UT]}}, {"Saját": {"db": 1, "utak": [self.UT]}})
        fm = "---\nTags:\n  - Sajat\nSource:\nStatus: Saját\nNN:\nCanvas:\n---\n"
        p = self.t.elemez(self.UT, fm)["problemak"]
        self.assertEqual(sorted((x["kod"], x["kulcs"]) for x in p), [("ertekkeszlet", "Status"), ("ertekkeszlet", "Tags")])
        # egy másik jegyzetből nézve ugyanez az érték már használt
        self.assertEqual(self.t.elemez("F01 - Fizika/Masik.md", fm)["problemak"], [])

    def test_meglevo_status_ervenyes_de_gep_nem_irhatja(self):
        self.hasznalat(status={"Saját": {"db": 2, "utak": ["A.md", "B.md"]}})
        self.assertTrue(self.mod(fm_blokk(NORMAL), kulcs="Status", ertek="Saját")["ok"])
        self.assertTrue(self.t.sema.status_gazdai)

    def test_nem_kesz_index_mellett_csak_a_sema_es_csak_megerositheto(self):
        def nem_kesz():
            raise NemKesz("az index még nem épült fel")
        self.t.index.ertekkeszlet_hasznalat = nem_kesz
        r = self.mod(fm_blokk(NORMAL), ertek=["Active-recall"])
        self.assertFalse(r["ok"])
        self.assertTrue(r["megerositheto"])
        self.assertEqual([(x["kod"], x["szint"]) for x in r["problemak"]], [("ertekkeszlet", tulajdonsagok.SERTES)])
        self.assertIn("index még épül", r["problemak"][0]["uzenet"])
        self.assertTrue(self.mod(fm_blokk(NORMAL), ertek=["Active-recall"], megerosit=True)["ok"])

    def test_generacionkent_egy_index_lekerdezes(self):
        hivas = []
        self.t.index.generacio = 1
        self.t.index.ertekkeszlet_hasznalat = lambda: hivas.append(1) or {"tags": {}, "status": {}}
        for _ in range(3):
            self.mod(fm_blokk(NORMAL), ertek=["Active-recall"])
        self.assertEqual(len(hivas), 1)
        self.t.index.generacio = 2
        self.mod(fm_blokk(NORMAL), ertek=["Active-recall"])
        self.assertEqual(len(hivas), 2)


class EloErtekkeszletValodiIndex(unittest.TestCase):
    """CX-002: a valódi index `ertekkeszlet_hasznalat` olvasója: frontmatter- és szövegbeli címke, Status, saját kizárás."""

    def test_valodi_index(self):
        from tests.helpers import ir
        from tests.index_segedek import index_indit
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, v = alg_core(t.name)
        ir(v, "F01 - Fizika/A.md", "---\nTags:\n  - Active-recall\nStatus: Saját\n---\n# A\n")
        ir(v, "F01 - Fizika/B.md", "# B\nSzövegbeli #Szovegcimke és #Active-recall\n")
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        h = ix.ertekkeszlet_hasznalat()
        self.assertEqual(h["tags"]["active-recall"]["db"], 2)
        self.assertEqual(h["tags"]["szovegcimke"]["utak"], ["F01 - Fizika/B.md"])
        self.assertEqual(h["status"]["Saját"]["utak"], ["F01 - Fizika/A.md"])
        tu = tulajdonsagok.Tulajdonsagok(cfg, ix)
        fm = "---\nTags:\n  - Szovegcimke\nSource:\nStatus: Saját\nNN:\nCanvas:\n---\n"
        self.assertEqual(tu.elemez("F01 - Fizika/C.md", fm)["problemak"], [])           # más jegyzet használja
        self.assertEqual([(x["kod"], x["kulcs"]) for x in tu.elemez("F01 - Fizika/A.md", fm)["problemak"]],
                         [("ertekkeszlet", "Status")])                                   # a Saját csak az A-ban áll


class BajthuSzerkesztes(Alap):
    def test_nem_erintett_sorok_bajtra_azonosak(self):
        fm = fm_blokk(NORMAL)
        r = self.mod(fm, kulcs="Status", ertek="Review")
        self.assertTrue(r["ok"], r)
        regi, uj = fm.split("\n"), r["fm_uj"].split("\n")
        self.assertEqual([s for s in uj if not s.startswith("Status")], [s for s in regi if not s.startswith("Status")])
        self.assertIn("Status: Review", uj)

    def test_nincs_valtoztatas_ha_ugyanaz_az_ertek(self):
        fm = fm_blokk(NORMAL)
        r = self.mod(fm, kulcs="Status", ertek="Completed")
        self.assertTrue(r["ok"])
        self.assertEqual(r["fm_uj"], fm)
        self.assertFalse(r["valtozas"])

    def test_crlf_megmarad(self):
        fm = fm_blokk(NORMAL.replace("\n", "\r\n"))
        r = self.mod(fm, kulcs="Status", ertek="Review")
        self.assertTrue(r["ok"], r)
        self.assertNotRegex(r["fm_uj"], r"(?<!\r)\n")
        self.assertIn("Status: Review\r\n", r["fm_uj"])

    def test_kulcssorrend_es_megjegyzes_megmarad(self):
        fm = "---\nTags:\n  - AI\n# megjegyzés\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
        r = self.mod(fm, kulcs="Source", ertek=["[[Alma]]"])
        self.assertTrue(r["ok"], r)
        self.assertIn("# megjegyzés\nSource:\n  - \"[[Alma]]\"\nStatus:", r["fm_uj"])

    def test_lista_blokkformaban_idezett_wikilinkkel(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="NN", ertek=["[[A]]", "[[B]]"])
        self.assertIn('NN:\n  - "[[A]]"\n  - "[[B]]"\nCanvas:', r["fm_uj"])

    def test_ures_ertek_ures_kulcs(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="Status", ertek=None)
        self.assertIn("Status:\nNN:", r["fm_uj"])
        r = self.mod(fm_blokk(NORMAL), kulcs="Tags", ertek=[])
        self.assertTrue(r["fm_uj"].startswith("---\nTags:\nSource:"))

    def test_lista_folytatosorai_a_kulcshoz_tartoznak(self):
        """A lista-elemek folytatósorai a kulcshoz tartoznak: a törlés nem hagy árva sort (a séma-kulcs törlése
        megerősítést kér, ezért `megerosit`)."""
        r = self.mod(fm_blokk(NORMAL), muvelet="torol", kulcs="Source", megerosit=True)
        self.assertTrue(r["ok"], r)
        self.assertNotIn("09 - Matematika", r["fm_uj"])
        self.assertIn("Status: Completed", r["fm_uj"])

    def test_szokatlan_szoveg_idezojelet_kap_es_visszaolvashato(self):
        for s in ["true", "123", "2026:ma", "# nem megjegyzés", "- elem", "sor1\nsor2", " szóköz ", "null", "a: b"]:
            r = self.mod(fm_blokk(NORMAL), kulcs="Megjegyzes", ertek=s, tipus="text", megerosit=True)
            self.assertTrue(r["ok"], (s, r))
            tul, hiba = elemzo.frontmatter(re.match(r"---\n(.*?)\n---", r["fm_uj"], re.S).group(1))
            self.assertIsNone(hiba)
            self.assertEqual({t.kulcs: t.ertek for t in tul}["Megjegyzes"], s)

    def test_mas_olvasonak_szam_vagy_bool_szoveg_idezojeles(self):
        """T157 (C31): amit az Obsidian (YAML 1.2 core: `0x1F`, `0o7`) vagy egy YAML 1.1-es olvasó (`1_000`, `10:30`, `yes`)
        számnak vagy logikai értéknek venne, az idézőjelet kap; a hétköznapi szöveg sima marad."""
        for s in ["0x1F", "0o7", "0b101", "1_000", "1_000.5", "10:30", "1:20:30", "yes", "No", "ON", "off", "y", "N"]:
            self.assertEqual(tulajdonsagok._szoveg_sor(s), f'"{s}"', s)
            r = self.mod(fm_blokk(NORMAL), kulcs="Megjegyzes", ertek=s, tipus="text", megerosit=True)
            self.assertTrue(r["ok"], (s, r))
            self.assertIn(f'Megjegyzes: "{s}"', r["fm_uj"].split("\n"))
            tul, hiba = elemzo.frontmatter(re.match(r"---\n(.*?)\n---", r["fm_uj"], re.S).group(1))
            self.assertIsNone(hiba)
            self.assertEqual({t.kulcs: t.ertek for t in tul}["Megjegyzes"], s)
        for s in ["snake_case", "alma", "Yesterday", "nov", "0xford", "10:30 óra", "v1.2"]:
            self.assertEqual(tulajdonsagok._szoveg_sor(s), s, s)

    def test_tipusok(self):
        for tipus, ertek, sor in [("number", 3, "Pont: 3"), ("number", "2,5", "Pont: 2.5"),
                                  ("checkbox", True, "Pont: true"), ("date", "2026-10-02", "Pont: 2026-10-02"),
                                  ("datetime", "2026-10-02T09:30", "Pont: 2026-10-02T09:30"),
                                  ("text", "alma", "Pont: alma")]:
            r = self.mod(fm_blokk(NORMAL), kulcs="Pont", ertek=ertek, tipus=tipus, megerosit=True)
            self.assertTrue(r["ok"], (tipus, r))
            self.assertIn(sor, r["fm_uj"].split("\n"))

    def test_ervenytelen_ertek_nem_irhato(self):
        for tipus, ertek in [("date", "tegnap"), ("number", "sok"), ("checkbox", "talán"), ("datetime", "2026-13")]:
            r = self.mod(fm_blokk(NORMAL), kulcs="Pont", ertek=ertek, tipus=tipus, megerosit=True)
            self.assertFalse(r["ok"], (tipus, r))
            self.assertEqual(r["problemak"][0]["kod"], "ertek_tipus")
            self.assertFalse(r["megerositheto"])

    def test_ervenytelen_kulcsnev(self):
        for kulcs in ["", "a:b", "-x", "1x", "x#y", "a" * 90]:
            r = self.mod(fm_blokk(NORMAL), kulcs=kulcs, ertek="x", megerosit=True)
            self.assertFalse(r["ok"], kulcs)
            self.assertEqual(r["problemak"][0]["kod"], "kulcs_nev")

    def test_formai_hibas_frontmatter_nem_irhato(self):
        fm = "---\nTags: [a\nSource:\n---\n"
        r = self.mod(fm, kulcs="Status", ertek="Review", megerosit=True)
        self.assertFalse(r["ok"])
        self.assertEqual(r["problemak"][0]["kod"], "yaml_hiba")

    def test_duplikalt_kulcs_nem_irhato(self):
        fm = "---\nTags:\n  - AI\nTags:\n  - AI\n---\n"
        r = self.mod(fm, kulcs="Tags", ertek=["AI"], megerosit=True)
        self.assertFalse(r["ok"])
        self.assertEqual(r["problemak"][0]["kod"], "duplikalt_kulcs")

    def test_szokatlan_szerkezet_visszaolvasas_proba_elutasit(self):
        # a kulcs értéke folyamatos blokk-skalár üres sorral: a sorokra bontás ezt is egyben kezeli
        fm = "---\nTags:\n  - AI\nSource: |\n  egy\n\n  kettő\nStatus:\nNN:\nCanvas:\n---\n"
        r = self.mod(fm, kulcs="Status", ertek="Review")
        self.assertTrue(r["ok"], r)
        self.assertIn("Source: |\n  egy\n\n  kettő\nStatus: Review", r["fm_uj"])


class Beszuras(Alap):
    def test_uj_kulcs_a_sema_szerinti_helyre(self):
        fm = "---\nTags:\n  - AI\nNN:\nCanvas:\n---\n"
        r = self.mod(fm, kulcs="Source", ertek=["[[X]]"], megerosit=True)
        self.assertEqual([m.split(":")[0] for m in r["fm_uj"].split("\n") if re.match(r"\w", m)],
                         ["Tags", "Source", "NN", "Canvas"])

    def test_nem_sema_kulcs_a_vegere(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="cover", ertek="[[kep.png]]", megerosit=True)
        self.assertTrue(r["fm_uj"].rstrip("\n").endswith('cover: "[[kep.png]]"\n---'))

    def test_frontmatter_nelkuli_jegyzet_uj_blokkot_kap_ures_sorral(self):
        r = self.mod(None, kulcs="Tags", ertek=["AI"], megerosit=True)
        self.assertEqual(r["fm_uj"], "---\nTags:\n  - AI\n---\n\n")

    def test_torles_frontmatter_nelkul_nem_valtoztat(self):
        r = self.mod(None, muvelet="torol", kulcs="Tags")
        self.assertTrue(r["ok"])
        self.assertFalse(r["valtozas"])

    def test_kviz_osztaly_sajat_sorrend(self):
        fm = "---\nSource: \"[[A]]\"\nModell: x\nKeszult: 2026-10-01 10:00\n---\n"
        r = self.mod(fm, kulcs="Kviz", ertek="k1", ut="ATTCHMNTS - quizes/A — Kvíz.md", megerosit=True)
        self.assertEqual([m.split(":")[0] for m in r["fm_uj"].split("\n") if re.match(r"\w", m)],
                         ["Source", "Kviz", "Modell", "Keszult"])


class Sema(Alap):
    def kodok(self, r):
        return sorted({p["kod"] for p in r["problemak"]})

    def test_ismeretlen_kulcs_megerositest_ker_nem_ir_csendben(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="icon", ertek="📘")
        self.assertFalse(r["ok"])
        self.assertTrue(r["megerositheto"])
        self.assertIsNone(r["fm_uj"])
        self.assertIn("ismeretlen_kulcs", self.kodok(r))
        r2 = self.mod(fm_blokk(NORMAL), kulcs="icon", ertek="📘", megerosit=True)
        self.assertTrue(r2["ok"])
        self.assertIn("icon: 📘", r2["fm_uj"])

    def test_icon_es_cover_ugyanigy(self):
        for k in ("icon", "cover"):
            r = self.mod(fm_blokk(NORMAL), kulcs=k, ertek="x.png")
            self.assertTrue(r["megerositheto"] and not r["ok"], k)

    def test_version_kulcs_barhol_engedett(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="version", ertek="2.0")
        self.assertTrue(r["ok"], r)

    def test_tag_az_ertekkeszleten_kivul(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="Tags", ertek=["Mathematics", "Active-recall"])
        self.assertTrue(r["megerositheto"])
        self.assertEqual([(p["kod"], p["ertek"]) for p in r["problemak"]], [("ertekkeszlet", "Active-recall")])

    def test_status_ertekkeszleten_kivul(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="Status", ertek="Kész")
        self.assertTrue(r["megerositheto"])
        self.assertEqual(r["problemak"][0]["kulcs"], "Status")

    def test_status_gepi_toltese_tilos_megerositessel_sem(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="Status", ertek="Review", forras="gep", megerosit=True)
        self.assertFalse(r["ok"])
        self.assertFalse(r["megerositheto"])
        self.assertEqual(r["problemak"][0]["kod"], "status_gep")
        # a gép más mezőt tölthet
        self.assertTrue(self.mod(fm_blokk(NORMAL), kulcs="Tags", ertek=["AI"], forras="gep")["ok"])

    def test_felhasznalo_a_statust_tolti(self):
        self.assertTrue(self.mod(fm_blokk(NORMAL), kulcs="Status", ertek="In progress")["ok"])

    def test_kisbetus_kulcs(self):
        r = self.mod(fm_blokk(NORMAL), kulcs="tags", ertek=["AI"])
        self.assertIn("kisbetus_kulcs", self.kodok(r))

    def test_a_mar_meglevo_sertes_nem_teszi_megerosites_koteless(self):
        fm = "---\nTags:\n  - Active-recall\nicon: 📘\n---\n"
        r = self.mod(fm, kulcs="Source", ertek=["[[X]]"])
        self.assertTrue(r["ok"], r)           # a mezosorrend és a címke és az icon már előtte is sértett

    def test_kanonikus_kulcs_torlese_uj_mezosorrend_sertes(self):
        r = self.mod(fm_blokk(NORMAL), muvelet="torol", kulcs="Canvas")
        self.assertTrue(r["megerositheto"])
        self.assertEqual(self.kodok(r), ["mezosorrend"])

    def test_sema_nelkuli_fajl_nincs_ellenorzes(self):
        r = self.mod("---\nfoo: 1\n---\n", kulcs="bar", ertek="x", ut="AI01 - Workflow System/CLAUDE.md")
        self.assertTrue(r["ok"], r)

    def test_konyv_jegyzet_osztaly(self):
        fm = "---\nSzerző: x\nMűfaj: y\nRate: 5\nStatus: Olvasva\n---\n"
        r = self.mod(fm, kulcs="Rate", ertek=4, ut="X03 - Books/The Silo.md")
        self.assertTrue(r["ok"], r)           # a könyv-osztálynál a Status értékkészlet nem érvényes

    def test_elemez_a_nyitott_szovegrol(self):
        e = self.t.elemez("F01/J.md", fm_blokk(NORMAL))
        self.assertTrue(e["van"])
        self.assertEqual([t["kulcs"] for t in e["tulajdonsagok"]], ["Tags", "Source", "Status", "NN", "Canvas"])
        self.assertEqual(e["problemak"], [])
        e = self.t.elemez("F01/J.md", "---\nTags: [a\n---\n")
        self.assertEqual(e["problemak"][0]["kod"], "yaml_hiba")
        e = self.t.elemez("F01/J.md", None)
        self.assertFalse(e["van"])

    def test_nem_frontmatter_blokk_400(self):
        from core.utvonalak import HttpError
        with self.assertRaises(HttpError):
            self.t.elemez("a.md", "szöveg")


class AuditKapuk(Alap):
    """C29.8a (2. audit): a nem szöveges Status, a Status-tilalom változatai, a duplikált kulcs, az üres és BOM-os
    frontmatter, a naptárilag érvénytelen dátum, az új hiányzó kulcs és a H1-szabály. Mind a javítás ELŐTT bukott."""

    def kodok(self, r):
        return sorted({p["kod"] for p in r["problemak"]})

    # ---- T042
    def test_nem_szoveges_status_ertekkeszleten_kivul(self):
        for kw in (dict(ertek=["Review"]), dict(tipus="checkbox", ertek=True), dict(tipus="number", ertek=5)):
            r = self.mod(fm_blokk(NORMAL), kulcs="Status", **kw)
            self.assertFalse(r["ok"], kw)                                       # ma: ok True, megerősítés nélkül íródik
            self.assertTrue(r["megerositheto"], kw)
            self.assertIn(("ertekkeszlet", "Status"), [(p["kod"], p["kulcs"]) for p in r["problemak"]])
        for fm in ("---\nStatus: true\n---\n", "---\nStatus: 5\n---\n", "---\nStatus: [a, b]\n---\n",
                   "---\nStatus: {a: 1}\n---\n"):
            e = self.t.elemez("F01/J.md", fm)
            self.assertIn(("ertekkeszlet", "Status"), [(p["kod"], p["kulcs"]) for p in e["problemak"]], fm)
        # a szöveges, értékkészletbeli és az üres Status rendben van
        for fm in (NORMAL, "---\nStatus:\n---\n", "---\nStatus: Review\n---\n"):
            e = self.t.elemez("F01/J.md", fm_blokk(fm) if fm is NORMAL else fm)
            self.assertNotIn("ertekkeszlet", [p["kod"] for p in e["problemak"]], fm)

    # ---- T127
    def test_status_tilalom_kis_nagybetutol_fuggetlen_es_torlesre_is(self):
        for muvelet, kulcs, ertek in (("beallit", "STATUS", "Review"), ("beallit", "status", "Review"),
                                      ("torol", "Status", None), ("torol", "status", None)):
            r = self.mod(fm_blokk(NORMAL), muvelet=muvelet, kulcs=kulcs, ertek=ertek, forras="gep", megerosit=True)
            self.assertFalse(r["ok"], (muvelet, kulcs))                         # ma: a kis/nagybetűs és a törlés átmegy
            self.assertEqual(r["problemak"][0]["kod"], "status_gep", (muvelet, kulcs))
        r = self.mod("---\nstatus: Completed\n---\n", muvelet="torol", kulcs="status", forras="gep", megerosit=True)
        self.assertEqual(r["problemak"][0]["kod"], "status_gep")
        self.assertTrue(self.mod(fm_blokk(NORMAL), muvelet="torol", kulcs="Status", megerosit=True)["ok"])    # a felhasználó törölheti

    # ---- T129
    def test_idezett_escape_es_komplex_kulcs_nem_hoz_letre_masodik_kulcsot(self):
        for fm in ('---\nTags:\n  - AI\n"Sta\\x74us": Review\n---\n', "---\n? Status\n: Review\nTags:\n  - AI\n---\n"):
            r = self.mod(fm, kulcs="Status", ertek="Completed", megerosit=True)
            self.assertFalse(r["ok"], fm)                                         # ma: ok True, két Status kulcs
            self.assertIn(r["problemak"][0]["kod"], ("belso_hiba", "duplikalt_kulcs"))

    def test_elemez_a_yaml_szintu_duplikalt_kulcsot_jelzi(self):
        fm = '---\nTags:\n  - AI\n"Tag\\x73":\n  - AI\n---\n'
        e = self.t.elemez("F01/J.md", fm)
        self.assertIn(("duplikalt_kulcs", "Tags"), [(p["kod"], p["kulcs"]) for p in e["problemak"]])

    # ---- T130
    def test_ures_es_bom_os_frontmatter(self):
        r = self.mod(fm_blokk("---\n---\n# C\n"), kulcs="Status", ertek="Review", megerosit=True)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["fm_uj"], "---\nStatus: Review\n---\n")               # egy blokk, nem kettő
        fm = fm_blokk("\ufeff---\nTags:\n  - AI\n---\n# C\n")
        r = self.mod(fm, kulcs="Status", ertek="Review", megerosit=True)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["fm_uj"].startswith("\ufeff---\n"))                     # a BOM megmarad
        self.assertIn("Status: Review", r["fm_uj"])
        self.assertEqual([t["kulcs"] for t in self.t.elemez("F01/J.md", fm)["tulajdonsagok"]], ["Tags"])

    # ---- T131
    def test_naptarilag_ervenytelen_datum_nem_irhato(self):
        for tipus, ertek in (("date", "2026-13-45"), ("date", "2026-02-30"), ("date", "0000-01-01"),
                             ("datetime", "2026-02-30T10:00"), ("datetime", "2026-10-02T25:61"), ("datetime", "2026-13-01")):
            r = self.mod(fm_blokk(NORMAL), kulcs="Pont", ertek=ertek, tipus=tipus, megerosit=True)
            self.assertFalse(r["ok"], (tipus, ertek))                            # ma: ok True, sima alakban íródik
            self.assertEqual(r["problemak"][0]["kod"], "ertek_tipus")
            self.assertFalse(r["megerositheto"])
        for tipus, ertek in (("date", "2024-02-29"), ("datetime", "2024-02-29T23:59"), ("datetime", "2026-10-02")):
            self.assertTrue(self.mod(fm_blokk(NORMAL), kulcs="Pont", ertek=ertek, tipus=tipus, megerosit=True)["ok"], ertek)
        # szövegként a dátumszerű érvénytelen érték idézőjelet kap (sima alakban dátumnak látszana)
        r = self.mod(fm_blokk(NORMAL), kulcs="Megj", ertek="2026-02-30", tipus="text", megerosit=True)
        self.assertIn('Megj: "2026-02-30"', r["fm_uj"].split("\n"))

    # ---- T133
    def test_hianyos_jegyzetben_a_kanonikus_kulcs_torlese_megerositest_ker(self):
        fm = "---\nTags:\n  - AI\nSource:\nNN:\nCanvas:\n---\n"                    # nincs Status
        for kulcs in ("Tags", "Source", "NN", "Canvas"):
            r = self.mod(fm, muvelet="torol", kulcs=kulcs)
            self.assertTrue(r["megerositheto"], kulcs)                           # ma: ok True, megerősítés nélkül
            self.assertEqual(self.kodok(r), ["mezosorrend"])
        r = self.mod(fm, kulcs="Status", ertek="In progress")                    # a hiányzó kulcs pótlása javít: nem kér megerősítést
        self.assertTrue(r["ok"], r)

    # ---- T044 (a H1-szabály, a legacy kalibrációból)
    def test_h1_szabaly(self):
        import unicodedata
        h1 = lambda ut, sz: [p["kod"] for p in self.t.h1_problemak(ut, sz)]    # noqa: E731
        self.assertEqual(h1("T01/Jegyzet.md", "# Jegyzet\n"), [])
        self.assertEqual(h1("T01/07 - Jegyzet.md", "# Jegyzet\n"), [])           # a `NN - ` sorszám-előtag levágva
        self.assertEqual(h1("T01/07F - Jegyzet.md", "# Jegyzet\n"), [])
        self.assertEqual(h1("T01/Jegyzet.md", "# Más\n"), ["h1"])
        self.assertEqual(h1("T01/Jegyzet.md", "szöveg, nincs H1\n"), ["h1_hiany"])
        self.assertEqual(h1("T01/Jegyzet.md", "---\nTags:\n---\n```\n# Más\n```\n# Jegyzet\n"), [])    # kódban nem fejezet
        self.assertEqual(h1("T01/Öröklés.md", unicodedata.normalize("NFD", "# Öröklés\n")), [])        # NFD H1 == NFC fájlnév
        self.assertEqual(h1("T01/Jegyzet.md", "Jegyzet\n=======\n"), [])                 # setext H1
        self.assertEqual(h1("T01/Jegyzet.md", "# Elsőként\n\n# Jegyzet\n"), ["h1"])    # az ELSŐ H1 számít
        for ut in ("AI02 - Log/2026-10-03.md", "X01 - Napló & To-Do/2026-10/Napló/a.md", "AI01 - Workflow System/2.0/A.md",
                   "Prjct01 - Obsidian/B.md", "AI03 - Memória/C.md", "_Template/Sablon.md"):
            self.assertEqual(h1(ut, "# Teljesen más\n"), [], ut)                       # kivétel-útvonalak
        self.assertEqual(h1("_Template/Sablon.md", "---\nTags:\n---\n"), [])           # sablon-váz: H1 nélkül is jó
        self.assertEqual(h1("M03 - Matek/Megoldások/Feladatsor - 18.md", "# Másról szól\n"), [])    # megoldás-sorszámos
        self.assertEqual(h1("M03 - Matek/Megoldások/Szorzattá Alakítás - Megoldások.md", "# Más\n"), ["h1"])
        self.assertEqual(h1("M03 - Matek/Téma.md", '---\nSource:\n  - "[[emelt matematika témakörök.pdf#page=3]]"\n---\n'
                                                     "# Hosszú követelmény-szöveg\n"), [])           # érettségi-témakör
        self.assertEqual(h1("M03 - Matek/Téma.md", "# Hosszú követelmény-szöveg\n"), ["h1"])
        kv = "ATTCHMNTS - quizes/Alma — Kvíz 2026-10-03 1015"
        self.assertEqual(h1(kv + ".md", f"# {kv.split('/')[1]}\n"), [])                      # kvíz: minta és fájlnév-egyezés
        self.assertEqual(h1(kv + " (2).md", f"# {kv.split('/')[1]} (2)\n"), [])
        self.assertEqual(h1(kv + ".md", "# Alma\n"), ["h1"])                                 # nem a minta
        self.assertEqual(h1(kv + ".md", "# Béla — Kvíz 2026-10-03 1015\n"), ["h1"])         # minta igen, a fájlnév nem
        self.assertEqual(h1("X03 - Books/The Silo.md", "# Part 1: Holston\n"), [])           # könyv: H1-ellenőrzés kikapcsolva
        self.assertEqual(h1("AI01 - Workflow System/CLAUDE.md", "nincs H1\n"), [])            # séma nélküli fájl
        self.assertEqual(h1("T01/kep.canvas", "# bármi\n"), [])                              # nem jegyzet


class SablonOsszefesules(Alap):
    """C32b (26(d) módosítása): a sablon frontmatterének összefésülése a jegyzetével, a `modosit` szabályaival."""
    UT = "F01 - Fizika/Jegyzet.md"

    def of(self, fm, sablon):
        return self.t.osszefesul(self.UT, fm, sablon)

    def test_az_uj_kulcs_hozzaadodik_a_meglevo_nem_ir_felul(self):
        fm = "---\nTags:\n  - Mathematics\nStatus: Completed\n---\n"
        sab = "---\nTags:\n  - Mathematics\nSource: []\nStatus: Review\nNN:\n---\n"
        r = self.of(fm, sab)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["megmaradt"], ["Status"])             # a meglévő, nem üres érték marad
        self.assertIn("Status: Completed", r["fm_uj"])
        self.assertNotIn("Review", r["fm_uj"])
        self.assertIn("Source:", r["fm_uj"])                      # az üres, de hiányzó kulcs is bekerül
        self.assertIn("NN:", r["fm_uj"])
        self.assertEqual(r["hozzaadva"], ["Source", "NN"])
        self.assertEqual(r["fuggo"], [])
        self.assertTrue(r["valtozas"])

    def test_a_lista_ertek_egyesul(self):
        fm = "---\nTags:\n  - Mathematics\n---\n"
        r = self.of(fm, "---\nTags:\n  - Mathematics\n  - Physics\n---\n")
        self.assertEqual(r["egyesitve"], ["Tags"])
        self.assertEqual(elemzo.frontmatter(r["fm_uj"].split("---\n")[1])[0][0].ertek, ["Mathematics", "Physics"])

    def test_a_jegyzet_ures_erteke_kitoltodik(self):
        r = self.of("---\nTags:\n  - Physics\nStatus:\n---\n", "---\nStatus: Review\n---\n")
        self.assertEqual(r["kitoltve"], ["Status"])
        self.assertIn("Status: Review", r["fm_uj"])

    def test_a_seme_sertes_nem_irodik_csendben_hanem_fuggo(self):
        fm = "---\nTags:\n  - Physics\n---\n"
        r = self.of(fm, "---\nTags:\n  - Physics\nicon: star\n---\n")
        self.assertEqual([f["kulcs"] for f in r["fuggo"]], ["icon"])
        self.assertEqual(r["fuggo"][0]["ertek"], "star")
        self.assertNotIn("icon", r["fm_uj"])
        self.assertFalse(r["valtozas"])
        # a megerősítés a meglévő `modosit` útján megy
        m = self.t.modosit(self.UT, r["fm_uj"], "beallit", "icon", "star", megerosit=True)
        self.assertTrue(m["ok"])
        self.assertIn("icon: star", m["fm_uj"])

    def test_ertekkeszleten_kivuli_cimke_szinten_fuggo(self):
        r = self.of("---\nTags:\n  - Physics\n---\n", "---\nTags:\n  - Physics\n  - Ismeretlen\n---\n")
        self.assertEqual([f["kulcs"] for f in r["fuggo"]], ["Tags"])
        self.assertEqual(r["egyesitve"], [])

    def test_nem_szerkesztheto_ertek_kimarad(self):
        r = self.of("---\nTags:\n  - Physics\n---\n", "---\nTags:\n  - Physics\nSource:\n  a: 1\n---\n")
        self.assertEqual([k["kulcs"] for k in r["kihagyva"]], ["Source"])

    def test_nincs_sablon_frontmatter_vagy_hibas(self):
        fm = "---\nTags:\n  - Physics\n---\n"
        self.assertEqual(self.of(fm, None)["fm_uj"], fm)
        self.assertFalse(self.of(fm, None)["valtozas"])
        r = self.of(fm, "---\na: [\n---\n")
        self.assertFalse(r["valtozas"])
        self.assertTrue(r["kihagyva"])

    def test_a_bajthu_csere_megmarad_crlf(self):
        fm = "---\r\nTags:\r\n  - Physics\r\n---\r\n"
        r = self.of(fm, "---\nTags:\n  - Physics\nSource:\n---\n")
        self.assertEqual(r["fm_uj"], "---\r\nTags:\r\n  - Physics\r\nSource:\r\n---\r\n")


class UjJegyzetEllenorzes(Alap):
    """Javító 7 (64(b), 22(b)): az új jegyzet leendő frontmatterje ugyanazzal az `elemez`-zel és szint-beosztással."""

    UT = "F01 - Fizika/Új.md"

    def ell(self, szoveg, ut=None):
        return self.t.uj_jegyzet_ellenorzes(ut or self.UT, szoveg)

    def test_frontmatter_nelkul_nincs_ellenorzes(self):
        self.assertEqual(self.ell("# Cím\n"), {"van": False, "hibak": [], "sertesek": []})
        self.assertEqual(self.ell(""), {"van": False, "hibak": [], "sertesek": []})

    def test_tiszta_frontmatter(self):
        r = self.ell(NORMAL)
        self.assertEqual((r["van"], r["hibak"], r["sertesek"]), (True, [], []))

    def test_ismeretlen_kulcs_az_icon_es_a_cover_is_sertes(self):
        for kulcs in ("icon", "cover", "Egyeb"):
            szoveg = NORMAL.replace("Status: Completed", f"{kulcs}: x\nStatus: Completed")
            r = self.ell(szoveg)
            self.assertEqual(r["hibak"], [], kulcs)
            self.assertIn(("ismeretlen_kulcs", kulcs), [(p["kod"], p["kulcs"]) for p in r["sertesek"]], kulcs)

    def test_ertekkeszleten_kivuli_cimke_es_status(self):
        r = self.ell(NORMAL.replace("Mathematics", "NincsIlyenCimke").replace("Completed", "Hamar"))
        self.assertEqual(r["hibak"], [])
        self.assertEqual(sorted((p["kod"], p["kulcs"]) for p in r["sertesek"]), [("ertekkeszlet", "Status"), ("ertekkeszlet", "Tags")])

    def test_kulcssorrend_sertes(self):
        r = self.ell("---\nStatus: Completed\nTags:\n  - Mathematics\n---\n")
        self.assertEqual(r["hibak"], [])
        self.assertTrue([p for p in r["sertesek"] if p["kod"] == "mezosorrend"])

    def test_formai_hiba_hiba_szintu(self):
        r = self.ell("---\nTags: [Mathematics\nStatus: : :\n---\n")
        self.assertEqual([p["kod"] for p in r["hibak"]], ["yaml_hiba"])

    def test_ismetlodo_kulcs_hiba_szintu(self):
        r = self.ell(NORMAL.replace("Status: Completed", "Status: Completed\nStatus: Review"))
        self.assertIn("duplikalt_kulcs", [p["kod"] for p in r["hibak"]])

    def test_tipushoz_nem_illo_ertek_hiba_szintu(self):
        t = tulajdonsagok.Tulajdonsagok(self.t.cfg, SimpleNamespace(tipusok={"Hatarido": "date"}))
        r = t.uj_jegyzet_ellenorzes(self.UT, NORMAL.replace("Status: Completed", "Hatarido: holnap\nStatus: Completed"))
        self.assertEqual([(p["kod"], p["kulcs"]) for p in r["hibak"]], [("ertek_tipus", "Hatarido")])

    def test_kivetel_osztaly_sajat_sorrendje(self):
        # a séma osztályonként más (itt a kvíz-osztály), ugyanaz a kód mint a panelé
        o = self.t.sema.osztalyok[0]
        ut = o["utvonal_elotag"][0] + "Új.md"
        r = self.ell("---\n" + "\n".join(f"{k}:" for k in o["mezosorrend"]) + "\n---\n", ut)
        self.assertEqual(r["sertesek"], [])


class Konfig(Alap):
    def test_sema_a_configbol(self):
        self.assertEqual(self.t.sema.mezosorrend, ["Tags", "Source", "Status", "NN", "Canvas"])
        self.assertEqual(self.t.sema.status, ["Completed", "In progress", "Review"])
        self.assertTrue(self.t.sema.status_gazdai)
        self.assertEqual(self.t.sema.osztaly("ATTCHMNTS - quizes/x.md")["nev"], "kviz")
        self.assertEqual(self.t.sema.osztaly("F/x.md")["nev"], "normal")


class Javaslatok(unittest.TestCase):
    """A gépelés közbeni javaslatok (kulcs- és érték-javaslat): tiszta olvasók az index fölött, a séma értékkészletével."""

    def setUp(self):
        self._tmp = tmpdir()
        self.addCleanup(self._tmp.cleanup)
        cfg, _, _ = alg_core(self._tmp.name)
        self.index = SimpleNamespace(
            tipusok={"Tags": "tags", "Szerző": "text"},
            tulajdonsag_kulcsok=lambda: [{"kulcs": "Tags", "db": 9}, {"kulcs": "Szerző", "db": 3}, {"kulcs": "Status", "db": 7},
                                         {"kulcs": "aliases", "db": 1}],
            tulajdonsag_ertekek=lambda kulcs: {"Status": [{"ertek": "Completed", "db": 5}, {"ertek": "Kész", "db": 2}],
                                               "Szerző": [{"ertek": "Arany János", "db": 2}, {"ertek": "Petőfi", "db": 1}]}.get(kulcs, []),
            cimkek=lambda: {"cimkek": [{"cimke": "Physics", "kis": "physics", "db": 4, "ossz": 4},
                                       {"cimke": "Fizika", "kis": "fizika", "db": 0, "ossz": 2},
                                       {"cimke": "Fizika/Optika", "kis": "fizika/optika", "db": 2, "ossz": 2},
                                       {"cimke": "Mathematics", "kis": "mathematics", "db": 1, "ossz": 1}]},
        )
        self.t = tulajdonsagok.Tulajdonsagok(cfg, self.index)

    def test_kulcsok_a_sema_sorrendjeben_utana_a_hasznaltak(self):
        r = self.t.kulcs_javaslatok("F01 - Fizika/J.md")
        nevek = [k["kulcs"] for k in r["kulcsok"]]
        self.assertEqual(nevek[:6], ["Tags", "Source", "Status", "NN", "Canvas", "version"])
        self.assertEqual(nevek[6:], ["Szerző", "aliases"])
        k = {x["kulcs"]: x for x in r["kulcsok"]}
        self.assertEqual((k["Tags"]["sema"], k["Tags"]["db"], k["Tags"]["tipus"]), (True, 9, "tags"))
        self.assertEqual((k["Szerző"]["sema"], k["Szerző"]["tipus"]), (False, "text"))
        self.assertTrue(r["index_kesz"])

    def test_kulcsok_kivetelosztalyban_es_sema_nelkul(self):
        nevek = [k["kulcs"] for k in self.t.kulcs_javaslatok("ATTCHMNTS - quizes/K.md")["kulcsok"] if k["sema"]]
        self.assertEqual(nevek[:4], ["Source", "Kviz", "Modell", "Keszult"])
        r = self.t.kulcs_javaslatok("AI01 - Workflow System/CLAUDE.md")
        self.assertFalse(any(k["sema"] for k in r["kulcsok"]))

    def test_cimkek_az_ertekkeszlet_elol_a_tobbi_jelolve(self):
        r = self.t.ertek_javaslatok("F01 - Fizika/J.md", "Tags")
        self.assertTrue(r["ertekkeszlet"])
        e = r["ertekek"]
        # az értékkészlet minden eleme benne van (a még nem használt is), a használtak elöl
        self.assertEqual([x["ertek"] for x in e[:2]], ["Physics", "Mathematics"])
        self.assertIn("Napló", [x["ertek"] for x in e if x["sema"]])
        self.assertEqual([x for x in e if x["ertek"] == "Napló"][0]["db"], 0)
        # a nem értékkészletbeli használt címke a végén, jelölve; a csak gyerekként létező szülő (db 0) nem javaslat
        self.assertEqual([(x["ertek"], x["sema"], x["db"]) for x in e if not x["sema"]], [("Fizika/Optika", False, 2)])

    def test_status_ertekkeszlet_es_a_hasznalt_eltero_ertek(self):
        e = self.t.ertek_javaslatok("F01 - Fizika/J.md", "Status")["ertekek"]
        self.assertEqual([(x["ertek"], x["sema"]) for x in e],
                         [("Completed", True), ("In progress", True), ("Review", True), ("Kész", False)])

    def test_ertekkeszlet_nelkuli_osztaly_es_kulcs(self):
        r = self.t.ertek_javaslatok("ATTCHMNTS - quizes/K.md", "Status")
        self.assertFalse(r["ertekkeszlet"])
        self.assertEqual([(x["ertek"], x["sema"]) for x in r["ertekek"]], [("Completed", None), ("Kész", None)])
        r = self.t.ertek_javaslatok("F01 - Fizika/J.md", "Szerző")
        self.assertEqual([(x["ertek"], x["db"], x["sema"]) for x in r["ertekek"]], [("Arany János", 2, None), ("Petőfi", 1, None)])

    def test_hianyzo_kulcs_400(self):
        for rossz in (None, "", "  ", 5):
            with self.assertRaises(HttpError):
                self.t.ertek_javaslatok("A.md", rossz)

    def test_nem_kesz_index_mellett_csak_a_sema(self):
        def nem_kesz(*_):
            raise NemKesz("az index még nem épült fel")
        t = tulajdonsagok.Tulajdonsagok(self.t.cfg, SimpleNamespace(tipusok={}, tulajdonsag_kulcsok=nem_kesz,
                                                                    tulajdonsag_ertekek=nem_kesz, cimkek=nem_kesz))
        r = t.ertek_javaslatok("F01 - Fizika/J.md", "Status")
        self.assertEqual(([x["ertek"] for x in r["ertekek"]], r["index_kesz"]), (["Completed", "In progress", "Review"], False))
        r = t.kulcs_javaslatok("F01 - Fizika/J.md")
        self.assertEqual((len(r["kulcsok"]), r["index_kesz"]), (6, False))


if __name__ == "__main__":
    unittest.main()
