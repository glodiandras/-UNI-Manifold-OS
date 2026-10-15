"""A higiénia-riport háttérszolgáltatása (C30a; 2. és 10. döntés, D8): a riport indexből, háttérben számolódik, a tevékenység
alatt szünetel, a kapcsoló ki → nem fut; a „új tételek” az állapotfájl szerint. Álvaulton, hamis órával és aktivitással."""
import os
import threading
import time
import unittest

from core import vezerlo
from core.asszisztens.allapot import Allapot
from core.asszisztens.szolgalat import HigieniaSzolgalat
from core.higienia import Higienia
from core.tulajdonsagok import Tulajdonsagok
from tests.helpers import ir, tmpdir
from tests.index_segedek import alvault, index_indit, var_ra

KERET = "---\nTags:\n  - Mathematics\nSource:\nStatus:\nNN:\nCanvas:\n---\n"


def jo(szoveg: str = "") -> str:
    return KERET + szoveg


FAJLOK = {"A.md": jo("[[Nincs]] és [[B]]\n"), "B.md": jo("[[A]]\n"), "C.md": jo("[[B]] [[A]]\n")}


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.indit_vault()

    def indit_vault(self, fajlok=None):
        cfg, self.v = alvault(self._t.name, FAJLOK if fajlok is None else fajlok)
        self.cfg = cfg
        self.ix, _ = index_indit(cfg)
        self.addCleanup(self.ix.leallit)
        self.t = 1000.0                                  # hamis monotonic óra
        self.aktiv = False
        self.esemenyek: list[dict] = []
        self.sz = self.uj_szolgalat()
        self.addCleanup(self.sz.leallit)

    def uj_szolgalat(self, **kw) -> HigieniaSzolgalat:
        h = Higienia(self.cfg, self.ix, Tulajdonsagok(self.cfg, self.ix))
        return HigieniaSzolgalat(self.cfg, self.ix, h, Allapot(self.cfg), aktiv=lambda: self.aktiv,
                                 publish=self.esemenyek.append, ido=lambda: self.t, szunet_mp=0.01, **kw)

    def modosit(self, ut, szoveg):
        ir(self.v, ut, szoveg)
        self.assertTrue(self.ix.frissit([ut]))


class TickTest(Alap):
    def test_szamol_es_gyorsitotarazza(self):
        self.assertFalse(self.sz.osszegzes()["kesz"])
        self.assertEqual(self.sz.tick(), "szamolt")
        o = self.sz.osszegzes()
        self.assertTrue(o["kesz"])
        self.assertEqual(o["osszesites"]["torott_link"], 1)
        self.assertEqual(o["ossz"], len(self.sz.riport["tetelek"]))
        self.assertEqual(self.sz.tick(), "nincs_valtozas")

    def test_kapcsolo_ki_nem_szamol(self):
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False})
        self.assertEqual(self.sz.tick(), "ki")
        self.assertFalse(self.sz.osszegzes()["kapcsolo"])
        self.assertFalse(self.sz.osszegzes()["kesz"])
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": True})
        self.assertEqual(self.sz.tick(), "szamolt")

    def test_aktiv_hasznalat_alatt_nem_szamol(self):
        self.aktiv = True
        self.assertEqual(self.sz.tick(), "aktiv")
        self.assertFalse(self.sz.osszegzes()["kesz"])
        self.aktiv = False
        self.assertEqual(self.sz.tick(), "szamolt")

    def test_az_index_valtozasara_ujraszamol_de_legalabb_a_min_kozzel(self):
        self.sz.tick()
        self.modosit("C.md", jo("[[B]] [[A]] [[Újabb nincs]]\n"))
        self.assertEqual(self.sz.tick(), "koran")                                  # 60 s nem telt el
        self.assertEqual(self.sz.osszegzes()["osszesites"]["torott_link"], 1)
        self.t += 61
        self.assertEqual(self.sz.tick(), "szamolt")
        self.assertEqual(self.sz.osszegzes()["osszesites"]["torott_link"], 2)

    def test_a_min_koz_a_beallitasbol_jon(self):
        self.cfg.data.setdefault("asszisztens", {})["higienia_min_koz_mp"] = 5
        self.sz.tick()
        self.modosit("C.md", jo("[[B]] [[A]] [[Újabb nincs]]\n"))
        self.t += 6
        self.assertEqual(self.sz.tick(), "szamolt")

    def test_nem_kesz_index_nem_szamol(self):
        self.ix._kesz.clear()
        self.ix.allapot_d["kesz"] = False
        self.assertEqual(self.sz.tick(), "nem_kesz")

    def test_hiba_nem_dobja_a_tickot_es_ujraprobal(self):
        eredeti = self.sz.higienia.riport
        self.sz.higienia.riport = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("váratlan"))
        self.assertEqual(self.sz.tick(), "hiba")
        self.assertIn("váratlan", self.sz.osszegzes()["hiba"])
        self.sz.higienia.riport = eredeti
        self.assertEqual(self.sz.tick(), "koran")
        self.t += 61
        self.assertEqual(self.sz.tick(), "szamolt")
        self.assertIsNone(self.sz.osszegzes()["hiba"])

    def test_ws_esemeny_a_kesz_riportra(self):
        self.sz.tick()
        self.assertEqual([e["tipus"] for e in self.esemenyek], ["asszisztens_valtozas"])
        self.assertEqual(self.esemenyek[0]["mi"], "higienia")


