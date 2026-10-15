"""A core naplója és a rögzített port (C29.7b, 2. audit T031/A2-hej-3, A2-hej-5):

  - a core stderr-je forgatott `{runs}/core.log`-ba is kerül (az eredeti stderr — a héj csöve — is megkapja), a
    `faulthandler` az összeomlás Python-veremét a naplóba írja: a halott core oka nem vész el;
  - a vesztes (`core.lock` foglalt) példány nem forgat és nem csonkolja az élő core naplóját;
  - `MOS_CORE_PORT`: a héj a core újraindításakor a régi porton indíthatja (a lap origin-je nem változik).
"""
import json
import os
import signal
import socket
import subprocess
import sys
import unittest
from pathlib import Path

from core import corenaplo
from tests import csak_darwin
from tests.helpers import REPO, alg_core, env, tmpdir


class ForgatasTest(unittest.TestCase):
    def test_forgatas_megtartja_az_utolso_n_naplot(self):
        with tmpdir() as t:
            ut = Path(t) / "core.log"
            for i in range(8):
                ut.write_text(f"futas {i}\n")
                corenaplo.forgat(ut, 3)
                self.assertFalse(ut.exists(), "a forgatás után az új napló még nem létezik")
            self.assertEqual(sorted(p.name for p in Path(t).iterdir()), ["core.log.1", "core.log.2", "core.log.3"])
            self.assertEqual((Path(t) / "core.log.1").read_text(), "futas 7\n")
            self.assertEqual((Path(t) / "core.log.3").read_text(), "futas 5\n")

    def test_forgatas_hianyzo_fajllal_sem_hibazik(self):
        with tmpdir() as t:
            corenaplo.forgat(Path(t) / "core.log", 3)


class MeretplafonTest(unittest.TestCase):
    """Lelet 11: a futó napló növekedését a `[core] naplo_max_mb` plafon korlátozza (forgatás, faulthandler átállítása)."""

    def test_a_plafon_elereskor_forog_es_a_faulthandler_az_uj_fajlra_all(self):
        from unittest import mock
        with tmpdir() as t:
            ut = Path(t) / "core.log"
            fh = open(ut, "a", buffering=1, encoding="utf-8")
            naplo = corenaplo._ForgoFajl(ut, fh, 200, db=3)
            with mock.patch.object(corenaplo.faulthandler, "enable") as fe:
                for i in range(60):
                    naplo.write(f"sor {i:03d} " + "x" * 20 + "\n")
            naplo.flush()
            nevek = sorted(p.name for p in Path(t).iterdir())
            self.assertEqual(nevek, ["core.log", "core.log.1", "core.log.2", "core.log.3"])        # db=3: a legrégebbi eldobva
            self.assertTrue(fe.called)
            self.assertIs(fe.call_args.kwargs["file"], naplo.fh)                                    # az új fájl
            for p in Path(t).iterdir():
                self.assertLess(p.stat().st_size, 200 + 100, p.name)                                # nincs plafon fölötti fájl
            self.assertIn("napló forgatva", (Path(t) / "core.log").read_text(encoding="utf-8"))
            self.assertIn("sor 059", (Path(t) / "core.log").read_text(encoding="utf-8") + (Path(t) / "core.log.1").read_text(encoding="utf-8"))
            naplo.fh.close()

    def test_nem_forgathato_naplo_nem_dob_es_nem_forog_vegtelenul(self):
        with tmpdir() as t:
            ut = Path(t) / "core.log"
            fh = open(ut, "a", buffering=1, encoding="utf-8")
            naplo = corenaplo._ForgoFajl(ut, fh, 50, db=2)
            from unittest import mock
            with mock.patch.object(corenaplo, "forgat", side_effect=OSError("tele lemez")):
                for _ in range(10):
                    naplo.write("y" * 40 + "\n")                 # nem dob kivételt
            self.assertTrue(ut.exists())
            fh.close()

    def test_a_plafon_az_os_tomlban_van(self):
        import tomllib
        d = tomllib.loads((REPO / "config" / "os.toml").read_text(encoding="utf-8"))
        self.assertEqual(d["core"]["naplo_max_mb"], corenaplo.ALAP_MAX_MB)


