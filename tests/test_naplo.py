"""A napi jegyzet (C15): útvonal-formátum, létrehozás a vault konvenciója szerint, meglévő jegyzet nem íródik
felül, a Canvas csak létező havi canvasra mutat, a felülíró sablon, versenyhelyzet. Álvaulton."""
import os
import unicodedata
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from core import naplo, sablon, snapshot, vaultio
from core.utvonalak import HttpError
from tests import csak_darwin
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit

NAP = date(2026, 10, 2)
UT = "X01 - Napló & To-Do/2026-10/Napló/2026-10-02.md"
VAZ = "---\nTags:\n  - Napló\nSource:\nStatus:\nNN:\n{canvas}\n---\n\n# Napló\n\n"


class Alap(unittest.TestCase):
    FAJLOK: dict = {}

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        for rp, t in self.FAJLOK.items():
            ir(self.v, rp, t)
        self.esemenyek = []
        self.vault = vaultio.Vault(self.cfg, publish=lambda e, **k: self.esemenyek.append(e))
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.app = SimpleNamespace(vault=self.vault, index=self.ix)

    def olvas(self, rp=UT):
        return (self.v / rp).read_text(encoding="utf-8")


class UtTest(Alap):
    def test_napi_ut(self):
        self.assertEqual(naplo.napi_ut(self.cfg, NAP), UT)
        self.assertEqual(naplo.napi_ut(self.cfg, date(2026, 1, 3)), "X01 - Napló & To-Do/2026-01/Napló/2026-01-03.md")

    def test_datum_ertek(self):
        self.assertEqual(naplo.datum_ertek("2026-10-02"), NAP)
        self.assertEqual(naplo.datum_ertek(None), date.today())
        self.assertEqual(naplo.datum_ertek(""), date.today())
        for hibas in ("2026-13-01", "2026-10-2", "tegnap", 20261002, "2026-02-30"):
            with self.assertRaises(HttpError, msg=str(hibas)) as e:
                naplo.datum_ertek(hibas)
            self.assertEqual(e.exception.code, 400)

    def test_konfigbol_felulirhato_az_ut(self):
        self.cfg.data.setdefault("naplo", {})["ut"] = "[Napló]/YYYY/YYYY-MM-DD"
        self.assertEqual(naplo.napi_ut(self.cfg, NAP), "Napló/2026/2026-10-02.md")


class LetrehozasTest(Alap):
    def test_letrehozas_hianyzo_mappakkal(self):
        r = naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertEqual((r["ut"], r["letrejott"]), (UT, True))
        t = self.olvas()
        self.assertEqual(t, VAZ.format(canvas="Canvas:") + "\n")
        self.assertEqual(r["kurzor"], len(VAZ.format(canvas="Canvas:")))
        self.assertTrue(any(e["tipus"] == "vault_iras" and e["ut"] == UT for e in self.esemenyek))

    def test_a_status_ures_es_a_sema_sorrendje_all(self):
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        kulcsok = [s.split(":")[0] for s in self.olvas().split("---")[1].splitlines() if s and not s.startswith(" ")]
        self.assertEqual(kulcsok, ["Tags", "Source", "Status", "NN", "Canvas"])
        self.assertIn("\nStatus:\n", self.olvas())               # gép nem tölti ki (L33)

    def test_meglevot_nem_ir_felul(self):
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        ir(self.v, UT, "a felhasználó szövege\n")
        r = naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertEqual((r["ut"], r["letrejott"], r["kurzor"]), (UT, False, None))
        self.assertEqual(self.olvas(), "a felhasználó szövege\n")

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_a_lemezen_allo_nfd_mappa_nem_duplazodik(self):
        nfd = unicodedata.normalize("NFD", "X01 - Napló & To-Do")
        ir(self.v, f"{nfd}/2026-09/Napló/2026-09-19.md", "régi\n")
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        felso = [n for n in os.listdir(self.v) if n.startswith("X01")]
        self.assertEqual(len(felso), 1)                         # az APFS egy mappát lát; nem jön létre NFC testvér
        self.assertTrue((self.v / UT).is_file())

    def test_a_hianyzo_honap_mappa_letrejon_a_meglevo_marad(self):
        ir(self.v, "X01 - Napló & To-Do/2026-10/Napló/2026-10-01.md", "tegnapi\n")
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertEqual(self.olvas("X01 - Napló & To-Do/2026-10/Napló/2026-10-01.md"), "tegnapi\n")
        self.assertTrue((self.v / UT).is_file())

    def test_versenyhelyzet_a_masik_letrehozta(self):
        eredeti = self.vault.create

        def veszit(d):
            ir(self.v, UT, "a nyertes\n")                       # közben létrejött
            return eredeti(d)
        self.vault.create = veszit
        r = naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertEqual((r["letrejott"], r["ut"]), (False, UT))
        self.assertEqual(self.olvas(), "a nyertes\n")

    def test_masik_hiba_tovabbmegy(self):
        def hiba(d):
            raise vaultio.Invalid("valami más")
        self.vault.create = hiba
        with self.assertRaises(vaultio.Invalid):
            naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")

    def test_gepi_commit_a_letrehozasrol(self):
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        log = repo.log(5)
        self.assertIn(UT, str(log[0]))
        self.assertIn("pult-szerkeszto", str(log[0]))


