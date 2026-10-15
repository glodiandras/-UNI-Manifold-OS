"""A naptár (C29): a legacy szabályai (kategória-javaslat, tantárgy, dolgozat/határidő, órarend-kötés), a szinkron az
ál-EventKit segéddel (új/változott/törölt, átnevezés, újra-összekötés, engedély nélkül), a `tr_naptar_blokk` építése.
Ál-segéd és álgyökér: a valódi naptárhoz és a valódi `pos.sqlite`-hoz a teszt nem nyúl."""
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from core import naptar, szemelyes_db
from core.naptar_seged import Seged, SegedHiba
from tests.helpers import alg_core, tmpdir
from tests.naptar_segedek import AlSeged, esemeny as ev, naptar as nt

TZ = timezone(timedelta(hours=2))
MOST = datetime(2026, 10, 3, 12, 0, tzinfo=TZ)

NAPTARAK = [nt("HAT", "Deadlines & Exams"), nt("ORA", "Órarend"), nt("TAN", "Studying"), nt("UNN", "Ünnepnapok"),
            nt("X", "Valami Különös")]
ESEMENYEK = [
    ev("e1", "TAN", "2026-10-05T17:00:00+02:00", "2026-10-05T18:00:00+02:00", "Matek gyakorlás"),
    ev("e2", "TAN", "2026-10-06T00:00:00+02:00", "2026-10-07T00:00:00+02:00", "Tanulós egész nap", egesznap=True),
    ev("e3", "ORA", "2026-10-07T10:00:00+02:00", "2026-10-07T10:45:00+02:00", "Fizika"),
    ev("e4", "HAT", "2026-10-07T10:00:00+02:00", "2026-10-07T10:45:00+02:00", "Témazáró"),
    ev("e5", "UNN", "2026-10-23T00:00:00+02:00", "2026-10-24T00:00:00+02:00", "Nemzeti ünnep", egesznap=True),
    ev("e6", "TAN", "2026-10-08T16:00:00+02:00", "2026-10-08T17:00:00+02:00", "Irodalom olvasás", allapot=3),
]


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.al = AlSeged(self._t.name, {"naptarak": list(NAPTARAK), "esemenyek": [dict(e) for e in ESEMENYEK]})
        self.cfg, self.root, self.v = alg_core(self._t.name, **self.al.env())
        self.seged = Seged(self.cfg)

    def sync(self, **kw):
        return naptar.szinkron(self.cfg, self.seged, most=MOST, **kw)

    def pos(self):
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        c.row_factory = sqlite3.Row
        self.addCleanup(c.close)
        return c


class SzabalyTest(unittest.TestCase):
    def test_kategoria_javaslat(self):
        for nev, vart in [("Deadlines & Exams", ("hatarido", True)), ("Studying", ("tanulas", True)), ("Órarend", ("orarend", True)),
                          ("Ünnepnapok", ("kizart", True)), ("Me-time és programok", ("szabadido", True)),
                          ("Workouts", ("edzes", True)), ("Valami Különös", ("egyeb", False))]:
            self.assertEqual(naptar.javasol(nev), vart, nev)
        self.assertEqual(naptar.javasol("Bárki", "szuletesnap"), ("kizart", True))

    def test_tantargy_szohatar(self):
        self.assertEqual(naptar.targy("Matek röpdolgozat"), ["Matematika"])
        self.assertEqual(naptar.targy("Materiál beszerzés"), [])            # a „mat” nem a „materiál”-ban
        self.assertEqual(naptar.targy("Magyar"), ["Irodalom", "Nyelvtan"])
        self.assertEqual(naptar.targy("Német - Röpdolgozat"), ["Német"])

    def test_esemeny_fajta(self):
        self.assertEqual(naptar.esemeny_fajta("Német - Röpdolgozat", "hatarido"), "dolgozat")
        self.assertEqual(naptar.esemeny_fajta("Bánk bán beadandó", "hatarido"), "hatarido")
        self.assertIsNone(naptar.esemeny_fajta("Dolgozatra készülés", "tanulas"))        # a tanulás nem számonkérés
        self.assertIsNone(naptar.esemeny_fajta("Dolgozat", "edzes"))
        self.assertEqual(naptar.esemeny_fajta("Matek", "hatarido"), "dolgozat")          # tantárgy, határidő-szó nélkül


