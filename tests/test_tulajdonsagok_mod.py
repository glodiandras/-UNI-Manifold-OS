"""A séma módjai (`[sema] mod = ki | tanacsado | szigoru`), a `null` értékkészletek, a nyitott kulcskészlet és a séma feloldási lánca
(`core/kiserok.sema_fajl`: a `[sema] vault` fájl → a megnevezett preset sémája → a szállított `[sema] alap`), F3-DESIGN §8.
Álgyökéren, semleges vaulttal; a szigorú mód viselkedése a v2-é (a `tests/test_tulajdonsagok.py` a v2-sémával fedi részletesen)."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import kiserok
from core.tulajdonsagok import HIBA, SERTES, TANACS, Sema, Tulajdonsagok
from tests.helpers import tmpdir
from tests.vaultgyar import alg_semleges

SEMA = {
    "mezosorrend": ["Tags", "Source"],
    "extra_kulcsok": ["version"],
    "tags_ertekkeszlet": ["Alpha", "Beta"],
    "status_ertekkeszlet": ["Open", "Done"],
    "status_gazdai": True,
    "kivetel_osztalyok": [{"nev": "kartya", "kisero": "kartya", "mezosorrend": ["Source", "Modell"], "tartalmi": False, "h1": False}],
    "h1": {"szabaly": "fajlnev", "sorszam_elotag": "^\\d+[A-Z]? - "},
    "sema_nelkuli_nevek": [],
}
UT = "Projects/a.md"
# minden fajta sértés egyben: ismeretlen kulcs (`icon`), kulcssorrend (Source előbb), értékkészleten kívüli címke és Status
SERTO_FM = "---\nSource:\nTags:\n  - Gamma\nStatus: Maybe\nicon: book\n---\n"
JO_FM = "---\nTags:\n  - Alpha\nSource:\n---\n"
DUPLA_FM = "---\nTags:\n  - Alpha\nTags:\n  - Beta\nSource:\n---\n"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)

    def epit(self, mod: str, sema: dict | None = SEMA) -> Tulajdonsagok:
        """Tulajdonságok az adott móddal; a séma egy teszt-fájlból (`[sema] vault`), `sema=None`: a szállított alap."""
        self.cfg.data["sema"]["mod"] = mod
        if sema is not None:
            f = Path(self._t.name) / "teszt-sema.json"
            f.write_text(json.dumps(sema), encoding="utf-8")
            self.cfg.data["sema"]["vault"] = str(f)
        return Tulajdonsagok(self.cfg, SimpleNamespace(tipusok={}))

    def kodok(self, lista):
        return sorted({p["kod"] for p in lista})


class AlapModTest(Alap):
    def test_a_szallitott_alap_ki_mod_semleges_semaval(self):
        self.assertEqual(self.cfg.section("sema")["mod"], "ki")
        t = Tulajdonsagok(self.cfg, SimpleNamespace(tipusok={}))
        self.assertEqual(t.sema.mod, "ki")
        self.assertEqual(kiserok.sema_fajl(self.cfg), self.root / "config" / "schema-default.json")
        self.assertEqual((t.sema.mezosorrend, t.sema.tags, t.sema.status, t.sema.status_gazdai), ([], None, None, True))
        e = t.elemez(UT, SERTO_FM)
        self.assertEqual((e["problemak"], e["tanacsok"]), ([], []))

    def test_mod_nelkuli_sema_a_v2_szigorusaga(self):
        self.assertEqual(Sema(SEMA).mod, "szigoru")                        # cfg nélkül: a v2 viselkedése
        self.assertEqual(Sema(SEMA, mod="tanacsado").mod, "tanacsado")
        self.assertEqual(Sema(SEMA, mod="ismeretlen").mod, "ki")           # elírt mód: nincs ellenőrzés (nem szigorúbb)

    def test_a_cfg_modja(self):
        for mod in ("ki", "tanacsado", "szigoru"):
            self.assertEqual(self.epit(mod).sema.mod, mod)
        self.cfg.data["sema"]["mod"] = "elirt"
        self.assertEqual(Sema.betolt(self.cfg).mod, "ki")


class SzigoruTest(Alap):
    def test_a_v2_viselkedes(self):
        t = self.epit("szigoru")
        e = t.elemez(UT, SERTO_FM)
        self.assertEqual(self.kodok(e["problemak"]), ["ertekkeszlet", "ismeretlen_kulcs", "mezosorrend"])
        self.assertTrue(all(p["szint"] == SERTES for p in e["problemak"]))
        self.assertEqual(e["tanacsok"], [])
        self.assertEqual(t.elemez(UT, JO_FM)["problemak"], [])

    def test_az_editor_megerosites_es_a_gep_tilalma(self):
        t = self.epit("szigoru")
        r = t.modosit(UT, JO_FM, "beallit", "icon", "book")
        self.assertEqual((r["ok"], r["megerositheto"]), (False, True))
        self.assertTrue(t.modosit(UT, JO_FM, "beallit", "icon", "book", megerosit=True)["ok"])
        self.assertEqual(t.uj_jegyzet_ellenorzes(UT, SERTO_FM + "\n# a\n")["sertesek"] != [], True)
        g = t.modosit(UT, JO_FM, "beallit", "Status", "Done", forras="gep")
        self.assertFalse(g["ok"])
        self.assertEqual(g["problemak"][0]["kod"], "status_gep")             # a gazdai Status

    def test_h1_szabaly(self):
        t = self.epit("szigoru")
        self.assertEqual([p["kod"] for p in t.h1_problemak(UT, "# Valami más\n")], ["h1"])
        self.assertEqual(t.h1_problemak(UT, "# a\n"), [])


class KiTest(Alap):
    def test_nincs_semaellenorzes(self):
        t = self.epit("ki")
        e = t.elemez(UT, SERTO_FM)
        self.assertEqual((e["problemak"], e["tanacsok"]), ([], []))
        self.assertEqual(t.uj_jegyzet_ellenorzes(UT, SERTO_FM + "\n# a\n"), {"van": True, "hibak": [], "sertesek": []})

    def test_a_formai_hiba_maradt(self):
        t = self.epit("ki")
        self.assertEqual(self.kodok(t.elemez(UT, DUPLA_FM)["problemak"]), ["duplikalt_kulcs"])

    def test_az_editor_szabad_a_gep_a_statust_a_ki_modban_sem_irhatja(self):
        """A `ki` mód a séma érték- és kulcsellenőrzését kapcsolja ki; a Status gazdai védelme (T127) a módtól független."""
        t = self.epit("ki")
        self.assertTrue(t.modosit(UT, JO_FM, "beallit", "icon", "book")["ok"])        # nincs megerősítés
        g = t.modosit(UT, JO_FM, "beallit", "Status", "Done", forras="gep")
        self.assertEqual((g["ok"], g["problemak"][0]["kod"]), (False, "status_gep"))
        self.assertTrue(t.modosit(UT, JO_FM, "beallit", "Status", "Done")["ok"])      # a felhasználó (az editor) írhatja
        self.assertTrue(t.sema.status_gazdai)
        self.assertEqual(t.h1_problemak(UT, "# Valami más\n"), [])

    def test_a_vault_sema_nem_kapcsolhatja_ki_a_meglevo_statusz_vedelmet(self):
        """A `schema.json` megbízhatatlan (a vault utazik): `status_gazdai: false` mellett is védett az a jegyzet, amelynek már van
        Status kulcsa (írás, törlés, kis-nagybetű-variáns); az új jegyzetet a séma szava dönti."""
        t = self.epit("ki", {**SEMA, "status_gazdai": False})
        self.assertFalse(t.sema.status_gazdai)
        van = "---\nTags:\n  - Alpha\nStatus: Open\n---\n"
        for muvelet, ertek in (("beallit", "Done"), ("torol", None)):
            g = t.modosit(UT, van, muvelet, "status", ertek, forras="gep")
            self.assertEqual((g["ok"], g["problemak"][0]["kod"]), (False, "status_gep"), muvelet)
        self.assertTrue(t.modosit(UT, van, "beallit", "Status", "Done")["ok"])         # a felhasználó szabad
        self.assertTrue(t.modosit(UT, JO_FM, "beallit", "Status", "Done", forras="gep")["ok"])   # nincs Status kulcs: a séma szava

    def test_a_kisero_osztaly_beszurasi_sorrendje_megmarad(self):
        t = self.epit("ki")
        self.assertEqual(t.sema.osztaly("Manifold - Cards/x.md")["nev"], "kartya")
        r = t.modosit("Manifold - Cards/x.md", "---\nModell: m\n---\n", "beallit", "Source", "[[A]]")
        self.assertTrue(r["ok"])
        self.assertLess(r["fm_uj"].index("Source"), r["fm_uj"].index("Modell"))      # a kísérő-osztály kulcssorrendje él


class TanacsadoTest(Alap):
    def test_a_sertesek_tanacsok(self):
        t = self.epit("tanacsado")
        e = t.elemez(UT, SERTO_FM)
        self.assertEqual(e["problemak"], [])                                          # semmi nem tilt, semmi nem kér megerősítést
        self.assertEqual(self.kodok(e["tanacsok"]), ["ertekkeszlet", "ismeretlen_kulcs", "mezosorrend"])
        self.assertTrue(all(p["szint"] == TANACS for p in e["tanacsok"]))
        self.assertEqual(t.elemez(UT, JO_FM)["tanacsok"], [])

    def test_nem_tilt_es_nem_kerdez(self):
        t = self.epit("tanacsado")
        r = t.modosit(UT, JO_FM, "beallit", "icon", "book")
        self.assertEqual((r["ok"], r["problemak"]), (True, []))
        self.assertEqual(t.uj_jegyzet_ellenorzes(UT, SERTO_FM + "\n# a\n"), {"van": True, "hibak": [], "sertesek": []})
        self.assertEqual(t.h1_problemak(UT, "# Valami más\n"), [])
        # a formai hiba itt is hiba
        self.assertEqual(self.kodok(t.elemez(UT, DUPLA_FM)["problemak"]), ["duplikalt_kulcs"])

    def test_a_gazdai_status_a_sema_kifejezett_szava(self):
        t = self.epit("tanacsado")
        g = t.modosit(UT, JO_FM, "beallit", "Status", "Done", forras="gep")
        self.assertFalse(g["ok"])
        self.assertEqual(g["problemak"][0]["kod"], "status_gep")


class NullErtekkeszletTest(Alap):
    def test_null_nincs_korlat_az_ures_lista_minden_ertek_serto(self):
        kulcsok = ["Tags", "Source", "Status"]
        nyitott = {**SEMA, "mezosorrend": kulcsok, "tags_ertekkeszlet": None, "status_ertekkeszlet": None}
        t = self.epit("szigoru", nyitott)
        fm = "---\nTags:\n  - Whatever\nSource:\nStatus: Anything\n---\n"
        self.assertEqual(t.elemez(UT, fm)["problemak"], [])
        self.assertEqual((t.sema.tags, t.sema.status), (None, None))
        self.assertEqual(t.sema.leiras()["tags_ertekkeszlet"], [])                    # a felület listát kap
        j = t.ertek_javaslatok(UT, "Tags")
        self.assertFalse(j["ertekkeszlet"])
        zart = {**SEMA, "mezosorrend": kulcsok, "tags_ertekkeszlet": [], "status_ertekkeszlet": []}
        t = self.epit("szigoru", zart)
        self.assertEqual(self.kodok(t.elemez(UT, fm)["problemak"]), ["ertekkeszlet"])
        self.assertEqual(sum(1 for p in t.elemez(UT, fm)["problemak"] if p["kod"] == "ertekkeszlet"), 2)   # a címke és a Status is

    def test_ures_mezosorrend_nyitott_kulcsok(self):
        nyitott = {**SEMA, "mezosorrend": [], "extra_kulcsok": []}
        t = self.epit("szigoru", nyitott)
        self.assertEqual(t.elemez(UT, "---\nicon: book\nzzz: 1\n---\n")["problemak"], [])
        self.assertEqual(t.elemez(UT, "---\nSource: [[A]]\nModell: m\nicon: x\n---\n".replace("Source: [[A]]", "Source: x"))["problemak"], [])
        # a kísérő-osztály zárt marad
        self.assertEqual(self.kodok(t.elemez("Manifold - Cards/x.md", "---\nSource: x\nicon: x\n---\n")["problemak"]),
                         ["ismeretlen_kulcs", "mezosorrend"])


class FeloldasiLancTest(Alap):
    def preset_sema(self, nev: str, mezosorrend: list[str]) -> Path:
        p = self.root / "config" / "presets" / f"{nev}.schema.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({**SEMA, "mezosorrend": mezosorrend}), encoding="utf-8")
        return p

    def test_sorrend_fajl_preset_alap(self):
        alap = self.root / "config" / "schema-default.json"
        self.assertEqual(kiserok.sema_fajl(self.cfg), alap)                           # nincs fájl, nincs preset: az alap
        v2 = self.preset_sema("v2-kompat", ["Preset"])
        self.cfg.data.setdefault("telepites", {})["presetek"] = ["v2-kompat"]
        self.assertEqual(kiserok.sema_fajl(self.cfg), v2)                             # a megnevezett preset sémája
        self.assertEqual(Sema.betolt(self.cfg).mezosorrend, ["Preset"])
        sajat = Path(self._t.name) / "workspace-schema.json"
        sajat.write_text(json.dumps({**SEMA, "mezosorrend": ["Sajat"]}), encoding="utf-8")
        self.cfg.data["sema"]["vault"] = str(sajat)
        self.assertEqual(kiserok.sema_fajl(self.cfg), sajat)                          # a munkatér fájlja mindent megelőz
        self.assertEqual(Sema.betolt(self.cfg).mezosorrend, ["Sajat"])
        sajat.unlink()
        self.assertEqual(kiserok.sema_fajl(self.cfg), v2)                             # a hiányzó fájl: a lánc folytatódik

    def test_a_munkater_presetje_az_elso(self):
        masik = self.preset_sema("masik", ["Masik"])
        v2 = self.preset_sema("v2-kompat", ["Preset"])
        self.cfg.data.setdefault("telepites", {})["presetek"] = ["v2-kompat"]
        self.assertEqual(kiserok.sema_fajl(self.cfg), v2)
        self.cfg.data.setdefault("workspace", {})["presetek"] = ["masik"]
        self.assertEqual(kiserok.sema_fajl(self.cfg), masik)
        self.cfg.data["workspace"]["presetek"] = ["nincs-sema-fajlja", "v2-kompat"]   # preset sémafájl nélkül: a következő
        self.assertEqual(kiserok.sema_fajl(self.cfg), v2)

    def test_nincs_sema_hiba(self):
        (self.root / "config" / "schema-default.json").unlink()
        self.assertIsNone(kiserok.sema_fajl(self.cfg))
        with self.assertRaises(FileNotFoundError):
            Sema.betolt(self.cfg)
        self.assertIsNone(kiserok.sema_fajl(None))


class KiseroOsztalyTest(Alap):
    def test_a_szallitott_osztalyok_a_kiserokbol_jonnek(self):
        t = Tulajdonsagok(self.cfg, SimpleNamespace(tipusok={}))
        for mappa, nev in (("Manifold - Cards", "kartya"), ("Manifold - Quizzes", "kviz"), ("Manifold - Summaries", "osszefoglalo")):
            self.assertEqual(t.sema.osztaly(f"{mappa}/x.md")["nev"], nev, mappa)
        self.assertEqual(t.sema.osztaly("ATTCHMNTS - cards/x.md")["nev"], "normal")   # a fejlesztő mappája itt nem különleges
        self.assertEqual(t.sema.leiras()["kisero"]["kartya"], "Manifold - Cards")

    def test_a_kviz_osztaly_h1_szabalya_szigoru_modban(self):
        t = self.epit("szigoru", None)
        self.assertEqual(t.h1_problemak("Manifold - Quizzes/x.md", "# Nem kvíz-alak\n")[0]["kod"], "h1")
        self.assertEqual(t.h1_problemak("Projects/x.md", "# Bármi\n"), [])            # a szállított sémának nincs általános H1-szabálya


if __name__ == "__main__":
    unittest.main()
