"""Tanulásiblokk-javaslat (C29): a beépített forrás szabályai, a dedupe, az elvetés, a jóváhagyás — és hogy a naptárba
**csak jóváhagyásra** kerül esemény (D12). Ál-segéddel és álgyökérrel."""
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

from core import naptar, naptar_javaslat, szemelyes_db
from core.naptar_javaslat import Javaslat, Javaslatok
from core.naptar_seged import Seged
from core.utvonalak import HttpError
from tests import budapest_idozona
from tests.helpers import alg_core, tmpdir
from tests.naptar_segedek import AlSeged, esemeny as ev, naptar as nt

TZ = timezone(timedelta(hours=2))
MOST = datetime(2026, 10, 3, 12, 0, tzinfo=TZ)
NAPTARAK = [nt("HAT", "Deadlines & Exams"), nt("ORA", "Órarend"), nt("TAN", "Studying")]
ESEMENYEK = [
    ev("d1", "HAT", "2026-10-07T10:00:00+02:00", "2026-10-07T10:45:00+02:00", "Matek témazáró"),
    ev("o1", "ORA", "2026-10-06T16:00:00+02:00", "2026-10-06T17:00:00+02:00", "Edzés-szerű óra"),
    ev("o2", "ORA", "2026-10-05T10:00:00+02:00", "2026-10-05T10:45:00+02:00", "Fizika"),
]


class Alap(unittest.TestCase):
    def setUp(self, esemenyek=None, naptarak=None):
        budapest_idozona(self)
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.al = AlSeged(self._t.name, {"naptarak": list(naptarak or NAPTARAK), "esemenyek": [dict(e) for e in (esemenyek or ESEMENYEK)]})
        self.cfg, self.root, self.v = alg_core(self._t.name, **self.al.env())
        self.esemenyek = []
        self.j = Javaslatok(self.cfg, Seged(self.cfg), publish=lambda e, **k: self.esemenyek.append(e), mikor=lambda: MOST)
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)

    def irasok(self):
        return self.al.olvas().get("esemeny_irasok", [])