class SzinkronTest(Alap):
    def test_elso_szinkron_felveszi_a_naptarakat_es_az_eseményeket(self):
        r = self.sync()
        self.assertEqual((r["allapot"], r["uj"], r["valtozott"], r["torolt"], r["osszes"]), ("engedelyezve", 6, 0, 0, 6))
        c = self.pos()
        kat = {x["azon"]: (x["kategoria"], x["kategoria_forras"]) for x in c.execute("SELECT * FROM naptar")}
        self.assertEqual(kat["HAT"], ("hatarido", "auto"))
        self.assertEqual(kat["TAN"], ("tanulas", "auto"))
        self.assertEqual(kat["UNN"], ("kizart", "auto"))
        self.assertEqual(kat["X"], ("egyeb", "javaslat"))                    # a név alapján nem biztos: megerősítendő
        self.assertEqual(c.execute("SELECT count(*) FROM forras_rekord WHERE forras='naptar'").fetchone()[0], 6)
        fut = c.execute("SELECT * FROM import_futas ORDER BY id DESC").fetchone()
        self.assertEqual((fut["allapot"], fut["uj"], fut["osszes"]), ("engedelyezve", 6, 6))

    def test_ismetlo_szinkron_valtozatlan_majd_valtozott_es_torolt(self):
        self.sync()
        r = self.sync()
        self.assertEqual((r["uj"], r["valtozott"], r["torolt"]), (0, 0, 0))
        def valt(d):
            d["esemenyek"][0]["cim"] = "Matek gyakorlás (átírva)"
            d["esemenyek"] = [e for e in d["esemenyek"] if not e["azon"].startswith("e5")]
        self.al.modosit(valt)
        r = self.sync()
        self.assertEqual((r["uj"], r["valtozott"], r["torolt"]), (0, 1, 1))
        torolt = self.pos().execute("SELECT torolve FROM forras_rekord WHERE forras_id LIKE 'e5|%'").fetchone()[0]
        self.assertIsNotNone(torolt)                                         # jelölés, nem törlés (provenancia)
        self.assertEqual(self.pos().execute("SELECT count(*) FROM forras_rekord").fetchone()[0], 6)

    def test_atnevezes_nem_bontja_a_kategoriat(self):
        self.sync()
        naptar.kategoria_allit(self.cfg, "X", "edzes")
        self.al.modosit(lambda d: d["naptarak"][-1].update(nev="Átnevezett"))
        r = self.sync()
        self.assertEqual([(v["fajta"], v["regi"], v["uj"]) for v in r["valtozasok"]], [("atnevezve", "Valami Különös", "Átnevezett")])
        row = self.pos().execute("SELECT nev, kategoria, kategoria_forras FROM naptar WHERE azon='X'").fetchone()
        self.assertEqual(tuple(row), ("Átnevezett", "edzes", "gazda"))

    def test_eltunt_naptar_utodja_oroklodik(self):
        self.sync()
        naptar.kategoria_allit(self.cfg, "X", "szabadido")
        self.al.modosit(lambda d: d["naptarak"][-1].update(azon="X2"))     # a fiók újra bejelentkezett: új azonosító
        r = self.sync()
        fajtak = sorted(v["fajta"] for v in r["valtozasok"])
        self.assertEqual(fajtak, ["eltunt", "osszekotve"])
        ujsor = self.pos().execute("SELECT kategoria, kategoria_forras FROM naptar WHERE azon='X2'").fetchone()
        self.assertEqual(tuple(ujsor), ("szabadido", "gazda"))
        self.assertEqual(self.pos().execute("SELECT utod FROM naptar WHERE azon='X'").fetchone()[0], "X2")

    def test_engedely_nelkul_semmi_nem_kerul_az_adatba(self):
        """T007 (2. audit): engedély nélkül a szinkron nem nyit író kapcsolatot — nem hoz létre fájlt, nem migrál,
        nem ír `import_futas` sort; az engedély-állapotot a szolgáltatás memóriája hordozza."""
        for allapot in ("nincs_dontes", "megtagadva"):
            self.al.modosit(lambda d: d.update(esemeny=allapot))
            r = self.sync()
            self.assertEqual((r["allapot"], r["uj"], r["osszes"]), (allapot, 0, 0))
            self.assertFalse(szemelyes_db.ut(self.cfg).exists())

    def test_engedely_nelkul_a_meglevo_adatbazis_erintetlen(self):
        """A legacy 1-es sémájú pos.sqlite engedély nélküli szinkronnál nem lép 3-asra (a main trackere ettől
        dobna el minden eseményt), és sora sem keletkezik."""
        szemelyes_db.ut(self.cfg).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        c.executescript(szemelyes_db.MIGRACIOK[0] + "PRAGMA user_version = 1;")
        c.close()
        elotte = szemelyes_db.ut(self.cfg).read_bytes()
        self.al.modosit(lambda d: d.update(esemeny="nincs_dontes"))
        self.sync()
        self.assertEqual(self.pos().execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(self.pos().execute("SELECT count(*) FROM import_futas").fetchone()[0], 0)
        self.assertEqual(szemelyes_db.ut(self.cfg).read_bytes(), elotte)

    def test_segedhiba(self):
        self.al.modosit(lambda d: d.update(hiba_parancs="olvas", hiba_uzenet="összeomlott"))
        with self.assertRaisesRegex(SegedHiba, "összeomlott"):
            self.sync()
        cfg2, _, _ = alg_core(self._t.name + "/masik")            # segéd nélküli gyökér
        with self.assertRaisesRegex(SegedHiba, "nincs naptár-segéd"):
            naptar.szinkron(cfg2, Seged(cfg2), most=MOST)

    def test_tanulasi_blokkok_csak_a_tracker_kapcsoloja_alatt(self):
        self.sync()
        self.assertEqual(self.pos().execute("SELECT count(*) FROM tr_naptar_blokk").fetchone()[0], 0)
        r = self.sync(tracker_be=True)
        self.assertEqual(r["blokkok"], 1)
        sor = self.pos().execute("SELECT nap, tantargy, kategoria FROM tr_naptar_blokk").fetchone()
        self.assertEqual(tuple(sor), ("2026-10-05", "Matematika", "tanulas"))     # nem egész napos, nem lemondott
        self.al.modosit(lambda d: d["esemenyek"].pop(0))
        self.assertEqual(self.sync(tracker_be=True)["blokkok"], 0)               # az eltűnt blokk kikerül


class EsemenyekTest(Alap):
    def test_dolgozat_ora_es_tantargy_az_orarendbol(self):
        self.sync()
        with szemelyes_db.olvaso(self.cfg) as c:
            lista = naptar.esemenyek(c, datetime(2026, 10, 1, tzinfo=TZ), datetime(2026, 10, 31, tzinfo=TZ), self.cfg)
        cimek = {e["cim"]: e for e in lista}
        self.assertNotIn("Nemzeti ünnep", cimek)                              # a kizárt naptár
        self.assertNotIn("Irodalom olvasás", cimek)                           # a lemondott esemény
        tz = cimek["Témazáró"]
        self.assertEqual((tz["fajta"], tz["targyak"], tz["targy_forras"]), ("dolgozat", ["Fizika"], "orarend"))
        self.assertEqual(tz["ora"]["cim"], "Fizika")

    def test_kategoria_allit_hibai(self):
        self.sync()
        with self.assertRaises(ValueError):
            naptar.kategoria_allit(self.cfg, "X", "nincs-ilyen")
        with self.assertRaises(KeyError):
            naptar.kategoria_allit(self.cfg, "NINCS", "edzes")


if __name__ == "__main__":
    unittest.main()
