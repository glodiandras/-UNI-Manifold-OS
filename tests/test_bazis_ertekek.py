"""A Bases értékei és kényszerítései (`core/bazis/ertekek.py`, C12 2. lépés): a terv „Kényszerítések” táblájának
minden sora, a dátum- és időtartam-kezelés, a rendezés és a JSON-kimenet."""
import math
import unittest
from datetime import datetime

from core.bazis import ertekek as e
from core.bazis.adat import Sor
from core.bazis.ertekek import (
    Cimke, Datum, Fajl, FutasHiba, Hiba, Html, Idotartam, Ikon, Kep, Link, Regex,
)


def D(s: str) -> Datum:
    return e.datum_szovegbol(s)


class IgazsagTest(unittest.TestCase):
    def test_hamis_ertekek(self):
        for x in (None, False, 0, 0.0, math.nan, ""):
            self.assertFalse(e.igaz_e(x), repr(x))

    def test_igaz_ertekek(self):
        for x in (True, 1, -1, "0", "false", [], {}, [0], D("2026-01-01")):
            self.assertTrue(e.igaz_e(x), repr(x))


class OsszeadTest(unittest.TestCase):
    def test_szam(self):
        self.assertEqual(e.osszead(1, 2), 3)
        self.assertEqual(e.osszead(0.5, 0.5), 1)
        self.assertIsInstance(e.osszead(0.5, 0.5), int)
        self.assertEqual(e.osszead(0.1, 0.2), 0.1 + 0.2)

    def test_szoveg_osszefuzes_az_ures_ures_szoveg(self):
        self.assertEqual(e.osszead("a", "b"), "ab")
        self.assertEqual(e.osszead("a", 1), "a1")
        self.assertEqual(e.osszead(1.5, "x"), "1.5x")
        self.assertEqual(e.osszead(None, "x"), "x")
        self.assertEqual(e.osszead("x", None), "x")
        self.assertEqual(e.osszead("x", True), "xtrue")
        self.assertEqual(e.osszead("x", [1, 2]), "x1,2")

    def test_ures_plusz_szam_ures(self):
        self.assertIsNone(e.osszead(None, 1))
        self.assertIsNone(e.osszead(1, None))
        self.assertIsNone(e.osszead(None, None))

    def test_datum_plusz_idotartam(self):
        self.assertEqual(e.osszead(D("2024-12-01"), "1M"), D("2025-01-01"))
        self.assertEqual(e.osszead(D("2024-01-31"), "1M"), D("2024-02-29"))        # a hónap végére vág
        self.assertEqual(e.osszead(D("2024-12-01"), Idotartam(0, e.NAP_MS)), D("2024-12-02"))
        r = e.osszead(D("2024-12-01"), "4h")
        self.assertTrue(r.van_ido)
        self.assertEqual(r.ertek, datetime(2024, 12, 1, 4))
        self.assertFalse(e.osszead(D("2024-12-01"), "2d").van_ido)
        self.assertEqual(e.osszead(Idotartam(0, e.NAP_MS), D("2024-12-01")), D("2024-12-02"))

    def test_datum_plusz_nem_idotartam_szoveg_osszefuzes(self):
        self.assertEqual(e.osszead(D("2024-12-01"), " kedd"), "2024-12-01 kedd")
        self.assertEqual(e.osszead("a: ", D("2024-12-01 10:30:00")), "a: 2024-12-01 10:30:00")

    def test_hiba(self):
        for a, b in [(True, 1), ([1], 1), ({}, 2), (1, [2]), (Link("x"), 1), (D("2024-01-01"), 1)]:
            with self.assertRaises(FutasHiba, msg=repr((a, b))):
                e.osszead(a, b)


class KivonTest(unittest.TestCase):
    def test_kivonas(self):
        self.assertEqual(e.kivon(5, 3), 2)
        self.assertEqual(e.kivon(D("2024-12-02"), D("2024-12-01")), e.NAP_MS)
        self.assertEqual(e.kivon(D("2024-12-01"), D("2024-12-02")), -e.NAP_MS)
        self.assertEqual(e.kivon(D("2024-12-01 10:00:00"), "2h"), D("2024-12-01 08:00:00"))
        self.assertEqual(e.kivon(D("2025-01-31"), "1M"), D("2024-12-31"))
        self.assertEqual(e.kivon(Idotartam(0, 10), Idotartam(0, 4)), Idotartam(0, 6))
        self.assertIsNone(e.kivon(None, 1))
        self.assertIsNone(e.kivon(1, None))

    def test_hiba(self):
        for a, b in [("a", "b"), (D("2024-01-01"), "nem időtartam"), (1, D("2024-01-01")), (True, 1)]:
            with self.assertRaises(FutasHiba, msg=repr((a, b))):
                e.kivon(a, b)

    def test_ket_datum_kulonbsege_egy_nap_ezredmasodpercben(self):
        self.assertEqual(e.kivon(e.osszead(D("2026-10-02 12:00:00"), "1d"), D("2026-10-02 12:00:00")), 86400000)


