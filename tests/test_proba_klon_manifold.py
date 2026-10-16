"""F3-DESIGN §3.6, K2: a D9-próbaklón a `.manifold` NÉLKÜL készül (`frame.apfs_clone_vault`).

A termékben a `{tmp}` a vaultban van (`.manifold/var/tmp`): a régi `cp -c -R <vault>` a klónba másolta volna a munkatér
állapotát, benne a korábbi próbaklónokat (és önmagát: rekurzió). A klón tartalma a vault a `.manifold` nélkül, bájtra; a
hordozható (v2) elrendezésben a régi teljes klónnal azonos."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from core import frame, gepi_iras, snapshot, vaultio, workspace
from tests import csak_darwin
from tests.fresh_install import lenyomat, obsidian_vault, termek_alap, termek_cfg
from tests.helpers import alg_core, tmpdir

KOR = "KARTYA-20261016-100000-proba"


@csak_darwin("APFS-klón (`cp -c`)")
class ProbaKlonManifoldTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        root, home, alap = termek_alap(self._t.name)
        self.v = obsidian_vault(self.t / "Vault")
        workspace.letrehoz(self.v, alap)
        self.cfg = termek_cfg(root, home, self.v)

    def test_a_klon_a_manifold_nelkul_bajtra_a_vault(self):
        d = self.cfg.path("tmp") / "proba" / "K1"
        self.assertTrue(str(d).startswith(str(self.v / ".manifold")))    # a klón célja a vault belsejében van
        kv, kg = frame.trial_clone(self.cfg, d)
        self.assertFalse((kv / ".manifold").exists())
        self.assertEqual(lenyomat(kv, kihagy=()), lenyomat(self.v))
        self.assertEqual(subprocess.run(["git", "--git-dir", str(kg), "config", "--get", "core.worktree"],
                                        capture_output=True, text=True).stdout.strip(), str(kv))

    def test_nincs_rekurzio_a_masodik_klon_nem_tartalmazza_az_elsot(self):
        k1, _ = frame.trial_clone(self.cfg, self.cfg.path("tmp") / "proba" / "K1")
        k2, _ = frame.trial_clone(self.cfg, self.cfg.path("tmp") / "proba" / "K2")
        self.assertEqual(lenyomat(k2, kihagy=()), lenyomat(k1, kihagy=()))
        db = sum(len(f) for _, _, f in os.walk(k2))
        self.assertEqual(db, sum(len(f) for _, _, f in os.walk(self.v)) - sum(len(f) for _, _, f in os.walk(self.v / ".manifold")))

    def test_a_gepi_iras_klonja_a_termekben(self):
        g = gepi_iras.GepiIras(self.cfg, vaultio.Vault(self.cfg), mock.Mock())
        k = g._klon(KOR)
        d = self.cfg.path("tmp") / "proba" / KOR
        self.assertEqual(k.cfg.path("vault"), d / self.v.name)
        self.assertFalse((d / self.v.name / ".manifold").exists())
        self.assertTrue((d / frame.PROBA_JELOLO).is_file())
        self.assertEqual(k.v.root, d / self.v.name)                        # a munkatér-azonosság a valódi workspace.toml-ból
        self.assertEqual(k.cfg.path("tmp"), self.cfg.path("tmp"))
        self.assertTrue(snapshot.repos(k.cfg)["vault"].live())

    def test_apfs_clone_vault_symlink_rejtett_fajl_es_jogok(self):
        src = self.t / "Forras"
        (src / ".obsidian").mkdir(parents=True)
        (src / ".manifold" / "var").mkdir(parents=True)
        (src / ".manifold" / "var" / "x").write_text("allapot")
        (src / "a.md").write_text("a")
        (src / "link.md").symlink_to("a.md")
        (src / "-kotojel.md").write_text("k")
        os.chmod(src, 0o750)
        dst = self.t / "Cel" / "Forras"
        frame.apfs_clone_vault(src, dst)
        self.assertEqual(sorted(os.listdir(dst)), ["-kotojel.md", ".obsidian", "a.md", "link.md"])
        self.assertTrue((dst / "link.md").is_symlink())
        self.assertEqual(os.readlink(dst / "link.md"), "a.md")
        self.assertEqual(os.stat(dst).st_mode & 0o777, 0o750)
        ures = self.t / "Ures"
        ures.mkdir()
        frame.apfs_clone_vault(ures, self.t / "UresKlon")
        self.assertEqual(os.listdir(self.t / "UresKlon"), [])


@csak_darwin("APFS-klón (`cp -c`)")
class HordozhatoKlonTest(unittest.TestCase):
    def test_hordozhatoban_a_regi_teljes_klonnal_azonos(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        cfg, _, v = alg_core(t.name)
        obsidian_vault(v)
        repo = snapshot.repos(cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        kv, _ = frame.trial_clone(cfg, Path(t.name) / "uj")
        regi = Path(t.name) / "regi" / v.name
        frame.apfs_clone(v, regi)                                           # a v2 `cp -c -R <vault> <dst>`
        self.assertEqual(lenyomat(kv, kihagy=()), lenyomat(regi, kihagy=()))


if __name__ == "__main__":
    unittest.main()
