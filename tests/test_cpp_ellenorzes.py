"""C36a: a C++ ellenőrzés (`modulok/cpp/ellenorzes.py`) a VALÓDI eszközláncon (LLVM + SDK a `runtime/` alatt) és a valódi
`sandbox-exec`-cel: fordítás a fordító-profil alatt, tesztenként futtatás a futtató profil alatt, eredmény-események.

A tesztek csak olvasnak a `runtime/llvm` és `runtime/sdk` mappából; minden kimenet az álgyökér `var/tmp`-jébe megy. Ha az
eszközlánc nincs telepítve (`bin/mos cpp telepit --igen`), a tesztek `[indokolt]` kihagyással futnak."""
import os
import sys
import unittest
from pathlib import Path

from core import config
from core import cpp_teszt as T
from modulok.cpp import ellenorzes, eszkoztar
from tests.helpers import alg_gyoker, tmpdir

MACOS = sys.platform == "darwin"
VALODI = config.load()
_E = eszkoztar.Eszkoztar(VALODI)
VAN = MACOS and _E.kesz() and _E.sdk_tbd_igazitva()
OK_SKIP = "[indokolt] nincs C++ eszköztár vagy sandbox-exec (bin/mos cpp telepit --igen; csak macOS)"

OSSZEG = """#include <iostream>
int main() {
    int n;
    std::cin >> n;
    long long s = 0;
    for (int i = 0; i < n; i++) {
        int x;
        std::cin >> x;
        s += x;
    }
    std::cout << s << "\\n";
}
"""


def teszt(bemenet: str, kimenet: str, ido: float | None = None, cim: str | None = None, n: int = 1) -> T.Teszt:
    return T.Teszt(n, n, cim, bemenet, kimenet, ido)