class SzorzasOsztasTest(unittest.TestCase):
    def test_szamok(self):
        self.assertEqual(e.szoroz(6, 7), 42)
        self.assertEqual(e.oszt(6, 3), 2)
        self.assertEqual(e.oszt(1, 4), 0.25)
        self.assertEqual(e.modulo(7, 3), 1)
        self.assertEqual(e.modulo(-7, 3), -1)                    # az osztandó előjele (JavaScript)
        self.assertEqual(e.modulo(7.5, 2), 1.5)

    def test_nullaval_osztas(self):
        self.assertEqual(e.oszt(1, 0), math.inf)
        self.assertEqual(e.oszt(-1, 0), -math.inf)
        self.assertTrue(math.isnan(e.oszt(0, 0)))
        self.assertTrue(math.isnan(e.modulo(5, 0)))

    def test_idotartam_skalarral(self):
        self.assertEqual(e.szoroz(Idotartam(0, 3_600_000), 2), Idotartam(0, 7_200_000))
        self.assertEqual(e.oszt(Idotartam(0, 3_600_000), 2), Idotartam(0, 1_800_000))
        with self.assertRaises(FutasHiba):
            e.szoroz(2, Idotartam(0, 5))                        # az időtartam a bal oldalon áll (dokumentáció)

    def test_csak_szam(self):
        for f in (e.szoroz, e.oszt, e.modulo):
            for a, b in [("a", 2), (2, "a"), (None, 2), (True, 2), ([1], 2)]:
                with self.assertRaises(FutasHiba, msg=f"{f.__name__} {a!r} {b!r}"):
                    f(a, b)


class EgyenloTest(unittest.TestCase):
    def test_primitivek(self):
        self.assertTrue(e.egyenlo(1, 1.0))
        self.assertTrue(e.egyenlo("a", "a"))
        self.assertFalse(e.egyenlo("a", "A"))
        self.assertTrue(e.egyenlo(None, None))
        self.assertFalse(e.egyenlo(None, 0))
        self.assertFalse(e.egyenlo(None, ""))
        self.assertFalse(e.egyenlo(0, False))                      # különböző típus
        self.assertFalse(e.egyenlo("1", 1))
        self.assertTrue(e.egyenlo(True, True))

    def test_lista_elemenkent_sorrendben(self):
        self.assertTrue(e.egyenlo([1, 2], [1, 2]))
        self.assertFalse(e.egyenlo([1, 2], [2, 1]))
        self.assertFalse(e.egyenlo([1], [1, 1]))
        self.assertTrue(e.egyenlo([], []))
        self.assertTrue(e.egyenlo([Cimke("#Book")], ["Book"]))      # `file.tags == ["Book"]`
        self.assertFalse(e.egyenlo([Cimke("#Book"), Cimke("#x")], ["Book"]))

    def test_objektum(self):
        self.assertTrue(e.egyenlo({"a": 1}, {"a": 1}))
        self.assertFalse(e.egyenlo({"a": 1}, {"a": 2}))
        self.assertFalse(e.egyenlo({"a": 1}, {"b": 1}))

    def test_cimke_es_szoveg(self):
        self.assertTrue(e.egyenlo(Cimke("#Book"), "Book"))
        self.assertTrue(e.egyenlo(Cimke("#Book"), "#book"))
        self.assertTrue(e.egyenlo("BOOK", Cimke("#book")))
        self.assertTrue(e.egyenlo(Cimke("#a/b"), Cimke("#A/B")))
        self.assertFalse(e.egyenlo(Cimke("#Book"), "Books"))
        self.assertFalse(e.egyenlo(Cimke("#Book"), 1))

    def test_datum_azonos_pillanat(self):
        self.assertTrue(e.egyenlo(D("2024-01-01"), D("2024-01-01 00:00:00")))
        self.assertFalse(e.egyenlo(D("2024-01-01"), D("2024-01-02")))
        self.assertFalse(e.egyenlo(D("2024-01-01"), "2024-01-01"))

    def test_link_es_fajl(self):
        s = Sor("A/Cél.md")
        f = Fajl(s, None)
        self.assertTrue(e.egyenlo(Link("Cél", None, "A/Cél.md"), Link("A/Cél", "másik név", "A/Cél.md")))
        self.assertFalse(e.egyenlo(Link("Cél", None, "A/Cél.md"), Link("Cél", None, "B/Cél.md")))
        self.assertTrue(e.egyenlo(Link("Cél", None, "A/Cél.md"), f))
        self.assertTrue(e.egyenlo(f, Link("x", None, "A/Cél.md")))
        self.assertFalse(e.egyenlo(Link("Cél", None, None), f))
        # feloldatlan linkek: a cél szövege
        self.assertTrue(e.egyenlo(Link("Nincs"), Link("Nincs", "kijelzés")))
        self.assertFalse(e.egyenlo(Link("Nincs"), Link("Más")))
        self.assertFalse(e.egyenlo(Link("Nincs"), "Nincs"))


