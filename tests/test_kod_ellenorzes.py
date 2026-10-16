"""F10: the language engine (`modulok/kod`) in the REAL sandbox (`sandbox-exec`): compile / run / test for every v1 language.

- Python, JavaScript, TypeScript: the embedded runtime (`{runtime}/python`, `{runtime}/node`) — real;
- C: the portable LLVM through the C36a engine — real (when installed);
- Swift: the system toolchain — real when the Xcode Command Line Tools are installed (else skipped);
- Java, Go, Rust: mock toolchains (`tests/kod_segedek.py`) in the real sandbox: the adapter, the discovery, the compile
  diagnostics bound to lines, the tests, the runtime report and the error contract are exercised; the native mocks
  "produce" an echo program built with the portable LLVM.
The isolation checks (no file outside the work folder, no network, no subprocess) run with the real Python and Node.
Missing pieces → `[indokolt]` skips."""
import os
import shutil
import sys
import unittest
from pathlib import Path

from core import config, cpp_teszt as T
from core import kod_nyelvek as KN
from modulok.kod import diagnosztika as D
from modulok.kod.ellenorzes import Ellenorzes
from modulok.kod.felderites import Felderites
from modulok.kod.futtato import Futtato
from tests.helpers import alg_gyoker, tmpdir
from tests.kod_segedek import ECHO_C, KodCfg, mock_eszkozlanc

MACOS = sys.platform == "darwin" and os.access("/usr/bin/sandbox-exec", os.X_OK)
VALODI = config.load()
OK_SKIP = "[indokolt] nincs sandbox-exec (csak macOS)"


def _cfg(t: Path, kod: dict | None = None):
    root = alg_gyoker(str(t)).resolve()
    c = config.load({"MOS_ROOT": str(root), "HOME": str(t / "home"), "MOS_LLVM": str(VALODI.path("llvm")),
                     "MOS_SDK": str(VALODI.path("sdk")), "MOS_RUNTIME": str(VALODI.path("runtime"))})
    return KodCfg(c, kod)


def teszt(n: int, be: str, ki: str, ido: float | None = None) -> T.Teszt:
    return T.Teszt(n, n, None, be, ki, ido)


OSSZEG_TESZTEK = [teszt(1, "3\n1 2 3\n", "6\n"), teszt(2, "1\n5\n", "5\n")]
FORRAS = {
    "python": "n = int(input())\nxs = list(map(int, input().split()))\nprint(sum(xs[:n]))\n",
    "javascript": ("const s = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\n"
                   "let t = 0;\nfor (let i = 1; i <= s[0]; i++) t += s[i];\nconsole.log(t);\n"),
    "typescript": ("const s: number[] = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\n"
                   "let t: number = 0;\nfor (let i = 1; i <= s[0]; i++) t += s[i];\nconsole.log(t);\n"),
    "cpp": ("#include <iostream>\nint main() {\n    int n, x; long long s = 0;\n    std::cin >> n;\n"
            "    for (int i = 0; i < n; i++) { std::cin >> x; s += x; }\n    std::cout << s << \"\\n\";\n}\n"),
    "c": ("#include <stdio.h>\nint main(void) {\n    int n, x; long long s = 0;\n    scanf(\"%d\", &n);\n"
          "    for (int i = 0; i < n; i++) { scanf(\"%d\", &x); s += x; }\n    printf(\"%lld\\n\", s);\n    return 0;\n}\n"),
    "swift": ("let n = Int(readLine()!)!\nlet xs = readLine()!.split(separator: \" \").map { Int($0)! }\n"
              "print(xs.prefix(n).reduce(0, +))\n"),
}
SZINTAXIS = {"python": ("def f(:\n    pass\n", 1), "javascript": ("let a = 1;\nconsole.log((a;\n", 2),
             "typescript": ("let x: number = 5\nlet y = x +* 2;\n", None), "swift": ("let x = 1\nlet y: Int = \"s\"\n", 2),
             "c": ("int main(void) {\n    return x;\n}\n", 2)}
