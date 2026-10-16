import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import csak_darwin
from tests.helpers import REPO, alg_gyoker, core_indito_szkript, env, tmpdir

APP = REPO / "Manifold.app"


class MosTeszt(unittest.TestCase):
    def test_nincs_path_fallback(self):
        """Python nélküli gyökérben a bin/mos hibával áll meg, és nem nyúl a PATH python3-hoz."""
        with tmpdir() as t:
            root = alg_gyoker(t)
            shutil.copy(REPO / "bin" / "mos", root / "bin" / "mos")
            (root / "config" / "requirements.lock").write_text("")
            e = env(PATH="/usr/bin:/bin:/Library/Frameworks/Python.framework/Versions/3.14/bin")
            p = subprocess.run([str(root / "bin" / "mos"), "doctor"], capture_output=True, text=True, env=e)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("nincs Python", p.stderr)

    def test_mos_parancsok(self):
        p = subprocess.run([str(REPO / "bin" / "mos"), "nemletezo"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("használat", p.stderr)


class MosTestParancsTeszt(unittest.TestCase):
    """T082 (2. audit): a `bin/mos test <modul>` a modulnevet közvetlenül a `-m unittest`-nek adja (a `discover` a pozicionális
    argumentumot kezdőmappának vette: `test_x` ImportError, `tests.test_x` pedig mind a ~1000 tesztet futtatta)."""

    def _fut(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(REPO / "bin" / "mos"), "test", *args], capture_output=True, text=True, timeout=300,
                              env=env(MOS_PYTHON=sys.executable))

    @staticmethod
    def _db(nev: str) -> int:
        import unittest as u
        return u.defaultTestLoader.loadTestsFromName(nev).countTestCases()

    def test_a_modulnev_alakjai_ugyanazt_a_keszletet_futtatjak(self):
        vart = self._db("tests.test_config")
        self.assertGreater(vart, 3)
        self.assertLess(vart, 100)                      # a teljes készlet ~1000: ez nem az
        for alak in ("test_config", "tests.test_config", "tests/test_config.py"):
            with self.subTest(alak=alak):
                p = self._fut(alak)
                self.assertEqual(p.returncode, 0, p.stderr[-800:])
                self.assertRegex(p.stderr, rf"Ran {vart} tests? in ")

    def test_tobb_modul_es_kapcsolo(self):
        vart = self._db("tests.test_config") + self._db("tests.test_sablon")
        p = self._fut("test_config", "test_sablon")
        self.assertEqual(p.returncode, 0, p.stderr[-800:])
        self.assertRegex(p.stderr, rf"Ran {vart} tests? in ")
        p = self._fut("test_config", "-v")
        self.assertIn("test_config", p.stderr)          # a -v kapcsoló átmegy a unittestnek

    def test_ismeretlen_modul_hibat_ad(self):
        p = self._fut("test_nincs_ilyen_modul")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("test_nincs_ilyen_modul", p.stderr)


class PerfKeszletTeszt(unittest.TestCase):
    """T008 (2. audit): a falióra-kapuk külön parancsban futnak (`bin/mos perf`), az alap készlet nem tartalmaz abszolút
    ms-kaput (csak arányt): a `fuzzy` 17–21 ms-ot adott a 15 ms-os kapuhoz terhelt gépen, a Bases 366 ms-ot a 300-hoz."""

    def test_a_perf_modulok_nem_az_alap_keszletben_vannak(self):
        import unittest as u
        loader = u.TestLoader()
        alap_db = loader.discover(str(REPO / "tests"), pattern="test*.py", top_level_dir=str(REPO)).countTestCases()
        perf_db = loader.discover(str(REPO / "tests"), pattern="perf_*.py", top_level_dir=str(REPO)).countTestCases()
        self.assertGreaterEqual(perf_db, 4)                     # Bases ×4 (hideg, meleg, egyszerű, visszalinkek) + index
        self.assertGreater(alap_db, 500)
        # a perf-modulok neve nem `test*.py`: a `bin/mos test` nem fut le velük
        self.assertTrue((REPO / "tests" / "perf_bazis.py").is_file() and (REPO / "tests" / "perf_index.py").is_file())
        self.assertFalse(any(p.name.startswith("test") for p in (REPO / "tests").glob("perf_*.py")))

    def test_az_alap_keszlet_nem_tartalmaz_abszolut_ms_kaput(self):
        """A funkcionális fájlok nem tartalmaznak abszolút ms-kaput: a `bazis` és az `index_api` az arányt/jelenlétet nézi."""
        for nev, tilos in (("test_bazis_teljesitmeny.py", "KORLAT_MS"), ("test_index_api.py", "200, f\"medián")):
            self.assertNotIn(tilos, (REPO / "tests" / nev).read_text(encoding="utf-8"), nev)
        for nev in ("fuzzy.test.ts", "graf_fizika.test.ts"):
            t = (REPO / "app" / "tests" / nev).read_text(encoding="utf-8")
            self.assertNotRegex(t, r"toBeLessThan\((12|15|16)\)", nev)
        for nev in ("fuzzy.perf.ts", "graf_fizika.perf.ts"):
            self.assertTrue((REPO / "app" / "tests" / "perf" / nev).is_file(), nev)

    def test_a_perf_parancs_ismert(self):
        p = subprocess.run([str(REPO / "bin" / "mos"), "nemletezo"], capture_output=True, text=True, env=env())
        self.assertIn("perf", p.stderr)


class MunkafaModTeszt(unittest.TestCase):
    """T002 (2. audit): git worktree-ben (a `.git` fájl, nem mappa) a `bin/mos` a munkafa SAJÁT `var/`-ját használja:
    az eszköztár a fő checkoutból jöhet, az állapot és a belső lemezes mentés nem. Symlinkelt `var/` hibát ad."""

    def _gyoker(self, t, munkafa=True) -> Path:
        root = alg_gyoker(t)
        shutil.copy(REPO / "bin" / "mos", root / "bin" / "mos")
        if munkafa:
            (root / ".git").write_text("gitdir: /nincs/ilyen/.git/worktrees/x\n")
        return root

    def _exec(self, root, *kodok, **extra):
        return subprocess.run([str(root / "bin" / "mos"), "exec", "sh", "-c", *kodok], capture_output=True, text=True,
                              env=env(**extra))

    def test_var_symlink_hiba(self):
        with tmpdir() as t:
            root = self._gyoker(t)
            kulso = Path(t) / "valodi-var"
            kulso.mkdir()
            shutil.rmtree(root / "var")
            os.symlink(kulso, root / "var")
            p = self._exec(root, "echo fut")
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("symlink", p.stderr)
            self.assertNotIn("fut", p.stdout)
            self.assertFalse(any(kulso.iterdir()), "a valódi var/-ba semmi nem íródhat")

    def test_sajat_var_es_a_mentes_a_munkafaba_megy(self):
        with tmpdir() as t:
            root = self._gyoker(t)
            p = self._exec(root, 'echo "$MOS_BACKUP"; echo "$MOS_MUNKAFA"')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.split("\n")[:2], [str(root.resolve() / "var" / "backup"), "1"])

    def test_megadott_mentes_marad(self):
        with tmpdir() as t:
            root = self._gyoker(t)
            p = self._exec(root, 'echo "$MOS_BACKUP"', MOS_BACKUP="/valami/mas")
            self.assertEqual(p.stdout.strip(), "/valami/mas")

    def test_nem_munkafaban_semmi_nem_valtozik(self):
        with tmpdir() as t:
            root = self._gyoker(t, munkafa=False)
            p = self._exec(root, 'echo "[$MOS_BACKUP][$MOS_MUNKAFA]"')
            self.assertEqual(p.stdout.strip(), "[][]")