class HasonlitTest(unittest.TestCase):
    def test_osszehasonlithato(self):
        self.assertEqual(e.hasonlit(1, 2), -1)
        self.assertEqual(e.hasonlit(2, 2.0), 0)
        self.assertEqual(e.hasonlit("b", "a"), 1)
        self.assertEqual(e.hasonlit(D("2024-01-01"), D("2024-01-02")), -1)
        self.assertEqual(e.hasonlit(Idotartam(0, 5), Idotartam(0, 4)), 1)

    def test_vegyes_vagy_ures_nem_osszehasonlithato(self):
        for a, b in [(1, "1"), (None, 1), (1, None), (None, None), ("a", None), (True, False), ([1], [2]),
                     (D("2024-01-01"), "2024-01-02"), (math.nan, 1)]:
            self.assertIsNone(e.hasonlit(a, b), repr((a, b)))


class IdotartamTest(unittest.TestCase):
    def test_egysegek(self):
        for sz, ho, ms in [("1y", 12, 0), ("2M", 2, 0), ("1d", 0, e.NAP_MS), ("2w", 0, 14 * e.NAP_MS),
                           ("3h", 0, 3 * 3_600_000), ("4m", 0, 240_000), ("5s", 0, 5000),
                           ("1 day", 0, e.NAP_MS), ("2 days", 0, 2 * e.NAP_MS), ("1 week", 0, 7 * e.NAP_MS),
                           ("1 month", 1, 0), ("2 Years", 24, 0), ("1 hour", 0, 3_600_000),
                           ("90 minutes", 0, 5_400_000), ("1M 4h 3m", 1, 4 * 3_600_000 + 180_000),
                           ("-1d", 0, -e.NAP_MS), ("1.5h", 0, 5_400_000)]:
            self.assertEqual(e.idotartam(sz), Idotartam(ho, ms), sz)

    def test_nagy_M_ho_kis_m_perc(self):
        self.assertEqual(e.idotartam("1M").honap, 1)
        self.assertEqual(e.idotartam("1m").ms, 60_000)

    def test_nem_idotartam(self):
        for sz in ("", "x", "1", "d", "1 fortnight", "1.5M", "2d x", None, 5):
            self.assertIsNone(e.idotartam(sz), repr(sz))

    def test_szoveg(self):
        self.assertEqual(Idotartam(14, 3 * 3_600_000).szoveg(), "1y 2M 3h")
        self.assertEqual(Idotartam(0, 0).szoveg(), "0s")


