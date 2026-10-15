"""A C28 felkészültség-forrás a C29 javaslat-horgán (C28a): a napi terv napjaiból tanulásiblokk-javaslat; a beépített forrás
arra a dolgozatra elnémul; **a naptárba csak jóváhagyásra kerül esemény** (D12)."""
import unittest
from datetime import timedelta, timezone
from unittest import mock

from core import naptar, naptar_javaslat
from core.felkeszultseg import forras
from core.naptar_javaslat import Javaslatok
from core.naptar_seged import Seged
from tests.felkeszultseg_segedek import Alap as FAlap, FAJLOK, FELK, MOST, T1, T2
from tests.naptar_segedek import esemeny as ev

UTC = timezone.utc


class Alap(FAlap):
    def setUp(self):
        super().setUp()
        self.publikalt = []
        self.j = Javaslatok(self.cfg, Seged(self.cfg), publish=lambda e, **k: self.publikalt.append(e), mikor=lambda: MOST,
                            index=self.ix)

    def irasok(self):
        return self.al.olvas().get("esemeny_irasok", [])


class KeveredTest(Alap):
    ESEMENYEK = FAlap.ESEMENYEK + [ev("d2", "HAT", "2026-10-09T10:00:00+02:00", "2026-10-09T10:45:00+02:00", "Fizika dolgozat")]

    def test_a_beepitett_forras_csak_a_felkeszultsegi_forrassal_rendelkezo_dolgozatra_nemul_el(self):
        self.j.frissit()
        k = {}
        for x in self.j.lista():
            k.setdefault(x["forras"], set()).add(x["cim"].split(" — ")[0])
        self.assertEqual(k["felkeszultseg"], {"Tanulás: Matematika"})
        self.assertEqual(k["alap"], {"Tanulás: Fizika"})