class SzunetTest(Alap):
    def futtat(self):
        """A számítás egy szálon, a tick aktivitás-vizsgálata nélkül (a számítás közben bekövetkező aktivitás)."""
        self.kesz = threading.Event()

        def fut():
            self.sz.szamol()
            self.kesz.set()
        self.szal = threading.Thread(target=fut, daemon=True)
        self.szal.start()

    def test_szamitas_kozben_aktivitasra_szunetel_majd_folytatja(self):
        self.aktiv = True
        self.futtat()
        self.assertTrue(var_ra(lambda: self.sz.osszegzes()["szunetel"], 3))
        time.sleep(0.2)
        self.assertFalse(self.kesz.is_set())                         # amíg az aktivitás tart, nem fejezi be
        self.assertFalse(self.sz.osszegzes()["kesz"])
        self.aktiv = False
        self.assertTrue(self.kesz.wait(5))
        self.assertTrue(self.sz.osszegzes()["kesz"])
        self.assertFalse(self.sz.osszegzes()["szunetel"])

    def test_a_szunet_alatt_az_egy_jegyzetes_lekerdezes_nem_akad(self):
        self.aktiv = True
        self.futtat()
        self.assertTrue(var_ra(lambda: self.sz.osszegzes()["szunetel"], 3))
        t0 = time.monotonic()
        r = self.sz.higienia.riport("A.md")                          # a jobb panel kérése: friss, soron belüli, nem a szolgáltatásé
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertEqual(r["osszesites"]["torott_link"], 1)
        self.aktiv = False
        self.assertTrue(self.kesz.wait(5))

    def test_leallitas_megszakitja_a_szunetet(self):
        self.aktiv = True
        self.futtat()
        self.assertTrue(var_ra(lambda: self.sz.osszegzes()["szunetel"], 3))
        t0 = time.monotonic()
        self.sz.leallit()
        self.szal.join(3)
        self.assertFalse(self.szal.is_alive())
        self.assertLess(time.monotonic() - t0, 3)
        self.assertFalse(self.sz.osszegzes()["kesz"])

    def test_a_kapcsolo_kikapcsolasa_megszakitja_a_szunetet(self):
        self.aktiv = True
        self.futtat()
        self.assertTrue(var_ra(lambda: self.sz.osszegzes()["szunetel"], 3))
        vezerlo.kapcsolo_ir(self.cfg, {"asszisztens": False})
        self.assertTrue(self.kesz.wait(5))
        self.assertFalse(self.sz.osszegzes()["kesz"])


