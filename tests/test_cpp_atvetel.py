"""C36a2: a `claude/c36a-cpp-formatum` ágról átvett viselkedések a main-i egyetlen formátumban — a `teszt` blokk `--- memoria`,
`--- osszevetes` (`tures`, `lebego`, `pontos`) és `--- ido` szakasza (`core/cpp_teszt.py`), az összevetési módok
(`modulok/cpp/osszevet.py`), a bővített fordító-diagnosztika (`modulok/cpp/diagnosztika.py`) és a tesztenkénti korlát
bekötése az ellenőrzésbe (`modulok/cpp/ellenorzes.py`, álhívóval: nem kell hozzá `sandbox-exec` vagy clang, Linuxon is fut)."""
import unittest
from pathlib import Path

from core import config
from core import cpp_teszt as T
from modulok.cpp import diagnosztika as D
from modulok.cpp import ellenorzes, eszkoztar
from modulok.cpp import osszevet as O
from tests.helpers import REPO, alg_gyoker, tmpdir

DIAG = REPO / "tests" / "adat" / "cpp_diag"


def blokk(*sorok: str, info: str = "teszt") -> str:
    return "```" + info + "\n" + "\n".join(sorok) + "\n```\n"


class SzakaszokTest(unittest.TestCase):
    def test_a_meglevo_blokk_valtozatlan_alapokkal(self):
        t = T.tesztek(blokk("--- bemenet", "5", "--- kimenet", "15", "--- idokorlat", "2"))[0]
        self.assertIsNone(t.hiba)
        self.assertEqual((t.memoria_kb, t.osszevetes, t.eps, t.memoria_mb), (None, "alap", None, None))
        self.assertEqual(t.szotar()["osszevetes"], "alap")

    def test_ido_az_idokorlat_alneve(self):
        for jel in ("ido", "idő", "IDO"):
            t = T.tesztek(blokk("--- kimenet", "x", f"--- {jel}", "500 ms"))[0]
            self.assertIsNone(t.hiba, jel)
            self.assertAlmostEqual(t.idokorlat_s, 0.5)

    def test_ido_es_idokorlat_egyutt_hiba(self):
        t = T.tesztek(blokk("--- kimenet", "x", "--- ido", "1", "--- idokorlat", "2"))[0]
        self.assertIn("kétszer", t.hiba)

    def test_memoria_formak(self):
        for szoveg, kb in (("64MB", 65536), ("64 MiB", 65536), ("1GB", 1048576), ("2048 KB", 2048), ("1,5 GB", 1572864),
                           ("1024kb", 1024)):
            t = T.tesztek(blokk("--- kimenet", "x", "--- memoria", szoveg))[0]
            self.assertIsNone(t.hiba, szoveg)
            self.assertEqual(t.memoria_kb, kb, szoveg)
        self.assertEqual(T.tesztek(blokk("--- kimenet", "x", "--- memória", "2MB"))[0].memoria_mb, 2.0)

    def test_memoria_hibak(self):
        for szoveg in ("sok", "64", "0MB", "512KB", "17GB", "-1MB", "1.0001MB", ""):
            t = T.tesztek(blokk("--- kimenet", "x", "--- memoria", szoveg))[0]
            self.assertIn("memóriakorlát", t.hiba or "", szoveg)

    def test_memoria_maximum(self):
        self.assertIn("legfeljebb 128", T.tesztek(blokk("--- kimenet", "x", "--- memoria", "129MB"), None, 128)[0].hiba)
        self.assertIsNone(T.tesztek(blokk("--- kimenet", "x", "--- memoria", "128MB"), None, 128)[0].hiba)

    def test_osszevetes_modok(self):
        for szoveg, mod, eps in (("alap", "alap", None), ("pontos", "pontos", None), ("TURES", "tures", None),
                                 ("lebego", "lebego", None), ("lebego 1e-6", "lebego", 1e-6), ("lebego  0.5", "lebego", 0.5),
                                 ("lebego 0", "lebego", 0.0)):
            t = T.tesztek(blokk("--- kimenet", "x", "--- osszevetes", szoveg))[0]
            self.assertIsNone(t.hiba, szoveg)
            self.assertEqual((t.osszevetes, t.eps), (mod, eps), szoveg)

    def test_osszevetes_hibak(self):
        for szoveg in ("laza", "", "tures 1e-3", "lebego x", "lebego 1", "lebego -1e-3", "lebego nan", "lebego 1e-3 2"):
            t = T.tesztek(blokk("--- kimenet", "x", "--- osszevetes", szoveg))[0]
            self.assertIsNotNone(t.hiba, szoveg)
            self.assertEqual(t.osszevetes, "alap", szoveg)         # hibánál nincs csendes alapérték-csere

    def test_hibas_blokk_nem_viszi_el_a_tobbit(self):
        sz = blokk("--- kimenet", "1", "--- memoria", "sok") + "\n" + blokk("--- kimenet", "2", "--- osszevetes", "tures")
        t = T.tesztek(sz)
        self.assertEqual([bool(x.hiba) for x in t], [True, False])
        self.assertEqual(t[1].osszevetes, "tures")

    def test_a_nem_szakaszjelzo_sor_tartalom(self):
        t = T.tesztek(blokk("--- kimenet", "--- osszevetes x", "--- memoria 5", "---memoria"))[0]
        self.assertIsNone(t.hiba)
        self.assertEqual(t.kimenet, "--- osszevetes x\n--- memoria 5\n---memoria\n")

    def test_szotar_kulcsai(self):
        t = T.tesztek(blokk("--- kimenet", "x", "--- memoria", "8MB", "--- osszevetes", "lebego 1e-3"))[0].szotar()
        self.assertEqual((t["memoria_kb"], t["osszevetes"], t["eps"]), (8192, "lebego", 1e-3))