@unittest.skipUnless(VAN, OK_SKIP)
class EllenorzesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.t = Path(os.path.realpath(cls._t.name))
        root = alg_gyoker(str(cls.t)).resolve()
        cls.cfg = config.load({"MOS_ROOT": str(root), "HOME": str(cls.t / "home"), "MOS_LLVM": str(VALODI.path("llvm")),
                               "MOS_SDK": str(VALODI.path("sdk")), "MOS_RUNTIME": str(VALODI.path("runtime"))})
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def setUp(self):
        self.esem: list[dict] = []
        self.kint = self.t / "kint"
        self.kint.mkdir(exist_ok=True)
        (self.kint / "titok.txt").write_text("TITOK\n")

    def fut(self, forras: str, tesztek: list[T.Teszt], mod="gyors", nev="Összeg.cpp", **kw) -> dict:
        cpp = self.t / nev
        cpp.write_text(forras, encoding="utf-8")
        e = ellenorzes.Ellenorzes(self.cfg, esemeny=self.esem.append, **kw)
        return e.fut(cpp, tesztek, mod)

    def teszt_esemenyek(self):
        return [x["teszt"] for x in self.esem if x["szakasz"] == "teszt"]

    # ---------------------------------------------------------------- az átmenő megoldás

    def test_atmeno_megoldas_esemenyek_sorrendje(self):
        r = self.fut(OSSZEG, [teszt("3\n10 20 30\n", "60\n", n=1), teszt("1\n5\n", "5\n", n=2)])
        self.assertTrue(r["atment"])
        self.assertEqual((r["tesztek_db"], r["atment_db"]), (2, 2))
        self.assertTrue(r["fordit_ok"])
        self.assertEqual([x["szakasz"] for x in self.esem], ["indul", "fordit_kesz", "teszt", "teszt", "kesz"])
        t = self.teszt_esemenyek()
        self.assertEqual([x["allapot"] for x in t], ["atment", "atment"])
        self.assertEqual([x["sorszam"] for x in t], [1, 2])
        self.assertGreater(t[0]["ido_ms"], 0)
        self.assertGreaterEqual(t[0]["csucs_mb"], 0)
        self.assertEqual(len(r["hash"]), 64)

    def test_az_indul_esemeny_a_modot_es_a_teszt_darabszamot_adja(self):
        self.fut(OSSZEG, [teszt("1\n1\n", "1\n")])
        e = self.esem[0]
        self.assertEqual((e["szakasz"], e["mod"], e["tesztek_db"]), ("indul", "gyors", 1))
        self.assertEqual(e["cpp"], "Összeg.cpp")

    def test_a_futas_mappa_a_vegen_torlodik(self):
        self.fut(OSSZEG, [teszt("1\n1\n", "1\n")])
        mappa = self.cfg.path("tmp") / "cpp"
        self.assertEqual([p.name for p in mappa.glob("futas-*")] if mappa.exists() else [], [])

    def test_bits_stdcpp_es_a_c17_fejlecek(self):
        forras = ('#include <bits/stdc++.h>\nusing namespace std;\nint main() {\n    optional<int> o = 3;\n'
                  '    variant<int, string> v = string("x");\n    filesystem::path p("/a/b.txt");\n'
                  '    regex re("a+");\n    cout << *o << p.filename().string() << regex_match("aaa", re) << get<1>(v) << "\\n";\n}\n')
        r = self.fut(forras, [teszt("", "3b.txt1x\n")])
        self.assertTrue(r["atment"], self.esem)

    # ---------------------------------------------------------------- hibás kimenet, diffel

    def test_hibas_kimenet_diffel(self):
        r = self.fut(OSSZEG, [teszt("3\n10 20 30\n", "61\n")])
        self.assertFalse(r["atment"])
        t = self.teszt_esemenyek()[0]
        self.assertEqual(t["allapot"], "hibas_kimenet")
        self.assertEqual(t["diff"]["elso_elteres"], 1)
        csere = t["diff"]["sorok"][0]
        self.assertEqual((csere["vart"], csere["kapott"]), ("61", "60"))
        self.assertEqual(t["stdout_kivonat"], "60\n")

    def test_az_eltero_teszt_nem_viszi_a_tobbit(self):
        r = self.fut(OSSZEG, [teszt("1\n1\n", "2\n", n=1), teszt("1\n1\n", "1\n", n=2)])
        self.assertEqual([x["allapot"] for x in self.teszt_esemenyek()], ["hibas_kimenet", "atment"])
        self.assertEqual((r["tesztek_db"], r["atment_db"], r["atment"]), (2, 1, False))

    def test_a_sorvegi_szokoz_es_a_zaro_ures_sor_nem_hiba(self):
        r = self.fut('#include <iostream>\nint main() { std::cout << "1  \\n\\n\\n"; }\n', [teszt("", "1\n")])
        self.assertTrue(r["atment"])

    # ---------------------------------------------------------------- fordítási hiba

    def test_fordítasi_hiba_a_helyes_sorral_es_nincs_futas(self):
        r = self.fut("#include <iostream>\nint main() {\n    int x = ;\n}\n", [teszt("", "")])
        self.assertFalse(r["fordit_ok"])
        self.assertFalse(r["atment"])
        fk = [x for x in self.esem if x["szakasz"] == "fordit_kesz"][0]["fordit"]
        self.assertFalse(fk["ok"])
        hiba = [d for d in fk["diagnosztika"] if d["szint"] == "error"][0]
        self.assertEqual((hiba["fajl"], hiba["sor"]), ("Összeg.cpp", 3))
        self.assertEqual(self.teszt_esemenyek(), [])
        self.assertEqual(self.esem[-1]["szakasz"], "kesz")

    def test_figyelmeztetes_nem_hiba_de_latszik(self):
        r = self.fut("#include <iostream>\nint main() {\n    int nem_hasznalt;\n    std::cout << 1;\n}\n",
                     [teszt("", "1\n")])
        self.assertTrue(r["atment"])
        fk = [x for x in self.esem if x["szakasz"] == "fordit_kesz"][0]["fordit"]
        self.assertGreaterEqual(fk["figyelmeztetes_db"], 1)
        self.assertEqual(fk["hiba_db"], 0)
        figy = [d for d in fk["diagnosztika"] if d["szint"] == "warning"][0]
        self.assertEqual((figy["sor"], figy["kapcsolo"]), (3, "-Wunused-variable"))

    def test_hianyzo_fejlec_hiba(self):
        r = self.fut('#include <nincs_ilyen_fejlec.h>\nint main() {}\n', [teszt("", "")])
        self.assertFalse(r["fordit_ok"])
        fk = [x for x in self.esem if x["szakasz"] == "fordit_kesz"][0]["fordit"]
        self.assertIn("file not found", fk["diagnosztika"][0]["uzenet"])

    def test_vegtelen_constexpr_nem_akasztja_meg_a_fordito(self):
        forras = "constexpr int f(int n) { return f(n + 1); }\nconstexpr int x = f(0);\nint main() { return x; }\n"
        r = self.fut(forras, [teszt("", "")])
        self.assertFalse(r["fordit_ok"])
        self.assertLess(r["ms"], 20000)

    def test_a_forras_a_vaulton_kivulrol_nem_olvashat_be(self):
        """C1: `#include`, `#embed` és `__has_include` a munkán kívülre nem lát: a fordító profilja az olvasást tiltja (a meglévő,
        de tiltott fájl „cannot open file … Operation not permitted” hibát ad; a nem létező fájl `__has_include`-ja hamis)."""
        for nev, forras in (("include", f'#include "{self.kint}/titok.txt"\nint main() {{}}\n'),
                            ("has_include", f'#if __has_include("{self.kint}/titok.txt")\n#endif\nint main() {{}}\n'),
                            ("embed", f'static const char a[] = {{\n#embed "{self.kint}/titok.txt"\n, 0}};\nint main() {{}}\n')):
            self.esem.clear()
            r = self.fut(forras, [teszt("", "")])
            self.assertFalse(r["fordit_ok"], nev)
            fk = [x for x in self.esem if x["szakasz"] == "fordit_kesz"][0]["fordit"]
            szoveg = " ".join(d["uzenet"] for d in fk["diagnosztika"]) + fk["kivonat"]
            self.assertNotIn("TITOK", szoveg, nev)
            self.assertTrue("Operation not permitted" in szoveg or "file not found" in szoveg, (nev, szoveg))
        self.esem.clear()
        r = self.fut('#if __has_include("/nincs/ilyen/fajl.h")\n#define X 1\n#else\n#define X 0\n#endif\n'
                     '#include <iostream>\nint main() { std::cout << X; }\n', [teszt("", "0\n")])
        self.assertTrue(r["atment"], self.esem)

    # ---------------------------------------------------------------- futási hibák

    def test_assert_futasi_hiba_a_sorral(self):
        r = self.fut('#include <cassert>\nint main() {\n    assert(1 == 2);\n}\n', [teszt("", "")])
        t = self.teszt_esemenyek()[0]
        self.assertEqual(t["allapot"], "futasi_hiba")
        self.assertEqual(t["jel"], "SIGABRT")
        self.assertEqual((t["jelentes"]["forras"], t["jelentes"]["sor"]), ("assert", 3))
        self.assertFalse(r["atment"])

    def test_nem_nulla_kilepesi_kod_futasi_hiba_akkor_is_ha_a_kimenet_jo(self):
        self.fut('#include <iostream>\nint main() { std::cout << "1\\n"; return 3; }\n', [teszt("", "1\n")])
        t = self.teszt_esemenyek()[0]
        self.assertEqual((t["allapot"], t["kilepes"]), ("futasi_hiba", 3))

    def test_szegmentacios_hiba(self):
        self.fut('int main() { volatile int* p = nullptr; *p = 1; }\n', [teszt("", "")])
        t = self.teszt_esemenyek()[0]
        self.assertEqual(t["allapot"], "futasi_hiba")
        self.assertIn(t["jel"], ("SIGSEGV", "SIGBUS"))

    def test_idotullepes_a_blokk_idokorlataval(self):
        r = self.fut("int main() { for (;;) {} }\n", [teszt("", "", ido=0.5)])
        t = self.teszt_esemenyek()[0]
        self.assertEqual(t["allapot"], "idotullepes")
        self.assertEqual(t["idokorlat_s"], 0.5)
        self.assertLess(t["ido_ms"], 3000)
        self.assertFalse(r["atment"])

    def test_nagy_kimenet(self):
        self.fut('#include <cstdio>\nint main() { for (;;) putchar(\'x\'); }\n', [teszt("", "", ido=5)])
        self.assertEqual(self.teszt_esemenyek()[0]["allapot"], "kimenet_tullepes")

    def test_memoria_korlat(self):
        self.fut('#include <cstdlib>\nint main() {\n    volatile char* p = (volatile char*)malloc(700u << 20);\n'
                 '    for (size_t i = 0; i < (700u << 20); i += 4096) p[i] = 1;\n    for (;;) {}\n}\n', [teszt("", "", ido=5)])
        self.assertEqual(self.teszt_esemenyek()[0]["allapot"], "memoria")

    def test_lemez_korlat(self):
        self.fut('#include <fstream>\nint main() {\n    std::ofstream f("nagy.bin", std::ios::binary);\n'
                 '    std::string s(1 << 20, \'x\');\n    for (;;) f << s << std::flush;\n}\n', [teszt("", "", ido=5)])
        self.assertEqual(self.teszt_esemenyek()[0]["allapot"], "iras_korlat")

    def test_nagy_bemenet_es_kimenet(self):
        n = 200000
        bemenet = f"{n}\n" + " ".join(str(i) for i in range(n)) + "\n"
        r = self.fut(OSSZEG, [teszt(bemenet, f"{sum(range(n))}\n", ido=5)])
        self.assertTrue(r["atment"], self.teszt_esemenyek())

    # ---------------------------------------------------------------- a futtató profil C++-ból

    def test_a_futo_cpp_program_nem_tud_kitorni(self):
        """F2–F7 lefordított programmal: fájl, hálózat, fork, exec, jel, mappalista — minden TILTOTT, a munka mappába írás ENGEDETT."""
        forras = r'''
#include <cstdio>
#include <cstdlib>
#include <cerrno>
#include <csignal>
#include <iostream>
#include <string>
#include <fstream>
#include <dirent.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
using namespace std;
static void jel(const char* nev, bool engedett) { cout << nev << (engedett ? " ENGEDETT" : " TILTOTT") << "\n"; }
int main() {
    string titok, kint_ir, mappa;
    getline(cin, titok); getline(cin, kint_ir); getline(cin, mappa);
    { FILE* f = fopen(titok.c_str(), "r"); jel("olvas_kint", f != nullptr); }
    { FILE* f = fopen(kint_ir.c_str(), "w"); jel("ir_kint", f != nullptr); if (f) fclose(f); }
    { FILE* f = fopen("munka.txt", "w"); jel("ir_munka", f != nullptr); if (f) fclose(f); }
    { int s = socket(AF_INET, SOCK_STREAM, 0); sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(9);
      inet_pton(AF_INET, "127.0.0.1", &a.sin_addr); jel("tcp", s >= 0 && connect(s, (sockaddr*)&a, sizeof a) == 0); }
    { jel("fork", fork() != -1); }
    { jel("exec", system("echo x > /dev/null") == 0); }
    { jel("jel", kill(1, 0) == 0); }
    { DIR* d = opendir(mappa.c_str()); jel("lista", d != nullptr); }
}
'''
        kint_ir = self.kint / "kint-iras.txt"
        bemenet = f"{self.kint / 'titok.txt'}\n{kint_ir}\n{self.kint}\n"
        vart = "olvas_kint TILTOTT\nir_kint TILTOTT\nir_munka ENGEDETT\ntcp TILTOTT\nfork TILTOTT\nexec TILTOTT\njel TILTOTT\nlista TILTOTT\n"
        for mod in ("gyors", "hibakereso"):
            self.esem.clear()
            r = self.fut(forras, [teszt(bemenet, vart, ido=5)], mod=mod)
            self.assertTrue(r["atment"], (mod, self.teszt_esemenyek()))
            self.assertFalse(kint_ir.exists())

    # ---------------------------------------------------------------- hibakereső mód: sanitizerek

    def test_hibakereso_mod_az_atmeno_program_is_atmegy(self):
        r = self.fut(OSSZEG, [teszt("3\n10 20 30\n", "60\n")], mod="hibakereso")
        self.assertTrue(r["atment"], self.esem)
        self.assertEqual(self.esem[0]["mod"], "hibakereso")

    def test_asan_tulindexeles_a_helyes_sorral(self):
        forras = ("#include <iostream>\n#include <vector>\nint main() {\n    std::vector<int> v(3);\n    int s = 0;\n"
                  "    for (int i = 0; i <= 3; i++) s += v[i];\n    std::cout << s << \"\\n\";\n}\n")
        r = self.fut(forras, [teszt("", "0\n")], mod="hibakereso")
        t = self.teszt_esemenyek()[0]
        self.assertEqual(t["allapot"], "szanitizer", t)
        j = t["jelentes"]
        self.assertEqual((j["forras"], j["fajta"]), ("asan", "heap-buffer-overflow"))
        self.assertEqual(j["hozzaferes"], "READ of size 4")
        self.assertEqual((j["fajl"], j["sor"]), ("Összeg.cpp", 6))
        self.assertEqual(j["fuggveny"], "main")
        self.assertFalse(r["atment"])
        self.assertNotIn(str(self.t), t["stderr_kivonat"])              # a belső ideiglenes utak nem szivárognak a felületre

    def test_ubsan_egesz_tulcsordulas_a_helyes_sorral(self):
        forras = ("#include <iostream>\n#include <climits>\nint main() {\n    int x;\n    std::cin >> x;\n"
                  "    int y = x + INT_MAX;\n    std::cout << y << \"\\n\";\n}\n")
        self.fut(forras, [teszt("1\n", "0\n")], mod="hibakereso")
        t = self.teszt_esemenyek()[0]
        self.assertEqual(t["allapot"], "szanitizer", t)
        self.assertEqual(t["jelentes"]["forras"], "ubsan")
        self.assertIn("signed integer overflow", t["jelentes"]["leiras"])
        self.assertEqual((t["jelentes"]["fajl"], t["jelentes"]["sor"]), ("Összeg.cpp", 6))

    def test_a_gyors_modban_ugyanaz_a_hiba_nem_szanitizer(self):
        forras = ("#include <iostream>\n#include <vector>\nint main() {\n    std::vector<int> v(3);\n"
                  "    std::cout << v[1] << \"\\n\";\n}\n")
        r = self.fut(forras, [teszt("", "0\n")], mod="gyors")
        self.assertTrue(r["atment"])

    # ---------------------------------------------------------------- teszt nélkül, hibás teszt, megszakítás

    def test_teszt_blokk_nelkul_csak_fordit(self):
        r = self.fut(OSSZEG, [])
        self.assertTrue(r["fordit_ok"])
        self.assertFalse(r["atment"])
        self.assertEqual(r["tesztek_db"], 0)
        self.assertIn("nincs teszt", r["uzenet"])

    def test_hibas_teszt_blokk_nem_fut_de_szamit(self):
        hibas = T.Teszt(1, 1, "Rossz", "", "", None, hiba="hiányzik a `--- kimenet` szakasz")
        r = self.fut(OSSZEG, [hibas, teszt("1\n1\n", "1\n", n=2)])
        t = self.teszt_esemenyek()
        self.assertEqual([x["allapot"] for x in t], ["hibas_teszt", "atment"])
        self.assertIn("kimenet", t[0]["hiba"])
        self.assertFalse(r["atment"])
        self.assertEqual((r["tesztek_db"], r["atment_db"]), (2, 1))

    def test_megszakitas_a_fordito_utan_a_teszteknel(self):
        szamlalo = {"n": 0}

        def megszakit():
            szamlalo["n"] += 1
            return any(x["szakasz"] == "fordit_kesz" for x in self.esem)

        r = self.fut(OSSZEG, [teszt("1\n1\n", "1\n")], megszakit=megszakit)
        self.assertEqual(self.esem[-1]["szakasz"], "megszakitva")
        self.assertFalse(r["atment"])
        self.assertEqual(self.teszt_esemenyek(), [])

    def test_az_eszkoztar_hianya_hibaesemeny(self):
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home"), "MOS_LLVM": str(self.t / "nincs-llvm"),
                           "MOS_SDK": str(self.t / "nincs-sdk")})
        cpp = self.t / "x.cpp"
        cpp.write_text(OSSZEG)
        esem = []
        r = ellenorzes.Ellenorzes(cfg, esemeny=esem.append).fut(cpp, [teszt("", "")], "gyors")
        self.assertFalse(r["atment"])
        self.assertEqual(esem[-1]["szakasz"], "hiba")
        self.assertEqual(esem[-1]["kod"], "nincs_eszkoztar")
        self.assertIn("bin/mos cpp telepit", esem[-1]["uzenet"])

    def test_az_idokorlat_a_hibakereso_modban_tobbszoros(self):
        self.fut(OSSZEG, [teszt("1\n1\n", "1\n", ido=1.0)], mod="hibakereso")
        self.assertEqual(self.teszt_esemenyek()[0]["idokorlat_s"], 3.0)

    def test_alapertelmezett_idokorlat_a_configbol(self):
        self.fut(OSSZEG, [teszt("1\n1\n", "1\n")])
        self.assertEqual(self.teszt_esemenyek()[0]["idokorlat_s"], 2.0)


