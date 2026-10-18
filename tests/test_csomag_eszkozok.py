"""F9 `packaging/`: a csomagoló eszközei egyenként — kizárások, relokálható venv, hordozható git, DMG, aláírás-terv,
`runtime_fetch` (hálózat nélkül, ál-nyitóval), csomag-tartalom ellenőrző, és hogy a `packaging/` nem fedi el a PyPI
`packaging` könyvtárát."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tarfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.helpers import REPO, tmpdir

CSOMAG = REPO / "packaging"
if str(CSOMAG) not in sys.path:
    sys.path.insert(0, str(CSOMAG))

import alairas  # noqa: E402
import build_app  # noqa: E402
import csomag_kozos  # noqa: E402
import csomag_tartalom  # noqa: E402
import dmg_keszito  # noqa: E402
import hordozhato_git  # noqa: E402
import relokacio  # noqa: E402
import runtime_fetch  # noqa: E402
from csomag_kozos import CsomagHiba  # noqa: E402


def _kesz(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _futtathato(p: Path, szoveg: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(szoveg, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


class NevterTest(unittest.TestCase):
    def test_a_packaging_mappa_nem_fedi_el_a_pypi_packaginget(self):
        self.assertFalse((CSOMAG / "__init__.py").exists(), "a packaging/__init__.py elfedné a PyPI `packaging`-et")
        spec = importlib.util.find_spec("packaging")
        if spec is not None and spec.origin:
            self.assertFalse(Path(spec.origin).resolve().is_relative_to(CSOMAG.resolve()), spec.origin)


class KizarasTest(unittest.TestCase):
    def test_export_ignore_es_a_csomagolo_kizarasai(self):
        mintak = list(csomag_kozos.KIZART_MINTAK) + csomag_kozos.export_ignore_mintak(REPO)
        self.assertIn("docs/plan/**", mintak)
        self.assertIn("config/presets/**", mintak)
        for rel in ("docs/plan/PLAN.md", "config/presets/v2-kompat.toml", "modulok/ytdlp/tests/test_cli.py",
                    "core/__pycache__/a.cpython-314.pyc", "modulok/ytdlp/.gitignore", "core/.DS_Store",
                    "modulok/ytdlp/staging/x/video.mp4", "tests/preset_v2/a.md"):
            self.assertTrue(csomag_kozos.kizart(rel, mintak), rel)
        for rel in ("core/server.py", "config/os.toml", "modulok/ytdlp/src/msp/config.py", "docs/user/HOTKEYS.md", "bin/mos"):
            self.assertFalse(csomag_kozos.kizart(rel, mintak), rel)

    def test_forras_fajlok_a_valodi_repobol(self):
        f = set(csomag_kozos.forras_fajlok(REPO))
        for kell in ("bin/mos", "core/__main__.py", "config/os.toml", "docs/user/GETTING-STARTED.md"):
            self.assertIn(kell, f)
        rossz = [x for x in f if x.startswith(("tests/", "config/presets/", "var/", "docs/plan/", "docs/dev/", "packaging/",
                                               "shell/", "app/")) or "/tests/" in x or "__pycache__" in x]
        self.assertEqual(rossz, [])

    def test_macho_felismeres(self):
        with tmpdir() as d:
            for nev, fej, vart in (("vekony", b"\xcf\xfa\xed\xfe" + b"\0" * 12, True), ("fat", b"\xca\xfe\xba\xbe\0\0\0\x02", True),
                                   ("java", b"\xca\xfe\xba\xbe\0\0\0\x37", False), ("szoveg", b"#!/bin/sh\n", False)):
                p = Path(d) / nev
                p.write_bytes(fej)
                self.assertEqual(csomag_kozos.macho(p), vart, nev)


class RelokacioTest(unittest.TestCase):
    def _ali_venv(self, d: Path) -> tuple[Path, Path]:
        py = d / "runtime" / "python"
        _futtathato(py / "bin" / "python3.14", "#!/bin/sh\n")
        (py / "bin" / "python3").symlink_to("python3.14")
        v = d / "runtime" / "venv"
        (v / "bin").mkdir(parents=True)
        (v / "bin" / "python").symlink_to(py / "bin" / "python3.14")          # abszolút, mint a `python -m venv`/uv
        (v / "bin" / "python3").symlink_to("python")
        (v / "pyvenv.cfg").write_text(f"home = {py / 'bin'}\nprompt = venv\nversion_info = 3.14.7\n", encoding="utf-8")
        _futtathato(v / "bin" / "hf", f"#!/bin/sh\n'''exec' '{v}/bin/python' \"$0\" \"$@\"\n' '''\nimport x\n")
        _futtathato(v / "bin" / "regi", f"#!{v}/bin/python3\nimport y\n")
        (v / "bin" / "activate").write_text(f"VIRTUAL_ENV='{v}'\n", encoding="utf-8")
        sp = v / "lib" / "python3.14" / "site-packages"
        (sp / "csomag-1.0.dist-info").mkdir(parents=True)
        (sp / "csomag-1.0.dist-info" / "direct_url.json").write_text(json.dumps({"url": f"file://{d}/x.whl"}))
        (sp / "__pycache__").mkdir()
        (sp / "__pycache__" / "a.pyc").write_bytes(str(d).encode())
        return py, v

    def test_relokal_es_ellenoriz(self):
        with tmpdir() as d:
            py, v = self._ali_venv(Path(d))
            self.assertTrue(relokacio.ellenoriz(v, py))                              # előtte: abszolút minden
            relokacio.relokal(v, py)
            self.assertEqual(relokacio.ellenoriz(v, py), [])
            self.assertEqual(os.readlink(v / "bin" / "python"), "../../python/bin/python3.14")
            cfg = (v / "pyvenv.cfg").read_text(encoding="utf-8")
            self.assertIn("home = ../python/bin", cfg)
            self.assertIn("relocatable = true", cfg)
            self.assertNotIn(str(d), cfg)
            for n in ("hf", "regi"):
                t = (v / "bin" / n).read_text(encoding="utf-8")
                self.assertTrue(t.startswith(relokacio.TRAMBULIN), n)
                self.assertNotIn(str(d), t)
            self.assertFalse((v / "bin" / "activate").exists())
            self.assertFalse(list(v.rglob("__pycache__")))
            self.assertFalse(list(v.rglob("direct_url.json")))

    def test_szerkesztheto_telepites_hiba(self):
        with tmpdir() as d:
            py, v = self._ali_venv(Path(d))
            relokacio.relokal(v, py)
            (v / "lib" / "python3.14" / "site-packages" / "__editable__.x.pth").write_text("/a/b\n")
            self.assertTrue(any("szerkeszthető" in h for h in relokacio.ellenoriz(v, py)))

    @unittest.skipUnless(sys.prefix != sys.base_prefix, "a teszt egy venvben futó Pythont igényel")
    def test_valodi_venv_athelyezes_utan_is_fut(self):
        with tmpdir() as d:
            a = Path(d) / "a" / "runtime"
            csomag_kozos.klonoz(Path(sys.base_prefix), a / "python")
            subprocess.run([str(a / "python" / "bin" / "python3"), "-I", "-B", "-m", "venv", "--without-pip", str(a / "venv")],
                           check=True, capture_output=True, env={"PATH": "/usr/bin:/bin"})
            relokacio.relokal(a / "venv", a / "python")
            self.assertEqual(relokacio.ellenoriz(a / "venv", a / "python"), [])
            b = Path(d) / "masik hely" / "runtime"
            b.parent.mkdir()
            a.rename(b)
            self.assertEqual(relokacio.futtathato_proba(b / "venv"), str(b / "venv"))
            self.assertEqual(relokacio.ellenoriz(b / "venv", b / "python"), [])

    def test_venv_epit_parancsai_offline(self):
        with tmpdir() as d:
            d = Path(d)
            for p in ("uv", "wheels/x.whl", "req.lock"):
                (d / p).parent.mkdir(parents=True, exist_ok=True)
                (d / p).write_text("")
            hivasok = []
            relokacio.venv_epit(uv=d / "uv", python_mappa=d / "py", cel=d / "venv", wheels=d / "wheels", lock=d / "req.lock",
                                cache=d / "cache", futtato=lambda cmd, **kw: hivasok.append((list(map(str, cmd)), kw)) or _kesz())
            self.assertEqual([c[0][1:3] for c in hivasok], [["venv", "--relocatable"], ["pip", "install"]])
            pip = hivasok[1][0]
            for k in ("--offline", "--no-index", "--require-hashes"):
                self.assertIn(k, pip)
            self.assertEqual(hivasok[1][1]["env"]["UV_PYTHON_DOWNLOADS"], "never")
            with self.assertRaises(CsomagHiba):
                relokacio.venv_epit(uv=d / "nincs", python_mappa=d, cel=d / "v2", wheels=d, lock=d, cache=d)


class HordozhatoGitTest(unittest.TestCase):
    def _git(self, d: Path, exec_path: str) -> Path:
        g = d / "git"
        _futtathato(g / "bin" / "git", f"#!/bin/sh\ncase \"$1\" in --version) echo 'git version 2.51.0';; "
                                       f"--exec-path) echo '{exec_path}';; esac\n")
        (g / "libexec" / "git-core").mkdir(parents=True)
        return g

    def test_hiany_erthetos_hiba(self):
        with tmpdir() as d:
            self.assertFalse(hordozhato_git.felderit(Path(d) / "nincs").van)
            with self.assertRaises(CsomagHiba) as e:
                hordozhato_git.kotelezo(Path(d) / "nincs")
            self.assertEqual(e.exception.kod, "git_hianyzik")
            for kell in ("runtime_fetch.py", "--git-nelkul", "GIT_SHA256"):
                self.assertIn(kell, str(e.exception))

    def test_relokalhato_es_beegetett_prefix(self):
        with tmpdir() as d:
            d = Path(os.path.realpath(d))
            g = self._git(d, "")
            (g / "bin" / "git").write_text(f"#!/bin/sh\ncase \"$1\" in --version) echo 'git version 2.51.0';; "
                                           f"--exec-path) echo \"$(dirname \"$0\")/../libexec/git-core\";; esac\n")
            a = hordozhato_git.kotelezo(g)
            self.assertEqual((a.verzio, a.relokalhato), ("2.51.0", True))
            self.assertEqual(a.szotar()["exec_path_relativ"], "libexec/git-core")
            g2 = self._git(d / "b", "/usr/local/libexec/git-core")
            a2 = hordozhato_git.felderit(g2)
            self.assertFalse(a2.relokalhato)
            with self.assertRaises(CsomagHiba):
                hordozhato_git.kotelezo(g2)

    def test_nem_rendszer_dylib_hiba(self):
        with tmpdir() as d:
            g = self._git(Path(d), str(Path(os.path.realpath(d)) / "git" / "libexec" / "git-core"))

            def futtato(cmd, **kw):
                if cmd[0] == "otool":
                    return _kesz(stdout=f"{cmd[-1]}:\n\t/usr/lib/libz.1.dylib (x)\n\t/opt/homebrew/lib/libintl.8.dylib (y)\n")
                return csomag_kozos.futtat(cmd, **kw)
            a = hordozhato_git.felderit(g, futtato)
            self.assertTrue(any("libintl" in h for h in a.hibak))

    def test_forrasbol_epites_parancsai(self):
        cmds = hordozhato_git.epites_parancsok(Path("/forras"), Path("/cel"), magok=2)
        self.assertEqual(len(cmds), 2)
        for k in ("RUNTIME_PREFIX=YesPlease", "NO_CURL=YesPlease", "NO_OPENSSL=YesPlease", "NO_GETTEXT=YesPlease",
                  "NO_PERL=YesPlease", "NO_PYTHON=YesPlease", "NO_TCLTK=YesPlease", "NO_EXPAT=YesPlease", "prefix=/"):
            self.assertIn(k, cmds[0])
        self.assertIn("DESTDIR=/cel", cmds[1])
        self.assertEqual(cmds[1][-1], "install")


class DmgTest(unittest.TestCase):
    def _app(self, d: Path) -> Path:
        app = d / "Manifold.app"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "Manifold"}))
        return app

    def test_dry_run_terv(self):
        with tmpdir() as d:
            app = self._app(Path(d))
            t = dmg_keszito.keszit(app, Path(d) / "out" / "M.dmg", dry_run=True, naplo=lambda s: None)
            self.assertTrue(t.dry_run)
            self.assertEqual(t.parancsok[0][:2], ["hdiutil", "create"])
            self.assertIn("UDZO", t.parancsok[0])
            self.assertEqual(t.parancsok[1][:2], ["hdiutil", "verify"])
            self.assertFalse((Path(d) / "out" / "M.dmg").exists())

    def test_hdiutil_nelkul_dry_run(self):
        with tmpdir() as d, mock.patch.object(dmg_keszito, "van_parancs", return_value=False):
            t = dmg_keszito.keszit(self._app(Path(d)), Path(d) / "M.dmg", naplo=lambda s: None)
            self.assertEqual((t.dry_run, t.ok_hianyzo_eszkoz), (True, "hdiutil"))

    def test_staging_tartalma_es_takaritasa(self):
        with tmpdir() as d:
            app = self._app(Path(d))
            latott = {}

            def futtato(cmd, **kw):
                if cmd[1] == "create":
                    st = Path(cmd[cmd.index("-srcfolder") + 1])
                    latott["tartalom"] = sorted(p.name for p in st.iterdir())
                    latott["link"] = os.readlink(st / "Applications")
                return _kesz()
            with mock.patch.object(dmg_keszito, "van_parancs", return_value=True):
                t = dmg_keszito.keszit(app, Path(d) / "M.dmg", futtato=futtato, naplo=lambda s: None)
            self.assertEqual(latott, {"tartalom": ["Applications", "Manifold.app"], "link": "/Applications"})
            self.assertFalse(t.staging.exists())

    @unittest.skipUnless(shutil.which("hdiutil"), "nincs hdiutil")
    def test_valodi_kis_dmg(self):
        with tmpdir() as d:
            app = self._app(Path(d))
            dmg = Path(d) / "M.dmg"
            dmg_keszito.keszit(app, dmg, naplo=lambda s: None)
            self.assertTrue(dmg.is_file() and dmg.stat().st_size > 0)


class AlairasTest(unittest.TestCase):
    def _app(self, d: Path) -> Path:
        app = d / "Manifold.app"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "MacOS" / "Manifold").write_bytes(b"\xcf\xfa\xed\xfe" + b"\0" * 12)
        for rel in ("Contents/Resources/manifold/runtime/python/bin/python3.14",
                    "Contents/Resources/manifold/runtime/venv/lib/python3.14/site-packages/x/_m.so"):
            (app / rel).parent.mkdir(parents=True, exist_ok=True)
            (app / rel).write_bytes(b"\xcf\xfa\xed\xfe" + b"\0" * 12)
        (app / "Contents" / "Resources" / "manifold" / "core").mkdir(parents=True)
        (app / "Contents" / "Resources" / "manifold" / "core" / "a.py").write_text("x")
        return app

    def test_nincs_mod_nem_ir_ala(self):
        with tmpdir() as d:
            self.assertEqual(alairas.terv(self._app(Path(d)), "nincs").parancsok, [])

    def test_adhoc_belulrol_kifele(self):
        with tmpdir() as d:
            app = self._app(Path(d))
            t = alairas.terv(app, "adhoc")
            self.assertEqual(t.machok, 2)
            belso = t.parancsok[0]
            self.assertEqual(belso[:4], ["codesign", "--force", "--sign", "-"])
            self.assertTrue(belso[4].endswith("_m.so"))                          # a legmélyebb előbb
            self.assertNotIn("--options", belso)
            self.assertEqual(t.parancsok[-2][-1], str(app))
            self.assertEqual(t.parancsok[-1][:3], ["codesign", "--verify", "--deep"])
            self.assertFalse(any(p.endswith("MacOS/Manifold") for c in t.parancsok[:-2] for p in c[4:]))

    def test_identitas_kornyezetbol_hardened_runtime(self):
        with tmpdir() as d:
            app = self._app(Path(d))
            with self.assertRaises(CsomagHiba):
                alairas.terv(app, "identitas")
            self.assertEqual(alairas.identitas_kornyezetbol({"MOS_ALAIRAS_IDENTITAS": "B"}), "B")
            self.assertEqual(alairas.identitas_kornyezetbol({"MANIFOLD_SIGN_IDENTITY": "A", "MOS_ALAIRAS_IDENTITAS": "B"}), "A")
            t = alairas.terv(app, "identitas", identitas="Developer ID Application: X")
            for k in ("--options", "runtime", "--timestamp", "--entitlements", str(alairas.ENTITLEMENTS)):
                self.assertIn(k, t.parancsok[0])
            hivasok = []

            def futtato(cmd, **kw):
                hivasok.append(cmd)
                return _kesz(stdout='  1) ABC "Masik"\n')
            with self.assertRaises(CsomagHiba):
                alairas.alair(app, "identitas", env={"MANIFOLD_SIGN_IDENTITY": "Developer ID Application: X"}, futtato=futtato,
                              naplo=lambda s: None)
            self.assertEqual(hivasok, [["security", "find-identity", "-p", "codesigning", "-v"]])   # aláírás nem indult

    def test_entitlements_es_notarizacio_profilbol(self):
        with open(alairas.ENTITLEMENTS, "rb") as fh:
            e = plistlib.load(fh)
        self.assertEqual(set(e), {"com.apple.security.cs.allow-jit", "com.apple.security.cs.allow-unsigned-executable-memory",
                                  "com.apple.security.cs.disable-library-validation"})
        with self.assertRaises(CsomagHiba):
            alairas.notarizal_terv(Path("/x.dmg"), "")
        t = alairas.notarizal_terv(Path("/x.dmg"), "manifold-notary")
        self.assertEqual(t[0], ["xcrun", "notarytool", "submit", "/x.dmg", "--keychain-profile", "manifold-notary", "--wait"])
        self.assertEqual(t[1][:3], ["xcrun", "stapler", "staple"])
        forras = "".join(p.read_text(encoding="utf-8") for p in CSOMAG.glob("*.py"))
        for tiltott in ("--password", "--apple-id", "app-specific"):
            self.assertNotIn(tiltott, forras)                                      # hitelesítő adat nem a repóban


class _Valasz(io.BytesIO):
    def __init__(self, adat: bytes, url: str):
        super().__init__(adat)
        self._url = url

    def geturl(self):
        return self._url


def _tetel(adat: bytes, url="https://github.com/a/b/uv.tar.gz", komponens="uv", verzio="1.0") -> runtime_fetch.Tetel:
    import hashlib
    return runtime_fetch.Tetel(komponens, url, hashlib.sha256(adat).hexdigest(), verzio)


class RuntimeFetchTest(unittest.TestCase):
    def test_a_repo_pinjei_es_a_terv(self):
        p = runtime_fetch.pinek_olvas()
        t = runtime_fetch.tervez(p)
        self.assertEqual([x.komponens for x in t], ["uv", "python", "node", "ffmpeg"])
        for x in t:
            runtime_fetch.url_ellenoriz(x.url)
        with self.assertRaises(CsomagHiba) as e:
            runtime_fetch.tervez({k: v for k, v in p.items() if not k.startswith("GIT_")}, ("git",))
        self.assertEqual(e.exception.kod, "pin_hianyzik")

    def test_csak_https_es_engedelyezett_hoszt(self):
        for rossz in ("http://github.com/x.tar.gz", "https://evil.example/x.tar.gz", "ftp://nodejs.org/x"):
            with self.assertRaises(CsomagHiba, msg=rossz):
                runtime_fetch.url_ellenoriz(rossz)
        runtime_fetch.url_ellenoriz("https://files.pythonhosted.org/packages/x.whl")

    def test_letoltes_hash_ellenorzessel(self):
        with tmpdir() as d:
            adat = b"archivum"
            t = _tetel(adat)
            hivas = []
            nyito = lambda url, timeout: hivas.append(url) or _Valasz(adat, url)      # noqa: E731
            f = runtime_fetch.letolt(t, Path(d), nyito=nyito, naplo=lambda s: None)
            self.assertEqual(f.read_bytes(), adat)
            runtime_fetch.letolt(t, Path(d), nyito=nyito, naplo=lambda s: None)       # megvan: nem tölt újra
            self.assertEqual(len(hivas), 1)
            f.write_bytes(b"serult")
            runtime_fetch.letolt(t, Path(d), nyito=nyito, naplo=lambda s: None)       # eltérő hash: újra
            self.assertEqual((len(hivas), f.read_bytes()), (2, adat))

    def test_eltero_hash_nem_hagy_fajlt(self):
        with tmpdir() as d:
            t = _tetel(b"eredeti")
            with self.assertRaises(CsomagHiba) as e:
                runtime_fetch.letolt(t, Path(d), nyito=lambda u, timeout: _Valasz(b"hamis", u), naplo=lambda s: None)
            self.assertEqual(e.exception.kod, "sha_elter")
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_atiranyitas_idegen_hosztra_tilos(self):
        with tmpdir() as d:
            t = _tetel(b"x")
            with self.assertRaises(CsomagHiba):
                runtime_fetch.letolt(t, Path(d), nyito=lambda u, timeout: _Valasz(b"x", "https://evil.example/x"),
                                     naplo=lambda s: None)
            self.assertEqual(list(Path(d).iterdir()), [])
            with self.assertRaises(CsomagHiba):
                runtime_fetch._OrzottAtiranyitas().redirect_request(None, None, 302, "", {}, "http://github.com/x")

    def test_halozati_hiba_ujraprobal(self):
        with tmpdir() as d:
            adat = b"ok"
            t = _tetel(adat)
            n = []

            def nyito(url, timeout):
                n.append(1)
                if len(n) == 1:
                    raise OSError("kapcsolat megszakadt")
                return _Valasz(adat, url)
            with mock.patch.object(runtime_fetch.time, "sleep"):
                f = runtime_fetch.letolt(t, Path(d), nyito=nyito, naplo=lambda s: None)
            self.assertEqual((len(n), f.read_bytes()), (2, adat))
            self.assertFalse(list(Path(d).glob("*.resz")))

    def test_igen_nelkul_csak_terv(self):
        nyito = mock.Mock()
        with tmpdir() as d:
            ki = []
            rc = runtime_fetch.fut(["--cel", d, "--komponens", "uv,python"], nyito=nyito, naplo=ki.append)
            self.assertEqual(rc, 2)
            nyito.assert_not_called()
            self.assertTrue(any("--igen" in s for s in ki))
            self.assertFalse((Path(d) / "dl").exists())

    @unittest.skipUnless((REPO / "runtime").is_symlink(), "a runtime itt nem symlink")
    def test_symlinkelt_runtime_ba_nem_ir(self):
        with self.assertRaises(CsomagHiba) as e:
            runtime_fetch.cel_valaszt(None)
        self.assertEqual(e.exception.kod, "runtime_symlink")

    def _tar(self, d: Path, verzio: str) -> Path:
        src = d / "src" / "python"
        _futtathato(src / "bin" / "python3", f"#!/bin/sh\necho 'Python {verzio}'\n")
        arc = d / f"py-{verzio}.tar.gz"
        with tarfile.open(arc, "w:gz") as tf:
            tf.add(src, arcname="python")
        return arc

    def test_kibontas_verzio_ellenorzessel_a_regi_felre(self):
        with tmpdir() as d:
            d = Path(d)
            rt = d / "rt"
            (rt / "python").mkdir(parents=True)
            (rt / "python" / "regi.txt").write_text("régi")
            t = runtime_fetch.Tetel("python", "https://github.com/x/py.tar.gz", "0" * 64, "3.14.7")
            kesz = runtime_fetch.kibont(t, self._tar(d, "3.14.7"), rt, pinek={}, naplo=lambda s: None)
            self.assertTrue((kesz / "bin" / "python3").is_file())
            self.assertEqual([p.name.split("-")[0] for p in (rt / "regi").iterdir()], ["python"])       # nem törlődött
            with self.assertRaises(CsomagHiba):
                runtime_fetch.kibont(t, self._tar(d / "b", "3.14.70"), rt, pinek={}, naplo=lambda s: None)
            self.assertTrue((rt / "python" / "bin" / "python3").is_file())         # a működő telepítés maradt
            self.assertFalse((rt / ".python.uj").exists())

    def test_ffmpeg_a_bianris_hashevel(self):
        import hashlib
        with tmpdir() as d:
            d = Path(d)
            bin_ = b"#!/bin/sh\necho 'ffmpeg version 7.1'\n"
            whl = d / "x.whl"
            with zipfile.ZipFile(whl, "w") as z:
                z.writestr("pkg/ffmpeg-bin", bin_)
            t = runtime_fetch.Tetel("ffmpeg", "https://files.pythonhosted.org/x.whl", "0" * 64, "7.1")
            pinek = {"FFMPEG_MEMBER": "pkg/ffmpeg-bin", "FFMPEG_BIN_SHA256": hashlib.sha256(bin_).hexdigest()}
            kesz = runtime_fetch.kibont(t, whl, d / "rt", pinek=pinek, naplo=lambda s: None)
            self.assertTrue((kesz / "ffmpeg").is_file())
            with self.assertRaises(CsomagHiba):
                runtime_fetch.kibont(t, whl, d / "rt2", pinek={**pinek, "FFMPEG_BIN_SHA256": "1" * 64}, naplo=lambda s: None)


class TartalomTest(unittest.TestCase):
    def _app(self, d: Path) -> Path:
        app = d / "Manifold.app"
        root = app / "Contents" / "Resources" / "manifold"
        for rel in ("bin/mos", "config/os.toml", "core/__main__.py", "app/dist/index.html", "docs/user/A.md",
                    "runtime/python/bin/python3", "runtime/venv/lib/x.py"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text("x", encoding="utf-8")
        return app

    def test_tiszta_csomag(self):
        with tmpdir() as d:
            j = csomag_tartalom.ellenoriz(self._app(Path(d)), tiltott_szovegek=["/Users/fejleszto"])
            self.assertEqual(j.hibak, [])

    def test_fejlesztoi_es_szemelyes_anyag(self):
        with tmpdir() as d:
            app = self._app(Path(d))
            root = app / "Contents" / "Resources" / "manifold"
            for rel in ("tests/kezi/kapu.py", "var/state/x.json", "config/presets/v2-kompat.toml", "docs/plan/PLAN.md",
                        "runtime/venv/lib/x/settings.toml", "runtime/wheels/a.whl", "core/x.sqlite", "app/src/a.ts",
                        "modulok/ytdlp/tests/test_cli.py"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x", encoding="utf-8")
            (root / "core" / "uj.py").write_text("UT = '/Users/fejleszto/Work/repo'\n", encoding="utf-8")
            (root / "runtime" / "python" / "lib.dylib").write_bytes(b"\0\0/Users/fejleszto/Work/repo\0")
            (root / "core" / "link").symlink_to("/Users/fejleszto/x")
            h = "\n".join(csomag_tartalom.ellenoriz(app, tiltott_szovegek=["/Users/fejleszto/Work/repo"]).hibak)
            for kell in ("tests", "var", "presets", "docs/plan", "settings.toml", "runtime/wheels", "x.sqlite", "app/src",
                         "modulok/ytdlp/tests", "core/uj.py", "lib.dylib", "core/link"):
                self.assertIn(kell, h)

    def test_nfd_alaku_ut_is_talalat(self):
        import unicodedata
        with tmpdir() as d:
            app = self._app(Path(d))
            (app / "Contents/Resources/manifold/core/nfd.py").write_bytes(unicodedata.normalize("NFD", "/Munka/Jegyzeteim").encode())
            self.assertFalse(csomag_tartalom.ellenoriz(app, tiltott_szovegek=["/Munka/Jegyzeteim"]).ok)

    def test_alap_tiltott_szovegek(self):
        t = csomag_tartalom.alap_tiltott_szovegek(REPO)
        self.assertIn(str(REPO), t)
        self.assertIn(os.path.expanduser("~"), t)
        self.assertNotIn("/", t)


class ElofeltetelTest(unittest.TestCase):
    """A forrás-buildek frissessége (héj, felület) egy ál-repón, git nélkül (a bejárásos ujjlenyomat)."""

    def _repo(self, d: Path) -> build_app.Beallitasok:
        from core import epites
        repo = d / "repo"
        for rel in ("shell/Sources/A.swift", "app/src/a.ts", "core/a.py", "core/__main__.py", "bin/mos", "config/os.toml"):
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("x", encoding="utf-8")
        j = epites.jegyzek(repo, hej_valtozat="kiadasi")
        hej = d / "Manifold.app"
        _futtathato(hej / "Contents" / "MacOS" / "Manifold", "#!/bin/sh\n")
        (hej / "Contents" / "Resources").mkdir(parents=True)
        with (hej / "Contents" / "Info.plist").open("wb") as fh:
            plistlib.dump({"CFBundleShortVersionString": "1.0", "CFBundleVersion": "1"}, fh)
        (hej / "Contents" / "Resources" / "epites.json").write_text(json.dumps(j))
        dist = d / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>")
        (dist / "epites.json").write_text(json.dumps(j))
        py = d / "python"
        _futtathato(py / "bin" / "python3", "#!/bin/sh\n")
        return build_app.Beallitasok(repo=repo, kimenet=d / "out", hej_app=hej, dist=dist, python=py, venv_mod="masol",
                                     venv_forras=py, git_nelkul=True, ffmpeg=None, node=None)

    def test_friss_buildek_es_az_elavult(self):
        with tmpdir() as d:
            b = self._repo(Path(d))
            (Path(d) / "python" / "pyvenv.cfg").write_text("home = x\n")
            elo = build_app.elofeltetelek(b, csomag_kozos.futtat, lambda s: None)
            self.assertEqual(elo["git"], None)
            self.assertEqual(elo["hej_valtozat"], "kiadasi")
            self.assertTrue(any("hordozható git" in f for f in b.figyelmeztetesek))
            (b.repo / "shell" / "Sources" / "A.swift").write_text("uj", encoding="utf-8")
            b.figyelmeztetesek = []
            with self.assertRaises(CsomagHiba) as e:
                build_app.elofeltetelek(b, csomag_kozos.futtat, lambda s: None)
            self.assertEqual(e.exception.kod, "hej_elavult")
            self.assertIn("shell/build.sh", str(e.exception))
            b.elavult_ok = True
            build_app.elofeltetelek(b, csomag_kozos.futtat, lambda s: None)
            self.assertTrue(any("hej buildje elavult" in f for f in b.figyelmeztetesek))

    def test_csak_explicit_kiadasi_hej_csomagolhato_az_elavult_kivetellel_is(self):
        # Hibás/legacy metaadatnál még staging-mappa sem készül, és a másoló/runtime/parancsfuttató nem indul el.
        for valtozat in ("fejlesztoi", None, "", "unknown", "release", False, [], {}):
            for elavult_ok in (False, True):
                with self.subTest(valtozat=valtozat, elavult_ok=elavult_ok), tmpdir() as d:
                    b = self._repo(Path(d))
                    p = b.hej_app / "Contents" / "Resources" / "epites.json"
                    j = json.loads(p.read_text())
                    if valtozat is None:
                        j.pop("hej_valtozat")
                    else:
                        j["hej_valtozat"] = valtozat
                    p.write_text(json.dumps(j))
                    b.elavult_ok = elavult_ok
                    futtato = mock.Mock()
                    with mock.patch.object(build_app, "klonoz") as masolas, \
                            mock.patch.object(build_app, "_runtime") as runtime, \
                            mock.patch.object(build_app.epites, "ujjlenyomat") as hash_, \
                            self.assertRaises(CsomagHiba) as e:
                        build_app.epit(b, futtato=futtato, naplo=lambda s: None)
                    self.assertEqual(e.exception.kod, "hej_valtozat")
                    self.assertIn("MOS_DEVELOPER_BUILD=0 bash shell/build.sh", str(e.exception))
                    self.assertIn("fejlesztői" if valtozat == "fejlesztoi" else "ismeretlen", str(e.exception))
                    self.assertFalse(b.kimenet.exists())
                    masolas.assert_not_called()
                    runtime.assert_not_called()
                    hash_.assert_not_called()
                    futtato.assert_not_called()

    def test_kiadasi_valtozat_a_befagyasztott_csomagban_megmarad(self):
        # Apró, szintetikus kódfa, tényleges másolás/fagyasztás/önellenőrzés; a nagy runtime építése nem része ennek a tesztnek.
        with tmpdir() as d:
            b = self._repo(Path(d))
            (b.python / "pyvenv.cfg").write_text("home = x\n")
            b.bajtkod = False
            with mock.patch.object(build_app, "_runtime", return_value={"git": None}) as runtime, \
                    mock.patch.object(build_app, "_git_adatok", return_value=("c" * 40, True)):
                r = build_app.epit(b, naplo=lambda s: None)
            runtime.assert_called_once()
            j = json.loads((r.app / "Contents" / "Resources" / "epites.json").read_text())
            self.assertEqual(r.epites, j)
            self.assertEqual(j["hej_valtozat"], "kiadasi")
            self.assertNotIn("hej_valtozat", j["csomag"])
            self.assertTrue(build_app.ellenoriz_app(r.app, naplo=lambda s: None))

    def test_hianyzo_git_alapbol_hiba(self):
        with tmpdir() as d:
            b = self._repo(Path(d))
            (Path(d) / "python" / "pyvenv.cfg").write_text("home = x\n")
            b.git_nelkul, b.git = False, Path(d) / "nincs-git"
            with self.assertRaises(CsomagHiba) as e:
                build_app.elofeltetelek(b, csomag_kozos.futtat, lambda s: None)
            self.assertEqual(e.exception.kod, "git_hianyzik")


if __name__ == "__main__":
    unittest.main()
