"""A felület (C07) a Python-tesztkörben: a vitest-tesztek, a lefordított csomag offline-vizsgálata és a
héj önellenőrzése a valódi felülettel — álgyökéren (a valódi vault és var/ nélkül).

A vitest-füstpróba csak akkor fut, ha az `app/node_modules` megvan (`bin/mos app install`; a teljes készlet a `bin/mos app
test`); a `dist`-vizsgálat és a héj-próba csak lefordított csomaggal (`bin/mos app build`).
"""
import json
import re
import shutil
import subprocess
import unittest

from tests import csak_darwin
from tests.helpers import REPO, alg_gyoker, env, tmpdir
from tests.test_mos_es_shell import APP, core_indito_szkript_start

APPDIR = REPO / "app"
DIST = APPDIR / "dist"
NODE = REPO / "runtime" / "node" / "bin" / "node"


@unittest.skipUnless((APPDIR / "node_modules").is_dir() and NODE.exists(), "nincs app/node_modules vagy Node")
class VitestTeszt(unittest.TestCase):
    def test_vitest_fustproba(self):
        """A Python-kör csak azt bizonyítja, hogy a vitest-lánc (Node, node_modules, konfig) indul és egy gyors fájlt lefuttat.
        A TELJES vitest-készlet a `bin/mos app test` — külön kapu —; a beágyazott teljes futás (T008) kétszer futtatta a
        ~1150 tesztet, és terhelés alatt a 300 s-os időkorlát miatt is bukott."""
        p = subprocess.run([str(NODE), str(APPDIR / "node_modules" / "vitest" / "vitest.mjs"), "run", "tests/fa-segedek.test.ts",
                            "tests/fuzzy.test.ts"], cwd=APPDIR, capture_output=True, text=True, timeout=120,
                           env=env(PATH=f"{NODE.parent}:/usr/bin:/bin", CI="1"))
        self.assertEqual(p.returncode, 0, p.stdout[-4000:] + p.stderr[-2000:])
        self.assertRegex(p.stdout, r"Tests\s+\d+ passed")


@unittest.skipUnless((DIST / "index.html").is_file(), "nincs lefordított app/dist")
class DistTeszt(unittest.TestCase):
    def test_nincs_kulso_betoltes(self):
        """A csomag semmit nem tölt be hálózatról (D3): a HTML-ben csak saját út, a CSS-ben nincs távoli url(),
        a JS-ben nincs távoli import, fetch vagy WebSocket-cím."""
        html = (DIST / "index.html").read_text(encoding="utf-8")
        for attr in re.findall(r'(?:src|href)="([^"]+)"', html):
            self.assertTrue(attr.startswith("/") and not attr.startswith("//"), attr)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("default-src 'self'", html)
        for css in DIST.rglob("*.css"):
            self.assertNotRegex(css.read_text(encoding="utf-8"), r"url\(\s*['\"]?(https?:)?//", css.name)
        for js in DIST.rglob("*.js"):
            t = js.read_text(encoding="utf-8")
            self.assertNotRegex(t, r"import\(\s*['\"`]https?://", js.name)
            self.assertNotRegex(t, r"fetch\(\s*['\"`]https?://", js.name)
            self.assertNotRegex(t, r"['\"`]wss?://(?!\$\{)", js.name)


