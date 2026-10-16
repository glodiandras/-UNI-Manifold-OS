"""A D9-próbaklón konfigja (F3-DESIGN §2.6, K2): a klón a FELOLDOTT utakat kapja, nem a sablonokat. Csak a négy klón-kulcs
(`vault`, `vault_git`, `run`, `ytdlp_git`) mutat a próbamappába; minden más — termékben a `{vault}`-ból számolt `{workspace}`,
`{var}` és családja is — a valódi helyén marad, így a klón nem kap más állapot-mappát. Az egyesített adatból épül (a rétegek
nem olvasódnak újra), az elrendezés és a munkatér-azonosító megmarad."""
import unittest
from pathlib import Path
from unittest import mock

from core import config, gepi_iras, vaultio
from tests.helpers import alg_bundle, alg_core, tmpdir

ID = "0123456789abcdef0123456789abcdef"
KLON_KULCSOK = {"vault", "vault_git", "run", "ytdlp_git"}


class KlonEnvTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)

    def klon_cfg(self, cfg, kor: str = "KARTYA-20261016-100000-proba"):
        """A `_klon` konfigja; a klón mappáját előre megteremti (a vault és egy `HEAD`), így APFS-klón nem kell."""
        d = cfg.path("tmp") / "proba" / kor
        (d / cfg.path("vault").name).mkdir(parents=True)
        (d / "vault.git").mkdir()
        (d / "vault.git" / "HEAD").write_text("ref: refs/heads/main\n")
        g = gepi_iras.GepiIras(cfg, vaultio.Vault(cfg), mock.Mock())
        return g._klon(kor).cfg, d

    def ellenoriz(self, cfg, kcfg, d: Path):
        self.assertIs(kcfg.data, cfg.data)
        self.assertEqual((kcfg.elrendezes, kcfg.workspace_id), (cfg.elrendezes, cfg.workspace_id))
        self.assertEqual(kcfg.feloldatlan, {})
        self.assertEqual(set(kcfg.utak), set(cfg.utak))
        for k, p in cfg.utak.items():
            if k not in KLON_KULCSOK:
                self.assertEqual(kcfg.path(k), p, k)
        self.assertEqual(kcfg.path("vault"), d / cfg.path("vault").name)
        self.assertEqual((kcfg.path("vault_git"), kcfg.path("run"), kcfg.path("ytdlp_git")),
                         (d / "vault.git", d / "run", d / "ytdlp.git"))
        self.assertEqual(kcfg.table["home"], cfg.table["home"])

    def test_hordozhato(self):
        cfg, _, _ = alg_core(self._t.name)
        kcfg, d = self.klon_cfg(cfg)
        self.ellenoriz(cfg, kcfg, d)
        self.assertEqual(kcfg.path("workspace"), cfg.path("workspace"))      # a klón nem a saját `.manifold`-ját olvasná

    def test_termek_a_vaultbol_szamolt_allapot_a_valodi_helyen_marad(self):
        root = alg_bundle(self._t.name)
        vault = self.t / "Jegyzetek"
        (vault / ".obsidian").mkdir(parents=True)
        (vault / ".manifold").mkdir()
        (vault / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{ID}"\n', encoding="utf-8")
        cfg = config.load({"MOS_ROOT": str(root), "HOME": str(self.t / "home"), "MOS_VAULT": str(vault)})
        self.assertEqual(cfg.path("var"), vault / ".manifold" / "var")
        kcfg, d = self.klon_cfg(cfg)
        self.ellenoriz(cfg, kcfg, d)
        for k in ("workspace", "var", "tmp", "state", "index", "szemelyes", "work", "backup"):
            self.assertEqual(kcfg.path(k), cfg.path(k), k)
            self.assertNotIn(d, kcfg.path(k).parents, k)
        self.assertEqual(kcfg.elrendezes, "termek")
        self.assertEqual(kcfg.workspace_id, ID)


if __name__ == "__main__":
    unittest.main()
