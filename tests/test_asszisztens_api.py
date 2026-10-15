"""Az Asszisztens végpontjai a futó core-on (C30a): a gyorsítótárazott higiénia-összegzés, a linkeletlen említések, a heti
szokásminta, a döntések és a statisztika (egy gombos törlés), a „Ma” oldal szakasza és a kapcsolók. Álgyökéren."""
import json
import os
import sqlite3
import time
import unittest
from datetime import date, datetime, timedelta

from core import szemelyes_db, tracker
from tests.index_segedek import var_ra
from tests.test_core_api import _Szerver

KERET = "---\nTags:\n  - Mathematics\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
FAJLOK = {
    "A.md": KERET + "[[Nincs ilyen]] és [[B]]\n",
    "B.md": KERET + "[[A]]\n",
    "Függvények.md": KERET + "# Függvények\n[[A]]\n",
}


class Alap(_Szerver):
    def elokeszit(self):
        for ut, szoveg in FAJLOK.items():
            (self.v / ut).write_text(szoveg, encoding="utf-8")
        a = self.cfg.data.setdefault("asszisztens", {})
        a["higienia_tick_mp"] = 0.05
        a["higienia_min_koz_mp"] = 0
        self.cfg.data.setdefault("aktivitas", {})["rendszer_tetlenseg"] = False       # a teszt gépe aktív: csak a fájl-jel számít
        self.szokas_adat()

    def szokas_adat(self, het: int = 6):
        """`het` korábbi azonos hétnap 30 perc matekkal (a mai napra illő minta, bármely hétnapon)."""
        ma = date.today()
        tr = tracker.Tracker(self.cfg)
        with tr._iro() as c:
            for k in range(1, het + 1):
                c.execute("INSERT INTO tr_aktiv (nap, ut, tantargy, mp) VALUES (?,?,?,?)",
                          ((ma - timedelta(days=7 * k)).isoformat(), "M01 - Matek/Függvények.md", "Mathematics", 1800))

    def get(self, ut):
        return self.k("GET", ut)

    def kesz_osszegzes(self) -> dict:
        r = {}

        def kesz():
            r.update(self.k("GET", "/api/asszisztens/higienia")[1])
            return r.get("kesz")
        self.assertTrue(var_ra(kesz, 15, 0.1))
        return r


class TeljesRiportVegpontTest(Alap):
    """A3-25: a `GET /api/higienia` `ut` nélkül a gyorsítótárból válaszol, soron belül nem számol, és a kapcsolót követi."""

    def test_ut_nelkul_a_gyorsitotarbol_nem_szamol(self):
        from unittest import mock
        from core import higienia
        self.kesz_osszegzes()
        with mock.patch.object(higienia.Higienia, "riport", side_effect=AssertionError("soron belül számolt")) as m:
            kod, r = self.k("GET", "/api/higienia")
        self.assertEqual(kod, 200)
        self.assertTrue(r["kesz"])
        self.assertGreaterEqual(r["osszesites"]["torott_link"], 1)
        m.assert_not_called()

    def test_kikapcsolt_asszisztensnel_nem_adja(self):
        self.kesz_osszegzes()
        self.assertEqual(self.k("PUT", "/api/vezerlo/kapcsolok", {"asszisztens": False})[0], 200)
        self.assertEqual(self.k("GET", "/api/higienia")[0], 409)

    def test_meg_nincs_riport_409(self):
        from core.asszisztens.szolgalat import HigieniaSzolgalat
        from core.utvonalak import HttpError
        sz = HigieniaSzolgalat(self.cfg, None, None, None, aktiv=lambda: False, kapcsolo=lambda: True)
        with self.assertRaises(HttpError) as e:
            sz.teljes_riport()
        self.assertEqual(e.exception.code, 409)

    def test_ut_szuro_tovabbra_soron_belul_megy(self):
        self.kesz_osszegzes()
        self.assertEqual(self.k("GET", "/api/higienia?ut=A.md")[0], 200)


class HigieniaApiTest(Alap):
    def test_osszegzes_a_hattervegzo_riportbol(self):
        o = self.kesz_osszegzes()
        self.assertTrue(o["kapcsolo"])
        self.assertGreaterEqual(o["osszesites"]["torott_link"], 1)
        self.assertEqual((o["uj"], o["uj_tetelek"]), (0, []))                      # az első riport csendes alapvonal
        self.assertTrue(o["alapvonal"])

    def test_latva_es_ma_szakasz(self):
        self.kesz_osszegzes()
        kod, r = self.k("POST", "/api/asszisztens/higienia/latva", {})
        self.assertEqual((kod, r["uj"]), (200, 0))
        ma = self.k("GET", "/api/ma")[1]["asszisztens"]
        self.assertEqual(set(ma), {"kapcsolo", "higienia"})
        self.assertEqual(set(ma["higienia"]), {"kesz", "ossz", "uj"})
        self.assertTrue(ma["higienia"]["kesz"])

    def test_a_ma_nem_ir_allapotfajlt(self):
        self.kesz_osszegzes()
        allapot = self.cfg.path("state") / "asszisztens.json"
        elotte = allapot.read_bytes() if allapot.exists() else None
        self.k("GET", "/api/ma")
        self.k("GET", "/api/asszisztens/higienia")
        self.assertEqual(allapot.read_bytes() if allapot.exists() else None, elotte)

    def test_kapcsolo_ki_nincs_szamitas_es_jelzi(self):
        self.assertEqual(self.k("PUT", "/api/vezerlo/kapcsolok", {"asszisztens": False})[0], 200)
        time.sleep(0.4)
        o = self.k("GET", "/api/asszisztens/higienia")[1]
        self.assertFalse(o["kapcsolo"])
        ma = self.k("GET", "/api/ma")[1]["asszisztens"]
        self.assertFalse(ma["kapcsolo"])