FUTASI = {"python": ("xs = [1]\nn = int(input())\nprint(xs[n])\n", 3, "IndexError"),
          "javascript": ("const a = [1];\nfunction f() { return a.x.y; }\nf();\n", 2, "TypeError"),
          "typescript": ("const n: number = 3;\nfunction f(): never { throw new Error('boom'); }\nif (n > 2) f();\n", 2, "Error")}


class _Alap(unittest.TestCase):
    KOD: dict | None = None

    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.t = Path(os.path.realpath(cls._t.name))
        cls.cfg = _cfg(cls.t, cls.KOD)

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def fut(self, nyelv: str, forras: str, tesztek=None, nev: str | None = None, mod: str = "gyors", cfg=None):
        p = KN.profil(nyelv)
        ut = self.t / "src" / (nev or ("Main.java" if nyelv == "java" else "Megoldas" + p.kiterjesztesek[0]))
        ut.parent.mkdir(exist_ok=True)
        ut.write_text(forras, encoding="utf-8")
        esem: list[dict] = []
        r = Ellenorzes(cfg or self.cfg, p, esemeny=esem.append).fut(ut, OSSZEG_TESZTEK if tesztek is None else tesztek, mod)
        return r, esem

    @staticmethod
    def szakasz(esem, nev):
        return [e for e in esem if e["szakasz"] == nev]

    def elerheto(self, nyelv: str) -> bool:
        return Felderites(self.cfg).nyelv(KN.profil(nyelv))["elerheto"]


@unittest.skipUnless(MACOS, OK_SKIP)
class ValodiNyelvekTest(_Alap):
    """Python, JavaScript, TypeScript (embedded runtime), C (portable LLVM), Swift (system) — compile, run, test, for real."""

    def _nyelv(self, nyelv):
        if not self.elerheto(nyelv):
            self.skipTest(f"[indokolt] no {nyelv} toolchain on this machine")

    def test_minden_teszt_atmegy(self):
        for nyelv in FORRAS:
            with self.subTest(nyelv=nyelv):
                self._nyelv(nyelv)
                r, esem = self.fut(nyelv, FORRAS[nyelv])
                self.assertTrue(r["atment"], esem)
                self.assertEqual((r["atment_db"], r["tesztek_db"]), (2, 2))
                self.assertTrue(all(e["nyelv"] == nyelv for e in esem))
                self.assertEqual(self.szakasz(esem, "indul")[0]["forras"], "Megoldas" + KN.profil(nyelv).kiterjesztesek[0])

    def test_hibas_kimenet_diffel(self):
        self._nyelv("python")
        r, esem = self.fut("python", FORRAS["python"], [teszt(1, "2\n1 1\n", "3\n")])
        t = self.szakasz(esem, "teszt")[0]["teszt"]
        self.assertEqual(t["allapot"], "hibas_kimenet")
        self.assertTrue(t["diff"])
        self.assertFalse(r["atment"])

    def test_szintaxis_hiba_sorhoz_kotve(self):
        for nyelv, (forras, sor) in SZINTAXIS.items():
            with self.subTest(nyelv=nyelv):
                self._nyelv(nyelv)
                r, esem = self.fut(nyelv, forras)
                f = self.szakasz(esem, "fordit_kesz")[0]["fordit"]
                self.assertFalse(f["ok"])
                self.assertFalse(r["fordit_ok"])
                self.assertEqual(self.szakasz(esem, "teszt"), [])          # no test runs after a failed compile
                hibak = [d for d in f["diagnosztika"] if d["szint"] == "error"]
                self.assertTrue(hibak, f)
                self.assertEqual(hibak[0]["fajl"], "Megoldas" + KN.profil(nyelv).kiterjesztesek[0])
                if sor is not None:
                    self.assertEqual(hibak[0]["sor"], sor)
                self.assertNotIn(str(self.t), str(f))                        # the sandbox folders are not shown

    def test_futasi_hiba_jelentes_sorral(self):
        for nyelv, (forras, sor, fajta) in FUTASI.items():
            with self.subTest(nyelv=nyelv):
                self._nyelv(nyelv)
                r, esem = self.fut(nyelv, forras, [teszt(1, "5\n", "1\n")])
                t = self.szakasz(esem, "teszt")[0]["teszt"]
                self.assertEqual(t["allapot"], "futasi_hiba", t)
                self.assertEqual(t["jelentes"]["fajta"], fajta)
                self.assertEqual(t["jelentes"]["sor"], sor)
                self.assertEqual(t["jelentes"]["fajl"], "Megoldas" + KN.profil(nyelv).kiterjesztesek[0])

    def test_idotullepes_es_memoria(self):
        self._nyelv("python")
        _, esem = self.fut("python", "while True:\n    pass\n", [teszt(1, "", "", 0.5)])
        self.assertEqual(self.szakasz(esem, "teszt")[0]["teszt"]["allapot"], "idotullepes")
        _, esem = self.fut("python", "x = bytearray(900 * 1024 * 1024)\nprint(len(x))\n", [teszt(1, "", "1\n")])
        self.assertEqual(self.szakasz(esem, "teszt")[0]["teszt"]["allapot"], "memoria")

    def test_typescript_enum_transform(self):
        self._nyelv("typescript")
        r, esem = self.fut("typescript", "enum Szin { Piros, Zold }\nconsole.log(Szin.Zold);\n", [teszt(1, "", "1\n")])
        self.assertTrue(r["atment"], esem)

    def test_hibakereso_mod_csak_c_es_cpp(self):
        r, esem = self.fut("python", FORRAS["python"], mod="hibakereso")
        h = self.szakasz(esem, "hiba")[0]
        self.assertEqual(h["kod"], "kod.mod_nem_tamogatott")
        self.assertFalse(r["atment"])

    def test_teszt_nelkul_csak_forditas(self):
        self._nyelv("javascript")
        r, esem = self.fut("javascript", FORRAS["javascript"], [])
        k = self.szakasz(esem, "kesz")[0]
        self.assertTrue(k["fordit_ok"])
        self.assertEqual(k["kod"], "kod.nincs_teszt")


