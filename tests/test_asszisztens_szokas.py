"""Az Asszisztens szokásminta-javaslata (C30a; CHATKALAUZ C30 3. pont): a hét napja × tantárgy a `tr_aktiv`-ból, legfeljebb heti
egy javaslat (újraindítás után is), a küszöb a statisztikából. Álgyökéren, a valódi `var/`-hoz nem nyúl."""
import contextlib
import json
import unittest
from datetime import date, datetime, timedelta

from core import tracker, vezerlo
from core.asszisztens import szokas
from core.asszisztens.allapot import Allapot
from core.asszisztens.beallitasok import beallitasok
from core.asszisztens.statisztika import Statisztika
from core.utvonalak import HttpError
from tests.helpers import alg_core, tmpdir

SZERDA = date(2026, 10, 7)                  # szerda
MATEK = "M01 - Matek/Függvények.md"
MATEK2 = "M01 - Matek/Sorozatok.md"
FIZIKA = "F01 - Fizika/Mozgás.md"


def sor(nap: date, ut: str, perc: int, tantargy: str = "Mathematics") -> tuple:
    return (nap.isoformat(), ut, tantargy, perc * 60)


def ora_sor(nap: date, ora: int, perc: int, tantargy: str = "Mathematics") -> tuple:
    """Egy `tr_aktiv_ora` sor (C30b): `(nap ISO, óra, tantárgy, mp)`."""
    return (nap.isoformat(), ora, tantargy, perc * 60)


def szerdak_ora(db: int, ora: int, *, perc: int = 30, tantargy: str = "Mathematics", kezdet: int = 1) -> list[tuple]:
    return [ora_sor(SZERDA - timedelta(days=7 * k), ora, perc, tantargy) for k in range(kezdet, kezdet + db)]


def szerdak(db: int, *, perc: int = 30, ut: str = MATEK, tantargy: str = "Mathematics", kezdet: int = 1) -> list[tuple]:
    """`db` darab korábbi szerda (a mai előtt `kezdet`-edikkel kezdve)."""
    return [sor(SZERDA - timedelta(days=7 * k), ut, perc, tantargy) for k in range(kezdet, kezdet + db)]


class _Cfg:
    """Álkonfig: az `[asszisztens] tantargy_nevek` a munkatér adata (a termék üresen szállítja; a fejlesztő szótára a `v2-kompat` presetben
    van, `tests/preset_v2/test_asszisztens_v2.py`), itt egy semleges, kifejezett térkép."""
    NEVEK = {"Mathematics": "matematika", "Physics": "fizika"}

    def section(self, *a):
        return {"tantargy_nevek": dict(self.NEVEK)} if a == ("asszisztens",) else {}