class CanvasTest(Alap):
    FAJLOK = {"X00 - Visual/2026-09.canvas": "{}"}

    def test_a_canvas_csak_letezo_havira_mutat(self):
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertIn("\nCanvas:\n", self.olvas())              # októberhez nincs canvas: üres
        naplo.megnyit_vagy_letrehoz(self.app, "2026-09-30")
        t = self.olvas("X01 - Napló & To-Do/2026-09/Napló/2026-09-30.md")
        self.assertIn('\nCanvas: "[[2026-09.canvas]]"\n', t)    # szeptemberhez van: a konvenció szerint

    def test_havi_canvas_kis_nagybetu_nelkul(self):
        self.assertEqual(naplo.havi_canvas(self.cfg, self.ix, date(2026, 9, 1)), "2026-09.canvas")
        self.assertIsNone(naplo.havi_canvas(self.cfg, self.ix, date(2026, 10, 1)))


class SajatSablonTest(Alap):
    FAJLOK = {"_Template/Napi jegyzet.md": "# {{title}} ({{date:dddd}})\n\n{{cursor}}tennivalók\n"}

    def test_a_sablonmappa_jegyzete_felulirja_a_beepitettet(self):
        r = naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertEqual(self.olvas(), "# 2026-10-02 (péntek)\n\ntennivalók\n")
        self.assertEqual(r["kurzor"], len("# 2026-10-02 (péntek)\n\n"))

    def test_a_beepitett_vaz_ha_nincs_ilyen_nevu(self):
        self.cfg.data.setdefault("naplo", {})["sablon"] = "Nincs ilyen"
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertIn("# Napló", self.olvas())


