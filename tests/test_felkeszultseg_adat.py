"""A felkészültség bemenetei (C28a): naptár + kötés, témák, kártya→téma, tracker (átnevezés-követéssel), kvíz — szintetikus
adaton, **csak olvasva** (a vault, a `pos.sqlite` és a `tanulas.sqlite` bájtra változatlan)."""
import hashlib
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from core import snapshot
from core.felkeszultseg import adat, atnevezes, forrasok
from core.felkeszultseg.forrasok import KvizEredmeny
from modulok.kartya import utemezo
from tests.felkeszultseg_segedek import (Alap, DOLGOZAT_NAP, FELK, KARTYA_MAPPA, MOST, PDF, T1, T2, T3, TZ)
from tests.helpers import ir

NAP = date.fromisoformat(DOLGOZAT_NAP)
UTC = timezone.utc


def fa_lenyomat(gyoker):
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        mappak[:] = [m for m in mappak if m != ".obsidian"]
        for f in fajlok:
            p = Path(d) / f
            ki[os.path.relpath(p, gyoker)] = hashlib.sha1(p.read_bytes()).hexdigest()
    return ki


class MenetTest(Alap):
    def test_alapertekek_az_os_tomlbol(self):
        m = adat.Menet.cfg_bol(self.cfg)
        self.assertEqual((m.elore_nap, m.mult_nap, m.ablak_nap, m.napi_perc, m.szelet_perc), (60, 3, 21, 45, 15))
        self.assertEqual(m.dolgozat_mappa, "Dolgozatok")


class NaptarEsKotesTest(Alap):
    def test_a_dolgozat_es_a_felkeszulesi_jegyzet_kotese(self):
        d = self.adatok().dolgozatok()
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["azon"][:2], d[0]["nap"], d[0]["tantargy"], d[0]["napok"], d[0]["lezart"]),
                         ("d1", DOLGOZAT_NAP, "Matematika", 4, False))
        self.assertEqual((d[0]["kotes"].jegyzet, d[0]["kotes"].fok), (FELK, "biztos"))

    def test_masik_naptaresemeny_nem_dolgozat(self):
        self.al.modosit(lambda m: m["esemenyek"].append({**self.ESEMENYEK[0], "azon": "x|1", "cim": "Edzés", "naptar": "TAN"}))
        from core import naptar
        from core.naptar_seged import Seged
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        self.assertEqual(len(self.adatok().dolgozatok()), 1)

    def test_a_lezart_dolgozat_az_ablakon_belul_marad_a_regebbi_kimarad(self):
        a = self.adatok(MOST + timedelta(days=5))            # 10-08: a dolgozat 1 napja lezárult
        d = a.dolgozatok()
        self.assertEqual((len(d), d[0]["lezart"], d[0]["napok"]), (1, True, -1))
        self.assertEqual(self.adatok(MOST + timedelta(days=9)).dolgozatok(), [])

    def test_nincs_naptaradat_hiany(self):
        class NincsNaptar(Alap):
            naptar_van = False
        t = NincsNaptar()
        t.setUp()
        self.addCleanup(t.doCleanups)
        with self.assertRaises(adat.Hiany) as cm:
            t.adatok().dolgozatok()
        self.assertIn("naptár", str(cm.exception))

    def test_nem_kesz_index_nincs_kotes_de_a_dolgozat_listazodik(self):
        a = self.adatok()
        with mock.patch.object(self.ix, "allapot", return_value={"kesz": False}):
            d = a.dolgozatok()
        self.assertEqual((len(d), d[0]["kotes"]), (1, None))
        self.assertTrue(any("index" in f for f in a.figyelmeztetesek))


class TemakTest(Alap):
    def test_temak_es_forrasok(self):
        t = self.adatok().temak(FELK)
        self.assertEqual(t.temak, (T1, T2, T3))
        self.assertEqual([(f.ut, f.tipus, f.oldalak) for f in t.forrasok], [(PDF, "pdf", "18–19, 28")])


