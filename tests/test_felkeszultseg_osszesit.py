"""A dolgozat-lista és a dolgozat-részlet (C28a): szám, kilátás, lefedettség, gyenge pontok, napi terv a naptári blokkokkal és
a javaslatokkal — a vault valós alakú szintetikus adatán. Csak olvas."""
import unittest
import unittest.mock
from datetime import date, timedelta, timezone

from core import naptar, szemelyes_db
from core.felkeszultseg import adat, osszesit
from core.felkeszultseg.forrasok import KvizEredmeny
from core.naptar_seged import Seged
from core.utvonalak import HttpError
from tests.felkeszultseg_segedek import Alap, DOLGOZAT_NAP, ESEMENYEK, FELK, MOST, T1, T2, T3
from tests.naptar_segedek import esemeny as ev

UTC = timezone.utc
T0 = MOST.astimezone(UTC) - timedelta(days=6)


def azon(a):
    return a.dolgozatok()[0]["azon"]


class NincsAdatTest(Alap):
    def test_lista_adat_nelkul_nincs_szam_de_a_temak_es_a_kotes_latszanak(self):
        a = self.adatok()
        l = osszesit.lista(a, MOST.date())
        d = l["dolgozatok"][0]
        self.assertEqual((d["szam"], d["kilatas"], d["szint"], d["temak_db"]), (None, None, "nincs_adat", 3))
        self.assertEqual(d["lefedettseg"], {"van": 0, "osszes": 3})
        self.assertEqual((d["jegyzet"], d["kotes"]["fok"]), (FELK, "biztos"))
        self.assertFalse(l["adatok"]["kartya"]["van"])
        self.assertFalse(l["adatok"]["kviz"]["van"])
        self.assertFalse(l["adatok"]["tracker"]["van"])
        self.assertFalse(l["naptar"]["regi"])

    def test_reszlet_adat_nelkul_a_terv_tanulatlan_temakkal(self):
        a = self.adatok()
        r = osszesit.reszlet(a, azon(a))
        self.assertEqual([t["nev"] for t in r["temak"]], ["01 - Hatvány", "02 - Gyökvonás", "03 - Logaritmus"])
        self.assertTrue(all(t["szam"] is None and t["ok"] == "nincs_mert_tudas" for t in r["temak"]))
        self.assertEqual([n["nap"] for n in r["terv"]["napok"]], ["2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06"])
        self.assertEqual(sum(n["perc"] for n in r["terv"]["napok"]), 180)
        self.assertEqual({s["ok"] for n in r["terv"]["napok"] for s in n["szeletek"]}, {"nincs adat"})
        self.assertEqual(r["gyenge_pontok"]["temak"], [])
        self.assertEqual(len(r["gyenge_pontok"]["nincs_adat"]), 3)
        self.assertEqual([f["oldalak"] for f in r["forrasok"]], ["18–19, 28"])
        self.assertFalse(r["keplet"]["kalibralt"])
        self.assertEqual(r["keplet"]["suly"]["kartya"], 0.40)
        self.assertEqual(r["terv"]["napok"][0]["kartya_esedekes"], 0)

    def test_ido_es_frissesseg_onmagaban_nem_ad_szamot_de_latszik(self):
        self.aktiv("2026-10-02", T1, 1800)
        r = osszesit.reszlet(self.adatok(), azon(self.adatok()))
        t = r["temak"][0]
        self.assertIsNone(t["szam"])
        self.assertEqual((t["tanult_perc"], t["utolso_tanulas"]), (30.0, "2026-10-02"))

    def test_ismeretlen_dolgozat_404(self):
        with self.assertRaises(HttpError) as cm:
            osszesit.reszlet(self.adatok(), "nincs")
        self.assertEqual(cm.exception.code, 404)

    def test_regi_naptar_jelzes(self):
        l = osszesit.lista(self.adatok(MOST + timedelta(days=3)), (MOST + timedelta(days=3)).date())
        self.assertTrue(l["naptar"]["regi"])


