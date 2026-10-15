"""C36a: a `bin/mos cpp ellenoriz|formaz|homokozo-proba` parancssor (`modulok/cpp/__main__.py`) — a core ezt hívja
gyermekfolyamatként, JSON-sorokkal; a megszakítás SIGTERM. A valódi eszközláncon és sandbox-exec-kel fut."""
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from core import config, cpp_teszt
from modulok.cpp import __main__ as cli
from modulok.cpp import eszkoztar
from tests.helpers import REPO, alg_gyoker, tmpdir

MACOS = sys.platform == "darwin"
VALODI = config.load()
_E = eszkoztar.Eszkoztar(VALODI)
VAN = MACOS and _E.kesz() and _E.sdk_tbd_igazitva()
OK_SKIP = "[indokolt] nincs C++ eszköztár vagy sandbox-exec (bin/mos cpp telepit --igen; csak macOS)"

OSSZEG = ("#include <iostream>\nint main() {\n    int a, b;\n    std::cin >> a >> b;\n    std::cout << a + b << \"\\n\";\n}\n")
JEGYZET = """---
Tags:
Source:
Status:
NN:
Canvas:
---

# Összeg

```teszt Példa
--- bemenet
3 4
--- kimenet
7
```

```teszt Nulla
--- bemenet
0 0
--- kimenet
0
```

![[Összeg.cpp]]
"""


@unittest.skipUnless(VAN, OK_SKIP)
class EllenorizCliTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.root = alg_gyoker(str(self.t)).resolve()
        self.vault = self.root.parent / "Manifold"
        (self.vault / "D08 - Algo").mkdir(parents=True)
        self.md = self.vault / "D08 - Algo" / "Összeg.md"
        self.cpp = self.vault / "D08 - Algo" / "Összeg.cpp"
        self.md.write_text(JEGYZET, encoding="utf-8")
        self.cpp.write_text(OSSZEG, encoding="utf-8")
        self.env = {"MOS_ROOT": str(self.root), "HOME": str(self.t / "home"), "MOS_LLVM": str(VALODI.path("llvm")),
                    "MOS_SDK": str(VALODI.path("sdk")), "MOS_VAULT": str(self.vault), "PYTHONPATH": str(REPO),
                    "PATH": "/usr/bin:/bin"}
        self.cfg = config.load(self.env)

    def fut(self, *argv):
        ki, hiba = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(ki), contextlib.redirect_stderr(hiba):
            kod = cli.main(list(argv), cfg=self.cfg)
        return kod, ki.getvalue(), hiba.getvalue()

    def test_json_sorok_a_jegyzetbol_a_beagyazott_cpp_feloldasaval(self):
        kod, ki, _ = self.fut("ellenoriz", str(self.md), "--json-sorok")
        self.assertEqual(kod, 0)
        esemenyek = [json.loads(s) for s in ki.splitlines()]
        self.assertEqual([e["szakasz"] for e in esemenyek], ["indul", "fordit_kesz", "teszt", "teszt", "kesz"])
        self.assertEqual(esemenyek[0]["cpp"], "Összeg.cpp")
        self.assertEqual(esemenyek[0]["tesztek_db"], 2)
        self.assertEqual(esemenyek[2]["teszt"]["cim"], "Példa")
        self.assertTrue(esemenyek[-1]["atment"])

    def test_a_cpp_es_a_jegyzet_kulon_megadva(self):
        kod, ki, _ = self.fut("ellenoriz", str(self.cpp), "--jegyzet", str(self.md), "--json-sorok")
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(ki.splitlines()[-1])["tesztek_db"], 2)

    def test_csak_cpp_jegyzet_nelkul_csak_fordit(self):
        kod, ki, _ = self.fut("ellenoriz", str(self.cpp), "--json-sorok")
        kesz = json.loads(ki.splitlines()[-1])
        self.assertEqual((kesz["tesztek_db"], kesz["fordit_ok"], kesz["atment"]), (0, True, False))
        self.assertEqual(kod, 1)

    def test_nem_atmeno_megoldas_1_es_kilepesi_kod(self):
        self.cpp.write_text(OSSZEG.replace("a + b", "a - b"), encoding="utf-8")
        kod, ki, _ = self.fut("ellenoriz", str(self.md), "--json-sorok")
        self.assertEqual(kod, 1)
        self.assertFalse(json.loads(ki.splitlines()[-1])["atment"])

    def test_hibakereso_kapcsolo(self):
        kod, ki, _ = self.fut("ellenoriz", str(self.md), "--hibakereso", "--json-sorok")
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(ki.splitlines()[0])["mod"], "hibakereso")

    def test_szoveges_kimenet_a_diffel_es_a_fordito_hibaval(self):
        self.cpp.write_text(OSSZEG.replace("a + b", "a - b"), encoding="utf-8")
        kod, ki, _ = self.fut("ellenoriz", str(self.md))
        self.assertIn("fordítás: ✓", ki)
        self.assertIn("hibás kimenet", ki)
        self.assertIn("várt:", ki)
        self.assertIn("kapott:", ki)
        self.assertIn("1/2 teszt ment át", ki)           # a „0 0” teszten az a − b is 0
        self.cpp.write_text("int main() { int x = ; }\n", encoding="utf-8")
        kod, ki, _ = self.fut("ellenoriz", str(self.md))
        self.assertIn("fordítás: ✗", ki)
        self.assertIn("Összeg.cpp:1:", ki)

    def test_hianyzo_beagyazas_vagy_fajl(self):
        self.md.write_text("# Nincs beágyazás\n\n```teszt\n--- kimenet\n1\n```\n", encoding="utf-8")
        kod, ki, hiba = self.fut("ellenoriz", str(self.md), "--json-sorok")
        self.assertEqual(kod, 2)
        self.assertIn("nincs beágyazott .cpp", hiba)
        kod, ki, hiba = self.fut("ellenoriz", str(self.vault / "nincs.cpp"), "--json-sorok")
        self.assertEqual(kod, 2)

    def test_a_beagyazott_cpp_feloldasa_a_vault_mas_mappajabol(self):
        (self.vault / "Forrasok").mkdir()
        (self.vault / "Forrasok" / "Máshol.cpp").write_text(OSSZEG, encoding="utf-8")
        self.md.write_text(JEGYZET.replace("![[Összeg.cpp]]", "![[Máshol.cpp]]"), encoding="utf-8")
        kod, ki, _ = self.fut("ellenoriz", str(self.md), "--json-sorok")
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(ki.splitlines()[0])["cpp"], "Máshol.cpp")

    def test_a_blokk_idokorlat_maximuma_a_configbol(self):
        self.md.write_text(JEGYZET.replace("--- kimenet\n7\n", "--- kimenet\n7\n--- idokorlat\n99\n"), encoding="utf-8")
        kod, ki, _ = self.fut("ellenoriz", str(self.md), "--json-sorok")
        t = [json.loads(s) for s in ki.splitlines() if '"teszt"' in s and '"szakasz": "teszt"' in s]
        self.assertEqual(t[0]["teszt"]["allapot"], "hibas_teszt")
        self.assertIn("legfeljebb 10", t[0]["teszt"]["hiba"])

    def test_sigterm_leallitja_a_futast_nincs_arva_folyamat(self):
        self.md.write_text(JEGYZET.replace("--- kimenet\n7\n", "--- kimenet\n7\n--- idokorlat\n10\n"), encoding="utf-8")
        self.cpp.write_text("int main() { for (;;) {} }\n", encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-B", "-m", "modulok.cpp", "ellenoriz", str(self.md), "--json-sorok"],
                             env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO))
        sorok = []
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60:                          # a fordítás után a végtelen ciklus már fut
            sor = p.stdout.readline()
            if not sor:
                break
            sorok.append(json.loads(sor))
            if sorok[-1]["szakasz"] == "fordit_kesz":
                time.sleep(0.8)
                break
        self.assertEqual(sorok[-1]["szakasz"], "fordit_kesz", sorok)
        p.send_signal(signal.SIGTERM)
        t1 = time.monotonic()
        kod = p.wait(timeout=15)
        self.assertLess(time.monotonic() - t1, 5)
        maradek = [json.loads(s) for s in p.stdout.read().splitlines()]
        self.assertEqual(maradek[-1]["szakasz"], "megszakitva")
        self.assertEqual(kod, 2)
        p.stdout.close()
        p.stderr.close()
        hiv = subprocess.run(["pgrep", "-f", str(self.cfg.path("tmp") / "cpp")], capture_output=True, text=True)
        self.assertEqual(hiv.stdout.strip(), "", "árva futtatott program maradt")


