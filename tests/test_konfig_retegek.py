"""Rétegzett konfiguráció (F3-DESIGN §2.2–§2.5): a rétegek sorrendje és eredete, a rétegenkénti engedélylista (egy
ellenséges `workspace.toml` sem írhatja át a homokozót, az utakat, a routert, a kalibrációt), az értékszabályok (típus, hossz,
regex, pontos szakasz), a végzetes TOML-hiba, az `ID_MINTA`, a `MOS_SETTINGS`, és a halasztott (`nincs_vault`,
`nincs_workspace`) kulcsok."""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from core import config
from tests.helpers import alg_bundle, alg_gyoker, tmpdir

ID = "0123456789abcdef0123456789abcdef"


def ir(p: Path, szoveg: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(szoveg, encoding="utf-8")
    return p


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.home = self.t / "home"

    def hordozhato(self, settings: str | None = None, workspace: str | None = None, **kw) -> Path:
        root = alg_gyoker(self._t.name, **kw)
        if settings is not None:
            ir(root / "var" / "settings.toml", settings)
        if workspace is not None:
            ir(root.parent / "Manifold" / ".manifold" / "workspace.toml", workspace)
        return root

    def load(self, root: Path, **env) -> config.Config:
        return config.load({"MOS_ROOT": str(root), "HOME": str(self.home), **env})

    def elutasitott(self, cfg, reteg: str) -> dict[str, str]:
        return {k: kod for r, k, kod in cfg.elutasitott if r == reteg}


class SorrendTeszt(Alap):
    def test_s_pi_i_pw_w_e_sorrend_es_eredet(self):
        root = self.hordozhato(
            settings='[utak]\nvault = "{work}/Manifold"\n[telepites]\npresetek = ["pi"]\n'
                     '[naplo]\nut = "I"\nsablon = "I"\ncanvas = "I"\n',
            workspace=f'[workspace]\nid = "{ID}"\npresetek = ["pw"]\n[naplo]\nut = "W"\n')
        ir(root / "config" / "presets" / "pi.toml",
           '[naplo]\nut = "PI"\nsablon = "PI"\ncanvas = "PI"\ndolgozat_mappa = "PI"\n')
        ir(root / "config" / "presets" / "pw.toml", '[naplo]\nut = "PW"\nsablon = "PW"\n')
        cfg = self.load(root, MOS_VAULT=str(root.parent / "Manifold"))
        n = cfg.section("naplo")
        self.assertEqual((n["ut"], n["sablon"], n["canvas"], n["dolgozat_mappa"]), ("W", "PW", "I", "PI"))
        self.assertEqual([cfg.forras("naplo", k) for k in ("ut", "sablon", "canvas", "dolgozat_mappa")],
                         ["munkater", "preset:pw", "telepites", "preset:pi"])
        self.assertEqual(cfg.forras("naplo", "naptar_regi_ora"), "os")              # a tábla többi kulcsa az S-é marad
        self.assertEqual(cfg.forras("utak", "vault"), "env")                         # az E nyer az I fölött
        self.assertEqual(cfg.workspace_id, ID)
        self.assertEqual(cfg.elutasitott, [])

    def test_tablak_egyesulnek_a_listak_cserelodnek(self):
        root = self.hordozhato(settings='[utak]\nvault = "{work}/Manifold"\n[naplo]\nkiertekelo_nevek = ["egy"]\n',
                               preset=None)
        alap = self.load(alg_gyoker(str(self.t / "masik"), preset=None))
        cfg = self.load(root)
        self.assertEqual(cfg.section("naplo")["kiertekelo_nevek"], ["egy"])
        self.assertEqual({k: v for k, v in cfg.section("naplo").items() if k != "kiertekelo_nevek"},
                         {k: v for k, v in alap.section("naplo").items() if k != "kiertekelo_nevek"})

    def test_ujraepitheto_a_config_az_egyesitett_adatbol(self):
        root = self.hordozhato(workspace=f'[workspace]\nid = "{ID}"\n[naplo]\nut = "W"\n')
        env = {"MOS_ROOT": str(root), "HOME": str(self.home)}
        cfg = config.load(env)
        masik = config.Config(cfg.root, cfg.data, env, cfg.source)
        for attr in ("utak", "feloldatlan", "elrendezes", "workspace_id", "retegek", "elutasitott"):
            self.assertEqual(getattr(masik, attr), getattr(cfg, attr), attr)

    def test_a_termek_kulonbsegei_os_termek_eredetuek(self):
        root = alg_bundle(self._t.name)
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)}, munkater=False)
        self.assertEqual(cfg.forras("utak", "install"), "os:termek")
        self.assertEqual(cfg.forras("utak", "state"), "os")


