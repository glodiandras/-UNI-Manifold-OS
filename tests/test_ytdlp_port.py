"""C20a: a legacy `modulok/ytdlp` portja — a másolat saját (pytest) tesztkészlete hálózat nélkül, és a port dokumentált eltérései.

A másolt `msp` azonosítói angolok (a port másolat; 12. döntés), a készletét a legacy pytest-tesztjei adják; itt a `bin/mos test` kapuja
lefuttatja őket alfolyamatban, és őrzi, amit a port megváltoztatott: nincs PATH- és imageio-ffmpeg-tartalék, az integráció és az átirat
kikapcsolt, nincs home-beli út a kódban."""
import dataclasses
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO, env, tmpdir

MODUL = REPO / "modulok" / "ytdlp"
SRC = MODUL / "src"
MIN_TESZT = 373


class PytestKeszletTeszt(unittest.TestCase):
    def test_a_legacy_pytest_keszlet_halozat_nelkul_zold(self):
        """A másolat tesztjei (373): hamis letöltővel, a hálózathoz nem nyúlnak; a port módosításai nem törték el őket."""
        with tmpdir() as t:
            e = env(MOS_ROOT=str(REPO), HOME=t) | {"PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": t}
            p = subprocess.run([sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", "-q",
                                "--no-header"], cwd=MODUL, env=e, capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stdout[-3000:] + p.stderr[-2000:])
        m = re.search(r"(\d+) passed", p.stdout)
        self.assertIsNotNone(m, p.stdout[-500:])
        self.assertGreaterEqual(int(m.group(1)), MIN_TESZT)
        self.assertNotRegex(p.stdout, r"\d+ (failed|error|skipped)")
        self.assertFalse((MODUL / ".pytest_cache").exists())