@unittest.skipUnless(APP.exists() and (DIST / "index.html").is_file(), "nincs Manifold.app vagy app/dist")
@csak_darwin("a Mach-O Manifold.app héj Linuxon nem fut")
class HejFelulettelTeszt(unittest.TestCase):
    def test_selftest_a_felulet_kesz_jelet_ad(self):
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start())
            shutil.copytree(DIST, root / "app" / "dist")
            p = subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), "--selftest"], capture_output=True,
                               text=True, timeout=60, env=env(MOS_ROOT=str(root), home=False))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK: a felület kész", p.stdout)

    def test_selftest_kilepes_a_szerkesztett_szoveg_a_lemezen(self):
        """C29.7b (T033): a valódi kilépési út. A felület a mentett állapotból megnyitja a jegyzetet; a héj a szerkesztőbe szöveget
        ír (mint a gépelés), 200 ms múlva `NSApp.terminate` — az 1 s-os autosave még nem futott: a szöveget a `window.manifold.mentes()`
        mentheti csak el, mielőtt a héj leállítja a core-t. A kilépési kód 0, a fájl a lemezen a jellel."""
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start())
            shutil.copytree(DIST, root / "app" / "dist")
            vault = root.parent / "Manifold"
            (vault / ".obsidian").mkdir()
            (vault / "Proba.md").write_text("# Kilépés próba\n\nszöveg\n", encoding="utf-8")
            allapot = {"verzio": 1, "tema": "vilagos", "munkaterulet": {
                "gyoker": {"tipus": "panel", "id": "p1", "fulek": [{"id": "f1", "ut": "Proba.md"}], "aktiv": "f1"},
                "aktivPanelId": "p1"}}
            (root / "var" / "state" / "felulet.json").write_text(json.dumps(allapot), encoding="utf-8")
            jel = "KILEPES-JEL-7f3a "
            p = subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), "--selftest=kilepes"], capture_output=True,
                               text=True, timeout=120, env=env(MOS_ROOT=str(root), home=False, MOS_SELFTEST_JEL=jel))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK: a kilépés", p.stdout)
            self.assertEqual((vault / "Proba.md").read_text(encoding="utf-8"), jel + "# Kilépés próba\n\nszöveg\n")
            self.assertFalse(list(vault.rglob("*.manifold-tmp")))

    def _proba_gyoker(self, t, szoveg: str, extra: dict[str, str] | None = None):
        root = alg_gyoker(t, core_indito_szkript_start())
        shutil.copytree(DIST, root / "app" / "dist")
        vault = root.parent / "Manifold"
        (vault / ".obsidian").mkdir()
        (vault / "Proba.md").write_text(szoveg, encoding="utf-8")
        for ut, tartalom in (extra or {}).items():
            (vault / ut).write_text(tartalom, encoding="utf-8")
        allapot = {"verzio": 1, "tema": "vilagos", "munkaterulet": {
            "gyoker": {"tipus": "panel", "id": "p1", "fulek": [{"id": "f1", "ut": "Proba.md"}], "aktiv": "f1"},
            "aktivPanelId": "p1"}}
        (root / "var" / "state" / "felulet.json").write_text(json.dumps(allapot), encoding="utf-8")
        return root, vault

    def test_selftest_szerkesztes_megnyitas_beagyazas_gepeles_mentes_link(self):
        """C33 (3. pont): a szkriptelt forgatókönyv a valódi WebKitben — a mentett állapotból megnyílt jegyzet, a `![[Cel]]`
        beágyazás a core feloldásával, 20 beszúrás a következő képkockáig mérve, az automatikus mentés a core API-ján
        visszaolvasva, és a ⌘-kattintás a kirajzolt `[[Cel|celhivatkozas]]` linkre (a cél megnyílik). A lemezen a beírt szöveg."""
        with tmpdir() as t:
            root, vault = self._proba_gyoker(t, "# Próba\n\nPROBA-JEL szöveg\n\nLásd: [[Cel|celhivatkozas]]\n\n![[Cel]]\n\nvége\n",
                                             {"Cel.md": "# Cél\n\nCEL-JEL a cél tartalma\n"})
            jel = "SZERKESZTES-JEL-41c2"
            p = subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), "--selftest=szerkesztes"], capture_output=True,
                               text=True, timeout=180, env=env(MOS_ROOT=str(root), home=False, MOS_SELFTEST_JEL=jel))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK: szerkesztés", p.stdout)
            self.assertRegex(p.stdout, r"SELFTEST IDŐ: a felület kész \d+ ms")
            meres = json.loads(re.search(r"SELFTEST OK: szerkesztés: (\{.*\})", p.stdout).group(1))
            for kulcs in ("megnyitas_ms", "beagyazas_ms", "gepeles_p50_ms", "gepeles_p95_ms", "mentes_ms", "link_ms"):
                self.assertIn(kulcs, meres)
            print(f"\n[selftest szerkesztés] {meres}", flush=True)
            szoveg = (vault / "Proba.md").read_text(encoding="utf-8")
            self.assertIn(jel, szoveg)
            self.assertIn("[[Cel|celhivatkozas]]", szoveg)
            self.assertEqual((vault / "Cel.md").read_text(encoding="utf-8"), "# Cél\n\nCEL-JEL a cél tartalma\n")
            self.assertFalse(list(vault.rglob("*.manifold-tmp")))

    def test_selftest_lecsatolas_ment_es_rendezetten_leall(self):
        """C33 (2. pont, M5; a K03 gépi része): a kötet lecsatolásának értesítésére (`NSWorkspace.willUnmountNotification` a gyökér
        kötetére) a héj a rendezett kilépés útját járja: a felület ment (a még nem autosave-elt gépelést is), a core leáll."""
        with tmpdir() as t:
            root, vault = self._proba_gyoker(t, "# Lecsatolás próba\n\nszöveg\n")
            jel = "LECSATOLAS-JEL-9b0e "
            p = subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), "--selftest=lecsatolas"], capture_output=True,
                               text=True, timeout=120, env=env(MOS_ROOT=str(root), home=False, MOS_SELFTEST_JEL=jel))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK: a kötet lecsatolásának", p.stdout)
            self.assertEqual((vault / "Proba.md").read_text(encoding="utf-8"), jel + "# Lecsatolás próba\n\nszöveg\n")


if __name__ == "__main__":
    unittest.main()
