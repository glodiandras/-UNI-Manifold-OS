"""Javító 1 (Audit 3: A3-07, A3-16, A3-23): a program-homokozó fordításának lemez- és memóriakorlátja, a zárva hibázó
memóriaőr és a `clang-format` a fordító-profil alatt.

A tesztek a **szülő-oldali őrzést** mérik egy ál-`sandbox-exec` alatt (a `-f`/`-D` kapcsolókat elhagyja, a maradékot
exec-eli), így Linuxon és macOS-en is futnak; a profil-állításokat a `test_homokozo_program.py` (csak macOS) méri.
A fordító helyén ál-fordító (shell, Python) vagy — ha a gépen van — a rendszer `c++`-a áll: itt csak a korlátot
mérjük, a 53(a) „rendszer fordítójára nincs visszaesés” szabálya a valódi úton (`modulok/cpp`) változatlan."""
import os
import shutil
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from modulok.cpp import eszkoztar
from modulok.homokozo import memoria, program
from tests.helpers import tmpdir
from tests.test_homokozo_elszigeteles import al_sandbox

PY = os.path.realpath(sys.executable)
MB = 1024 * 1024


# a `true` program helye: macOS-en csak /usr/bin/true van (a /bin/true nincs), Linuxon mindkettő (Mac-integráció 2026-10-07)
IGAZ_PROGRAM = Path("/usr/bin/true") if Path("/usr/bin/true").exists() else Path("/bin/true")


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.munka = self.t / "munka"
        self.munka.mkdir()
        self.ph = program.Programhomokozo(sandbox_exec=al_sandbox(self.t))

    def fordit(self, parancs: list[str], **kw):
        kw.setdefault("idokorlat_s", 20)
        return self.ph.fordit(parancs, munka=self.munka, llvm=self.t, sdk=self.t, pot=self.t, **kw)

    def munka_meret(self) -> int:
        return sum(p.stat().st_size for p in self.munka.rglob("*") if p.is_file())


class ForditasLemezTest(_Alap):
    """A3-07: a fordítás is `RLIMIT_FSIZE`-t és `munka/`-méretfigyelést kap (a gyermekfolyamatra — a linkerre — is)."""

    def test_nagy_kimeneti_fajl_iras_korlat(self):
        e = self.fordit(["/bin/sh", "-c", "head -c 20000000 /dev/zero > prog.o"], munka_max_mb=8)
        self.assertEqual(e["allapot"], "iras_korlat", e)
        self.assertLessEqual(self.munka_meret(), 8 * MB)

    def test_a_gyermekfolyamat_linker_is_oroklodik(self):
        e = self.fordit(["/bin/sh", "-c", "/bin/sh -c 'head -c 20000000 /dev/zero > prog' ; exit 0"], munka_max_mb=8)
        self.assertEqual(e["allapot"], "iras_korlat", e)
        self.assertLessEqual(self.munka_meret(), 8 * MB)

    def test_sok_kicsi_fajl_osszmerete_es_szama(self):
        e = self.fordit([PY, "-c", "import time\nfor i in range(40):\n    open(f'f{i}', 'wb').write(b'x' * 1000000)\n"
                         "time.sleep(3)"], munka_max_mb=8)
        self.assertEqual(e["allapot"], "iras_korlat", e)
        e = self.fordit([PY, "-c", "import time\nfor i in range(100):\n    open(f'g{i}', 'wb').close()\ntime.sleep(3)"],
                        munka_max_mb=8, munka_max_fajl=50)
        self.assertEqual(e["allapot"], "iras_korlat", e)

    def test_a_korlat_alatt_rendes_forditas(self):
        e = self.fordit(["/bin/sh", "-c", "head -c 1000000 /dev/zero > prog"], munka_max_mb=8)
        self.assertEqual(e["allapot"], "ok", e)

    def test_alapbol_is_van_korlat(self):
        hivas = {}
        eredeti = self.ph._inditas

        def figyelt(*a, **kw):
            hivas.update(kw)
            return eredeti(*a, **kw)

        with mock.patch.object(self.ph, "_inditas", figyelt):
            self.fordit(["/bin/true"])
        self.assertIsNotNone(hivas["fsize_b"])
        self.assertEqual(hivas["fsize_b"], int(program.FORDIT_MUNKA_MAX_MB * MB))

    def test_valodi_fordito_a_400_mb_os_tomb_kicsinyitve(self):
        cxx = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
        if not cxx:
            self.skipTest("[indokolt] nincs rendszer-C++-fordító ezen a gépen (a valódi eszközlánccal: K143)")
        (self.munka / "f.cpp").write_text("char a[40000000] = {1};\nint main() { return a[5]; }\n")
        e = self.fordit([cxx, "-O2", "-c", "f.cpp", "-o", "f.o"], munka_max_mb=8, idokorlat_s=60,
                        kornyezet={"PATH": "/usr/bin:/bin", "TMPDIR": str(self.munka)})
        self.assertEqual(e["allapot"], "iras_korlat", e)
        self.assertLessEqual(self.munka_meret(), 8 * MB)