class GeneralasTest(Alap):
    def test_dolgozat_elotti_szabad_esti_savok(self):
        self.assertEqual(self.j.frissit(), {"uj": 3})
        lista = self.j.lista()
        self.assertEqual([x["nap"] for x in lista], ["2026-10-04", "2026-10-05", "2026-10-06"])
        self.assertEqual({x["cim"] for x in lista}, {"Tanulás: Matematika — Matek témazáró"})
        k = {x["nap"]: (x["kezd"], x["veg"]) for x in lista}
        self.assertEqual(k["2026-10-04"][0], "2026-10-04T16:00:00+02:00")
        self.assertEqual(k["2026-10-06"][0], "2026-10-06T17:00:00+02:00")      # a 16–17-es óra után: a foglalt sáv kikerülve
        self.assertEqual(lista[0]["perc"], 45)  # CX-009: közös napi keret
        self.assertIn("2026-10-07", lista[0]["indok"])
        self.assertTrue(any(e.get("tipus") == "naptar_javaslat" and e["uj"] == 3 for e in self.esemenyek))

    def test_az_idezett_javaslat_nem_a_naptarba_irodik_jovahagyas_nelkul(self):
        self.j.frissit()
        self.assertEqual(self.irasok(), [])
        self.assertEqual([e["cim"] for e in self.al.olvas()["esemenyek"]], [e["cim"] for e in ESEMENYEK])

    def test_ismetles_nem_keszit_ujat_es_az_elvetett_nem_ter_vissza(self):
        self.j.frissit()
        elso = self.j.lista()[0]
        self.assertEqual(self.j.elvet(elso["id"])["allapot"], "elvetett")
        self.assertEqual(self.j.frissit(), {"uj": 0})
        self.assertEqual(len(self.j.lista()), 2)
        with self.assertRaises(HttpError) as cm:
            self.j.elvet(elso["id"])
        self.assertEqual(cm.exception.code, 409)

    def test_ha_van_tanulasi_blokk_a_tantargyhoz_nincs_javaslat(self):
        self.al.modosit(lambda d: d["esemenyek"].append(ev("t1", "TAN", "2026-10-05T17:00:00+02:00", "2026-10-05T18:00:00+02:00", "Matek gyakorlás")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        self.assertEqual(self.j.frissit(), {"uj": 0})
        # Másik tantárgy blokkja is fogyasztja az aznapi közös keretet.
        self.al.modosit(lambda d: d["esemenyek"].__setitem__(-1, ev("t1", "TAN", "2026-10-05T17:00:00+02:00", "2026-10-05T18:00:00+02:00", "Irodalom olvasás")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        self.assertEqual(self.j.frissit()["uj"], 2)

    def test_tervbol_kiesett_visszaterhet_de_elvetett_nem(self):
        self.j.frissit()
        regi = self.j.lista(); self.j.elvet(regi[0]['id'])
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("UPDATE naptar_javaslat SET allapot='lejart', hiba='terv_valtozott' WHERE id=?", (regi[1]['id'],))
        self.assertEqual(self.j.frissit(), {'uj': 1})
        self.assertEqual({r['id'] for r in self.j.lista()}, {regi[1]['id'], regi[2]['id']})

    def test_csokkent_keret_megallitja_a_regi_jovahagyast(self):
        from core.felkeszultseg import keret
        self.j.frissit(); j = self.j.lista()[0]
        keret.ir(self.cfg, {'napi_perc': 15})
        with self.assertRaises(HttpError): self.j.jovahagy(j['id'])
        self.assertEqual(self.irasok(), [])

    def test_max_darab(self):
        self.cfg.data["javaslat"]["max_darab"] = 2
        self.assertEqual(self.j.frissit(), {"uj": 2})

    def test_kikapcsolva(self):
        self.cfg.data["javaslat"]["be"] = False
        self.assertEqual(self.j.frissit(), {"uj": 0})

    def test_a_multbeli_nyitott_lejart_lesz(self):
        self.j.frissit()
        keso = Javaslatok(self.cfg, Seged(self.cfg), mikor=lambda: datetime(2026, 10, 5, 23, 0, tzinfo=TZ))
        keso.frissit()
        self.assertEqual([x["nap"] for x in keso.lista()], ["2026-10-06"])       # a 10-04 és a 10-05 lejárt
        self.assertEqual(sum(1 for x in keso.lista(False) if x["allapot"] == "lejart"), 2)

    def test_a_mai_nap_savja_a_mostani_idohoz_igazodik(self):
        b = naptar_javaslat.beallitasok(self.cfg)
        most = datetime(2026, 10, 3, 17, 10, tzinfo=TZ)
        sav = naptar_javaslat.szabad_sav(most.date(), [], b, most)
        self.assertEqual(sav, datetime(2026, 10, 3, 18, 0, tzinfo=TZ))            # 17:40 → fel a félórás rácsra
        self.assertIsNone(naptar_javaslat.szabad_sav(most.date(), [], b, datetime(2026, 10, 3, 20, 0, tzinfo=TZ)))

    def test_regisztralt_forras_javaslatai_is_megjelennek(self):
        def forras(ctx):
            return [Javaslat(forras="ertekelo", azon="x|1", nap="2026-10-05", kezd="2026-10-05T18:00:00+02:00",
                             veg="2026-10-05T19:00:00+02:00", perc=60, cim="Tanulás: gyenge pontok", tantargy="Fizika")]
        naptar_javaslat.regisztral_forras("proba", forras)
        self.addCleanup(naptar_javaslat.FORRASOK.pop, "proba", None)
        self.j.frissit()
        self.assertIn("ertekelo", {x["forras"] for x in self.j.lista()})

    def test_a_bukott_forras_latszik_es_nem_viszi_el_a_javaslatait(self):
        """F6 (2026-10-14): a hibára futó forrás a `hiba` mezőben és egyszer a naplóban látszik; a többi forrás javasol, és a
        bukott forrás nyitott javaslatai nem járnak le „a terv változott” okkal."""
        import contextlib
        import io
        jo = {"x": True}

        def forras(ctx):
            if not jo["x"]:
                raise RuntimeError("elromlott")
            return [Javaslat(forras="proba", azon="x|1", nap="2026-10-05", kezd="2026-10-05T18:00:00+02:00",
                             veg="2026-10-05T19:00:00+02:00", perc=60, cim="Tanulás: gyenge pontok", tantargy="Fizika")]
        naptar_javaslat.regisztral_forras("proba", forras)
        self.addCleanup(naptar_javaslat.FORRASOK.pop, "proba", None)
        self.assertNotIn("hiba", self.j.frissit())
        self.assertIsNone(self.j.hiba)
        jo["x"] = False
        naplo = io.StringIO()
        with contextlib.redirect_stderr(naplo):
            r1 = self.j.frissit()
            r2 = self.j.frissit()
        self.assertIn("proba", r1["hiba"])
        self.assertIn("elromlott", self.j.hiba)
        self.assertEqual(r1["hiba"], r2["hiba"])
        self.assertEqual(naplo.getvalue().count("[naptár]"), 1)              # egyszer a naplóban
        self.assertIn("proba", {x["forras"] for x in self.j.lista()})       # a nyitott javaslata megmaradt
        self.assertIn("alap", {x["forras"] for x in self.j.lista()})        # a többi forrás javasol
        jo["x"] = True
        self.assertNotIn("hiba", self.j.frissit())
        self.assertIsNone(self.j.hiba)


class JovahagyasTest(Alap):
    def setUp(self):
        super().setUp()
        self.j.frissit()
        self.elso = self.j.lista()[0]

    def test_jovahagyas_beirja_az_esemenyt_a_tanulas_naptarba(self):
        r = self.j.jovahagy(self.elso["id"])
        self.assertEqual((r["ok"], r["allapot"], r["naptar"]), (True, "beirva", "TAN"))
        ir = self.irasok()
        self.assertEqual((len(ir), ir[0]["javaslat"], ir[0]["naptar"]), (1, self.elso["id"], "TAN"))
        e = [x for x in self.al.olvas()["esemenyek"] if x["cim"] == self.elso["cim"]]
        self.assertEqual((len(e), e[0]["kezd"], e[0]["veg"]), (1, self.elso["kezd"], self.elso["veg"]))
        self.assertIn(f"Manifold-javaslat #{self.elso['id']}", e[0]["jegyzet"])
        self.assertEqual(next(x for x in self.j.lista(False) if x["id"] == self.elso["id"])["allapot"], "beirva")
        with self.assertRaises(HttpError) as cm:                                  # kétszer nem
            self.j.jovahagy(self.elso["id"])
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(len(self.irasok()), 1)

    def test_a_beirt_blokk_utan_nincs_ujabb_javaslat_ugyanarra(self):
        self.j.jovahagy(self.elso["id"])
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)                     # a naptár most már tartalmazza a blokkot
        self.assertEqual(self.j.frissit()["uj"], 0)
        self.assertEqual(len(self.j.lista()), 0)  # a forrás már nem javasolja: a korábbi sorok is lejárnak

    def test_nincs_tanulas_naptar(self):
        self.al.modosit(lambda d: d["naptarak"].pop())
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        with self.assertRaises(HttpError) as cm:
            self.j.jovahagy(self.elso["id"])
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.irasok(), [])

    def test_nem_irhato_naptar(self):
        self.al.modosit(lambda d: d["naptarak"][-1].update(irhato=False))
        with self.assertRaises(HttpError) as cm:
            self.j.jovahagy(self.elso["id"])
        self.assertEqual(cm.exception.code, 502)
        self.assertEqual(self.irasok(), [])
        self.assertEqual(next(x for x in self.j.lista(False) if x["id"] == self.elso["id"])["allapot"], "uj")   # nyitva marad

    def test_a_kozben_foglalt_lett_sav_lejart(self):
        self.al.modosit(lambda d: d["esemenyek"].append(ev("b", "ORA", self.elso["kezd"], self.elso["veg"], "Beékelt óra")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        with self.assertRaises(HttpError) as cm:
            self.j.jovahagy(self.elso["id"])
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.irasok(), [])
        mostani = next(x for x in self.j.lista(False) if x["id"] == self.elso["id"])
        self.assertEqual(mostani["allapot"], "lejart")

    def _beirt_szinkron_nelkul(self, nap, perc=45):
        """Egy már beírt, de a naptár-szinkronban még nem látszó javaslat ugyanarra a napra (CX-009)."""
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("INSERT INTO naptar_javaslat (forras, azon, nap, kezd, veg, perc, cim, allapot, esemeny_azon, letrehozva) "
                      "VALUES ('kulso', 'kulso|1', ?, ?, ?, ?, 'Tanulás', 'beirva', 'meg-nem-szinkronizalt', ?)",
                      (nap, f"{nap}T08:00:00+02:00", f"{nap}T08:45:00+02:00", perc, MOST.isoformat()))

    def test_keret_miatt_lezart_javaslat_nem_nyilik_ujra(self):
        # CX-009: a jóváhagyás keret miatt zár; a frissítés ugyanazzal a kerettel számol, így nem nyitja újra (nincs kör)
        self._beirt_szinkron_nelkul(self.elso["nap"])
        with self.assertRaises(HttpError) as cm:
            self.j.jovahagy(self.elso["id"])
        self.assertEqual(cm.exception.code, 409)
        sor = next(x for x in self.j.lista(False) if x["id"] == self.elso["id"])
        self.assertEqual((sor["allapot"], sor["hiba"]), ("lejart", naptar_javaslat.KERET_ELFOGYOTT))
        for _ in range(2):
            self.j.frissit()
            sor = next(x for x in self.j.lista(False) if x["id"] == self.elso["id"])
            self.assertEqual(sor["allapot"], "lejart")
        self.assertEqual(self.irasok(), [])

    def test_keret_miatt_lezart_ujranyilik_ha_a_keret_felszabadul(self):
        from core.felkeszultseg import keret
        self._beirt_szinkron_nelkul(self.elso["nap"])
        with self.assertRaises(HttpError):
            self.j.jovahagy(self.elso["id"])
        keret.ir(self.cfg, {"napi_perc": 120})
        self.j.frissit()
        sor = next(x for x in self.j.lista(False) if x["id"] == self.elso["id"])
        self.assertEqual(sor["allapot"], "uj")
        self.assertEqual(self.j.jovahagy(self.elso["id"])["allapot"], "beirva")

    def test_hianyos_tanulasi_esemeny_nem_dont_el(self):
        # CX-009: a hiányzó `veg`/`kezd`/`azon` esemény a keret-számításból kimarad, nem TypeError/KeyError
        hianyos = [{"kategoria": "tanulas", "kezd": self.elso["kezd"], "veg": None, "cim": "x"},
                   {"kategoria": "tanulas", "kezd": None, "veg": self.elso["veg"], "cim": "y"},
                   {"kategoria": "tanulas", "kezd": "nem-datum", "veg": "nem-datum", "cim": "z"}]
        with mock.patch.object(naptar_javaslat.naptar, "esemenyek", return_value=hianyos):
            r = self.j.jovahagy(self.elso["id"])
        self.assertEqual(r["allapot"], "beirva")

    def test_mult_idopont_nem_irhato(self):
        keso = Javaslatok(self.cfg, Seged(self.cfg), mikor=lambda: datetime(2026, 10, 9, 12, 0, tzinfo=TZ))
        with self.assertRaises(HttpError):
            keso.jovahagy(self.elso["id"])
        self.assertEqual(self.irasok(), [])

    def test_tanulas_naptar_konfigbol(self):
        self.al.modosit(lambda d: d["naptarak"].append(nt("TAN2", "Studying 2")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        self.cfg.data.setdefault("naptar", {})["tanulas_naptar"] = "Studying 2"
        self.assertEqual(self.j.jovahagy(self.elso["id"])["naptar"], "TAN2")

    def test_ismeretlen_javaslat(self):
        with self.assertRaises(HttpError) as cm:
            self.j.jovahagy(9999)
        self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