class OsszevetesTest(unittest.TestCase):
    def test_alap_valtozatlan(self):
        self.assertTrue(O.egyezik("1 2\n3\n\n", "1 2  \r\n3"))
        self.assertFalse(O.egyezik("1 2", "1  2"))
        self.assertFalse(O.egyezik("a", " a"))
        self.assertFalse(O.egyezik("a", "A"))

    def test_pontos(self):
        self.assertTrue(O.egyezik("a b\n", "a b", "pontos"))          # az egyetlen záró sorvég nem számít
        self.assertTrue(O.egyezik("a\r\nb\r\n", "a\nb\n", "pontos"))
        self.assertFalse(O.egyezik("a b", "a b ", "pontos"))          # a sorvégi szóköz számít (az `alap`-pal ellentétben)
        self.assertFalse(O.egyezik("a\n", "a\n\n", "pontos"))
        e = O.elteres("a b\nc", "a b\nd", "pontos")
        self.assertEqual((e["sor"], e["oszlop"], e["ok"]), (2, 1, "a sor eltér"))

    def test_tures(self):
        self.assertTrue(O.egyezik("1  2\t3\n4\n\n\n", "  1 2 3  \r\n4", "tures"))
        self.assertFalse(O.egyezik("1 2\n3", "1 2 3", "tures"))       # a sorszerkezet számít
        self.assertFalse(O.egyezik("a", "A", "tures"))
        e = O.elteres("1 2 3\n4 5", "1 2 3\n4 6", "tures")
        self.assertEqual((e["sor"], e["token"], e["vart"], e["kapott"]), (2, 2, "4 5", "4 6"))
        self.assertEqual(O.elteres("a\nb", "a", "tures")["ok"], "a kimenet rövidebb a vártnál")
        self.assertEqual(O.elteres("a", "a\nb", "tures")["ok"], "a kimenet hosszabb a vártnál")

    def test_lebego_szamok(self):
        self.assertTrue(O.egyezik("3.14159265", "3.14159", "lebego", 1e-5))
        self.assertFalse(O.egyezik("3.14159265", "3.14", "lebego", 1e-5))
        self.assertTrue(O.egyezik("1000000", "1000000.5", "lebego", 1e-6))     # relatív tűrés
        self.assertTrue(O.egyezik("0", "0.0000001", "lebego", 1e-6))           # abszolút tűrés
        self.assertTrue(O.egyezik("1e3", "1000", "lebego", 0.0))
        self.assertTrue(O.egyezik("-0.0", "0", "lebego", 0.0))

    def test_lebego_sorszerkezet_nem_szamit_a_nem_szam_pontos(self):
        self.assertTrue(O.egyezik("1 2\n3", "1\n2 3\n", "lebego"))
        self.assertFalse(O.egyezik("igen 1", "Igen 1", "lebego"))
        self.assertFalse(O.egyezik("1 2", "1", "lebego"))
        self.assertFalse(O.egyezik("1", "1 2", "lebego"))

    def test_lebego_nan_inf(self):
        self.assertTrue(O.egyezik("nan inf -inf", "NaN INF -Inf", "lebego"))
        self.assertFalse(O.egyezik("nan", "1", "lebego"))
        self.assertFalse(O.egyezik("inf", "-inf", "lebego"))
        self.assertFalse(O.egyezik("inf", "1e308", "lebego", 0.5))

    def test_lebego_elteres_helye_es_oka(self):
        e = O.elteres("1.0 2.0\n3.0", "1.0 2.0\n3.5", "lebego", 1e-6)
        self.assertEqual((e["sor"], e["token"], e["vart"], e["kapott"], e["ok"]), (2, 3, "3.0", "3.5", "a szám a tűrésen kívül esik"))
        self.assertEqual(O.elteres("1 ok", "1 nem", "lebego")["ok"], "a token eltér")
        self.assertEqual(O.elteres("1", "1 2", "lebego")["ok"], "a kimenet több tokent tartalmaz")
        self.assertEqual(O.elteres("1 2", "1", "lebego")["ok"], "a kimenet kevesebb tokent tartalmaz")

    def test_ismeretlen_mod(self):
        with self.assertRaises(ValueError):
            O.egyezik("a", "a", "laza")

    def test_diff_modja_es_elteresei(self):
        d = O.diff("1 2\n3\n", "1  2\n4\n", mod="tures")
        self.assertFalse(d["egyezik"])
        self.assertEqual(d["mod"], "tures")
        self.assertEqual(d["elso_elteres"], 2)               # az 1. sor szóköz-toleránsan egyező: nem eltérés a diffben
        self.assertEqual(d["elteres"]["sor"], 2)
        self.assertEqual(d["elteres_db"], 1)                 # csak a 2. sor cserélődik
        self.assertTrue(O.diff("a", "a", mod="lebego")["egyezik"])
        self.assertIsNone(O.diff("a", "a")["elteres"])

    def test_diff_pontos_modban_a_sorveg_szokoz_is_latszik(self):
        d = O.diff("a\n", "a \n", mod="pontos")
        self.assertFalse(d["egyezik"])
        self.assertEqual(d["elteres_db"], 1)
        self.assertEqual(d["sorok"][0]["tipus"], "csere")
        self.assertEqual(d["elteres"]["oszlop"], 2)

    def test_diff_alapertelmezes_valtozatlan(self):
        d = O.diff("a\nb\n", "a\nc\n")
        self.assertEqual((d["mod"], d["elso_elteres"], d["elteres"]["sor"]), ("alap", 2, 2))


