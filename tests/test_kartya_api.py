"""C23b: a kártya-végpontok a valódi core-on (álvault, saját pillanatkép-tároló, ál-var): esedékesek, pakli, értékelés és
visszavonás, a tracker-esemény alakja, a „Ma” oldal szakasza, az `.apkg` export és az éles import (kísérőjegyzet gépi írással,
utána az állapot), a lépés-token kizárása."""
from __future__ import annotations

import http.client
import json
import os
import threading
import unittest
import urllib.parse
import zipfile
from pathlib import Path

from core import server, snapshot, tanulas_db
from modulok.kartya import formatum as F
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.index_segedek import var_ra
from tests.test_core_api import _Kimenet
from tests.test_kartya_apkg import _idegen_gyujtemeny

FORRAS = "M10 - Sorozatok/Mértani sorozat.md"
KISERO = "ATTCHMNTS - cards/Mértani sorozat — kártyák.md"


def kisero_szoveg() -> str:
    return F.ir([F.Kartya("Mi állandó a mértani sorozatban?", "a szomszédos tagok hányadosa", "c-0000aaaa", "Mértani sorozat#^m-1a2b"),
                 F.Kartya("Mennyi a 2, 6, 18 hányadosa?", "3", "c-0000bbbb", "Mértani sorozat#^m-1a2b")],
                ["Mértani sorozat"], modell="qwen35_4b", keszult="2026-10-08")


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, FORRAS, "---\nTags: Mathematics\n---\n# Mértani sorozat\n\nA hányados állandó. ^m-1a2b\n")
        ir(self.v, KISERO, kisero_szoveg())
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/vault/index")[1].get("kesz"), 30))

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def k(self, method, path, body=None, titok=API_TITOK):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": titok, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")


class IsmetlesTest(Alap):
    def test_esedekes_pakli_valasz_visszavon(self):
        kod, d = self.k("GET", "/api/kartya/esedekes")
        self.assertEqual(kod, 200, d)
        self.assertEqual([x["azon"] for x in d["kartyak"]], ["c-0000aaaa", "c-0000bbbb"])
        self.assertEqual((d["uj"], d["esedekes"], d["allapot"]), (2, 0, "kesz"))
        self.assertEqual(d["kartyak"][0]["kerdes"], "Mi állandó a mértani sorozatban?")   # a szöveg a vaultból
        self.assertEqual(set(d["kartyak"][0]["elorejelzes"]), {"1", "2", "3", "4"})
        kod, p = self.k("GET", "/api/kartya/jegyzet?" + urllib.parse.urlencode({"ut": KISERO}))
        self.assertEqual(kod, 200, p)
        self.assertEqual((p["osszes"], p["uj"]), (2, 2))
        kod, v = self.k("POST", "/api/kartya/valasz", {"azon": "c-0000aaaa", "jegy": 3, "ms": 4200})
        self.assertEqual(kod, 200, v)
        self.assertEqual(v["tracker"], {"ut": FORRAS, "adat": {"jegy": 3, "kartya_id": "c-0000aaaa", "ms": 4200}})
        self.assertEqual(v["allapot"]["allapot"], 1)                                      # tanulás
        kod, v = self.k("POST", "/api/kartya/visszavon", {"azon": "c-0000aaaa"})
        self.assertEqual((kod, v["visszavonva"], v["allapot"]["allapot"]), (200, True, 0))
        kod, v = self.k("POST", "/api/kartya/visszavon", {"azon": "c-0000aaaa"})
        self.assertFalse(v["visszavonva"])
        kod, ma = self.k("GET", "/api/ma")
        self.assertEqual(ma["kartyak"]["allapot"], "kesz")
        self.assertEqual(ma["kartyak"]["uj"], 2)

    def test_ervenytelen_kerelmek(self):
        self.assertEqual(self.k("POST", "/api/kartya/valasz", {"azon": "c-0000aaaa", "jegy": 5})[0], 400)
        self.assertEqual(self.k("POST", "/api/kartya/valasz", {"azon": "x", "jegy": 3})[0], 400)
        self.assertEqual(self.k("POST", "/api/kartya/valasz", {"azon": "c-0000ffff", "jegy": 3})[0], 400)
        self.assertEqual(self.k("GET", "/api/kartya/jegyzet?ut=" + urllib.parse.quote(FORRAS))[0], 400)

    def test_torolt_kartya_nem_esedekes(self):
        self.k("GET", "/api/kartya/esedekes")                                              # szinkron
        ir(self.v, KISERO, F.ir([F.Kartya("Mennyi a 2, 6, 18 hányadosa?", "3", "c-0000bbbb")], ["Mértani sorozat"]))
        self.assertTrue(var_ra(lambda: [x["azon"] for x in self.k("GET", "/api/kartya/esedekes")[1]["kartyak"]] == ["c-0000bbbb"], 20))

        def sirkovek():
            with tanulas_db.olvaso(self.cfg) as c:
                return c.execute("SELECT COUNT(*) FROM sirko").fetchone()[0]
        self.assertTrue(var_ra(lambda: sirkovek() == 1, 60))                              # a szinkron a vault változására fut