class EngedelylistaTeszt(Alap):
    def test_ellenseges_workspace_toml_nem_ir_at_vedett_kulcsot(self):
        ellenseges = "\n".join([
            f'[workspace]\nid = "{ID}"',
            '[homokozo]\nidokorlat_mp = 99999',
            '[utak]\nvar = "/tmp/ellenseges-var"\nsandbox_exec = "/bin/sh"',
            '[router]\nx = 1',
            '[kalibracio]\nkuszob = 0.0',
            '[kapuk]\nidezet_kuszob = 0.0',
            '[pillanat.vault]\nkizar = ["*"]',
            '[sema]\nvault = "/etc/passwd"',
            '[mentes]\nkodtar = "/"\nmegtartott_bundle = 1',
            '[modellek.qwen35_9b]\nkalibralt = true',
            '[felkeszultseg]\nkalibralt = true',
            '[naplo]\nut = ".manifold/var/x"',
            '[kartya]\nmappa = "../kint"',
            '[kviz]\nmappa = "/abszolut"',
            '[osszefoglalas]\nmappa = "A/.obsidian/b"',
            '[media]\nvideo_mappa = "{home}/x"',
            '[fuzet]\nmappak = ["/Users/x/titok"]',
            '[sablon]\nmappa = "~/x"',
        ]) + "\n"
        root = self.hordozhato(workspace=ellenseges)
        alap = config.load({"MOS_ROOT": str(alg_gyoker(str(self.t / "tiszta"))), "HOME": str(self.t / "tiszta" / "home")})
        cfg = self.load(root)
        rossz = self.elutasitott(cfg, "munkater")
        for kulcs in ("homokozo.idokorlat_mp", "utak.var", "utak.sandbox_exec", "router.x", "kalibracio.kuszob",
                      "kapuk.idezet_kuszob", "pillanat.vault.kizar", "sema.vault", "mentes.kodtar",
                      "mentes.megtartott_bundle", "modellek.qwen35_9b.kalibralt", "felkeszultseg.kalibralt", "fuzet.mappak"):
            self.assertEqual(rossz.get(kulcs), "reteg_tiltott", kulcs)
        self.assertEqual(rossz["naplo.ut"], "ut_pontos_szakasz")
        self.assertEqual(rossz["kartya.mappa"], "ut_szulo")
        self.assertEqual(rossz["kviz.mappa"], "ut_abszolut")
        self.assertEqual(rossz["osszefoglalas.mappa"], "ut_pontos_szakasz")
        self.assertEqual(rossz["media.video_mappa"], "ut_abszolut")
        self.assertEqual(rossz["sablon.mappa"], "ut_abszolut")
        # semmi nem változott: az utak, a szakaszok az alapé (a munkatér-azonosítón kívül)
        def relativ(c):
            alap_mappa = c.root.parent.parent
            return {k: os.path.relpath(p, alap_mappa) if alap_mappa in p.parents else str(p) for k, p in c.utak.items()}
        self.assertEqual(relativ(cfg), relativ(alap))
        for sz in ("homokozo", "kapuk", "pillanat", "sema", "mentes", "naplo", "kartya", "kviz", "media", "fuzet", "sablon"):
            self.assertEqual(json.dumps(cfg.section(sz), sort_keys=True).replace(str(root.parent.parent), "<T>"),
                             json.dumps(alap.section(sz), sort_keys=True).replace(str(alap.root.parent.parent), "<T>"), sz)
        self.assertEqual(cfg.workspace_id, ID)

    def test_a_telepitesi_reteg_engedelylistaja(self):
        root = self.hordozhato(settings='[utak]\nvault = "{work}/Manifold"\nvar = "/x"\n[homokozo]\nidokorlat_mp = 1\n'
                                        '[workspace]\nid = "' + ID + '"\n[mentes]\nmegtartott_bundle = 1\nido_perc = 5\n'
                                        '[modellgazda]\nmin_szabad_szazalek = 30\nport = 7\n', preset=None)
        cfg = self.load(root)
        rossz = self.elutasitott(cfg, "telepites")
        self.assertEqual(rossz, {"utak.var": "reteg_tiltott", "homokozo.idokorlat_mp": "reteg_tiltott",
                                 "workspace.id": "reteg_tiltott", "mentes.megtartott_bundle": "tartomany",
                                 "modellgazda.port": "reteg_tiltott"})
        self.assertEqual(cfg.section("mentes")["ido_perc"], 5)
        self.assertEqual(cfg.section("modellgazda")["min_szabad_szazalek"], 30)
        self.assertIsNone(cfg.workspace_id)

    def test_a_vaultot_termekben_a_telepitesi_reteg_nem_adhatja(self):
        root = alg_bundle(self._t.name)
        install = self.home / "Library" / "Application Support" / "Manifold"
        ir(install / "settings.toml", f'[utak]\nvault = "{self.t}/v"\n[fuzet]\nmappak = ["/x"]\n'
                                      '[munkaterek."' + ID + '".fuzet]\nmappak = ["/y"]\n')
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)}, munkater=False)
        self.assertEqual(self.elutasitott(cfg, "telepites"), {"utak.vault": "reteg_tiltott", "fuzet.mappak": "reteg_tiltott"})
        self.assertEqual(cfg.feloldatlan.get("vault"), config.NINCS_VAULT)
        self.assertEqual(cfg.section("munkaterek", ID, "fuzet")["mappak"], ["/y"])

    def test_reteg_ellenoriz_api(self):
        alap = self.load(self.hordozhato()).data
        self.assertEqual(config.reteg_ellenoriz("munkater", {"naplo": {"ut": "Napi/YYYY"}}, alap), [])
        self.assertEqual(config.reteg_ellenoriz("munkater", {"router": {"a": 1}, "naplo": {"ut": 5}}, alap),
                         [("router.a", "reteg_tiltott"), ("naplo.ut", "tipus")])
        with self.assertRaises(config.ConfigError) as e:
            config.reteg_ellenoriz("nincs", {}, alap)
        self.assertEqual(e.exception.kod, "reteg_ismeretlen")


