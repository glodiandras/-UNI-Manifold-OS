"""C36a: a C++ eszközlánc (`modulok/cpp/eszkoztar.py`, `telepites.py`): utak, a fordítási parancs (tiszta függvény),
a telepítő (hamis archívummal, hálózat nélkül) és az SDK-régiség függvénye. A valódi letöltés és a valódi fordító
nem szerepel itt (azok a `test_cpp_ellenorzes.py` és a `bin/mos cpp telepit` dolga)."""
import contextlib
import hashlib
import io
import json
import os
import tarfile
import unittest
from pathlib import Path
from unittest import mock

from core import config
from modulok.cpp import __main__ as cli
from modulok.cpp import eszkoztar, telepites
from tests.helpers import REPO, alg_gyoker, tmpdir


def _cfg(root: Path, **env):
    return config.load({"MOS_ROOT": str(root), "HOME": str(root.parent / "home"), **env})


def _hamis_eszkoztar(root: Path, *, clang=True, formaz=True, sdk=True) -> None:
    """Egy minimális, hamis `runtime/llvm` és `runtime/sdk` (a fájlok léteznek és futtathatók, de nem fordítók)."""
    bin_ = root / "runtime" / "llvm" / "bin"
    bin_.mkdir(parents=True, exist_ok=True)
    for nev, kell in (("clang++", clang), ("clang-format", formaz), ("clangd", True), ("ld64.lld", True)):
        if kell:
            (bin_ / nev).write_text("#!/bin/sh\nexit 0\n")
            (bin_ / nev).chmod(0o755)
    if sdk:
        s = root / "runtime" / "sdk"
        (s / "usr" / "include" / "c++" / "v1").mkdir(parents=True, exist_ok=True)
        (s / "SDKSettings.json").write_text('{"Version": "27.0", "DisplayName": "macOS 27.0"}')


class BeallitasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name).resolve()

    def test_az_utak_a_configbol_jonnek(self):
        e = eszkoztar.Eszkoztar(_cfg(self.root))
        self.assertEqual(e.llvm, self.root / "runtime" / "llvm")
        self.assertEqual(e.sdk, self.root / "runtime" / "sdk")
        self.assertEqual(e.pot, REPO / "modulok" / "cpp" / "pot")

    def test_az_ut_felulirhato_kornyezeti_valtozoval(self):
        e = eszkoztar.Eszkoztar(_cfg(self.root, MOS_LLVM=str(self.root / "mas-llvm")))
        self.assertEqual(e.llvm, self.root / "mas-llvm")

    def test_alapertekek_es_a_config_szakasz(self):
        b = eszkoztar.beallitas(_cfg(self.root))
        self.assertEqual(b["std"], "c++17")
        self.assertEqual(b["teszt_idokorlat_s"], 2.0)
        self.assertIn("-O2", b["gyors"])
        self.assertIn("-fsanitize=address,undefined", b["hibakereso"])

    def test_a_config_nelkuli_alapertek_is_ervenyes(self):
        b = eszkoztar.beallitas(None)
        self.assertEqual(b["std"], "c++17")
        self.assertEqual(b["memoria_mb"], 256)

    def test_hianyzo_kulcsot_az_alapertek_potol(self):
        (self.root / "config" / "os.toml").write_text(
            '[utak]\nos_x = "{os}"\nruntime = "{os}/runtime"\nllvm = "{runtime}/llvm"\nsdk = "{runtime}/sdk"\n'
            '[cpp]\nstd = "c++20"\n')
        b = eszkoztar.beallitas(_cfg(self.root))
        self.assertEqual(b["std"], "c++20")
        self.assertEqual(b["kimenet_max_kb"], 1024)


class KeszTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name).resolve()

    def test_ures_runtime_nem_kesz(self):
        e = eszkoztar.Eszkoztar(_cfg(self.root))
        self.assertFalse(e.kesz())
        self.assertIn("clang++", e.hianyzo())
        self.assertIn("sdk", e.hianyzo())

    def test_teljes_hamis_eszkoztar_kesz(self):
        _hamis_eszkoztar(self.root)
        e = eszkoztar.Eszkoztar(_cfg(self.root))
        self.assertEqual(e.hianyzo(), [])
        self.assertTrue(e.kesz())

    def test_hianyzo_fordito_vagy_formazo_vagy_sdk(self):
        _hamis_eszkoztar(self.root, clang=False)
        self.assertEqual(eszkoztar.Eszkoztar(_cfg(self.root)).hianyzo(), ["clang++"])
        _hamis_eszkoztar(self.root, clang=True, formaz=False)
        (self.root / "runtime" / "llvm" / "bin" / "clang-format").unlink()
        self.assertEqual(eszkoztar.Eszkoztar(_cfg(self.root)).hianyzo(), ["clang-format"])
        (self.root / "runtime" / "llvm" / "bin" / "clang-format").write_text("#!/bin/sh\n")
        (self.root / "runtime" / "llvm" / "bin" / "clang-format").chmod(0o755)
        (self.root / "runtime" / "sdk" / "SDKSettings.json").unlink()
        self.assertEqual(eszkoztar.Eszkoztar(_cfg(self.root)).hianyzo(), ["sdk"])

    def test_nem_futtathato_fajl_nem_szamit(self):
        _hamis_eszkoztar(self.root)
        (self.root / "runtime" / "llvm" / "bin" / "clang++").chmod(0o644)
        self.assertIn("clang++", eszkoztar.Eszkoztar(_cfg(self.root)).hianyzo())

    def test_sdk_verzio(self):
        _hamis_eszkoztar(self.root)
        self.assertEqual(eszkoztar.Eszkoztar(_cfg(self.root)).sdk_verzio(), "27.0")

    def test_sdk_verzio_hianyzo_vagy_hibas_fajlnal_none(self):
        e = eszkoztar.Eszkoztar(_cfg(self.root))
        self.assertIsNone(e.sdk_verzio())
        (self.root / "runtime" / "sdk").mkdir(parents=True)
        (self.root / "runtime" / "sdk" / "SDKSettings.json").write_text("nem json")
        self.assertIsNone(e.sdk_verzio())

    def test_az_ld64_lld_hianya_kotelezo_hiany_nincs_tartalek_linker(self):
        """K168: a rendszer linkere a fordító-profil alatt nem futhat, ezért az `ld64.lld` hiánya nem „csak figyelmeztetés”."""
        _hamis_eszkoztar(self.root)
        (self.root / "runtime" / "llvm" / "bin" / "ld64.lld").unlink()
        e = eszkoztar.Eszkoztar(_cfg(self.root))
        self.assertFalse(e.van_lld())
        self.assertEqual(e.hianyzo(), ["ld64.lld"])
        self.assertFalse(e.kesz())
        self.assertEqual(e.linker(), "lld")           # akkor sem esik vissza a rendszer linkerére


class SdkRegisegTest(unittest.TestCase):
    def test_regebbi(self):
        for sdk, os_ in (("26.5", "27.0"), ("26", "27.0.1"), ("15.4", "26.0"), ("27.0", "27.1")):
            self.assertTrue(eszkoztar.sdk_regebbi(sdk, os_), (sdk, os_))

    def test_nem_regebbi(self):
        for sdk, os_ in (("27.0", "27.0"), ("27.1", "27.0"), ("28", "27.0"), ("27.0", "27.0.1")):
            self.assertFalse(eszkoztar.sdk_regebbi(sdk, os_), (sdk, os_))

    def test_ertelmezhetetlen_verzio_nem_riaszt(self):
        for sdk, os_ in ((None, "27.0"), ("27.0", None), ("x", "27.0"), ("27.0", ""), ("", "")):
            self.assertFalse(eszkoztar.sdk_regebbi(sdk, os_), (sdk, os_))


