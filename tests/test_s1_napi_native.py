"""S1 napi must: developer WKWebView + valódi core, kizárólag szintetikus root/vault/backup.

Nem screenshot-/release-audit: Canvas task byte/save/Undo/Redo és Bases List négy fogyasztója.
"""
import json
import re
import shutil
import subprocess
import unittest

from tests import csak_darwin
from tests.helpers import API_TITOK, REPO, alg_gyoker, env, tmpdir
from tests.test_mos_es_shell import APP, core_indito_szkript_start


def _fixture(root):
    vault = root.parent / "Manifold"
    (vault / ".obsidian").mkdir()
    (vault / "Items").mkdir()
    fajlok = {
        "Items/Alpha.md": '---\nMarker: ALPHA-ROW-S1\n---\n# Alpha\n\nSynthetic alpha.\n',
        "Items/Beta.md": '---\nMarker: BETA-ROW-S1\n---\n# Beta\n\nSynthetic beta.\n',
        "List.base": 'filters: file.inFolder("Items") && file.ext == "md"\nviews:\n  - type: list\n    name: List\n    order: [file.name, Marker]\n    indentProperties: true\n',
        "Host.md": '# Host\n\n![[List.base#List]]\n\nUnchanged synthetic host.\n',
    }
    canvas = {
        "unknown_root": {"unicode": "ő—😀", "keep": [1, False, None]},
        "nodes": [
            {"id": "task", "type": "text", "x": 0, "y": 0, "width": 280, "height": 180,
             "text": "- [ ] TASK-S1\n\nKeep this line.\n", "unknown_node": {"keep": True}},
            {"id": "base", "type": "file", "x": 360, "y": 0, "width": 600, "height": 340,
             "file": "List.base", "subpath": "#List"},
        ],
        "edges": [],
    }
    fajlok["Board.canvas"] = json.dumps(canvas, ensure_ascii=False, indent=2) + "\n"
    eredeti = {}
    for ut, text in fajlok.items():
        # A normál dokumentum/foltozó út a CRLF-et és az ismeretlen JSON-mezőket is köteles megőrizni.
        adat = text.replace("\n", "\r\n").encode("utf-8")
        (vault / ut).write_bytes(adat)
        eredeti[ut] = adat
    allapot = {"verzio": 1, "tema": "vilagos", "csend": {"be": False}, "jobbPanel": {"nyitva": False}, "munkaterulet": {
        "gyoker": {"tipus": "panel", "id": "p1", "fulek": [
            {"id": "canvas-s1", "ut": "Board.canvas"},
            {"id": "base-s1", "ut": "List.base"},
            {"id": "host-s1", "ut": "Host.md", "nezet": {"mod": "elo"}},
        ], "aktiv": "canvas-s1"}, "aktivPanelId": "p1"}}
    (root / "var/state/felulet.json").write_text(json.dumps(allapot), encoding="utf-8")
    return vault, eredeti


@csak_darwin("a valódi WKWebView napi kapu macOS-t igényel")
@unittest.skipUnless(APP.exists() and (REPO / "app/dist/index.html").is_file(), "nincs Manifold.app vagy app/dist")
class NapiNativeTest(unittest.TestCase):
    def test_canvas_task_undo_zoom_es_list_negy_fogyasztoja(self):
        metadata = json.loads((APP / "Contents/Resources/epites.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata.get("hej_valtozat"), "fejlesztoi", "A napi-integracio kapu friss developer héjat igényel.")
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start(), preset=None)
            shutil.copytree(REPO / "app/dist", root / "app/dist")
            vault, eredeti = _fixture(root)
            p = subprocess.run([str(APP / "Contents/MacOS/Manifold"), "--selftest=napi-integracio"], capture_output=True,
                               text=True, timeout=180, env=env(MOS_ROOT=str(root), home=False))
            # A privát API-argumentum sem sikeres, sem hibás naplóban nem jelenhet meg.
            reszlet = (p.stdout + p.stderr).replace(API_TITOK, "[REDACTED]")
            self.assertEqual(p.returncode, 0, reszlet)
            m = re.search(r"SELFTEST OK: napi-integracio: (\{.*\})", p.stdout)
            self.assertIsNotNone(m, reszlet)
            adat = json.loads(m.group(1))
            for k in ("canvas_task", "undo", "redo", "visszaallitas"):
                self.assertTrue(adat[k], k)
            self.assertTrue(adat["kijeloles_fit"]["kozep"])
            self.assertTrue(adat["kijeloles_fit"]["belefer"])
            self.assertGreater(adat["kijeloles_fit"]["z"], 0)
            self.assertLessEqual(adat["kijeloles_fit"]["z"], 2.001)
            self.assertEqual([s["hely"] for s in adat["lista"]], ["canvas", "fajl", "LP", "Reading"])
            for s in adat["lista"]:
                self.assertEqual(s["sorok"], 2, s["hely"])
                self.assertEqual(s["utak"], ["Items/Alpha.md", "Items/Beta.md"], s["hely"])
            for ut, vart in eredeti.items():
                self.assertEqual((vault / ut).read_bytes(), vart, ut)
            self.assertFalse(list(vault.rglob("*.manifold-tmp")))
            print("\n[S1 napi WebKit] " + json.dumps(adat, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    unittest.main()
