"""C36a: a kimenet-összevetés (`modulok/cpp/osszevet.py`) és a fordító- és sanitizer-kimenet elemzése
(`modulok/cpp/diagnosztika.py`). A minták a valódi eszközláncon mért kimenetek (clang 23.1.2, macOS 27, 2026-10-04)."""
import unittest

from modulok.cpp import diagnosztika as D
from modulok.cpp import osszevet as O

CLANG = """In file included from /m/munka/forras.cpp:1:
/m/munka/forras.cpp:5:5: error: use of undeclared identifier 'y'
    5 |     y = 3;
      |     ^
/m/munka/forras.cpp:7:7: warning: unused variable 'z' [-Wunused-variable]
    7 |   int z;
      |       ^
/m/munka/forras.cpp:7:7: note: declared here
/Volumes/Work/Manifold-OS v2/runtime/sdk/usr/include/c++/v1/vector:100:3: warning: valami a fejlécben [-Wfoo]
2 warnings and 1 error generated.
"""

LINKER = """ld64.lld: error: undefined symbol: foo(int)
>>> referenced by /m/munka/forras-1a2b3c.o:(symbol main+0x20)

ld64.lld: error: undefined symbol: __stack_chk_fail
>>> referenced by /m/munka/forras.cpp
>>>               /m/munka/forras-1a2b3c.o:(symbol main+0x1d4)
"""

ASAN_HEAP = """=================================================================
==13439==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x60200000091c at pc 0x0001047148dc bp 0x00016b6eb430 sp 0x00016b6eb428
READ of size 4 at 0x60200000091c thread T0
    #0 0x0001047148d8  (/Volumes/Work/Manifold-OS v2/var/tmp/x/m/p-hibakereso:arm64+0x1000008d8)
    #1 0x000196513e84  (/usr/lib/dyld:arm64e+0x31e84)

0x60200000091c is located 0 bytes after 12-byte region [0x602000000910,0x60200000091c)
allocated by thread T0 here:
    #0 0x000104b596cc  (/Volumes/Work/Manifold-OS v2/runtime/llvm/lib/clang/23/lib/darwin/libclang_rt.asan_osx_dynamic.dylib:arm64+0x656cc)
    #1 0x000104714818  (/Volumes/Work/Manifold-OS v2/var/tmp/x/m/p-hibakereso:arm64+0x100000818)

SUMMARY: AddressSanitizer: heap-buffer-overflow (/Volumes/Work/Manifold-OS v2/var/tmp/x/m/p-hibakereso:arm64+0x1000008d8)
Shadow bytes around the buggy address:
==13439==ABORTING
"""

ASAN_STACK = """AddressSanitizer:DEADLYSIGNAL
=================================================================
==13577==ERROR: AddressSanitizer: stack-overflow on address 0x00016a8f3ff0 (pc 0x000104d106c8 bp 0x00016a8f4000 sp 0x00016a8f4000 T0)
    #0 0x000104d106c8  (/x/m/p-hibakereso:arm64+0x1000006c8)

SUMMARY: AddressSanitizer: stack-overflow (/x/m/p-hibakereso:arm64+0x1000006c8)
==13577==ABORTING
"""

ASAN_UAF = """=================================================================
==13645==ERROR: AddressSanitizer: heap-use-after-free on address 0x602000000910 at pc 0x000100c8c788 bp 0x00016f173500 sp 0x00016f1734f8
READ of size 4 at 0x602000000910 thread T0
    #0 0x000100c8c784 in main+0x18 (/x/m/p-hibakereso:arm64+0x100000784)
    #1 0x000196513e84  (/usr/lib/dyld:arm64e+0x31e84)
"""

UBSAN = """/private/tmp/x/m2-tulindexeles_verem/f.cpp:2:82: runtime error: index 3 out of bounds for type 'int[3]'
SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior /private/tmp/x/m2-tulindexeles_verem/f.cpp:2:82
"""

ASSERT = "Assertion failed: (1 == 2), function main, file f.cpp, line 2.\n"