class CsakOlvashatoCsomagTeszt(unittest.TestCase):
    """F3 (F3-DESIGN §2.6, I1): termék-alakú, írásvédett (`chmod -R a-w`) csomagból futó `bin/mos` semmit nem ír a csomagba:
    a gyökerek a rétegzett konfigból jönnek (`core.gyokerek shell`), az állapot a munkatérben és az `{install}` alatt él."""

    def test_irasvedett_csomagban_nincs_iras(self):
        from tests.helpers import alg_bundle
        t = tmpdir()
        self.addCleanup(t.cleanup)
        tmp = Path(t.name)
        root = alg_bundle(t.name)
        (root / "bin").mkdir()
        shutil.copy(REPO / "bin" / "mos", root / "bin" / "mos")
        vault = tmp / "Jegyzetek"
        (vault / ".manifold").mkdir(parents=True)
        (vault / ".manifold" / "workspace.toml").write_text('[workspace]\nid = "0123456789abcdef0123456789abcdef"\n')
        csomag = tmp / "X.app"

        def jog(irhato: bool):
            for d, mappak, fajlok in os.walk(csomag):
                for n in [*mappak, *fajlok]:
                    p = Path(d) / n
                    if not p.is_symlink():
                        p.chmod(p.stat().st_mode | 0o200 if irhato else p.stat().st_mode & ~0o222)
            csomag.chmod(0o755 if irhato else 0o555)
        jog(False)
        self.addCleanup(jog, True)
        elotte = sorted((str(p.relative_to(csomag)), p.stat().st_mtime_ns) for p in csomag.rglob("*"))
        e = env(MOS_PYTHON=sys.executable, PYTHONPATH=str(REPO), HOME=str(tmp / "home"), MOS_VAULT=str(vault))
        p = subprocess.run([str(root / "bin" / "mos"), "models", "list"], capture_output=True, text=True, env=e, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-1500:])
        self.assertNotRegex(p.stderr, r"(?i)permission denied|read-only|operation not permitted")
        self.assertEqual(sorted((str(p.relative_to(csomag)), p.stat().st_mtime_ns) for p in csomag.rglob("*")), elotte)
        install = tmp / "home" / "Library" / "Application Support" / "Manifold"
        self.assertTrue((vault / ".manifold" / "var" / "tmp").is_dir())                  # a TMPDIR a munkatérben
        self.assertTrue((install / ".metadata_never_index").is_file())


