"""C26b: az összefoglaló végpontjai a valódi core-on, álvaulton (`core/osszefoglalas_api.py`): a kontextus-csomag útvonal nélkül, a külső
AI válaszának feldolgozása (a vaultba nem ír: kézi beillesztés, 49. döntés), az összefoglaló-jegyzet elemzése és a sodródás."""
from __future__ import annotations

import http.client
import json
import os
import threading
import unittest
import urllib.parse

from core import server, snapshot
from modulok.osszefoglalas import formatum as FM
from modulok.osszefoglalas import futtat as F
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.index_segedek import var_ra
from tests.test_core_api import _Kimenet
from tests.test_osszefoglalas_futtat import KISERO, AlGepi, AlWorker
from tests.test_osszefoglalas_lanc import JEGYZET, Q1, Q2, RP, valasz


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, RP, JEGYZET)
        gepi = AlGepi({RP: JEGYZET})
        F.futtat_jegyzet(self.cfg, RP, gepi=gepi, worker=AlWorker())          # az álgépi írás eredménye a vaultba
        for m in gepi.irasok[0]["muveletek"]:
            ir(self.v, m["ut"], m["tartalom"])
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.fejek = len(self.repo.log(20))
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

    def tearDown(self):
        self.assertEqual(len(self.repo.log(20)), self.fejek, "a végpontok a vaultba nem írnak")


class KontextusTest(Alap):
    def test_csomag_utvonal_nelkul(self):
        kod, d = self.k("POST", "/api/osszefoglalas/kontextus", {"utak": [RP], "kerdes": "Mi történt Kr. e. 49-ben?"})
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["azonositok"], d["benne"]), ({"J1": RP}, ["J1"]))
        self.assertIn("Mi történt Kr. e. 49-ben?", d["szoveg"])
        self.assertIn("Rubicont", d["szoveg"])
        self.assertNotIn("T03", d["szoveg"])                    # a mappanév (tantárgy) nem szivárog
        self.assertNotIn("Elmélet", d["szoveg"])

    def test_hibas_kerdesek(self):
        for torzs in ({}, {"utak": []}, {"utak": ["nincs-ilyen.txt"]}, {"utak": [RP, RP]}, {"utak": [RP], "max_karakter": 5},
                      {"utak": [RP], "kerdes": 5}):
            self.assertEqual(self.k("POST", "/api/osszefoglalas/kontextus", torzs)[0], 400, torzs)
        self.assertEqual(self.k("POST", "/api/osszefoglalas/kontextus", {"utak": ["nincs/ilyen.md"]})[0], 404)
        self.assertEqual(self.k("POST", "/api/osszefoglalas/kontextus", {"utak": [RP]}, titok="rossz")[0], 403)


class ValaszTest(Alap):
    def test_a_kapun_atmeno_allitasok_torzse_kezi_beillesztesre(self):
        jo = {"allitas": "Caesar katonáival átlépte a Rubicont.", "forras": "J1", "idezet": Q2}
        hamis = {"allitas": "Caesar Britanniában legyőzte a keltákat.", "forras": "J1", "idezet": Q1}
        ismeretlen = {"allitas": "Caesar átlépte a Rubicont.", "forras": "J7", "idezet": Q2}
        kod, d = self.k("POST", "/api/osszefoglalas/valasz", {"utak": [RP], "valasz": valasz(jo, hamis, ismeretlen), "cim": "Caesar"})
        self.assertEqual(kod, 200, d)
        self.assertEqual(d["allitasok"], 1)
        self.assertEqual(sorted(x["ok"] for x in d["elvetett"]), ["ismeretlen_forras", "tamogatas"])
        self.assertTrue(d["torzs"].startswith("## Állítások\n\n1. Caesar katonáival átlépte a Rubicont. [["))
        e = FM.elemez(d["jegyzet"])
        self.assertEqual((e.hibak, e.osszefoglalo.szint, e.osszefoglalo.modell), ([], "kontextus", "külső AI"))

    def test_ertelmezhetetlen_valasz_nem_kivetel(self):
        kod, d = self.k("POST", "/api/osszefoglalas/valasz", {"utak": [RP], "valasz": "Sajnos nem tudok segíteni."})
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["allitasok"], d["torzs"], d["jegyzet"]), (0, "", ""))
        self.assertEqual(d["statisztika"]["nem_ertelmezheto"], 1)

    def test_hibas_kerdesek(self):
        for torzs in ({"utak": [RP]}, {"utak": [RP], "valasz": ""}, {"utak": [RP], "valasz": "x" * 200_001},
                      {"utak": [RP], "valasz": "[]", "cim": "két\nsor"}):
            self.assertEqual(self.k("POST", "/api/osszefoglalas/valasz", torzs)[0], 400, str(torzs)[:60])


class MappaTervTest(Alap):
    def test_terv(self):
        ir(self.v, "T03 - Az ókori Róma/Elmélet/09 - Másik.md", JEGYZET)
        kod, d = self.k("GET", "/api/osszefoglalas/mappa-terv?ut=" + urllib.parse.quote("T03 - Az ókori Róma/Elmélet/"))
        self.assertEqual(kod, 200, d)
        self.assertEqual((len(d["jegyzetek"]), d["van"], len(d["keszul"]), d["tetelek"]), (2, [RP], 1, 2))
        kod, d = self.k("GET", "/api/osszefoglalas/mappa-terv?ut=" + urllib.parse.quote("T03 - Az ókori Róma/Elmélet") + "&kiegeszit=0")
        self.assertEqual((kod, d["keszul"], d["tetelek"]), (200, [], 1))
        for rossz in ("", "x.md", "ATTCHMNTS - cards"):
            self.assertEqual(self.k("GET", "/api/osszefoglalas/mappa-terv?ut=" + urllib.parse.quote(rossz))[0], 400, rossz)
        self.assertEqual(self.k("GET", "/api/osszefoglalas/mappa-terv?ut=nincs%2Filyen")[0], 404)


class JegyzetTest(Alap):
    def get(self, ut):
        return self.k("GET", "/api/osszefoglalas/jegyzet?" + urllib.parse.urlencode({"ut": ut}))

    def test_elemzes_es_sodras(self):
        kod, d = self.get(KISERO)
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["szint"], d["cim"], d["hibak"], d["sodrodott"], d["forras_ut"]),
                         ("jegyzet", "A polgárháborúk kora és Caesar", [], [], RP))
        self.assertEqual(len(d["allitasok"]), 3)
        self.assertTrue(all(x["alcel"].startswith("^m-") and not x["sodrodott"] and not x["horgony_hianyzik"] for x in d["allitasok"]))
        # a forrás azóta megváltozott: az érintett állítás elavult
        ir(self.v, RP, (self.v / RP).read_text(encoding="utf-8").replace("Mikor Caesart", "Amikor Caesart"))
        kod, d = self.get(KISERO)
        self.assertEqual((kod, d["sodrodott"]), (200, ["a2"]))
        # a forrás törlése: a forrás hiánya
        (self.v / RP).unlink()
        kod, d = self.get(KISERO)
        self.assertEqual((kod, d["forras_hianyzik"]), (200, [RP.removesuffix(".md")]))

    def test_csak_az_osszefoglalo_mappabol(self):
        self.assertEqual(self.get(RP)[0], 400)
        self.assertEqual(self.get("ATTCHMNTS - summaries/nincs.md")[0], 404)
        self.assertEqual(self.get("ATTCHMNTS - summaries/kep.png")[0], 400)


if __name__ == "__main__":
    unittest.main()
