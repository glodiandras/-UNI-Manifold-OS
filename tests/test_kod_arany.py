"""C36b: a `kod` aranyhalmaz (`modulok/eval/kod/`) — a tételek, a forrásfájlok épsége, a verzió a routernek, és a pontozó álválaszokkal
(a homokozós módok a VALÓDI eszközláncon; nélküle `[indokolt]` kihagyás)."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

from core import config
from core.modell import eval as E
from core.modell import halmaz
from modulok.cpp import ai, ai_ellenorzes as AE, eszkoztar
from tests.helpers import alg_gyoker, tmpdir

VALODI = config.load()
MAPPA = VALODI.path("modulok") / "eval" / "kod"
_E = eszkoztar.Eszkoztar(VALODI)
VAN = sys.platform == "darwin" and _E.kesz() and _E.sdk_tbd_igazitva()
OK_SKIP = "[indokolt] nincs C++ eszköztár vagy sandbox-exec (bin/mos cpp telepit --igen; csak macOS)"

MAGYAR = ("A feltétel miatt az egyenlő szomszédokat is emelkedésnek veszi a ciklus, ezért a szakasz hossza nagyobb lesz a "
          "vártnál, és hibás eredményt kapunk.")

GEN_K02 = """#include <bits/stdc++.h>
int main(int argc, char** argv) {
    std::mt19937 r(atoi(argv[1]));
    long long sz[] = {0, 1, 2, 3999999999LL, 4000000000LL};
    int n = r() % 8 + 1;
    std::cout << n << "\\n";
    for (int i = 0; i < n; i++) std::cout << (r() % 2 ? sz[r() % 5] : (long long)(r() % 10)) << " ";
    std::cout << "\\n";
}
"""


def modul():
    return E.feladat_modul(VALODI, "kod")


class AranyTest(unittest.TestCase):
    def test_tetelek(self):
        m = modul()
        self.assertEqual(m.ROUTER_FELADAT, "kod")
        self.assertTrue(m.VERZIO.startswith("kod-v"))
        t = list(m.tetelek(VALODI))
        db = {}
        for x in t:
            db[x["vart"]["mod"]] = db.get(x["vart"]["mod"], 0) + 1
        self.assertEqual(db, {"hiba": 24, "tipp": 12, "megoldas": 12, "teszt": 6, "stressz": 6})
        self.assertEqual(len({x["id"] for x in t}), len(t))
        for x in t:
            p = x["keres"]["messages"][0]["content"]
            sor = x["vart"]["sor"]
            self.assertRegex(p, rf"(?m)^\s*{sor} \| ")
            if x["vart"]["mod"] in ("hiba", "tipp", "megoldas"):
                self.assertIn("MIT LÁTUNK", p)

    def test_a_forrasfajlok_az_arany_szerint(self):
        """A `feladatok/kNN/` fájljai nem változhatnak a homokozós ellenőrzés (`keszit.py --ir`) nélkül."""
        arany = json.loads((MAPPA / "arany.json").read_text(encoding="utf-8"))
        self.assertEqual(len(arany["feladatok"]), 12)
        for f in arany["feladatok"]:
            self.assertEqual(len(f["hibak"]), 3, f["id"])
            for nev, h in f["sha256"].items():
                self.assertEqual(hashlib.sha256((MAPPA / "feladatok" / f["id"] / nev).read_bytes()).hexdigest(), h,
                                 f"{f['id']}/{nev}: futtasd a keszit.py --ir-t")
            for h in f["hibak"]:
                self.assertIn(h["fajta"], ai.FAJTAK)
                self.assertIn(h["bizonyitek"]["fajta"], ("teszt", "ido", "nagy"))

    def test_a_router_latja_a_verziot(self):
        self.assertEqual(halmaz.Verziok(VALODI.path("modulok"))("kod"), modul().VERZIO)

    def test_szoveges_pontozas(self):
        m = modul()
        vart = {"mod": "hiba", "sor": 11, "fajta": "feltetel"}
        self.assertEqual(m.pont_hiba(MAGYAR + "\nHIBA: 11 feltetel", vart)[0], 1.0)
        self.assertAlmostEqual(m.pont_hiba(MAGYAR + "\nHIBA: 11 index", vart)[0], 0.7)
        self.assertAlmostEqual(m.pont_hiba(MAGYAR + "\nHIBA: 10 feltetel", vart)[0], 0.3)
        self.assertEqual(m.pont_hiba("The condition is wrong.\nHIBA: 11 feltetel", vart)[0], 0.0)
        tipp = ("1. IRÁNY: nézd meg, hogyan kezeli a ciklus az egyenlő szomszédokat.\n2. ALGORITMUS: csak a szigorúan "
                "nagyobb érték növelheti a szakaszt.\n3. HELY: a 11. sorban az összehasonlítás túl engedékeny.")
        eredeti = "        if (a[i] > a[i - 1]) cur++;"
        self.assertEqual(m.pont_tipp(tipp, vart, eredeti)[0], 1.0)
        self.assertAlmostEqual(m.pont_tipp(tipp.replace("11.", "9."), vart, eredeti)[0], 0.4)
        self.assertEqual(m.pont_tipp(tipp + "\nírd így: if (a[i] > a[i - 1]) cur++;", vart, eredeti)[0], 0.0)
        self.assertEqual(m.pont_tipp(tipp + "\n```cpp\nx\n```", vart, eredeti)[0], 0.0)
        self.assertTrue(m.formatum_ok("HIBA: 3 index", {"mod": "hiba"}))
        self.assertFalse(m.formatum_ok("semmi", {"mod": "stressz"}))


@unittest.skipUnless(VAN, OK_SKIP)
class HomokozosPontozasTest(unittest.TestCase):
    """A fordítást és futtatást kérő módok (megoldás, szélső teszt, stressz) álválaszokkal, a homokozóban."""

    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        root = alg_gyoker(cls._t.name).resolve()
        cls.cfg = config.load({"MOS_ROOT": str(root), "HOME": str(Path(cls._t.name) / "home"),
                               "MOS_LLVM": str(VALODI.path("llvm")), "MOS_SDK": str(VALODI.path("sdk")),
                               "MOS_RUNTIME": str(VALODI.path("runtime"))})

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_tokeletes_es_rossz_valaszok(self):
        m = modul()
        tetelek = {t["id"]: t for t in m.tetelek(VALODI)}
        ref = {f: (MAPPA / "feladatok" / f / "ref.cpp").read_text(encoding="utf-8") for f in ("k01", "k02")}
        lassu = {f: (MAPPA / "feladatok" / f / "lassu.cpp").read_text(encoding="utf-8") for f in ("k01", "k02")}
        meg = next(i for i in tetelek if i.startswith("k01") and i.endswith("megoldas"))
        tsz = next(i for i in tetelek if i.startswith("k01") and i.endswith("teszt"))
        st = next(i for i in tetelek if i.startswith("k02") and i.endswith("stressz"))
        k01_h = json.loads((MAPPA / "arany.json").read_text(encoding="utf-8"))["feladatok"][0]["hibak"]
        hibas_bem = next(h["bizonyitek"]["bemenet"] for h in k01_h if h["id"] == tetelek[tsz]["vart"]["hiba"])
        rekordok = [
            {"id": meg, "vart": tetelek[meg]["vart"], "valasz": "Javítottam.\n```cpp\n" + ref["k01"] + "```"},
            {"id": meg + "-rossz", "vart": tetelek[meg]["vart"], "valasz": "```cpp\nint main(){}\n```"},
            {"id": tsz, "vart": tetelek[tsz]["vart"],
             "valasz": f"```bemenet\n{hibas_bem}```\n```bemenet\n1\n5\n```\n```cpp\n{lassu['k01']}```"},
            {"id": st, "vart": tetelek[st]["vart"], "valasz": f"```cpp\n{GEN_K02}```\n```cpp\n{lassu['k02']}```"},
        ]
        with AE.Futtato(self.cfg) as f:
            ert = m.pontoz(rekordok, futtato=f)
        pont = {r["id"]: r["pont"] for r in ert["rossz"]}
        self.assertNotIn(meg, pont, ert)
        self.assertEqual(pont.get(meg + "-rossz"), 0.0)
        self.assertNotIn(tsz, pont, ert)
        self.assertNotIn(st, pont, ert)
        self.assertEqual(ert["modok"]["teszt"], 1.0)
        self.assertEqual(ert["modok"]["stressz"], 1.0)
        self.assertEqual(ert["modok"]["megoldas"], 0.5)


if __name__ == "__main__":
    unittest.main()