@csak_darwin("a Mach-O Manifold.app héj Linuxon nem fut")
@unittest.skipUnless(APP.exists(), "nincs lefordított Manifold.app")
class ShellTeszt(unittest.TestCase):
    def test_alairas(self):
        p = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(APP)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_selftest_ures_lap(self):
        """app/dist nélkül (álgyökér) a core üres lapot ad; a héj ezt is elfogadja."""
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start())
            p = subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), "--selftest"], capture_output=True,
                               text=True, timeout=60, env=env(MOS_ROOT=str(root), home=False))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK", p.stdout)
            # a core leállásakor készülő állapotmásolat az álgyökér-lokális backup-ba ment, nem a valódi ~/Manifold-backup-ba
            self.assertTrue(list((Path(t) / "home" / "Manifold-backup").glob("mos-allapot-*")), "a mentés nem a helyi backupba ment")

    def test_selftest_masik_core_fut_nincs_masodik_ablak(self):
        """C29.6 (T027): ha ugyanazon a vaulton már fut egy core, az indított core a `foglalt` kézfogással kilép, és a héj
        üzenettel (ablak nélkül) jelez — a `--selftest` ezt hibaként jelenti, a szöveg a másik példányra utal."""
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start())
            elso = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env=env(MOS_ROOT=str(root), PYTHONPATH=str(REPO)))
            try:
                json.loads(elso.stdout.readline())                  # az első core él, a core.lock nála van
                p = subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), "--selftest"], capture_output=True,
                                   text=True, timeout=60, env=env(MOS_ROOT=str(root), home=False))
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertIn("SELFTEST HIBA", p.stdout)
                self.assertIn("már fut", p.stdout)
                self.assertIn(f"pid-je: {elso.pid}", p.stdout)
            finally:
                elso.stdin.close()
                elso.wait(timeout=30)
                elso.stdout.close()

    def test_kuka_hibaja_angol_szoveggel(self):
        """A `--kuka` segéd hibánál `{"ok": false, "kod", "hiba"}` választ ad, a `hiba` angol szöveg (a core továbbadhatja);
        a próba csak tiltott és érvénytelen kérést küld, a valódi Kukához nem nyúl."""
        exe = str(APP / "Contents" / "MacOS" / "Manifold")
        with tmpdir() as t:
            gyoker = Path(t) / "vault"
            gyoker.mkdir()
            esetek = [
                ("nem json", 2, "ervenytelen_keres"),
                (json.dumps({"ut": str(Path(t) / "kivul.md"), "gyoker": str(gyoker)}), 2, "tiltott_ut"),
                (json.dumps({"ut": str(gyoker / "nincs-ilyen.md"), "gyoker": str(gyoker)}), 2, "tiltott_ut"),
                (json.dumps({"ut": str(gyoker), "gyoker": str(gyoker)}), 2, "tiltott_ut"),
            ]
            for bemenet, kod, gepi in esetek:
                p = subprocess.run([exe, "--kuka"], input=bemenet, capture_output=True, text=True, timeout=30,
                                   env=env(home=False))
                self.assertEqual(p.returncode, kod, p.stdout + p.stderr)
                v = json.loads(p.stdout)
                self.assertIs(v["ok"], False)
                self.assertEqual(v["kod"], gepi)
                self.assertIn("Trash", v["hiba"])
                self.assertNotIn(str(t), v["hiba"], "a hibaszövegben nincs abszolút út")

    def _selftest(self, forgatokonyv: str, root: Path, timeout=90, **extra):
        return subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), f"--selftest={forgatokonyv}"], capture_output=True,
                              text=True, timeout=timeout, env=env(MOS_ROOT=str(root), home=False, **extra))

    def test_ismeretlen_forgatokonyv_hiba(self):
        with tmpdir() as t:
            p = self._selftest("nincs-ilyen", alg_gyoker(t), timeout=30)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("ismeretlen forgatókönyv", p.stdout)

    def test_selftest_core_halal_a_stderr_vegevel(self):
        """C29.7b (T031): a core futás közbeni halála nem „A Manifold nem indul”: a héj jelzi, hogy a core leállt, és megmutatja a
        stderr utolsó sorait (a héj maga öli meg a core-t `SIGKILL`-lel; a selftestben az üzenet ablak nélküli)."""
        with tmpdir() as t:
            szkript = core_indito_szkript_start().replace("PYTHONPATH", "echo 'PROBA-STDERR-SOR' >&2\nPYTHONPATH", 1)
            root = alg_gyoker(t, szkript)
            p = self._selftest("core-halal", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK: A core leállt", p.stdout)
            self.assertIn("PROBA-STDERR-SOR", p.stdout, "a stderr (a core indulási sorai) benne van az üzenetben")
            self.assertNotIn("nem indul", p.stdout)

    def test_selftest_core_ujraindul_ugyanazon_a_porton(self):
        """C29.7b (T031): az „Újraindítás” útja: a core halála után a héj ugyanazon a porton indítja újra (`MOS_CORE_PORT`; a
        `core.lock` az elhalt core-tól felszabadult, a port újra foglalható) — így a lap és a benne lévő szöveg megmarad."""
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start())
            p = self._selftest("core-ujraindul", root)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK: a core újraindult ugyanazon a porton", p.stdout)

    def test_selftest_kezfogas_idokorlat(self):
        """C29.7b (T123): ha a core a portsor előtt elakad, a héj a határidő után „A core nem válaszol” üzenetet ad a stderr végével."""
        with tmpdir() as t:
            root = alg_gyoker(t, "#!/bin/sh\necho 'LASSU-INDULAS-SOR' >&2\nexec sleep 120\n")
            p = self._selftest("kezfogas-ido", root, MOS_KEZFOGAS_MP="1")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("SELFTEST OK: A core nem válaszol", p.stdout)
            self.assertIn("LASSU-INDULAS-SOR", p.stdout)

    def test_selftest_a_kezfogas_ideje_alapbol_nem_lep_kozbe(self):
        """A határidő nélküli (alap 25 s) indulás nem esik bele a próbába: az alap selftest zöld marad (a tábla is fut)."""
        with tmpdir() as t:
            root = alg_gyoker(t, core_indito_szkript_start())
            p = subprocess.run([str(APP / "Contents" / "MacOS" / "Manifold"), "--selftest"], capture_output=True, text=True,
                               timeout=90, env=env(MOS_ROOT=str(root), home=False))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertNotIn("nem válaszol", p.stdout)


def core_indito_szkript_start() -> str:
    return core_indito_szkript().replace('-m core "$@"', '-m core start')


if __name__ == "__main__":
    unittest.main()