class MemoriaorTest(_Alap):
    """A3-16: a fordítónál a folyamatcsoport összege számít; az élő folyamat olvashatatlan memóriája zárva hibázik."""

    def test_a_gyermekfolyamat_memoriaja_is_szamit(self):
        kod = ("import subprocess, sys\nsubprocess.run([sys.executable, '-c', "
               "'import time\\nx = bytearray(300 * 2**20)\\nfor i in range(0, len(x), 4096): x[i] = 1\\ntime.sleep(10)'])")
        e = self.fordit([PY, "-c", kod], memoria_mb=150)
        self.assertEqual(e["allapot"], "memoria", e)
        self.assertGreater(e["csucs_mb"], 150)

    def test_olvashatatlan_memoria_a_forditasnal_homokozo_hiba(self):
        with mock.patch.object(memoria, "csoport_mb", return_value=None), \
                mock.patch.object(memoria, "mb", return_value=None):
            e = self.fordit(["/bin/sleep", "5"])
        self.assertEqual(e["allapot"], "homokozo_hiba", e)
        self.assertIn("memória", e["uzenet"])

    def test_olvashatatlan_memoria_a_futtatasnal_homokozo_hiba(self):
        with mock.patch.object(memoria, "mb", return_value=None):
            e = self.ph.futtat(Path("/bin/sleep"), argv=["5"], munka=self.munka, idokorlat_s=10)
        self.assertEqual(e["allapot"], "homokozo_hiba", e)
        self.assertIn("memória", e["uzenet"])

    def test_a_gyorsan_kilepo_program_nem_hamis_hiba(self):
        with mock.patch.object(memoria, "mb", return_value=None):
            e = self.ph.futtat(IGAZ_PROGRAM, munka=self.munka, idokorlat_s=10)
        self.assertIn(e["allapot"], ("ok", "homokozo_hiba"), e)          # a kilépés és a minta versenye: legfeljebb hiba
        e = self.ph.futtat(IGAZ_PROGRAM, munka=self.munka, idokorlat_s=10)
        self.assertEqual(e["allapot"], "ok", e)


AL_CLANG_FORMAT = """#!/bin/sh
# ál-clang-format (csak teszt): az utolsó argumentum a fájl; nagybetűsít, és a környezetét a stderr-re írja
for a; do f=$a; done
env >&2
tr a-z A-Z < "$f"
"""


class FormazasTest(_Alap):
    """A3-23: a `clang-format` a fordító-profil alatt, a program-homokozón át fut; sandbox nélkül zárva hibázik."""

    def setUp(self):
        super().setUp()
        self.llvm = self.t / "llvm"
        (self.llvm / "bin").mkdir(parents=True)
        cf = self.llvm / "bin" / "clang-format"
        cf.write_text(AL_CLANG_FORMAT)
        cf.chmod(cf.stat().st_mode | stat.S_IXUSR)
        self.e = eszkoztar.Eszkoztar(None, llvm=self.llvm, sdk=self.t / "sdk")

    def test_a_homokozon_at_fut(self):
        hivasok = []
        eredeti = self.ph.fordit

        def figyelt(parancs, **kw):
            hivasok.append((parancs, kw))
            return eredeti(parancs, **kw)

        with mock.patch.object(self.ph, "fordit", figyelt):
            ok, ki = self.e.formaz("int main(){}\n", homokozo=self.ph)
        self.assertEqual((ok, ki), (True, "INT MAIN(){}\n"))
        parancs, kw = hivasok[0]
        self.assertEqual(parancs[0], str(self.e.clang_format))
        self.assertIn("-fallback-style=none", parancs)
        self.assertEqual(Path(parancs[-1]).parent, kw["munka"])         # a szöveg a munka mappából, nem a stdin-ről
        self.assertEqual(kw["kornyezet"], {})

    def test_sandbox_nelkul_zarva_hibazik(self):
        ph = program.Programhomokozo(sandbox_exec=str(self.t / "nincs-ilyen"))
        ok, ki = self.e.formaz("int main(){}\n", homokozo=ph)
        self.assertFalse(ok)
        self.assertIn("sandbox-exec", ki)

    def test_a_hiba_szovege_atjon(self):
        cf = self.llvm / "bin" / "clang-format"
        cf.write_text("#!/bin/sh\necho 'rossz stílus' >&2\nexit 1\n")
        ok, ki = self.e.formaz("x", homokozo=self.ph)
        self.assertEqual((ok, ki), (False, "rossz stílus"))


if __name__ == "__main__":
    unittest.main()
