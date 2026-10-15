"""A becslés rekonstrukciója egy múltbeli időpontra és az eredmények betöltése (C28b): a kártya-állapot a `valasz`
(`utana`/`visszavonva`) és a `letrehozva`/`torolve` naplóból, a tracker a nap végéig, a kvíz az időbélyegeiből — külön becslés-napló
nélkül; az eredmény a „Dolgozat kiértékelő” jegyzetből. Szintetikus adaton, csak olvasva."""
import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone

from core import tanulas_db
from core.felkeszultseg import adat, forrasok, keplet, osszesit, rekonstrukcio
from core.felkeszultseg.forrasok import KvizEredmeny
from modulok.kartya import utemezo
from tests.felkeszultseg_segedek import Alap, DOLGOZAT_NAP, FELK, MOST, T1, T2, TZ
from tests.helpers import ir

NAP = date.fromisoformat(DOLGOZAT_NAP)
UTC = timezone.utc
KIERT = "X01 - Napló & To-Do/2026-10/Napló/2026-10 - Dolgozat kiértékelő.md"


def kiertekelo(szakaszok: str) -> str:
    return "---\nTags:\n  - Dolgozat-kiértékelés\nSource:\nStatus:\nNN:\nCanvas:\n---\n\n" + szakaszok


class RekonstrukcioAlap(Alap):
    """A T1 három kártyája: az első 10 nappal, a második 6 nappal MOST előtt tanult; a harmadik új."""

    def setUp(self):
        super().setUp()
        self.t0 = MOST.astimezone(UTC) - timedelta(days=12)
        self.kartyak(T1, ("c-00000001", "Mi a hatvány?", "ismételt szorzás"), ("c-00000002", "Mi a 2^3?", "8"),
                     ("c-00000003", "Új kártya", "válasz"), most=self.t0)
        self.valasz("c-00000001", 3, self.t0 + timedelta(days=2))             # 10 nappal MOST előtt
        self.valasz("c-00000001", 3, self.t0 + timedelta(days=4))             # 8 nappal
        self.valasz("c-00000002", 1, self.t0 + timedelta(days=6))             # 6 nappal

    def ekkor(self, napok_mostig: float) -> datetime:
        return (MOST - timedelta(days=napok_mostig)).astimezone(UTC)

    def tarolt(self, azon: str) -> dict:
        with tanulas_db.olvaso(self.cfg) as c:
            return dict(c.execute("SELECT * FROM kartya WHERE azon = ?", (azon,)).fetchone())

    def ekkori(self, ekkor, azon=None):
        with tanulas_db.olvaso(self.cfg) as c:
            ki, utolso = rekonstrukcio.kartyak_ekkor(c, ekkor)
        return ({k["azon"]: k for k in ki}, utolso) if azon is None else ({k["azon"]: k for k in ki}[azon], utolso.get(azon))