class KartyaTest(Alap):
    def setUp(self):
        super().setUp()
        t0 = MOST.astimezone(UTC) - timedelta(days=10)
        self.kartyak(T1, ("c-00000001", "Mi a hatvány?", "ismételt szorzás"), ("c-00000002", "Mi a 2^3?", "8"),
                     ("c-00000003", "Mi a 0^0?", "nem értelmezett"), ("c-00000004", "Új kártya", "válasz"), most=t0)
        self.kartyak(T2, ("c-00000011", "Mi a gyök?", "fordított hatvány"), most=t0)
        for azon, jegyek in (("c-00000001", (3, 3)), ("c-00000002", (4,)), ("c-00000003", (1, 3)), ("c-00000011", (3,))):
            for i, j in enumerate(jegyek):
                self.valasz(azon, j, t0 + timedelta(days=i * 2))

    def test_kartya_temankent_a_forras_linkbol(self):
        a = self.adatok()
        self.assertEqual({t: len(k) for t, k in a.temankent().items()}, {T1: 4, T2: 1})
        self.assertEqual(a.adatok["kartya"]["kotetlen"], 0)

    def test_tema_jel_felidezes_az_fsrs_bol(self):
        a = self.adatok()
        jel, r = a.tema_jel(T1, NAP, MOST)
        kartyak = {k["azon"]: k for k in a.kartyak()}
        vart = tuple(utemezo.felidezes(kartyak[x], MOST, a.sched()) for x in ("c-00000001", "c-00000002", "c-00000003", "c-00000004"))
        self.assertEqual(jel.kartya, vart)
        self.assertEqual(jel.kartya[3], 0.0)                                   # az új kártya 0
        self.assertEqual((jel.uj_kartya, r["kartya"]["db"], r["kartya"]["uj"]), (1, 4, 1))
        self.assertTrue(all(0 < x <= 1 for x in jel.kartya[:3]))

    def test_a_kilatas_a_dolgozat_napjara_nem_nagyobb_felidezes(self):
        a = self.adatok()
        most, _ = a.tema_jel(T1, NAP, MOST)
        kil, _ = a.tema_jel(T1, NAP, datetime(2026, 10, 7, 9, 0, tzinfo=TZ))
        self.assertTrue(all(k <= m for k, m in zip(kil.kartya, most.kartya)))
        self.assertLess(sum(kil.kartya), sum(most.kartya))

    def test_gyenge_kartyak_a_legalacsonyabb_felidezessel_elol_az_uj_nelkul(self):
        _, r = self.adatok().tema_jel(T1, NAP, MOST)
        gy = r["kartya"]["gyenge"]
        self.assertEqual(len(gy), 3)
        self.assertEqual([x["felidezes"] for x in gy], sorted(x["felidezes"] for x in gy))
        self.assertNotIn("c-00000004", [x["azon"] for x in gy])

    def test_utolso_tanulas_a_legutobbi_kartyavalaszbol(self):
        a = self.adatok()
        jel, r = a.tema_jel(T2, NAP, MOST)
        t0 = (MOST.astimezone(UTC) - timedelta(days=10)).astimezone().date()
        self.assertEqual(r["utolso_tanulas"], t0.isoformat())
        self.assertEqual(jel.utolso_tanulas_nap, (MOST.date() - t0).days)

    def test_visszavont_valasz_nem_szamit_utolso_tanulasnak(self):
        a0 = self.adatok()
        _, r0 = a0.tema_jel(T2, NAP, MOST)
        self.valasz("c-00000011", 3, MOST.astimezone(UTC) - timedelta(days=1))
        utemezo.visszavon(self.cfg, "c-00000011")
        _, r1 = self.adatok().tema_jel(T2, NAP, MOST)
        self.assertEqual(r1["utolso_tanulas"], r0["utolso_tanulas"])

    def test_forras_nelkuli_vagy_feloldatlan_kartya_a_kisero_source_aval(self):
        self.kartyak(T3, ("c-00000021", "Mi a log?", "kitevő", "Nincs ilyen jegyzet#^m-9"))
        a = self.adatok()
        self.assertEqual(len(a.temankent().get(T3, [])), 1)

    def test_kotetlen_kartya_szamolva(self):
        ir(self.v, f"{KARTYA_MAPPA}/Árva — kártyák.md",
           "---\nSource:\nStatus:\n---\n> [!card]- Árva kérdés\n> válasz\n\n^c-0000ffff\n")
        from modulok.kartya import szinkron
        szinkron.szinkron(self.cfg, most=MOST.astimezone(UTC))
        self.ix.frissit([f"{KARTYA_MAPPA}/Árva — kártyák.md"])
        a = self.adatok()
        a.temankent()
        self.assertEqual(a.adatok["kartya"]["kotetlen"], 1)

    def test_esedekes_napra_becsles(self):
        a = self.adatok()
        napok = [(MOST.date() + timedelta(days=i)).isoformat() for i in range(0, 12)]
        ki = a.esedekes_napra([T1, T2], napok)
        # az összes nem új kártya (3 + 1) valamelyik napra esik, vagy a mai (lejárt) vödörbe, vagy később
        self.assertLessEqual(sum(ki.values()), 4)
        self.assertGreaterEqual(ki[MOST.date().isoformat()], 0)


