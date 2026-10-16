"""F5 integration-review regressions: Automatic clears hints, related routes stay gated."""
import copy
import json
import os
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from core import modulkapu, termek_beallitasok as b, tulajdonsagok
from core.utvonalak import HttpError
from tests.helpers import tmpdir
from tests.multi_user import termek_telepites, munkater, termek_cfg


class F5BeallitasJavitasTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.v, self.id = munkater(self.t.name, "Synthetic notes")
        self.cfg = termek_cfg(self.root, self.home, self.v)

    def _ment(self, valtozas):
        return b.ir(self.cfg, b.olvas(self.cfg)["rev"], valtozas)

    def test_automatikus_valasztas_torli_a_korabbi_tartalmi_nyelvet(self):
        sema = tulajdonsagok.Sema.betolt(self.cfg)
        for nyelv in ("hu", "en"):
            with self.subTest(nyelv=nyelv):
                self._ment({"altalanos": {"nyelv": nyelv}})
                self.assertEqual(sema.leiras()["nyelv"], nyelv)
                self._ment({"altalanos": {"nyelv": "auto"}})
                self.assertEqual(self.cfg.section("sablon")["nyelv"], "")
                self.assertEqual(sema.leiras()["nyelv"], "")
                uj = termek_cfg(self.root, self.home, self.v)
                self.assertEqual(b.olvas(uj)["ertek"]["altalanos"]["nyelv"], "auto")
                self.assertEqual(tulajdonsagok.Sema.betolt(uj).leiras()["nyelv"], "")

    def test_obsidian_current_uj_jegyzet_mappa_megmarad(self):
        obsidian = self.v / ".obsidian" / "app.json"
        obsidian.write_text(json.dumps({"newFileLocation": "current"}), encoding="utf-8")
        regi = obsidian.read_bytes()
        self.assertEqual(b.olvas(self.cfg)["ertek"]["fajlok"]["uj_mappa"], ".")
        self._ment({"setup": {"kesz": True}})
        uj = termek_cfg(self.root, self.home, self.v)
        self.assertEqual(b.olvas(uj)["ertek"]["fajlok"]["uj_mappa"], ".")
        self.assertEqual(obsidian.read_bytes(), regi)
        for rossz in ("./Other", "./../Other", "../Other"):
            with self.subTest(rossz=rossz), self.assertRaises(HttpError):
                self._ment({"fajlok": {"uj_mappa": rossz}})

    def test_zar_szimlinkre_cserelt_szulo_mogott_sem_hoz_letre_fajlt(self):
        cel = self.v / ".manifold" / "workspace.toml"
        mappa = cel.parent
        masik = Path(self.t.name) / "outside"
        masik.mkdir()
        felretett = self.v / ".manifold-original"
        eredeti_open = os.open

        def nyit(ut, *args, **kwargs):
            if Path(ut) == mappa:
                mappa.rename(felretett)
                mappa.symlink_to(masik, target_is_directory=True)
            return eredeti_open(ut, *args, **kwargs)

        try:
            with mock.patch.object(b.os, "open", side_effect=nyit), self.assertRaises(HttpError) as e:
                with b._zar(cel):
                    self.fail("a replaced settings directory must not be locked")
            self.assertEqual(e.exception.kod, "beallitas.symlink")
            self.assertEqual(list(masik.iterdir()), [], "even a lock cannot be created outside the workspace")
        finally:
            if mappa.is_symlink():
                mappa.unlink()
            if felretett.exists():
                felretett.rename(mappa)

    def test_emlekezteto_es_valos_sablon_vegpontok_is_kapuzottak(self):
        utak = {"naptar": ("/api/emlekezteto/allapot", "/api/emlekezteto/utkozes/latva"),
                "sablonok": ("/api/sablon/lista", "/api/sablon/alkalmaz", "/api/vault/sablon")}
        self._ment({"modulok": {"naptar": False, "sablonok": False}})
        for modul, prefixek in utak.items():
            for ut in prefixek:
                with self.subTest(ut=ut), self.assertRaises(HttpError) as e:
                    modulkapu.ellenoriz(self.cfg, ut)
                self.assertEqual((e.exception.code, e.exception.kod, e.exception.param["modul"]), (409, "modul.kikapcsolva", modul))
        # The prefix guard does not accidentally block similarly named unrelated routes.
        modulkapu.ellenoriz(self.cfg, "/api/sablonok-mas")
        modulkapu.ellenoriz(self.cfg, "/api/vault/fajl")
        self._ment({"modulok": {"naptar": True, "sablonok": True}})
        for prefixek in utak.values():
            for ut in prefixek:
                modulkapu.ellenoriz(self.cfg, ut)

    def test_toml_idegen_unicode_inline_kulcsai_is_visszaolvashatok(self):
        # TOML supports literal Unicode keys, but does not support JSON's surrogate escape form for astral characters.
        adat = {"custom": {"items": [{"📓": "kept", "árvíz": "unchanged"}], "other": {"🧠": 2}}}
        eredeti = copy.deepcopy(adat)
        self.assertEqual(tomllib.loads(b.toml_ir(adat)), eredeti)
        p = self.v / ".manifold" / "workspace.toml"
        p.write_text(p.read_text() + b.toml_ir(adat), encoding="utf-8")
        self._ment({"setup": {"kesz": True}})
        self.assertEqual(tomllib.loads(p.read_text())["custom"], eredeti["custom"])

    def test_graf_bazis_es_kereses_feluletei_kapuzottak_a_nyers_jegyzet_szabad(self):
        utak = {
            "graf": ("/api/vault/graf", "/api/vault/graf-meta", "/api/vault/graf-beallitasok"),
            "kereses": ("/api/vault/kereses", "/api/kereses/hibrid", "/api/kereses/hasonlo", "/api/kereses/vektor-allapot"),
            "bazis": ("/api/vault/bazis/lekerdez", "/api/vault/bazis/modosit"),
            "hivatkozasok": ("/api/vault/visszahivatkozasok", "/api/vault/emlitesek"),
            "napi": ("/api/ma", "/api/naplo/ma"),
        }
        self._ment({"modulok": dict.fromkeys(utak, False)})
        for modul, vegpontok in utak.items():
            for ut in vegpontok:
                with self.subTest(ut=ut), self.assertRaises(HttpError) as e:
                    modulkapu.ellenoriz(self.cfg, ut)
                self.assertEqual(e.exception.param["modul"], modul)
        for ut in ("/api/vault/fajl", "/api/vault/uj", "/api/vault/fa", "/api/vault/sema", "/api/vault/linkcel",
                   "/api/beallitasok", "/api/kereses/kerdezz", "/api/kereses/hasonlosag"):
            modulkapu.ellenoriz(self.cfg, ut)
        self._ment({"modulok": {"kerdezz": False, "asszisztens": False}})
        for ut, modul in (("/api/kereses/kerdezz", "kerdezz"), ("/api/kereses/hasonlosag", "asszisztens")):
            with self.subTest(ut=ut), self.assertRaises(HttpError) as e:
                modulkapu.ellenoriz(self.cfg, ut)
            self.assertEqual(e.exception.param["modul"], modul)
        self._ment({"modulok": dict.fromkeys(utak, True)})
        for vegpontok in utak.values():
            for ut in vegpontok:
                modulkapu.ellenoriz(self.cfg, ut)


if __name__ == "__main__":
    unittest.main()
