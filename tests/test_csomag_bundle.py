"""F9 integrációs kapu: VALÓDI termék-csomag a `packaging/build_app.py`-val (a tesztfolyamat Pythonja + venvje relokálva,
ál-héj és ál-felület), és vele:

1. a csomag tartalma tiszta (`csomag_tartalom`), a venv relokálható, az `epites.json` befagyasztott jegyzéke teljes;
2. a RootLocator a csomag saját Pythonjából `csomag` módot és termék-elrendezést lát, `MOS_ROOT`-tal `env` módot;
3. a csomag `bin/mos`-a (a csomag Pythonjával) munkateret hoz létre és core-t indít egy szintetikus vaulton; a Health
   `telepites` sora és a `/api/rendszer/epites` zöld; a csomagba semmi nem íródik;
4. a csomag átmásolva (szóközös útra, csak olvashatóan) ugyanígy indul (relokáció), és egy utólag módosított fájlt a Health
   jelez;
5. a csomagba mutató `MOS_INSTALL`-t a core elutasítja (I1).
A fejlesztő var/-ja és valódi vaultja nélkül; hálózat nincs.
"""
from __future__ import annotations

import http.client
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import REPO, tmpdir
from tests.multi_user import elso_sor

CSOMAG = REPO / "packaging"
if str(CSOMAG) not in sys.path:
    sys.path.insert(0, str(CSOMAG))

import build_app  # noqa: E402
import csomag_tartalom  # noqa: E402
import relokacio  # noqa: E402
from core import epites  # noqa: E402

TITOK = "csomag-titok-0123456789abcdef"
VENVBEN = sys.prefix != sys.base_prefix and (Path(sys.prefix) / "pyvenv.cfg").is_file()


def _fa(gyoker: Path) -> dict[str, tuple]:
    """A fa lenyomata (út → méret, mtime_ns, mód): a csomagba írás kimutatására."""
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        for n in mappak + fajlok:
            p = Path(d) / n
            st = p.lstat()
            ki[str(p.relative_to(gyoker))] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return ki


