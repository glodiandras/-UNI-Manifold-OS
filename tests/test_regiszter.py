"""F3-DESIGN §3.5: a gép munkatér-regisztere (`{install}/workspaces.json`). Csak index: atomi írás a `workspaces.lock` alatt, a
sérült fájl félre kerül (nem törlődik), az `elfelejt` fájlt nem töröl, párhuzamos írók nem veszítenek bejegyzést, és a
`config.load` ebből (csak olvasva) veszi az állapot helyét."""
from __future__ import annotations

import json
import os
import threading
import unittest
from pathlib import Path

from core import config, workspace
from tests.fresh_install import termek_alap, termek_cfg
from tests.helpers import tmpdir

A, B = "a" * 32, "b" * 32


class RegiszterTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.install = Path(self._t.name) / "install"
        self.reg = workspace.Regiszter(self.install)

    def test_ures_regiszter(self):
        self.assertEqual(self.reg.olvas(), {"formatum": 1, "utolso": None, "munkaterek": {}})
        self.assertFalse((self.install / "workspaces.json").exists())       # olvasás nem hoz létre semmit

    def test_felvesz_frissit_elfelejt(self):
        self.reg.felvesz(id=A, vault="/x/A", nev="A", megnyitva="2026-01-01T00:00:00")
        self.reg.felvesz(id=B, vault="/x/B", nev="B", megnyitva="2026-02-01T00:00:00")
        r = json.loads((self.install / "workspaces.json").read_text(encoding="utf-8"))
        self.assertEqual((r["formatum"], r["utolso"], sorted(r["munkaterek"])), (1, B, [A, B]))
        self.assertEqual(self.reg.frissit(A, nev="Á")["vault"], "/x/A")    # összefésül, nem ír felül mást
        self.assertEqual(self.reg.felvesz(id=A, allapot="vault")["nev"], "Á")
        self.assertEqual(self.reg.olvas()["utolso"], A)
        with self.assertRaises(KeyError):
            self.reg.frissit("c" * 32, nev="x")
        self.assertTrue(self.reg.elfelejt(A))
        self.assertFalse(self.reg.elfelejt(A))
        self.assertEqual(self.reg.olvas()["utolso"], B)                    # a legutóbb megnyitott marad a legutóbbi
        self.assertEqual(sorted(p.name for p in self.install.iterdir()), ["run", "workspaces.json"])
        self.assertEqual(os.listdir(self.install / "run"), ["workspaces.lock"])

    def test_hibas_azonosito_tilos(self):
        for i in (None, "x", "A" * 32, "../" + "a" * 29):
            with self.assertRaises(ValueError):
                self.reg.felvesz(id=i, vault="/x")
        self.assertFalse((self.install / "workspaces.json").exists())

    def test_serult_fajl_felre_kerul_nem_torlodik(self):
        self.install.mkdir()
        (self.install / "workspaces.json").write_text("{ez nem json", encoding="utf-8")
        self.assertEqual(self.reg.olvas()["munkaterek"], {})
        self.reg.felvesz(id=A, vault="/x/A")
        felre = [p for p in self.install.iterdir() if p.name.startswith("workspaces.json.serult-")]
        self.assertEqual(len(felre), 1)
        self.assertEqual(felre[0].read_text(encoding="utf-8"), "{ez nem json")
        self.assertEqual(list(self.reg.olvas()["munkaterek"]), [A])

    def test_parhuzamos_irok_nem_veszitenek_bejegyzest(self):
        idk = [f"{i:032x}" for i in range(24)]
        hibak = []

        def ir(i):
            try:
                workspace.Regiszter(self.install).felvesz(id=i, vault=f"/x/{i}")
            except Exception as e:  # noqa: BLE001
                hibak.append(e)
        szalak = [threading.Thread(target=ir, args=(i,)) for i in idk]
        for s in szalak:
            s.start()
        for s in szalak:
            s.join()
        self.assertEqual(hibak, [])
        self.assertEqual(sorted(self.reg.olvas()["munkaterek"]), idk)

    def test_keres_kanonikus_es_azonossag_szerint(self):
        v = Path(self._t.name) / "Vault"
        v.mkdir()
        self.reg.felvesz(id=A, vault=str(v), kanonikus=workspace.kanonikus(v))
        self.assertEqual(self.reg.keres(v)[0], A)
        link = Path(self._t.name) / "link"
        link.symlink_to(v)
        self.assertEqual(self.reg.keres(link)[0], A)
        masik = Path(self._t.name) / "Masik"
        masik.mkdir()
        self.assertIsNone(self.reg.keres(masik))


class RegiszterKonfigTest(unittest.TestCase):
    def test_a_config_load_a_regiszterbol_olvassa_az_allapot_helyet(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        root, home, alap = termek_alap(t.name)
        v = Path(t.name) / "V"
        (v / ".manifold").mkdir(parents=True)
        (v / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{A}"\n', encoding="utf-8")
        install = alap.path("install")
        reg = workspace.Regiszter(install)
        reg.felvesz(id=A, vault=str(v), allapot="vault")
        self.assertEqual(termek_cfg(root, home, v).path("var"), v / ".manifold" / "var")
        reg.frissit(A, allapot="telepites")
        cfg = termek_cfg(root, home, v)
        self.assertEqual(cfg.path("var"), install / "workspaces" / A / "var")
        self.assertEqual(config.load({"MOS_ROOT": str(root), "HOME": str(home)}, munkater=False).path("install"), install)
        reg.elfelejt(A)
        self.assertEqual(termek_cfg(root, home, v).path("var"), v / ".manifold" / "var")
        self.assertTrue((v / ".manifold" / "workspace.toml").is_file())   # az elfelejtés fájlt nem töröl


if __name__ == "__main__":
    unittest.main()