class ForditParancsTest(unittest.TestCase):
    def setUp(self):
        self.llvm, self.sdk, self.pot = Path("/x/llvm"), Path("/x/sdk"), Path("/x/pot")
        self.b = eszkoztar.beallitas(None)

    def parancs(self, mod="gyors", **kw):
        return eszkoztar.fordit_parancs(self.llvm, self.sdk, self.pot, self.b, "/m/forras.cpp", "/m/prog", mod, **kw)

    def test_a_fordito_az_llvm_bin_alol_jon_abszolut_uttal(self):
        self.assertEqual(self.parancs()[0], "/x/llvm/bin/clang++")

    def test_gyors_mod_a_spec_kapcsoloival(self):
        p = self.parancs()
        for k in ("-std=c++17", "-O2", "-Wall", "-Wextra", "-fno-color-diagnostics"):
            self.assertIn(k, p)
        self.assertEqual(p[p.index("-isysroot") + 1], "/x/sdk")
        self.assertEqual(p[-3:], ["/m/forras.cpp", "-o", "/m/prog"])
        self.assertFalse([k for k in p if k.startswith("-fsanitize")])

    def test_hibakereso_mod(self):
        p = self.parancs("hibakereso")
        for k in ("-g", "-O1", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"):
            self.assertIn(k, p)
        self.assertNotIn("-O2", p)

    def test_az_sdk_libcxx_fejlece_es_a_potfejlec_a_rendszerfejlecek_helyett(self):
        p = self.parancs()
        self.assertIn("-nostdinc++", p)
        isystem = [p[i + 1] for i, k in enumerate(p) if k == "-isystem"]
        self.assertEqual(isystem, ["/x/sdk/usr/include/c++/v1", "/x/pot"])

    def test_nincs_rendszer_ut_es_nincs_path_keresztel_hivott_program(self):
        for mod in ("gyors", "hibakereso"):
            for k in self.parancs(mod):
                self.assertFalse(k.startswith(("/usr/bin", "/Library/Developer", "/Applications/Xcode")), k)
        self.assertTrue(self.parancs()[0].startswith("/"))

    def test_a_linker_mindig_az_lld(self):
        """K168: a „rendszer” érték kikerült; a parancs akkor is `-fuse-ld=lld`-t kap, ha a config még a régit hordozza."""
        self.assertIn("-fuse-ld=lld", self.parancs())
        for ertek in ("rendszer", "ld", ""):
            self.b["linker"] = ertek
            self.assertIn("-fuse-ld=lld", self.parancs())

    def test_a_regi_rendszer_ertek_figyelmeztetest_ad_az_lld_nem(self):
        self.assertIsNone(eszkoztar.linker_figyelmeztetes({"linker": "lld"}))
        self.assertIsNone(eszkoztar.linker_figyelmeztetes({}))
        uz = eszkoztar.linker_figyelmeztetes({"linker": "rendszer"})
        self.assertIn("rendszer", uz)
        self.assertIn("lld", uz)

    def test_a_std_a_beallitasbol_jon(self):
        self.b["std"] = "c++20"
        self.assertIn("-std=c++20", self.parancs())

    def test_ismeretlen_mod_hiba(self):
        with self.assertRaises(ValueError):
            self.parancs("gyorsabb")

    def test_a_forras_egy_argumentum_akkor_is_ha_szokozt_tartalmaz(self):
        p = eszkoztar.fordit_parancs(self.llvm, self.sdk, self.pot, self.b, "/m/a b.cpp", "/m/p r", "gyors")
        self.assertIn("/m/a b.cpp", p)
        self.assertIn("/m/p r", p)

    def test_a_konstexpr_es_sablonmelyseg_korlatos(self):
        p = self.parancs()
        self.assertTrue(any(k.startswith("-fconstexpr-steps=") for k in p))
        self.assertTrue(any(k.startswith("-ftemplate-depth=") for k in p))


class KornyezetTest(unittest.TestCase):
    def test_a_futtato_kornyezet_ures_es_csak_a_sanitizer_valtozok(self):
        b = eszkoztar.beallitas(None)
        gyors = eszkoztar.futtat_kornyezet(b, "gyors")
        self.assertEqual(gyors, {})
        hib = eszkoztar.futtat_kornyezet(b, "hibakereso")
        self.assertEqual(set(hib), {"ASAN_OPTIONS", "UBSAN_OPTIONS"})
        self.assertIn("symbolize=0", hib["ASAN_OPTIONS"])
        self.assertIn("detect_leaks=0", hib["ASAN_OPTIONS"])

    def test_a_fordito_kornyezete_minimalis(self):
        k = eszkoztar.fordit_kornyezet(Path("/m/munka"), Path("/x/sdk"))
        self.assertEqual(k["TMPDIR"], "/m/munka")
        self.assertEqual(k["SDKROOT"], "/x/sdk")
        self.assertNotIn("PATH", k)
        self.assertNotIn("HOME", k)


# ----------------------------------------------------------------------------------------------------- telepítő

def _archivum(tar_ut: Path, elemek: dict[str, bytes], *, gyoker: str | None = "LLVM-X-macOS-ARM64",
              futtathato: tuple[str, ...] = (), link: dict[str, str] | None = None, extra=None,
              ablak_log: int | None = None) -> str:
    """Hamis `.tar.zst` az elemekkel; → a sha256. Az `ablak_log` a zstd-ablak log2-je (a valódi LLVM-csomag 30)."""
    opciok = None
    if ablak_log:
        from compression.zstd import CompressionParameter
        opciok = {CompressionParameter.window_log: ablak_log}
    with tarfile.open(tar_ut, "w:zst", options=opciok) as t:
        for nev, adat in elemek.items():
            ti = tarfile.TarInfo(f"{gyoker}/{nev}" if gyoker else nev)
            ti.size = len(adat)
            ti.mode = 0o755 if nev in futtathato else 0o644
            t.addfile(ti, io.BytesIO(adat))
        for nev, cel in (link or {}).items():
            ti = tarfile.TarInfo(f"{gyoker}/{nev}" if gyoker else nev)
            ti.type = tarfile.SYMTYPE
            ti.linkname = cel
            t.addfile(ti)
        if extra:
            extra(t)
    return hashlib.sha256(tar_ut.read_bytes()).hexdigest()


class TelepitoTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name).resolve()
        self.cfg = _cfg(self.root)
        self.dl = self.root / "runtime" / "dl"
        self.hamis = Path(self._t.name) / "hamis.tar.zst"
        self.sha = _archivum(self.hamis, {"bin/clang++": b"#!/bin/sh\n", "lib/x.txt": b"x"},
                             futtathato=("bin/clang++",), link={"bin/clang": "clang++"})
        self.pinek = {"LLVM_VERSION": "9.9.9", "LLVM_URL": "https://pelda.invalid/hamis.tar.zst",
                      "LLVM_ARCHIVE": "hamis.tar.zst", "LLVM_BYTES": str(self.hamis.stat().st_size),
                      "LLVM_SHA256": self.sha}
        self.letoltesek: list[str] = []

    def telepito(self, *, hamis_bajtok: bytes | None = None, pinek=None):
        def letolto(url, cel: Path):
            self.letoltesek.append(url)
            cel.write_bytes(hamis_bajtok if hamis_bajtok is not None else self.hamis.read_bytes())
        return telepites.Telepito(self.cfg, letolto=letolto, pinek=pinek or self.pinek)

    # -- a pinek és a lista

    def test_a_valodi_pinfajl_ertelmezheto(self):
        p = telepites.pinek_beolvas(REPO / "config" / "cpp-pins.env")
        self.assertTrue(p["LLVM_URL"].startswith("https://github.com/llvm/llvm-project/releases/download/"))
        self.assertTrue(p["LLVM_URL"].endswith(".tar.zst"))
        self.assertEqual(len(p["LLVM_SHA256"]), 64)
        self.assertGreater(int(p["LLVM_BYTES"]), 100_000_000)

    def test_hianyos_pinfajl_hiba(self):
        ut = Path(self._t.name) / "pins.env"
        ut.write_text("LLVM_VERSION=1\n")
        with self.assertRaises(telepites.TelepitesHiba):
            telepites.pinek_beolvas(ut)

    def test_lista_a_nevet_meretet_hasht_es_a_celt_mutatja_halozat_nelkul(self):
        t = self.telepito()
        with mock.patch("subprocess.run", side_effect=AssertionError("a lista nem futtathat programot")), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("a lista nem használhat hálózatot")):
            szoveg = t.lista()
        self.assertIn("hamis.tar.zst", szoveg)
        self.assertIn(self.sha, szoveg)
        self.assertIn(f"{int(self.pinek['LLVM_BYTES']):,}".replace(",", " "), szoveg)
        self.assertIn(str(self.root / "runtime" / "llvm"), szoveg)
        self.assertIn(str(self.root / "runtime" / "sdk"), szoveg)
        self.assertEqual(self.letoltesek, [])

    # -- letöltés

    def test_igen_nelkul_nem_toltl_le_semmit(self):
        t = self.telepito()
        r = t.llvm(igen=False)
        self.assertEqual(r["allapot"], "nincs_igen")
        self.assertEqual(self.letoltesek, [])
        self.assertFalse((self.root / "runtime" / "llvm").exists())

    def test_letoltes_ellenorzes_kicsomagolas(self):
        t = self.telepito()
        r = t.llvm(igen=True)
        self.assertEqual(r["allapot"], "telepitve")
        self.assertEqual(self.letoltesek, ["https://pelda.invalid/hamis.tar.zst"])
        llvm = self.root / "runtime" / "llvm"
        self.assertTrue((llvm / "bin" / "clang++").is_file())
        self.assertTrue(os.access(llvm / "bin" / "clang++", os.X_OK))
        self.assertFalse(os.access(llvm / "lib" / "x.txt", os.X_OK))
        self.assertTrue((llvm / "bin" / "clang").is_symlink())
        self.assertEqual(os.readlink(llvm / "bin" / "clang"), "clang++")
        self.assertTrue((self.dl / "hamis.tar.zst").is_file())             # a letöltött archívum megmarad (újratelepítéshez)
        self.assertEqual([p.name for p in (self.root / "runtime").glob("llvm.*")], [])   # nincs ideiglenes mappa

    def test_hash_elteres_leall_es_nem_csomagol_ki(self):
        bajtok = bytearray(self.hamis.read_bytes())
        bajtok[-1] ^= 0x01                                                # ugyanakkora, egyetlen bit eltér
        t = self.telepito(hamis_bajtok=bytes(bajtok))
        with self.assertRaises(telepites.TelepitesHiba) as cm:
            t.llvm(igen=True)
        self.assertIn("sha256", str(cm.exception))
        self.assertFalse((self.root / "runtime" / "llvm").exists())
        self.assertEqual([p.name for p in (self.root / "runtime").glob("llvm*")], [])
        self.assertFalse((self.dl / "hamis.tar.zst").exists())            # a hibás archívumot nem tartjuk meg

    def test_meret_elteres_is_hiba(self):
        t = self.telepito(pinek=self.pinek | {"LLVM_BYTES": "12345"})
        with self.assertRaises(telepites.TelepitesHiba) as cm:
            t.llvm(igen=True)
        self.assertIn("méret", str(cm.exception))
        self.assertFalse((self.root / "runtime" / "llvm").exists())

    def test_a_mar_letoltott_helyes_archivum_nem_toltodik_le_ujra(self):
        self.dl.mkdir(parents=True)
        (self.dl / "hamis.tar.zst").write_bytes(self.hamis.read_bytes())
        t = self.telepito()
        self.assertEqual(t.llvm(igen=True)["allapot"], "telepitve")
        self.assertEqual(self.letoltesek, [])

    def test_a_mar_letoltott_hibas_archivum_ujratoltodik(self):
        self.dl.mkdir(parents=True)
        (self.dl / "hamis.tar.zst").write_bytes(b"csonka")
        t = self.telepito()
        self.assertEqual(t.llvm(igen=True)["allapot"], "telepitve")
        self.assertEqual(len(self.letoltesek), 1)

    # -- a telepített állapot és az újratelepítés

    def test_mar_telepitett_eszkoztar_nem_nyulodik_ujra(self):
        (self.root / "runtime" / "llvm" / "bin").mkdir(parents=True)
        (self.root / "runtime" / "llvm" / "bin" / "clang++").write_text("regi")
        t = self.telepito()
        self.assertEqual(t.llvm(igen=True)["allapot"], "mar_megvan")
        self.assertEqual(self.letoltesek, [])
        self.assertEqual((self.root / "runtime" / "llvm" / "bin" / "clang++").read_text(), "regi")

    def test_ujra_a_regit_felreteszi_nem_torli(self):
        regi = self.root / "runtime" / "llvm"
        (regi / "bin").mkdir(parents=True)
        (regi / "bin" / "clang++").write_text("regi")
        r = self.telepito().llvm(igen=True, ujra=True)
        self.assertEqual(r["allapot"], "telepitve")
        self.assertEqual((self.root / "runtime" / "llvm.regi" / "bin" / "clang++").read_text(), "regi")
        self.assertEqual((regi / "bin" / "clang++").read_text(), "#!/bin/sh\n")

    def test_sikertelen_ujratelepites_a_meglevot_nem_bantja(self):
        regi = self.root / "runtime" / "llvm"
        (regi / "bin").mkdir(parents=True)
        (regi / "bin" / "clang++").write_text("regi")
        with self.assertRaises(telepites.TelepitesHiba):
            self.telepito(hamis_bajtok=b"hibas").llvm(igen=True, ujra=True)
        self.assertEqual((regi / "bin" / "clang++").read_text(), "regi")
        self.assertFalse((self.root / "runtime" / "llvm.regi").exists())

    # -- a kicsomagolás biztonsága

    def test_kifele_mutato_elem_elutasitva(self):
        ut = Path(self._t.name) / "rossz.tar.zst"
        sha = _archivum(ut, {"bin/ok": b"x"}, extra=lambda t: t.addfile(
            _tarinfo("LLVM-X-macOS-ARM64/../../kint.txt", 3), io.BytesIO(b"kin")))
        t = self.telepito(hamis_bajtok=ut.read_bytes(), pinek=self.pinek | {
            "LLVM_SHA256": sha, "LLVM_BYTES": str(ut.stat().st_size)})
        with self.assertRaises(telepites.TelepitesHiba):
            t.llvm(igen=True)
        self.assertFalse((self.root / "runtime" / "kint.txt").exists())
        self.assertFalse((self.root / "runtime" / "llvm").exists())

    def test_kifele_mutato_symlink_elutasitva(self):
        ut = Path(self._t.name) / "rossz2.tar.zst"
        sha = _archivum(ut, {"bin/ok": b"x"}, link={"bin/kint": "/etc/hosts"})
        t = self.telepito(hamis_bajtok=ut.read_bytes(), pinek=self.pinek | {
            "LLVM_SHA256": sha, "LLVM_BYTES": str(ut.stat().st_size)})
        with self.assertRaises(telepites.TelepitesHiba):
            t.llvm(igen=True)
        self.assertFalse((self.root / "runtime" / "llvm").exists())

    def test_nagy_zstd_ablakos_archivum_is_kicsomagolhato(self):
        """A valódi LLVM-csomag 2^30-as zstd-ablakkal készült; a Python alapértelmezett határa (2^27) „Frame requires too
        much memory for decoding” hibával elbukna (a C36a valódi telepítésén derült ki)."""
        ut = Path(self._t.name) / "nagyablak.tar.zst"
        sha = _archivum(ut, {"bin/clang++": b"x" * 4096}, ablak_log=28)
        t = self.telepito(hamis_bajtok=ut.read_bytes(), pinek=self.pinek | {
            "LLVM_SHA256": sha, "LLVM_BYTES": str(ut.stat().st_size)})
        t.llvm(igen=True)
        self.assertTrue((self.root / "runtime" / "llvm" / "bin" / "clang++").is_file())

    def test_gyoker_nelkuli_archivum_is_kicsomagolhato(self):
        ut = Path(self._t.name) / "lapos.tar.zst"
        sha = _archivum(ut, {"bin/clang++": b"x"}, gyoker=None)
        t = self.telepito(hamis_bajtok=ut.read_bytes(), pinek=self.pinek | {
            "LLVM_SHA256": sha, "LLVM_BYTES": str(ut.stat().st_size)})
        t.llvm(igen=True)
        self.assertTrue((self.root / "runtime" / "llvm" / "bin" / "clang++").is_file())

    # -- az SDK-másolat

    def _hamis_sdk(self) -> Path:
        s = Path(self._t.name) / "forras-sdk" / "MacOSX27.0.sdk"
        (s / "usr" / "include").mkdir(parents=True)
        (s / "usr" / "include" / "stdio.h").write_text("// stdio")
        (s / "SDKSettings.json").write_text('{"Version": "27.0"}')
        return s

    def test_sdk_masolat(self):
        forras = self._hamis_sdk()
        t = telepites.Telepito(self.cfg, letolto=None, pinek=self.pinek, sdk_forras=lambda: forras)
        r = t.sdk()
        self.assertEqual(r["allapot"], "telepitve")
        sdk = self.root / "runtime" / "sdk"
        self.assertEqual((sdk / "usr" / "include" / "stdio.h").read_text(), "// stdio")
        self.assertEqual(r["verzio"], "27.0")

    def test_sdk_forras_ervenytelen(self):
        ures = Path(self._t.name) / "ures"
        ures.mkdir()
        t = telepites.Telepito(self.cfg, letolto=None, pinek=self.pinek, sdk_forras=lambda: ures)
        with self.assertRaises(telepites.TelepitesHiba):
            t.sdk()
        self.assertFalse((self.root / "runtime" / "sdk").exists())

    def test_sdk_nincs_forras(self):
        t = telepites.Telepito(self.cfg, letolto=None, pinek=self.pinek, sdk_forras=lambda: None)
        with self.assertRaises(telepites.TelepitesHiba):
            t.sdk()

    def test_mar_meglevo_sdk_nem_nyulodik_ujra_az_ujra_felreteszi_a_regit(self):
        forras = self._hamis_sdk()
        t = telepites.Telepito(self.cfg, letolto=None, pinek=self.pinek, sdk_forras=lambda: forras)
        t.sdk()
        self.assertEqual(t.sdk()["allapot"], "mar_megvan")
        (forras / "SDKSettings.json").write_text('{"Version": "27.1"}')
        r = t.sdk(ujra=True)
        self.assertEqual(r["verzio"], "27.1")
        self.assertTrue((self.root / "runtime" / "sdk.regi" / "SDKSettings.json").is_file())

    def test_a_masolat_nem_ugyanaz_a_hely_mint_a_forras(self):
        t = telepites.Telepito(self.cfg, letolto=None, pinek=self.pinek, sdk_forras=lambda: self.root / "runtime" / "sdk")
        (self.root / "runtime" / "sdk").mkdir(parents=True)
        (self.root / "runtime" / "sdk" / "SDKSettings.json").write_text('{"Version": "27.0"}')
        with self.assertRaises(telepites.TelepitesHiba):
            t.sdk(ujra=True)