class CreateKulcsokTest(Alap):
    """A `Vault.create` két új kulcsa (C15)."""

    def test_tartalom_es_mappa_keszit(self):
        r = self.vault.create({"mappa": "Új/Mappa", "nev": "J", "tartalom": "szöveg\n", "mappa_keszit": True})
        self.assertEqual(r["ut"], "Új/Mappa/J.md")
        self.assertEqual(self.olvas("Új/Mappa/J.md"), "szöveg\n")

    def test_mappa_keszit_nelkul_nem_hoz_letre_mappat(self):
        with self.assertRaises(vaultio.NotFound):
            self.vault.create({"mappa": "Új/Mappa", "nev": "J", "tartalom": "x"})
        self.assertFalse((self.v / "Új").exists())

    def test_mappa_keszit_tiltott_nevvel_nem(self):
        with self.assertRaises(vaultio.NotFound):
            self.vault.create({"mappa": "Új/a:b", "nev": "J", "mappa_keszit": True})
        with self.assertRaises(vaultio.Invalid):
            self.vault.create({"mappa": ".rejtett/x", "nev": "J", "mappa_keszit": True})
        with self.assertRaises(vaultio.Invalid):
            self.vault.create({"mappa": "../kint", "nev": "J", "mappa_keszit": True})

    def test_abszolut_mappa_nem_hoz_letre_mappat_a_vaulton_belul_sem(self):
        """`POST /api/vault/uj`: az abszolút mappa nem válhat csendben vault-relatívvá (a `norm_path` a vezető `/`-t levágná)."""
        kint = tmpdir()
        self.addCleanup(kint.cleanup)
        for mappa in (f"{kint.name}/ujmappa", "/etc/ujmappa", "\\\\kint\\ujmappa", "~/ujmappa", "C:/ujmappa", ["Lista"]):
            for keszit in (True, False):
                with self.subTest(mappa=mappa, keszit=keszit):
                    with self.assertRaises(vaultio.Invalid) as e:
                        self.vault.create({"mappa": mappa, "nev": "J", "mappa_keszit": keszit})
                    self.assertEqual(e.exception.hiba_kod, "vault.mappa_nem_relativ")
        self.assertFalse((self.v / "etc").exists() or (self.v / "ujmappa").exists() or (self.v / kint.name.lstrip("/")).exists())
        self.assertFalse(Path(kint.name, "ujmappa").exists())

    def test_szimlinkes_mappan_at_nem_keszul_mappa_a_vaulton_kivul(self):
        kint = tmpdir()
        self.addCleanup(kint.cleanup)
        os.symlink(kint.name, self.v / "Kivezet")
        for mappa in ("Kivezet", "Kivezet/ujmappa"):
            with self.subTest(mappa=mappa):
                with self.assertRaises(vaultio.Invalid):
                    self.vault.create({"mappa": mappa, "nev": "J", "mappa_keszit": True})
        self.assertEqual(os.listdir(kint.name), [])

    def test_tartalom_csak_jegyzethez_es_csak_szoveg(self):
        for d in ({"mappa": "", "nev": "J", "tipus": "base", "tartalom": "x"},
                  {"mappa": "", "nev": "J", "tartalom": 5},
                  {"mappa": "", "nev": "J", "tartalom": ["x"]}):
            with self.assertRaises(vaultio.Invalid):
                self.vault.create(d)

    def test_tartalom_nelkul_a_regi_viselkedes(self):
        self.vault.create({"mappa": "", "nev": "03 - Valami"})
        self.assertEqual(self.olvas("03 - Valami.md"), "# Valami\n")
        with self.assertRaises(vaultio.Invalid):
            self.vault.create({"mappa": "", "nev": "03 - Valami"})


class SemlegesAlap(unittest.TestCase):
    """A szállított semleges alapok (preset nélkül): angol nevek, `Daily/` mappa, semleges váz. 12-templates-04/08/09."""
    FAJLOK: dict = {}

    def setUp(self):
        from tests.vaultgyar import alg_semleges
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_semleges(self._t.name)
        for rp, t in self.FAJLOK.items():
            ir(self.v, rp, t)
        self.vault = vaultio.Vault(self.cfg)
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.app = SimpleNamespace(vault=self.vault, index=self.ix)

    def olvas(self, rp):
        return (self.v / rp).read_text(encoding="utf-8")

    def naplo(self, **kulcsok):
        self.cfg.data.setdefault("naplo", {}).update(kulcsok)


class SemlegesVazTest(SemlegesAlap):
    """12-templates-09: a beépített váz semleges, angol, a fejlesztő konvenciója nélkül."""

    def test_az_alap_ut_es_a_semleges_vaz(self):
        r = naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertEqual((r["ut"], r["letrejott"], r["sablon_hiany"]), ("Daily/2026-10-02.md", True, None))
        t = self.olvas("Daily/2026-10-02.md")
        self.assertEqual(t, "# 2026-10-02\n\n\n")
        self.assertEqual(r["kurzor"], len("# 2026-10-02\n\n"))
        for tiltott in ("Tags", "Source", "Status", "NN", "Canvas", "Napló", "---"):
            self.assertNotIn(tiltott, t)

    def test_a_szallitott_konfig_nem_hordoz_fejleszto_vazat(self):
        b = naplo.beallitasok(self.cfg)
        self.assertEqual((b["sablon"], b["vaz"]), ("", "semleges"))
        szoveg = (Path(naplo.__file__).parent.parent / "config" / "os.toml").read_text(encoding="utf-8")
        self.assertNotIn("Napi jegyzet", szoveg)

    def test_a_v2_vaz_csak_kifejezett_kerésre(self):
        self.naplo(vaz="v2")
        naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")
        self.assertIn("\nStatus:\n", self.olvas("Daily/2026-10-02.md"))

    def test_a_v2_preset_a_regi_vazat_es_nevet_hozza(self):
        """A `v2-kompat` preset (a tesztgyökér alapja): sablonnév, váz és hónapnevek a fejlesztő konvenciója — beállításon át."""
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg = alg_core(t.name)[0]
        b = naplo.beallitasok(cfg)
        self.assertEqual((b["vaz"], b["sablon"]), ("v2", "Napi jegyzet"))
        self.assertEqual(sablon.tartalmi_nyelv(cfg), "hu")


