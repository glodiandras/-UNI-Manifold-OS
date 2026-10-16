"""F3 (F3-DESIGN §4): a core konfigurációs hibánál nem tracebackkel hal el — az első stdout-sor `{"hiba": kod, "param",
"uzenet"}`, a kilépési kód 78 (EX_CONFIG); a héj a `kod`-ból mutat üzenetet. A már fogott zárak elengedve, és a core semmit
nem hoz létre egy nem elérhető vault helyén (egy nem csatolt kötet `/Volumes/X`-e)."""
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from core import config, server, workspace
from tests.helpers import REPO, alg_gyoker, env, tmpdir
from tests.multi_user import munkater, termek_cfg, termek_env, termek_telepites


def _start(e: dict) -> tuple[int, dict, str]:
    p = subprocess.run([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, input=b"", capture_output=True, env=e,
                       timeout=90)
    sorok = p.stdout.decode("utf-8", "replace").splitlines()
    return p.returncode, (json.loads(sorok[0]) if sorok else {}), p.stderr.decode("utf-8", "replace")


class CoreStartHibaTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def _hiba(self, rc: int, sor: dict, stderr: str, kod: str) -> None:
        self.assertEqual(rc, server.KONFIG_HIBA_KILEPES, stderr)
        self.assertEqual(sor.get("hiba"), kod, sor)
        self.assertIsInstance(sor.get("param"), dict)
        self.assertTrue(sor.get("uzenet"))
        self.assertNotIn("Traceback", stderr)

    def test_hordozhato_vault_nelkul(self):
        root = alg_gyoker(self._t.name, vault=False)
        rc, sor, err = _start(env(MOS_ROOT=str(root), PYTHONPATH=str(REPO)))
        self._hiba(rc, sor, err, config.NINCS_VAULT)
        self.assertEqual(sor["param"], {"kulcs": "vault"})

    def test_hibas_settings_toml(self):
        root = alg_gyoker(self._t.name)
        (root / "var" / "settings.toml").write_text("[utak\nvault = 1\n", encoding="utf-8")
        rc, sor, err = _start(env(MOS_ROOT=str(root), PYTHONPATH=str(REPO)))
        self._hiba(rc, sor, err, "settings_toml_hibas")

    def test_termek_nem_munkater_mappa(self):
        root, home = termek_telepites(self._t.name)
        v = Path(self._t.name) / "Csak jegyzetek"
        (v / ".obsidian").mkdir(parents=True)
        rc, sor, err = _start(termek_env(root, home, v))
        self._hiba(rc, sor, err, "nem_workspace")
        self.assertFalse((v / ".manifold").exists(), "a core munkateret nem hoz létre")

    def test_termek_ujabb_formatumu_munkater(self):
        root, home = termek_telepites(self._t.name)
        v, _ = munkater(self._t.name, "Jovobeli", olvaso_min=workspace.FORMATUM_MAX + 1)
        rc, sor, err = _start(termek_env(root, home, v))
        self._hiba(rc, sor, err, "workspace_ujabb")
        self.assertIsNone(server.zar_foglalt(v / ".manifold" / "var" / "run" / "core.lock"))

    def test_nem_elerheto_vault_helyen_semmi_nem_keletkezik(self):
        root, home = termek_telepites(self._t.name)
        v = Path(self._t.name) / "Lecsatolt kotet" / "Jegyzetek"
        cfg = termek_cfg(root, home, v, MOS_WORKSPACE_ID="c" * 32)
        out = io.StringIO()
        self.assertEqual(server.start(cfg, out=out), server.KONFIG_HIBA_KILEPES)
        sor = json.loads(out.getvalue().splitlines()[0])
        self.assertEqual((sor["hiba"], sor["param"]), ("vault_nem_elerheto", {"vault": str(v)}))
        self.assertFalse(v.parent.exists())

    def test_a_munkater_megnyitasa_utani_hiba_elengedi_a_zarakat(self):
        root, home = termek_telepites(self._t.name)
        v, _ = munkater(self._t.name, "Jegyzet")
        cfg = termek_cfg(root, home, v)
        out = io.StringIO()
        hiba = config.ConfigError("próba", kod="workspace_csere", param={"x": Path("/p")})
        with mock.patch.object(workspace, "nyit", side_effect=hiba):
            self.assertEqual(server.start(cfg, out=out), server.KONFIG_HIBA_KILEPES)
        self.assertEqual(json.loads(out.getvalue().splitlines()[0]),
                         {"hiba": "workspace_csere", "param": {"x": "/p"}, "uzenet": "próba"})
        self.assertIsNone(server.zar_foglalt(cfg.path("run") / "core.lock"))
        self.assertIsNone(server.zar_foglalt(server.vault_or_ut(cfg)))

    def test_kod_nelkuli_hiba_nem_nyelodik_el(self):
        root, home = termek_telepites(self._t.name)
        v, _ = munkater(self._t.name, "Jegyzet")
        cfg = termek_cfg(root, home, v)
        with mock.patch.object(workspace, "nyit", side_effect=RuntimeError("váratlan")):
            with self.assertRaises(RuntimeError):
                server.start(cfg, out=io.StringIO())
        self.assertIsNone(server.zar_foglalt(cfg.path("run") / "core.lock"))


if __name__ == "__main__":
    unittest.main()