class ForrasTest(Alap):
    def test_a_forras_regisztralva_van(self):
        self.assertIn("felkeszultseg", naptar_javaslat.FORRASOK)

    def test_javaslat_a_terv_minden_napjara_a_szabad_esti_savba(self):
        self.assertEqual(self.j.frissit(), {"uj": 4})
        lista = self.j.lista()
        self.assertEqual([x["nap"] for x in lista], ["2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06"])
        self.assertEqual({x["forras"] for x in lista}, {"felkeszultseg"})
        self.assertTrue(all(x["perc"] == 45 for x in lista))
        self.assertEqual(lista[1]["kezd"], "2026-10-04T16:00:00+02:00")
        self.assertTrue(lista[0]["cim"].startswith("Tanulás: Matematika — "))
        self.assertIn("Hatvány", lista[0]["cim"])
        self.assertIn("nincs adat", lista[0]["indok"])
        self.assertIn("0 / 3", lista[0]["indok"])
        self.assertEqual({x["dolgozat"] for x in lista}, {self.adatok().dolgozatok()[0]["azon"]})

    def test_a_beepitett_forras_arra_a_dolgozatra_elnemul(self):
        self.j.frissit()
        self.assertEqual({x["forras"] for x in self.j.lista(csak_nyitott=False)}, {"felkeszultseg"})

    def test_felkeszulesi_jegyzet_nelkul_a_beepitett_forras_dolgozik(self):
        class NincsJegyzet(Alap):
            FAJLOK = {k: v for k, v in FAJLOK.items() if k != FELK}
        t = NincsJegyzet()
        t.setUp()
        self.addCleanup(t.doCleanups)
        t.j.frissit()
        self.assertEqual({x["forras"] for x in t.j.lista()}, {"alap"})

    def test_nincs_index_a_forras_ures_es_nem_dob(self):
        j = Javaslatok(self.cfg, Seged(self.cfg), publish=lambda e, **k: None, mikor=lambda: MOST)
        j.frissit()
        self.assertEqual({x["forras"] for x in j.lista()}, {"alap"})

    def test_hibas_index_a_forras_ures(self):
        with mock.patch.object(self.ix, "allapot", side_effect=RuntimeError("elromlott")):
            self.j.frissit()
        self.assertEqual({x["forras"] for x in self.j.lista()}, {"alap"})

    def test_naptarba_csak_jovahagyasra_kerul_esemeny(self):
        self.j.frissit()
        self.assertEqual(self.irasok(), [])
        elso = self.j.lista()[0]
        r = self.j.jovahagy(elso["id"])
        self.assertEqual(r["allapot"], "beirva")
        self.assertEqual(len(self.irasok()), 1)
        self.assertEqual(self.irasok()[0]["javaslat"], elso["id"])
        beirt = [e for e in self.al.olvas()["esemenyek"] if e["azon"] == self.irasok()[0]["azon"]][0]
        self.assertEqual(beirt["cim"], elso["cim"])

    def test_elvetett_nem_ter_vissza(self):
        self.j.frissit()
        elso = self.j.lista()[0]
        self.j.elvet(elso["id"])
        self.assertEqual(self.j.frissit(), {"uj": 0})
        self.assertNotIn(elso["id"], [x["id"] for x in self.j.lista()])

    def test_a_meglevo_tanulasi_blokk_napjara_nincs_javaslat(self):
        self.al.modosit(lambda m: m["esemenyek"].append(ev("t1", "TAN", "2026-10-05T17:00:00+02:00", "2026-10-05T18:00:00+02:00", "Matek gyakorlás")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        self.j.frissit()
        self.assertEqual([x["nap"] for x in self.j.lista()], ["2026-10-03", "2026-10-04", "2026-10-06"])

    def test_foglalt_savot_kikeruli(self):
        self.al.modosit(lambda m: m["esemenyek"].append(ev("o1", "ORA", "2026-10-04T16:00:00+02:00", "2026-10-04T17:00:00+02:00", "Fizika")))
        naptar.szinkron(self.cfg, Seged(self.cfg), most=MOST)
        self.j.frissit()
        self.assertEqual({x["nap"]: x["kezd"] for x in self.j.lista()}["2026-10-04"], "2026-10-04T17:00:00+02:00")

    def test_max_darab_a_legkorabbi_napokat_tartja(self):
        szoveg = (self.root / "config" / "os.toml").read_text(encoding="utf-8").replace("max_darab = 6", "max_darab = 2")
        (self.root / "config" / "os.toml").write_text(szoveg, encoding="utf-8")
        from core import config
        cfg2 = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.root.parent / "home"), **self.al.env()})
        j = Javaslatok(cfg2, Seged(cfg2), publish=lambda e, **k: None, mikor=lambda: MOST, index=self.ix)
        j.frissit()
        self.assertEqual([x["nap"] for x in j.lista()], ["2026-10-03", "2026-10-04"])

    def test_a_gyenge_tema_a_cimben_es_az_indokban(self):
        self.kartyak(T2, ("c-00000011", "Mi a gyök?", "x"), ("c-00000012", "Mi a négyzetgyök?", "y"),
                     ("c-00000013", "Mi a köbgyök?", "z"), most=MOST.astimezone(UTC) - timedelta(days=60))
        for a in ("c-00000011", "c-00000012", "c-00000013"):
            self.valasz(a, 1, MOST.astimezone(UTC) - timedelta(days=60))
        self.j.frissit()
        x = self.j.lista()[0]
        self.assertIn("Gyökvonás", x["cim"])
        self.assertIn("gyenge", x["indok"].lower())

    def test_a_lezart_dolgozat_nem_kap_javaslatot(self):
        j = Javaslatok(self.cfg, Seged(self.cfg), publish=lambda e, **k: None, mikor=lambda: MOST + timedelta(days=5), index=self.ix)
        j.frissit()
        self.assertEqual(j.lista(), [])

    def test_a_tavoli_dolgozat_nem_kap_javaslatot(self):
        """Az `elorenezes_nap` (10) fölötti távolságú dolgozatra még nincs javaslat (a beépített forrás sem ad)."""
        j = Javaslatok(self.cfg, Seged(self.cfg), publish=lambda e, **k: None, mikor=lambda: MOST - timedelta(days=11), index=self.ix)
        j.frissit()
        self.assertEqual(j.lista(), [])


if __name__ == "__main__":
    unittest.main()
