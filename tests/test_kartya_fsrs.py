"""C23a: az FSRS-ütemezés és a szinkron (`modulok/kartya/utemezo.py`, `szinkron.py`; `docs/C23-TERV.md` 2–3.).

Ütemezés, válasznapló, visszavonás, esedékesek — és a fő ígéret: **a kártya szövegének szerkesztése nem nullázza a
történetét** (az állapot az azonosítóhoz kötött). Álvaulton és ál-`var/`-ban; a fuzz kikapcsolva (determinisztikus)."""
import json
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

import fsrs

from core import tanulas_db
from modulok.kartya import formatum as f
from modulok.kartya import szinkron, utemezo
from tests.helpers import alg_core, ir, tmpdir

T0 = datetime(2026, 10, 4, 10, 0, 0, tzinfo=timezone.utc)
MAPPA = "ATTCHMNTS - cards"


def kiserojegyzet(*kartyak: tuple[str, str, str]) -> str:
    return f.ir([f.Kartya(k, v, a, "Forrás#^m-1a2b") for a, k, v in kartyak], ["Forrás"])


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.sched = utemezo.utemezo(self.cfg, fuzz=False)

    def jegyzet(self, nev: str, *kartyak) -> None:
        ir(self.v, f"{MAPPA}/{nev}.md", kiserojegyzet(*kartyak))

    def sor(self, azon: str) -> dict:
        with tanulas_db.olvaso(self.cfg) as c:
            return dict(c.execute("SELECT * FROM kartya WHERE azon = ?", (azon,)).fetchone())

    def naplo(self, azon: str) -> list[dict]:
        with tanulas_db.olvaso(self.cfg) as c:
            return [dict(r) for r in c.execute("SELECT * FROM valasz WHERE kartya = ? ORDER BY id", (azon,))]