class TisztaTest(unittest.TestCase):
    B = beallitasok(_Cfg())

    def j(self, sorok, ma=SZERDA, szorzo=1.0):
        return szokas.javaslat(sorok, ma, self.B, szorzo)

    def test_hat_a_nyolc_szerdabol_javaslat(self):
        j = self.j(szerdak(6))
        self.assertEqual((j["tantargy"], j["hit"], j["het"]), ("Mathematics", 6, 8))
        self.assertEqual(j["nap_neve"], "szerda")
        self.assertEqual(j["atlag_perc"], 30)
        self.assertIn("Szerdánként", j["szoveg"])
        self.assertIn("6 szerdán", j["szoveg"])

        self.assertIn("matematika", j["szoveg"])
        self.assertEqual(j["legutobbi_ut"], MATEK)

    def test_a_nap_neve_ragozva(self):
        csut = SZERDA + timedelta(days=1)
        j = self.j([sor(csut - timedelta(days=7 * k), MATEK, 30) for k in range(1, 7)], ma=csut)
        self.assertIn("Csütörtökönként", j["szoveg"])
        self.assertIn("6 csütörtökön", j["szoveg"])

    def test_kevés_hét_nincs_javaslat(self):
        self.assertIsNone(self.j(szerdak(3)))

    def test_a_min_het_a_szorzoval_nő(self):
        self.assertIsNotNone(self.j(szerdak(4)))
        self.assertIsNone(self.j(szerdak(5), szorzo=1.5))           # ceil(4 × 1,5) = 6
        self.assertIsNotNone(self.j(szerdak(6), szorzo=1.5))

    def test_rovid_napok_nem_szamitanak(self):
        self.assertIsNone(self.j(szerdak(8, perc=19)))
        self.assertIsNotNone(self.j(szerdak(8, perc=20)))

    def test_egy_napon_tobb_jegyzet_osszeadodik(self):
        sorok = szerdak(5, perc=12) + szerdak(5, perc=12, ut=MATEK2)
        self.assertIsNotNone(self.j(sorok))

    def test_mas_hetnapok_nem_szamitanak(self):
        sorok = [sor(SZERDA - timedelta(days=7 * k + 1), MATEK, 60) for k in range(1, 9)]       # csütörtökök
        self.assertIsNone(self.j(sorok))

    def test_ablakon_kivuli_het_nem_szamit(self):
        self.assertIsNone(self.j(szerdak(6, kezdet=9)))

    def test_ma_mar_tanult_nincs_javaslat(self):
        self.assertIsNone(self.j(szerdak(6) + [sor(SZERDA, MATEK, 25)]))
        self.assertIsNotNone(self.j(szerdak(6) + [sor(SZERDA, MATEK, 5)]))

    def test_egyeb_kimarad(self):
        self.assertIsNone(self.j(szerdak(8, tantargy="Egyéb")))

    def test_tobb_tantargybol_a_tobb_alkalommal_nyer(self):
        sorok = szerdak(5, tantargy="Mathematics") + szerdak(7, ut=FIZIKA, tantargy="Physics")
        self.assertEqual(self.j(sorok)["tantargy"], "Physics")

    def test_egyenlo_alkalomnal_a_hosszabb_nyer(self):
        sorok = szerdak(5, perc=30) + szerdak(5, perc=50, ut=FIZIKA, tantargy="Physics")
        self.assertEqual(self.j(sorok)["tantargy"], "Physics")

    def test_ismeretlen_tantargy_nev_marad(self):
        j = self.j(szerdak(6, tantargy="Kémia"))
        self.assertIn("Kémia", j["szoveg"])

    def test_legutobbi_jegyzet_a_legkozelebbi_napi(self):
        sorok = szerdak(5, ut=MATEK, kezdet=2) + szerdak(1, ut=MATEK2, kezdet=1)
        self.assertEqual(self.j(sorok)["legutobbi_ut"], MATEK2)


