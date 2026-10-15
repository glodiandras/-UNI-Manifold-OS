"""A worker ütemezője álmodellel: aktivitásjel, kötegelés, interaktív elsőbbség, távol-keret, ürítések, hűtés."""
import threading
import time
import unittest

from core.modell import beallitas as B
from core.modell.aktivitas import AKTIV, TAVOL, TETLEN
from core.modell.betolto import KeretHiba
from core.modell.hatter import Megszakitva
from core.modell.ho import Ho
from core.modell.kalibracio import Tabla
from core.modell.router import Router, RoutingHiba
from core.modell.utemezo import AUTO, INTERAKTIV, Keres, Utemezo
from tests.helpers import alg_core, tmpdir
from tests.modell_segedek import AlAktivitas, AlHatter, al_betolto, beallitas


def var(felt, mp=5.0):
    t0 = time.time()
    while not felt() and time.time() - t0 < mp:
        time.sleep(0.02)
    return felt()


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)
        self.t = Tabla(self.b.router_db)
        self.addCleanup(self.t.close)
        self.akt = AlAktivitas(TETLEN)
        self.u = None

    def utemezo(self, **hatter_kw):
        self.bt = al_betolto(self.b, **hatter_kw)
        self.ho = Ho({**self.b.ho, "alap_minta": 2, "ablak": 2}, self.t)
        self.u = Utemezo(self.b, self.bt, self.akt, Router(self.b, self.t), self.ho, tick_mp=0.02,
                         naplo=lambda s: None)
        self.addCleanup(self.u.leall)
        return self.u

    def kuld(self, k, eredmenyek):
        def fut():
            try:
                eredmenyek.append((k, self.u.bekuld(k, timeout=10)))
            except Exception as exc:  # noqa: BLE001
                eredmenyek.append((k, exc))
        th = threading.Thread(target=fut, daemon=True)
        th.start()
        return th

    def chat(self, szoveg, modell=None, feladat=None, mod=AUTO, keret=None):
        return Keres("chat", {"messages": [{"content": szoveg}]}, mod=mod, feladat=feladat,
                     modell=self.b.modell(modell) if modell else None, keret=keret)

    def generalasok(self):
        return [e[2] for e in AlHatter.naplo if e[0] == "general"]

    def fuggo_db(self, n, mp=5.0):
        """Vár, amíg pontosan `n` kérés vár az ütemezőben (T085: a beküldés sorrendje esemény, nem `sleep`)."""
        return var(lambda: len(self.u.allapot()["fuggo"]) == n, mp)

    def kor_utan(self, n=3, mp=5.0):
        """Vár, amíg az ütemező hurka még `n` döntési kört lefutott (az aktivitásjel lekérdezései számlálják): a negatív
        állítás („nem indult el”) így csak azután értékelődik, hogy az ütemező biztosan látta az állapotot (T085)."""
        n0 = self.akt.hivasok
        return var(lambda: self.akt.hivasok >= n0 + n, mp)


class AktivitasTest(Alap):
    def test_automatikus_keres_aktiv_hasznalatkor_nem_tolt_be(self):
        self.akt.allit(AKTIV)
        u = self.utemezo()
        e = []
        self.kuld(self.chat("auto", "qwen3_vl_4b"), e)
        self.assertTrue(self.fuggo_db(1))
        self.assertTrue(self.kor_utan())
        self.assertEqual(AlHatter.naplo, [])                      # nem töltött be, nem futott
        self.assertEqual(len(u.allapot()["fuggo"]), 1)
        self.akt.allit(TETLEN)
        self.assertTrue(var(lambda: e))
        self.assertEqual(self.generalasok(), ["auto"])

    def test_interaktiv_aktiv_hasznalatkor_is_fut(self):
        self.akt.allit(AKTIV)
        self.utemezo()
        e = []
        self.kuld(self.chat("kézi", "qwen3_vl_4b", mod=INTERAKTIV), e)
        self.assertTrue(var(lambda: e))
        self.assertEqual(self.generalasok(), ["kézi"])

    def test_kotegek_kozott_szunetel(self):
        u = self.utemezo()
        e = []
        k1 = self.chat("1", "qwen3_vl_4b")
        self.kuld(k1, e)
        self.assertTrue(var(lambda: e))
        self.akt.allit(AKTIV)                                        # a felhasználó visszajött
        self.kuld(self.chat("2", "qwen3_vl_4b"), e)
        self.assertTrue(self.fuggo_db(1))
        self.assertTrue(self.kor_utan())
        self.assertEqual(self.generalasok(), ["1"])
        self.akt.allit(TETLEN)
        self.assertTrue(var(lambda: len(e) == 2))
        self.assertEqual(self.generalasok(), ["1", "2"])