class NormalTest(unittest.TestCase):
    def test_normalizalas(self):
        self.assertEqual(O.normal("a  \r\nb\t\n\n\n"), ["a", "b"])
        self.assertEqual(O.normal("  a"), ["  a"])
        self.assertEqual(O.normal(""), [])
        self.assertEqual(O.normal("\n\n  \n"), [])
        self.assertEqual(O.normal("a\rb"), ["a", "b"])

    def test_egyezik(self):
        for v, k in (("1\n", "1"), ("", "\n"), ("a  \nb\n", "a\nb"), ("x\n\n\n", "x"), ("a\r\nb\r\n", "a\nb\n")):
            self.assertTrue(O.egyezik(v, k), (v, k))

    def test_nem_egyezik(self):
        for v, k in (("1", "2"), ("a\nb", "a\n\nb"), ("a b", "a  b"), ("  a", "a"), ("A", "a"), ("1\n2", "1"), ("", "0")):
            self.assertFalse(O.egyezik(v, k), (v, k))


class DiffTest(unittest.TestCase):
    def test_egyezo_kimenetnek_nincs_diffje(self):
        d = O.diff("1\n2\n", "1\n2")
        self.assertTrue(d["egyezik"])
        self.assertEqual(d["sorok"], [])
        self.assertIsNone(d["elso_elteres"])
        self.assertEqual(d["elteres_db"], 0)

    def test_egy_sor_cserelve(self):
        d = O.diff("a\nb\nc\n", "a\nX\nc\n")
        self.assertFalse(d["egyezik"])
        self.assertEqual((d["elso_elteres"], d["elteres_db"]), (2, 1))
        self.assertEqual([r["tipus"] for r in d["sorok"]], ["egyenlo", "csere", "egyenlo"])
        csere = d["sorok"][1]
        self.assertEqual((csere["vart"], csere["kapott"], csere["vart_sor"], csere["kapott_sor"]), ("b", "X", 2, 2))

    def test_hianyzo_es_felesleges_sor(self):
        d = O.diff("a\nb\nc\n", "a\nc\n")
        self.assertEqual([r["tipus"] for r in d["sorok"]], ["egyenlo", "torolt", "egyenlo"])
        self.assertEqual((d["sorok"][1]["vart"], d["sorok"][1]["kapott"]), ("b", None))
        d = O.diff("a\nc\n", "a\nb\nc\n")
        self.assertEqual([r["tipus"] for r in d["sorok"]], ["egyenlo", "beszurt", "egyenlo"])
        self.assertEqual((d["sorok"][1]["vart"], d["sorok"][1]["kapott"], d["sorok"][1]["kapott_sor"]), (None, "b", 2))

    def test_a_hosszu_egyezo_szakasz_osszecsukva(self):
        vart = "\n".join(str(i) for i in range(30)) + "\nvege\n"
        kapott = "\n".join(str(i) for i in range(30)) + "\nMASIK\n"
        d = O.diff(vart, kapott, kornyezet=2)
        tipusok = [r["tipus"] for r in d["sorok"]]
        self.assertEqual(tipusok, ["kihagyva", "egyenlo", "egyenlo", "csere"])
        self.assertEqual(d["sorok"][0]["db"], 28)
        self.assertEqual(d["elso_elteres"], 31)

    def test_ures_kapott_kimenet(self):
        d = O.diff("1\n2\n", "")
        self.assertFalse(d["egyezik"])
        self.assertEqual([r["tipus"] for r in d["sorok"]], ["torolt", "torolt"])
        self.assertEqual((d["vart_sor_db"], d["kapott_sor_db"]), (2, 0))

    def test_a_sorok_hossza_korlatos(self):
        d = O.diff("a" * 1000 + "\n", "b\n", max_hossz=50)
        sor = d["sorok"][0]["vart"]
        self.assertLessEqual(len(sor), 51)
        self.assertTrue(sor.endswith("…"))

    def test_a_sorok_szama_korlatos(self):
        vart = "\n".join(f"v{i}" for i in range(500))
        kapott = "\n".join(f"k{i}" for i in range(500))
        d = O.diff(vart, kapott, max_sor=200)
        self.assertEqual(len(d["sorok"]), 200)
        self.assertTrue(d["levagva"])
        self.assertEqual(d["elteres_db"], 500)

    def test_a_vegi_szokoz_nem_elteres(self):
        self.assertTrue(O.diff("a \nb\t\n", "a\nb")["egyezik"])