class NapszakTisztaTest(unittest.TestCase):
    """C30b (K205 (a)): a napszak a hét napja × tantárgy mintát finomítja („szerda este matek”), külön javaslatot nem ad."""
    B = TisztaTest.B

    def j(self, sorok, ora_sorok, ma=SZERDA, szorzo=1.0, b=None):
        return szokas.javaslat(sorok, ma, b or self.B, szorzo, ora_sorok)

    def test_a_napszakok_hatarai(self):
        egy = {0: "éjszaka", 4: "éjszaka", 5: "reggel", 8: "reggel", 9: "délelőtt", 11: "délelőtt", 12: "délután", 16: "délután",
               17: "este", 21: "este", 22: "éjszaka", 23: "éjszaka"}
        for ora, nev in egy.items():
            self.assertEqual(szokas.napszak_neve(ora), nev, ora)
        self.assertEqual({szokas.napszak_neve(o) for o in range(24)}, {n for n, _, _ in szokas.NAPSZAKOK})

    def test_szerda_este_matek(self):
        j = self.j(szerdak(6), szerdak_ora(6, 19))
        self.assertEqual((j["napszak"], j["napszak_hit"]), ("este", 6))
        self.assertIn("Szerdánként általában este tanulsz (tantárgy: matematika)", j["szoveg"])
        self.assertIn("ebből 6 este", j["szoveg"])
        self.assertTrue(j["szoveg"].endswith("Ma még nem."))

    def test_a_napszak_nelkuli_javaslat_valtozatlan(self):
        alap = self.j(szerdak(6), None)
        self.assertIsNone(alap["napszak"])
        self.assertIsNone(alap["napszak_hit"])
        self.assertNotIn("este", alap["szoveg"])
        self.assertIn("Szerdánként általában tanulsz (tantárgy: matematika)", alap["szoveg"])
        # üres és kevés napszak-adat ugyanezt adja
        self.assertEqual(self.j(szerdak(6), [])["szoveg"], alap["szoveg"])
        self.assertEqual(self.j(szerdak(6), szerdak_ora(3, 19))["szoveg"], alap["szoveg"])

    def test_a_napszak_nem_ad_kulon_javaslatot(self):
        self.assertIsNone(self.j(szerdak(3), szerdak_ora(6, 19)))                   # a hét napja × tantárgy minta nem teljesül
        self.assertIsNone(self.j(szerdak(6) + [sor(SZERDA, MATEK, 25)], szerdak_ora(6, 19)))     # ma már tanult

    def test_a_tobb_alkalmas_napszak_nyer_dontetlennel_a_tobb_mp_majd_a_sorrend(self):
        delutan, este = szerdak_ora(4, 15, perc=25), szerdak_ora(3, 19, perc=30)
        self.assertEqual(self.j(szerdak(6), delutan + este)["napszak"], "délután")        # 4 > 3
        delutan, este = szerdak_ora(4, 15, perc=25, kezdet=1), szerdak_ora(4, 19, perc=30, kezdet=5)
        self.assertEqual(self.j(szerdak(8, perc=30), delutan + este)["napszak"], "este")       # 4 = 4, több mp
        a, b_ = szerdak_ora(4, 8, perc=30, kezdet=1), szerdak_ora(4, 13, perc=30, kezdet=5)
        self.assertEqual(self.j(szerdak(8), a + b_)["napszak"], "reggel")                       # teljes döntetlen: a korábbi napszak

    def test_az_azonos_napszakba_eso_orak_osszeadodnak(self):
        sorok = [ora_sor(SZERDA - timedelta(days=7 * k), o, 12) for k in range(1, 7) for o in (17, 18)]         # 2 × 12 perc este
        self.assertEqual(self.j(szerdak(6, perc=24), sorok)["napszak"], "este")
        sorok = [ora_sor(SZERDA - timedelta(days=7 * k), o, 15) for k in range(1, 7) for o in (14, 19)]          # 15 perc délután + 15 este
        self.assertIsNone(self.j(szerdak(6), sorok)["napszak"])                                                 # egyik sem éri el a 20 percet

    def test_az_ejfel_utani_ora_az_ejszakae(self):
        self.assertEqual(self.j(szerdak(6), szerdak_ora(6, 1))["napszak"], "éjszaka")
        self.assertEqual(self.j(szerdak(6), szerdak_ora(6, 23))["napszak"], "éjszaka")

    def test_csak_a_tantargy_azonos_hetnapjai_szamitanak(self):
        masik = [ora_sor(SZERDA - timedelta(days=7 * k + 1), 19, 60) for k in range(1, 9)]                       # csütörtökök
        self.assertIsNone(self.j(szerdak(6), masik)["napszak"])
        self.assertIsNone(self.j(szerdak(6), szerdak_ora(6, 19, tantargy="Physics"))["napszak"])
        self.assertIsNone(self.j(szerdak(6), szerdak_ora(6, 19, kezdet=9))["napszak"])                           # az ablakon kívüli hetek

    def test_a_kuszob_szorzoja_a_napszakra_is_igaz(self):
        self.assertIsNotNone(self.j(szerdak(6), szerdak_ora(5, 19), szorzo=1.5))                                # a minta megvan (6 nap)…
        self.assertIsNone(self.j(szerdak(6), szerdak_ora(5, 19), szorzo=1.5)["napszak"])                         # …a napszak csak 5 napon: kevés (ceil(4×1,5) = 6)
        self.assertEqual(self.j(szerdak(6), szerdak_ora(6, 19), szorzo=1.5)["napszak"], "este")

    def test_a_beallitas_kikapcsolja(self):
        b = {**self.B, "szokas_napszak": False}
        self.assertIsNone(self.j(szerdak(6), szerdak_ora(6, 19), b=b)["napszak"])


class SzolgaltatasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.ido = datetime(2026, 10, 7, 9, 0)
        self.ujra()

    def ujra(self):
        """Új példányok ugyanazon az adaton: a core újraindulása."""
        self.tr = tracker.Tracker(self.cfg, mikor=lambda: self.ido)
        self.st = Statisztika(self.cfg, self.tr)
        self.sz = szokas.Szokasok(self.cfg, self.tr, self.st, Allapot(self.cfg), mikor=lambda: self.ido)

    def adat(self, sorok):
        with self.tr._iro() as c:
            c.executemany("INSERT INTO tr_aktiv (nap, ut, tantargy, mp) VALUES (?,?,?,?) "
                          "ON CONFLICT(nap, ut) DO UPDATE SET mp = mp + excluded.mp", [(n, u, t, m) for n, u, t, m in sorok])

    def adat_ora(self, sorok):
        with self.tr._iro() as c:
            c.executemany("INSERT INTO tr_aktiv_ora (nap, ora, tantargy, mp) VALUES (?,?,?,?) "
                          "ON CONFLICT(nap, ora, tantargy) DO UPDATE SET mp = mp + excluded.mp", sorok)

    def allapotfajl(self):
        return self.cfg.path("state") / "asszisztens.json"

    def test_javaslat_es_persistalas(self):
        self.adat(szerdak(6))
        j = self.sz.aktualis()
        self.assertEqual(j["tantargy"], "Mathematics")
        self.assertEqual(j["allapot"], "uj")
        self.assertTrue(self.allapotfajl().exists())
        self.ujra()                                      # újraindulás: ugyanaz a javaslat, nem új
        self.assertEqual(self.sz.aktualis()["azon"], j["azon"])

    def test_nincs_minta_nincs_allapotfajl_es_nem_fogy_el_a_het(self):
        self.assertIsNone(self.sz.aktualis())
        self.assertFalse(self.allapotfajl().exists())
        self.adat(szerdak(6))
        self.assertIsNotNone(self.sz.aktualis())

    def test_dontes_utan_a_het_vegeig_nincs_ujabb(self):
        self.adat(szerdak(6) + [sor(SZERDA - timedelta(days=7 * k + 1), FIZIKA, 60, "Physics") for k in range(1, 9)])
        j = self.sz.aktualis()
        self.assertTrue(self.sz.dontes(j["azon"], "elutasit")["ok"])
        self.assertIsNone(self.sz.aktualis())
        self.ujra()
        self.assertIsNone(self.sz.aktualis())

    def test_a_dontes_a_statisztikaba_kerul(self):
        self.adat(szerdak(6))
        j = self.sz.aktualis()
        self.sz.dontes(j["azon"], "elfogad")
        self.assertEqual(self.st.osszesit()["fajtak"]["szokas"]["elfogad"], 1)

    def test_ismeretlen_azon_es_ketszeri_dontes(self):
        self.adat(szerdak(6))
        j = self.sz.aktualis()
        with self.assertRaises(HttpError) as e:
            self.sz.dontes("szokas:masik", "elfogad")
        self.assertEqual(e.exception.code, 404)
        self.sz.dontes(j["azon"], "elfogad")
        with self.assertRaises(HttpError) as e:
            self.sz.dontes(j["azon"], "elfogad")
        self.assertEqual(e.exception.code, 409)
        with self.assertRaises(HttpError) as e:
            self.sz.dontes(j["azon"], "talan")
        self.assertEqual(e.exception.code, 400)

    def test_figyelmen_kivul_hagyva_a_javaslat_a_nap_vegen_lejar_es_a_het_nem_ad_ujat(self):
        self.adat(szerdak(6) + [sor(SZERDA - timedelta(days=7 * k + 1), FIZIKA, 60, "Physics") for k in range(1, 9)])
        self.assertIsNotNone(self.sz.aktualis())
        self.ido += timedelta(days=1)                   # csütörtök, ugyanaz az ISO-hét
        self.assertIsNone(self.sz.aktualis())

    def test_kovetkezo_heten_uj_javaslat(self):
        self.adat(szerdak(6))
        j = self.sz.aktualis()
        self.sz.dontes(j["azon"], "elfogad")
        self.ido += timedelta(days=7)
        j2 = self.sz.aktualis()
        self.assertIsNotNone(j2)
        self.assertNotEqual(j2["azon"], j["azon"])

    def test_kapcsolok_alatt_nincs_javaslat_es_nincs_allapot(self):
        self.adat(szerdak(6))
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False})
        self.assertIsNone(self.sz.aktualis())
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": True, "tracker": False})
        self.assertIsNone(self.sz.aktualis())
        self.assertFalse(self.allapotfajl().exists())

    def test_nema_kuszobnel_nincs_javaslat(self):
        self.adat(szerdak(6))
        for _ in range(25):
            self.st.rogzit("szokas", "elutasit")
        self.assertIsNone(self.sz.aktualis())

    def test_szigoru_kuszobnel_tobb_het_kell(self):
        self.adat(szerdak(5))
        self.assertIsNotNone(self.sz.aktualis())
        self.allapotfajl().unlink()
        for _ in range(1):
            self.st.rogzit("szokas", "elfogad")
        for _ in range(14):
            self.st.rogzit("szokas", "elutasit")        # arány < 0,15 → szigorú: min_het 6
        self.assertIsNone(self.sz.aktualis())

    def test_szerda_este_matek_a_tr_aktiv_orabol_es_persistalodik(self):
        self.adat(szerdak(6))
        self.adat_ora(szerdak_ora(6, 19))
        j = self.sz.aktualis()
        self.assertEqual((j["napszak"], j["napszak_hit"]), ("este", 6))
        self.assertIn("általában este tanulsz", j["szoveg"])
        self.ujra()
        self.assertEqual(self.sz.aktualis()["napszak"], "este")                 # újraindulás után ugyanaz (az állapotfájlból)

    def test_napszak_adat_nelkul_a_c30a_javaslat(self):
        self.adat(szerdak(6))
        j = self.sz.aktualis()
        self.assertIsNone(j["napszak"])
        self.assertNotIn("este", j["szoveg"])

    def test_4_es_sema_mellett_az_olvasas_nem_migral_es_nem_dob(self):
        import sqlite3
        from core import szemelyes_db
        self.tr.ut().parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.tr.ut())
        for sql in szemelyes_db.MIGRACIOK[:4]:
            c.executescript(sql)
        c.execute("PRAGMA user_version = 4")
        c.executemany("INSERT INTO tr_aktiv (nap, ut, tantargy, mp) VALUES (?,?,?,?)", [(n, u, t, m) for n, u, t, m in szerdak(6)])
        c.commit()
        c.close()
        j = self.sz.aktualis()
        self.assertEqual(j["tantargy"], "Mathematics")
        self.assertIsNone(j["napszak"])
        with contextlib.closing(sqlite3.connect(self.tr.ut())) as c:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_a_beallitas_kikapcsolja_a_napszakot(self):
        self.cfg.data.setdefault("asszisztens", {})["szokas_napszak"] = False
        self.adat(szerdak(6))
        self.adat_ora(szerdak_ora(6, 19))
        self.assertIsNone(self.sz.aktualis()["napszak"])

    def test_a_tracker_gyujtotte_adat_a_szolgaltatasig_er(self):
        """A teljes út: a tracker `fogad`-ja írja a `tr_aktiv_ora`-t (a mostani órára), a szokásminta olvassa."""
        for k in range(1, 7):
            nap = SZERDA - timedelta(days=7 * k)
            self.ido = datetime(nap.year, nap.month, nap.day, 19, 30)
            self.tr.fogad({"aktiv": [{"ut": MATEK, "mp": 1800}]})
        self.ido = datetime(2026, 10, 7, 9, 0)
        j = self.sz.aktualis()
        self.assertEqual((j["tantargy"], j["napszak"], j["hit"], j["napszak_hit"]), ("Mathematics", "este", 6, 6))

    def test_sertett_allapotfajl_nem_dob(self):
        self.allapotfajl().write_text("{nem json", encoding="utf-8")
        self.adat(szerdak(6))
        self.assertIsNotNone(self.sz.aktualis())
        json.loads(self.allapotfajl().read_text(encoding="utf-8"))


class AllapotTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)

    def test_alapertek_es_atomi_iras(self):
        a = Allapot(self.cfg)
        self.assertEqual(a.olvas(), {"higienia_latva": None, "szokas": None, "hangolas": {}, "muveletek": {}, "kartya_dontesek": {}})
        a.modosit(lambda d: d.update(szokas={"het": "2026-W41"}))
        self.assertEqual(Allapot(self.cfg).olvas()["szokas"], {"het": "2026-W41"})
        self.assertEqual(sorted(p.name for p in a.ut.parent.glob("asszisztens*")), ["asszisztens.json"])

    def test_ismeretlen_kulcs_megmarad(self):
        a = Allapot(self.cfg)
        a.ut.write_text(json.dumps({"szokas": None, "jovobeli": 1}), encoding="utf-8")
        a.modosit(lambda d: d.update(higienia_latva=["x"]))
        self.assertEqual(json.loads(a.ut.read_text(encoding="utf-8"))["jovobeli"], 1)


if __name__ == "__main__":
    unittest.main()