class DatumTest(unittest.TestCase):
    def test_szovegbol(self):
        self.assertEqual(D("2025-01-01 04:03:00").ertek, datetime(2025, 1, 1, 4, 3))
        self.assertTrue(D("2025-01-01 04:03").van_ido)
        self.assertTrue(D("2025-01-01T04:03:00").van_ido)
        self.assertFalse(D("2025-01-01").van_ido)
        for rossz in ("2025-13-01", "2025-02-30", "holnap", "2025-1-1", "", "2025-01-01 25:00"):
            self.assertIsNone(e.datum_szovegbol(rossz), rossz)

    def test_idozona_helyi_idore_valt(self):
        a = e.datum_szovegbol("2025-06-01T12:00:00Z")
        b = e.datum_szovegbol("2025-06-01T14:00:00+02:00")
        self.assertEqual(a, b)

    def test_formaz(self):
        d = D("2025-03-07 14:05:09")
        for minta, vart in [("YYYY-MM-DD", "2025-03-07"), ("YY/M/D", "25/3/7"), ("HH:mm:ss", "14:05:09"),
                            ("h:mm A", "2:05 PM"), ("dddd, MMMM Do", "Friday, March 7th"), ("ddd MMM", "Fri Mar"),
                            ("[YYYY] YYYY", "YYYY 2025"), ("Q", "1"), ("SSS", "000"), ("a", "pm"), ("W", "10")]:
            self.assertEqual(e.datum_formaz(d, minta), vart, minta)

    def test_relativ(self):
        most = D("2026-10-02 12:00:00")
        for s, vart in [("2026-10-02 11:59:50", "a few seconds ago"), ("2026-10-02 11:50:00", "10 minutes ago"),
                        ("2026-10-02 09:00:00", "3 hours ago"), ("2026-09-29 12:00:00", "3 days ago"),
                        ("2026-10-02 13:00:00", "in an hour"), ("2025-10-02 12:00:00", "a year ago"),
                        ("2026-07-02 12:00:00", "3 months ago")]:
            self.assertEqual(e.datum_relativ(D(s), most), vart, s)

    def test_mezok(self):
        d = D("2025-03-07 14:05:09")
        self.assertEqual([e.datum_mezo(d, n) for n in ("year", "month", "day", "hour", "minute", "second",
                                                      "millisecond")], [2025, 3, 7, 14, 5, 9, 0])
        self.assertIsNone(e.datum_mezo(d, "nincs"))


class HelyiIdoTest(unittest.TestCase):
    """T155 (C31): a dátum-különbség és a `Z`/`ZZ` a helyi időzóna szerint, ahogy a JS `Date` és a moment (Budapest)."""

    def setUp(self):
        import os
        import time
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Budapest"
        time.tzset()

    def tearDown(self):
        import os
        import time
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def test_kulonbseg_a_nyari_ido_valtasan_at(self):
        self.assertEqual(e.kivon(D("2026-03-30"), D("2026-03-29")), 23 * 3_600_000)      # tavaszi váltás (márc. 29.)
        self.assertEqual(e.kivon(D("2026-10-26"), D("2026-10-25")), 25 * 3_600_000)      # őszi váltás (okt. 25.)
        self.assertEqual(e.kivon(D("2026-03-29 03:00:00"), D("2026-03-29 01:00:00")), 3_600_000)
        self.assertEqual(e.kivon(D("2026-04-02"), D("2026-04-01")), e.NAP_MS)

    def test_z_es_zz_a_helyi_eltolas(self):
        self.assertEqual(e.datum_formaz(D("2026-01-15 10:00:00"), "Z|ZZ"), "+01:00|+0100")
        self.assertEqual(e.datum_formaz(D("2026-07-15 10:00:00"), "Z|ZZ"), "+02:00|+0200")


class SzamSzovegTest(unittest.TestCase):
    def test_kerekites_a_fel_felfele(self):
        self.assertEqual(e.kerekit(2.5), 3)
        self.assertEqual(e.kerekit(-2.5), -2)
        self.assertEqual(e.kerekit(2.3333, 2), 2.33)
        self.assertEqual(e.kerekit(1.005, 2), 1)                    # a bináris érték 1.00499…
        self.assertEqual(e.kerekit(1234, -2), 1200)

    def test_fixre(self):
        self.assertEqual(e.fixre(3.14159, 2), "3.14")
        self.assertEqual(e.fixre(2.5, 0), "3")
        self.assertEqual(e.fixre(-2.5, 0), "-3")
        self.assertEqual(e.fixre(1.005, 2), "1.00")
        self.assertEqual(e.fixre(5, 2), "5.00")
        self.assertEqual(e.fixre(-0.001, 2), "-0.00")              # JS: x < 0 → „-” előtag (T155, C31)
        self.assertEqual(e.fixre(-0.0, 2), "0.00")                 # a -0 nem kisebb 0-nál
        self.assertEqual(e.fixre(math.inf, 2), "Infinity")

    def test_fixre_28_jegy_felett_es_1e21(self):
        """T155 (C31): az alap `decimal`-kontextus 28 jegye nem korlát; az `|x| ≥ 1e21` a JS `String(x)`-e."""
        self.assertEqual(e.fixre(1e20, 10), "100000000000000000000.0000000000")
        self.assertEqual(e.fixre(123456789.123, 30), "123456789.122999995946884155273437500000")
        self.assertEqual(e.fixre(0.1, 40), "0.1000000000000000055511151231257827021182")
        self.assertEqual(e.fixre(1e21, 2), "1e+21")
        self.assertEqual(e.fixre(-1.5e22, 2), "-1.5e+22")
        self.assertEqual(e.fixre(10 ** 25, 0), "1e+25")

    def test_szam_szoveg(self):
        self.assertEqual([e.szam_szoveg(x) for x in (3, 3.0, 2.5, -1, math.inf, -math.inf, math.nan)],
                         ["3", "3", "2.5", "-1", "Infinity", "-Infinity", "NaN"])