def _csak_olvashato(p: Path, iras: bool = False) -> None:
    for d, mappak, fajlok in os.walk(p):
        for n in mappak + fajlok:
            x = Path(d) / n
            if not x.is_symlink():
                m = x.stat().st_mode
                x.chmod(m | stat.S_IWUSR if iras else m & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    m = p.stat().st_mode
    p.chmod(m | stat.S_IWUSR if iras else m & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


@unittest.skipUnless(VENVBEN, "a csomag venvje a tesztfolyamat venvjének relokált másolata: venvben futó Python kell")
class TermekCsomagTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.t = Path(os.path.realpath(cls._t.name))
        j = epites.jegyzek(REPO)
        hej = cls.t / "hej" / "Manifold.app"
        (hej / "Contents" / "MacOS").mkdir(parents=True)
        (hej / "Contents" / "Resources").mkdir()
        shutil.copy(REPO / "shell" / "Info.plist", hej / "Contents" / "Info.plist")
        exe = hej / "Contents" / "MacOS" / "Manifold"
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        exe.chmod(0o755)
        (hej / "Contents" / "Resources" / "epites.json").write_text(json.dumps(j), encoding="utf-8")
        dist = cls.t / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<!doctype html><title>Manifold</title>", encoding="utf-8")
        (dist / "epites.json").write_text(json.dumps(j), encoding="utf-8")
        cls.naplo: list[str] = []
        b = build_app.Beallitasok(kimenet=cls.t / "out", hej_app=hej, dist=dist, python=Path(sys.base_prefix),
                                  venv_mod="masol", venv_forras=Path(sys.prefix), git_nelkul=True, ffmpeg=None, node=None,
                                  elavult_ok=True,        # a forrás közben változhat (párhuzamos munka): a frissesség külön teszt
                                  bajtkod=False, verzio="9.8.7", build_szam="42", tartalom_max_mb=16)
        cls.e = build_app.epit(b, naplo=cls.naplo.append)
        cls.app = cls.e.app
        cls.root = cls.app / "Contents" / "Resources" / "manifold"
        cls.home = cls.t / "home"
        cls.home.mkdir()
        cls.vault = cls.t / "Jegyzetek"
        (cls.vault / ".obsidian").mkdir(parents=True)
        (cls.vault / "Első.md").write_text("# Első\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        for p in cls.t.glob("**/Manifold.app"):
            _csak_olvashato(p, iras=True)
        cls._t.cleanup()

    # ------------------------------------------------------------------ segédek

    def _env(self, root: Path, **extra) -> dict:
        """Tiszta környezet, mint a héjé: a fejlesztő `MOS_*`, `PYTHON*`, `VIRTUAL_ENV` változói nélkül."""
        e = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "MOS_API_TITOK": TITOK, "LANG": "en_US.UTF-8"}
        e.update(extra)
        return e

    def _mos(self, root: Path, *args, **env) -> subprocess.CompletedProcess:
        return subprocess.run([str(root / "bin" / "mos"), *args], cwd="/", env=self._env(root, **env), capture_output=True,
                              text=True, timeout=300)

    def _core(self, root: Path, **env):
        p = subprocess.Popen([str(root / "bin" / "mos"), "core", "start"], cwd="/", stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self._env(root, MOS_VAULT=str(self.vault), **env))
        self.addCleanup(self._leallit, p)
        sor = elso_sor(p, 180)
        return p, sor

    @staticmethod
    def _leallit(p):
        if p.poll() is None:
            p.stdin.close()
            try:
                p.wait(60)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for f in (p.stdin, p.stdout, p.stderr):
            if f and not f.closed:
                f.close()

    @staticmethod
    def _get(port: int, ut: str):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        try:
            c.request("GET", ut, headers={"Host": f"127.0.0.1:{port}", "X-Manifold": TITOK})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            c.close()

    def _munkater(self) -> str:
        reg = self.home / "Library" / "Application Support" / "Manifold" / "workspaces.json"
        if (self.vault / ".manifold" / "workspace.toml").is_file():
            return json.loads(reg.read_text(encoding="utf-8"))["utolso"]
        p = self._mos(self.root, "workspace", "letrehoz", str(self.vault), "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout[p.stdout.index("{\n"):])["id"]

    def _ellenoriz_futo_core(self, root: Path) -> None:
        p, sor = self._core(root)
        self.assertTrue(sor, "nincs kézfogás")
        k = json.loads(sor)
        self.assertEqual((k["elrendezes"], k["vault"]), ("termek", str(self.vault)))
        # a core a CSOMAG Pythonjával fut (a venv relokált symlinkje a csomag runtime/python-jára)
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(k["pid"])], capture_output=True, text=True).stdout.strip()
        self.assertTrue(cmd.startswith(str(root / "runtime" / "venv" / "bin" / "python")), cmd)
        kod, eg = self._get(k["port"], "/api/egeszseg")
        self.assertEqual(kod, 200, eg)
        t = next(s for s in eg["ellenorzesek"] if s["kod"] == "telepites")
        self.assertEqual((t["allapot"], t["param"]), ("ok", {"verzio": "9.8.7"}), t)
        kod, ep = self._get(k["port"], "/api/rendszer/epites")
        self.assertEqual(kod, 200, ep)
        self.assertTrue(ep["ok"], ep)
        self.assertEqual(ep["csomag"]["termek_verzio"], "9.8.7")
        self._leallit(p)
        self.assertEqual(p.returncode, 0)

    # ------------------------------------------------------------------ 1.

    def test_1_tartalom_relokacio_es_jegyzek(self):
        self.assertEqual(sorted(x.name for x in self.root.iterdir()), ["app", "bin", "config", "core", "docs", "modulok", "runtime"])
        self.assertEqual(sorted(x.name for x in (self.root / "runtime").iterdir()), ["python", "venv"])
        self.assertFalse((self.root / "config" / "presets").exists())
        self.assertFalse(list(self.root.glob("modulok/*/tests")))
        j = csomag_tartalom.ellenoriz(self.app, tiltott_szovegek=csomag_tartalom.alap_tiltott_szovegek(extra=[str(self.t)]),
                                      max_bajt=16 * 2**20)
        self.assertEqual(j.hibak, [])
        self.assertEqual(relokacio.ellenoriz(self.root / "runtime" / "venv", self.root / "runtime" / "python"), [])
        jegy = json.loads((self.app / "Contents" / "Resources" / "epites.json").read_text(encoding="utf-8"))
        cs = jegy["csomag"]
        self.assertEqual((cs["termek_verzio"], cs["build"], cs["git"], cs["alairas"]), ("9.8.7", "42", None, "nincs"))
        self.assertRegex(cs["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(cs["epitve"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn("core/__main__.py", cs["fajlok"])
        self.assertEqual(set(cs["runtime"]), {"python", "venv"})
        with open(self.app / "Contents" / "Info.plist", "rb") as fh:
            pl = plistlib.load(fh)
        self.assertEqual((pl["CFBundleShortVersionString"], pl["CFBundleVersion"]), ("9.8.7", "42"))
        self.assertTrue(epites.csomag_ellenoriz(self.root, runtime=True)["ok"])
        self.assertTrue(any("hordozható git" in f for f in self.e.figyelmeztetesek))

    # ------------------------------------------------------------------ 2.

    def test_2_rootlocator_a_csomagbol(self):
        py = self.root / "runtime" / "venv" / "bin" / "python"
        for env, mod in (({}, "csomag"), ({"MOS_ROOT": str(REPO)}, "env")):
            with self.subTest(mod):
                p = subprocess.run([str(py), "-B", "-m", "core.gyoker_kereso", "--json"], cwd=self.root,
                                   env={**self._env(self.root), "PYTHONPATH": str(self.root), **env}, capture_output=True,
                                   text=True, timeout=120)
                self.assertEqual(p.returncode, 0, p.stderr)
                ki = json.loads(p.stdout)
                self.assertEqual(ki["mod"], mod)
                if mod == "csomag":
                    self.assertEqual((ki["gyoker"], ki["termek"], ki["elrendezes"]), (str(self.root), True, "termek"))
                    self.assertEqual(ki["install"], str(self.home / "Library" / "Application Support" / "Manifold"))

    # ------------------------------------------------------------------ 3.

    def test_3_core_indul_a_csomagbol_es_nem_ir_bele(self):
        elotte = _fa(self.root)
        self._munkater()
        self._ellenoriz_futo_core(self.root)
        self.assertEqual(_fa(self.root), elotte, "a csomagba semmi nem íródhat")

    # ------------------------------------------------------------------ 4.

    def test_4_relokacio_utan_is_indul_es_a_modositast_jelzi(self):
        self._munkater()
        masik = self.t / "Másik hely" / "Manifold.app"
        masik.parent.mkdir(exist_ok=True)
        subprocess.run(["cp", "-c", "-pPR", str(self.app), str(masik)], check=True)
        _csak_olvashato(masik)
        uj_root = masik / "Contents" / "Resources" / "manifold"
        self.assertEqual(relokacio.ellenoriz(uj_root / "runtime" / "venv", uj_root / "runtime" / "python"), [])
        self._ellenoriz_futo_core(uj_root)
        # utólagos módosítás a csomagban → a Health piros
        f = uj_root / "core" / "gyoker_kereso.py"
        f.chmod(0o644)
        f.write_text(f.read_text(encoding="utf-8") + "\n# módosítva\n", encoding="utf-8")
        p, sor = self._core(uj_root)
        k = json.loads(sor)
        _, eg = self._get(k["port"], "/api/egeszseg")
        t = next(s for s in eg["ellenorzesek"] if s["kod"] == "telepites")
        self.assertEqual((t["allapot"], t["uzenet_kod"]), ("hiba", "telepites.modositott"))
        self.assertIn("core/gyoker_kereso.py", json.dumps(t["reszletek"]))

    # ------------------------------------------------------------------ 5.

    def test_5_a_csomagba_mutato_install_elutasitva(self):
        self._munkater()
        p, sor = self._core(self.root, MOS_INSTALL=str(self.root / "install"))
        p.wait(60)
        hiba = sor.decode("utf-8", "replace") + p.stderr.read().decode("utf-8", "replace")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("iras_a_kodba", hiba)
        self.assertFalse((self.root / "install").exists())


if __name__ == "__main__":
    unittest.main()