_TBD_X1 = """--- !tapi-tbd
tbd-version:     4
targets:         [ x86_64-macos, x86_64-maccatalyst, arm64-macos, arm64-maccatalyst, 
                   arm64e-macos, arm64e-maccatalyst, arm64e.x1-macos, arm64e.x1-maccatalyst ]
install-name:    '/usr/lib/libc++.1.dylib'
exports:
  - targets:         [ x86_64-macos, x86_64-maccatalyst ]
    symbols:         [ __ZTINSt3__110__time_getE ]
  - targets:         [ arm64-macos, arm64-maccatalyst, arm64e-macos, arm64e-maccatalyst, 
                       arm64e.x1-macos, arm64e.x1-maccatalyst ]
    symbols:         [ __ZNSt3__1lsE, _arm64e.x1_nem_cel ]
...
"""


class TbdIgazitasTest(unittest.TestCase):
    """Az LLVM `ld64.lld` 23.1.2 nem ismeri a macOS 27 SDK `arm64e.x1-*` célját („unknown target”: a valódi fordításon
    derült ki): a másolat .tbd-iből ezek a célok kikerülnek (csak az arm64-et linkeljük), minden más változatlan."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.sdk = Path(self._t.name) / "sdk"
        (self.sdk / "usr" / "lib").mkdir(parents=True)
        (self.sdk / "usr" / "lib" / "libc++.tbd").write_text(_TBD_X1)
        (self.sdk / "usr" / "lib" / "libm.tbd").write_text(_TBD_X1.replace("arm64e.x1-", "arm64e-").replace(
            "arm64e-macos, arm64e-maccatalyst, arm64e-macos", "arm64e-macos"))
        (self.sdk / "usr" / "include").mkdir()
        (self.sdk / "usr" / "include" / "arm64e.x1-szoveg.h").write_text("// arm64e.x1-macos nem tbd\n")

    def test_az_ismeretlen_celok_kikerulnek_a_tobbi_marad(self):
        r = telepites.tbd_igazit(self.sdk)
        szoveg = (self.sdk / "usr" / "lib" / "libc++.tbd").read_text()
        self.assertNotIn("arm64e.x1-macos", szoveg)
        self.assertNotIn("arm64e.x1-maccatalyst", szoveg)
        for cel in ("x86_64-macos", "x86_64-maccatalyst", "arm64-macos", "arm64-maccatalyst", "arm64e-macos",
                    "arm64e-maccatalyst"):
            self.assertIn(cel, szoveg)
        self.assertEqual(r["modositott"], 1)
        self.assertEqual(r["tbd"], 2)

    def test_a_szimbolumnevek_es_a_tobbi_sor_valtozatlan(self):
        telepites.tbd_igazit(self.sdk)
        szoveg = (self.sdk / "usr" / "lib" / "libc++.tbd").read_text()
        self.assertIn("_arm64e.x1_nem_cel", szoveg)                     # nem `targets:` lista: nem nyúlunk hozzá
        self.assertIn("install-name:    '/usr/lib/libc++.1.dylib'", szoveg)
        self.assertIn("__ZNSt3__1lsE", szoveg)
        self.assertEqual(szoveg.count("targets:"), 3)

    def test_a_celok_listaja_ervenyes_marad(self):
        telepites.tbd_igazit(self.sdk)
        import re
        for m in re.finditer(r"targets:\s*\[([^\]]*)\]", (self.sdk / "usr" / "lib" / "libc++.tbd").read_text()):
            elemek = [x.strip() for x in m.group(1).split(",")]
            self.assertTrue(all(elemek), elemek)                          # nincs üres elem, nincs árva vessző
            self.assertEqual(len(elemek), len(set(elemek)))

    def test_idempotens(self):
        telepites.tbd_igazit(self.sdk)
        elso = (self.sdk / "usr" / "lib" / "libc++.tbd").read_text()
        r = telepites.tbd_igazit(self.sdk)
        self.assertEqual(r["modositott"], 0)
        self.assertEqual((self.sdk / "usr" / "lib" / "libc++.tbd").read_text(), elso)

    def test_a_nem_tbd_fajl_es_a_x1_nelkuli_tbd_erintetlen(self):
        fejlec = self.sdk / "usr" / "include" / "arm64e.x1-szoveg.h"
        elotte = fejlec.read_text()
        libm = self.sdk / "usr" / "lib" / "libm.tbd"
        libm_elotte = libm.read_bytes()
        telepites.tbd_igazit(self.sdk)
        self.assertEqual(fejlec.read_text(), elotte)
        self.assertEqual(libm.read_bytes(), libm_elotte)

    def test_nincs_ideiglenes_fajl_maradek(self):
        telepites.tbd_igazit(self.sdk)
        self.assertEqual([p.name for p in self.sdk.rglob("*") if p.name.endswith((".tmp", ".part"))], [])

    def test_a_masolas_utan_az_sdk_igazitva_van(self):
        forras = Path(self._t.name) / "forras-sdk"
        (forras / "usr" / "lib").mkdir(parents=True)
        (forras / "usr" / "include").mkdir()
        (forras / "SDKSettings.json").write_text('{"Version": "27.0"}')
        (forras / "usr" / "lib" / "libc++.tbd").write_text(_TBD_X1)
        root = alg_gyoker(self._t.name).resolve()
        t = telepites.Telepito(_cfg(root), letolto=None, pinek={"LLVM_VERSION": "1", "LLVM_URL": "u", "LLVM_ARCHIVE": "a",
                                                                 "LLVM_BYTES": "1", "LLVM_SHA256": "0" * 64},
                               sdk_forras=lambda: forras)
        r = t.sdk()
        self.assertEqual(r["tbd_igazitva"], 1)
        self.assertNotIn("arm64e.x1-", (root / "runtime" / "sdk" / "usr" / "lib" / "libc++.tbd").read_text())
        self.assertIn("arm64e.x1-", (forras / "usr" / "lib" / "libc++.tbd").read_text())     # a forrás érintetlen

    def test_az_allapot_jelzi_ha_az_sdk_nincs_igazitva(self):
        root = alg_gyoker(self._t.name).resolve()
        _hamis_eszkoztar(root)
        (root / "runtime" / "sdk" / "usr" / "lib").mkdir(parents=True, exist_ok=True)
        (root / "runtime" / "sdk" / "usr" / "lib" / "libSystem.tbd").write_text(_TBD_X1)
        e = eszkoztar.Eszkoztar(_cfg(root))
        self.assertFalse(e.sdk_tbd_igazitva())
        self.assertFalse(e.allapot()["sdk_tbd_igazitva"])
        telepites.tbd_igazit(root / "runtime" / "sdk")
        self.assertTrue(e.sdk_tbd_igazitva())


class _HamisTelepito:
    def __init__(self, hiba=None):
        self.hivasok, self.hiba = [], hiba

    def lista(self):
        return "A LISTA"

    def llvm(self, igen, ujra=False):
        self.hivasok.append(("llvm", igen, ujra))
        if self.hiba:
            raise self.hiba
        return {"allapot": "telepitve"}

    def sdk(self, ujra=False):
        self.hivasok.append(("sdk", ujra))
        return {"allapot": "telepitve"}


class ParancssorTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name).resolve()
        self.cfg = _cfg(self.root)

    def fut(self, *argv, telepito=None):
        ki, hiba = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(ki), contextlib.redirect_stderr(hiba):
            kod = cli.main(list(argv), cfg=self.cfg, telepito=telepito)
        return kod, ki.getvalue(), hiba.getvalue()

    def test_allapot_json_nem_kesz(self):
        kod, ki, _ = self.fut("allapot", "--json")
        self.assertEqual(kod, 1)
        d = json.loads(ki)
        self.assertFalse(d["kesz"])
        self.assertIn("clang++", d["hianyzo"])

    def test_allapot_json_kesz(self):
        _hamis_eszkoztar(self.root)
        kod, ki, _ = self.fut("allapot", "--json")
        self.assertEqual(kod, 0)
        d = json.loads(ki)
        self.assertTrue(d["kesz"])
        self.assertEqual(d["sdk_verzio"], "27.0")
        self.assertEqual(d["linker"], "lld")
        self.assertIsNone(d["linker_figyelmeztetes"])

    def test_allapot_a_regi_rendszer_linker_beallitast_jelzi(self):
        """K168: a `linker = "rendszer"` config nem marad csendben: az állapot JSON-ja és a szöveges kimenet is figyelmeztet."""
        _hamis_eszkoztar(self.root)
        self.cfg.data.setdefault("cpp", {})["linker"] = "rendszer"
        kod, ki, _ = self.fut("allapot", "--json")
        self.assertEqual(kod, 0)                                        # a fordítás az lld-vel él, az eszköztár kész
        d = json.loads(ki)
        self.assertEqual(d["linker"], "lld")
        self.assertIn("rendszer", d["linker_figyelmeztetes"])
        _, szoveg, _ = self.fut("allapot")
        self.assertIn("FIGYELEM", szoveg)
        self.assertIn("rendszer", szoveg)

    def test_allapot_szoveg_a_telepitest_mondja_ha_nem_kesz(self):
        kod, ki, _ = self.fut("allapot")
        self.assertEqual(kod, 1)
        self.assertIn("bin/mos cpp telepit", ki)

    def test_telepit_kapcsolo_nelkul_csak_listat_ir(self):
        t = _HamisTelepito()
        kod, ki, _ = self.fut("telepit", telepito=t)
        self.assertEqual(kod, 0)
        self.assertIn("A LISTA", ki)
        self.assertEqual(t.hivasok, [])

    def test_igen_az_llvm_utan_az_sdk_t_is_telepiti(self):
        t = _HamisTelepito()
        self.fut("telepit", "--igen", telepito=t)
        self.assertEqual(t.hivasok, [("llvm", True, False), ("sdk", False)])

    def test_sdk_kapcsolo_csak_az_sdk_t_telepiti_halozat_nelkul(self):
        t = _HamisTelepito()
        self.fut("telepit", "--sdk", "--ujra", telepito=t)
        self.assertEqual(t.hivasok, [("sdk", True)])

    def test_tbd_igazit_kapcsolo_a_meglevo_sdk_t_igazitja_halozat_nelkul(self):
        _hamis_eszkoztar(self.root)
        (self.root / "runtime" / "sdk" / "usr" / "lib").mkdir(parents=True, exist_ok=True)
        (self.root / "runtime" / "sdk" / "usr" / "lib" / "libSystem.tbd").write_text(_TBD_X1)
        kod, ki, _ = self.fut("telepit", "--tbd-igazit")
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(ki.splitlines()[0])["modositott"], 1)
        self.assertNotIn("arm64e.x1-", (self.root / "runtime" / "sdk" / "usr" / "lib" / "libSystem.tbd").read_text())

    def test_telepitesi_hiba_nem_nulla_kilepesi_kod(self):
        t = _HamisTelepito(hiba=telepites.TelepitesHiba("elromlott"))
        kod, _, hiba = self.fut("telepit", "--igen", telepito=t)
        self.assertEqual(kod, 1)
        self.assertIn("elromlott", hiba)


def _tarinfo(nev: str, meret: int) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(nev)
    ti.size = meret
    return ti


if __name__ == "__main__":
    unittest.main()