class _Core:
    def __init__(self, tc, elozo=None, **extra):
        self.tc = tc
        self.cfg, self.root, self.v = (elozo.cfg, elozo.root, elozo.v) if elozo else alg_core(tc._t.name)
        e = env(MOS_ROOT=str(self.root), PYTHONPATH=str(REPO), HOME=str(self.root.parent / "home"), **extra)
        self.p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e)
        tc.addCleanup(self.leallit)
        self.kezfogas = json.loads(self.p.stdout.readline())
        self.log = self.cfg.path("runs") / "core.log"

    def leallit(self):
        if self.p.poll() is None:
            try:
                self.p.stdin.close()
            except OSError:
                pass
            try:
                self.p.wait(30)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()
        for f in (self.p.stdout, self.p.stderr, self.p.stdin):
            if f and not f.closed:
                try:
                    f.close()
                except OSError:
                    pass


class CoreNaploTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def test_stderr_a_naploba_es_az_eredeti_csobe_is_kerul(self):
        c = _Core(self)
        self.assertTrue(c.log.is_file(), "a core.log induláskor létrejön a {runs} alatt")
        self.assertIn("[core] indul", c.log.read_text(encoding="utf-8"))
        c.p.stdin.close()
        c.p.wait(30)
        csorol = c.p.stderr.read().decode("utf-8", "replace")
        self.assertIn("[core] indul", csorol, "a héj csöve (az eredeti stderr) is megkapja")

    @csak_darwin("a faulthandler összeomlás-kimenete platformfüggő (Linuxon Python 3.14 alatt `<freed thread state>`, nincs `Thread` sor)")
    def test_faulthandler_az_osszeomlas_okat_a_naploba_irja(self):
        c = _Core(self)
        os.kill(c.p.pid, signal.SIGSEGV)
        self.assertEqual(c.p.wait(15), -signal.SIGSEGV)
        szoveg = c.log.read_text(encoding="utf-8")
        self.assertIn("Fatal Python error: Segmentation fault", szoveg)
        self.assertIn("Thread", szoveg, "minden szál vermét kiírja")

    def test_a_vesztes_masodik_core_nem_forgat_es_nem_csonkol(self):
        c = _Core(self)
        elotte = c.log.read_bytes()
        ino = c.log.stat().st_ino
        masodik = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=env(MOS_ROOT=str(c.root), PYTHONPATH=str(REPO), HOME=str(c.root.parent / "home")))
        try:
            self.assertTrue(json.loads(masodik.stdout.readline())["foglalt"])
            self.assertEqual(masodik.wait(30), 75)
        finally:
            for f in (masodik.stdout, masodik.stderr, masodik.stdin):
                f.close()
            if masodik.poll() is None:
                masodik.kill()
        self.assertTrue(c.log.read_bytes().startswith(elotte), "az élő core naplója nem csonkolódott")
        self.assertEqual(c.log.stat().st_ino, ino)
        self.assertFalse((c.log.parent / "core.log.1").exists(), "a vesztes példány nem forgat")

    def test_a_kovetkezo_indulas_forgat(self):
        c = _Core(self)
        c.p.stdin.close()
        c.p.wait(30)
        c.leallit()
        c2 = _Core(self, elozo=c)
        self.assertTrue((c2.log.parent / "core.log.1").is_file(), "az előző futás naplója core.log.1 lett")
        self.assertIn("[core] indul", (c2.log.parent / "core.log.1").read_text(encoding="utf-8"))


def szabad_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RogzitettPortTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def test_mos_core_port_a_kezfogas_portja(self):
        port = szabad_port()
        c = _Core(self, MOS_CORE_PORT=str(port))
        self.assertEqual(c.kezfogas["port"], port)

    def test_foglalt_port_hibaval_kilep_nem_a_foglalt_core_kodjaval(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            cfg, root, v = alg_core(self._t.name)
            p = subprocess.run([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, input=b"", capture_output=True,
                               timeout=60, env=env(MOS_ROOT=str(root), PYTHONPATH=str(REPO), HOME=str(root.parent / "home"),
                                                   MOS_CORE_PORT=str(port)))
        self.assertNotIn(p.returncode, (0, 75))
        self.assertIn(b"Address already in use", p.stderr)


if __name__ == "__main__":
    unittest.main()