class UjTetelekTest(Alap):
    def test_az_elso_riport_csendes_alapvonal(self):
        self.sz.tick()
        o = self.sz.osszegzes()
        self.assertEqual(o["uj"], 0)
        self.assertTrue(o["alapvonal"])
        self.assertEqual(o["uj_tetelek"], [])
        self.assertIsNotNone(Allapot(self.cfg).olvas()["higienia_latva"])

    def test_uj_tetel_szamlalas_es_latva(self):
        self.sz.tick()
        self.modosit("C.md", jo("[[B]] [[A]] [[Újabb nincs]]\n"))
        self.t += 61
        self.sz.tick()
        o = self.sz.osszegzes()
        self.assertEqual(o["uj"], 1)
        self.assertFalse(o["alapvonal"])
        self.assertEqual([(x["ut"], x["fajta"]) for x in o["uj_tetelek"]], [("C.md", "torott_link")])
        r = self.sz.latva()
        self.assertEqual(r["uj"], 0)
        self.assertEqual(self.sz.osszegzes()["uj"], 0)
        self.modosit("C.md", jo("[[B]] [[A]] [[Újabb nincs]] [[Megint nincs]]\n"))
        self.t += 61
        self.sz.tick()
        self.assertEqual(self.sz.osszegzes()["uj"], 1)

    def test_a_latva_allapot_ujrainditas_utan_is_megvan(self):
        self.sz.tick()
        self.modosit("C.md", jo("[[B]] [[A]] [[Újabb nincs]]\n"))
        self.t += 61
        self.sz.tick()
        self.sz.latva()
        self.sz2 = self.uj_szolgalat()
        self.addCleanup(self.sz2.leallit)
        self.assertEqual(self.sz2.tick(), "szamolt")
        self.assertEqual(self.sz2.osszegzes()["uj"], 0)

    def test_javitott_tetel_eltunik_es_nem_ujkent_jon_vissza_ha_ugyanaz(self):
        self.sz.tick()
        self.modosit("A.md", jo("[[B]]\n"))                          # a törött link javítva
        self.t += 61
        self.sz.tick()
        self.assertEqual(self.sz.osszegzes()["ossz"], 0)
        self.assertEqual(self.sz.osszegzes()["uj"], 0)

    def test_a_latva_riport_nelkul_409(self):
        from core.utvonalak import HttpError
        with self.assertRaises(HttpError) as e:
            self.sz.latva()
        self.assertEqual(e.exception.code, 409)

    def test_a_ma_oldal_szakasza_csak_olvas(self):
        self.sz.tick()
        elotte = Allapot(self.cfg).ut.read_bytes()
        self.assertEqual(self.sz.ma(), {"kesz": True, "ossz": self.sz.osszegzes()["ossz"], "uj": 0})
        self.assertEqual(Allapot(self.cfg).ut.read_bytes(), elotte)


class SzalTest(Alap):
    def test_indulasi_keses_alatt_nem_szamol(self):
        sz = self.uj_szolgalat(indulasi_kesleltetes_mp=3600)
        self.addCleanup(sz.leallit)
        sz.indit()
        time.sleep(0.3)
        self.assertFalse(sz.osszegzes()["kesz"])
        t0 = time.monotonic()
        sz.leallit()
        self.assertLess(time.monotonic() - t0, 3)

    def test_kesleltetes_utan_a_szal_szamol(self):
        sz = self.uj_szolgalat(indulasi_kesleltetes_mp=0, tick_mp=0.05)
        self.addCleanup(sz.leallit)
        sz.indit()
        self.assertTrue(var_ra(lambda: sz.osszegzes()["kesz"], 10))
        sz.leallit()
        self.assertFalse(sz._szal and sz._szal.is_alive())


if __name__ == "__main__":
    unittest.main()