class EmlitesApiTest(Alap):
    def kesz(self):
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/vault/index")[1].get("kesz"), 15, 0.1))

    def test_emlitesek_a_kapott_szovegben(self):
        self.kesz()
        kod, r = self.k("POST", "/api/asszisztens/emlitesek", {"ut": "B.md", "szoveg": "Ma a függvények: [[A]] és `függvények`"})
        self.assertEqual(kod, 200)
        self.assertEqual([(x["szoveg"], x["cel"]) for x in r["emlitesek"]], [("függvények", "Függvények.md")])

    def test_hibas_torzs(self):
        self.kesz()
        self.assertEqual(self.k("POST", "/api/asszisztens/emlitesek", {"ut": "B.md"})[0], 400)
        self.assertEqual(self.k("POST", "/api/asszisztens/emlitesek", [1])[0], 400)

    def test_kapcsolo_ki_ures(self):
        self.kesz()
        self.k("PUT", "/api/vezerlo/kapcsolok", {"asszisztens": False})
        kod, r = self.k("POST", "/api/asszisztens/emlitesek", {"ut": "B.md", "szoveg": "függvények"})
        self.assertEqual((kod, r["emlitesek"], r["kapcsolo"]), (200, [], False))


class SzokasEsStatisztikaApiTest(Alap):
    def test_heti_javaslat_es_dontes(self):
        kod, r = self.k("GET", "/api/asszisztens/szokas")
        self.assertEqual(kod, 200)
        j = r["javaslat"]
        self.assertEqual((j["tantargy"], j["allapot"]), ("Mathematics", "uj"))
        self.assertEqual(self.k("GET", "/api/asszisztens/szokas")[1]["javaslat"]["azon"], j["azon"])
        kod, d = self.k("POST", "/api/asszisztens/szokas/dontes", {"azon": j["azon"], "dontes": "elfogad"})
        self.assertEqual((kod, d["ok"]), (200, True))
        self.assertIsNone(self.k("GET", "/api/asszisztens/szokas")[1]["javaslat"])
        self.assertEqual(self.k("POST", "/api/asszisztens/szokas/dontes", {"azon": j["azon"], "dontes": "elfogad"})[0], 409)
        self.assertEqual(self.k("POST", "/api/asszisztens/szokas/dontes", {"azon": "szokas:x", "dontes": "elfogad"})[0], 404)
        self.assertEqual(self.k("POST", "/api/asszisztens/szokas/dontes", {"azon": j["azon"], "dontes": "talan"})[0], 400)
        s = self.k("GET", "/api/asszisztens/statisztika")[1]
        self.assertEqual(s["fajtak"]["szokas"]["elfogad"], 1)

    def test_dontes_statisztika_torles(self):
        kod, r = self.k("POST", "/api/asszisztens/dontes", {"fajta": "emlites", "dontes": "elfogad"})
        self.assertEqual((kod, r), (200, {"fogadva": True}))
        self.k("POST", "/api/asszisztens/dontes", {"fajta": "emlites", "dontes": "elutasit"})
        s = self.k("GET", "/api/asszisztens/statisztika")[1]
        self.assertEqual((s["fajtak"]["emlites"]["elfogad"], s["fajtak"]["emlites"]["elutasit"]), (1, 1))
        self.assertEqual(s["ablak_nap"], 30)
        kod, t = self.k("POST", "/api/asszisztens/statisztika/torles", {})
        self.assertEqual((kod, t["torolt"], t["tisztitva"]), (200, 1 + 1, True))
        s = self.k("GET", "/api/asszisztens/statisztika")[1]
        self.assertEqual(s["fajtak"]["emlites"]["db"], 0)

    def test_hibas_dontes_400(self):
        self.assertEqual(self.k("POST", "/api/asszisztens/dontes", {"fajta": "x", "dontes": "elfogad"})[0], 400)
        self.assertEqual(self.k("POST", "/api/asszisztens/dontes", {"fajta": "emlites", "dontes": "x"})[0], 400)
        self.assertEqual(self.k("POST", "/api/asszisztens/dontes", [1])[0], 400)

    def test_kapcsolok_alatt_nem_ir(self):
        self.k("PUT", "/api/vezerlo/kapcsolok", {"tracker": False})
        r = self.k("POST", "/api/asszisztens/dontes", {"fajta": "emlites", "dontes": "elfogad"})[1]
        self.assertEqual((r["fogadva"], r["ok"]), (False, "tracker_ki"))
        self.k("PUT", "/api/vezerlo/kapcsolok", {"tracker": True, "asszisztens": False})
        r = self.k("POST", "/api/asszisztens/dontes", {"fajta": "emlites", "dontes": "elfogad"})[1]
        self.assertEqual((r["fogadva"], r["ok"]), (False, "asszisztens_ki"))
        self.assertIsNone(self.k("GET", "/api/asszisztens/szokas")[1]["javaslat"])

    def test_fejlec_nelkul_403(self):
        for m, u in (("GET", "/api/asszisztens/statisztika"), ("POST", "/api/asszisztens/dontes"),
                     ("POST", "/api/asszisztens/emlitesek"), ("GET", "/api/asszisztens/tanult"),
                     ("POST", "/api/asszisztens/kartya"), ("POST", "/api/asszisztens/tanul")):
            self.assertEqual(self.k(m, u, {} if m == "POST" else None, {"X-Manifold": "0"})[0], 403)