class KotegTest(Alap):
    def test_betoltott_modell_kerese_elobb_es_interaktiv_elsobbseg(self):
        self.akt.allit(AKTIV)
        self.utemezo()
        e = []
        self.kuld(self.chat("A0", "qwen3_vl_4b", mod=INTERAKTIV), e)   # betölti az A-t
        self.assertTrue(var(lambda: e))
        self.kuld(self.chat("B1", "qwen35_2b"), e)                      # régebbi, másik modell
        self.assertTrue(self.fuggo_db(1))
        self.kuld(self.chat("A1", "qwen3_vl_4b"), e)
        self.assertTrue(self.fuggo_db(2))
        self.kuld(self.chat("B2", "qwen35_2b"), e)
        self.assertTrue(self.fuggo_db(3))
        self.akt.allit(TETLEN)
        self.assertTrue(var(lambda: len(e) == 4))
        self.assertEqual(self.generalasok(), ["A0", "A1", "B1", "B2"])   # modellcsere csak egyszer
        self.assertEqual([x[1] for x in AlHatter.naplo if x[0] == "betolt"], ["qwen3_vl_4b", "qwen35_2b"])

    def test_interaktiv_megelozi_az_automatikust(self):
        kapu = threading.Event()
        self.utemezo(kesleltetes=kapu)
        e = []
        self.kuld(self.chat("elso", "qwen3_vl_4b"), e)                  # fut, a kapuig vár
        self.assertTrue(var(lambda: self.u.allapot()["fut"] is not None))
        self.kuld(self.chat("auto", "qwen3_vl_4b"), e)
        self.assertTrue(self.fuggo_db(1))
        self.kuld(self.chat("kezi", "qwen35_2b", mod=INTERAKTIV), e)
        self.assertTrue(self.fuggo_db(2))
        kapu.set()
        self.assertTrue(var(lambda: len(e) == 3))
        self.assertEqual(self.generalasok(), ["elso", "kezi", "auto"])


