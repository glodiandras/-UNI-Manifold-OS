"""C36a: a C++ munkafelület végpontjai a valódi core-on, álvaulton (`core/cpp_utvonal.py`): `/api/cpp/allapot|feladat|ellenoriz|
futas|megszakit|formaz`, a `cpp_futas` WS-események, a tracker-esemény, a megszakítás és a leállás.

A feladat-párosítás, az új feladat és a hibaágak az eszközlánc nélkül is futnak; az ellenőrzés a valódi LLVM-mel és
`sandbox-exec`-cel (különben `[indokolt]` kihagyás)."""
import json
import os
import sqlite3
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from core import config, cpp_teszt
from modulok.cpp import eszkoztar
from tests.helpers import ir
from tests.index_segedek import var_ra
from tests.test_core_api import _Szerver, ws_connect, ws_csatlakozik

MACOS = sys.platform == "darwin"
VALODI = config.load()
_E = eszkoztar.Eszkoztar(VALODI)
VAN = MACOS and _E.kesz() and _E.sdk_tbd_igazitva()
FIGYELO_SKIP = "[indokolt] a futás közben írt fájlt az index csak az FSEvents-figyelővel látja (csak macOS)"
OK_SKIP = "[indokolt] nincs C++ eszköztár vagy sandbox-exec (bin/mos cpp telepit --igen; csak macOS)"

MAPPA = "D08 - Algoritmizálás és programozás"
JEGYZET = f"{MAPPA}/Összeg.md"
CPP = f"{MAPPA}/Összeg.cpp"
OSSZEG = ("#include <iostream>\nint main() {\n    int a, b;\n    std::cin >> a >> b;\n"
          "    std::cout << a + b << \"\\n\";\n}\n")
