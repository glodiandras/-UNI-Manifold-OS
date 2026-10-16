"""F10: the multi-language workbench endpoints on the real core, on a fake vault (`core/kod_utvonal.py`, `/api/kod/*`): the
language list, the note ↔ source pairing of a Python task, a check run through the engine child process in the real sandbox
(the embedded Python), the summary for late joiners, the `kod_futas` WS events, and the error contract (`kod` + `param` +
English message). The C36a `/api/cpp/*` endpoints answer as before on the same vault."""
import json
import os
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from core import config
from tests.helpers import ir
from tests.index_segedek import var_ra
from tests.test_core_api import _Szerver, ws_connect, ws_csatlakozik

MACOS = sys.platform == "darwin" and os.access("/usr/bin/sandbox-exec", os.X_OK)
VALODI = config.load()
MAPPA = "Programozas"
JEGYZET = f"{MAPPA}/Osszeg.md"
FORRAS = f"{MAPPA}/Osszeg.py"
PY = "a, b = map(int, input().split())\nprint(a + b)\n"
NOTE = """# Sum
```teszt Example
--- bemenet
3 4
--- kimenet
7
```
```teszt Zero
--- bemenet
0 0
--- kimenet
0
```
![[Osszeg.py]]
"""


class KodApiTest(_Szerver):
    def elokeszit(self):
        self.cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"),
                                "MOS_RUNTIME": str(VALODI.path("runtime")), "MOS_LLVM": str(VALODI.path("llvm")),
                                "MOS_SDK": str(VALODI.path("sdk"))})
        ir(self.v, JEGYZET, NOTE)
        ir(self.v, FORRAS, PY)

    def setUp(self):
        super().setUp()
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/vault/index")[1].get("kesz"), 30))

    def feladat(self, ut):
        return self.k("GET", "/api/kod/feladat?ut=" + quote(ut))

    def test_parositas_jegyzetbol_es_forrasbol(self):
        kod, d = self.feladat(JEGYZET)
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["nyelv"], d["jegyzet"], d["forras"]), ("python", JEGYZET, FORRAS))
        self.assertEqual([t["cim"] for t in d["tesztek"]], ["Example", "Zero"])
        self.assertTrue(var_ra(lambda: self.feladat(FORRAS)[1].get("jegyzet") == JEGYZET, 30))
        self.assertEqual(self.feladat(FORRAS)[1]["nyelv"], "python")

    def test_hibaszerzodes(self):
        for ut_, body, statusz, kod in (
                ("/api/kod/ellenoriz", {"ut": f"{MAPPA}/x.txt"}, 400, "kod.ismeretlen_kiterjesztes"),
                ("/api/kod/ellenoriz", {"ut": JEGYZET, "mod": "hibakereso"}, 400, "kod.mod_nem_tamogatott"),
                ("/api/kod/ellenoriz", {"ut": JEGYZET, "mod": "lassu"}, 400, "kod.ismeretlen_mod"),
                ("/api/kod/ellenoriz", {"ut": JEGYZET, "nyelv": "cobol"}, 400, "kod.ismeretlen_nyelv"),
                ("/api/kod/ai", {"ut": JEGYZET, "mod": "megoldas"}, 400, "kod.megerosites_kell"),
                ("/api/kod/ai", {"ut": JEGYZET, "mod": "valami"}, 400, "kod.ismeretlen_ai_mod"),
                ("/api/kod/megszakit", {"futas": "kod-000000000000"}, 404, "kod.nincs_ilyen_futas")):
            with self.subTest(ut=ut_, body=body):
                s, d = self.k("POST", ut_, body)
                self.assertEqual(s, statusz, d)
                self.assertEqual(d.get("kod"), kod, d)
                self.assertTrue(d.get("hiba") or d.get("uzenet"), d)
        self.assertEqual(self.k("GET", "/api/kod/futas/kod-000000000000")[0], 404)
        s, d = self.feladat(f"{MAPPA}/Nincs.py")
        self.assertEqual((s, d.get("kod")), (404, "kod.nincs_forras"))

    @unittest.skipUnless(MACOS, "[indokolt] nincs sandbox-exec (csak macOS)")
    def test_nyelvek(self):
        s, d = self.k("GET", "/api/kod/nyelvek")
        self.assertEqual(s, 200, d)
        nyelvek = {n["azonosito"]: n for n in d["nyelvek"]}
        self.assertEqual(set(nyelvek), {"cpp", "c", "python", "javascript", "typescript", "java", "go", "rust", "swift"})
        self.assertTrue(nyelvek["python"]["elerheto"], nyelvek["python"])
        for n in nyelvek.values():
            self.assertTrue(n["elerheto"] or n["hiba"]["kod"] == "kod.nincs_eszkozlanc", n)

    @unittest.skipUnless(MACOS and ws_connect is not None, "[indokolt] nincs sandbox-exec vagy WS-kliens (csak macOS, venv)")
    def test_ellenorzes_python_homokozoban_ws_esemenyekkel(self):
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))                                       # hello
            s, d = self.k("POST", "/api/kod/ellenoriz", {"ut": JEGYZET})
            self.assertEqual(s, 202, d)
            self.assertEqual((d["nyelv"], d["forras"], d["tesztek_db"]), ("python", FORRAS, 2))
            fid = d["futas"]
            es = []
            t0 = time.time()
            while time.time() - t0 < 60 and not (es and es[-1]["szakasz"] in ("kesz", "hiba")):
                e = json.loads(ws.recv(timeout=60))
                if e.get("tipus") == "kod_futas" and e.get("futas") == fid:
                    es.append(e)
        self.assertEqual([e["szakasz"] for e in es], ["indul", "fordit_kesz", "teszt", "teszt", "kesz"], es)
        for e in es:
            self.assertEqual((e["nyelv"], e["forras"], e["jegyzet"], e["mod"]), ("python", FORRAS, JEGYZET, "gyors"))
        self.assertTrue(es[-1]["atment"])
        kod, o = self.k("GET", f"/api/kod/futas/{fid}")
        self.assertEqual(kod, 200)
        self.assertEqual(o["allapot"], "kesz", o)
        self.assertEqual([t["allapot"] for t in o["tesztek"]], ["atment", "atment"])
        self.assertTrue(o["fordit"]["ok"])
        s, d = self.k("POST", "/api/kod/megszakit", {"futas": fid})
        self.assertEqual((s, d["megszakitva"]), (200, False))

    def test_cpp_vegpontok_valtozatlanok(self):
        ir(self.v, f"{MAPPA}/C.md", "# C\n```teszt\n--- kimenet\n1\n```\n![[C.cpp]]\n")
        ir(self.v, f"{MAPPA}/C.cpp", "int main() {}\n")
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/cpp/feladat?ut=" + quote(f"{MAPPA}/C.md"))[1].get("cpp")
                               == f"{MAPPA}/C.cpp", 30))
        s, d = self.k("GET", "/api/kod/feladat?ut=" + quote(f"{MAPPA}/C.md"))
        self.assertEqual((s, d["nyelv"], d["forras"]), (200, "cpp", f"{MAPPA}/C.cpp"))


if __name__ == "__main__":
    unittest.main()
