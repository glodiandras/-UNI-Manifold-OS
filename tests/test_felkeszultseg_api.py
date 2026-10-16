"""A felkészültség HTTP-végpontjai (C28a) a valódi core-on, álvaulton és ál-naptáron: lista, részlet, hibakódok, és hogy
a lekérdezés semmit nem ír (a vault bájtra változatlan, nem jön létre adatbázis)."""
import hashlib
import json
import os
import threading
import unittest
import urllib.parse
from datetime import timedelta
from pathlib import Path

from core import naptar, server
from core.naptar_seged import Seged
from tests.felkeszultseg_segedek import DOLGOZAT_NAP, ESEMENYEK, FAJLOK, FELK, MOST, NAPTARAK, T1
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.index_segedek import var_ra
from tests.naptar_segedek import AlSeged
from tests.test_core_api import _Kimenet

DATUM = "2026-10-03"


class ApiTest(unittest.TestCase):
    naptar_van = True

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.al = AlSeged(self._t.name, {"naptarak": list(NAPTARAK), "esemenyek": [dict(e) for e in ESEMENYEK]})
        env = self.al.env()
        if not self.naptar_van:
            # A core háttér-naptárszinkronja (start_delay=0) az ál-segédből naptárat építene: „nincs naptár” esetben
            # a segéd maga hiányzik (nem létező út), így a szinkron sehol nem ír.
            env["MOS_NAPTAR_SEGED"] = str(Path(self._t.name) / "nincs-seged" / "Manifold")
        self.cfg, self.root, self.v = alg_core(self._t.name, **env)
        for rp, t in FAJLOK.items():
            ir(self.v, rp, t, "wb" if isinstance(t, bytes) else "w")
        if self.naptar_van:
            naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
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

    def k(self, method, path, body=None):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def lenyomat(self):
        ki = {}
        for d, mappak, fajlok in os.walk(self.v):
            mappak[:] = [m for m in mappak if m != ".obsidian"]
            for f in fajlok:
                p = Path(d) / f
                ki[os.path.relpath(p, self.v)] = hashlib.sha1(p.read_bytes()).hexdigest()
        # a pos.sqlite-ot a core saját naptár-szolgálata is írja (WAL-kiürítés): a végpont olvasás-tisztaságát a
        # `test_felkeszultseg_adat.CsakOlvasTest` a folyamaton belül bizonyítja (az adatbázisok bájtra változatlanok)
        ki["tanulas.sqlite"] = self.cfg.path("tanulas_db").exists()
        return ki

    def test_lista(self):
        kod, d = self.k("GET", "/api/felkeszultseg?" + urllib.parse.urlencode({"datum": DATUM}))
        self.assertEqual(kod, 200)
        self.assertEqual(d["nap"], DATUM)
        self.assertEqual(len(d["dolgozatok"]), 1)
        x = d["dolgozatok"][0]
        self.assertEqual((x["nap"], x["napok"], x["jegyzet"], x["kotes"]["fok"], x["temak_db"]), (DOLGOZAT_NAP, 4, FELK, "biztos", 3))
        self.assertIsNone(x["szam"])
        self.assertEqual(x["szint"], "nincs_adat")
        self.assertIn("kartya", d["adatok"])

    def test_reszlet(self):
        azon = self.k("GET", "/api/felkeszultseg?datum=" + DATUM)[1]["dolgozatok"][0]["azon"]
        kod, d = self.k("GET", "/api/felkeszultseg/dolgozat?" + urllib.parse.urlencode({"datum": DATUM, "azon": azon}))
        self.assertEqual(kod, 200)
        self.assertEqual(len(d["temak"]), 3)
        self.assertEqual(len(d["terv"]["napok"]), 4)
        self.assertIn("leiras", d["keplet"])
        self.assertEqual(d["forrasok"][0]["oldalak"], "18–19, 28")

    def test_hibakodok(self):
        self.assertEqual(self.k("GET", "/api/felkeszultseg?datum=holnap")[0], 400)
        self.assertEqual(self.k("GET", "/api/felkeszultseg/dolgozat?datum=" + DATUM)[0], 400)          # azon nélkül
        self.assertEqual(self.k("GET", "/api/felkeszultseg/dolgozat?datum=" + DATUM + "&azon=nincs")[0], 404)

    def test_lekerdezes_nem_ir(self):
        elotte = self.lenyomat()
        azon = self.k("GET", "/api/felkeszultseg?datum=" + DATUM)[1]["dolgozatok"][0]["azon"]
        self.k("GET", "/api/felkeszultseg/dolgozat?" + urllib.parse.urlencode({"datum": DATUM, "azon": azon}))
        self.assertEqual(self.lenyomat(), elotte)


class NincsNaptarApiTest(ApiTest):
    naptar_van = False

    def test_lista(self):
        kod, d = self.k("GET", "/api/felkeszultseg?datum=" + DATUM)
        self.assertEqual(kod, 200)
        self.assertEqual(d["dolgozatok"], [])
        self.assertIn("calendar", d["hiba"])

    def test_reszlet(self):
        self.assertEqual(self.k("GET", "/api/felkeszultseg/dolgozat?datum=" + DATUM + "&azon=x")[0], 404)

    def test_hibakodok(self):
        self.assertEqual(self.k("GET", "/api/felkeszultseg?datum=holnap")[0], 400)

    def test_lekerdezes_nem_ir(self):
        elotte = self.lenyomat()
        self.k("GET", "/api/felkeszultseg?datum=" + DATUM)
        self.assertEqual(self.lenyomat(), elotte)
        self.assertFalse((self.cfg.path("szemelyes") / "pos.sqlite").exists())        # nem hozott létre adatbázist


if __name__ == "__main__":
    unittest.main()