class SablonUtTest(SemlegesAlap):
    """12-templates-08: a napi sablon vault-relatív út (bárhol a vaultban), látható tartalékkal."""
    FAJLOK = {"Templates/Daily.md": "# Daily {{date:dddd}}\n\n{{cursor}}",
              "Elsewhere/Journal/Day.md": "Day {{title}}\n",
              "_Template/Rövid.md": "Short {{title}}\n"}

    def nyit(self):
        return naplo.megnyit_vagy_letrehoz(self.app, "2026-10-02")

    def test_utvonal_a_sablonmappan_kivul_is(self):
        self.naplo(sablon="Elsewhere/Journal/Day.md")
        r = self.nyit()
        self.assertEqual(self.olvas(r["ut"]), "Day 2026-10-02\n")
        self.assertIsNone(r["sablon_hiany"])

    def test_az_md_kiterjesztes_elhagyhato(self):
        self.naplo(sablon="Templates/Daily")
        r = self.nyit()
        self.assertEqual(self.olvas(r["ut"]), "# Daily Friday\n\n")                 # angol nap, alap nyelv
        self.assertEqual(r["kurzor"], len("# Daily Friday\n\n"))

    def test_puszta_nev_a_sablonmappaban_regi_rovidites(self):
        self.naplo(sablon="Rövid")
        self.assertEqual(self.olvas(self.nyit()["ut"]), "Short 2026-10-02\n")

    def test_hianyzo_sablon_semleges_vaz_es_lathato_jelzes(self):
        self.naplo(sablon="Templates/Nincs.md")
        r = self.nyit()
        self.assertEqual(self.olvas(r["ut"]), "# 2026-10-02\n\n\n")
        self.assertEqual(r["sablon_hiany"], "Templates/Nincs.md")
        self.naplo(sablon="Nincs ilyen")                                              # puszta név: a sablonmappa útja a jelzésben
        r = naplo.megnyit_vagy_letrehoz(self.app, "2026-10-03")
        self.assertEqual(r["sablon_hiany"], "_Template/Nincs ilyen.md")

    def test_ervenytelen_sablon_ut_sem_dob_hibat(self):
        for rossz in ("../kint.md", ".obsidian/app.json", "Templates/../../x.md", "/abszolut/x.md"):
            self.naplo(sablon=rossz)
            r = naplo.megnyit_vagy_letrehoz(self.app, "2026-10-04")
            self.assertTrue(r["sablon_hiany"], rossz)
            self.assertEqual(self.olvas(r["ut"]), "# 2026-10-04\n\n\n")
            (self.v / r["ut"]).unlink()

    def test_meglevo_jegyzetnel_nincs_jelzes(self):
        self.naplo(sablon="Templates/Nincs.md")
        self.nyit()
        r = self.nyit()
        self.assertEqual((r["letrejott"], r["sablon_hiany"]), (False, None))

    def test_nem_szoveges_sablon_hianynak_szamit(self):
        ir(self.v, "Templates/kep.png", b"\x89PNG", "wb")
        self.naplo(sablon="Templates/kep.png")
        self.assertEqual(self.nyit()["sablon_hiany"], "Templates/kep.png.md")


