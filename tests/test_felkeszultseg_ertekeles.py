"""A szöveges értékelés tesztjei (C28b; `core/felkeszultseg/ertekeles.py`, `api.ertekeles_valasz`): a tények előre formázottak, útvonal
nélküliek; a modell kimenete a szám-kapun át megy (csak a tényekben álló szám szerepelhet); az újrapróbálkozás; D9 (kalibrált modell
vagy próba); a végpont nem ír. Hamis (szkriptelt) modellel — modellt a teszt nem tölt be."""
import hashlib
import os
import unittest
from datetime import date, timedelta, timezone
from pathlib import Path

from core import kereses_api
from core.felkeszultseg import adat, api, ertekeles, osszesit
from core.utvonalak import HttpError
from tests.felkeszultseg_segedek import Alap, DOLGOZAT_NAP, FELK, MOST, T1, T2

UTC = timezone.utc
TENYEK = "Felkészültség: 62%. Kilátás: 55%. 3 / 5 témára van mért adat. Utolsó tanulás: 3 napja. 45 perc, október 7., 4,5 pont."


class Kapu(unittest.TestCase):
    def test_a_tenyekben_allo_szam_megengedett(self):
        ok, tiltott = ertekeles.kapu("Összesen 62% a felkészültséged, a kilátás 55%; 3 napja tanultál, 45 perc volt, október 7-én írod.", TENYEK)
        self.assertEqual((ok, tiltott), (True, []))

    def test_uj_szam_tiltott_a_szamolas_is(self):
        ok, tiltott = ertekeles.kapu("Ha még 20 percet tanulsz, 70%-ra emelkedhet; 62 − 55 = 7 pont a különbség.", TENYEK)
        self.assertFalse(ok)
        self.assertEqual(set(tiltott), {"20", "70"})            # a 7 az „október 7.” miatt szerepel a tényekben

    def test_tizedes_vesszo_es_pont(self):
        self.assertTrue(ertekeles.kapu("4,5 pont", TENYEK)[0])
        self.assertTrue(ertekeles.kapu("4.5 pont", TENYEK)[0])
        self.assertFalse(ertekeles.kapu("4,6 pont", TENYEK)[0])

    def test_szam_szavak_csak_ha_az_ertekuk_a_tenyekben_van(self):
        self.assertFalse(ertekeles.kapu("Még négy napod van.", TENYEK)[0])
        self.assertTrue(ertekeles.kapu("Három napja nem tanultál.", TENYEK)[0], "3 a tényekben")
        self.assertEqual(ertekeles.kapu("Húsz perc elég lenne.", TENYEK), (False, ["húsz"]))
        self.assertTrue(ertekeles.kapu("Egy témával kezdd, a hét végén ismételj.", TENYEK)[0], "az „egy” és a „hét” nem szám")

    def test_felsorolasjelolo_nem_szam(self):
        self.assertTrue(ertekeles.kapu("1. Ismételj.\n2) Kvízezz.\n- Pihenj.", TENYEK)[0])
        self.assertFalse(ertekeles.kapu("Az 1. helyen a logaritmus áll, 9 kártyával.", TENYEK)[0])

    def test_a_szamjegy_a_szo_belsejeben_is_szamit(self):
        self.assertFalse(ertekeles.kapu("a 99%-os cél", TENYEK)[0])


