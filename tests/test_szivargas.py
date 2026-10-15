"""Kis memóriaszivárgások (F7, 2026-10-14): az útvonal-zárak, az események ritkítás-kulcsai és a próbakörök klón-szolgáltatásai
korlátosak; a működés (kizárás, ritkítás, újrahasznosítás) változatlan. Fájlrendszer nélkül."""
import gc
import threading
import time
import unittest
from unittest import mock

from core import events, gepi_iras, vaultio


class UtZarTest(unittest.TestCase):
    def test_a_tartott_zar_ugyanaz_az_elengedett_eltunik(self):
        elotte = len(vaultio._UT_ZARAK)
        z = vaultio._ut_zar("F7/Próba.md")
        self.assertIs(vaultio._ut_zar("f7/próba.md"), z)              # kis-nagybetű és NFC: ugyanaz a zár
        with z:
            self.assertFalse(vaultio._ut_zar("F7/Próba.md").acquire(blocking=False))   # a kizárás marad
        del z
        for i in range(500):
            with vaultio._ut_zar(f"F7/sok-{i}.md"):
                pass
        gc.collect()
        self.assertLessEqual(len(vaultio._UT_ZARAK), elotte)          # nem gyűlnek a valaha írt utak zárai

    def test_varakozo_szal_ugyanazt_a_zarat_kapja(self):
        z = vaultio._ut_zar("F7/varo.md")
        z.acquire()
        megkapta = threading.Event()

        def var():
            with vaultio._ut_zar("F7/varo.md"):
                megkapta.set()
        t = threading.Thread(target=var)
        t.start()
        time.sleep(0.1)
        self.assertFalse(megkapta.is_set())
        z.release()
        t.join(5)
        self.assertTrue(megkapta.is_set())


class RitkitasTest(unittest.TestCase):
    def test_a_lejart_kulcsok_kitakarodnak_a_ritkitas_marad(self):
        bus = events.Bus()
        ido = [1000.0]
        with mock.patch.object(events.time, "monotonic", lambda: ido[0]):
            for i in range(events.LAST_MAX * 4):
                bus.publish({"i": i}, throttle_key=f"feladat-{i}")
                ido[0] += 1.0                                         # minden kulcs régi lesz a következő előtt
            self.assertLessEqual(len(bus._last), events.LAST_MAX)
            self.assertTrue(bus.publish({}, throttle_key="x"))
            self.assertFalse(bus.publish({}, throttle_key="x"))       # az ablakon belül ritkít


class KlonSzolgaltatasTest(unittest.TestCase):
    def test_korlatos_lru(self):
        d = gepi_iras._Korlatos(3)
        for k in "abc":
            d[k] = k
        d["a"]                                                        # használat: a végére kerül
        d["d"] = "d"
        self.assertEqual(list(d), ["c", "a", "d"])
        self.assertNotIn("b", d)
        self.assertEqual(len(d), 3)


if __name__ == "__main__":
    unittest.main()
