"""A napi jegyzet (C15): útvonal-formátum, létrehozás a vault konvenciója szerint, meglévő jegyzet nem íródik
felül, a Canvas csak létező havi canvasra mutat, a felülíró sablon, versenyhelyzet. Álvaulton."""
import os
import unicodedata
import unittest
from datetime import date
from types import SimpleNamespace

from core import naplo, snapshot, vaultio
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


if __name__ == "__main__":
    unittest.main()