class ForditoKimenetTest(unittest.TestCase):
    def setUp(self):
        self.d = D.fordito(CLANG, "forras.cpp")

    def test_hibak_figyelmeztetesek_megjegyzesek(self):
        szintek = [x["szint"] for x in self.d["diagnosztika"]]
        self.assertEqual(szintek, ["error", "warning", "note", "warning"])
        self.assertEqual((self.d["hiba_db"], self.d["figyelmeztetes_db"]), (1, 2))

    def test_a_hely_es_az_uzenet(self):
        h = self.d["diagnosztika"][0]
        self.assertEqual((h["fajl"], h["sor"], h["oszlop"]), ("forras.cpp", 5, 5))
        self.assertEqual(h["uzenet"], "use of undeclared identifier 'y'")
        self.assertTrue(h["sajat"])

    def test_a_figyelmeztetes_kapcsoloja_kulon_mezo(self):
        f = self.d["diagnosztika"][1]
        self.assertEqual(f["kapcsolo"], "-Wunused-variable")
        self.assertEqual(f["uzenet"], "unused variable 'z'")

    def test_a_masik_fajl_nem_sajat_es_a_teljes_utat_megtartja(self):
        f = self.d["diagnosztika"][3]
        self.assertFalse(f["sajat"])
        self.assertTrue(f["fajl"].endswith("c++/v1/vector"))
        self.assertIn("Manifold-OS v2", f["fajl"])                    # a szóközös út is egyben marad

    def test_a_forraskod_idezet_es_az_osszegzes_nem_diagnosztika(self):
        self.assertEqual(len(self.d["diagnosztika"]), 4)

    def test_vegzetes_hiba_hianyzo_fejlec(self):
        d = D.fordito("/m/f.cpp:1:10: fatal error: 'nincs.h' file not found\n    1 | #include <nincs.h>\n", "f.cpp")
        self.assertEqual(d["diagnosztika"][0]["szint"], "error")
        self.assertEqual(d["hiba_db"], 1)
        self.assertEqual(d["diagnosztika"][0]["uzenet"], "'nincs.h' file not found")

    def test_linker_hibak_hely_nelkul_a_reszletekkel(self):
        d = D.fordito(LINKER, "forras.cpp")
        self.assertEqual(len(d["diagnosztika"]), 2)
        h = d["diagnosztika"][0]
        self.assertEqual((h["szint"], h["fajl"], h["sor"]), ("error", None, None))
        self.assertEqual(h["uzenet"], "undefined symbol: foo(int)")
        self.assertEqual(len(h["reszletek"]), 1)
        self.assertEqual(len(d["diagnosztika"][1]["reszletek"]), 2)
        self.assertEqual(d["hiba_db"], 2)

    def test_levagas(self):
        sok = "".join(f"/m/f.cpp:{i}:1: warning: w{i}\n" for i in range(1, 301))
        d = D.fordito(sok, "f.cpp", max_db=100)
        self.assertEqual(len(d["diagnosztika"]), 100)
        self.assertTrue(d["levagva"])
        self.assertEqual(d["figyelmeztetes_db"], 300)

    def test_ures_es_ertelmezhetetlen_kimenet(self):
        for szoveg in ("", "valami nem diagnosztika\n", "clang: error: no such file or directory: 'x.cpp'\n"):
            d = D.fordito(szoveg, "f.cpp")
            self.assertIsInstance(d["diagnosztika"], list)
        self.assertEqual(D.fordito("clang: error: no such file or directory: 'x.cpp'\n", "f.cpp")["hiba_db"], 1)

    def test_az_hibas_sor_szama_a_valodi_hely(self):
        self.assertEqual([x["sor"] for x in self.d["diagnosztika"] if x["szint"] == "error"], [5])

    def test_a_tippelo_kapcsolo_nelkuli_figyelmeztetes(self):
        d = D.fordito("/m/f.cpp:3:1: warning: control reaches end of non-void function\n", "f.cpp")
        self.assertIsNone(d["diagnosztika"][0]["kapcsolo"])


