"""A vault-index HTTP-végpontjai és WS-eseménye (C06), a core-ral együtt, álvaulton.

Kész-feltétel (álvaulton is): egy külső módosítás 200 ms alatt látszik az API-ban; a saját mentés a
válasz pillanatában.
"""
import json
import os
import statistics
import threading
import time
import unittest
import urllib.parse

from core import server
from tests import csak_darwin
from tests.helpers import API_TITOK, tmpdir
from tests.index_segedek import alvault, var_ra
from tests.test_core_api import _Kimenet, ws_connect, ws_csatlakozik


class IndexApiAlap(unittest.TestCase):
    """A core egy szálon, álvaulton (a `perf_index.py` és az `IndexApiTest` közös alapja)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name)
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)
        self.assertTrue(var_ra(lambda: self.get("/api/vault/index")[1].get("kesz"), 30))

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def k(self, method, path, body=None):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def get(self, vegpont, **q):
        return self.k("GET", vegpont + ("?" + urllib.parse.urlencode(q) if q else ""))



class IndexApiTest(IndexApiAlap):
    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_lassu_regex_400_es_a_core_el(self):
        """H5 (audit): a katasztrofális regex 400-at ad magyar üzenettel, közben a `/health` válaszol."""
        import time
        (self.v / "Lassú.md").write_text("a" * 60 + "!\n", encoding="utf-8")
        self.assertTrue(var_ra(lambda: self.get("/api/vault/kereses", q="file:Lassú")[1].get("osszes") == 1, 10))
        eredmeny = {}
        t = threading.Thread(target=lambda: eredmeny.update(r=self.get("/api/vault/kereses", q="/(a|aa)+$/")))
        t.start()
        time.sleep(0.3)
        t0 = time.monotonic()
        self.assertEqual(self.get("/health")[0], 200)
        self.assertLess(time.monotonic() - t0, 1)
        t.join(10)
        kod, d = eredmeny["r"]
        self.assertEqual(kod, 400)
        self.assertIn("túl sokáig", d["hiba"])

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_vegpontok(self):
        kod, a = self.get("/api/vault/index")
        self.assertEqual((kod, a["figyelo"]), (200, "fsevents"))
        kod, fa = self.get("/api/vault/fa")
        self.assertIn("Cél.md", [f["ut"] for f in fa["fajlok"]])
        kod, j = self.get("/api/vault/jegyzet", ut="Cél.md")
        self.assertEqual((kod, j["tulajdonsagok"][0]["kulcs"]), (200, "Tags"))
        self.assertEqual(self.get("/api/vault/jegyzet", ut="nincs.md")[0], 404)
        self.assertEqual(self.get("/api/vault/jegyzet")[0], 400)
        kod, b = self.get("/api/vault/visszahivatkozasok", ut="Cél.md")
        self.assertIn("Tabla.md", [f["ut"] for f in b["forrasok"]])
        kod, e = self.get("/api/vault/emlitesek", ut="Cél X.md")
        self.assertEqual(kod, 200)
        kod, k = self.get("/api/vault/kereses", q="tag:#math", limit=5)
        self.assertEqual([t["ut"] for t in k["talalatok"]], ["Cél.md"])
        self.assertEqual(self.get("/api/vault/kereses", q="(")[0], 400)
        self.assertEqual(self.get("/api/vault/kereses", q="tag:#math", kornyezet=6)[0], 400)      # C11a: 0–5
        self.assertEqual(self.get("/api/vault/kereses", q="tag:#math", kornyezet=1)[0], 200)
        kod, g = self.get("/api/vault/graf")
        self.assertIn(["X01 - Napló/00 - Index.md", "X01 - Napló/2026-09-12.md"], g["elek"])
        self.assertIn("nincs ilyen", g["feloldatlan"])
        self.assertEqual(self.get("/api/vault/nincs")[0], 404)

    def _var_index(self, ut, feltetel):
        self.assertTrue(var_ra(lambda: feltetel(self.get("/api/vault/jegyzet", ut=ut)), 5, 0.01))

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_cimkek_fa_szamlalokkal(self):
        """C11b: a címkefa minden címkét és szülőt ad; `db` a pontos, `ossz` a gyerekekkel együtt (egy jegyzet egyszer)."""
        (self.v / "C1.md").write_text("---\nTags:\n  - Fizika/Mechanika/Newton\n  - Fizika/Mechanika\n---\n#Fizika/Optika szöveg\n")
        (self.v / "C2.md").write_text("---\nTags: Fizika/Mechanika\n---\n")
        (self.v / "C3.md").write_text("#Matek\n")
        for ut in ("C1.md", "C2.md", "C3.md"):
            self._var_index(ut, lambda r: r[0] == 200)
        self.assertTrue(var_ra(lambda: any(c["kis"] == "matek" for c in self.get("/api/vault/cimkek")[1]["cimkek"]), 5, 0.01))
        kod, d = self.get("/api/vault/cimkek")
        self.assertEqual(kod, 200)
        t = {c["kis"]: (c["db"], c["ossz"]) for c in d["cimkek"]}
        self.assertEqual(t["fizika"], (0, 2))                       # C1, C2: egyik jegyzet sem viseli pontosan
        self.assertEqual(t["fizika/mechanika"], (2, 2))
        self.assertEqual(t["fizika/mechanika/newton"], (1, 1))
        self.assertEqual(t["fizika/optika"], (1, 1))
        self.assertEqual(t["matek"], (1, 1))
        self.assertEqual(t["math/algebra"], (1, 1))                 # az alapvault Cél.md-je
        self.assertEqual({c["cimke"] for c in d["cimkek"] if c["kis"] == "fizika/mechanika/newton"},
                         {"Fizika/Mechanika/Newton"})

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_tulajdonsag_javaslatok(self):
        """Tulajdonság-javaslatok: a vaultban használt kulcsok és értékek jegyzetszámmal (kis-nagybetűtől függetlenül, a lista
        eleme külön), a `Tags` a címke-indexből, az értékkészlet a sémából."""
        (self.v / "P1.md").write_text("---\nTags:\n  - Physics\nSzerző: Arany János\nStatus: Review\n---\n#Physics szöveg\n")
        (self.v / "P2.md").write_text("---\nszerző: Arany János\nMűfaj:\n  - ballada\n  - líra\nKész: true\n---\n")
        (self.v / "P3.md").write_text("---\nSzerző: Petőfi Sándor\n---\n")
        for ut in ("P1.md", "P2.md", "P3.md"):
            self._var_index(ut, lambda r: r[0] == 200)
        kod, d = self.get("/api/vault/tulajdonsagok/ertekek", ut="F01 - F/J.md", kulcs="Szerző")
        self.assertEqual(kod, 200)
        self.assertEqual([(x["ertek"], x["db"]) for x in d["ertekek"]], [("Arany János", 2), ("Petőfi Sándor", 1)])
        d = self.get("/api/vault/tulajdonsagok/ertekek", ut="F01 - F/J.md", kulcs="Műfaj")[1]
        self.assertEqual(sorted(x["ertek"] for x in d["ertekek"]), ["ballada", "líra"])
        self.assertEqual(self.get("/api/vault/tulajdonsagok/ertekek", ut="F01 - F/J.md", kulcs="Kész")[1]["ertekek"], [])
        d = self.get("/api/vault/tulajdonsagok/ertekek", ut="F01 - F/J.md", kulcs="Tags")[1]
        physics = [x for x in d["ertekek"] if x["ertek"] == "Physics"][0]
        self.assertEqual((physics["db"], physics["sema"], d["ertekkeszlet"]), (1, True, True))
        d = self.get("/api/vault/tulajdonsagok/ertekek", ut="F01 - F/J.md", kulcs="Status")[1]
        self.assertEqual([x["ertek"] for x in d["ertekek"]][0], "Review")       # a használt elöl
        kod, d = self.get("/api/vault/tulajdonsagok/kulcsok", ut="F01 - F/J.md")
        k = {x["kulcs"]: x for x in d["kulcsok"]}
        self.assertEqual((kod, k["Szerző"]["db"], k["Szerző"]["sema"], k["Tags"]["sema"]), (200, 3, False, True))
        self.assertNotIn("szerző", k)                                          # az írásmódok összevonva
        self.assertEqual(self.get("/api/vault/tulajdonsagok/ertekek", ut="A.md")[0], 400)

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_ikonok(self):
        (self.v / "I1.md").write_text("---\nicon: 📘\ncover: \"[[kep.png]]\"\n---\n")
        (self.v / "I2.md").write_text("---\nCover: kep.png\nicon: https://x.hu/i.png\n---\n")
        self.assertTrue(var_ra(lambda: len(self.get("/api/vault/ikonok")[1]["ikonok"]) == 2, 5, 0.01))
        d = self.get("/api/vault/ikonok")[1]["ikonok"]
        self.assertEqual(d["I1.md"]["icon"], {"ertek": "📘", "ut": None})
        self.assertEqual(d["I1.md"]["cover"], {"ertek": "[[kep.png]]", "ut": "kep.png"})
        self.assertEqual(d["I2.md"]["cover"]["ut"], "kep.png")
        self.assertIsNone(d["I2.md"]["icon"]["ut"])                  # külső URL nem oldódik fel

    def test_tulajdonsag_vegpontok(self):
        kod, s = self.get("/api/vault/sema", ut="ATTCHMNTS - quizes/K.md")
        self.assertEqual((kod, s["osztaly"]["nev"], s["mezosorrend"][0]), (200, "kviz", "Tags"))
        fm = "---\nTags:\n  - AI\n---\n"
        kod, e = self.k("POST", "/api/vault/tulajdonsagok/elemez", {"ut": "A.md", "fm": fm})
        self.assertEqual((kod, e["tulajdonsagok"][0]["kulcs"]), (200, "Tags"))
        kod, m = self.k("POST", "/api/vault/tulajdonsagok/modosit",
                        {"ut": "A.md", "fm": fm, "muvelet": "beallit", "kulcs": "icon", "ertek": "📘"})
        self.assertEqual((kod, m["ok"], m["megerositheto"]), (200, False, True))
        kod, m = self.k("POST", "/api/vault/tulajdonsagok/modosit",
                        {"ut": "A.md", "fm": fm, "muvelet": "beallit", "kulcs": "icon", "ertek": "📘", "megerosit": True})
        self.assertEqual((kod, m["ok"]), (200, True))
        self.assertEqual(self.k("POST", "/api/vault/tulajdonsagok/modosit", {"ut": "A.md", "fm": fm, "muvelet": "x"})[0], 400)
        self.assertEqual(self.k("POST", "/api/vault/tulajdonsagok/elemez", {"ut": "A.md", "fm": "nem fm"})[0], 400)
        kod, m = self.k("POST", "/api/vault/tulajdonsagok/modosit",
                        {"ut": "A.md", "fm": fm, "muvelet": "beallit", "kulcs": "Status", "ertek": "Review", "forras": "gep"})
        self.assertEqual((kod, m["ok"], m["problemak"][0]["kod"]), (200, False, "status_gep"))

    def test_megerosit_csak_igaz_logikai_ertek(self):
        """T128 (C29.8): a `megerosit` szigorúan `true`; a `"false"` szöveg (ma `bool()`-lal igaz) és minden más típus 400."""
        fm = "---\nTags:\n  - AI\n---\n"
        torzs = {"ut": "A.md", "fm": fm, "muvelet": "beallit", "kulcs": "icon", "ertek": "📘"}
        for rossz in ("false", "true", 1, 0, [], {}, "igen"):
            kod, m = self.k("POST", "/api/vault/tulajdonsagok/modosit", {**torzs, "megerosit": rossz})
            self.assertEqual(kod, 400, repr(rossz))
        for jo in (False, None):                                          # hamis vagy hiányzó: nincs megerősítés
            kod, m = self.k("POST", "/api/vault/tulajdonsagok/modosit", {**torzs, "megerosit": jo})
            self.assertEqual((kod, m["ok"], m["megerositheto"]), (200, False, True))
        kod, m = self.k("POST", "/api/vault/tulajdonsagok/modosit", {**torzs, "megerosit": True})
        self.assertEqual((kod, m["ok"]), (200, True))

    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_kulso_modositas_latszik(self):
        """Funkcionálisan: egy külső módosítás látszik az API-ban (a keresés megtalálja). A késleltetés számszerű kapuja
        (medián, p90, max) a perf-készletben van (`tests/perf_index.py`, `bin/mos perf`): falióra-kapu a funkcionális
        készletben terhelés alatt hamisan bukna (T008)."""
        for i in range(3):
            szo = f"zebra{i}kulso"
            (self.v / "Cél X.md").write_text(f"# Cél X\n{szo}\n")
            self.assertTrue(var_ra(lambda: self.get("/api/vault/kereses", q=szo)[1].get("osszes") == 1, 10, 0.005), szo)

    def test_sajat_mentes_azonnal_latszik_es_nem_kulso(self):
        d = self.get("/api/vault/fajl", ut="Cél X.md")[1]
        kod, _ = self.k("PUT", "/api/vault/fajl", {"ut": "Cél X.md", "tartalom": "sajatmentes\n", "alap": d["hash"]})
        self.assertEqual(kod, 200)
        self.assertEqual(self.get("/api/vault/kereses", q="sajatmentes")[1]["osszes"], 1)

    @unittest.skipIf(ws_connect is None, "nincs websockets-kliens")
    @csak_darwin("FSEvents-figyelő (Linuxon a figyelő nem indul: `CFStringCreateWithCString`)")
    def test_ws_vault_valtozas(self):
        with ws_csatlakozik(self.port) as ws:
            self.assertEqual(json.loads(ws.recv(5))["tipus"], "hello")
            (self.v / "Uj.md").write_text("[[Cél]]")
            t0 = time.time()
            while time.time() - t0 < 5:
                e = json.loads(ws.recv(5))
                if e["tipus"] == "vault_valtozas":
                    break
            self.assertEqual((e["utak"], e["kulso"], e["torolt"]), (["Uj.md"], ["Uj.md"], []))


if __name__ == "__main__":
    unittest.main()
