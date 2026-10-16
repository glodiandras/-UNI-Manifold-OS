"""F5 coreless launcher protocol and starter workspace, synthetic files only."""
import fcntl
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from core import config, indito, munkater_futo, termek_beallitasok as b, workspace
from core.utvonalak import HttpError
from tests.helpers import REPO, env, tmpdir
from tests.multi_user import termek_telepites, termek_cfg


class InditoTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.alap = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_SETTINGS": ""}, munkater=False)
        self.v = Path(self.t.name) / "My Notes"

    def ker(self, muvelet, **adat):
        return indito.muvelet({"muvelet": muvelet, **adat}, self.alap)

    def letrehoz(self):
        return self.ker("letrehoz", vault=str(self.v), uj_mappa=True, elfogad=True)["munkater"]

    def test_elso_inditas_ures_lista_es_mappa_elonezet_nem_ir(self):
        self.assertEqual(self.ker("lista")["munkaterek"], [])
        r = self.ker("felmer", vault=str(self.v), uj_mappa=True)
        self.assertEqual(r["felmeres"]["eredmeny"], "mehet")
        self.assertTrue(r["valtozasok"])
        self.assertFalse(self.v.exists())

    def test_megerosites_nelkul_semmit_nem_hoz_letre(self):
        with self.assertRaises(HttpError):
            self.ker("letrehoz", vault=str(self.v), uj_mappa=True)
        self.assertFalse(self.v.exists())

    def test_letrehoz_megnyit_lista_elfelejt_nem_torol(self):
        w = self.letrehoz()
        self.assertEqual(self.ker("megnyit", vault=str(self.v))["munkater"], w)
        r = self.ker("lista")
        self.assertEqual(r["utolso"], w["id"])
        self.assertTrue(r["munkaterek"][0]["elerheto"])
        self.ker("elfelejt", id=w["id"])
        self.assertEqual(self.ker("lista")["munkaterek"], [])
        self.assertTrue((self.v / ".manifold/workspace.toml").exists())

    def test_obsidian_megnyitas_nem_irja_at_a_jegyzetet(self):
        (self.v / ".obsidian").mkdir(parents=True)
        p = self.v / "Original.md"
        p.write_bytes(b"# Original\r\n\r\nKeep me.\r\n")
        eredeti = p.read_bytes()
        self.ker("letrehoz", vault=str(self.v), elfogad=True)
        self.assertEqual(p.read_bytes(), eredeti)

    def test_elveszett_recent_megmarad_es_inditasi_beallitas(self):
        self.letrehoz()
        cfg = termek_cfg(self.root, self.home, self.v)
        b.ir(cfg, b.olvas(cfg)["rev"], {"altalanos": {"inditas": "valaszto"}})
        self.assertEqual(self.ker("lista")["inditas"], "valaszto")
        self.v.rename(self.v.with_name("Moved"))
        self.assertFalse(self.ker("lista")["munkaterek"][0]["elerheto"])

    def test_demo_ujranyitas_nem_ir_felul_es_torolt_jegyzetet_sem_hoz_vissza(self):
        w = self.ker("demo")["munkater"]
        v = Path(w["vault"])
        self.assertEqual(len(list(v.glob("*.md"))), 3)
        (v / "Welcome.md").write_text("User changed this")
        (v / "Connected ideas.md").unlink()
        self.assertEqual(self.ker("demo")["munkater"], w)
        self.assertEqual((v / "Welcome.md").read_text(), "User changed this")
        self.assertFalse((v / "Connected ideas.md").exists())

    def test_core_bejelentes_titok_nelkul_es_csak_elo_zarral(self):
        self.letrehoz()
        cfg = termek_cfg(self.root, self.home, self.v)
        cfg.path("run").mkdir(parents=True, exist_ok=True)
        with open(cfg.path("run") / "core.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            munkater_futo.bejelent(cfg, 12345)
            r = self.ker("lista")["munkaterek"][0]
            self.assertTrue(r["fut"])
            self.assertEqual(r["pid"], os.getpid())
            p = cfg.path("install_run") / "cores" / f"{cfg.workspace_id}.json"
            self.assertNotIn("titok", p.read_text())
        self.assertFalse(self.ker("lista")["munkaterek"][0]["fut"])
        munkater_futo.elfelejt(cfg)
        self.assertFalse(p.exists())

    def test_valodi_cli_ndjson_es_hibas_keres_angol_hiba(self):
        e = env(MOS_ROOT=str(self.root), HOME=str(self.home), PYTHONPATH=str(REPO))
        for adat, rc in (({"muvelet": "lista"}, 0), ({"muvelet": "bad"}, 1)):
            p = subprocess.run([sys.executable, "-B", "-m", "core.indito"], input=json.dumps(adat), text=True,
                               capture_output=True, env=e, cwd=REPO, timeout=30)
            self.assertEqual(p.returncode, rc, p.stderr)
            r = json.loads(p.stdout.splitlines()[-1])
            self.assertEqual(r["ok"], rc == 0)
            if rc:
                self.assertIn("workspace request", r["hiba"])


if __name__ == "__main__":
    unittest.main()
