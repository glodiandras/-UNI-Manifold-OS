"""C22a: a `kviz_eredmeny` tracker-esemény adata (`modulok/kviz/esemeny.py`) — fehérlistás, jegyzettartalom nélküli."""
import json
import unittest

from core import tracker
from modulok.kviz import ertekeles as E
from modulok.kviz import esemeny as ES
from tests.test_kviz_ertekeles import kviz, rossz


def ertekeles():
    k = kviz()
    return E.kitoltes_ertekel(k, [{"kerdes": "k1", "valasz": k.kerdesek[0].helyes, "tipp": False, "ms": 900},
                                  {"kerdes": "k2", "valasz": rossz(k, 1), "tipp": False},
                                  {"kerdes": "k3", "valasz": k.kerdesek[2].helyes, "tipp": True}], ido_ms=61000), k


class EsemenyAdatTest(unittest.TestCase):
    def test_az_adat_alakja(self):
        e, k = ertekeles()
        d = ES.adat(e, k.azon)
        self.assertEqual(d, {"kviz": k.azon, "mod": "teljes", "pont": 2, "osszes": 3, "szazalek": 67, "tudja": 1, "szerencses": 1,
                             "tevkepzet": 1, "hiany": 0, "ms": 61000})
        self.assertEqual(ES.hibak(d), [])

    def test_csak_a_fehérlistás_kulcsok_es_nincs_jegyzettartalom(self):
        e, k = ertekeles()
        d = ES.adat(e, k.azon)
        self.assertEqual(set(d), set(ES.KULCSOK))
        szoveg = json.dumps(d, ensure_ascii=False)
        for tilos in ("Mi a", "Nevezetes", "M03", "Algebra", "szakasz", "idezet", "valaszok"):
            self.assertNotIn(tilos, szoveg)

    def test_belefer_a_tracker_korlatba_es_a_tracker_elfogadja(self):
        e, k = ertekeles()
        self.assertLess(len(json.dumps(ES.adat(e, k.azon)).encode()), tracker.ADAT_MAX)
        self.assertIn("kviz_eredmeny", tracker.ESEMENY_TIPUSOK)

    def test_a_tracker_sema_egyezik_a_kviz_esemennyel(self):
        """A3-05: a core által küldött adat az `adat_tisztit` után egy kulcsot sem veszít; a két oldal tartománya és
        azonosító-mintája egyezik (egy séma)."""
        e, k = ertekeles()
        d = ES.adat(e, k.azon)
        tiszta, elhagyott = tracker.adat_tisztit("kviz_eredmeny", d)
        self.assertEqual(elhagyott, [])
        self.assertEqual(tiszta, d)
        self.assertTrue(set(ES.KULCSOK) <= set(tracker.ADAT_SEMA["kviz_eredmeny"]))
        self.assertEqual(tracker.KVIZ_AZON.pattern, ES.AZON_RE.pattern)
        sema = tracker.ADAT_SEMA["kviz_eredmeny"]
        for kulcs in ES.KULCSOK[2:]:                                  # a számkulcsok felső határa azonos
            hatar = 100 if kulcs == "szazalek" else 86_400_000 if kulcs == "ms" else 100_000
            self.assertEqual(sema[kulcs][2], hatar, kulcs)
            b = {**d, "osszes": 100_000}                              # a `pont` határa csak ennél az összesnél érvényes
            self.assertEqual(ES.hibak({**b, kulcs: hatar}), [], kulcs)
            self.assertEqual(tracker.adat_tisztit("kviz_eredmeny", {**b, kulcs: hatar})[0][kulcs], hatar, kulcs)
            self.assertTrue(ES.hibak({**b, kulcs: hatar + 1}), kulcs)
            with self.assertRaises(tracker.HttpError):
                tracker.adat_tisztit("kviz_eredmeny", {**b, kulcs: hatar + 1})

    def test_a_tracker_elutasitja_a_lehetetlen_pontot(self):
        e, k = ertekeles()
        with self.assertRaises(tracker.HttpError):
            tracker.adat_tisztit("kviz_eredmeny", {**ES.adat(e, k.azon), "pont": 4, "osszes": 3})
        self.assertTrue(ES.hibak({**ES.adat(e, k.azon), "pont": 4, "osszes": 3}))

    def test_hianyzo_ido_nem_kerul_bele(self):
        e, k = ertekeles()
        e["ido_ms"] = None
        self.assertNotIn("ms", ES.adat(e, k.azon))

    def test_hibak(self):
        e, k = ertekeles()
        jo = ES.adat(e, k.azon)
        for rossz_adat in ({**jo, "kviz": "nem azonosito"}, {**jo, "mod": "furcsa"}, {**jo, "pont": -1}, {**jo, "szazalek": 101},
                           {**jo, "extra": 1}, {k_: v for k_, v in jo.items() if k_ != "pont"}, {**jo, "ms": "x"}):
            self.assertTrue(ES.hibak(rossz_adat), rossz_adat)


if __name__ == "__main__":
    unittest.main()