def _tablazat(r):
    return [(d["fajl"], d["sor"], d["oszlop"], d["szint"], d["vegzetes"]) for d in r["diagnosztika"]]


def _olvas(nev: str) -> str:
    return (DIAG / nev).read_text(encoding="utf-8")


class DiagnosztikaTest(unittest.TestCase):
    def test_clang_hibak_kodreszlettel_note_kulon_tetel(self):
        r = D.fordito(_olvas("clang-hiba.txt"), "hiba.cpp")
        self.assertEqual(_tablazat(r), [("./fej.h", 1, 19, "error", False), ("hiba.cpp", 8, 14, "error", False),
                                        ("hiba.cpp", 10, 13, "error", False), ("hiba.cpp", 11, 5, "error", False),
                                        ("hiba.cpp", 5, 5, "note", False)])
        d = r["diagnosztika"]
        self.assertEqual(d[2]["kodreszlet"], ["   10 |     cout << y << endl;", "      |             ^"])
        self.assertEqual(d[1]["kodreszlet"][-1].strip(), "|              ;")
        self.assertTrue(d[1]["sajat"])
        self.assertEqual((r["hiba_db"], r["figyelmeztetes_db"]), (4, 0))

    def test_gcc_figyelmeztetes_kapcsolo(self):
        r = D.fordito(_olvas("gcc-hiba.txt"), "hiba.cpp")
        w = r["diagnosztika"][-1]
        self.assertEqual((w["szint"], w["kapcsolo"], w["uzenet"]), ("warning", "-Wunused-variable", "unused variable 'x'"))
        self.assertEqual((r["hiba_db"], r["figyelmeztetes_db"]), (4, 1))

    def test_vegzetes_jelzo(self):
        for nev in ("clang-fatal.txt", "gcc-fatal.txt"):
            r = D.fordito(_olvas(nev), "fatal.cpp")
            self.assertEqual([(d["szint"], d["vegzetes"]) for d in r["diagnosztika"]], [("error", True)], nev)
            self.assertEqual(r["hiba_db"], 1)

    def test_gnu_linker_hiba_oka(self):
        for nev in ("gcc-link.txt", "clang-link.txt"):
            r = D.fordito(_olvas(nev), "link.cpp")
            self.assertIn("undefined reference to `hianyzo(int)'", r["diagnosztika"][0]["uzenet"], nev)
            self.assertEqual(r["diagnosztika"][0]["fajl"], "link.cpp")
            self.assertTrue(r["diagnosztika"][0]["sajat"])
        # a clang++ „linker command failed” sora külön tétel; a gcc collect2 sora nem illeszkedik (a hiba oka a lényeg)
        self.assertEqual(D.fordito(_olvas("gcc-link.txt"), "link.cpp")["hiba_db"], 1)
        self.assertEqual(D.fordito(_olvas("clang-link.txt"), "link.cpp")["hiba_db"], 2)

    def test_macos_ld64_hibaja_a_valodi_kimenet_alakja(self):
        r = D.fordito(_olvas("macos-link-kezi.txt"), "link.cpp")
        d = r["diagnosztika"]
        self.assertEqual(d[0]["uzenet"], "Undefined symbols for architecture arm64")
        self.assertIn('"hianyzo(int)", referenced from', d[0]["reszletek"][0])
        self.assertEqual(d[1]["uzenet"], "ld: symbol(s) not found for architecture arm64")
        self.assertTrue(d[2]["uzenet"].startswith("linker command failed"))
        self.assertEqual(r["hiba_db"], 3)

    def test_oszlop_nelkuli_hely(self):
        r = D.fordito("a.cpp:3: warning: valami [-Wextra-x]\n", "a.cpp")
        self.assertEqual(_tablazat(r), [("a.cpp", 3, None, "warning", False)])
        self.assertEqual(r["diagnosztika"][0]["kapcsolo"], "-Wextra-x")

    def test_az_lld_alak_es_a_keretsorok_valtozatlanok(self):
        sz = ("In file included from /m/f.cpp:1:\n/m/f.cpp:5:5: error: x\n    5 |     y;\n      |     ^\n"
              "1 error generated.\nld64.lld: error: undefined symbol: foo(int)\n>>> referenced by /m/f.o\n")
        r = D.fordito(sz, "f.cpp")
        self.assertEqual([d["fajl"] for d in r["diagnosztika"]], ["f.cpp", None])
        self.assertEqual(r["diagnosztika"][1]["reszletek"], ["referenced by /m/f.o"])
        self.assertEqual(len(r["diagnosztika"][0]["kodreszlet"]), 2)

    def test_kodreszlet_korlatos_es_ures_bemenet(self):
        sz = "a.cpp:1:1: error: x\n" + "".join(f"  {i} | sor\n" for i in range(20))
        self.assertEqual(len(D.fordito(sz, "a.cpp")["diagnosztika"][0]["kodreszlet"]), 6)
        self.assertEqual(D.fordito("", "a.cpp")["diagnosztika"], [])

    def test_tobbi_jelentes_valtozatlan(self):
        self.assertEqual(D.jelentes("Assertion failed: (x > 0), function f, file a.cpp, line 3.\n", "a.cpp")["forras"], "assert")


