"""C31 (2. audit T065): visszaállítás a belső lemezes bundle-ből (`core/visszaallitas.py`, `bin/mos visszaallit`).

Álvaulton és ál-`{backup}`-on: a bundle a `mentes.ment` valódi kimenete; a visszaállítás egy ÚJ, üres helyre megy
(`MOS_VAULT`, `MOS_VAULT_GIT` a teszt mappájában). Igazolja: a `.md` bájtra egyezik (CRLF, NFD-név, futtatható bit), a
`.jpg` hiányzik (a média nincs a bundle-ben, 14. döntés), a meglévő fájl érintetlen, a nem üres tároló mellett hiba, és
a visszaállított tároló a 2.0 beállításait kapja (a pillanatkép tovább működik)."""
import os
import unicodedata
import unittest
from pathlib import Path

from core import config, mentes, snapshot, visszaallitas
from tests.helpers import alg_core, ir, tmpdir


class VisszaallitasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "A.md", "# A\n\n[[B]]\n")
        ir(self.v, "Mappa/B.md", b"# B\r\nCRLF\r\n", "wb")
        ir(self.v, unicodedata.normalize("NFD", "Ékezetes jegyzet.md"), "# Ékezetes\n")
        ir(self.v, "Mappa/kep.jpg", b"\xff\xd8\xff" + b"\x00" * 200, "wb")
        ir(self.v, ".obsidian/app.json", '{"alwaysUpdateLinks": true}')
        (self.v / "szkript.sh").write_text("#!/bin/sh\necho x\n", encoding="utf-8")
        (self.v / "szkript.sh").chmod(0o755)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.bundle = mentes.ment(self.cfg)[0]
        self.assertTrue(self.bundle.name.startswith("vault-"))
        # az új hely: üres vault és hiányzó tároló
        self.uj_vault = Path(self._t.name) / "uj" / "Manifold"
        self.uj_git = Path(self._t.name) / "uj" / "var" / "vault.git"
        self.uj_vault.parent.mkdir(parents=True)
        self.ucfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"),
                                 "MOS_VAULT": str(self.uj_vault), "MOS_VAULT_GIT": str(self.uj_git)})

    def _fajlok(self, gyoker: Path) -> dict[str, bytes]:
        ki = {}
        for d, almappak, fajlok in os.walk(gyoker):
            for f in fajlok:
                p = Path(d) / f
                ki[unicodedata.normalize("NFC", str(p.relative_to(gyoker)))] = p.read_bytes()
        return ki

    def test_ures_helyre_a_szoveg_bajtra_a_media_hianyzik(self):
        r = visszaallitas.visszaallit(self.ucfg, self.bundle)
        self.assertTrue(r["munkafa_letrehozva"])
        self.assertEqual(r["head"], self.repo.git("rev-parse", "HEAD").stdout.strip())
        regi, uj = self._fajlok(self.v), self._fajlok(self.uj_vault)
        self.assertNotIn("Mappa/kep.jpg", uj)                               # a média nincs a bundle-ben (14.)
        self.assertIn("Mappa/kep.jpg", regi)
        for ut in ("A.md", "Mappa/B.md", "Ékezetes jegyzet.md", ".obsidian/app.json", "szkript.sh"):
            self.assertEqual(uj[ut], regi[ut], ut)                          # bájtra (a CRLF is)
        self.assertEqual(sorted(uj), sorted(k for k in regi if not k.endswith(".jpg")))
        self.assertTrue(os.access(self.uj_vault / "szkript.sh", os.X_OK))
        self.assertEqual(sorted(r["irt"]), sorted(uj))
        self.assertEqual((r["azonos"], r["elter"], r["status"]), ([], [], []))
        # a visszaállított tároló a 2.0-é: worktree, exclude, és a pillanatkép tovább megy
        urepo = snapshot.repos(self.ucfg)["vault"]
        self.assertEqual(urepo.git("config", "core.worktree").stdout.strip(), str(self.uj_vault))
        self.assertEqual(urepo.git("config", "core.bare").stdout.strip(), "false")
        self.assertEqual(urepo.git("remote").stdout.strip(), "")
        self.assertIn("*.manifold-tmp", (self.uj_git / "info" / "exclude").read_text(encoding="utf-8"))
        ir(self.uj_vault, "C.md", "# C\n")
        self.assertTrue(urepo.commit("új", {"Mos-Forras": "kezi"}))
        self.assertEqual(len(urepo.log(10)), 2)

    def test_meglevo_fajlt_nem_ir_felul(self):
        ir(self.uj_vault, "A.md", "# A — helyben javított\n")
        ir(self.uj_vault, "Mappa/B.md", b"# B\r\nCRLF\r\n", "wb")
        r = visszaallitas.visszaallit(self.ucfg, self.bundle)
        self.assertFalse(r["munkafa_letrehozva"])
        self.assertEqual((self.uj_vault / "A.md").read_text(encoding="utf-8"), "# A — helyben javított\n")
        self.assertEqual(r["elter"], ["A.md"])
        self.assertEqual(r["azonos"], ["Mappa/B.md"])
        self.assertNotIn("A.md", r["irt"])
        self.assertEqual([s[3:] for s in r["status"]], ["A.md"])           # a helyi változás látszik, nem veszett el

    def test_nem_ures_tarolo_mellett_hiba_es_semmi_nem_valtozik(self):
        self.uj_git.mkdir(parents=True)
        (self.uj_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        with self.assertRaises(visszaallitas.VisszaallitasHiba):
            visszaallitas.visszaallit(self.ucfg, self.bundle)
        self.assertEqual(os.listdir(self.uj_git), ["HEAD"])
        self.assertFalse(self.uj_vault.exists())

    def test_ures_tarolomappa_megengedett(self):
        self.uj_git.mkdir(parents=True)
        r = visszaallitas.visszaallit(self.ucfg, self.bundle)
        self.assertTrue((self.uj_git / "HEAD").is_file())
        self.assertIn("A.md", r["irt"])

    def test_hianyzo_szulo_mellett_nem_hoz_letre_munkafat(self):
        ucfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"),
                            "MOS_VAULT": str(Path(self._t.name) / "nincs-kotet" / "Manifold"),
                            "MOS_VAULT_GIT": str(self.uj_git)})
        with self.assertRaises(visszaallitas.VisszaallitasHiba):
            visszaallitas.visszaallit(ucfg, self.bundle)
        self.assertFalse((Path(self._t.name) / "nincs-kotet").exists())
        self.assertFalse(self.uj_git.exists())

    def test_hibas_bundle_nem_hagy_felkesz_tarolot(self):
        rossz = Path(self._t.name) / "rossz.bundle"
        rossz.write_bytes(b"# v2 git bundle\nszemet\n")
        with self.assertRaises(visszaallitas.VisszaallitasHiba):
            visszaallitas.visszaallit(self.ucfg, rossz)
        self.assertFalse(self.uj_git.exists())
        self.assertEqual([p.name for p in self.uj_git.parent.glob("*")] if self.uj_git.parent.exists() else [], [])

    def test_cli_igen_nelkul_megall(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        with mock.patch.object(visszaallitas.config, "load", return_value=self.ucfg), \
                mock.patch("builtins.input", side_effect=EOFError), redirect_stdout(io.StringIO()):
            self.assertEqual(visszaallitas.main([str(self.bundle)]), 1)
        self.assertFalse(self.uj_git.exists())
        with mock.patch.object(visszaallitas.config, "load", return_value=self.ucfg), redirect_stdout(io.StringIO()):
            self.assertEqual(visszaallitas.main([str(self.bundle), "--igen"]), 0)
        self.assertTrue((self.uj_vault / "A.md").is_file())


if __name__ == "__main__":
    unittest.main()
