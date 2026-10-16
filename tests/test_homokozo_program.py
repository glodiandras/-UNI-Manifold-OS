"""C36a: a program-homokozó (`modulok/homokozo/program.py`, `profil_futtat.sb`, `profil_fordit.sb`) — biztonsági próbák
a valódi `sandbox-exec`-cel. A futtatott „programok” rendszer-binárisok (`/bin/bash`, `/bin/cat`) és a hordozható Python
(a profil szempontjából egy Mach-O program, mint a lefordított C++): a profil szemantikáját mérik, a fordítóra nem
támaszkodnak. A lefordított C++-szal ugyanezt a készletet a `test_cpp_ellenorzes.py` futtatja, ha az eszközlánc megvan.

A kitörések: írás a `munka/`-n kívülre, a vault és a home olvasása, hálózat, exec, fork, jel; idő, memória, kimenet és
lemez áradat; holtpont-mentesség; az árva folyamat hiánya."""
import os
import shlex
import sys
import time
import unittest
from pathlib import Path

from modulok.homokozo import program
from tests.helpers import tmpdir

MACOS = sys.platform == "darwin"
PY = Path(os.path.realpath(sys.executable))
PY_PREFIX = Path(os.path.realpath(sys.base_prefix))


def q(p) -> str:
    """Egy út shell-idézve (a repó útja szóközt tartalmazhat)."""
    return shlex.quote(str(p))


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class FuttatasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ph = program.Programhomokozo()
        if not cls.ph.sandbox_exec or not Path(cls.ph.sandbox_exec).exists():
            raise AssertionError(f"macOS-en a sandbox-exec kötelező: {cls.ph.sandbox_exec}")

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.munka = self.t / "munka"
        self.munka.mkdir()
        self.kint = self.t / "kint"                     # a munkán kívüli hely (a vault / home helyett)
        self.kint.mkdir()
        (self.kint / "titok.txt").write_text("TITOK\n")

    def bash(self, szkript: str, **kw):
        return self.ph.futtat(Path("/bin/bash"), argv=["-c", szkript], munka=self.munka, **kw)

    def python(self, kod: str, **kw):
        kw.setdefault("memoria_mb", 512)
        return self.ph.futtat(PY, argv=["-I", "-B", "-X", "utf8", "-c", kod], munka=self.munka,
                              bin_mappa=PY_PREFIX, **kw)

    def el(self, pid) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    # ---------------------------------------------------------------- F1 · rendes program

    def test_f1_stdin_stdout(self):
        e = self.ph.futtat(Path("/bin/cat"), bemenet=b"hello\n", munka=self.munka)
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual(e["stdout"], b"hello\n")
        self.assertEqual(e["kilepes"], 0)
        self.assertGreater(e["ido_ms"], 0)
        self.assertGreaterEqual(e["csucs_mb"], 0)

    def test_f1_nem_nulla_kilepes_kulon_allapot(self):
        e = self.bash("exit 3")
        self.assertEqual(e["allapot"], "kilepesi_hiba")
        self.assertEqual(e["kilepes"], 3)

    def test_f1_a_kimenet_es_a_hibakimenet_kulon_jon(self):
        e = self.bash("echo ki; echo hiba >&2")
        self.assertEqual(e["stdout"], b"ki\n")
        self.assertEqual(e["stderr"], b"hiba\n")

    def test_f1_ures_kornyezet(self):
        e = self.bash("echo \"HOME=[$HOME] PATH=[$PATH] X=[$X]\"")
        self.assertNotIn(b"/Users", e["stdout"])
        self.assertIn(b"X=[]", e["stdout"])

    def test_f1_a_megadott_kornyezet_atmegy(self):
        e = self.bash("echo \"[$ASAN_OPTIONS]\"", kornyezet={"ASAN_OPTIONS": "symbolize=0"})
        self.assertEqual(e["stdout"], b"[symbolize=0]\n")

    def test_f1_a_munka_a_munkakonyvtar(self):
        e = self.bash("pwd")
        self.assertEqual(e["stdout"].decode().strip(), str(self.munka))

    # ---------------------------------------------------------------- F2 · fájlírás

    def test_f2_irhat_a_munka_mappaba_de_mashova_nem(self):
        e = self.bash(f"echo ok > a.txt; echo tiltott > {q(self.kint / 'kint.txt')}")
        self.assertEqual((self.munka / "a.txt").read_text(), "ok\n")
        self.assertFalse((self.kint / "kint.txt").exists())
        self.assertIn(b"Operation not permitted", e["stderr"])
        self.assertNotEqual(e["kilepes"], 0)

    def test_f2_almappa_a_munkaban_engedett_a_szulo_mappa_nem(self):
        e = self.python("import os\nos.makedirs('b/c')\nopen('b/c/d.txt', 'w').write('x')\n"
                        "for ut in ('../szulo.txt', " + repr(str(self.t / "szulo2.txt")) + "):\n"
                        "    try:\n        open(ut, 'w')\n    except OSError as x:\n        print('TILTOTT', x.errno)\n"
                        "try:\n    os.mkdir(" + repr(str(self.t / "uj")) + ")\nexcept OSError as x:\n    print('TILTOTT', x.errno)\n")
        self.assertTrue((self.munka / "b" / "c" / "d.txt").is_file(), e["stderr"])
        self.assertEqual(e["stdout"].count(b"TILTOTT"), 3, e["stdout"])
        self.assertFalse((self.t / "szulo.txt").exists())
        self.assertFalse((self.t / "szulo2.txt").exists())
        self.assertFalse((self.t / "uj").exists())

    def test_f2_a_munka_mappa_symlinkje_nem_vezet_ki(self):
        e = self.python("import os\nos.symlink(" + repr(str(self.kint)) + ", 'hid')\n"
                        "try:\n    open('hid/atirva.txt', 'w')\nexcept OSError as x:\n    print('TILTOTT', x.errno)")
        self.assertIn(b"TILTOTT", e["stdout"], e)
        self.assertFalse((self.kint / "atirva.txt").exists())

    # ---------------------------------------------------------------- F3 · olvasás a munkán kívül

    def test_f3_a_munkan_kivuli_fajl_nem_olvashato(self):
        e = self.bash(f"read -r x < {q(self.kint / 'titok.txt')}; echo \"[$x]\"")
        self.assertNotIn(b"TITOK", e["stdout"])
        self.assertIn(b"[]", e["stdout"])
        self.assertIn(b"Operation not permitted", e["stderr"])

    def test_f3_a_munkan_kivuli_mappa_nem_listazhato(self):
        e = self.bash(f"for f in {q(self.kint)}/*; do echo \"$f\"; done")
        self.assertNotIn(b"titok.txt", e["stdout"])

    def test_f3_a_home_es_a_vault_nem_olvashato(self):
        home = Path(os.path.expanduser("~"))
        e = self.bash(f"for f in {q(home)}/*; do echo \"$f\"; done; read -r x < /etc/hosts; echo \"[$x]\"")
        self.assertNotIn(str(home / "Documents").encode(), e["stdout"])       # a mappa listája nem olvasható: a minta marad
        self.assertIn(b"[]", e["stdout"])                                     # az /etc/hosts tartalma sem

    # ---------------------------------------------------------------- F4 · hálózat

    def test_f4_tcp_tiltott(self):
        e = self.bash("exec 3<>/dev/tcp/127.0.0.1/9")
        self.assertNotEqual(e["kilepes"], 0)
        self.assertIn(b"Operation not permitted", e["stderr"])

    def test_f4_dns_es_kulso_cim_tiltott(self):
        e = self.bash("exec 3<>/dev/tcp/1.1.1.1/80")
        self.assertNotEqual(e["kilepes"], 0)
        e = self.bash("exec 3<>/dev/tcp/example.com/80")
        self.assertNotEqual(e["kilepes"], 0)

    def test_f4_unix_socket_es_udp_tiltott(self):
        e = self.python("import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
                        "s.sendto(b'x', ('127.0.0.1', 9))\nprint('KILDVE')")
        self.assertNotIn(b"KILDVE", e["stdout"])
        e = self.python("import socket\ns = socket.socket(socket.AF_UNIX)\ns.connect('/var/run/syslog')\nprint('KAPCSOLODOTT')")
        self.assertNotIn(b"KAPCSOLODOTT", e["stdout"])

    # ---------------------------------------------------------------- F5 · exec, fork

    def test_f5_masik_program_inditasa_tiltott(self):
        e = self.bash("/bin/ls /")
        self.assertEqual(e["kilepes"], 126)
        self.assertIn(b"Operation not permitted", e["stderr"])

    def test_f5_fork_tiltott(self):
        e = self.bash("(echo gyermek)")
        self.assertNotIn(b"gyermek", e["stdout"])
        self.assertIn(b"fork", e["stderr"])

    def test_f5_python_subprocess_es_os_system_tiltott(self):
        e = self.python("import os\nprint(os.system('echo x'))")
        self.assertNotIn(b"x\n0", e["stdout"])
        e = self.python("import os\nos.fork()")
        self.assertNotEqual(e["allapot"], "ok")

    # ---------------------------------------------------------------- F6 · jelek

    def test_f6_jel_masik_folyamatnak_tiltott(self):
        e = self.bash("kill -0 1")
        self.assertNotEqual(e["kilepes"], 0)
        self.assertIn(b"Operation not permitted", e["stderr"])

    def test_f6_az_onjel_mukodik_abort_assert(self):
        e = self.bash("kill -ABRT $$")
        self.assertEqual(e["allapot"], "jel")
        self.assertEqual(e["jel"], "SIGABRT")

    # ---------------------------------------------------------------- F7 · idő

    def test_f7_vegtelen_ciklus_idotullepes_nincs_arva(self):
        e = self.bash("while :; do :; done", idokorlat_s=0.6)
        self.assertEqual(e["allapot"], "idotullepes")
        self.assertGreaterEqual(e["ido_ms"], 550)
        self.assertLess(e["ido_ms"], 3000)
        self.assertFalse(self.el(e["pid"]))

    def test_f7_a_cpu_ido_es_a_falido_kulon_jon(self):
        e = self.python("import time\nt = time.time()\nwhile time.time() - t < 0.3: pass")
        self.assertEqual(e["allapot"], "ok")
        self.assertGreater(e["cpu_ms"], 150)
        e = self.python("import time\ntime.sleep(0.4)")
        self.assertLess(e["cpu_ms"], 200)
        self.assertGreater(e["ido_ms"], 380)

    # ---------------------------------------------------------------- F8 · memória

    def test_f8_memoria_korlat(self):
        e = self.python("x = [0] * (10**8)\nprint(len(x))", memoria_mb=256)
        self.assertEqual(e["allapot"], "memoria")
        self.assertGreater(e["csucs_mb"], 200)
        self.assertFalse(self.el(e["pid"]))

    def test_f8_a_korlat_alatt_fut(self):
        e = self.python("x = [0] * (10**6)\nprint(len(x))", memoria_mb=256)
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual(e["stdout"], b"1000000\n")

    # ---------------------------------------------------------------- F9 · kimenet-áradat

    def test_f9_stdout_aradat(self):
        e = self.python("import sys\nwhile True: sys.stdout.buffer.write(b'x' * 1000000)", kimenet_max_kb=1024,
                        idokorlat_s=5)
        self.assertEqual(e["allapot"], "kimenet_tullepes")
        self.assertLessEqual(len(e["stdout"]), 1024 * 1024 + 70000)
        self.assertFalse(self.el(e["pid"]))

    def test_f9_stderr_aradat(self):
        e = self.python("import sys\nwhile True: sys.stderr.buffer.write(b'e' * 1000000)", kimenet_max_kb=1024,
                        stderr_max_kb=64, idokorlat_s=5)
        self.assertEqual(e["allapot"], "kimenet_tullepes")
        self.assertLessEqual(len(e["stderr"]), 64 * 1024)

    def test_f9_a_stderr_levagasa_nem_hiba(self):
        e = self.python("import sys\nsys.stderr.write('e' * 200000)", stderr_max_kb=64, kimenet_max_kb=1024)
        self.assertEqual(e["allapot"], "ok")
        self.assertTrue(e["stderr_levagva"])
        self.assertLessEqual(len(e["stderr"]), 64 * 1024)

    # ---------------------------------------------------------------- F10 · lemez-áradat a munka mappában

    def test_f10_nagy_fajl_iras_korlat(self):
        e = self.python("f = open('nagy.bin', 'wb')\nwhile True: f.write(b'x' * 1000000)", munka_max_mb=4, idokorlat_s=5)
        self.assertEqual(e["allapot"], "iras_korlat", e)
        self.assertLessEqual((self.munka / "nagy.bin").stat().st_size, 5 * 1024 * 1024)

    def test_f10_sok_fajl_iras_korlat(self):
        e = self.python("i = 0\nwhile True:\n    open(f'f{i}', 'w').close()\n    i += 1", munka_max_fajl=100, idokorlat_s=5)
        self.assertEqual(e["allapot"], "iras_korlat", e)
        self.assertLess(len(os.listdir(self.munka)), 20000)

    def test_f10_sok_kicsi_fajl_osszmerete_is_szamit(self):
        e = self.python("i = 0\nwhile True:\n    open(f'f{i}', 'wb').write(b'x' * 100000)\n    i += 1", munka_max_mb=4,
                        munka_max_fajl=100000, idokorlat_s=5)
        self.assertEqual(e["allapot"], "iras_korlat", e)

    # ---------------------------------------------------------------- F11 · holtpont-mentesség

    def test_f11_nagy_bemenet_es_nagy_kimenet_egyszerre(self):
        adat = os.urandom(3_000_000)
        e = self.ph.futtat(Path("/bin/cat"), bemenet=adat, munka=self.munka, kimenet_max_kb=8192, idokorlat_s=10)
        self.assertEqual(e["allapot"], "ok", e["allapot"])
        self.assertEqual(e["stdout"], adat)

    def test_f11_a_bemenetet_nem_olvaso_program_nem_akasztja_meg(self):
        e = self.python("import sys\nsys.stdout.write('kesz')", bemenet=b"y" * 5_000_000, idokorlat_s=10)
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual(e["stdout"], b"kesz")

    def test_f11_a_kimenetet_nem_iro_program_nem_akasztja_meg(self):
        e = self.ph.futtat(Path("/bin/cat"), argv=["/dev/null"], bemenet=b"z" * 4_000_000, munka=self.munka)
        self.assertEqual(e["allapot"], "ok")

    # ---------------------------------------------------------------- F12 · futási hibák nem a homokozó hibái

    def test_f12_szegmentacios_hiba(self):
        e = self.python("import ctypes\nctypes.string_at(0)")
        self.assertEqual(e["allapot"], "jel")
        self.assertEqual(e["jel"], "SIGSEGV")

    def test_f12_lebegopontos_kivetel_jel(self):
        e = self.python("import os, signal\nos.kill(os.getpid(), signal.SIGFPE)")
        self.assertEqual((e["allapot"], e["jel"]), ("jel", "SIGFPE"))

    # ---------------------------------------------------------------- F13 · a leállítás után tiszta

    def test_f13_a_leallitott_futas_utan_a_kovetkezo_tiszta(self):
        e1 = self.bash("while :; do :; done", idokorlat_s=0.4)
        self.assertEqual(e1["allapot"], "idotullepes")
        e2 = self.ph.futtat(Path("/bin/cat"), bemenet=b"ujra\n", munka=self.munka)
        self.assertEqual((e2["allapot"], e2["stdout"]), ("ok", b"ujra\n"))
        self.assertFalse(self.el(e1["pid"]))

    # ---------------------------------------------------------------- megszakítás

    def test_megszakitas_leallitja_a_futast_nincs_arva(self):
        t0 = time.monotonic()
        e = self.bash("while :; do :; done", idokorlat_s=30, megszakit=lambda: time.monotonic() - t0 > 0.3)
        self.assertEqual(e["allapot"], "megszakitva")
        self.assertLess(e["ido_ms"], 3000)
        self.assertFalse(self.el(e["pid"]))
        self.assertIn("megszakít", e["uzenet"])

    def test_megszakitas_a_stdin_irasa_kozben_is_mukodik(self):
        t0 = time.monotonic()
        e = self.python("import time\ntime.sleep(30)", bemenet=b"y" * 10_000_000, idokorlat_s=30,
                        megszakit=lambda: time.monotonic() - t0 > 0.3)
        self.assertEqual(e["allapot"], "megszakitva")
        self.assertFalse(self.el(e["pid"]))

    def test_a_nem_teljesulo_megszakitas_nem_zavar(self):
        e = self.ph.futtat(Path("/bin/cat"), bemenet=b"x\n", munka=self.munka, megszakit=lambda: False)
        self.assertEqual(e["allapot"], "ok")

    # ---------------------------------------------------------------- indítási hibák

    def test_hianyzo_sandbox_exec_zarva_hibazik(self):
        ph = program.Programhomokozo(sandbox_exec="/nincs/ilyen/sandbox-exec")
        e = ph.futtat(Path("/bin/cat"), munka=self.munka)
        self.assertEqual(e["allapot"], "homokozo_hiba")
        self.assertIn("elzáratlan futtatás nincs", e["uzenet"])
        self.assertFalse(ph.elerheto()[0])

    def test_hianyzo_program_homokozo_hiba(self):
        e = self.ph.futtat(self.t / "nincs-ilyen-program", munka=self.munka)
        self.assertEqual(e["allapot"], "homokozo_hiba")
        self.assertIn("nem található", e["uzenet"])

    def test_elerheto_onproba(self):
        ok, uzenet = self.ph.elerheto()
        self.assertTrue(ok, uzenet)


