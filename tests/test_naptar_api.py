"""A C29 HTTP-végpontjai a valódi core-on, álvaulton és ál-segéddel: állapot, kézi és háttér-szinkron, kategória,
javaslat jóváhagyása, emlékeztető-tükör és -ütközés, a Ma oldal új szakaszai. A valódi naptárhoz a teszt nem nyúl."""
import http.client
import json
import os
import threading
import unittest
from datetime import date, datetime, timedelta

from core import server, snapshot, szemelyes_db
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.index_segedek import var_ra
from tests.naptar_segedek import AlSeged, esemeny as ev, naptar as nt
from tests.test_core_api import _Kimenet

MA = date.today()
HOLNAP3 = MA + timedelta(days=3)


def idopont(nap: date, ora: int) -> str:
    return datetime(nap.year, nap.month, nap.day, ora, 0).astimezone().isoformat(timespec="seconds")


NAPTARAK = [nt("HAT", "Deadlines & Exams"), nt("ORA", "Órarend"), nt("TAN", "Studying"), nt("X", "Valami Különös")]
ESEMENYEK = [
    ev("o1", "ORA", idopont(MA, 8), idopont(MA, 9), "Testnevelés"),
    ev("d1", "HAT", idopont(HOLNAP3, 10), idopont(HOLNAP3, 11), "Fizika témazáró"),
]
JEGYZET = f"- [ ] Házi 📅 {MA + timedelta(days=2)}\n"
UT = "Tennivalók.md"


class Alap(unittest.TestCase):
    kezdo: dict = {}            # az ál-segéd kezdő állapotának felülírása (a háttér-szinkron azonnal fut, start_delay=0)

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.al = AlSeged(self._t.name, {"naptarak": list(NAPTARAK), "esemenyek": [dict(e) for e in ESEMENYEK],
                                         **self.kezdo})
        self.cfg, self.root, self.v = alg_core(self._t.name, **self.al.env())
        ir(self.v, UT, JEGYZET)
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
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
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")


class EngedelyNelkulTest(Alap):
    # Az engedély már az indulásnál hiányzik: a core háttér-szinkronja nem versenyezhet a teszttel (különben a szinkron
    # még engedéllyel lefutna, és az adatbázis létrejönne).
    kezdo = {"esemeny": "nincs_dontes", "emlekezteto": "nincs_dontes"}

    def test_engedely_nelkul(self):
        kod, d = self.k("POST", "/api/naptar/szinkron")
        self.assertEqual((kod, d["esemeny_engedely"]), (200, "nincs_dontes"))
        ma = self.k("GET", f"/api/ma?datum={MA.isoformat()}")[1]
        self.assertEqual(ma["naptar_allapot"]["esemeny_engedely"], "nincs_dontes")
        # engedély nélkül nincs adatbázis (T007: a szinkron nem migrál és nem hoz létre fájlt): a Ma oldal ezt mondja
        self.assertIn("No calendar data is available yet", ma["naptar"]["hiba"])
        self.assertFalse(szemelyes_db.ut(self.cfg).exists())
        self.assertEqual(self.al.olvas().get("emlekeztetok"), {})
        kod, d = self.k("GET", "/api/naptar/allapot?frissit=1")
        self.assertEqual(d["emlekezteto_engedely"], "nincs_dontes")


class AllapotTest(Alap):
    def test_hatter_szinkron_magatol_lefut(self):
        # start_delay=0: a háttérszál az indulás után azonnal körözik (a segéd az ál-EventKit)
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/naptar/allapot")[1].get("utolso"), 20))
        kod, d = self.k("GET", "/api/naptar/allapot")
        self.assertEqual((kod, d["seged"], d["esemeny_engedely"], d["hiba"]), (200, True, "engedelyezve", None))
        self.assertEqual({n["nev"] for n in d["naptarak"]}, {n["nev"] for n in NAPTARAK})
        self.assertEqual(next(n for n in d["naptarak"] if n["azon"] == "X")["kategoria_forras"], "javaslat")
        self.assertIn("tanulas", {k["id"] for k in d["kategoriak"]})
        # az emlékeztető-tükör is megépült az indexből
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/emlekezteto/allapot")[1]["tukor"]["aktiv"] == 1, 20))
        self.assertEqual([r["cim"] for r in self.al.olvas()["emlekeztetok"].values()], ["Házi"])

    def test_kezi_szinkron_es_ma_oldal(self):
        kod, d = self.k("POST", "/api/naptar/szinkron")
        self.assertEqual((kod, d["esemeny_engedely"]), (200, "engedelyezve"))
        kod, ma = self.k("GET", f"/api/ma?datum={MA.isoformat()}")
        self.assertEqual(kod, 200)
        self.assertEqual([e["cim"] for e in ma["naptar"]["esemenyek"]], ["Testnevelés"])
        self.assertFalse(ma["naptar"]["regi"])                                   # élő szinkron: a kor-jelzés nem „régi”
        self.assertEqual(ma["naptar_allapot"]["esemeny_engedely"], "engedelyezve")
        self.assertEqual([x["cim"] for x in ma["dolgozatok"]["lista"]], ["Fizika témazáró"])
        self.assertEqual(ma["javaslatok"]["lista"] and ma["javaslatok"]["lista"][0]["tantargy"], "Fizika")

    def test_segedhiba_az_allapotban(self):
        self.al.modosit(lambda d: d.update(hiba_parancs="olvas", hiba_uzenet="ál-hiba"))
        d = self.k("POST", "/api/naptar/szinkron")[1]
        self.assertEqual(d["hiba"], "ál-hiba")


