import unittest

from core import config
from tests.helpers import alg_gyoker, tmpdir


class ConfigTeszt(unittest.TestCase):
    def test_helyorzok(self):
        with tmpdir() as t:
            root = alg_gyoker(t)
            c = config.load({"MOS_ROOT": str(root), "HOME": "/hazi"})
            self.assertEqual(c.path("var"), root / "var")
            self.assertEqual(c.path("vault"), root.parent / "Manifold")
            self.assertEqual(str(c.path("backup")), "/hazi/Manifold-backup")
            self.assertEqual(c.path("cache"), root / "var" / "cache")

    def test_kulcs_felulirasa(self):
        with tmpdir() as t:
            root = alg_gyoker(t)
            c = config.load({"MOS_ROOT": str(root), "MOS_VAULT": "/mas/vault", "HOME": "/h"})
            self.assertEqual(str(c.path("vault")), "/mas/vault")

    def test_felulirt_kulcs_a_hivatkozokra_is_hat(self):
        with tmpdir() as t:
            root = alg_gyoker(t)
            c = config.load({"MOS_ROOT": str(root), "MOS_VAR": "/x/var", "HOME": "/h"})
            self.assertEqual(str(c.path("models")), "/x/var/models")

    def test_gyoker_a_csomag_helyebol(self):
        self.assertEqual(config.os_root(), config.Path(__file__).resolve().parent.parent)


class LegacyConfigTeszt(unittest.TestCase):
    """A legacy `ConfigTest` portja (L49): lánc, körkörös és ismeretlen kulcs, env-felülírás, valódi config."""

    def test_expand_chain_and_normpath(self):
        t = {"os": "/X/Manifold-OS", "work": "{os}/..", "vault": "{work}/Manifold",
             "modulok": "{os}/modulok", "tools": "{modulok}/eszkozok"}
        self.assertEqual(config.expand("{vault}", t), "/X/Manifold")
        self.assertEqual(config.expand("{tools}", t), "/X/Manifold-OS/modulok/eszkozok")

    def test_cycle_and_unknown(self):
        with self.assertRaises(config.ConfigError):
            config.expand("{a}", {"a": "{b}", "b": "{a}"})
        with self.assertRaises(config.ConfigError):
            config.expand("{nincs}", {})
        with self.assertRaises(config.ConfigError):
            config.load({"MOS_CONFIG": "/nincs/ilyen.toml", "HOME": "/h"})

    def test_env_override(self):
        with tmpdir() as d:
            p = config.Path(d) / "os.toml"
            p.write_text('[utak]\nwork = "{os}/.."\nvault = "{work}/V"\n', encoding="utf-8")
            cfg = config.load({"MOS_CONFIG": str(p), "MOS_VAULT": "/masik/vault", "MOS_ROOT": "/R/os", "HOME": "/h"})
            self.assertEqual(str(cfg.path("vault")), "/masik/vault")
            self.assertEqual(str(cfg.path("work")), "/R")

    def test_real_config_resolves_relative_to_package(self):
        cfg = config.load({"HOME": "/h"})
        root = config.os_root()
        self.assertEqual(cfg.path("work"), root.parent)
        self.assertEqual(cfg.path("vault"), root.parent / "Manifold")
        self.assertEqual(cfg.path("vault_git"), root / "var" / "vault.git")
        self.assertEqual(config.Path(cfg.expand(cfg.section("pillanat", "vault")["git_dir"])), root / "var" / "vault.git")
        self.assertEqual(cfg.path("ytdlp"), root / "modulok" / "ytdlp")

    def test_pillanat_ut_a_felulirasra_hallgat(self):
        cfg = config.load({"HOME": "/h", "MOS_VAULT_GIT": "/proba/vault.git"})
        self.assertEqual(cfg.expand(cfg.section("pillanat", "vault")["git_dir"]), "/proba/vault.git")


class SemaConfigTeszt(unittest.TestCase):
    """T162 (2. audit, C11b): a `[sema] vault` kulcs feloldódik, a vault-séma JSON betölthető; a hiányzó kulcs és a
    hiányzó fájl hiba (a tulajdonság-szerkesztő és a gépi írás nem indulhat séma nélkül)."""

    def test_valodi_config_semaja_feloldodik_es_betoltheto(self):
        from core import tulajdonsagok
        cfg = config.load({"HOME": "/h"})
        ut = config.Path(cfg.expand(cfg.section("sema")["vault"]))
        self.assertEqual(ut, config.os_root() / "config" / "vault-sema.json")
        sema = tulajdonsagok.Sema.betolt(cfg)
        self.assertEqual(sema.mezosorrend, ["Tags", "Source", "Status", "NN", "Canvas"])
        self.assertTrue(sema.osztalyok)

    def test_hianyzo_kulcs_es_fajl_hiba(self):
        import tempfile
        from core import tulajdonsagok
        eredeti = (config.os_root() / "config" / "os.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="mos-teszt-") as d:
            toml = config.Path(d) / "os.toml"
            toml.write_text(eredeti.replace('vault = "{os}/config/vault-sema.json"', ""), encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                tulajdonsagok.Sema.betolt(config.load({"HOME": "/h", "MOS_CONFIG": str(toml)}))
            toml.write_text(eredeti.replace("{os}/config/vault-sema.json", f"{d}/nincs.json"), encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                tulajdonsagok.Sema.betolt(config.load({"HOME": "/h", "MOS_CONFIG": str(toml)}))


class RejtettAlapertekTeszt(unittest.TestCase):
    """Lelet 8: a kódban `.get(kulcs, ALAP)`-pal olvasott [core] kulcsok az `os.toml`-ban is szerepelnek, az alapértékkel
    egyezően (nincs rejtett alapérték); a core által nem olvasott (történeti) kulcsok megjegyzése kimondja ezt."""

    @classmethod
    def setUpClass(cls):
        import tomllib

        from tests.helpers import REPO
        cls.szoveg = (REPO / "config" / "os.toml").read_text(encoding="utf-8")
        cls.os_toml = tomllib.loads(cls.szoveg)

    def test_a_kezelo_idokorlat_az_os_tomlban_van_es_egyezik_az_alapertekkel(self):
        from core import server
        self.assertEqual(self.os_toml["core"]["kezelo_idokorlat_mp"], server.KEZELO_IDOKORLAT_MP)

    def test_a_halott_fuzetfigyelo_kulcsok_torteneti_megjegyzessel_allnak(self):
        import re
        for kulcs in ("figyelo_be", "figyelo_indulasi_szunet_mp", "figyelo_periodus_mp", "figyelo_nyugalom_mp"):
            with self.subTest(kulcs=kulcs):
                fuzet = self.szoveg.split("\n[fuzet]\n", 1)[1].split("\n[", 1)[0]
                sor = re.search(rf"(?m)^{kulcs}\s*=.*$", fuzet)
                self.assertIsNotNone(sor)
                self.assertIn("történeti kulcs", sor.group(0))


if __name__ == "__main__":
    unittest.main()