@unittest.skipUnless(MACOS, "[indokolt] a homokozó a macOS sandbox-exec-jére épül; más rendszeren nem fut")
class FordtasTest(unittest.TestCase):
    """A fordító-profil: a „fordító” itt a `/bin` (bash), az eszközlánc gyökere a `/bin`, az SDK és a pótfejléc egy-egy
    ideiglenes mappa; a profil szemantikáját méri, a valódi clang++-ot a `test_cpp_ellenorzes.py` próbálja."""

    @classmethod
    def setUpClass(cls):
        cls.ph = program.Programhomokozo()

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.munka = self.t / "munka"
        self.munka.mkdir()
        self.sdk = self.t / "sdk"
        self.sdk.mkdir()
        (self.sdk / "fejlec.h").write_text("SDK-FEJLEC\n")
        self.pot = self.t / "pot"
        self.pot.mkdir()
        (self.pot / "pot.h").write_text("POT-FEJLEC\n")
        self.kint = self.t / "kint"
        self.kint.mkdir()
        (self.kint / "titok.txt").write_text("TITOK\n")

    def f(self, szkript: str, **kw):
        return self.ph.fordit(["/bin/bash", "-c", szkript], munka=self.munka, llvm=Path("/bin"), llvm_bin=Path("/bin"),
                              sdk=self.sdk, pot=self.pot, **kw)

    def test_c4_rendes_futas_a_munkaban_ir(self):
        e = self.f("echo kesz > prog; echo uzenet >&2")
        self.assertEqual(e["allapot"], "ok", e)
        self.assertEqual((self.munka / "prog").read_text(), "kesz\n")
        self.assertEqual(e["stderr"], "uzenet\n")
        self.assertEqual(e["kilepes"], 0)

    def test_olvashatja_az_sdk_t_es_a_potfejlecet_de_a_vaultot_nem(self):
        e = self.f(f"read -r a < {q(self.sdk / 'fejlec.h')}; read -r b < {q(self.pot / 'pot.h')}; echo \"$a $b\"; "
                   f"read -r c < {q(self.kint / 'titok.txt')}; echo \"[$c]\"")
        self.assertIn("SDK-FEJLEC POT-FEJLEC", e["stdout"])
        self.assertNotIn("TITOK", e["stdout"])

    def test_c1_include_a_munkan_kivulre_nem_lat(self):
        e = self.f(f"read -r c < {q(self.kint / 'titok.txt')}")
        self.assertNotEqual(e["kilepes"], 0)
        self.assertIn("Operation not permitted", e["stderr"])
        e = self.f("read -r c < /etc/hosts")
        self.assertNotEqual(e["kilepes"], 0)

    def test_c2_kimenet_a_munkan_kivulre_nem_irhato(self):
        e = self.f(f"echo x > {q(self.kint / 'prog')}; echo y > {q(self.sdk / 'prog')}; echo z > {q(self.pot / 'prog')}")
        self.assertFalse((self.kint / "prog").exists())
        self.assertFalse((self.sdk / "prog").exists())
        self.assertFalse((self.pot / "prog").exists())
        self.assertNotEqual(e["kilepes"], 0)

    def test_c2_halozat_tiltott(self):
        e = self.f("exec 3<>/dev/tcp/127.0.0.1/9")
        self.assertNotEqual(e["kilepes"], 0)
        self.assertIn("Operation not permitted", e["stderr"])

    def test_exec_csak_az_eszkozlanc_mappabol(self):
        self.assertEqual(self.f("/bin/ls / > /dev/null")["kilepes"], 0)              # a /bin alatt: engedett (gyermekfolyamat)
        e = self.f("/usr/bin/true")
        self.assertNotEqual(e["kilepes"], 0)
        self.assertIn("Operation not permitted", e["stderr"])

    def test_jel_masik_folyamatnak_tiltott(self):
        self.assertNotEqual(self.f("kill -0 1")["kilepes"], 0)

    def test_c3_idokorlat_leallitja_nincs_arva(self):
        e = self.f("while :; do :; done", idokorlat_s=0.5)
        self.assertEqual(e["allapot"], "idotullepes")
        with self.assertRaises(ProcessLookupError):
            os.kill(e["pid"], 0)

    def test_a_kornyezet_csak_a_megadott(self):
        e = self.f("echo \"[$TMPDIR][$HOME][$PATH]\"", kornyezet={"TMPDIR": str(self.munka)})
        # a bash üres PATH-nál a saját beépített alapértelmezését használja: az nem örökölt érték
        self.assertTrue(e["stdout"].startswith(f"[{self.munka}][]["), e["stdout"])
        self.assertNotIn("/Users", e["stdout"])
        self.assertNotIn("/Volumes", e["stdout"].split("][")[2])

    def test_kimenet_aradat_ol(self):
        e = self.f("/bin/dd if=/dev/urandom bs=1m count=50 2>/dev/null", kimenet_max_kb=256, idokorlat_s=5)
        self.assertEqual(e["allapot"], "kimenet_tullepes")

    def test_nem_nulla_kilepes_hiba_allapot_es_a_szoveg_atjon(self):
        e = self.f("echo 'forras.cpp:3:5: error: valami' >&2; exit 1")
        self.assertEqual(e["allapot"], "hiba")
        self.assertIn("forras.cpp:3:5: error", e["stderr"])

    def test_a_fordito_megszakithato(self):
        t0 = time.monotonic()
        e = self.f("while :; do :; done", idokorlat_s=30, megszakit=lambda: time.monotonic() - t0 > 0.3)
        self.assertEqual(e["allapot"], "megszakitva")
        with self.assertRaises(ProcessLookupError):
            os.kill(e["pid"], 0)

    def test_hianyzo_sandbox_exec_zarva_hibazik(self):
        ph = program.Programhomokozo(sandbox_exec="/nincs/ilyen")
        e = ph.fordit(["/bin/true"], munka=self.munka, llvm=Path("/bin"), llvm_bin=Path("/bin"), sdk=self.sdk, pot=self.pot)
        self.assertEqual(e["allapot"], "homokozo_hiba")


if __name__ == "__main__":
    unittest.main()