def _msp():
    """A másolt `msp` csomag (a `modulok/ytdlp/src` az import-útra)."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    import msp.config as konfig
    import msp.downloader as letolto
    return konfig, letolto


class EszkozFeloldasTeszt(unittest.TestCase):
    """Az ffmpeg és a node feloldása: csak a runtime, nincs PATH- és imageio-tartalék, nincs home-beli út."""

    def setUp(self):
        self.konfig, self.letolto = _msp()
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.os = Path(self._t.name) / "os"
        self.projekt = self.os / "modulok" / "ytdlp"
        self.projekt.mkdir(parents=True)
        (self.projekt / "config").mkdir()
        (self.projekt / "config" / "config.yaml").write_text((MODUL / "config" / "config.yaml").read_text(encoding="utf-8"),
                                                              encoding="utf-8")
        self.cfg = self.konfig.Config.load(project_root=self.projekt)
        self._regi = {k: os.environ.pop(k, None) for k in ("MOS_FFMPEG", "MOS_NODE")}
        self.addCleanup(self._visszaallit)

    def _visszaallit(self):
        for k, v in self._regi.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _futtathato(self, ut: Path) -> Path:
        ut.parent.mkdir(parents=True, exist_ok=True)
        ut.write_text("#!/bin/sh\nexit 0\n")
        ut.chmod(ut.stat().st_mode | stat.S_IXUSR)
        return ut

    def test_az_ffmpeg_csak_a_kapott_utbol_jon(self):
        """Javító 3 (A3-17): `auto` = nincs ffmpeg, a `<os>/runtime` keresése sincs (az ellenőrzött és a futtatott bináris ugyanaz);
        a lánc a `[utak] ffmpeg`-et adja át (`lanc.msp_konfig`)."""
        ff = self._futtathato(self.os / "runtime" / "ffmpeg" / "ffmpeg")
        self.assertIsNone(self.letolto.resolve_ffmpeg(self.cfg), "auto: a runtime-ban álló ffmpeg-et sem keresi")
        kapott = dataclasses.replace(self.cfg, ytdlp=dataclasses.replace(self.cfg.ytdlp, ffmpeg_location=str(ff)))
        self.assertEqual(self.letolto.resolve_ffmpeg(kapott), str(ff))

    def test_a_path_es_a_home_beli_ffmpeg_nem_szamit(self):
        """A Save4K-symlinkes `~/.local/bin/ffmpeg` és a PATH-os ffmpeg tiltott: a port nem veszi észre őket."""
        pathos = self._futtathato(Path(self._t.name) / "path" / "ffmpeg")
        regi = os.environ["PATH"]
        os.environ["PATH"] = f"{pathos.parent}{os.pathsep}{regi}"
        self.addCleanup(os.environ.__setitem__, "PATH", regi)
        self.assertIsNone(self.letolto.resolve_ffmpeg(self.cfg))

    def test_a_mos_ffmpeg_env_nem_er_semmit_a_hianyzo_kapott_ut_hiba(self):
        egyedi = self._futtathato(Path(self._t.name) / "egyedi" / "ffmpeg")
        os.environ["MOS_FFMPEG"] = str(egyedi)
        self.assertIsNone(self.letolto.resolve_ffmpeg(self.cfg), "a környezeti ffmpeg nem használható (A3-17)")
        hianyzo = dataclasses.replace(self.cfg, ytdlp=dataclasses.replace(self.cfg.ytdlp, ffmpeg_location=str(egyedi.parent / "nincs")))
        with self.assertRaises(self.letolto.DependencyError):
            self.letolto.resolve_ffmpeg(hianyzo)

    def test_node_csak_a_kapott_utbol_jon(self):
        """Javító 3 (A3-18): nincs `MOS_NODE`, nincs runtime-keresés, nincs PATH; a lánc a `[utak] node`-ot adja át."""
        node = self._futtathato(self.os / "runtime" / "node" / "bin" / "node")
        self.assertIsNone(self.letolto._js_runtime_path("node", self.cfg))
        os.environ["MOS_NODE"] = str(self._futtathato(Path(self._t.name) / "m" / "node"))
        self.addCleanup(os.environ.pop, "MOS_NODE", None)
        self.assertIsNone(self.letolto._js_runtime_path("node", self.cfg))
        kapott = dataclasses.replace(self.cfg, ytdlp=dataclasses.replace(self.cfg.ytdlp, node_location=str(node)))
        self.assertEqual(self.letolto._js_runtime_path("node", kapott), str(node))
        self.assertEqual(self.letolto.resolve_js_runtime(kapott), "node")
        self.assertIsNone(self.letolto._js_runtime_path("deno", kapott), "a deno nincs pinelve")

    def test_az_alap_konfig_a_2_0_beallitasait_adja(self):
        self.assertFalse(self.cfg.integration.enabled)
        self.assertEqual(self.cfg.integration.command, ())
        self.assertFalse(self.cfg.transcript.enabled, "az átirat a C20b-é")
        self.assertEqual(self.cfg.ytdlp.ffmpeg_location, "auto")
        self.assertEqual(self.cfg.output_root.name, "staging")


class ForraskodTeszt(unittest.TestCase):
    """A port kódjában nincs a tiltott út vagy tartalék (a doctor és a CLAUDE.md §4 szabálya)."""

    @staticmethod
    def _kod_szovegek(fajl: Path):
        """Az AST-ből: az importált modulnevek és a docstringen kívüli szöveg-konstansok (a megjegyzés és a docstring szabad)."""
        import ast
        fa = ast.parse(fajl.read_text(encoding="utf-8"))
        docstring = set()
        for csomopont in ast.walk(fa):
            if isinstance(csomopont, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and csomopont.body:
                elso = csomopont.body[0]
                if isinstance(elso, ast.Expr) and isinstance(elso.value, ast.Constant) and isinstance(elso.value.value, str):
                    docstring.add(id(elso.value))
        modulok, szovegek = [], []
        for csomopont in ast.walk(fa):
            if isinstance(csomopont, ast.Import):
                modulok += [a.name for a in csomopont.names]
            elif isinstance(csomopont, ast.ImportFrom):
                modulok.append(csomopont.module or "")
            elif isinstance(csomopont, ast.Constant) and isinstance(csomopont.value, str) and id(csomopont) not in docstring:
                szovegek.append(csomopont.value)
        return modulok, szovegek

    def test_nincs_imageio_ffmpeg_import_es_nincs_home_beli_ut(self):
        for fajl in SRC.rglob("*.py"):
            modulok, szovegek = self._kod_szovegek(fajl)
            self.assertNotIn("imageio_ffmpeg", modulok, str(fajl))
            for sz in szovegek:
                self.assertNotIn(".local/bin", sz, f"{fajl}: home-beli út")
                self.assertNotRegex(sz, r"bin/mos[\"', ]+kor", f"{fajl}: a legacy `bin/mos kor` hívása nem élhet a 2.0-ban")

    def test_a_port_md_felsorolja_a_modositott_fajlokat(self):
        port = (MODUL / "PORT.md").read_text(encoding="utf-8")
        for fajl in ("src/msp/downloader.py", "src/msp/config.py", "src/msp/transcription/base.py", "config/config.yaml"):
            self.assertIn(fajl, port)

    def test_a_staging_es_az_allapot_nem_kerul_a_kodtarba(self):
        gi = (REPO / ".gitignore").read_text(encoding="utf-8")
        for minta in ("modulok/ytdlp/staging/", "modulok/ytdlp/archive/", "modulok/ytdlp/logs/"):
            self.assertIn(minta, gi)


if __name__ == "__main__":
    unittest.main()