@unittest.skipUnless(VAN, OK_SKIP)
class FormazCliTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = alg_gyoker(self._t.name).resolve()
        self.cfg = config.load({"MOS_ROOT": str(self.root), "HOME": self._t.name, "MOS_LLVM": str(VALODI.path("llvm")),
                                "MOS_SDK": str(VALODI.path("sdk"))})

    def test_formaz_stdinrol(self):
        be = io.StringIO("int main(){return 0;}\n")
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            import sys as _s
            regi, _s.stdin = _s.stdin, be
            try:
                kod = cli.main(["formaz", "-"], cfg=self.cfg)
            finally:
                _s.stdin = regi
        self.assertEqual(kod, 0)
        self.assertEqual(ki.getvalue(), "int main() {\n    return 0;\n}\n")

    def test_formaz_fajlbol_es_a_fajl_valtozatlan(self):
        f = Path(self._t.name) / "x.cpp"
        f.write_text("int  main( ){ }\n")
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            kod = cli.main(["formaz", str(f)], cfg=self.cfg)
        self.assertEqual((kod, ki.getvalue()), (0, "int main() {}\n"))
        self.assertEqual(f.read_text(), "int  main( ){ }\n")


@unittest.skipUnless(VAN, OK_SKIP)
class HomokozoProbaCliTest(unittest.TestCase):
    def test_a_teljes_probakeszlet_rendben(self):
        t = tmpdir()
        self.addCleanup(t.cleanup)
        root = alg_gyoker(t.name).resolve()
        cfg = config.load({"MOS_ROOT": str(root), "HOME": t.name, "MOS_LLVM": str(VALODI.path("llvm")),
                           "MOS_SDK": str(VALODI.path("sdk"))})
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            kod = cli.main(["homokozo-proba"], cfg=cfg)
        szoveg = ki.getvalue()
        self.assertEqual(kod, 0, szoveg)
        self.assertIn("RENDBEN:", szoveg)
        self.assertNotIn("HIBA ", szoveg)
        self.assertGreaterEqual(szoveg.count("RENDBEN "), 18)


if __name__ == "__main__":
    unittest.main()