class MegszakitasTest(Alap):
    """C17: a leállított feladat folyó generálása megszakad, a várakozó kérése nem indul, a későn érkező sem."""

    def chat_feladatnak(self, szoveg, fid, modell="qwen3_vl_4b", mod=INTERAKTIV):
        k = self.chat(szoveg, modell, mod=mod)
        k.feladat_id = fid
        return k

    def test_folyo_generalas_megszakad(self):
        elindult = threading.Event()
        u = self.utemezo(folyamatos=elindult)
        e = []
        self.kuld(self.chat_feladatnak("hosszú", "F-1"), e)
        self.assertTrue(elindult.wait(5))
        self.assertEqual(u.megszakit("F-1"), 1)
        self.assertTrue(var(lambda: e))
        self.assertIsInstance(e[0][1], Megszakitva)
        self.assertIn(("megszakitva", "qwen3_vl_4b"), AlHatter.naplo)
        self.assertTrue(var(lambda: u.allapot()["fut"] is None))      # az ütemező szabad, a modell betöltve marad

    def test_varakozo_kerese_nem_indul_es_a_masik_feladate_igen(self):
        elindult = threading.Event()
        u = self.utemezo(folyamatos=elindult)
        e = []
        self.kuld(self.chat_feladatnak("fut", "F-1"), e)
        self.assertTrue(elindult.wait(5))
        self.kuld(self.chat_feladatnak("vár", "F-2"), e)
        self.assertTrue(var(lambda: len(u.allapot()["fuggo"]) == 1))
        self.assertEqual(u.allapot()["fuggo"][0]["feladat_id"], "F-2")
        self.assertEqual(u.megszakit("F-2"), 1)                       # a várakozó kérés azonnal véget ér
        self.assertTrue(var(lambda: any(isinstance(x[1], Megszakitva) for x in e)))
        self.assertEqual(u.allapot()["fuggo"], [])
        u.megszakit("F-1")
        self.assertTrue(var(lambda: len(e) == 2))
        self.assertEqual(self.generalasok(), [])                      # a „fut” kérés nem fejeződött be értékkel

    def test_keso_kerest_a_leallitott_feladattol_nem_indit(self):
        u = self.utemezo()
        u.megszakit("F-9")
        with self.assertRaises(Megszakitva):
            u.bekuld(self.chat_feladatnak("késő", "F-9"), timeout=2)
        self.assertEqual(AlHatter.naplo, [])                          # modell sem töltődött be
        e = []
        self.kuld(self.chat_feladatnak("másik", "F-10"), e)           # más feladat, azonos modell: megy
        self.assertTrue(var(lambda: e))
        self.assertEqual(self.generalasok(), ["másik"])

    def test_feladat_nelkuli_kerest_a_megszakitas_nem_erint(self):
        u = self.utemezo()
        u.megszakit("F-1")
        e = []
        self.kuld(self.chat("névtelen", "qwen3_vl_4b", mod=INTERAKTIV), e)
        self.assertTrue(var(lambda: e))
        self.assertEqual(self.generalasok(), ["névtelen"])

    def test_megszakitott_azonositok_halmaza_korlatos(self):
        u = self.utemezo()
        for i in range(300):
            u.megszakit(f"F-{i}")
        self.assertEqual(len(u._megszakitott), 256)
        self.assertNotIn("F-0", u._megszakitott)
        self.assertIn("F-299", u._megszakitott)