class Lanc(unittest.TestCase):
    T = {"szoveg": TENYEK, "szam_van": True, "temak": [], "kulcs": "k"}

    def hivo(self, *valaszok):
        hivasok = []
        it = iter(valaszok)

        def h(prompt, max_tokens):
            hivasok.append((prompt, max_tokens))
            return next(it)
        h.hivasok = hivasok
        return h

    def test_jo_szoveg_elsore(self):
        h = self.hivo("A felkészültséged 62%, a kilátás 55%.")
        r = ertekeles.futtat(h, self.T)
        self.assertEqual((r["allapot"], r["probalkozas"], r["tiltott"]), ("kesz", 1, []))
        self.assertEqual(h.hivasok[0][1], ertekeles.MAX_TOKEN)
        self.assertIn(TENYEK, h.hivasok[0][0])
        self.assertNotIn("FIGYELEM", h.hivasok[0][0])

    def test_buko_szoveg_utan_egy_ujrapróbalkozas_a_tiltott_szamokkal(self):
        h = self.hivo("Kb. 80%-os vagy.", "A felkészültséged 62%.")
        r = ertekeles.futtat(h, self.T)
        self.assertEqual((r["allapot"], r["probalkozas"]), ("kesz", 2))
        self.assertIn("FIGYELEM", h.hivasok[1][0])
        self.assertIn("80", h.hivasok[1][0])

    def test_ket_buko_valasz_utan_nincs_szoveg(self):
        h = self.hivo("80%", "90%")
        r = ertekeles.futtat(h, self.T)
        self.assertEqual((r["allapot"], r["szoveg"], r["probalkozas"], r["tiltott"]), ("kapu_bukott", None, 2, ["90"]))

    def test_ures_valasz(self):
        r = ertekeles.futtat(self.hivo("  \n "), self.T)
        self.assertEqual((r["allapot"], r["szoveg"], r["probalkozas"]), ("ures", None, 1))

    def test_tokenfolyam_es_gondolkodas_maradek(self):
        r = ertekeles.futtat(self.hivo(iter(["<think>számolok 99</think>", "A felkészültséged ", "**62%**."])), self.T)
        self.assertEqual((r["allapot"], r["szoveg"]), ("kesz", "A felkészültséged 62%."))

    def test_a_hivo_hibaja_tovabbmegy(self):
        def rossz(prompt, max_tokens):
            raise OSError("nincs worker")
        with self.assertRaises(OSError):
            ertekeles.futtat(rossz, self.T)

    def test_a_prompt_nem_enged_szamolast(self):
        p = ertekeles.prompt(self.T)
        self.assertIn("Nem számolhatsz", p)
        self.assertIn("ADATOK", p)
        self.assertTrue(p.rstrip().endswith("ÉRTÉKELÉS:"))


class AlVault:
    def __init__(self, gyoker: Path):
        self.gyoker = gyoker

    def read(self, rp: str) -> dict:
        return {"ut": rp, "tartalom": (self.gyoker / rp).read_text(encoding="utf-8")}


class AlApp:
    def __init__(self, cfg, index, vault):
        self.cfg, self.index, self.vault = cfg, index, vault