class ApkgTest(Alap):
    def test_export_es_import_proba(self):
        cel = Path(self._t.name) / "ki.apkg"
        kod, d = self.k("POST", "/api/kartya/export", {"cel": str(cel)})
        self.assertEqual((kod, d["kartyak"]), (200, 2), d)
        self.assertTrue(cel.is_file())
        kod, d = self.k("POST", "/api/kartya/import", {"fajl": str(cel), "proba": True})
        self.assertEqual(kod, 200, d)
        self.assertEqual(d["kisero"], [])                                                  # a saját kártyák már a vaultban élnek
        self.assertEqual(self.k("POST", "/api/kartya/export", {"cel": str(self.v / "x.apkg")})[0], 400)   # a vaultba nem

    def test_eles_import_kisero_utana_allapot(self):
        gy = Path(self._t.name) / "gy.anki21"
        _idegen_gyujtemeny(gy)
        csomag = Path(self._t.name) / "idegen.apkg"
        with zipfile.ZipFile(csomag, "w") as z:
            z.write(gy, "collection.anki21")
        kod, d = self.k("POST", "/api/kartya/import", {"fajl": str(csomag), "proba": False})
        self.assertEqual(kod, 200, d)
        self.assertEqual(d["kisero"], [{"pakli": "1848", "kartyak": 4}])
        ut = "ATTCHMNTS - cards/1848 — kártyák.md"
        self.assertEqual(d["irasok"][0]["ut"], ut)
        szoveg = (self.v / ut).read_text(encoding="utf-8")
        e = F.elemez(szoveg)
        self.assertEqual(len(F.ervenyes(e)), 4)
        self.assertEqual(e.modell, "")
        c = self.repo.log(1)[0]
        self.assertEqual(c.trailers.get("Mos-Forras"), "mos-kartya")
        with tanulas_db.olvaso(self.cfg) as db:
            sorok = {r["kerdes"]: dict(r) for r in db.execute("SELECT * FROM kartya WHERE eredet = 'apkg'")}
        self.assertEqual(sorok["Mikor volt **Mohács**?"]["allapot"], 2)                     # az FSRS-állapot átjött
        # újraimport: nem duplikál
        kod, d2 = self.k("POST", "/api/kartya/import", {"fajl": str(csomag), "proba": False})
        self.assertEqual((kod, d2["kisero"]), (200, []), d2)


class LepesTokenTest(Alap):
    def test_lepes_nem_ertekelhet(self):
        from core import lepes_kapu
        for ut in ("/api/kartya/valasz", "/api/kartya/visszavon", "/api/kartya/export", "/api/kartya/import"):
            self.assertFalse(lepes_kapu.engedelyezett("POST", ut))


if __name__ == "__main__":
    unittest.main()