class TanuloMagApiTest(Alap):
    """J1/J3 a futó core-on: a linkjavaslat döntése a hangolásba is megy, és a sok elutasítás a linkjavaslat küszöbét elnémítja;
    a tanult tételek listája és soronkénti törlése; a kártya és a tanítás kikapcsolt Asszisztensnél nem ír."""

    def test_linkjavaslat_ugyanazzal_a_hangolassal(self):
        for _ in range(5):
            self.k("POST", "/api/asszisztens/dontes", {"fajta": "emlites", "dontes": "elutasit"})
        s = self.k("GET", "/api/asszisztens/statisztika")[1]
        self.assertEqual(s["fajtak"]["emlites"]["kuszob"]["szint"], "nema")
        self.assertIsNone(s["fajtak"]["emlites"]["hasonlosag_kuszob"])
        t = self.k("GET", "/api/asszisztens/tanult")[1]
        self.assertEqual([(h["kulcs"], h["szint"]) for h in t["hangolas"]], [("link|szoveg", "nema")])
        kod, t = self.k("POST", "/api/asszisztens/tanult/torles", {"fajta": "hangolas", "kulcs": "link|szoveg"})
        self.assertEqual((kod, t["hangolas"]), (200, []))
        self.assertEqual(self.k("GET", "/api/asszisztens/statisztika")[1]["fajtak"]["emlites"]["kuszob"]["szint"], "alap")
        self.assertEqual(self.k("POST", "/api/asszisztens/tanult/torles", {"fajta": "hangolas", "kulcs": "link|szoveg"})[0], 404)
        self.assertEqual(self.k("POST", "/api/asszisztens/tanult/torles", {"fajta": "x", "kulcs": "y"})[0], 400)

    def test_tanul_kartya_es_kikapcsolas(self):
        for _ in range(3):
            self.assertTrue(self.k("POST", "/api/asszisztens/tanul", {"muvelet": "cimke", "ut": "B.md", "ertek": "Analízis"})[1]["fogadva"])
        kod, r = self.k("POST", "/api/asszisztens/kartya", {"ut": "A.md", "szoveg": KERET + "szöveg\n", "alkalom": "szunet"})
        self.assertEqual(kod, 200)
        self.assertEqual(r["javaslat"]["muvelet"], {"fajta": "cimke", "ertek": "Analízis"})
        j = r["javaslat"]
        kod, d = self.k("POST", "/api/asszisztens/kartya/dontes", {"azon": j["azon"], "tipus": j["tipus"], "helyzet": j["helyzet"],
                                                                  "dontes": "elutasit", "cim": j["cim"]})
        self.assertEqual((kod, d["fogadva"]), (200, True))
        t = self.k("GET", "/api/asszisztens/tanult")[1]
        self.assertEqual([m["ertek"] for m in t["muveletek"]], ["Analízis"])
        self.assertEqual([e["kulcs"] for e in t["elutasitott"]], [j["azon"]])
        self.k("PUT", "/api/vezerlo/kapcsolok", {"asszisztens": False})
        r = self.k("POST", "/api/asszisztens/kartya", {"ut": "A.md", "szoveg": "x", "alkalom": "szunet"})[1]
        self.assertEqual((r["javaslat"], r["kapcsolo"]), (None, False))
        self.assertFalse(self.k("POST", "/api/asszisztens/tanul", {"muvelet": "cimke", "ut": "B.md", "ertek": "Új"})[1]["fogadva"])
        self.assertEqual(self.k("POST", "/api/asszisztens/kiegeszites", {"azon": "kiegeszites-0001", "elotte": "Megoldom a feladatot"})[1]["szoveg"], "")
        kod, t = self.k("POST", "/api/asszisztens/tanult/torles", {"fajta": "mind"})
        self.assertEqual((kod, t["muveletek"], t["elutasitott"]), (200, [], []))
        for ut in FAJLOK:
            self.assertEqual((self.v / ut).read_text(encoding="utf-8"), FAJLOK[ut])


if __name__ == "__main__":
    unittest.main()
