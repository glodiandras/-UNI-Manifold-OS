"""I6 racsni (F3-DESIGN §3.6, K1): minden vault-bejáró kihagyja a `.manifold`-ot.

A `core/` és a `modulok/` minden `for …, <mappák>, … in os.walk(…)` ciklusában a `<mappák>` listát érintő utasítások (a
metszés) vagy a `core/rejtett.py`-t használják (`rejtett.metsz`, `rejtett.kihagyott`, `KIHAGYOTT_MAPPAK`, a `rejtett`-ből vett
`SKIP_DIRS`-en át is), vagy bizonyítottan minden pontos mappát kihagynak (`startswith(".")`). Az `rglob`/`glob("**")` nem metszhető: csak nem-vault fán
(staging, SDK, homokozó) engedett, a `NEM_VAULT` listán, indokkal. Új bejáró csak így kerülhet be.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from tests.helpers import REPO

HIVAS = re.compile(r"os\.walk\(|\.rglob\(|\.glob\(\s*[\"']\*\*")
REJTETT = re.compile(r"rejtett\.|metsz\(|KIHAGYOTT_MAPPAK")
PONTOS = re.compile(r"startswith\(\s*[\"']\.[\"']\s*\)")
FELOLDAS_SKIP = re.compile(r"from\s+[\w.]*feloldas\s+import[^\n]*\bSKIP_DIRS\b|^SKIP_DIRS\s*=[^\n]*\brejtett\.", re.M)

# Nem vault-bejárók (`fájl::függvény`): a bejárt fa nem a vault, ezért nem kell (és az `rglob` nem is tud) metszeni.
NEM_VAULT = {
    "core/doctor.py::_meret_szoveg": "egy próbaklón mappájának mérete (a `{tmp}/proba/<kör>` alatt)",
    "core/teljes_mentes.py::_fajlok": "a teljes mentés a gyökereit a saját kizárási szabályaival járja be (§5)",
    "modulok/cpp/proba.py::nagy_objektum": "a homokozó munkamappája (mérés)",
    "modulok/cpp/telepites.py::tbd_igazit": "a hordozható macOS SDK",
    "modulok/homokozo/program.py::_elerte_a_fajlmeret_korlatot": "a homokozó munkamappája",
    "modulok/ytdlp/__main__.py::cmd_felmeres": "a videólánc staging-fája (`{staging}`)",
    "modulok/ytdlp/src/msp/integration.py::pending_folders": "a staging-fa manifestjei",
    "modulok/ytdlp/src/msp/integration.py::status_counts": "a staging-fa manifestjei",
    "modulok/ytdlp/src/msp/pipeline.py::iter_source_dirs": "a staging-fa forrásmappái",
    "modulok/ytdlp/src/msp/validation.py::_find_orphans": "a staging-fa ellenőrzése",
}

def _metszes(fa: ast.AST, src: str, sor: int) -> str | None:
    """A `sor`-on kezdődő `for …, <mappák>, … in os.walk(…)` ciklus törzsének a `<mappák>`-at érintő utasításai (forrásként);
    None, ha a hívás nem ilyen ciklus (akkor nem is metszhető)."""
    for n in ast.walk(fa):
        if isinstance(n, ast.For) and n.iter.lineno == sor and isinstance(n.iter, ast.Call) \
                and ast.unparse(n.iter.func) == "os.walk" and isinstance(n.target, ast.Tuple) \
                and len(n.target.elts) == 3 and isinstance(n.target.elts[1], ast.Name):
            nev = n.target.elts[1].id
            return "\n".join(ast.get_source_segment(src, u) or "" for u in n.body
                             if any(isinstance(x, ast.Name) and x.id == nev for x in ast.walk(u)))
    return None


def _helyek():
    """→ [(`fájl::függvény`, sorszám, a metszés forrása vagy None, a fájl forrása)]."""
    ki = []
    for p in sorted([*(REPO / "core").rglob("*.py"), *(REPO / "modulok").rglob("*.py")]):
        if "__pycache__" in p.parts:
            continue
        src = p.read_text(encoding="utf-8")
        if not HIVAS.search(src):
            continue
        rel = p.relative_to(REPO).as_posix()
        fa = ast.parse(src)
        fv = [(n.lineno, n.end_lineno, n.name) for n in ast.walk(fa) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for i, sor in enumerate(src.splitlines(), 1):
            if HIVAS.search(sor) and not sor.lstrip().startswith("#"):
                nev = min((f for f in fv if f[0] <= i <= f[1]), key=lambda f: f[1] - f[0], default=(0, 0, "<modul>"))[2]
                ki.append((f"{rel}::{nev}", i, _metszes(fa, src, i) if "os.walk(" in sor else None, src))
    return ki


def _megfelel(metszes: str | None, src: str) -> bool:
    if not metszes:
        return False                                    # rglob / glob("**") / metszés nélküli bejárás
    if REJTETT.search(metszes) or PONTOS.search(metszes):
        return True
    return "SKIP_DIRS" in metszes and bool(FELOLDAS_SKIP.search(src))


class RejtettBejarasTest(unittest.TestCase):
    def test_minden_vault_bejaro_kihagyja_a_manifoldot(self):
        helyek = _helyek()
        self.assertGreater(len(helyek), 20)
        for kulcs, sor, ablak, src in helyek:
            with self.subTest(hely=f"{kulcs}:{sor}"):
                if kulcs in NEM_VAULT or _megfelel(ablak, src):
                    continue
                self.fail(f"{kulcs}:{sor} bejárója nem hagyja ki a `.manifold`-ot: `rejtett.metsz(…)` kell "
                          f"(vagy nem-vault fánál a NEM_VAULT listába, indokkal)")

    def test_a_nem_vault_lista_nem_avul_el(self):
        meglevo = {k for k, *_ in _helyek()}
        for kulcs in NEM_VAULT:
            with self.subTest(kulcs=kulcs):
                self.assertIn(kulcs, meglevo)

    def test_a_feloldas_es_a_binaris_naplo_a_rejtett_listat_hasznalja(self):
        from core import binaris_naplo, rejtett
        from core.index import feloldas
        self.assertIs(feloldas.SKIP_DIRS, rejtett.KIHAGYOTT_MAPPAK)
        self.assertIs(binaris_naplo.KIHAGY, rejtett.MEDIA_KIHAGYOTT_MAPPAK)
        self.assertIn(".manifold", rejtett.KIHAGYOTT_MAPPAK)
        self.assertIn(".manifold", rejtett.MEDIA_KIHAGYOTT_MAPPAK)

    def test_az_i6_nem_szukiti_a_v2_bejarasait_a_node_modules_nem_marad_ki_a_mediabol_es_a_zarolasbol(self):
        """A közös lista (`KIHAGYOTT_MAPPAK`) a `node_modules`-t is kihagyja (index, linkfeloldás, próbaklón-takarítás: mint a v2-ben);
        a bináris napló, a média-egyezés és a Kukába helyezés zárolt útjai viszont a v2 szerint járnak be (csak a `.manifold` marad ki)."""
        from core import rejtett
        self.assertEqual(rejtett.MEDIA_KIHAGYOTT_MAPPAK, rejtett.KIHAGYOTT_MAPPAK - {"node_modules"})
        mappak = [".manifold", ".git", ".obsidian", ".trash", "node_modules", "Jegyzetek"]
        self.assertEqual(rejtett.metsz(list(mappak)), ["Jegyzetek"])
        self.assertEqual(rejtett.media_metsz(list(mappak)), ["node_modules", "Jegyzetek"])
        self.assertEqual(rejtett.metsz_munkater(list(mappak)), [".git", ".obsidian", ".trash", "node_modules", "Jegyzetek"])

    def test_a_node_modules_media_a_leltarban_es_a_media_indexben_marad_a_manifold_kimarad(self):
        import tempfile
        from core import binaris_naplo
        from modulok.ytdlp import elhelyezes
        with tempfile.TemporaryDirectory() as t:
            v = Path(t)
            for rel in ("node_modules/csomag/kep.png", ".manifold/var/tmp/klon/kep.png", ".git/kep.png", "Jegyzetek/kep.png",
                        "node_modules/csomag/film.mp4", ".manifold/var/tmp/klon/klon.mp4", "Jegyzetek/jegyzet.mp4"):
                (v / rel).parent.mkdir(parents=True, exist_ok=True)
                (v / rel).write_bytes(b"x")
            self.assertIn("node_modules/csomag/kep.png", binaris_naplo.leltar(v))
            self.assertNotIn(".manifold/var/tmp/klon/kep.png", binaris_naplo.leltar(v))
            self.assertNotIn(".git/kep.png", binaris_naplo.leltar(v))
            index = elhelyezes.media_index(v)
            self.assertEqual(index.get("film.mp4"), "node_modules/csomag/film.mp4")
            self.assertNotIn("klon.mp4", index)
            self.assertIn("jegyzet.mp4", index)

    def test_az_ellenor_maga(self):
        def m(kod: str, elotte: str = "") -> bool:
            src = elotte + "def f(v):\n" + "".join(f"    {s}\n" for s in kod.splitlines())
            return _megfelel(_metszes(ast.parse(src), src, elotte.count("\n") + 2), src)
        self.assertTrue(m("for d, m, f in os.walk(v):\n    rejtett.metsz(m)"))
        self.assertTrue(m("for d, m, f in os.walk(v):\n    m[:] = [x for x in m if not x.startswith('.')]"))
        self.assertTrue(m("for d, m, f in os.walk(v):\n    for x in list(m):\n        if rejtett.kihagyott(x):\n"
                          "            m.remove(x)"))
        self.assertTrue(m("for d, m, f in os.walk(v):\n    m[:] = [x for x in m if x not in SKIP_DIRS]",
                          "from .index.feloldas import SKIP_DIRS, Feloldo\n"))
        self.assertTrue(m("for d, m, f in os.walk(v):\n    m[:] = [x for x in m if x not in SKIP_DIRS]",
                          "SKIP_DIRS = set(rejtett.KIHAGYOTT_MAPPAK)\n"))
        self.assertFalse(m("for d, m, f in os.walk(v):\n    m[:] = [x for x in m if x not in SKIP_DIRS]",
                           'SKIP_DIRS = {".obsidian", ".git"}\n'))
        self.assertFalse(m("for d, m, f in os.walk(v):\n    m[:] = [x for x in m if x not in KIHAGY]"))
        # a fájlnév-szűrő (`f.startswith(".")`) nem mappa-metszés
        self.assertFalse(m("for d, m, f in os.walk(v):\n    m[:] = [x for x in m if x != 'a']\n"
                           "    k = [y for y in f if not y.startswith('.')]"))
        self.assertFalse(m("for d, m, f in os.walk(v):\n    pass"))
        self.assertFalse(_megfelel(None, ""))                      # rglob


if __name__ == "__main__":
    unittest.main()