class _Homokozo:
    """Álhívó a program-homokozó helyett: rögzíti a futtatás korlátait, a megadott stdoutot adja vissza."""

    def __init__(self, stdout: bytes):
        self.stdout = stdout
        self.hivasok: list[dict] = []

    def futtat(self, prog, **kw):
        self.hivasok.append(kw)
        return {"allapot": "ok", "ido_ms": 1.0, "cpu_ms": 1.0, "csucs_mb": 1.0, "kilepes": 0, "jel": None, "uzenet": "",
                "stdout": self.stdout, "stderr": b""}


class EllenorzesBekotesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        root = alg_gyoker(cls._t.name).resolve()
        cls.cfg = config.load({"MOS_ROOT": str(root), "HOME": str(Path(cls._t.name) / "home")})
        cls.futas = Path(cls._t.name) / "futas"
        cls.futas.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def _fut(self, t: T.Teszt, stdout: bytes, mod: str = "gyors"):
        hk = _Homokozo(stdout)
        e = ellenorzes.Ellenorzes(self.cfg, eszkoztar=eszkoztar.Eszkoztar(self.cfg), homokozo=hk)
        egy = self.futas / f"t{t.sorszam}"
        if egy.exists():
            import shutil
            shutil.rmtree(egy)
        eredmeny = e._teszt(t, self.futas, self.futas, self.futas / "prog", mod, "Feladat.cpp")
        return eredmeny, hk.hivasok[0]

    def test_alapok_valtozatlanok(self):
        e, kw = self._fut(T.Teszt(1, 1, None, "", "3\n", None), b"3\n")
        self.assertEqual(e["allapot"], "atment")
        self.assertEqual(kw["memoria_mb"], 256.0)
        self.assertEqual((e["memoria_mb"], e["osszevetes"]), (256.0, "alap"))

    def test_a_blokk_memoriakorlatja_a_futtatasig_eljut(self):
        e, kw = self._fut(T.Teszt(2, 2, None, "", "x\n", None, None, 65536), b"x\n")
        self.assertEqual((kw["memoria_mb"], e["memoria_mb"]), (64.0, 64.0))

    def test_hibakereso_modban_a_sanitizer_kerete_nem_szukul(self):
        _, kw = self._fut(T.Teszt(3, 3, None, "", "x\n", None, None, 65536), b"x\n", "hibakereso")
        self.assertEqual(kw["memoria_mb"], 1024.0)
        _, kw = self._fut(T.Teszt(4, 4, None, "", "x\n", None, None, 4 * 1024 * 1024), b"x\n", "hibakereso")
        self.assertEqual(kw["memoria_mb"], 4096.0)

    def test_tures_mod_az_atmenetben(self):
        t = T.Teszt(5, 5, None, "", "1 2\n3\n", None, None, None, "tures")
        self.assertEqual(self._fut(t, b" 1   2\n3  \n")[0]["allapot"], "atment")
        e, _ = self._fut(t, b"1 2 3\n")
        self.assertEqual(e["allapot"], "hibas_kimenet")
        self.assertEqual(e["diff"]["mod"], "tures")
        self.assertEqual(e["diff"]["elteres"]["sor"], 1)

    def test_lebego_mod_blokk_es_alap_tureserrel(self):
        t = T.Teszt(6, 6, None, "", "3.14159265\n", None, None, None, "lebego", 1e-5)
        self.assertEqual(self._fut(t, b"3.14159\n")[0]["allapot"], "atment")
        self.assertEqual(self._fut(t, b"3.1415\n")[0]["allapot"], "hibas_kimenet")
        t = T.Teszt(7, 7, None, "", "1.0\n", None, None, None, "lebego")            # [cpp] lebego_eps = 1e-6
        self.assertEqual(self._fut(t, b"1.0000005\n")[0]["allapot"], "atment")
        self.assertEqual(self._fut(t, b"1.00001\n")[0]["allapot"], "hibas_kimenet")

    def test_hibas_blokk_nem_fut(self):
        t = T.tesztek(blokk("--- kimenet", "x", "--- memoria", "sok"))[0]
        hk = _Homokozo(b"")
        e = ellenorzes.Ellenorzes(self.cfg, eszkoztar=eszkoztar.Eszkoztar(self.cfg), homokozo=hk)
        r = e._teszt(t, self.futas, self.futas, self.futas / "prog", "gyors", "Feladat.cpp")
        self.assertEqual(r["allapot"], "hibas_teszt")
        self.assertEqual(hk.hivasok, [])


if __name__ == "__main__":
    unittest.main()