class DontesTest(Alap):
    def setUp(self):
        super().setUp()
        self.k("POST", "/api/naptar/szinkron")

    def test_kategoria(self):
        self.assertEqual(self.k("POST", "/api/naptar/kategoria", {"azon": "X", "kategoria": "edzes"})[0], 200)
        d = self.k("GET", "/api/naptar/allapot")[1]
        self.assertEqual(next((n["kategoria"], n["kategoria_forras"]) for n in d["naptarak"] if n["azon"] == "X"), ("edzes", "gazda"))
        self.assertEqual(self.k("POST", "/api/naptar/kategoria", {"azon": "X", "kategoria": "nincs"})[0], 400)
        self.assertEqual(self.k("POST", "/api/naptar/kategoria", {"azon": "NINCS", "kategoria": "edzes"})[0], 404)
        self.assertEqual(self.k("POST", "/api/naptar/kategoria", {"azon": 3})[0], 400)

    def test_javaslat_jovahagyas_elvetes(self):
        lista = self.k("GET", "/api/naptar/javaslatok")[1]["javaslatok"]
        self.assertTrue(lista)
        elso, masodik = lista[0]["id"], lista[1]["id"]
        self.assertEqual(self.al.olvas().get("esemeny_irasok"), None)
        kod, d = self.k("POST", f"/api/naptar/javaslat/{elso}/jovahagy")
        self.assertEqual((kod, d["allapot"]), (200, "beirva"))
        self.assertEqual(len(self.al.olvas()["esemeny_irasok"]), 1)
        self.assertEqual(self.k("POST", f"/api/naptar/javaslat/{elso}/jovahagy")[0], 409)
        self.assertEqual(self.k("POST", f"/api/naptar/javaslat/{masodik}/elvet")[1]["allapot"], "elvetett")
        self.assertEqual(self.k("POST", "/api/naptar/javaslat/9999/elvet")[0], 404)
        self.assertEqual(len(self.al.olvas()["esemeny_irasok"]), 1)               # az elvetés semmit nem ír a naptárba
        # a beírt blokk a következő olvasás után a naptárban (a jóváhagyás után a szolgáltatás frissít)
        cimek = self.k("GET", f"/api/naptar/allapot")[1]
        self.assertTrue(all(j["id"] not in (elso, masodik) for j in cimek["javaslatok"]))

    def test_emlekezteto_utkozes_lattamozasa(self):
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/emlekezteto/allapot")[1]["tukor"]["aktiv"] == 1, 20))
        self.al.modosit(lambda d: [r.update(cim="Átírt") for r in d["emlekeztetok"].values()])
        self.k("POST", "/api/naptar/szinkron")
        a = self.k("GET", "/api/emlekezteto/allapot")[1]
        self.assertEqual([u["fajta"] for u in a["utkozesek"]], ["szerkesztve"])
        kod, d = self.k("POST", "/api/emlekezteto/utkozes/latva", {})
        self.assertEqual((kod, d["db"]), (200, 1))
        self.assertIsNotNone(self.k("GET", "/api/emlekezteto/allapot")[1]["utkozesek"][0]["latva"])
        self.assertEqual(self.k("POST", "/api/emlekezteto/utkozes/latva", {"azonok": "x"})[0], 400)


if __name__ == "__main__":
    unittest.main()
