"""A `bin/mos runtime fetch` útja és a C34 (2. audit T187, T188, T190) bin/mos-tételei — hálózat nélkül.

A pinek `file://` URL-ekre mutatnak, a „letöltött” archívumok apró ál-eszközök (shell-szkriptek, amelyek a pinelt
verziót írják ki). Így a valódi letöltési út (curl, sha256, kibontás, verzió-ellenőrzés, pin-váltás) lefut; semmi nem
megy ki a hálózatra, és a valódi `runtime/`-hoz nem nyúl: minden egy ideiglenes álgyökérben (`bin/mos` másolata) történik.
"""
import hashlib
import io
import shutil
import subprocess
import sys
import tarfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import quote

from tests.helpers import REPO, tmpdir

ESZKOZOK = ("bash", "curl", "shasum", "tar", "grep")
FFMPEG_TAG = "imageio_ffmpeg/binaries/ffmpeg-ful"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _tar(tagok: dict[str, tuple[bytes, int]]) -> bytes:
    """tar.gz egy dict-ből: út → (tartalom, mód)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for ut, (tartalom, mod) in tagok.items():
            ti = tarfile.TarInfo(ut)
            ti.size, ti.mode = len(tartalom), mod
            t.addfile(ti, io.BytesIO(tartalom))
    return buf.getvalue()


def _szkript(kimenet: str, delegal: bool = False) -> bytes:
    if delegal:           # python3: --version → ál-verzió; `-m pip …` → sikeres semmi; a többi a valódi értelmező
        return (f"#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo '{kimenet}'; exit 0; fi\n"
                f"if [ \"$3\" = \"pip\" ]; then exit 0; fi\nexec '{sys.executable}' \"$@\"\n").encode()
    return f"#!/bin/sh\necho '{kimenet}'\n".encode()


@unittest.skipUnless(all(shutil.which(e) for e in ESZKOZOK), "bash, curl, shasum, tar, grep kell")
class RuntimeFetchTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        d = Path(self._t.name)
        self.os = d / "os"
        self.forras = d / "forras"
        (self.os / "bin").mkdir(parents=True)
        (self.os / "config").mkdir()
        self.forras.mkdir()
        shutil.copy(REPO / "bin" / "mos", self.os / "bin" / "mos")
        (self.os / "bin" / "mos").chmod(0o755)
        (self.os / "config" / "requirements.lock").write_text("# ál-lock\n", encoding="utf-8")
        self.rt = self.os / "runtime"
        self.kiadas(uv="0.12.21", py="3.14.7", node="24.21.0")

    # ------------------------------------------------------------------ ál-kiadás és pin
    def kiadas(self, uv: str, py: str, node: str, py_valos: str | None = None, rontott: set | None = None) -> None:
        """Létrehozza a `forras/` fájljait és a pinfájlt. `py_valos`: a Python-archívum tényleges verziója (a pintől eltérő
        verzió ellenőrzéséhez); `rontott`: azok az archívumok, amelyek sha256-ja nem a pinelt."""
        rontott = rontott or set()
        py_nev = f"cpython-{py}+20260929-aarch64-apple-darwin-install_only.tar.gz"      # a lemezen '+', az URL-ben %2B
        uv_nev, node_nev = f"uv-{uv}-aarch64-apple-darwin.tar.gz", f"node-v{node}-darwin-arm64.tar.gz"
        py_b = _tar({"python/bin/python3": (_szkript(f"Python {py_valos or py}", delegal=True), 0o755)})
        uv_b = _tar({"uv-aarch64-apple-darwin/uv": (_szkript(f"uv {uv} (abc 2026-09-29 aarch64-apple-darwin)"), 0o755),
                     "uv-aarch64-apple-darwin/uvx": (_szkript(f"uvx {uv}"), 0o755)})
        node_b = _tar({f"node-v{node}-darwin-arm64/bin/node": (_szkript(f"v{node}"), 0o755)})
        ffmpeg_tartalom = b"ker-ffmpeg-" + uv.encode()
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as z:
            z.writestr(FFMPEG_TAG, ffmpeg_tartalom)
        ff_nev = f"imageio_ffmpeg-0.6.0-{uv}-py3-none-macosx_11_0_arm64.whl"
        mind = {py_nev: py_b, uv_nev: uv_b, node_nev: node_b, ff_nev: zbuf.getvalue()}
        sha = {n: _sha(b) for n, b in mind.items()}
        for n, b in mind.items():
            (self.forras / n).write_bytes(b)
        for n in rontott:
            sha[n] = "0" * 64
        url = lambda n: f"file://{quote(str(self.forras))}/{n.replace('+', '%2B')}"   # noqa: E731
        (self.os / "config" / "runtime-pins.env").write_text(
            f"UV_VERSION={uv}\nUV_URL=\"{url(uv_nev)}\"\nUV_SHA256={sha[uv_nev]}\n"
            f"PY_VERSION={py}\nPY_URL=\"{url(py_nev)}\"\nPY_SHA256={sha[py_nev]}\n"
            f"NODE_VERSION={node}\nNODE_URL=\"{url(node_nev)}\"\nNODE_SHA256={sha[node_nev]}\n"
            f"FFMPEG_VERSION=7.1\nFFMPEG_URL=\"{url(ff_nev)}\"\nFFMPEG_SHA256={sha[ff_nev]}\n"
            f"FFMPEG_MEMBER={FFMPEG_TAG}\nFFMPEG_BIN_SHA256={_sha(ffmpeg_tartalom)}\n", encoding="utf-8")
        self.nevek = {"py": py_nev, "uv": uv_nev, "node": node_nev, "ffmpeg": ff_nev}

    def mos(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.os / "bin" / "mos"), *args], capture_output=True, text=True, timeout=120,
                              env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path(self._t.name) / "home")})

    def fetch(self) -> subprocess.CompletedProcess:
        return self.mos("runtime", "fetch")

    def verzio(self, *ut: str) -> str:
        return subprocess.run([str(self.rt.joinpath(*ut)), "--version"], capture_output=True, text=True).stdout.strip()

    # ------------------------------------------------------------------ esetek
    def test_friss_letoltes_az_eredeti_fajlnevekkel_es_kibontott_verziokkal(self):
        p = self.fetch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        dl = {x.name for x in (self.rt / "dl").iterdir()}
        # a gyorsítótár fájlneve a pin URL-jének eredeti neve (a Python nevében a '+' az URL-ben %2B, úgy marad a lemezen is)
        self.assertEqual(dl, {self.nevek["py"].replace("+", "%2B"), self.nevek["uv"], self.nevek["node"], self.nevek["ffmpeg"]})
        self.assertFalse([n for n in dl if n.endswith(".resz")])
        self.assertIn("3.14.7", self.verzio("python", "bin", "python3"))
        self.assertIn("v24.21.0", self.verzio("node", "bin", "node"))
        self.assertIn("uv 0.12.21", self.verzio("uv"))
        self.assertTrue((self.rt / "ffmpeg" / "ffmpeg").is_file())
        self.assertFalse((self.rt / "regi").exists(), "friss telepítésnél nincs mit félretenni")

    def test_a_masodik_futas_nem_tolt_le_semmit_ujra(self):
        self.assertEqual(self.fetch().returncode, 0)
        mtime = {x.name: x.stat().st_mtime_ns for x in (self.rt / "dl").iterdir()}
        for n in (self.nevek["uv"], self.nevek["node"]):          # ha újra letöltené, a forrás törlése miatt hibázna
            (self.forras / n).unlink()
        (self.forras / self.nevek["py"]).unlink()
        p = self.fetch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(mtime, {x.name: x.stat().st_mtime_ns for x in (self.rt / "dl").iterdir()})

    def test_sha_hiba_torli_a_letoltott_fajlt_es_nem_bont_ki(self):
        self.kiadas(uv="0.12.21", py="3.14.7", node="24.21.0", rontott={"node-v24.21.0-darwin-arm64.tar.gz"})
        p = self.fetch()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("SHA256 eltér", p.stderr)
        self.assertIn("törölve", p.stderr)
        dl = [x.name for x in (self.rt / "dl").iterdir()]
        self.assertNotIn("node-v24.21.0-darwin-arm64.tar.gz", dl)
        self.assertFalse([n for n in dl if n.endswith(".resz")], "a részleges fájl sem maradhat")
        self.assertFalse((self.rt / "node").exists())

    def test_serult_gyorsitotarazott_fajl_torlodik_es_ujra_letoltodik(self):
        self.assertEqual(self.fetch().returncode, 0)
        sajat = self.rt / "dl" / self.nevek["node"]
        sajat.write_bytes(sajat.read_bytes()[:100])               # megszakadt/csonka letöltés a végleges néven
        shutil.rmtree(self.rt / "node")                           # és a kibontott sincs meg
        p = self.fetch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("törlöm, újra letöltöm", p.stderr)
        self.assertIn("v24.21.0", self.verzio("node", "bin", "node"))

    def test_resz_fajl_maradvanya_nem_zavarja(self):
        (self.rt / "dl").mkdir(parents=True)
        (self.rt / "dl" / f"{self.nevek['node']}.resz").write_bytes(b"megszakadt letoltes")
        p = self.fetch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse((self.rt / "dl" / f"{self.nevek['node']}.resz").exists())

    def test_pin_valtas_lecsereli_a_kibontott_verziot_a_regit_felreteszi(self):
        self.assertEqual(self.fetch().returncode, 0)
        self.kiadas(uv="0.12.22", py="3.14.8", node="24.22.0")
        p = self.fetch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("3.14.8", self.verzio("python", "bin", "python3"))
        self.assertIn("v24.22.0", self.verzio("node", "bin", "node"))
        self.assertIn("uv 0.12.22", self.verzio("uv"))
        regi = sorted(x.name.split("-")[0] for x in (self.rt / "regi").iterdir())
        self.assertEqual(regi, ["node", "python", "uv", "uvx"])
        regi_py = next(x for x in (self.rt / "regi").iterdir() if x.name.startswith("python"))
        self.assertIn("3.14.7", subprocess.run([str(regi_py / "bin" / "python3"), "--version"], capture_output=True,
                                               text=True).stdout, "a régi verzió megvan (nem törlődött)")
        self.assertIn("félretéve", p.stderr)
        # a régi archívum is a helyén marad a dl alatt (másik fájlnév), a venv újraépítése a felhasználó dolga
        self.assertTrue((self.rt / "dl" / self.nevek["node"]).is_file())

    def test_a_kibontott_verzio_nem_egyezik_a_pinnel_hiba_es_a_mukodo_telepites_marad(self):
        self.assertEqual(self.fetch().returncode, 0)
        self.kiadas(uv="0.12.21", py="3.14.8", node="24.21.0", py_valos="3.14.6")   # a pin 3.14.8, az archívum 3.14.6
        p = self.fetch()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("nem a pinelt 3.14.8", p.stderr)
        self.assertIn("3.14.7", self.verzio("python", "bin", "python3"), "a működő telepítés érintetlen")
        self.assertFalse((self.rt / ".python.uj").exists(), "az ideiglenes kibontás nem marad")

    def test_a_hordozhato_git_a_runtime_alol_elol_all_a_path_en(self):
        """C34: ha a runtime/git/bin/git megvan, a `bin/mos` ezt teszi a PATH elejére; nélküle a PATH változatlan."""
        self.assertNotIn("HORDOZHATO", self.mos("exec", "sh", "-c", "command -v git; git --version 2>&1").stdout)
        git = self.rt / "git" / "bin" / "git"
        git.parent.mkdir(parents=True)
        git.write_text("#!/bin/sh\necho HORDOZHATO-GIT\n")
        git.chmod(0o755)
        p = self.mos("exec", "sh", "-c", "command -v git; git --version")
        self.assertIn(str(git), p.stdout)
        self.assertIn("HORDOZHATO-GIT", p.stdout)

    def test_a_bin_mos_letrehozza_a_spotlight_kizaro_jelolot(self):
        self.assertFalse((self.os / "var" / ".metadata_never_index").exists())
        p = self.mos("exec", "true")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.os / "var" / ".metadata_never_index").is_file())

    def test_az_app_install_eltavolitja_a_napi_rs_canvas_ot_de_mas_csomagot_nem(self):
        """29(a) döntés (T187): az `npm ci` az opcionális natív canvas-t felrakhatja; az `app install` eltávolítja."""
        (self.os / "app").mkdir()
        node = self.rt / "node" / "bin"
        node.mkdir(parents=True)
        (node / "node").write_text("#!/bin/sh\necho v24.21.0\n")
        (node / "npm").write_text("#!/bin/sh\nmkdir -p node_modules/@napi-rs/canvas node_modules/@napi-rs/canvas-darwin-arm64 "
                                  "node_modules/@napi-rs/wasm-runtime node_modules/vite\nexit 0\n")
        for f in ("node", "npm"):
            (node / f).chmod(0o755)
        p = self.mos("app", "install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        nm = self.os / "app" / "node_modules"
        self.assertFalse((nm / "@napi-rs" / "canvas").exists())
        self.assertFalse((nm / "@napi-rs" / "canvas-darwin-arm64").exists())
        self.assertTrue((nm / "@napi-rs" / "wasm-runtime").is_dir(), "a Vite saját @napi-rs csomagja marad")
        self.assertTrue((nm / "vite").is_dir())
        self.assertIn("29(a)", p.stdout)

    def _hamis_npm(self) -> Path:
        (self.os / "app").mkdir(exist_ok=True)
        node = self.rt / "node" / "bin"
        node.mkdir(parents=True, exist_ok=True)
        (node / "node").write_text("#!/bin/sh\necho v24.21.0\n")
        naplo = self.os / "npm-argumentumok.txt"
        (node / "npm").write_text(f"#!/bin/sh\necho \"$*\" >> '{naplo}'\nexit 0\n")
        for f in ("node", "npm"):
            (node / f).chmod(0o755)
        return naplo

    def test_az_app_install_alapbol_offline_az_online_kapcsolo_egyszeri_halozati_lepes(self):
        naplo = self._hamis_npm()
        self.assertEqual(self.mos("app", "install").returncode, 0)
        self.assertEqual(self.mos("app", "install", "--online").returncode, 0)
        sorok = naplo.read_text().splitlines()
        self.assertEqual(sorok, ["ci --offline --ignore-scripts", "ci --ignore-scripts"])

    def test_az_app_install_ismeretlen_kapcsolot_elutasit(self):
        naplo = self._hamis_npm()
        p = self.mos("app", "install", "--valami")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("használat: mos app install [--online]", p.stderr)
        self.assertFalse(naplo.exists(), "az npm nem futhat ismeretlen kapcsolóra")

    def test_az_app_install_hibaja_a_kimeneti_kodban_marad(self):
        (self.os / "app").mkdir()
        node = self.rt / "node" / "bin"
        node.mkdir(parents=True)
        (node / "node").write_text("#!/bin/sh\necho v24.21.0\n")
        (node / "npm").write_text("#!/bin/sh\nexit 7\n")
        for f in ("node", "npm"):
            (node / f).chmod(0o755)
        self.assertNotEqual(self.mos("app", "install").returncode, 0)

    def _hamis_uv(self) -> Path:
        """Ál-`uv`: a `venv <út>` létrehozza a mappát egy jelzővel; a `pip install` a `runtime/bukik` fájl megléténél hibázik."""
        (self.rt / "python" / "bin").mkdir(parents=True, exist_ok=True)
        py = self.rt / "python" / "bin" / "python3"
        py.write_text("#!/bin/sh\nexit 0\n")
        py.chmod(0o755)
        uv = self.rt / "uv"
        uv.write_text('#!/bin/sh\nd="$(dirname "$0")"\ncase "$1" in\n'
                      '  venv) mkdir -p "$2/bin" && echo uj > "$2/jelzo" ;;\n'
                      '  pip) [ -e "$d/bukik" ] && exit 3; exit 0 ;;\nesac\n')
        uv.chmod(0o755)
        return uv

    def _venv(self, tartalom: str | None) -> Path:
        v = self.os / "var" / "venv"
        if tartalom is not None:
            v.mkdir(parents=True)
            (v / "jelzo").write_text(tartalom)
        return v

    def test_a_runtime_install_hibaja_utan_a_regi_venv_visszakerul(self):
        """Lelet 12: az új venv felépülése előtt a régi nem törlődik; bukó offline build után a régi marad."""
        self._hamis_uv()
        v = self._venv("regi")
        (self.rt / "bukik").write_text("")
        p = self.mos("runtime", "install")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("visszakerült", p.stderr)
        self.assertEqual((v / "jelzo").read_text(), "regi")
        self.assertEqual([x.name for x in (self.os / "var").iterdir() if x.name.startswith("venv.regi")], [])

    def test_a_runtime_install_hiba_regi_venv_nelkul_nem_hagy_felkesz_mappat(self):
        self._hamis_uv()
        v = self._venv(None)
        (self.rt / "bukik").write_text("")
        p = self.mos("runtime", "install")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(v.exists())

    def test_a_runtime_install_siker_utan_az_uj_venv_all_a_regi_nem_marad(self):
        self._hamis_uv()
        v = self._venv("regi")
        p = self.mos("runtime", "install")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((v / "jelzo").read_text().strip(), "uj")
        self.assertEqual([x.name for x in (self.os / "var").iterdir() if x.name.startswith("venv.regi")], [])

    def test_python_nelkul_tiszta_hibauzenet_exec_zaj_nelkul(self):
        """Lelet 12: nincs értelmező (sem venv, sem runtime/python): egyetlen érthető HIBA, nem „exec: : not found”."""
        p = self.mos("doctor")
        self.assertEqual(p.returncode, 1)
        self.assertIn("nincs Python", p.stderr)
        self.assertNotIn("exec", p.stderr)
        self.assertNotIn("not found", p.stderr)
        self.assertEqual(p.stderr.count("HIBA"), 1)
        p = self.mos("runtime", "install")                                   # a runtime-parancsok nem igényelnek Pythont
        self.assertIn("hiányzik a runtime", p.stderr)


if __name__ == "__main__":
    unittest.main()