class ErtekSzabalyTeszt(Alap):
    def ellenoriz(self, **valtozasok) -> dict[str, str]:
        if not hasattr(self, "_alap"):
            self._root = self.hordozhato()
            self._alap = self.load(self._root).data
        return dict(config.reteg_ellenoriz("munkater", valtozasok, self._alap, self._root))

    def test_tipus_hossz_regex(self):
        self.assertEqual(self.ellenoriz(naplo={"ut": 5}), {"naplo.ut": "tipus"})
        self.assertEqual(self.ellenoriz(naplo={"ut": "x" * 513}), {"naplo.ut": "szoveg_hossz"})
        self.assertEqual(self.ellenoriz(video={"kizart_mappak": ["a"] * 257}), {"video.kizart_mappak": "lista_hossz"})
        self.assertEqual(self.ellenoriz(video={"kizart_mappak": [1]}), {"video.kizart_mappak": "tipus"})
        self.assertEqual(self.ellenoriz(video={"tema_minta": "a" * 201}), {"video.tema_minta": "regex_hossz"})
        self.assertEqual(self.ellenoriz(video={"tema_minta": "(nyitott"}), {"video.tema_minta": "regex"})
        self.assertEqual(self.ellenoriz(video={"tema_minta": r"^\d{2} - "}), {})
        self.assertEqual(self.ellenoriz(felkeszultseg={"suly_kartya": True}), {"felkeszultseg.suly_kartya": "tipus"})
        self.assertEqual(self.ellenoriz(felkeszultseg={"suly_kartya": 1}), {})              # egész a lebegőpontos helyén
        self.assertEqual(self.ellenoriz(naplo={"uj_kulcs": "x"}), {"naplo.uj_kulcs": "ismeretlen_kulcs"})
        self.assertEqual(self.ellenoriz(naplo="szoveg"), {"naplo": "reteg_tiltott"})

    def test_uj_kulcs_csak_a_nyitott_tablakban(self):
        self.assertEqual(self.ellenoriz(pdf={"tags": {"Uj targy": "uj"}}, naptar={"szotar": {"targyak": {"Uj": ["uj"]}}},
                                        asszisztens={"tantargy_nevek": {"uj": "Új"}}), {})

    def test_ut_szabalyok(self):
        self.assertEqual(self.ellenoriz(naplo={"ut": "Napi/YYYY-MM-DD"}), {})
        self.assertEqual(self.ellenoriz(naplo={"ut": "a/../b"}), {"naplo.ut": "ut_szulo"})
        self.assertEqual(self.ellenoriz(naplo={"ut": "é"}), {"naplo.ut": "ut_nem_nfc"})
        self.assertEqual(self.ellenoriz(asszisztens={"emlites_kizart": ["Jo", ".obsidian"]}),
                         {"asszisztens.emlites_kizart": "ut_pontos_szakasz"})
        self.assertEqual(self.ellenoriz(naplo={"sablon": "/abs/sablon.md"}), {"naplo.sablon": "ut_abszolut"})

    def test_workspace_id_minta(self):
        self.assertEqual(self.ellenoriz(workspace={"id": ID}), {})
        for rossz in ("ABC", ID.upper(), ID + "0", "../" + ID[3:]):
            self.assertEqual(self.ellenoriz(workspace={"id": rossz}), {"workspace.id": "id"}, rossz)
        self.assertEqual(self.ellenoriz(workspace={"presetek": ["nincs-ilyen"]}), {"workspace.presetek": "preset_ismeretlen"})
        self.assertEqual(self.ellenoriz(workspace={"presetek": ["../x"]}), {"workspace.presetek": "preset_ismeretlen"})
        self.assertEqual(self.ellenoriz(workspace={"presetek": ["v2-kompat"]}), {})
        self.assertTrue(config.ID_MINTA.match(ID))

    def test_rossz_id_a_munkateren_nem_lesz_azonosito(self):
        cfg = self.load(self.hordozhato(workspace='[workspace]\nid = "rossz"\n'))
        self.assertIsNone(cfg.workspace_id)
        self.assertEqual(self.elutasitott(cfg, "munkater"), {"workspace.id": "id"})

    def test_rossz_mos_workspace_id_vegzetes(self):
        with self.assertRaises(config.ConfigError) as e:
            self.load(self.hordozhato(), MOS_WORKSPACE_ID="../x")
        self.assertEqual(e.exception.kod, "workspace_id_hibas")


