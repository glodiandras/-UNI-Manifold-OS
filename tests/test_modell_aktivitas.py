"""Aktivitásjel és a feladatsor kapuja: az automatikus feladat csak tétlenségben, az indulási szünet után
indul; a kézi feladat nem vár (1. / 2. döntés, D8)."""
import os
import sys
import threading
import time
import unittest

from core import tasks
from core.modell.aktivitas import AKTIV, TAVOL, TETLEN, Aktivitas
from core.modell.jelek import Jelek
from core.modell.kapu import Kapu
from tests.helpers import alg_core, tmpdir


class Ora:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class AktivitasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.ora = Ora()
        self.hid = {"v": None}
        self.a = Aktivitas(os.path.join(self._t.name, "run", "aktivitas"), aktiv_mp=120, tavol_perc=15,
                           ido=self.ora, hid=lambda: self.hid["v"], hid_gyorsitotar_mp=0)

    def test_jel_nelkul_tavol(self):
        self.assertEqual(self.a.allapot(), TAVOL)

    def test_a_felulet_jele_szerint(self):
        self.a.jel()
        self.assertEqual(self.a.allapot(), AKTIV)
        self.ora.t += 121
        self.assertEqual(self.a.allapot(), TETLEN)
        self.ora.t += 15 * 60
        self.assertEqual(self.a.allapot(), TAVOL)

    def test_a_rendszer_tetlensege_is_szamit_a_frissebb_dont(self):
        self.a.jel()
        self.ora.t += 3600
        self.hid["v"] = 5.0                              # közben másik appban gépelt
        self.assertEqual(self.a.allapot(), AKTIV)
        self.hid["v"] = 7200.0
        self.assertEqual(self.a.allapot(), TAVOL)       # a felület jele 1 órás: a frissebb dönt
        ki = Aktivitas(self.a.fajl, rendszer=False, ido=self.ora, hid=lambda: 1.0)
        self.assertEqual(ki.allapot(), TAVOL)

    def test_jel_ritkitva(self):
        self.a.jel()
        m1 = os.stat(self.a.fajl).st_mtime
        self.ora.t += 0.2
        self.a.jel()
        self.assertEqual(os.stat(self.a.fajl).st_mtime, m1)
        self.ora.t += 1.0
        self.a.jel()
        self.assertGreater(os.stat(self.a.fajl).st_mtime, m1)


class _Akt:
    def __init__(self, a=TETLEN):
        self.a = a

    def allapot(self):
        return self.a


def _tipus(tid, automatikus=False, resources=()):
    def plan(cfg, p, stop):
        return [tasks.Step("lépés", [sys.executable, "-c", "import os; print('url=' + os.environ.get('MOS_WORKER_URL', '-')"
                                     " + ' mod=' + os.environ.get('MOS_MODELL_MOD', '-'))"], "/")], "", []
    return tasks.register(tasks.TaskType(tid, tid, plan, frozenset(resources), automatikus=automatikus))


class KapuTest(unittest.TestCase):
    def setUp(self):
        self.ora = Ora(0.0)
        self.akt = _Akt()
        self.mem = {"v": 60}
        self.k = Kapu(self.akt, 20, 180, mem=lambda: self.mem["v"], ido=self.ora)
        self.auto = tasks.TaskType("x", "x", None, frozenset(), automatikus=True)
        self.kezi = tasks.TaskType("y", "y", None, frozenset({"modell"}))
        self.sima = tasks.TaskType("z", "z", None)

    def test_indulasi_szunet_csak_az_automatikusat_tartja(self):
        self.assertFalse(self.k.admit(self.auto))
        self.assertTrue(self.k.admit(self.kezi))
        self.ora.t = 181
        self.assertTrue(self.k.admit(self.auto))

    def test_aktiv_hasznalat_es_memoria(self):
        self.ora.t = 1000
        self.akt.a = AKTIV
        self.assertFalse(self.k.admit(self.auto))
        self.assertEqual(self.k.utolso_ok, "aktív használat")
        self.assertTrue(self.k.admit(self.kezi))
        self.akt.a = TETLEN
        self.mem["v"] = 10
        self.assertFalse(self.k.admit(self.auto))
        self.assertFalse(self.k.admit(self.kezi))
        self.assertTrue(self.k.admit(self.sima))       # modell nélküli kézi feladatot a memória nem tart


