"""S1: valódi WKWebView, szintetikus vault, szűk natív ablak; a megjelenítés nem írhatja át a jegyzetet."""
import json
import re
import shutil
import subprocess
import unittest

from tests import csak_darwin
from tests.helpers import REPO, alg_gyoker, env, tmpdir
from tests.test_mos_es_shell import APP, core_indito_szkript_start


@csak_darwin("a WKWebView kapu macOS-t igényel")
@unittest.skipUnless(APP.exists() and (REPO / "app/dist/index.html").is_file(), "nincs Manifold.app vagy app/dist")
class MunkafeluletTest(unittest.TestCase):
    def test_cim_nezetek_popup_temak_es_szelesseg(self):
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start())
            shutil.copytree(REPO / "app/dist", root / "app/dist")
            vault = root.parent / "Manifold"
            (vault / ".obsidian").mkdir()
            szoveg = '---\ntags: [synthetic]\nlong_property_name: "Keep this exact value"\n---\n# Proba\n\nSynthetic body.\n\n# Section\n\nKeep this section.\n'
            note = vault / "Proba.md"
            note.write_text(szoveg, encoding="utf-8")
            (vault / ("Long-synthetic-" + "name-" * 18 + ".canvas")).write_text('{"nodes": [], "edges": []}', encoding="utf-8")
            allapot = {"verzio": 1, "tema": "vilagos", "csend": {"be": False}, "kenyelmiVerzio": 1,
                "oldalsav": {"nyitva": True, "szelesseg": 264, "nezet": "fajlok"},
                "tulajdonsagok": {"nyitva": True}, "jobbPanel": {"nyitva": False}, "munkaterulet": {
                "gyoker": {"tipus": "panel", "id": "p1", "fulek": [{"id": "f1", "ut": "Proba.md"}], "aktiv": "f1"}, "aktivPanelId": "p1"}}
            (root / "var/state/felulet.json").write_text(json.dumps(allapot), encoding="utf-8")
            p = subprocess.run([str(APP / "Contents/MacOS/Manifold"), "--selftest=munkafelulet"], capture_output=True,
                               text=True, timeout=150, env=env(MOS_ROOT=str(root), home=False))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            adat = json.loads(re.search(r"SELFTEST OK: munkafelület: (\{.*\})", p.stdout).group(1))
            self.assertEqual([a["tema"] for a in adat["temak"]], ["vilagos", "sotet", "rendszer"])
            for k in ("elo_cim", "forras", "olvaso_cim", "fa_jelveny", "tulajdonsagok"):
                self.assertTrue(adat[k], k)
            self.assertNotEqual(adat["temak"][0]["hatter"], adat["temak"][1]["hatter"])
            self.assertEqual(note.read_bytes(), szoveg.encode())
            self.assertFalse(list(vault.rglob("*.manifold-tmp")))
            print("\n[S1 WebKit] " + json.dumps(adat, ensure_ascii=False), flush=True)