@unittest.skipUnless(MACOS, OK_SKIP)
class ElszigetelesTest(_Alap):
    """The program cannot read outside its folder, cannot reach the network, cannot start a program."""

    def setUp(self):
        self.titok = self.t / "kint" / "titok.txt"
        self.titok.parent.mkdir(exist_ok=True)
        self.titok.write_text("TITOK\n")

    def _ok(self, nyelv, forras):
        if not self.elerheto(nyelv):
            self.skipTest(f"[indokolt] no {nyelv}")
        _, esem = self.fut(nyelv, forras, [teszt(1, "", "OK\n")])
        t = self.szakasz(esem, "teszt")[0]["teszt"]
        self.assertEqual(t["allapot"], "atment", t)

    def test_python(self):
        self._ok("python", f"""import socket, subprocess
ok = True
try:
    open({str(self.titok)!r}).read(); ok = False
except OSError:
    pass
try:
    socket.create_connection(("127.0.0.1", 9), timeout=1); ok = False
except OSError:
    pass
try:
    subprocess.run(["/bin/echo", "x"]); ok = False
except OSError:
    pass
try:
    import os; os.listdir({str(self.t)!r}); ok = False
except OSError:
    pass
print("OK" if ok else "SZIVARGAS")
""")

    def test_node(self):
        self._ok("javascript", f"""const fs = require('fs'); const cp = require('child_process');
let ok = true;
try {{ fs.readFileSync({str(self.titok)!r}); ok = false; }} catch (e) {{}}
try {{ cp.execFileSync('/bin/echo', ['x']); ok = false; }} catch (e) {{}}
try {{ fs.readdirSync({str(self.t)!r}); ok = false; }} catch (e) {{}}
console.log(ok ? 'OK' : 'SZIVARGAS');
""")

    def test_a_fordito_lepes_sem_olvas_kifele(self):
        """The Python checker does not run the program: a top-level side effect never happens."""
        if not self.elerheto("python"):
            self.skipTest("[indokolt] no python")
        jel = self.t / "kint" / "jel.txt"
        r, esem = self.fut("python", f"open({str(jel)!r}, 'w').write('x')\nprint('OK')\n", [])
        self.assertTrue(self.szakasz(esem, "fordit_kesz")[0]["fordit"]["ok"])
        self.assertFalse(jel.exists())