class NincsKartyaTest(Alap):
    def test_nincs_tanulas_sqlite_nincs_adat_es_nem_jon_letre(self):
        a = self.adatok()
        self.assertEqual(a.kartyak(), [])
        self.assertFalse(a.adatok["kartya"]["van"])
        self.assertFalse((self.cfg.path("tanulas_db")).exists())
        jel, r = a.tema_jel(T1, NAP, MOST)
        self.assertEqual((jel.kartya, jel.uj_kartya), ((), 0))


class FsrsNelkulTest(Alap):
    def test_py_fsrs_nelkul_is_el_a_lap_ha_nincs_tanult_kartya(self):
        """Ha a py-fsrs hiányzik (pl. a fő venv a lockon kívül), a kártya nélküli vagy csak új kártyás téma számolása nem akad el."""
        self.kartyak(T1, ("c-00000001", "Mi a hatvány?", "szorzás"))             # csak új kártya
        with mock.patch.dict("sys.modules", {"fsrs": None}):
            jel, r = self.adatok().tema_jel(T1, NAP, MOST)
            self.assertEqual((jel.kartya, jel.uj_kartya), ((0.0,), 1))
            jel2, _ = self.adatok().tema_jel(T2, NAP, MOST)
            self.assertEqual(jel2.kartya, ())


class TrackerTest(Alap):
    def test_tanult_perc_az_ablakban_utolso_tanulas_idokorlat_nelkul(self):
        self.aktiv("2026-10-01", T1, 600)
        self.aktiv("2026-10-02", T1, 900)
        self.aktiv("2026-09-01", T1, 3000)            # az ablakon (dolgozat − 21 nap = 09-16) kívül: csak a frissességhez
        jel, r = self.adatok().tema_jel(T1, NAP, MOST)
        self.assertEqual(jel.tanult_perc, 25.0)
        self.assertEqual(jel.utolso_tanulas_nap, 1)
        self.assertEqual(r["utolso_tanulas"], "2026-10-02")

    def test_csak_regi_sor_a_frissesseg_mar_regi_perc_nulla(self):
        self.aktiv("2026-09-01", T1, 3000)
        jel, _ = self.adatok().tema_jel(T1, NAP, MOST)
        self.assertEqual((jel.tanult_perc, jel.utolso_tanulas_nap), (0.0, 32))

    def test_rovid_nezes_nem_tanulas(self):
        self.aktiv("2026-10-02", T1, 30)
        jel, _ = self.adatok().tema_jel(T1, NAP, MOST)
        self.assertEqual(jel.tanult_perc, 0.5)
        self.assertIsNone(jel.utolso_tanulas_nap)

    def test_mas_tema_ideje_nem_szamit(self):
        self.aktiv("2026-10-02", T2, 900)
        jel, _ = self.adatok().tema_jel(T1, NAP, MOST)
        self.assertEqual((jel.tanult_perc, jel.utolso_tanulas_nap), (0.0, None))

    def test_nincs_tracker_adat(self):
        a = self.adatok()
        jel, _ = a.tema_jel(T1, NAP, MOST)
        self.assertEqual(jel.tanult_perc, 0.0)
        self.assertFalse(a.adatok["tracker"]["van"])

    def test_a_felkeszulesi_jegyzet_maga_mint_tema(self):
        self.aktiv("2026-10-02", FELK, 1200)
        jel, _ = self.adatok().tema_jel(FELK, NAP, MOST)
        self.assertEqual(jel.tanult_perc, 20.0)

    def test_atnevezes_elotti_ut_ideje_az_uj_uthoz_szamit(self):
        regi = "M06 - Exponenciális/Elmélet/Régi Hatvány.md"
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        ir(self.v, regi, "# Régi\n")
        repo.commit_machine("x", {"Mos-Kor": "SZERK-20261002-100000"}, [regi])
        os.rename(self.v / regi, self.v / "M06 - Exponenciális/Elmélet/Új Hatvány.md")
        uj = "M06 - Exponenciális/Elmélet/Új Hatvány.md"
        repo.commit_machine("átnevezve", {"Mos-Kor": "ATNEV-20261002-120000"}, [regi, uj])
        self.aktiv("2000-01-01", "valami.md", 10)             # a tracker legkorábbi napja: az átnevezés „azóta” történt
        self.aktiv("2026-10-01", regi, 600)
        self.aktiv("2026-10-02", uj, 300)
        atnevezes._GYORSITOTAR.clear()
        jel, r = self.adatok().tema_jel(uj, NAP, MOST)
        self.assertEqual(jel.tanult_perc, 15.0)
        self.assertEqual(r["aliasok"], [regi])

    def test_atnevezes_kovetes_kikapcsolva(self):
        regi = "M06 - Exponenciális/Elmélet/Régi Hatvány.md"
        szoveg = (self.root / "config" / "os.toml").read_text(encoding="utf-8").replace(
            "atnevezes_kovetes = true", "atnevezes_kovetes = false")
        (self.root / "config" / "os.toml").write_text(szoveg, encoding="utf-8")
        from core import config
        cfg2 = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.root.parent / "home")})
        self.aktiv("2026-10-01", regi, 600)
        a = adat.Adatok(cfg2, self.ix, MOST)
        self.assertEqual(a.terkep().aliasok("x.md"), {"x.md"})


