"""F5 Settings: conflict/data boundaries, real config reload, module enforcement."""
import copy
import json
import tomllib
import unittest
from pathlib import Path
from unittest import mock
from core import config, csatolmany, modulkapu, termek_beallitasok as b, vezerlo
from core.utvonalak import HttpError
from tests.helpers import tmpdir
from tests.multi_user import termek_telepites, munkater, termek_cfg


class BeallitasTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.v, self.id = munkater(self.t.name, "Notes")
        self.cfg = termek_cfg(self.root, self.home, self.v)
        self.p = self.v / ".manifold/workspace.toml"
        self.note = self.v / "Kept.md"
        self.note.write_bytes(b"# Original\r\n\r\nUnchanged bytes.\r\n")

    def ment(self, d):
        return b.ir(self.cfg, b.olvas(self.cfg)["rev"], d)

    def test_elso_setup_automatikus_nyelv_egy_mentes_es_ujrainditas(self):
        elotte = self.note.read_bytes()
        regi = self.p.read_bytes()
        r = self.ment({"setup": {"kesz": True, "elmeny": "kutato"}, "szerkeszto": {"tab_meret": 4},
                       "altalanos": {"nyelv": "auto", "inditas": "valaszto"}, "modulok": {"video": False}})
        self.assertFalse(r["setup_szukseges"])
        cfg = termek_cfg(self.root, self.home, self.v)
        self.assertEqual(b.olvas(cfg), r)
        self.assertEqual(cfg.workspace_id, self.id)
        self.assertEqual(cfg.section("workspace")["nyelv"], "")
        self.assertFalse(cfg.section("modulok")["video"])
        self.assertEqual(self.note.read_bytes(), elotte)
        self.assertEqual(self.p.with_name("workspace.toml.elozo").read_bytes(), regi)

    def test_kulso_valtozas_409_es_nem_vesz_el_semmi(self):
        d = b.olvas(self.cfg)
        self.p.write_text(self.p.read_text() + "\n# changed in another editor\n")
        regi = self.p.read_bytes()
        with self.assertRaises(HttpError) as e:
            b.ir(self.cfg, d["rev"], {"setup": {"kesz": True}})
        self.assertEqual((e.exception.code, e.exception.kod), (409, "beallitas.utkozes"))
        self.assertEqual(self.p.read_bytes(), regi)
        self.assertFalse(b.olvas(self.cfg)["ertek"]["setup"]["kesz"])

    def test_hibas_ertekek_semmit_nem_irnak(self):
        regi = self.p.read_bytes()
        rossz = [{"ismeretlen": {}}, {"szerkeszto": {"tab_meret": True}}, {"szerkeszto": {"tab_meret": 99}},
                 {"megjelenes": {"betumeret": 2}}, {"altalanos": {"nyelv": "../../en"}},
                 {"fajlok": {"uj_mappa": "../Other"}}, {"fajlok": {"sablon_mappa": "/private"}},
                 {"fajlok": {"csatolmany_mappa": "./../Other"}}, {"modulok": {"new": True}},
                 {"fajlok": {"napi_ut": "Daily/{datum}.md"}}, {"billentyuk": {"bad id": "Mod+X"}}]
        for d in rossz:
            with self.subTest(d=d), self.assertRaises(HttpError):
                self.ment(d)
            self.assertEqual(self.p.read_bytes(), regi)

    def test_munkater_azonossaga_nem_valtoztathato(self):
        with self.assertRaises(HttpError):
            self.ment({"workspace": {"id": "a" * 32}})
        self.p.write_text(self.p.read_text().replace(self.id, "b" * 32))
        with self.assertRaises(HttpError) as e:
            b.olvas(self.cfg)
        self.assertEqual(e.exception.kod, "beallitas.munkater_csere")

    def test_szimlink_cel_es_mappa_nem_irhato(self):
        eredeti = self.p.read_bytes()
        masik = Path(self.t.name) / "outside.toml"
        masik.write_bytes(eredeti)
        self.p.unlink()
        self.p.symlink_to(masik)
        with self.assertRaises(config.ConfigError):
            b.olvas(self.cfg)
        self.assertEqual(masik.read_bytes(), eredeti)

    def test_idegen_toml_ertekek_es_eredeti_megjegyzes_visszanyerheto(self):
        self.p.write_text(self.p.read_text() + '\n# Keep original comments\n[custom]\narr = [{x=2}, {x=3}]\nwhen=2026-01-02\n')
        regi = tomllib.loads(self.p.read_text())["custom"]
        self.ment({"megjelenes": {"tema": "sotet"}})
        self.assertEqual(tomllib.loads(self.p.read_text())["custom"], regi)
        self.assertIn("Keep original comments", self.p.with_name("workspace.toml.elozo").read_text())

    def test_iras_hibaja_megori_a_regi_ertekeket_es_memoriat(self):
        regi = self.p.read_bytes()
        cfg_adat = copy.deepcopy(self.cfg.data)
        from core import workspace
        eredeti = workspace._atomi_ir_nofollow
        def ir(mappa, nev, adat):
            if nev == "workspace.toml":
                raise OSError("disk full")
            return eredeti(mappa, nev, adat)
        with mock.patch.object(workspace, "_atomi_ir_nofollow", side_effect=ir), self.assertRaises(OSError):
            self.ment({"setup": {"kesz": True}})
        self.assertEqual(self.p.read_bytes(), regi)
        self.assertEqual(self.cfg.data, cfg_adat)

    def test_obsidian_utak_atvetele_eredeti_fajlok_atirasa_nelkul(self):
        o = self.v / ".obsidian/app.json"
        o.write_text(json.dumps({"attachmentFolderPath": "./Assets", "newFileLocation": "folder", "newFileFolderPath": "Drafts"}))
        eredeti = o.read_bytes()
        d = b.olvas(self.cfg)["ertek"]
        self.assertEqual((d["fajlok"]["uj_mappa"], d["fajlok"]["csatolmany_mappa"]), ("Drafts", "./Assets"))
        self.ment({"setup": {"kesz": True}})
        self.assertEqual(o.read_bytes(), eredeti)

    def test_napi_sablon_nyelv_es_kulonbozo_modulok_live(self):
        self.ment({"altalanos": {"nyelv": "en"}, "fajlok": {"sablon_mappa": "Templates", "napi_ut": "[Journal]/YYYY-MM-DD"},
                   "modulok": {"video": False, "kartya": False}})
        self.assertEqual(self.cfg.section("sablon")["mappa"], "Templates")
        self.assertEqual(self.cfg.section("naplo")["ut"], "[Journal]/YYYY-MM-DD")
        for ut in ("/api/video/allapot", "/api/kartya/mai"):
            with self.assertRaises(HttpError) as e:
                modulkapu.ellenoriz(self.cfg, ut)
            self.assertEqual(e.exception.kod, "modul.kikapcsolva")
        modulkapu.ellenoriz(self.cfg, "/api/vault/fajl")
        self.ment({"modulok": {"video": True}})
        modulkapu.ellenoriz(self.cfg, "/api/video/allapot")

    def test_adatvedelem_es_legacy_kapcsolok_egy_forras(self):
        self.cfg.path("state").mkdir(parents=True)
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        self.assertFalse(b.olvas(self.cfg)["ertek"]["adatvedelem"]["tracker"])
        self.ment({"adatvedelem": {"tracker": True, "asszisztens": False}})
        self.assertEqual(vezerlo.kapcsolok(self.cfg), {"tracker": True, "asszisztens": False})
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": True})
        self.assertTrue(b.olvas(self.cfg)["ertek"]["adatvedelem"]["asszisztens"])

    def test_billentyu_pontozott_azonosito_visszatoltese(self):
        d = self.ment({"billentyuk": {"szerkeszto.mentes": "Mod+Alt+S"}})
        self.assertEqual(b.olvas(termek_cfg(self.root, self.home, self.v)), d)

    def test_mentes_utan_munkater_uj_azonositot_kaphat_beallitasvesztes_nelkul(self):
        from core import workspace
        eredeti = self.note.read_bytes()
        self.ment({"setup": {"kesz": True}, "billentyuk": {"szerkeszto.mentes": "Mod+Alt+S"}})
        elotte = tomllib.loads(self.p.read_text())
        uj = "b" * 32
        workspace._uj_id_irasa(self.p, self.id, uj)
        utana = tomllib.loads(self.p.read_text())
        self.assertEqual(utana["workspace"]["id"], uj)
        elotte["workspace"]["id"] = uj
        self.assertEqual(utana, elotte)
        self.assertEqual(self.note.read_bytes(), eredeti)


if __name__ == "__main__":
    unittest.main()