class TomlHibaTeszt(Alap):
    def test_settings_toml_hiba_vegzetes(self):
        root = self.hordozhato(settings="[utak\nvault = ")
        with self.assertRaises(config.ConfigError) as e:
            self.load(root)
        self.assertEqual(e.exception.kod, "settings_toml_hibas")
        self.assertIn("settings.toml", e.exception.param["ut"])

    def test_workspace_toml_hiba_vegzetes(self):
        root = self.hordozhato(workspace="[workspace\n")
        with self.assertRaises(config.ConfigError) as e:
            self.load(root)
        self.assertEqual(e.exception.kod, "workspace_toml_hibas")

    def test_preset_toml_hiba_vegzetes(self):
        root = self.hordozhato()
        ir(root / "config" / "presets" / "v2-kompat.toml", "[x\n")
        with self.assertRaises(config.ConfigError) as e:
            self.load(root)
        self.assertEqual(e.exception.kod, "preset_toml_hibas")


class MosSettingsTeszt(Alap):
    def test_nem_ures_ut_barmely_gyokerre_hat(self):
        root = self.hordozhato(preset=None, vault=False)
        masik = ir(self.t / "masik.toml", '[utak]\nvault = "/a/vault"\n')
        cfg = self.load(root, MOS_SETTINGS=str(masik))
        self.assertEqual(cfg.path("vault"), Path("/a/vault"))
        self.assertEqual(cfg.data["_meta"]["settings"], str(masik))

    def test_ures_ertek_a_kod_checkoutjanak_reteget_kapcsolja_ki(self):
        root = self.hordozhato()
        with mock.patch.object(config, "_KOD_GYOKER", root.resolve()):
            cfg = self.load(root, MOS_SETTINGS="")
            self.assertEqual(cfg.feloldatlan["vault"], config.NINCS_VAULT)
            self.assertEqual(cfg.data["_meta"]["settings"], "")
            with mock.patch.dict(os.environ, {"MOS_SETTINGS": ""}):        # a `bin/mos test` folyamat-környezete is
                self.assertIn("vault", self.load(root).feloldatlan)
        # idegen gyökérnél (álgyökér a tesztben) az üres érték nem hat: az álgyökér a saját rétegét olvassa
        self.assertEqual(self.load(root, MOS_SETTINGS="").path("vault"), root.parent / "Manifold")