class UtemezesTest(Alap):
    def setUp(self):
        super().setUp()
        self.jegyzet("Forrás — kártyák", ("c-00000001", "Mi a q?", "a hányados"))
        szinkron.szinkron(self.cfg, most=T0)

    def test_uj_kartya(self):
        s = self.sor("c-00000001")
        self.assertEqual((s["allapot"], s["esedekes"], s["eredet"]), (0, T0.isoformat(), "kezi"))

    def test_egyezik_a_py_fsrs_szel(self):
        """A tárolt állapot ugyanaz, amit a py-fsrs közvetlenül ad (Good, Good, Again, Good, Easy)."""
        card = fsrs.Card(card_id=1)
        t = T0
        for i, jegy in enumerate((3, 3, 1, 3, 4)):
            card, _ = self.sched.review_card(card, fsrs.Rating(jegy), review_datetime=t)
            a = utemezo.valaszol(self.cfg, "c-00000001", jegy, ms=1500 + i, most=t, sched=self.sched)
            self.assertEqual((a["allapot"], a["lepes"], a["stabilitas"], a["nehezseg"], a["esedekes"], a["utolso"]),
                             (int(card.state), card.step, card.stability, card.difficulty,
                              card.due.isoformat(), card.last_review.isoformat()), f"{i}. válasz")
            t = card.due + timedelta(hours=1)
        s = self.sor("c-00000001")
        self.assertEqual(s["esedekes"], card.due.isoformat())

    def test_good_az_elso_lepesre_easy_ismetlesbe(self):
        a = utemezo.valaszol(self.cfg, "c-00000001", 3, most=T0, sched=self.sched)
        self.assertEqual((a["allapot"], a["lepes"]), (1, 1))
        self.assertEqual(a["esedekes"], (T0 + timedelta(minutes=10)).isoformat())
        b = utemezo.valaszol(self.cfg, "c-00000001", 4, most=T0 + timedelta(minutes=10), sched=self.sched)
        self.assertEqual(b["allapot"], 2)
        self.assertGreaterEqual(datetime.fromisoformat(b["esedekes"]) - (T0 + timedelta(minutes=10)), timedelta(days=1))

    def test_again_ismetlesbol_ujratanulas(self):
        utemezo.valaszol(self.cfg, "c-00000001", 4, most=T0, sched=self.sched)
        a = utemezo.valaszol(self.cfg, "c-00000001", 1, most=T0 + timedelta(days=10), sched=self.sched)
        self.assertEqual((a["allapot"], a["lepes"]), (3, 0))

    def test_naplo_elotte_utana(self):
        utemezo.valaszol(self.cfg, "c-00000001", 3, ms=2100, most=T0, sched=self.sched)
        n = self.naplo("c-00000001")
        self.assertEqual(len(n), 1)
        self.assertEqual((n[0]["jegy"], n[0]["ms"], n[0]["forras"], n[0]["mikor"]), (3, 2100, "ismetles", T0.isoformat()))
        self.assertEqual(json.loads(n[0]["elotte"])["allapot"], 0)
        self.assertEqual(json.loads(n[0]["utana"])["lepes"], 1)

    def test_visszavonas_pontos_es_lancolhato(self):
        elso = {k: self.sor("c-00000001")[k] for k in utemezo.MEZOK}
        utemezo.valaszol(self.cfg, "c-00000001", 3, most=T0, sched=self.sched)
        kozep = {k: self.sor("c-00000001")[k] for k in utemezo.MEZOK}
        utemezo.valaszol(self.cfg, "c-00000001", 1, most=T0 + timedelta(minutes=10), sched=self.sched)
        self.assertEqual(utemezo.visszavon(self.cfg, "c-00000001"), kozep)
        self.assertEqual({k: self.sor("c-00000001")[k] for k in utemezo.MEZOK}, kozep)
        self.assertEqual(utemezo.visszavon(self.cfg, "c-00000001"), elso)
        self.assertEqual({k: self.sor("c-00000001")[k] for k in utemezo.MEZOK}, elso)
        self.assertIsNone(utemezo.visszavon(self.cfg, "c-00000001"))
        self.assertTrue(all(n["visszavonva"] for n in self.naplo("c-00000001")))

    def test_hibas_jegy_es_ismeretlen_kartya(self):
        with self.assertRaises(ValueError):
            utemezo.valaszol(self.cfg, "c-00000001", 5, most=T0)
        with self.assertRaises(ValueError):
            utemezo.valaszol(self.cfg, "c-ffffffff", 3, most=T0)

    def test_felfuggesztett_nem_ertekelheto(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("UPDATE kartya SET felfuggesztve = 1")
        with self.assertRaises(ValueError):
            utemezo.valaszol(self.cfg, "c-00000001", 3, most=T0)

    def test_elorejelzes_nem_ir(self):
        e = utemezo.elorejelzes(self.cfg, "c-00000001", most=T0, sched=self.sched)
        self.assertEqual((e[1], e[2], e[3]), (60, 330, 600))           # 1 perc, (1+10)/2 perc, 10 perc
        self.assertGreaterEqual(e[4], 86400)
        self.assertEqual(self.sor("c-00000001")["allapot"], 0)
        self.assertEqual(self.naplo("c-00000001"), [])

    def test_lepesek(self):
        self.assertEqual(utemezo.lepesek(["30s", "1m", "1.5h", "2d"]),
                         (timedelta(seconds=30), timedelta(minutes=1), timedelta(hours=1.5), timedelta(days=2)))
        with self.assertRaises(ValueError):
            utemezo.lepesek(["tíz perc"])


class EsedekesekTest(Alap):
    def setUp(self):
        super().setUp()
        self.jegyzet("A — kártyák", *[(f"c-0000000{i}", f"K{i}?", f"V{i}") for i in range(1, 6)])
        szinkron.szinkron(self.cfg, most=T0)

    def test_esedekes_elol_ujak_limittel(self):
        utemezo.valaszol(self.cfg, "c-00000003", 3, most=T0, sched=self.sched)          # 10 perc múlva esedékes
        most = T0 + timedelta(minutes=11)
        lista = [k["azon"] for k in utemezo.esedekesek(self.cfg, most=most, uj_limit=3)]
        self.assertEqual(lista[0], "c-00000003")
        self.assertEqual(lista[1:], ["c-00000001", "c-00000002"])         # 3 új a limit − 1 ma már elkezdett
        self.assertEqual(len(utemezo.esedekesek(self.cfg, most=T0 + timedelta(minutes=1), uj_limit=0)), 0)

    def test_torolt_es_felfuggesztett_kimarad(self):
        with tanulas_db.iro(self.cfg) as c:
            c.execute("UPDATE kartya SET felfuggesztve = 1 WHERE azon = 'c-00000001'")
            c.execute("UPDATE kartya SET torolve = 't' WHERE azon = 'c-00000002'")
        lista = [k["azon"] for k in utemezo.esedekesek(self.cfg, most=T0, uj_limit=10)]
        self.assertEqual(lista, ["c-00000003", "c-00000004", "c-00000005"])

    def test_nincs_db(self):
        with tmpdir() as t:
            cfg, _, _ = alg_core(t)
            self.assertEqual(utemezo.esedekesek(cfg, most=T0), [])
            self.assertFalse(tanulas_db.ut(cfg).exists())


class SzinkronTest(Alap):
    def test_szovegszerkesztes_utan_megmarad_a_tortenet(self):
        self.jegyzet("Forrás — kártyák", ("c-00000001", "Mi a q?", "a hányados"))
        szinkron.szinkron(self.cfg, most=T0)
        utemezo.valaszol(self.cfg, "c-00000001", 3, ms=1000, most=T0, sched=self.sched)
        utemezo.valaszol(self.cfg, "c-00000001", 3, ms=1000, most=T0 + timedelta(minutes=10), sched=self.sched)
        elotte = {k: self.sor("c-00000001")[k] for k in utemezo.MEZOK}
        self.jegyzet("Forrás — kártyák", ("c-00000001", "Mi a mértani sorozat hányadosa?", "q = a(n+1)/a(n)"))
        jel = szinkron.szinkron(self.cfg, most=T0 + timedelta(hours=1))
        self.assertEqual((jel["szoveg_valtozott"], jel["uj"], jel["torolt"]), (1, 0, 0))
        s = self.sor("c-00000001")
        self.assertEqual({k: s[k] for k in utemezo.MEZOK}, elotte)
        self.assertEqual((s["kerdes"], s["valasz"]), ("Mi a mértani sorozat hányadosa?", "q = a(n+1)/a(n)"))
        self.assertEqual(s["szoveg_valtozott"], (T0 + timedelta(hours=1)).isoformat())
        self.assertEqual(len(self.naplo("c-00000001")), 2)

    def test_masik_fajlba_koltozes(self):
        self.jegyzet("A — kártyák", ("c-00000001", "K?", "V"))
        szinkron.szinkron(self.cfg, most=T0)
        utemezo.valaszol(self.cfg, "c-00000001", 4, most=T0, sched=self.sched)
        (self.v / MAPPA / "A — kártyák.md").unlink()
        self.jegyzet("B — kártyák", ("c-00000001", "K?", "V"))
        jel = szinkron.szinkron(self.cfg, most=T0 + timedelta(hours=1))
        self.assertEqual(jel["torolt"], 0)
        s = self.sor("c-00000001")
        self.assertEqual((s["jegyzet"], s["allapot"], s["torolve"]), (f"{MAPPA}/B — kártyák.md", 2, None))

    def test_torles_sirko_es_feltamadas(self):
        self.jegyzet("A — kártyák", ("c-00000001", "K1?", "V"), ("c-00000002", "K2?", "V"))
        szinkron.szinkron(self.cfg, most=T0)
        utemezo.valaszol(self.cfg, "c-00000002", 4, most=T0, sched=self.sched)
        self.jegyzet("A — kártyák", ("c-00000001", "K1?", "V"))
        jel = szinkron.szinkron(self.cfg, most=T0 + timedelta(hours=1))
        self.assertEqual(jel["torolt"], 1)
        self.assertIsNotNone(self.sor("c-00000002")["torolve"])
        with tanulas_db.olvaso(self.cfg) as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT ujjlenyomat, kartya FROM sirko")],
                             [(f.ujjlenyomat("K2?", "Forrás#^m-1a2b"), "c-00000002")])
        self.jegyzet("A — kártyák", ("c-00000001", "K1?", "V"), ("c-00000002", "K2?", "V"))   # pl. visszavonás
        jel = szinkron.szinkron(self.cfg, most=T0 + timedelta(hours=2))
        self.assertEqual(jel["feltamadt"], 1)
        s = self.sor("c-00000002")
        self.assertEqual((s["torolve"], s["allapot"]), (None, 2))

    def test_reszleges_szinkron_csak_a_sajat_fajljait_torli(self):
        self.jegyzet("A — kártyák", ("c-00000001", "K1?", "V"))
        self.jegyzet("B — kártyák", ("c-00000002", "K2?", "V"))
        szinkron.szinkron(self.cfg, most=T0)
        rp = f"{MAPPA}/A — kártyák.md"
        jel = szinkron.szinkron(self.cfg, {rp: f.elemez(kiserojegyzet())}, most=T0 + timedelta(hours=1))
        self.assertEqual(jel["torolt"], 1)
        self.assertIsNotNone(self.sor("c-00000001")["torolve"])
        self.assertIsNone(self.sor("c-00000002")["torolve"])

    def test_torles_max_or(self):
        self.jegyzet("A — kártyák", *[(f"c-000000{i:02d}", f"K{i}?", "V") for i in range(5)])
        szinkron.szinkron(self.cfg, most=T0)
        (self.v / MAPPA / "A — kártyák.md").unlink()
        with mock.patch.object(szinkron, "beallitas", return_value={"torles_max": 3}):
            jel = szinkron.szinkron(self.cfg, most=T0 + timedelta(hours=1))
        self.assertEqual(jel["torolt"], 0)
        self.assertIn("5 kártya", jel["figyelmeztetes"])
        self.assertIsNone(self.sor("c-00000000")["torolve"])

    def test_duplikalt_azonosito_ket_fajlban(self):
        self.jegyzet("A — kártyák", ("c-00000001", "Első?", "V"))
        self.jegyzet("B — kártyák", ("c-00000001", "Másolat?", "V"))
        jel = szinkron.szinkron(self.cfg, most=T0)
        self.assertEqual(jel["uj"], 1)
        self.assertEqual([h["fajta"] for h in jel["hibak"]], ["duplikalt"])
        self.assertEqual(self.sor("c-00000001")["kerdes"], "Első?")

    def test_a_vaultot_nem_irja(self):
        self.jegyzet("A — kártyák", ("c-00000001", "K?", "V"))
        elotte = {p: p.read_bytes() for p in self.v.rglob("*") if p.is_file()}
        szinkron.szinkron(self.cfg, most=T0)
        utemezo.valaszol(self.cfg, "c-00000001", 3, most=T0, sched=self.sched)
        self.assertEqual({p: p.read_bytes() for p in self.v.rglob("*") if p.is_file()}, elotte)

    def test_foglalt_azonositok(self):
        self.jegyzet("A — kártyák", ("c-00000001", "K?", "V"))
        szinkron.szinkron(self.cfg, most=T0)
        self.assertEqual(szinkron.foglalt_azonositok(self.cfg, {"x": f.elemez(kiserojegyzet(("c-00000009", "K", "V")))}),
                         {"c-00000001", "c-00000009"})


if __name__ == "__main__":
    unittest.main()