@unittest.skipUnless(MACOS, OK_SKIP)
class MockEszkozlancTest(_Alap):
    """Java, Go, Rust through their adapters, with mock toolchains in the real sandbox."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.prog = None
        c = KN.profil("c")
        with Futtato(cls.cfg, c) as f:                     # the echo program, built with the portable LLVM in the sandbox
            if f.hiany() is None:
                p = f.fordit(ECHO_C, "echo")
                if p.ok:
                    cls.prog = cls.t / "echo-prog"
                    shutil.copy2(p.bin, cls.prog)
        cls.cfg = KodCfg(cls.cfg._c, mock_eszkozlanc(cls.t / "tc", cls.prog))

    ECHO = [teszt(1, "hello\n", "hello\n"), teszt(2, "a\n", "b\n"), teszt(3, "KIVETEL\n", "x\n")]

    def _nativ(self):
        if self.prog is None:
            self.skipTest("[indokolt] no portable LLVM for the native echo program (bin/mos cpp telepit --igen)")

    def test_felderites_a_konfigbol(self):
        fd = Felderites(self.cfg)
        for nyelv in ("java", "go", "rust"):
            with self.subTest(nyelv=nyelv):
                st = fd.nyelv(KN.profil(nyelv))
                self.assertTrue(st["elerheto"], st)
                self.assertTrue(all(e["forras"] == "konfig" for e in st["eszkozok"]))
                self.assertIn("mock", st["eszkozok"][0]["verzio"])

    def test_java(self):
        r, esem = self.fut("java", "class Main {}\n", self.ECHO)
        allapot = [e["teszt"]["allapot"] for e in self.szakasz(esem, "teszt")]
        self.assertEqual(allapot, ["atment", "hibas_kimenet", "futasi_hiba"], esem)
        j = self.szakasz(esem, "teszt")[2]["teszt"]["jelentes"]
        self.assertEqual((j["fajta"], j["sor"], j["fajl"]), ("ArithmeticException", 4, "Main.java"))

    def test_go_es_rust(self):
        self._nativ()
        for nyelv, fajl in (("go", "Megoldas.go"), ("rust", "Megoldas.rs")):
            with self.subTest(nyelv=nyelv):
                r, esem = self.fut(nyelv, "package main\n" if nyelv == "go" else "fn main() {}\n", self.ECHO)
                allapot = [e["teszt"]["allapot"] for e in self.szakasz(esem, "teszt")]
                self.assertEqual(allapot, ["atment", "hibas_kimenet", "futasi_hiba"], esem)
                j = self.szakasz(esem, "teszt")[2]["teszt"]["jelentes"]
                self.assertEqual(j["forras"], nyelv)
                self.assertEqual(j["fajta"], "panic")
                if nyelv == "rust":
                    self.assertEqual((j["fajl"], j["sor"]), (fajl, 4))

    def test_forditasi_hiba_minden_mock_nyelven(self):
        for nyelv, fajl, sor in (("java", "Main.java", 3), ("go", "Megoldas.go", 2), ("rust", "Megoldas.rs", 2)):
            with self.subTest(nyelv=nyelv):
                r, esem = self.fut(nyelv, "HIBA\n", self.ECHO)
                f = self.szakasz(esem, "fordit_kesz")[0]["fordit"]
                self.assertFalse(f["ok"])
                d = f["diagnosztika"][0]
                self.assertEqual((d["fajl"], d["sor"], d["szint"]), (fajl, sor, "error"))
                self.assertEqual(self.szakasz(esem, "kesz")[0]["kod"], "kod.forditasi_hiba")

    def test_hianyzo_eszkozlanc_hibaszerzodes(self):
        cfg = KodCfg(self.cfg._c, {"eszkozok": {"go": str(self.t / "nincs" / "go"), "javac": str(self.t / "nincs" / "javac"),
                                                "java": str(self.t / "nincs" / "java"),
                                                "rustc": str(self.t / "nincs" / "rustc")}})
        for nyelv in ("java", "go", "rust"):
            with self.subTest(nyelv=nyelv):
                r, esem = self.fut(nyelv, "x\n", cfg=cfg)
                h = self.szakasz(esem, "hiba")
                self.assertEqual(len(h), 1, esem)
                self.assertEqual(h[0]["kod"], "kod.nincs_eszkozlanc")
                self.assertEqual(h[0]["param"]["nyelv"], KN.profil(nyelv).nev)
                self.assertTrue(h[0]["param"]["tipp"])
                self.assertIn(KN.profil(nyelv).nev, h[0]["uzenet"])
                self.assertEqual(self.szakasz(esem, "fordit_kesz"), [])


class DiagnosztikaTest(unittest.TestCase):
    """The parsers on the real tools' output formats (no toolchain needed)."""

    def test_fordito_formatumok(self):
        esetek = [
            ("gcc", "megoldas.swift:3:5: error: cannot find 'x' in scope\n    x = 1\n    ^\n", "megoldas.swift", (3, 5, "error")),
            ("gcc", "megoldas.rs:2:5: error[E0425]: cannot find value `x` in this scope\n", "megoldas.rs", (2, 5, "error")),
            ("gcc", "megoldas.rs:1:5: warning: unused variable: `y`\n", "megoldas.rs", (1, 5, "warning")),
            ("gcc", "# command-line-arguments\n./megoldas.go:7:2: declared and not used: x\n", "megoldas.go", (7, 2, "error")),
            ("javac", "Main.java:5: error: ';' expected\n        int x = 5\n                 ^\n1 error\n", "Main.java", (5, 18, "error")),
            ("javac", "Main.java:2: warning: [rawtypes] found raw type: List\n", "Main.java", (2, None, "warning")),
        ]
        for parser, szoveg, nev, (sor, oszlop, szint) in esetek:
            with self.subTest(szoveg=szoveg[:30]):
                d = D.fordito(parser, szoveg, nev)["diagnosztika"][0]
                self.assertEqual((d["sor"], d["oszlop"], d["szint"]), (sor, oszlop, szint))
                self.assertTrue(d["sajat"])

    def test_futasi_jelentesek(self):
        esetek = [
            ("python", 'Traceback (most recent call last):\n  File "/x/megoldas.py", line 3, in <module>\n    f()\n'
                       '  File "/x/megoldas.py", line 2, in f\n    return 1 / 0\nZeroDivisionError: division by zero\n',
             "megoldas.py", ("ZeroDivisionError", 2)),
            ("node", "/x/megoldas.js:2\n  a.b\n    ^\n\nTypeError: Cannot read properties of undefined\n"
                     "    at f (/x/megoldas.js:2:5)\n    at Object.<anonymous> (/x/megoldas.js:4:1)\n", "megoldas.js", ("TypeError", 2)),
            ("java", 'Exception in thread "main" java.lang.ArrayIndexOutOfBoundsException: Index 5 out of bounds\n'
                     "\tat Main.f(Main.java:9)\n\tat Main.main(Main.java:3)\n", "Main.java", ("ArrayIndexOutOfBoundsException", 9)),
            ("go", "panic: runtime error: integer divide by zero\n\ngoroutine 1 [running]:\nmain.main()\n"
                   "\t/x/megoldas.go:6 +0x1c\nexit status 2\n", "megoldas.go", ("panic", 6)),
            ("rust", "thread 'main' panicked at megoldas.rs:3:5:\nattempt to divide by zero\n", "megoldas.rs", ("panic", 3)),
            ("swift", "megoldas.swift:4: Fatal error: Index out of range\n", "megoldas.swift", ("fatal_error", 4)),
        ]
        for parser, stderr, nev, (fajta, sor) in esetek:
            with self.subTest(parser=parser):
                j = D.jelentes(parser, stderr, nev)
                self.assertIsNotNone(j)
                self.assertEqual((j["fajta"], j["sor"]), (fajta, sor))

    def test_ismeretlen_kimenet_nem_jelentes(self):
        self.assertIsNone(D.jelentes("python", "just some text\n", "megoldas.py"))
        self.assertIsNone(D.jelentes(None, "Traceback", "x"))
        self.assertEqual(D.fordito("gcc", "Note: this is prose: not a location\n", "m.py")["diagnosztika"], [])


if __name__ == "__main__":
    unittest.main()