class TenyekEsVegpont(Alap):
    def setUp(self):
        super().setUp()
        self.t0 = MOST.astimezone(UTC) - timedelta(days=10)
        self.kartyak(T1, ("c-00000001", "Mi a hatvány?", "ismételt szorzás"), ("c-00000002", "Mi a 2^3?", "8"),
                     ("c-00000003", "Mi a 0^0?", "nem értelmezett"), ("c-00000004", "Új kártya", "válasz"), most=self.t0)
        self.kartyak(T2, ("c-00000011", "Mi a gyök?", "fordított hatvány"), most=self.t0)
        for azon, jegyek in (("c-00000001", (3, 3)), ("c-00000002", (4,)), ("c-00000003", (1, 3)), ("c-00000011", (3,))):
            for i, j in enumerate(jegyek):
                self.valasz(azon, j, self.t0 + timedelta(days=i * 2))
        self.aktiv("2026-10-01", T1, 1800)
        self.app = AlApp(self.cfg, self.ix, AlVault(self.v))
        self.addCleanup(lambda: kereses_api._szolgalatok.pop(self.app, None))
        self.azon = self.adatok().dolgozatok()[0]["azon"]
        self.reszlet = osszesit.reszlet(self.adatok(), self.azon)

    def modell(self, szoveg):
        hivasok = []

        def m(prompt, max_tokens):
            hivasok.append(prompt)
            return szoveg(prompt) if callable(szoveg) else szoveg
        m.hivasok = hivasok
        return m

    def lenyomat(self):
        ki = {}
        for d, mappak, fajlok in os.walk(self.v):
            mappak[:] = [x for x in mappak if x != ".obsidian"]
            for f in fajlok:
                p = Path(d) / f
                ki[str(p)] = hashlib.sha1(p.read_bytes()).hexdigest()
        return ki

    # ---- a tények

    def test_a_tenyek_utvonal_nelkuliek_es_a_szamok_elore_formazottak(self):
        t = ertekeles.tenyek(self.reszlet, self.adatok().ma)
        self.assertTrue(t["szam_van"])
        sz = t["szoveg"]
        self.assertNotIn("M06 - Exponenciális", sz)
        self.assertNotIn("/", sz.replace(" / ", ""))                       # a „3 / 5 témára” kivételével nincs perjel (útvonal)
        self.assertNotIn(".md", sz)
        for nev in ("01 - Hatvány", "02 - Gyökvonás", "03 - Logaritmus"):
            self.assertIn(nev, sz)
        self.assertIn("október 7.", sz)
        self.assertIn("4 nap múlva", sz)
        self.assertRegex(sz, r"Felkészültség: \d+%")
        self.assertIn("kalibrálatlan", sz)
        self.assertIn("nincs adat", sz)                                    # a Logaritmus témára nincs mért tudás
        self.assertNotIn("\n- /", sz)
        self.assertEqual(len(t["kulcs"]), 16)

    def test_a_kulcs_a_tenyek_tartalmatol_fugg(self):
        a = ertekeles.tenyek(self.reszlet, self.adatok().ma)["kulcs"]
        self.assertEqual(a, ertekeles.tenyek(self.reszlet, self.adatok().ma)["kulcs"])
        self.valasz("c-00000004", 3, MOST.astimezone(UTC) - timedelta(hours=3))
        ujra = osszesit.reszlet(self.adatok(), self.azon)
        self.assertNotEqual(a, ertekeles.tenyek(ujra, self.adatok().ma)["kulcs"])
        self.assertEqual(self.reszlet["ertekeles_kulcs"], a)

    def test_az_ertekeles_kulcs_a_reszletben(self):
        self.assertEqual(self.reszlet["ertekeles_kulcs"], ertekeles.tenyek(self.reszlet, self.adatok().ma)["kulcs"])

    def test_mert_szam_nelkul_nincs_szam_van(self):
        class Ures(Alap):
            pass
        t = Ures()
        t.setUp()
        self.addCleanup(t.doCleanups)
        r = osszesit.reszlet(t.adatok(), t.adatok().dolgozatok()[0]["azon"])
        self.assertIsNone(r["szam"])
        te = ertekeles.tenyek(r, t.adatok().ma)
        self.assertFalse(te["szam_van"])
        self.assertIn("nincs szám", te["szoveg"])

    # ---- a végpont törzse

    def jo(self, prompt):
        return "A felkészültséged most " + ertekeles.tenyek(self.reszlet, self.adatok().ma)["szoveg"].split("Felkészültség: ")[1].split(" ")[0] \
            + ". A leggyengébb témákra érdemes időt szánni."

    def test_kalibralt_modell_eles_szoveg(self):
        m = self.modell(self.jo)
        kereses_api.kotes(self.app, modell=m, kalibralt=True)
        elotte = self.lenyomat()
        r = api.ertekeles_valasz(self.app, {"azon": self.azon, "datum": "2026-10-03"})
        self.assertEqual((r["allapot"], r["proba"], r["kalibralt"], r["probalkozas"]), ("kesz", False, True, 1))
        self.assertTrue(r["szoveg"].startswith("A felkészültséged most"))
        self.assertEqual(r["kulcs"], self.reszlet["ertekeles_kulcs"])
        self.assertEqual(r["prompt_verzio"], ertekeles.PROMPT_VERZIO)
        self.assertEqual(len(m.hivasok), 1)
        self.assertEqual(self.lenyomat(), elotte, "a szöveges értékelés a vaultba nem ír")

    def test_nem_kalibralt_modell_proba(self):
        kereses_api.kotes(self.app, modell=self.modell(self.jo), kalibralt=False)
        r = api.ertekeles_valasz(self.app, {"azon": self.azon, "datum": "2026-10-03"})
        self.assertEqual((r["proba"], r["kalibralt"], r["allapot"]), (True, False, "kesz"))

    def test_a_worker_proba_jelzese_is_proba(self):
        m = self.modell(self.jo)
        m.proba, m.nev = True, "qwen-proba"
        kereses_api.kotes(self.app, modell=m, kalibralt=True)
        r = api.ertekeles_valasz(self.app, {"azon": self.azon, "datum": "2026-10-03"})
        self.assertEqual((r["proba"], r["modell"]), (True, "qwen-proba"))

    def test_kalibralt_modell_nelkul_503(self):
        with self.assertRaises(HttpError) as cm:
            api.ertekeles_valasz(self.app, {"azon": self.azon, "datum": "2026-10-03"})
        self.assertEqual(cm.exception.code, 503)
        self.assertIn("kalibrált", str(cm.exception))

    def test_nincs_mert_adat_a_modell_nem_fut(self):
        class Ures(Alap):
            pass
        t = Ures()
        t.setUp()
        self.addCleanup(t.doCleanups)
        app = AlApp(t.cfg, t.ix, AlVault(t.v))
        self.addCleanup(lambda: kereses_api._szolgalatok.pop(app, None))
        m = self.modell("x 99%")
        kereses_api.kotes(app, modell=m, kalibralt=True)
        r = api.ertekeles_valasz(app, {"azon": t.adatok().dolgozatok()[0]["azon"], "datum": "2026-10-03"})
        self.assertEqual((r["allapot"], r["szoveg"], m.hivasok), ("nincs_mert_adat", None, []))
        self.assertIn("no measured card or quiz data", r["uzenet"])

    def test_hamis_szam_ketszer_a_szoveg_nem_jut_ki(self):
        m = self.modell("Biztosan 97%-os leszel.")
        kereses_api.kotes(self.app, modell=m, kalibralt=True)
        r = api.ertekeles_valasz(self.app, {"azon": self.azon, "datum": "2026-10-03"})
        self.assertEqual((r["allapot"], r["szoveg"], r["probalkozas"]), ("kapu_bukott", None, 2))
        self.assertIn("97", r["tiltott_szamok"])
        self.assertEqual(len(m.hivasok), 2)
        self.assertIn("assessment is hidden", r["uzenet"])

    def test_hibas_kerdesek(self):
        kereses_api.kotes(self.app, modell=self.modell(self.jo), kalibralt=True)
        for body, kod in (({}, 400), ({"azon": 5}, 400), ({"azon": self.azon, "datum": 5}, 400), ({"azon": "nincs"}, 404),
                          ({"azon": self.azon, "datum": "2026-10-03", "modell": "nincs-ilyen-modell"}, 400)):
            with self.subTest(body):
                with self.assertRaises(HttpError) as cm:
                    api.ertekeles_valasz(self.app, {"datum": "2026-10-03", **body})
                self.assertEqual(cm.exception.code, kod)

    def test_a_modell_kapcsolat_hibaja_503(self):
        from core.modell.kliens import KliensHiba

        def rossz(prompt, max_tokens):
            raise KliensHiba(409, "nincs kalibrált modell")
        kereses_api.kotes(self.app, modell=rossz, kalibralt=True)
        with self.assertRaises(HttpError) as cm:
            api.ertekeles_valasz(self.app, {"azon": self.azon, "datum": "2026-10-03"})
        self.assertEqual(cm.exception.code, 503)


if __name__ == "__main__":
    unittest.main()