class KeretTest(Alap):
    def test_tavol_keret_csak_tartos_tetlensegben(self):
        self.t.rogzit("ocr_kezi", "qwen35_9b", 0.9, "v1", kalibralt=True)
        self.t.rogzit("ocr_kezi", "qwen3_vl_4b", 0.5, "v1", kalibralt=True)
        self.utemezo()
        e = []
        self.kuld(self.chat("fotó", feladat="ocr_kezi"), e)
        self.assertTrue(self.fuggo_db(1))
        self.assertTrue(self.kor_utan())
        self.assertEqual(e, [])                                        # tavolra_var: vár
        self.akt.allit(TAVOL)
        self.assertTrue(var(lambda: e))
        k, o = e[0]
        self.assertEqual((o["modell"].nev, o["keret_gb"]), ("qwen35_9b", 9.0))
        self.akt.allit(AKTIV)                                          # visszajöttél: a 9B kiürül
        self.assertTrue(var(lambda: self.bt.modell is None))

    def test_interaktiv_nem_var_a_tavolra(self):
        self.t.rogzit("ocr_kezi", "qwen35_9b", 0.9, "v1", kalibralt=True)
        self.utemezo()
        e = []
        self.kuld(self.chat("fotó", feladat="ocr_kezi", mod=INTERAKTIV), e)
        self.assertTrue(var(lambda: e))
        self.assertIsInstance(e[0][1], RoutingHiba)

    def test_kalibralatlan_feladat_hiba_kifejezett_keret(self):
        self.utemezo()
        e = []
        self.kuld(self.chat("x", feladat="szoveg"), e)
        self.assertTrue(var(lambda: e))
        self.assertIsInstance(e[0][1], RoutingHiba)
        self.kuld(self.chat("y", "gemma4_12b", keret="tavol"), e)          # kifejezett keret: tétlenségben még nem távol
        self.assertTrue(self.fuggo_db(1))
        self.assertTrue(self.kor_utan())
        self.assertEqual(len(e), 1)                                        # M3: a kérés nem emelheti a keretet — vár
        self.akt.allit(TAVOL)
        self.assertTrue(var(lambda: len(e) == 2))
        self.assertEqual(e[1][1]["keret_gb"], 9.0)

    def test_m3_a_kifejezett_keret_csak_szukit(self):
        """M3 (C19, T049): a kérés `keret`-je az aktivitásból következő keretet szűkítheti, emelni nem; az interaktív kérés a
        keretbe nem férő kifejezett modellel hibát kap, nem vár; a környezeti felülírás (a CLI saját workere) mindennél erősebb."""
        u = self.utemezo()
        k = self.chat("x", "ministral3_3b", keret=4)
        self.assertEqual(u.keret_gb(k, TETLEN), 4.0)
        self.assertEqual(u.keret_gb(self.chat("x", keret="tavol"), TETLEN), 5.0)
        self.assertEqual(u.keret_gb(self.chat("x", keret="tavol"), AKTIV), 5.0)
        self.assertEqual(u.keret_gb(self.chat("x", keret=99), TAVOL), 9.0)
        self.assertEqual(u.keret_gb(self.chat("x", keret=3), TAVOL), 3.0)
        e = []
        self.kuld(self.chat("y", "gemma4_12b", mod=INTERAKTIV, keret="tavol"), e)
        self.assertTrue(var(lambda: e))
        self.assertIsInstance(e[0][1], KeretHiba)
        self.b.keret_felulirva = 9.0
        self.assertEqual(u.keret_gb(self.chat("x", keret="munka"), AKTIV), 9.0)
        self.kuld(self.chat("z", "gemma4_12b"), e)
        self.assertTrue(var(lambda: len(e) == 2))
        self.assertEqual(e[1][1]["keret_gb"], 9.0)

    def test_m3_ervenytelen_keret(self):
        for rossz in ("nan", float("nan"), float("inf"), "-inf", 0, -1, "0", True, "valami"):
            with self.subTest(keret=rossz), self.assertRaises(ValueError):
                B.ervenyes_keret(self.b.keretek, rossz)
        self.assertEqual(B.ervenyes_keret(self.b.keretek, "2.5"), 2.5)
        with self.assertRaises(ValueError):
            B.betolt(self.cfg, {"MANIFOLD_MODELL_KERET_GB": "nan"})


class UritesTest(Alap):
    def test_tetlensegi_urites(self):
        self.b.gazda["tetlen_urites_perc"] = 0.3 / 60
        self.utemezo()
        e = []
        self.kuld(self.chat("x", "qwen3_vl_4b"), e)
        self.assertTrue(var(lambda: e))
        self.assertIsNotNone(self.bt.modell)
        self.assertTrue(var(lambda: self.bt.modell is None, 3))
        self.assertEqual(self.bt.zar.tartalom(), "")

    def test_hutesi_szunet_az_automatikust_tartja(self):
        sebesseg = iter([50, 50, 10, 10])
        self.utemezo(tps=lambda: next(sebesseg, 50))
        self.ho.c["hutes_mp"] = 0.5
        e = []
        for i in range(4):
            self.kuld(self.chat(str(i), "qwen3_vl_4b"), e)
            self.assertTrue(var(lambda: len(e) == i + 1))
        self.assertGreater(self.u.hutes_ig, time.monotonic())
        t0 = time.monotonic()
        self.kuld(self.chat("utana", "qwen3_vl_4b"), e)
        self.assertTrue(var(lambda: len(e) == 5))
        self.assertGreater(time.monotonic() - t0, 0.3)
        self.assertEqual(self.ho.szunetek, 1)

    def test_leallas_a_fuggot_elutasitja(self):
        self.akt.allit(AKTIV)
        u = self.utemezo()
        e = []
        self.kuld(self.chat("x", "qwen3_vl_4b"), e)
        self.assertTrue(self.fuggo_db(1))
        u.leall()
        self.assertTrue(var(lambda: e))
        self.assertIn("leáll", str(e[0][1]))


if __name__ == "__main__":
    unittest.main()