class HalasztottTeszt(Alap):
    def test_vault_nelkul_csak_a_vaultra_epulo_kulcsok_halasztottak(self):
        root = self.hordozhato(preset=None, vault=False)
        cfg = self.load(root)
        self.assertEqual(cfg.feloldatlan, {"vault": "nincs_vault", "workspace": "nincs_vault"})
        self.assertEqual(cfg.path("var"), root / "var")
        for hivas in (lambda: cfg.path("vault"), lambda: cfg.path("workspace"), lambda: cfg.expand("{vault}/x")):
            with self.assertRaises(config.ConfigError) as e:
                hivas()
            self.assertEqual(e.exception.kod, "nincs_vault")
        with self.assertRaises(config.ConfigError) as e:
            cfg.path("nincs_ilyen")
        self.assertEqual(e.exception.kod, "ismeretlen_ut")

    def test_elgepelt_helyorzo_tovabbra_is_betolteskor_hiba(self):
        root = self.hordozhato()
        szoveg = (root / "config" / "os.toml").read_text(encoding="utf-8").replace('"{var}/state"', '"{vra}/state"', 1)
        ir(root / "config" / "os.toml", szoveg)
        with self.assertRaises(config.ConfigError) as e:
            self.load(root)
        self.assertEqual(e.exception.kod, "helyorzo_ismeretlen")

    def test_termek_munkater_nelkul(self):
        root = alg_bundle(self._t.name)
        vault = self.t / "Jegyzetek"
        vault.mkdir()
        env = {"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_VAULT": str(vault)}
        with self.assertRaises(config.ConfigError) as e:
            config.load(env)
        self.assertEqual((e.exception.kod, e.exception.param["vault"]), ("nem_workspace", str(vault)))
        cfg = config.load(env, munkater=False)
        for k in ("workspace", "var", "tmp", "state", "index", "vault_git", "ytdlp", "archive", "backup"):
            self.assertEqual(cfg.feloldatlan.get(k), "nincs_workspace", k)
        with self.assertRaises(config.ConfigError) as e:
            cfg.path("tmp")
        self.assertEqual(e.exception.kod, "nincs_workspace")
        install = self.home / "Library" / "Application Support" / "Manifold"
        self.assertEqual((cfg.path("install"), cfg.path("models"), cfg.path("vault")), (install, install / "models", vault))
        # vault nélkül a vaultra épülő kulcsok `nincs_vault`-ok, a többi feloldódik
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.home)})
        self.assertEqual((cfg.feloldatlan["vault"], cfg.feloldatlan["workspace"], cfg.feloldatlan["var"]),
                         ("nincs_vault", "nincs_vault", "nincs_vault"))

    def test_termek_munkaterrel_es_a_regiszter_dont_az_allapot_helyerol(self):
        root = alg_bundle(self._t.name)
        vault = self.t / "Jegyzetek"
        ir(vault / ".manifold" / "workspace.toml", f'[workspace]\nid = "{ID}"\n')
        env = {"MOS_ROOT": str(root), "HOME": str(self.home), "MOS_VAULT": str(vault)}
        cfg = config.load(env)
        self.assertEqual((cfg.elrendezes, cfg.workspace_id, cfg.feloldatlan), ("termek", ID, {}))
        self.assertEqual(cfg.path("var"), vault / ".manifold" / "var")
        install = self.home / "Library" / "Application Support" / "Manifold"
        self.assertEqual(cfg.path("backup"), install / "backups" / ID)
        # a regiszter-bejegyzés csak a SAJÁT vaulthoz kötve dönt (az azonosító a vaulttal utazik: egy másolat vagy egy letöltött vault
        # ugyanazt hordozhatja, és nem kaphatja meg a regisztrált szinkronmappa-munkatér állapotát)
        ir(install / "workspaces.json", json.dumps({"formatum": 1, "munkaterek": {ID: {"allapot": "telepites"}}}))
        self.assertEqual(config.load(env).path("var"), vault / ".manifold" / "var")              # útvonal nélkül: nem a miénk
        masik = self.t / "Masik"
        masik.mkdir()
        ir(install / "workspaces.json", json.dumps({"formatum": 1, "munkaterek": {
            ID: {"allapot": "telepites", "vault": str(masik), "kanonikus": str(masik)}}}))
        self.assertEqual(config.load(env).path("var"), vault / ".manifold" / "var")              # másik létező vaulté
        ir(install / "workspaces.json", json.dumps({"formatum": 1, "munkaterek": {
            ID: {"allapot": "telepites", "vault": str(vault), "kanonikus": str(vault)}}}))
        cfg = config.load(env)
        self.assertEqual(cfg.path("var"), install / "workspaces" / ID / "var")
        self.assertEqual(cfg.forras("utak", "var"), "regiszter")
        # a vaultban utazó workspace.toml nem dönthet az állapot helyéről
        ir(vault / ".manifold" / "workspace.toml", f'[workspace]\nid = "{ID}"\nallapot = "telepites"\n[utak]\nvar = "/x"\n')
        ir(install / "workspaces.json", "{}")
        cfg = config.load(env)
        self.assertEqual(cfg.path("var"), vault / ".manifold" / "var")
        self.assertEqual(self.elutasitott(cfg, "munkater"), {"workspace.allapot": "reteg_tiltott", "utak.var": "reteg_tiltott"})


class ConfigErrorTeszt(unittest.TestCase):
    def test_kod_es_param(self):
        e = config.ConfigError("szöveg", kod="x", param={"a": 1})
        self.assertEqual((str(e), e.kod, e.param), ("szöveg", "x", {"a": 1}))
        self.assertEqual(config.ConfigError("y").kod, "konfig_hiba")
        self.assertIsInstance(e, ValueError)


if __name__ == "__main__":
    unittest.main()