class SzovegeTest(unittest.TestCase):
    def test_szovegge(self):
        for x, vart in [(None, ""), (True, "true"), (False, "false"), (3, "3"), (2.5, "2.5"), ("a", "a"),
                        ([1, "a", None], "1,a,"), (D("2024-01-01"), "2024-01-01"),
                        (D("2024-01-01 10:00:00"), "2024-01-01 10:00:00"), (Link("A/Cél", None, "A/Cél.md"), "Cél"),
                        (Link("Cél", "mutat"), "mutat"), (Cimke("#x"), "#x"), (Fajl(Sor("A/B.md"), None), "A/B.md"),
                        (Html("<b>"), "<b>"), (Ikon("plus"), "plus"), (Hiba("rossz"), "rossz")]:
            self.assertEqual(e.szovegge(x), vart, repr(x))


class RendezesTest(unittest.TestCase):
    def rendez(self, lista):
        return sorted(lista, key=e.rendezo_kulcs)

    def test_ures_elol_tipusonkent(self):
        self.assertEqual(self.rendez([3, None, 1, 2]), [None, 1, 2, 3])
        self.assertEqual(self.rendez(["b", None, "a"]), [None, "a", "b"])

    def test_szoveg_kis_nagybetu_es_ekezet_nelkul_elsodlegesen(self):
        self.assertEqual(self.rendez(["b", "A", "á", "a", "B"]), ["A", "a", "á", "b", "B"])
        self.assertEqual(self.rendez(["Zsolt", "Ádám", "Béla", "adél"]), ["Ádám", "adél", "Béla", "Zsolt"])

    def test_datum_idorendben(self):
        self.assertEqual(self.rendez([D("2024-03-01"), D("2024-01-01"), D("2024-02-01")]),
                         [D("2024-01-01"), D("2024-02-01"), D("2024-03-01")])

    def test_link_a_nev_szerint(self):
        a, b = Link("Béla", None, "Béla.md"), Link("Anna", None, "Anna.md")
        self.assertEqual(self.rendez([a, b]), [b, a])


class FmErtekTest(unittest.TestCase):
    def felold(self, cel):
        return {"Cél": "A/Cél.md"}.get(cel)

    def test_link(self):
        l = e.fm_ertekbol("[[Cél]]", "text", self.felold)
        self.assertEqual(l, Link("Cél", None, "A/Cél.md"))
        l = e.fm_ertekbol("[[Cél#Fej|mutat]]", "text", self.felold)
        self.assertEqual((l.cel, l.alcel, l.megjelenites, l.ut), ("Cél", "Fej", "mutat", "A/Cél.md"))
        self.assertIsNone(e.fm_ertekbol("[[Nincs]]", "text", self.felold).ut)

    def test_nem_teljes_link_szoveg_marad(self):
        for s in ("lásd [[Cél]]", "[[Cél]] és más", "[ [Cél] ]", "[[Cél]"):
            self.assertEqual(e.fm_ertekbol(s, "text", self.felold), s)

    def test_lista_es_objektum_rekurziv(self):
        self.assertEqual(e.fm_ertekbol(["[[Cél]]", "x", 1], "multitext", self.felold),
                         [Link("Cél", None, "A/Cél.md"), "x", 1])
        self.assertEqual(e.fm_ertekbol({"a": "[[Cél]]"}, None, self.felold)["a"].ut, "A/Cél.md")

    def test_datum_tipus(self):
        self.assertEqual(e.fm_ertekbol("2024-05-01", "date"), D("2024-05-01"))
        self.assertTrue(e.fm_ertekbol("2024-05-01T10:00", "datetime").van_ido)
        self.assertEqual(e.fm_ertekbol("2024-05-01", "text"), "2024-05-01")          # szöveg-típusnál szöveg marad
        self.assertEqual(e.fm_ertekbol("nem dátum", "date"), "nem dátum")

    def test_primitivek(self):
        self.assertEqual(e.fm_ertekbol(3, "number"), 3)
        self.assertIs(e.fm_ertekbol(True, "checkbox"), True)
        self.assertIsNone(e.fm_ertekbol(None, "text"))