class NapAzUtbolTest(SemlegesAlap):
    """12-templates-04: a napi jegyzet napja az útjából (a `napi_ut` fordítottja)."""

    def test_korbejaras_tobb_formatummal(self):
        from datetime import date
        for fmt in ("[Daily]/YYYY-MM-DD", "YYYY-MM-DD", "YYYY/MMMM/YYYY-MMM-DD", "[Journal]/gggg/[W]ww/dddd",
                    "[Dnevnik]/DD.MM.YYYY", "gggg-[W]ww-E"):
            self.naplo(ut=fmt)
            for nap in (date(2026, 1, 1), date(2026, 10, 17), date(2026, 12, 31), date(2024, 2, 29)):
                ut = naplo.napi_ut(self.cfg, nap)
                # (a hét-év formátumoknál a decemberi/januári határnap az év ±1-ében is megtalálható)
                self.assertEqual(naplo.nap_az_utbol(self.cfg, ut), nap, f"{fmt} → {ut}")

    def test_nem_napi_jegyzet_none(self):
        self.assertIsNone(naplo.nap_az_utbol(self.cfg, "Welcome.md"))
        self.assertIsNone(naplo.nap_az_utbol(self.cfg, "Daily/valami.md"))
        self.assertIsNone(naplo.nap_az_utbol(self.cfg, "../Daily/2026-10-01.md"))
        self.assertIsNone(naplo.nap_az_utbol(self.cfg, ""))
        self.assertIsNone(naplo.nap_az_utbol(self.cfg, None))


class SzomszedTest(SemlegesAlap):
    """12-templates-04: előző / következő napi jegyzet."""
    FAJLOK = {"Daily/2026-10-01.md": "egy\n", "Daily/2026-10-05.md": "öt\n", "Daily/2026-10-20.md": "húsz\n"}

    def test_a_legkozelebbi_letezo_jegyzet_a_hivatkozasi_naptol(self):
        r = naplo.szomszed(self.app, "Daily/2026-10-05.md", None, "elozo")
        self.assertEqual((r["ut"], r["datum"], r["letrejott"]), ("Daily/2026-10-01.md", "2026-10-01", False))
        r = naplo.szomszed(self.app, "Daily/2026-10-05.md", None, "kovetkezo")
        self.assertEqual((r["ut"], r["datum"], r["letrejott"]), ("Daily/2026-10-20.md", "2026-10-20", False))
        self.assertFalse((self.v / "Daily/2026-10-06.md").exists())             # a hézag nem jön létre

    def test_kifejezett_datum_a_hivatkozas(self):
        r = naplo.szomszed(self.app, "Welcome.md", "2026-10-20", "elozo")
        self.assertEqual(r["datum"], "2026-10-05")

    def test_nem_napi_jegyzetrol_a_mai_naphoz_kepest(self):
        from datetime import date, timedelta
        ma = date.today()
        ir(self.v, f"Daily/{(ma - timedelta(days=3)).isoformat()}.md", "x\n")
        r = naplo.szomszed(self.app, "Welcome.md", None, "elozo")
        self.assertEqual(r["datum"], (ma - timedelta(days=3)).isoformat())

    def test_ha_nincs_letezo_a_szomszedos_naptari_nap_jon_letre(self):
        r = naplo.szomszed(self.app, "Daily/2026-10-20.md", None, "kovetkezo")
        self.assertEqual((r["ut"], r["letrejott"], r["datum"]), ("Daily/2026-10-21.md", True, "2026-10-21"))
        self.assertEqual(self.olvas("Daily/2026-10-21.md"), "# 2026-10-21\n\n\n")
        r = naplo.szomszed(self.app, "Daily/2026-10-01.md", None, "elozo")
        self.assertEqual((r["ut"], r["letrejott"]), ("Daily/2026-09-30.md", True))

    def test_az_ablakon_tul_nem_keres(self):
        ir(self.v, "Daily/2025-01-01.md", "régi\n")
        r = naplo.szomszed(self.app, "Daily/2026-10-01.md", None, "elozo")
        self.assertEqual(r["datum"], "2026-09-30")                              # 2025-01-01 több mint SZOMSZED_ABLAK napra van

    def test_hibas_irany_es_datum_400(self):
        for irany in ("fel", None, 1):
            with self.assertRaises(HttpError, msg=str(irany)) as e:
                naplo.szomszed(self.app, None, None, irany)
            self.assertEqual(e.exception.code, 400)
        with self.assertRaises(HttpError):
            naplo.szomszed(self.app, None, "tegnap", "elozo")


if __name__ == "__main__":
    unittest.main()