class KartyaAllapotEkkorTest(RekonstrukcioAlap):
    def test_a_mostani_allapot_egyezik_a_tarolttal(self):
        mind, _ = self.ekkori(MOST.astimezone(UTC) + timedelta(days=1))
        for azon in ("c-00000001", "c-00000002", "c-00000003"):
            t = self.tarolt(azon)
            self.assertEqual({k: mind[azon][k] for k in utemezo.MEZOK}, {k: t[k] for k in utemezo.MEZOK}, azon)

    def test_az_elso_valasz_elott_a_kartya_uj(self):
        k, ut = self.ekkori(self.t0 + timedelta(days=1), "c-00000001")
        self.assertEqual((k["allapot"], k["stabilitas"], ut), (utemezo.UJ, None, None))

    def test_a_valasz_utani_allapot_az_utana_mezobol(self):
        k, ut = self.ekkori(self.t0 + timedelta(days=3), "c-00000001")           # csak az első válasz után
        self.assertNotEqual(k["allapot"], utemezo.UJ)
        stabilitas_elso = k["stabilitas"]
        masodik, _ = self.ekkori(self.t0 + timedelta(days=5), "c-00000001")
        self.assertGreater(masodik["stabilitas"], stabilitas_elso)                # két jó válasz után erősebb
        self.assertTrue(ut.startswith((self.t0 + timedelta(days=2)).strftime("%Y-%m-%d")))

    def test_a_felidezes_a_rekonstrualt_allapotbol_szamolodik(self):
        k, _ = self.ekkori(self.t0 + timedelta(days=3), "c-00000001")
        tau = self.t0 + timedelta(days=5)
        r = utemezo.felidezes(k, tau, self.sched)
        self.assertTrue(0 < r < 1)
        # a mostani (több válasz utáni) állapot ugyanarra az időpontra más felidézést adna
        mostani = utemezo.felidezes(self.tarolt("c-00000001"), tau, self.sched)
        self.assertNotEqual(round(r, 4), round(mostani, 4))

    def test_a_visszavont_valasz_a_visszavonas_elott_meg_szamit_utana_nem(self):
        # c-00000002 válasza 6 napja volt; visszavonjuk MOST-kor
        utemezo.visszavon(self.cfg, "c-00000002", most=MOST.astimezone(UTC))
        a_visszavonas_elott, _ = self.ekkori(self.ekkor(2), "c-00000002")
        self.assertNotEqual(a_visszavonas_elott["allapot"], utemezo.UJ, "a visszavonás előtt a válasz érvényes volt")
        utana, ut = self.ekkori(MOST.astimezone(UTC) + timedelta(hours=1), "c-00000002")
        self.assertEqual((utana["allapot"], ut), (utemezo.UJ, None), "a visszavonás után a kártya újra új")
        self.assertEqual(self.tarolt("c-00000002")["allapot"], utemezo.UJ)

    def test_a_kesobb_letrehozott_kartya_nem_letezik(self):
        self.kartyak(T2, ("c-00000011", "Mi a gyök?", "fordított"), most=MOST.astimezone(UTC) - timedelta(days=1))
        regi, _ = self.ekkori(MOST.astimezone(UTC) - timedelta(days=5))
        self.assertNotIn("c-00000011", regi)
        uj, _ = self.ekkori(MOST.astimezone(UTC))
        self.assertIn("c-00000011", uj)

    def test_a_kesobb_torolt_kartya_akkor_meg_letezett(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("UPDATE kartya SET torolve = ? WHERE azon = 'c-00000002'", ((MOST.astimezone(UTC) - timedelta(days=1)).isoformat(),))
        akkor, _ = self.ekkori(self.ekkor(3))
        self.assertIn("c-00000002", akkor)
        most, _ = self.ekkori(MOST.astimezone(UTC))
        self.assertNotIn("c-00000002", most)

    def test_a_felfuggesztett_kartya_kimarad(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("UPDATE kartya SET felfuggesztve = 1 WHERE azon = 'c-00000001'")
        mind, _ = self.ekkori(MOST.astimezone(UTC))
        self.assertNotIn("c-00000001", mind)

    def test_valasz_nelkuli_importalt_allapot_az_utolso_atnezes_szerint(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("UPDATE kartya SET allapot = 2, lepes = NULL, stabilitas = 5.0, nehezseg = 5.0, utolso = ?, esedekes = ? "
                      "WHERE azon = 'c-00000003'", ((MOST.astimezone(UTC) - timedelta(days=3)).isoformat(), MOST.astimezone(UTC).isoformat()))
        elotte, _ = self.ekkori(self.ekkor(5), "c-00000003")
        self.assertEqual(elotte["allapot"], utemezo.UJ, "az átnézés előtt új")
        utana, _ = self.ekkori(self.ekkor(2), "c-00000003")
        self.assertEqual(utana["stabilitas"], 5.0)


class RekonstrualtAdatokTest(RekonstrukcioAlap):
    def setUp(self):
        super().setUp()
        for nap, mp in (("2026-09-25", 900), ("2026-10-01", 1200), ("2026-10-02", 600), ("2026-10-03", 3000)):
            self.aktiv(nap, T1, mp)

    def rek(self, most):
        return self.rekadat(most)

    def rekadat(self, most):
        return adat.Adatok(self.cfg, self.ix, most, rekonstrukcio=True)

    def test_a_tracker_a_nap_vegeig_szamit_a_kesobbi_nap_nem(self):
        a = self.rek(datetime(2026, 10, 1, 23, 59, tzinfo=TZ))
        jel, r = a.tema_jel(T1, NAP, a.most)
        self.assertAlmostEqual(r["tanult_perc"], (900 + 1200) / 60)               # 09-25 és 10-01, a 10-02 és 10-03 nem
        self.assertEqual(r["utolso_tanulas"], "2026-10-01")
        mai = self.adatok(datetime(2026, 10, 1, 23, 59, tzinfo=TZ))                 # nem rekonstrukció: a „most” korlát a ma_iso-ban
        _, r2 = mai.tema_jel(T1, NAP, mai.most)
        self.assertEqual(r2["tanult_perc"], r["tanult_perc"])

    def test_a_kartyak_az_akkori_allapotban_toltodnek(self):
        akkor = (self.t0 + timedelta(days=3)).astimezone()
        a = self.rek(akkor)
        db_uj = [k for k in a.kartyak() if k["allapot"] == utemezo.UJ]
        self.assertEqual({k["azon"] for k in db_uj}, {"c-00000002", "c-00000003"})        # csak a c-…01-et néztük át addig
        jel, _ = a.tema_jel(T1, NAP, a.most)
        self.assertEqual(len(jel.kartya), 3)
        self.assertEqual(sum(1 for x in jel.kartya if x == 0.0), 2)

    def test_a_valodi_becsles_kulonbozik_a_rekonstrualttol_es_a_rekonstrualt_nem_latja_a_jovot(self):
        korai = self.rek((self.t0 + timedelta(days=3)).astimezone())
        k1, _ = korai.tema_jel(T1, NAP, korai.most)
        most = self.adatok()
        k2, _ = most.tema_jel(T1, NAP, MOST)
        self.assertNotEqual(sum(k1.kartya), sum(k2.kartya))

    def test_kviz_az_idopontig(self):
        self.kviz(KvizEredmeny(T1, self.t0 + timedelta(days=5), 3, 4), KvizEredmeny(T1, self.t0 + timedelta(days=9), 4, 4))
        a = self.rek((self.t0 + timedelta(days=7)).astimezone())
        jel, _ = a.tema_jel(T1, NAP, a.most)
        self.assertEqual(len(jel.kviz), 1)
        self.assertEqual(jel.kviz[0][1:], (3, 4))

    def test_a_rekonstrukcio_nem_ir(self):
        import hashlib
        import os
        from pathlib import Path

        def lenyomat():
            ki = {}
            for gyoker in (self.cfg.path("tanulas_db").parent,):
                for d, _, fajlok in os.walk(gyoker):
                    for f in fajlok:
                        if f.endswith(".sqlite"):
                            ki[f] = hashlib.sha1(Path(d, f).read_bytes()).hexdigest()
            return ki
        elotte = lenyomat()
        a = self.rek((self.t0 + timedelta(days=5)).astimezone())
        a.kartyak(), a.aktiv(), a.kviz()
        self.assertEqual(lenyomat(), elotte)


class EredmenyBetoltesTest(Alap):
    def kiertekelo(self, szakaszok: str) -> None:
        ir(self.v, KIERT, kiertekelo(szakaszok))
        self.ix.frissit([KIERT])

    def olvaso(self):
        def olvas(rp):
            return (self.v / rp).read_text(encoding="utf-8")
        return olvas

    def lezart(self):
        return adat.Adatok(self.cfg, self.ix, MOST + timedelta(days=5), olvas=self.olvaso())

    def test_az_eredmeny_a_felkeszulesi_jegyzethez_kotodik(self):
        self.kiertekelo(f"# Október 7: Matematika\n\n[[2026-10-07 - Matematika]]\n\n13/16 pontos lett.\n\n"
                        "# Október 8: Német\n\n[[2026-10-08 - Német]]\n\n4,5/10 lett.\n")
        a = self.lezart()
        e = a.eredmenyek()
        self.assertEqual(set(e), {FELK})                                           # a Német jegyzet nincs a vaultban
        self.assertEqual((e[FELK]["eredmeny"]["pont"], e[FELK]["eredmeny"]["max"]), (13.0, 16.0))
        self.assertEqual(e[FELK]["fajl"], KIERT)
        self.assertEqual(a.adatok["eredmeny"]["db"], 1)

    def test_a_dolgozat_ertekelese_tartalmazza_az_eredmenyt_csak_lezartnak(self):
        self.kiertekelo("# Október 7: Matematika\n\n[[2026-10-07 - Matematika]]\n\n13/16 pontos lett.\n")
        nyitott = adat.Adatok(self.cfg, self.ix, MOST, olvas=self.olvaso())
        d = nyitott.dolgozatok()[0]
        self.assertIsNone(osszesit.ertekel(nyitott, d)["eredmeny"])
        a = self.lezart()
        e = osszesit.ertekel(a, a.dolgozatok()[0])
        self.assertEqual((e["eredmeny"]["pont"], e["eredmeny"]["max"], e["eredmeny"]["szazalek"]), (13.0, 16.0, 81.2))
        self.assertEqual(e["eredmeny"]["jegyzet"], KIERT)
        self.assertIsNone(e["eredmeny_ellentmondas"])

    def test_ellentmondas_jelzese(self):
        self.kiertekelo("# Október 7: Matematika\n\n[[2026-10-07 - Matematika]]\n\n68% lett (18/31).\n")
        a = self.lezart()
        e = osszesit.ertekel(a, a.dolgozatok()[0])
        self.assertIsNone(e["eredmeny"])
        self.assertEqual(len(e["eredmeny_ellentmondas"]["jeloltek"]), 2)

    def test_olvaso_nelkul_nincs_eredmeny_es_megmondja_miert(self):
        a = adat.Adatok(self.cfg, self.ix, MOST + timedelta(days=5))
        self.assertEqual(a.eredmenyek(), {})
        self.assertFalse(a.adatok["eredmeny"]["van"] or False)
        self.assertIn("olvasó", a.adatok["eredmeny"]["ok"])

    def test_nincs_kiertekelo_jegyzet(self):
        a = self.lezart()
        self.assertEqual(a.eredmenyek(), {})
        self.assertEqual(a.adatok["eredmeny"]["ok"], "nincs kiértékelő jegyzet")

    def test_a_dolgozat_napló_nevu_jegyzet_is_kiertekelo(self):
        ir(self.v, "X01 - Napló & To-Do/2026-10/Napló/2026-10 - Dolgozat Napló.md",
           kiertekelo("# Október 7\n[[2026-10-07 - Matematika]]\n10/10 pontos lett."))
        self.ix.frissit(["X01 - Napló & To-Do/2026-10/Napló/2026-10 - Dolgozat Napló.md"])
        self.assertEqual(self.lezart().eredmenyek()[FELK]["eredmeny"]["pont"], 10.0)

    def test_olvasasi_hiba_figyelmeztetes_nem_kivetel(self):
        self.kiertekelo("# Október 7\n[[2026-10-07 - Matematika]]\n10/10 pontos lett.")

        def rossz(rp):
            raise OSError("nem olvasható")
        a = adat.Adatok(self.cfg, self.ix, MOST + timedelta(days=5), olvas=rossz)
        self.assertEqual(a.eredmenyek(), {})
        self.assertTrue(any("nem olvasható" in f for f in a.figyelmeztetesek))

    def test_az_ablak_visszamenoleg_kiterjesztheto(self):
        a = adat.Adatok(self.cfg, self.ix, MOST + timedelta(days=30), olvas=self.olvaso())
        self.assertEqual(a.dolgozatok(), [])
        b = adat.Adatok(self.cfg, self.ix, MOST + timedelta(days=30), olvas=self.olvaso(), visszamenoleg_nap=60)
        d = b.dolgozatok()
        self.assertEqual((len(d), d[0]["lezart"]), (1, True))
        self.assertEqual(d[0]["kotes"].fok, "biztos")


class KvizTarForrasTest(Alap):
    def test_a_kviz_kitoltes_tabla_a_felkeszultseg_kvizforrasa(self):
        with tanulas_db.iro(self.cfg) as c:
            def be(kulcs, forras, mikor, mod, pont, osszes):
                c.execute("INSERT INTO kviz_kitoltes (kulcs, kviz, kviz_ut, forras, modell, szoveg_hash, mikor, mod, pont, osszes, szazalek, "
                          "ido_ms, elemzes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (kulcs, "KVIZ-1", "ATTCHMNTS - quizes/x.md", forras, None, "h", mikor, mod, pont, osszes, 0, None, "{}"))
            be("k1", T1[:-3], (MOST - timedelta(days=2)).astimezone(UTC).isoformat(), "teljes", 3, 4)
            be("k2", T1[:-3], (MOST - timedelta(days=1)).astimezone(UTC).isoformat(), "hibasak", 1, 1)
            be("k3", T2[:-3], (MOST + timedelta(days=1)).astimezone(UTC).isoformat(), "teljes", 4, 4)
        forrasok._FORRASOK.clear()
        forrasok.regisztral_kviz_forras("kviz", forrasok.kviz_tar_forras)
        a = self.adatok()
        jel, r = a.tema_jel(T1, date.fromisoformat(DOLGOZAT_NAP), MOST)
        self.assertEqual([x[1:] for x in jel.kviz], [(3, 4)])                       # csak a teljes kitöltés, csak a MOST-ig
        self.assertEqual(r["kviz"]["db"], 1)

    def test_nincs_adatbazis_nincs_hiba(self):
        self.assertEqual(forrasok.kviz_tar_forras(self.cfg, MOST - timedelta(days=9), MOST), [])


if __name__ == "__main__":
    unittest.main()