@unittest.skipUnless(VAN, OK_SKIP)
class FormazasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        root = alg_gyoker(self._t.name).resolve()
        self.e = eszkoztar.Eszkoztar(config.load({"MOS_ROOT": str(root), "HOME": self._t.name,
                                                  "MOS_LLVM": str(VALODI.path("llvm")), "MOS_SDK": str(VALODI.path("sdk"))}))

    def test_formazas(self):
        ok, szoveg = self.e.formaz("int main(){int x=1;if(x){return 0;}return 1;}\n")
        self.assertTrue(ok, szoveg)
        self.assertEqual(szoveg, "int main() {\n    int x = 1;\n    if (x) {\n        return 0;\n    }\n    return 1;\n}\n")

    def test_a_forrasbol_stilus_fajl_nem_hat(self):
        """A `.clang-format` keresése tiltott (az inline stílus): a munkakönyvtár `.clang-format`-ja nem számít."""
        ok, szoveg = self.e.formaz("int main(){return 0;}\n")
        self.assertTrue(ok)
        self.assertIn("    return 0;", szoveg)

    def test_mar_formazott_forras_valtozatlan(self):
        forras = "int main() {\n    return 0;\n}\n"
        ok, szoveg = self.e.formaz(forras)
        self.assertEqual((ok, szoveg), (True, forras))

    def test_szintaktikailag_hibas_forrast_is_formaz(self):
        ok, szoveg = self.e.formaz("int main( {\n")
        self.assertTrue(ok)

    def test_utf8_megmarad(self):
        ok, szoveg = self.e.formaz('const char* s="árvíztűrő tükörfúrógép";\n')
        self.assertTrue(ok)
        self.assertIn("árvíztűrő tükörfúrógép", szoveg)


if __name__ == "__main__":
    unittest.main()