class KimenetTest(unittest.TestCase):
    def test_alakok(self):
        for x, vart in [
            (None, None), (True, True), (3, 3), (2.5, 2.5), ("a", "a"),
            (math.inf, {"t": "szam", "v": "Infinity"}), (math.nan, {"t": "szam", "v": "NaN"}),
            ([1, "a"], {"t": "lista", "e": [1, "a"]}), ({"a": 1}, {"t": "objektum", "e": {"a": 1}}),
            (D("2024-01-02"), {"t": "datum", "iso": "2024-01-02", "ido": False}),
            (D("2024-01-02 03:04:05"), {"t": "datum", "iso": "2024-01-02T03:04:05", "ido": True}),
            (Link("Cél", None, "A/Cél.md"), {"t": "link", "cel": "Cél", "ut": "A/Cél.md", "nev": "Cél"}),
            (Link("Cél", "mutat", None, "Fej"), {"t": "link", "cel": "Cél", "ut": None, "nev": "mutat", "alcel": "Fej"}),
            (Fajl(Sor("A/B.md"), None), {"t": "link", "cel": "A/B.md", "ut": "A/B.md", "nev": "B"}),
            (Cimke("#x"), {"t": "cimke", "v": "#x"}), (Hiba("rossz"), {"t": "hiba", "u": "rossz"}),
            (Kep(szin="#fff"), {"t": "kep", "szin": "#fff"}), (Ikon("plus"), {"t": "ikon", "nev": "plus"}),
            (Html("<b>"), {"t": "html", "v": "<b>"}), (Regex("a", "g"), {"t": "regex", "v": "/a/g"}),
        ]:
            self.assertEqual(e.kimenet(x), vart, repr(x))

    def test_json_alak_szerializalhato(self):
        import json
        json.dumps(e.kimenet([D("2024-01-01"), [Link("x")], {"k": Cimke("#t")}, math.inf]), allow_nan=False)


class KulcsTest(unittest.TestCase):
    def test_kulcs_az_egyenlosegnek_megfelelo(self):
        self.assertEqual(e.kulcs(1), e.kulcs(1.0))
        self.assertNotEqual(e.kulcs(1), e.kulcs(True))
        self.assertNotEqual(e.kulcs("1"), e.kulcs(1))
        self.assertEqual(e.kulcs(Link("a", None, "X.md")), e.kulcs(Fajl(Sor("X.md"), None)))
        self.assertEqual(e.kulcs([1, "a"]), e.kulcs([1, "a"]))
        self.assertEqual(e.kulcs({"a": 1, "b": 2}), e.kulcs({"b": 2, "a": 1}))


class AuditHataroktTest(unittest.TestCase):
    """C29.8 (T041): szélsőséges dátum és kerekítés — a Bases-lekérdezés ne 500-zal essen el."""

    def test_nagyon_koran_es_nagyon_kesei_datum_rendezo_kulcsa(self):
        koran = e.rendezo_kulcs(Datum(datetime(1, 1, 1), True))              # ma: ValueError (a helyi időzóna miatt)
        kesei = e.rendezo_kulcs(Datum(datetime(9999, 12, 31, 23, 59), True))
        ma = e.rendezo_kulcs(Datum(datetime(2026, 10, 2, 12), True))
        self.assertEqual((koran[0], ma[0], kesei[0]), (3, 3, 3))
        self.assertLess(koran, ma)
        self.assertLess(ma, kesei)
        self.assertEqual(e.datum_ms(Datum(datetime(2026, 1, 1), True)), round(datetime(2026, 1, 1).timestamp() * 1000))
        self.assertIsInstance(e.datum_ms(Datum(datetime(1, 1, 1), True)), int)

    def test_kerekites_jegyeinek_korlatja(self):
        self.assertEqual(e.kerekit(1.2345, 2), 1.23)
        self.assertEqual(e.kerekit(1.5, 10), 1.5)
        for jegyek in (101, 3_000_000, -101):
            with self.assertRaisesRegex(FutasHiba, "100 közti"):
                e.kerekit(1.5, jegyek)


if __name__ == "__main__":
    unittest.main()