class AdattalTest(Alap):
    def setUp(self):
        super().setUp()
        self.kartyak(T1, ("c-00000001", "Mi a hatvány?", "szorzás"), ("c-00000002", "Mi a 2^3?", "8"),
                     ("c-00000003", "Mi a 0^0?", "nem értelmezett"), most=T0)
        regi = MOST.astimezone(UTC) - timedelta(days=60)
        self.kartyak(T2, ("c-00000011", "Mi a gyök?", "fordított hatvány"), ("c-00000012", "Mi a négyzetgyök?", "x"),
                     ("c-00000013", "Mi a köbgyök?", "y"), most=regi)
        for azon_, jegy in (("c-00000001", 4), ("c-00000002", 4), ("c-00000003", 4)):         # a hatvány jól megy, frissen
            self.valasz(azon_, jegy, T0 + timedelta(days=4))
        for azon_ in ("c-00000011", "c-00000012", "c-00000013"):                              # a gyökvonás: egyszer elrontva,
            self.valasz(azon_, 1, regi)                                                       # azóta nem ismételve

    def test_szam_kilatas_es_lefedettseg(self):
        a = self.adatok()
        d = osszesit.lista(a, MOST.date())["dolgozatok"][0]
        self.assertIsNotNone(d["szam"])
        self.assertTrue(0 <= d["szam"] <= 1)
        self.assertEqual(d["lefedettseg"], {"van": 2, "osszes": 3})
        self.assertEqual(d["nincs_adat_db"], 1)
        self.assertLess(d["kilatas"], d["szam"])                 # a dolgozat napjára csökken, ha nincs több tanulás

    def test_a_jo_tema_jobb_mint_a_rossz_es_a_gyenge_pont_a_rossz(self):
        a = self.adatok()
        r = osszesit.reszlet(a, azon(a))
        t = {x["nev"]: x for x in r["temak"]}
        self.assertGreater(t["01 - Hatvány"]["szam"], t["02 - Gyökvonás"]["szam"])
        self.assertEqual(t["01 - Hatvány"]["szint"] in ("jo", "kozepes"), True)
        self.assertEqual([x["nev"] for x in r["gyenge_pontok"]["temak"]][:1], ["02 - Gyökvonás"])
        self.assertEqual([x["nev"] for x in r["gyenge_pontok"]["nincs_adat"]], ["03 - Logaritmus"])
        self.assertTrue(r["gyenge_pontok"]["kartyak"])
        self.assertTrue(all(c["tema"] == T2 for c in r["gyenge_pontok"]["kartyak"][:3]))

    def test_osszetevok_lefurhatok(self):
        r = osszesit.reszlet(self.adatok(), azon(self.adatok()))
        t = r["temak"][0]
        self.assertEqual([o["nev"] for o in t["osszetevok"]], ["kartya", "kviz", "frissesseg", "ido"])
        k = t["osszetevok"][0]
        self.assertEqual((k["adat"]["db"], k["bizalom"]), (3, 0.6))
        self.assertIsNone(t["osszetevok"][1]["ertek"])               # nincs kvíz
        self.assertEqual(t["kartya"]["db"], 3)
        self.assertTrue(r["adatok"]["kartya"]["van"])

    def test_a_terv_a_gyenge_temanak_ad_tobb_idot(self):
        a = self.adatok()
        r = osszesit.reszlet(a, azon(a))
        perc = {}
        for n in r["terv"]["napok"]:
            for s in n["szeletek"]:
                perc[s["tema"]] = perc.get(s["tema"], 0) + s["perc"]
        self.assertGreater(perc["02 - Gyökvonás"], perc.get("01 - Hatvány", 0))
        self.assertGreater(perc["03 - Logaritmus"], perc.get("01 - Hatvány", 0))

    def test_kviz_javitja_a_szamot(self):
        elotte = osszesit.lista(self.adatok(), MOST.date())["dolgozatok"][0]["szam"]
        self.kviz(*[KvizEredmeny(T2, MOST - timedelta(days=1), 10, 10)])
        utana = osszesit.lista(self.adatok(), MOST.date())["dolgozatok"][0]["szam"]
        self.assertGreater(utana, elotte)

    def test_esedekes_kartyak_osszege_a_listaban(self):
        a = self.adatok(MOST + timedelta(days=30))                # távoli „most”: minden felülvizsgált kártya esedékes lenne
        # a dolgozat ekkor már lezárult → csak az esedékes szám érdekes
        l = osszesit.lista(a, (MOST + timedelta(days=30)).date())
        self.assertEqual(l["dolgozatok"], [])