NOTE = """---
Tags:
  - Informatics
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


def eszkoztarral(tmp_cfg_root: Path, home: str) -> config.Config:
    return config.load({"MOS_ROOT": str(tmp_cfg_root), "HOME": home, "MOS_LLVM": str(VALODI.path("llvm")),
                        "MOS_SDK": str(VALODI.path("sdk")), "MOS_RUNTIME": str(VALODI.path("runtime"))})


class CppApiAlap(_Szerver):
    """Közös előkészítés: a feladat-jegyzet és a megoldás az álvaultban; `PYTHONPATH` a gyermekfolyamatoknak."""
    ESZKOZTARRAL = False

    def elokeszit(self):
        if self.ESZKOZTARRAL:
            self.cfg = eszkoztarral(self.root, str(Path(self._t.name) / "home"))
        ir(self.v, JEGYZET, NOTE)
        ir(self.v, CPP, OSSZEG)

    def vegpont_var(self, kep, mp=30):
        return var_ra(kep, mp)

    def pos(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.cfg.path("szemelyes") / "pos.sqlite")
        c.row_factory = sqlite3.Row
        self.addCleanup(c.close)
        return c


class FeladatTest(CppApiAlap):
    def setUp(self):
        super().setUp()
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/index")[1].get("kesz")))
        self.assertTrue(self.vegpont_var(lambda: any(
            f["ut"] == CPP for f in self.k("GET", "/api/vault/fa")[1]["fajlok"])))

    def feladat(self, ut):
        return self.k("GET", "/api/cpp/feladat?ut=" + quote(ut))

    def test_jegyzetbol_a_tesztek_es_a_beagyazott_cpp(self):
        kod, d = self.feladat(JEGYZET)
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["jegyzet"], d["cpp"], d["jegyzetek"]), (JEGYZET, CPP, [JEGYZET]))
        self.assertEqual([t["cim"] for t in d["tesztek"]], ["Példa", "Nulla"])
        self.assertEqual(d["tesztek"][0]["bemenet"], "3 4\n")
        self.assertEqual(d["tesztek"][0]["kimenet"], "7\n")
        self.assertIsNone(d["tesztek"][0]["hiba"])
        self.assertIsNone(d.get("hiba"))

    def test_cpp_bol_a_visszahivatkozo_jegyzet(self):
        kod, d = self.feladat(CPP)
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["jegyzet"], d["cpp"], d["jegyzetek"]), (JEGYZET, CPP, [JEGYZET]))
        self.assertEqual(len(d["tesztek"]), 2)

    @unittest.skipUnless(MACOS, FIGYELO_SKIP)
    def test_tobb_jegyzet_ugyanazt_a_cpp_t_agyazza_be(self):
        ir(self.v, f"{MAPPA}/Másik.md", NOTE.replace("# Összeg", "# Másik"))
        self.assertTrue(self.vegpont_var(lambda: len(self.feladat(CPP)[1]["jegyzetek"]) == 2))
        d = self.feladat(CPP)[1]
        self.assertIsNone(d["jegyzet"])
        self.assertEqual(sorted(d["jegyzetek"]), [f"{MAPPA}/Másik.md", JEGYZET])
        self.assertEqual(d["tesztek"], [])

    @unittest.skipUnless(MACOS, FIGYELO_SKIP)
    def test_a_teszt_nelkuli_beagyazo_jegyzet_nem_jelolt(self):
        ir(self.v, f"{MAPPA}/Csak link.md", "# Link\n\n![[Összeg.cpp]]\n")
        self.assertTrue(self.vegpont_var(lambda: any(
            "Csak link" in s["ut"] for s in self.k("GET", "/api/vault/visszahivatkozasok?ut=" + quote(CPP))[1]["forrasok"])))
        self.assertEqual(self.feladat(CPP)[1]["jegyzetek"], [JEGYZET])

    @unittest.skipUnless(MACOS, FIGYELO_SKIP)
    def test_beagyazas_nelkuli_jegyzet(self):
        ir(self.v, f"{MAPPA}/Nincs.md", "# Nincs\n\n```teszt\n--- kimenet\n1\n```\n")
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/jegyzet?ut=" + quote(f"{MAPPA}/Nincs.md"))[0] == 200))
        kod, d = self.feladat(f"{MAPPA}/Nincs.md")
        self.assertEqual(kod, 200)
        self.assertIsNone(d["cpp"])
        self.assertIn("nincs beágyazott .cpp", d["hiba"])
        self.assertEqual(len(d["tesztek"]), 1)

    def test_hibas_blokk_a_listaban_hibaval(self):
        ir(self.v, JEGYZET, NOTE.replace("--- kimenet\n0\n", ""))
        self.assertTrue(self.vegpont_var(lambda: self.feladat(JEGYZET)[1]["tesztek"][1]["hiba"] is not None, 10))
        self.assertIn("kimenet", self.feladat(JEGYZET)[1]["tesztek"][1]["hiba"])

    def test_hibas_utak(self):
        for ut in ("", "../kint.md", "x.png", "x.txt", ".rejtett.md"):
            self.assertIn(self.feladat(ut)[0], (400, 404), ut)
        self.assertEqual(self.feladat(f"{MAPPA}/Nincs-ilyen.md")[0], 404)
        self.assertEqual(self.k("GET", "/api/cpp/feladat")[0], 400)

    @unittest.skipUnless(MACOS, FIGYELO_SKIP)
    def test_feladat_keres_cpp_nek_a_hianyzo_cpp_hiba(self):
        ir(self.v, f"{MAPPA}/Hiányzó.md", "# H\n\n```teszt\n--- kimenet\n1\n```\n\n![[Nincs ilyen.cpp]]\n")
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/jegyzet?ut=" + quote(f"{MAPPA}/Hiányzó.md"))[0] == 200))
        d = self.feladat(f"{MAPPA}/Hiányzó.md")[1]
        self.assertIsNone(d["cpp"])
        self.assertIn("nem található", d["hiba"])


class UjFeladatTest(CppApiAlap):
    def setUp(self):
        super().setUp()
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/index")[1].get("kesz")))

    def uj(self, **d):
        return self.k("POST", "/api/cpp/feladat", d)

    def test_letrehozas_jegyzet_es_cpp_a_beepitett_vazzal(self):
        kod, d = self.uj(mappa=MAPPA, nev="Szorzás")
        self.assertEqual(kod, 201, d)
        self.assertEqual((d["jegyzet"], d["cpp"]), (f"{MAPPA}/Szorzás.md", f"{MAPPA}/Szorzás.cpp"))
        md = (self.v / d["jegyzet"]).read_text(encoding="utf-8")
        self.assertEqual(md, cpp_teszt.feladat_vaz("Szorzás", "Informatics"))
        self.assertIn("Tags:\n  - Informatics\n", md)
        self.assertIn("![[Szorzás.cpp]]", md)
        self.assertEqual((self.v / d["cpp"]).read_text(encoding="utf-8"), cpp_teszt.cpp_vaz())
        self.assertEqual(len(cpp_teszt.tesztek(md)), 1)

    def test_a_cimke_a_legfelso_mappa_betujebol_a_gyokerben_ures(self):
        kod, d = self.uj(mappa="", nev="Gyökér")
        self.assertEqual(kod, 201, d)
        self.assertTrue((self.v / "Gyökér.md").read_text(encoding="utf-8").startswith("---\nTags:\nSource:"))
        kod, d = self.uj(mappa="M01 - Matek", nev="Matekfeladat")
        self.assertEqual(kod, 404)                                              # a mappa nem létezik
        (self.v / "M01 - Matek").mkdir()
        self.assertEqual(self.uj(mappa="M01 - Matek", nev="Matekfeladat")[0], 201)
        self.assertIn("Tags:\n  - Mathematics\n", (self.v / "M01 - Matek" / "Matekfeladat.md").read_text(encoding="utf-8"))

    def test_a_sablonmappa_cpp_feladat_jegyzete_felulirja_a_vazat(self):
        ir(self.v, "_Template/C++ feladat.md", "# {{title}}\n\nSaját váz.\n\n![[{{title}}.cpp]]\n")
        kod, d = self.uj(mappa=MAPPA, nev="Sajat")
        self.assertEqual(kod, 201, d)
        self.assertEqual((self.v / d["jegyzet"]).read_text(encoding="utf-8"), "# Sajat\n\nSaját váz.\n\n![[Sajat.cpp]]\n")

    def test_meglevo_nev_nem_ir_felul_es_nem_hagy_arva_cpp_t(self):
        ir(self.v, f"{MAPPA}/Foglalt.md", "# régi\n")
        kod, d = self.uj(mappa=MAPPA, nev="foglalt")                            # kis-nagybetűtől független ütközés
        self.assertEqual(kod, 400, d)
        self.assertFalse((self.v / MAPPA / "foglalt.cpp").exists())
        self.assertFalse((self.v / MAPPA / "Foglalt.cpp").exists())
        self.assertEqual((self.v / f"{MAPPA}/Foglalt.md").read_text(encoding="utf-8"), "# régi\n")
        ir(self.v, f"{MAPPA}/Cpp.cpp", "// régi\n")
        self.assertEqual(self.uj(mappa=MAPPA, nev="Cpp")[0], 400)
        self.assertFalse((self.v / MAPPA / "Cpp.md").exists())

    def test_hibas_nev_es_mappa(self):
        for nev in ("", ".rejtett", "a/b", "x#y", "a:b", None):
            self.assertEqual(self.uj(mappa=MAPPA, nev=nev)[0], 400, nev)
        self.assertEqual(self.uj(mappa="Nincs ilyen mappa", nev="X")[0], 404)
        self.assertEqual(self.uj(mappa="../kint", nev="X")[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/feladat", {})[0], 400)

    def test_a_nev_vegi_kiterjesztes_levagodik(self):
        kod, d = self.uj(mappa=MAPPA, nev="Vége.cpp")
        self.assertEqual((kod, d["cpp"]), (201, f"{MAPPA}/Vége.cpp"))

    def test_a_letrehozott_feladat_azonnal_ellenorizheto_parban(self):
        self.uj(mappa=MAPPA, nev="Új")
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/cpp/feladat?ut=" + quote(f"{MAPPA}/Új.md"))[1].get("cpp") == f"{MAPPA}/Új.cpp"))


class EszkoztarNelkulTest(CppApiAlap):
    def elokeszit(self):
        super().elokeszit()
        self.cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(Path(self._t.name) / "home"),
                                "MOS_LLVM": str(Path(self._t.name) / "nincs-llvm"), "MOS_SDK": str(Path(self._t.name) / "nincs-sdk")})

    def setUp(self):
        super().setUp()
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/index")[1].get("kesz")))
        self.assertTrue(self.vegpont_var(lambda: any(f["ut"] == CPP for f in self.k("GET", "/api/vault/fa")[1]["fajlok"])))

    def test_allapot_nem_kesz(self):
        kod, d = self.k("GET", "/api/cpp/allapot")
        self.assertEqual(kod, 200, d)
        self.assertFalse(d["kesz"])
        self.assertIn("clang++", d["hianyzo"])
        self.assertIsNone(d["futas"])

    def test_ellenoriz_503_magyar_uzenettel(self):
        kod, d = self.k("POST", "/api/cpp/ellenoriz", {"ut": JEGYZET})
        self.assertEqual(kod, 503)
        self.assertIn("bin/mos cpp telepit", d["hiba"])

    def test_formaz_503(self):
        kod, d = self.k("POST", "/api/cpp/formaz", {"szoveg": "int main(){}"})
        self.assertEqual(kod, 503)
        self.assertIn("clang-format", d["hiba"])

    def test_hibas_torzsek(self):
        self.assertEqual(self.k("POST", "/api/cpp/ellenoriz", {})[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/ellenoriz", {"ut": 5})[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/ellenoriz", {"ut": JEGYZET, "mod": "gyorsabb"})[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/ellenoriz", {"ut": "x.txt"})[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/formaz", {})[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/formaz", {"szoveg": 5})[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/megszakit", {})[0], 400)

    def test_ismeretlen_futas(self):
        self.assertEqual(self.k("GET", "/api/cpp/futas/futas-nincs")[0], 404)
        kod, d = self.k("POST", "/api/cpp/megszakit", {"futas": "futas-nincs"})
        self.assertEqual(kod, 404)

    def test_a_hibas_uttal_a_futas_id_nem_injektalhato(self):
        self.assertEqual(self.k("GET", "/api/cpp/futas/..%2f..%2fetc")[0], 404)


@unittest.skipUnless(VAN, OK_SKIP)
class FormazasTest(CppApiAlap):
    ESZKOZTARRAL = True

    def test_formaz(self):
        kod, d = self.k("POST", "/api/cpp/formaz", {"szoveg": "int main(){int x=1;return x;}\n"})
        self.assertEqual(kod, 200, d)
        self.assertTrue(d["valtozott"])
        self.assertEqual(d["szoveg"], "int main() {\n    int x = 1;\n    return x;\n}\n")

    def test_mar_formazott_nem_valtozott(self):
        s = "int main() {\n    return 0;\n}\n"
        d = self.k("POST", "/api/cpp/formaz", {"szoveg": s})[1]
        self.assertEqual((d["szoveg"], d["valtozott"]), (s, False))

    def test_tul_nagy_szoveg_400(self):
        self.assertEqual(self.k("POST", "/api/cpp/formaz", {"szoveg": "x" * (3 * 1024 * 1024)})[0], 400)

    def test_allapot_kesz(self):
        kod, d = self.k("GET", "/api/cpp/allapot")
        self.assertEqual(kod, 200)
        self.assertTrue(d["kesz"], d)
        self.assertTrue(d["clang_format"])
        self.assertTrue(d["sdk_tbd_igazitva"])


@unittest.skipUnless(VAN and ws_connect is not None, OK_SKIP)
class EllenorzesApiTest(CppApiAlap):
    ESZKOZTARRAL = True

    def setUp(self):
        super().setUp()
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/index")[1].get("kesz")))
        self.assertTrue(self.vegpont_var(lambda: any(f["ut"] == CPP for f in self.k("GET", "/api/vault/fa")[1]["fajlok"])))
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/cpp/feladat?ut=" + quote(CPP))[1].get("jegyzet") == JEGYZET))

    def esemenyek(self, ws, futas, vege=("kesz", "hiba", "megszakitva"), mp=90):
        ki = []
        t0 = time.monotonic()
        while time.monotonic() - t0 < mp:
            e = json.loads(ws.recv(timeout=mp))
            if e.get("tipus") == "cpp_futas" and e["futas"] == futas:
                ki.append(e)
                if e["szakasz"] in vege:
                    break
        return ki

    def indit(self, ws, **d):
        kod, r = self.k("POST", "/api/cpp/ellenoriz", {"ut": JEGYZET, **d})
        self.assertEqual(kod, 202, r)
        return r

    def test_ellenorzes_ws_esemenyek_es_a_futas_vegpont(self):
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))                                       # hello
            r = self.indit(ws)
            self.assertEqual((r["jegyzet"], r["cpp"], r["mod"], r["tesztek_db"]), (JEGYZET, CPP, "gyors", 2))
            es = self.esemenyek(ws, r["futas"])
        self.assertEqual([e["szakasz"] for e in es], ["indul", "fordit_kesz", "teszt", "teszt", "kesz"])
        for e in es:
            self.assertEqual((e["ut"], e["jegyzet"], e["mod"]), (CPP, JEGYZET, "gyors"))
        self.assertTrue(es[-1]["atment"])
        self.assertEqual(es[2]["teszt"]["cim"], "Példa")
        kod, f = self.k("GET", f"/api/cpp/futas/{r['futas']}")
        self.assertEqual(kod, 200)
        self.assertEqual((f["allapot"], f["tesztek_db"], len(f["tesztek"])), ("kesz", 2, 2))
        self.assertTrue(f["fordit"]["ok"])
        self.assertTrue(f["kesz"]["atment"])

    def test_cpp_bol_inditva_ugyanaz(self):
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            kod, r = self.k("POST", "/api/cpp/ellenoriz", {"ut": CPP})
            self.assertEqual((kod, r["jegyzet"], r["tesztek_db"]), (202, JEGYZET, 2))
            self.assertTrue(self.esemenyek(ws, r["futas"])[-1]["atment"])

    def test_hibakereso_mod(self):
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            r = self.indit(ws, mod="hibakereso")
            es = self.esemenyek(ws, r["futas"])
        self.assertEqual(es[0]["mod"], "hibakereso")
        self.assertTrue(es[-1]["atment"])

    def test_a_tracker_esemeny_kod_nelkul_a_feladat_utjaval(self):
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            r = self.indit(ws)
            self.esemenyek(ws, r["futas"])
        sor = self.pos().execute("SELECT tipus, tantargy, ut, adat FROM tr_esemeny WHERE tipus = 'cpp_proba'").fetchone()
        self.assertIsNotNone(sor)
        self.assertEqual((sor["tantargy"], sor["ut"]), ("Informatics", JEGYZET))
        adat = json.loads(sor["adat"])
        self.assertEqual({k: adat[k] for k in ("atment", "tesztek", "atment_db", "fordit_ok", "mod")},
                         {"atment": True, "tesztek": 2, "atment_db": 2, "fordit_ok": True, "mod": "gyors"})
        self.assertNotIn("int main", sor["adat"])
        self.assertEqual(set(adat), {"atment", "tesztek", "atment_db", "fordit_ok", "mod", "ms"})

    def test_a_nem_atmeno_proba_is_beirodik(self):
        ir(self.v, CPP, OSSZEG.replace("a + b", "a - b"))
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/fajl?ut=" + quote(CPP))[1]["tartalom"].count("a - b") == 1))
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            r = self.indit(ws)
            es = self.esemenyek(ws, r["futas"])
        self.assertFalse(es[-1]["atment"])
        adat = json.loads(self.pos().execute("SELECT adat FROM tr_esemeny WHERE tipus = 'cpp_proba'").fetchone()[0])
        self.assertEqual((adat["atment"], adat["atment_db"], adat["tesztek"]), (False, 1, 2))

    def test_a_kikapcsolt_tracker_nem_ir(self):
        from core import vezerlo
        vezerlo.kapcsolo_ir(self.cfg, {"tracker": False})
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            r = self.indit(ws)
            self.esemenyek(ws, r["futas"])
        self.assertFalse((self.cfg.path("szemelyes") / "pos.sqlite").exists())

    def test_cpp_jegyzet_nelkul_csak_fordit_nincs_tracker_esemeny(self):
        (self.v / MAPPA / "Egyedül.cpp").write_text(OSSZEG, encoding="utf-8")
        self.assertTrue(self.vegpont_var(lambda: any(f["ut"] == f"{MAPPA}/Egyedül.cpp" for f in self.k("GET", "/api/vault/fa")[1]["fajlok"])))
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            kod, r = self.k("POST", "/api/cpp/ellenoriz", {"ut": f"{MAPPA}/Egyedül.cpp"})
            self.assertEqual((kod, r["jegyzet"], r["tesztek_db"]), (202, None, 0))
            es = self.esemenyek(ws, r["futas"])
        self.assertEqual([e["szakasz"] for e in es], ["indul", "fordit_kesz", "kesz"])
        self.assertFalse((self.cfg.path("szemelyes") / "pos.sqlite").exists())

    def test_tobbertelmu_jegyzet_409_a_jeloltekkel(self):
        ir(self.v, f"{MAPPA}/Másik.md", NOTE.replace("# Összeg", "# Másik"))
        self.assertTrue(self.vegpont_var(lambda: len(self.k("GET", "/api/cpp/feladat?ut=" + quote(CPP))[1]["jegyzetek"]) == 2))
        kod, d = self.k("POST", "/api/cpp/ellenoriz", {"ut": CPP})
        self.assertEqual(kod, 409, d)
        self.assertEqual(d["kod"], "tobbertelmu")
        self.assertEqual(sorted(d["jegyzetek"]), [f"{MAPPA}/Másik.md", JEGYZET])
        with ws_csatlakozik(self.port) as ws:                 # a kiválasztott jegyzettel megy
            json.loads(ws.recv(timeout=5))
            kod, r = self.k("POST", "/api/cpp/ellenoriz", {"ut": CPP, "jegyzet": JEGYZET})
            self.assertEqual((kod, r["jegyzet"]), (202, JEGYZET))
            self.esemenyek(ws, r["futas"])

    def test_beagyazas_nelkuli_jegyzet_400(self):
        ir(self.v, f"{MAPPA}/Nincs.md", "# Nincs\n\n```teszt\n--- kimenet\n1\n```\n")
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/jegyzet?ut=" + quote(f"{MAPPA}/Nincs.md"))[0] == 200))
        kod, d = self.k("POST", "/api/cpp/ellenoriz", {"ut": f"{MAPPA}/Nincs.md"})
        self.assertEqual((kod, d["kod"]), (400, "nincs_cpp"))

    def test_egyszerre_egy_futas_a_masodik_409(self):
        ir(self.v, JEGYZET, NOTE.replace("--- kimenet\n7\n", "--- kimenet\n7\n--- idokorlat\n8\n"))
        ir(self.v, CPP, "int main() { for (;;) {} }\n")
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/cpp/feladat?ut=" + quote(JEGYZET))[1]["tesztek"][0]["idokorlat_s"] == 8.0))
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            r = self.indit(ws)
            kod, d = self.k("POST", "/api/cpp/ellenoriz", {"ut": JEGYZET})
            self.assertEqual((kod, d["kod"], d["futas"]), (409, "foglalt", r["futas"]))
            self.assertEqual(self.k("GET", "/api/cpp/allapot")[1]["futas"], r["futas"])
            self.k("POST", "/api/cpp/megszakit", {"futas": r["futas"]})
            es = self.esemenyek(ws, r["futas"])
        self.assertEqual(es[-1]["szakasz"], "megszakitva")

    def test_megszakitas_a_fut_teszt_kozben_utana_uj_futas_indulhat_nincs_arva(self):
        ir(self.v, JEGYZET, NOTE.replace("--- kimenet\n7\n", "--- kimenet\n7\n--- idokorlat\n10\n"))
        ir(self.v, CPP, "int main() { for (;;) {} }\n")
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/cpp/feladat?ut=" + quote(JEGYZET))[1]["tesztek"][0]["idokorlat_s"] == 10.0))
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            r = self.indit(ws)
            self.esemenyek(ws, r["futas"], vege=("fordit_kesz",))
            time.sleep(0.8)                                                      # a végtelen ciklus már fut
            t1 = time.monotonic()
            kod, m = self.k("POST", "/api/cpp/megszakit", {"futas": r["futas"]})
            self.assertEqual((kod, m["megszakitva"]), (200, True))
            es = self.esemenyek(ws, r["futas"], mp=15)
            self.assertLess(time.monotonic() - t1, 8)
            self.assertEqual(es[-1]["szakasz"], "megszakitva")
            self.assertEqual(self.k("GET", f"/api/cpp/futas/{r['futas']}")[1]["allapot"], "megszakitva")
            self.assertEqual(self.k("POST", "/api/cpp/megszakit", {"futas": r["futas"]})[1]["megszakitva"], False)
            ir(self.v, CPP, OSSZEG)                                              # a következő futás indulhat
            self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/vault/fajl?ut=" + quote(CPP))[1]["tartalom"] == OSSZEG))
            r2 = self.indit(ws)
            self.assertTrue(self.esemenyek(ws, r2["futas"])[-1].get("atment") is not None)
        arva = subprocess.run(["pgrep", "-f", str(self.cfg.path("tmp") / "cpp")], capture_output=True, text=True).stdout.strip()
        self.assertEqual(arva, "")

    def test_a_core_leallitasa_megszakitja_a_futast_nincs_arva_folyamat(self):
        ir(self.v, JEGYZET, NOTE.replace("--- kimenet\n7\n", "--- kimenet\n7\n--- idokorlat\n10\n"))
        ir(self.v, CPP, "int main() { for (;;) {} }\n")
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/cpp/feladat?ut=" + quote(JEGYZET))[1]["tesztek"][0]["idokorlat_s"] == 10.0))
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            r = self.indit(ws)
            self.esemenyek(ws, r["futas"], vege=("fordit_kesz",))
            time.sleep(0.8)
        self._leall()                                                            # a stdin lezárása: rendezett leállás
        t0 = time.monotonic()
        arva = "x"
        while time.monotonic() - t0 < 10 and arva:
            arva = subprocess.run(["pgrep", "-f", str(self.cfg.path("tmp") / "cpp")], capture_output=True, text=True).stdout.strip()
            time.sleep(0.2)
        self.assertEqual(arva, "", "a core leállása után futó C++ folyamat maradt")


if __name__ == "__main__":
    unittest.main()