class KvizTest(Alap):
    def test_kviz_az_illesztobol_az_ablakra_es_a_temara(self):
        self.kviz(KvizEredmeny(T1, MOST - timedelta(days=1), 3, 4), KvizEredmeny(T2, MOST - timedelta(days=2), 1, 4),
                  KvizEredmeny(T1, MOST - timedelta(days=60), 4, 4))
        jel, r = self.adatok().tema_jel(T1, NAP, MOST)
        self.assertEqual(len(jel.kviz), 1)
        self.assertAlmostEqual(jel.kviz[0][0], 1.0)
        self.assertEqual(jel.kviz[0][1:], (3, 4))
        self.assertEqual(jel.utolso_tanulas_nap, 1)
        self.assertEqual(r["kviz"]["db"], 1)

    def test_nincs_forras_nincs_adat_jelzessel(self):
        a = self.adatok()
        a.tema_jel(T1, NAP, MOST)
        self.assertFalse(a.adatok["kviz"]["van"])
        self.assertIn("nincs kvíz-adatforrás", a.adatok["kviz"]["ok"])

    def test_hibas_forras_figyelmeztetes(self):
        forrasok.regisztral_kviz_forras("rossz", lambda cfg, tol, ig: 1 / 0)
        a = self.adatok()
        a.tema_jel(T1, NAP, MOST)
        self.assertTrue(any("kvíz-forrás" in f for f in a.figyelmeztetesek))


class CsakOlvasTest(Alap):
    def test_semmi_nem_valtozik_a_vaultban_es_az_adatbazisokban(self):
        self.kartyak(T1, ("c-00000001", "Mi a hatvány?", "szorzás"))
        self.valasz("c-00000001", 3, MOST.astimezone(UTC) - timedelta(days=1))
        self.aktiv("2026-10-02", T1, 600)
        self.kviz(KvizEredmeny(T1, MOST - timedelta(days=1), 3, 4))
        db = [self.cfg.path("tanulas_db"), self.cfg.path("szemelyes") / "pos.sqlite"]
        elotte = (fa_lenyomat(self.v), [hashlib.sha1(p.read_bytes()).hexdigest() for p in db])
        a = self.adatok()
        for d in a.dolgozatok():
            a.temak(d["kotes"].jegyzet)
        for t in (T1, T2, T3):
            a.tema_jel(t, NAP, MOST)
        a.esedekes_napra([T1], [DOLGOZAT_NAP])
        self.assertEqual((fa_lenyomat(self.v), [hashlib.sha1(p.read_bytes()).hexdigest() for p in db]), elotte)


class FelidezesTest(unittest.TestCase):
    """A `utemezo.felidezes` a py-fsrs saját felidézését adja (nem másolt képlet)."""

    def test_az_fsrs_szel_egyezik_es_az_uj_kartya_nulla(self):
        import fsrs
        sched = fsrs.Scheduler()
        t0 = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
        card, _ = sched.review_card(fsrs.Card(), fsrs.Rating.Good, review_datetime=t0)
        a = {"allapot": int(card.state), "lepes": card.step, "stabilitas": card.stability, "nehezseg": card.difficulty,
             "esedekes": card.due.isoformat(), "utolso": card.last_review.isoformat()}
        for nap in (0, 1, 5, 30):
            t = t0 + timedelta(days=nap)
            self.assertAlmostEqual(utemezo.felidezes(a, t), sched.get_card_retrievability(card, t), places=9)
        self.assertGreater(utemezo.felidezes(a, t0 + timedelta(days=1)), utemezo.felidezes(a, t0 + timedelta(days=30)))
        self.assertEqual(utemezo.felidezes({"allapot": 0, "lepes": None, "stabilitas": None, "nehezseg": None,
                                            "esedekes": t0.isoformat(), "utolso": None}, t0), 0.0)

    def test_allapot_nelkuli_nem_uj_kartya_nulla(self):
        self.assertEqual(utemezo.felidezes({"allapot": 2, "stabilitas": None, "utolso": None, "lepes": None, "nehezseg": None,
                                            "esedekes": None}, datetime(2026, 10, 1, tzinfo=UTC)), 0.0)


if __name__ == "__main__":
    unittest.main()