class TervReszletekTest(Alap):
    def test_naptari_blokk_es_javaslat_a_terv_napjan(self):
        self.al.modosit(lambda m: m["esemenyek"].append(ev("t1", "TAN", "2026-10-05T17:00:00+02:00", "2026-10-05T18:00:00+02:00", "Matek gyakorlás")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        a = self.adatok()
        az = azon(a)
        with szemelyes_db.iro(self.cfg) as c:
            c.execute("INSERT INTO naptar_javaslat (forras, azon, nap, kezd, veg, perc, cim, dolgozat, letrehozva) "
                      "VALUES ('felkeszultseg', ?, '2026-10-04', '2026-10-04T17:00:00+02:00', '2026-10-04T18:00:00+02:00', 60, 'x', ?, 'ma')",
                      (az + "|2026-10-04", az))
        r = osszesit.reszlet(self.adatok(), az)
        nap = {n["nap"]: n for n in r["terv"]["napok"]}
        self.assertEqual([b["cim"] for b in nap["2026-10-05"]["naptar"]], ["Matek gyakorlás"])
        self.assertEqual(nap["2026-10-04"]["naptar"], [])
        self.assertEqual(nap["2026-10-04"]["javaslat"]["allapot"], "uj")
        self.assertIsNone(nap["2026-10-05"]["javaslat"])

    def test_masik_tantargy_blokkja_nem_latszik(self):
        self.al.modosit(lambda m: m["esemenyek"].append(ev("t2", "TAN", "2026-10-05T17:00:00+02:00", "2026-10-05T18:00:00+02:00", "Irodalom olvasás")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        a = self.adatok()
        r = osszesit.reszlet(a, azon(a))
        self.assertTrue(all(n["naptar"] == [] for n in r["terv"]["napok"]))


class KotesNelkulTest(Alap):
    ESEMENYEK = ESEMENYEK + [ev("d2", "HAT", "2026-10-09T10:00:00+02:00", "2026-10-09T10:45:00+02:00", "Fizika dolgozat")]

    def test_felkeszulesi_jegyzet_nelkuli_dolgozat(self):
        a = self.adatok()
        d = {x["cim"]: x for x in osszesit.lista(a, MOST.date())["dolgozatok"]}
        self.assertIsNone(d["Fizika dolgozat"]["jegyzet"])
        self.assertEqual(d["Fizika dolgozat"]["temak_db"], 0)
        r = osszesit.reszlet(self.adatok(), d["Fizika dolgozat"]["azon"])
        self.assertEqual(r["temak"], [])
        self.assertIn("Nincs téma", r["terv"]["uzenet"])
        self.assertTrue(any("nincs felkészülési jegyzet" in f for f in r["figyelmeztetesek"]))


class LezartTest(Alap):
    def test_lezart_dolgozat_nincs_terv_nincs_kilatas(self):
        a = self.adatok(MOST + timedelta(days=5))
        r = osszesit.reszlet(a, a.dolgozatok()[0]["azon"])
        self.assertEqual(r["terv"]["napok"], [])
        self.assertEqual(r["terv"]["uzenet"], "A dolgozat már lezárult.")
        self.assertTrue(all(t["kilatas"] is None for t in r["temak"]))


class NemBiztosKotesTest(Alap):
    FAJLOK = {k.replace("2026-10-07 - Matematika", "2026-10-06 - Matematika"): v for k, v in Alap.FAJLOK.items()}

    def test_athelyezve_kotes_figyelmeztetes(self):
        a = self.adatok()
        r = osszesit.reszlet(a, azon(a))
        self.assertEqual(r["kotes"]["fok"], "athelyezve")
        self.assertTrue(any("nem biztos" in f for f in r["figyelmeztetesek"]))


if __name__ == "__main__":
    unittest.main()


class KozosTervFigyelmeztetesTest(Alap):
    """CX-009: a közös terv a többi dolgozatot is értékeli; azok figyelmeztetései nem kerülhetnek ennek a dolgozatnak a
    `figyelmeztetesek` listájába, és a közös terv explicit mezőben (`Adatok.kozos_tervek`) gyorsítótárazódik."""
    FIZ = "X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-09 - Fizika.md"
    ESEMENYEK = ESEMENYEK + [ev("d2", "HAT", "2026-10-09T10:00:00+02:00", "2026-10-09T10:45:00+02:00", "Fizika dolgozat")]
    FAJLOK = {**Alap.FAJLOK,
              FIZ: "---\nTags:\n  - Active-recall\nSource:\nStatus:\nNN:\n  - \"[[Nincs ilyen fizika téma]]\"\nCanvas:\n---\n# Készülés\n"}

    def _azon(self, a, cim):
        return next(d["azon"] for d in a.dolgozatok() if d["cim"] == cim)

    def test_a_masik_dolgozat_figyelmeztetese_nem_szivarog_at(self):
        a = self.adatok()
        fiz = osszesit.reszlet(a, self._azon(a, "Fizika dolgozat"))
        self.assertTrue(any("Nincs ilyen fizika téma" in f for f in fiz["figyelmeztetesek"]), fiz["figyelmeztetesek"])
        a = self.adatok()
        self.assertIsNone(a.kozos_tervek)
        r = osszesit.reszlet(a, self._azon(a, "Matek témazáró"))
        self.assertIsNotNone(a.kozos_tervek)
        self.assertFalse(any("Nincs ilyen fizika téma" in f for f in r["figyelmeztetesek"]), r["figyelmeztetesek"])
        self.assertTrue(r["terv"]["napok"])

    def test_a_kozos_terv_egyszer_szamolodik(self):
        a = self.adatok()
        d = next(x for x in a.dolgozatok() if x["cim"] == "Matek témazáró")
        e = osszesit.ertekel(a, d)
        elso = osszesit.terv_szamolas(a, d, e)
        with unittest.mock.patch.object(osszesit, "ertekel", side_effect=AssertionError("újraszámolva")):
            self.assertEqual(osszesit.terv_szamolas(a, d, e), elso)