class JelekTest(unittest.TestCase):
    """T132 (C29.8, L11): a feladatsor kapuja nem hív alfolyamatot (`sysctl`, `ioreg`) a sor zárja alatt: a jeleket egy külön szál
    frissíti, a kapu a gyorsítótárból olvas."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])

    def test_lassu_jel_nem_blokkolja_a_feladatsort(self):
        belepett, elenged = threading.Event(), threading.Event()
        hivasok = {"n": 0}

        def lassu_mem():
            hivasok["n"] += 1
            if hivasok["n"] > 1:                                # az első (szinkron) mérés gyors, a többi elakad
                belepett.set()
                elenged.wait(10)
            return 60
        jelek = Jelek(mem=lassu_mem, hid=lambda: None, periodus_mp=0.05)
        jelek.indit()
        self.addCleanup(jelek.leallit)
        self.assertTrue(belepett.wait(5))                       # a frissítő szál elakadt a lassú mérésben
        _tipus("t_auto", automatikus=True)
        kapu = Kapu(_Akt(TETLEN), 20, 0, jelek=jelek)
        q = tasks.Queue(self.cfg, admit=kapu.admit, start_delay=0)
        self.addCleanup(q.close)
        a = q.submit("t_auto")["id"]
        kesz = threading.Event()
        threading.Thread(target=lambda: (q.get(a), q.list(), kesz.set()), daemon=True).start()
        t0 = time.monotonic()
        self.assertTrue(kesz.wait(1.0))                         # ma (alfolyamat a zár alatt): ameddig a mérés tart, a sor zárolva van
        self.assertLess(time.monotonic() - t0, 1.0)
        elenged.set()

    def test_az_olvasas_nem_meres_es_a_hid_extrapolalt(self):
        ora = Ora(100.0)
        meresek = {"hid": 0, "mem": 0}

        def hid():
            meresek["hid"] += 1
            return 30.0

        def mem():
            meresek["mem"] += 1
            return 55
        jelek = Jelek(mem=mem, hid=hid, periodus_mp=3600, ido=ora)
        jelek.hatterben = True                                  # a háttérszál „dolgozik”: az olvasás gyorsítótárból megy
        jelek.frissit()                                         # egy mérés
        self.assertEqual((meresek["hid"], meresek["mem"]), (1, 1))
        ora.t += 7
        self.assertEqual((jelek.mem(), jelek.hid()), (55, 37.0))           # a tétlenség az eltelt idővel nő
        for _ in range(50):
            jelek.mem(), jelek.hid()
        self.assertEqual((meresek["hid"], meresek["mem"]), (1, 1))        # az olvasás nem mér

    def test_elavult_jel_az_automatikus_munkat_tartja_a_kezit_nem(self):
        ora = Ora(0.0)
        jelek = Jelek(mem=lambda: 60, hid=lambda: None, periodus_mp=3.0, ido=ora)
        jelek.hatterben = True
        kapu = Kapu(_Akt(TETLEN), 20, 0, jelek=jelek, ido=ora)
        auto = tasks.TaskType("x", "x", None, frozenset(), automatikus=True)
        kezi = tasks.TaskType("y", "y", None, frozenset({"modell"}))
        self.assertFalse(kapu.admit(auto))                      # még nem volt mérés: nincs jel
        self.assertEqual(kapu.utolso_ok, "a rendszerjelek még nem mértek / elavultak")
        jelek.frissit()
        self.assertTrue(kapu.admit(auto))
        ora.t += 100                                            # a frissítő szál elakadt: a jel elavult
        self.assertFalse(kapu.admit(auto))
        self.assertTrue(kapu.admit(kezi))                       # a kézi feladatot a memória-küszöb tartja, a jel kora nem

    def test_sok_varakozo_es_sok_tick_egy_meres(self):
        meresek = {"n": 0}

        def mem():
            meresek["n"] += 1
            return 60
        jelek = Jelek(mem=mem, hid=lambda: None, periodus_mp=3600)
        jelek.hatterben = True
        jelek.frissit()
        _tipus("t_auto", automatikus=True)
        admit_hivas = {"n": 0}
        kapu = Kapu(_Akt(AKTIV), 20, 0, jelek=jelek)

        def admit(t):
            admit_hivas["n"] += 1
            return kapu.admit(t)                                # aktív használat: a sor vár, az ütemező tickel
        q = tasks.Queue(self.cfg, admit=admit, start_delay=0)
        self.addCleanup(q.close)
        for _ in range(5):
            q.submit("t_auto")
        t0 = time.monotonic()
        while admit_hivas["n"] < 15 and time.monotonic() - t0 < 20:
            time.sleep(0.02)
        self.assertGreaterEqual(admit_hivas["n"], 15)
        self.assertEqual(meresek["n"], 1)                       # 5 sor × sok tick sem mért újra (ma: minden `admit` egy `sysctl`)

    def test_a_meres_hibaja_latszik_es_egyszer_naplozodik(self):
        """F6 (2026-10-14): a mérés kivétele nem nyelődik el: a `hiba` mezőben és a kapu indoklásában áll, a napló egyszer
        szól; a sikeres mérés törli."""
        import contextlib
        import io
        allapot = {"rossz": True, "n": 0}

        def mem():
            allapot["n"] += 1
            if allapot["rossz"]:
                raise OSError("sysctl nem fut")
            return 60
        jelek = Jelek(mem=mem, hid=lambda: None, periodus_mp=0.02)
        kapu = Kapu(_Akt(TETLEN), 20, 0, jelek=jelek)
        auto = tasks.TaskType("x", "x", None, frozenset(), automatikus=True)
        naplo = io.StringIO()
        with contextlib.redirect_stderr(naplo):
            jelek.indit(elso_varakozas_mp=1)
            self.addCleanup(jelek.leallit)
            t0 = time.monotonic()
            while allapot["n"] < 5 and time.monotonic() - t0 < 5:
                time.sleep(0.01)
            self.assertIn("sysctl nem fut", jelek.hiba)
            self.assertFalse(kapu.admit(auto))
            self.assertIn("a mérés hibája: OSError: sysctl nem fut", kapu.utolso_ok)
            allapot["rossz"] = False
            t0 = time.monotonic()
            while jelek.hiba is not None and time.monotonic() - t0 < 5:
                time.sleep(0.01)
        self.assertIsNone(jelek.hiba)
        self.assertEqual(naplo.getvalue().count("[jelek]"), 1)
        self.assertTrue(kapu.admit(auto))

    def test_indulas_elott_a_szinkron_tartalek_marad(self):
        """Ha a frissítő szál nincs elindítva (tesztek, nem az app), a jel a régi módon, szinkron mérődik."""
        jelek = Jelek(mem=lambda: 42, hid=lambda: 5.0)
        self.assertEqual(jelek.mem(), 42)
        self.assertIsNotNone(jelek.hid())


class SorKapuTest(unittest.TestCase):
    """A feladatsor a kaput feladatonként kérdezi: a várakozó automatikus mellett a kézi elindul."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])
        self.akt = _Akt(AKTIV)
        self.kapu = Kapu(self.akt, 20, 0, mem=lambda: 60)

    def test_automatikus_var_a_kezi_fut_env(self):
        _tipus("t_auto", automatikus=True)
        _tipus("t_kezi", resources=("modell",))
        env = lambda t: {"MOS_WORKER_URL": "http://al", "MOS_MODELL_MOD": "auto" if t.automatikus else "interaktiv"}
        hivasok = {"n": 0}

        def admit(t):
            hivasok["n"] += 1
            return self.kapu.admit(t)

        q = tasks.Queue(self.cfg, admit=admit, env_extra=env, start_delay=0)
        self.addCleanup(q.close)
        a = q.submit("t_auto")["id"]
        k = q.submit("t_kezi")["id"]
        t0 = time.time()
        while q.get(k)["allapot"] != "kesz" and time.time() - t0 < 10:
            time.sleep(0.05)
        self.assertEqual(q.get(k)["allapot"], "kesz")
        self.assertIn("url=http://al mod=interaktiv", q.detail(k)["sorok"])
        # T085: nem fix idő, hanem esemény: a kézi kész, és az ütemező még kétszer megkérdezte a kaput az automatikusról
        n0, t0 = hivasok["n"], time.time()
        while hivasok["n"] < n0 + 2 and time.time() - t0 < 15:
            time.sleep(0.02)
        self.assertGreaterEqual(hivasok["n"], n0 + 2)
        self.assertEqual(q.get(a)["allapot"], "sorban")            # aktív használat: vár
        self.akt.a = TETLEN
        t0 = time.time()
        while q.get(a)["allapot"] != "kesz" and time.time() - t0 < 10:
            time.sleep(0.05)
        self.assertEqual(q.get(a)["allapot"], "kesz")
        self.assertIn("url=http://al mod=auto", q.detail(a)["sorok"])


if __name__ == "__main__":
    unittest.main()