class JelentesTest(unittest.TestCase):
    def test_asan_heap_buffer_overflow(self):
        j = D.jelentes(ASAN_HEAP, "f.cpp", bin_nev="p-hibakereso")
        self.assertEqual((j["forras"], j["fajta"]), ("asan", "heap-buffer-overflow"))
        self.assertEqual(j["hozzaferes"], "READ of size 4")
        self.assertEqual(j["leiras"], "heap-buffer-overflow (READ of size 4)")
        self.assertEqual([k["index"] for k in j["keretek"]], [0, 1])               # csak az első (a hibát jelző) verem
        self.assertEqual(j["keretek"][0]["offset"], 0x1000008D8)
        self.assertTrue(j["keretek"][0]["sajat_modul"])
        self.assertFalse(j["keretek"][1]["sajat_modul"])
        self.assertIn("Manifold-OS v2", j["keretek"][0]["modul"])                   # szóközös út is egyben

    def test_asan_stack_overflow_es_deadlysignal(self):
        j = D.jelentes(ASAN_STACK, "f.cpp", bin_nev="p-hibakereso")
        self.assertEqual(j["fajta"], "stack-overflow")
        self.assertIsNone(j["hozzaferes"])
        self.assertEqual(j["keretek"][0]["offset"], 0x1000006C8)

    def test_asan_use_after_free_fuggvenynevvel(self):
        j = D.jelentes(ASAN_UAF, "f.cpp", bin_nev="p-hibakereso")
        self.assertEqual(j["fajta"], "heap-use-after-free")
        self.assertEqual(j["keretek"][0]["fuggveny"], "main")

    def test_ubsan_a_forrassor_a_jelentesben(self):
        j = D.jelentes(UBSAN, "f.cpp")
        self.assertEqual((j["forras"], j["fajta"]), ("ubsan", "ub"))
        self.assertEqual(j["leiras"], "index 3 out of bounds for type 'int[3]'")
        self.assertEqual((j["fajl"], j["sor"], j["oszlop"]), ("f.cpp", 2, 82))

    def test_ubsan_masik_fajl_teljes_uttal(self):
        j = D.jelentes("/sdk/include/x.h:9:4: runtime error: division by zero\n", "f.cpp")
        self.assertEqual(j["fajl"], "/sdk/include/x.h")
        self.assertFalse(j["sajat"])

    def test_assert(self):
        j = D.jelentes(ASSERT, "f.cpp")
        self.assertEqual((j["forras"], j["fajta"], j["fajl"], j["sor"], j["fuggveny"]), ("assert", "assert", "f.cpp", 2, "main"))
        self.assertEqual(j["leiras"], "1 == 2")

    def test_nincs_jelentes(self):
        for szoveg in ("", "valami hibaüzenet\n", "runtime error: nincs hely\n", "ERROR: nem sanitizer\n"):
            self.assertIsNone(D.jelentes(szoveg, "f.cpp"), szoveg)

    def test_asan_az_ubsan_elott(self):
        j = D.jelentes(UBSAN + ASAN_HEAP, "f.cpp", bin_nev="p-hibakereso")
        self.assertEqual(j["forras"], "asan")


class SzimbolizalasTest(unittest.TestCase):
    def jelentes(self):
        return D.jelentes(ASAN_HEAP, "f.cpp", bin_nev="p-hibakereso")

    def test_a_szimbolizalo_parancs_cimei_a_sajat_modul_keretei(self):
        j = self.jelentes()
        self.assertEqual(D.szimbolizalando_cimek(j), ["0x1000008d8"])

    def test_az_elso_sajat_fajlbeli_keret_adja_a_sort(self):
        j = self.jelentes()
        D.szimbolizal(j, "f.cpp", "int* std::__1::__libcpp_allocate<int>(unsigned long)\n/sdk/__new/allocate.h:60:28\n"
                      "std::__1::vector<int>::operator[](unsigned long)\n/sdk/__vector/vector.h:300:5\n"
                      "main\n/m/munka/f.cpp:4:12\n\n")
        self.assertEqual((j["sor"], j["oszlop"], j["fuggveny"]), (4, 12, "main"))
        self.assertEqual(j["fajl"], "f.cpp")
        self.assertEqual(j["keretek"][0]["fuggveny"], "main")

    def test_ha_nincs_sajat_fajl_az_elso_keret_marad_de_sor_nincs(self):
        j = self.jelentes()
        D.szimbolizal(j, "f.cpp", "std::__1::foo()\n/sdk/x.h:1:1\n\n")
        self.assertIsNone(j["sor"])
        self.assertEqual(j["keretek"][0]["fajl"], "/sdk/x.h")

    def test_ismeretlen_hely_nem_ront(self):
        j = self.jelentes()
        D.szimbolizal(j, "f.cpp", "main\n??:0:0\n\n")
        self.assertIsNone(j["sor"])
        self.assertIsNone(j["keretek"][0]["fajl"])

    def test_ures_szimbolizalo_kimenet(self):
        j = self.jelentes()
        D.szimbolizal(j, "f.cpp", "")
        self.assertIsNone(j["sor"])


if __name__ == "__main__":
    unittest.main()
