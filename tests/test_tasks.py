"""A feladatsor (`core/tasks.py`) — a legacy `FuttatoTest` portja + a 2.0 bővítései (tartósság,
prioritás, erőforrás-szabály, legacy-előzmény). Valódi alfolyamatok, modell és hálózat nélkül."""
import json
import os
import signal
import sys
import time
import unittest
from pathlib import Path

from core import tasks
from tests.helpers import alg_core, tmpdir


def _tipus(tid, argvs, resources=(), graceful=False):
    """Egy teszt-feladattípus: lépésenként `python -c <kód>`; a `STOP` a stop-fájl útjára cserélődik."""
    def plan(cfg, p, stop):
        return [tasks.Step(f"lépés {i + 1}", [sys.executable, "-c", code.replace("STOP", stop)], "/")
                for i, code in enumerate(argvs)], "", []
    return tasks.register(tasks.TaskType(tid, tid, plan, frozenset(resources), graceful))


def _tart(enged: Path, elotte: str = "") -> str:
    """Egy teszt-lépés kódja, amely az `enged` fájl létrejöttéig fut (T085: esemény-, nem idő-alapú tartás — a „fut”,
    „sorban” állapotok vizsgálata nem függ attól, hogy a gép épp milyen gyors)."""
    return f"import os, time\n{elotte}\nwhile not os.path.exists({str(enged)!r}): time.sleep(0.02)"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)
        self.enged = Path(self._t.name) / "enged"
        self.esemenyek = []
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])

    def sor(self, **kw):
        kw.setdefault("publish", lambda e, **k: self.esemenyek.append(e))
        q = tasks.Queue(self.cfg, **kw)
        self.addCleanup(q.close)
        return q

    def var(self, q, fid, allapotok=("kesz", "hiba", "megallitva"), mp=20):
        t0 = time.time()
        while q.get(fid)["allapot"] not in allapotok and time.time() - t0 < mp:
            time.sleep(0.05)
        return q.get(fid)["allapot"]

    def sorok(self, q, fid):
        return q.detail(fid)["sorok"]

    def var_sorra(self, q, fid, s, mp=10):
        t0 = time.time()
        while s not in self.sorok(q, fid) and time.time() - t0 < mp:
            time.sleep(0.05)


class LepesTarolasTest(Alap):
    """C33 (T178, L10): a DB-ben nincs abszolút gyökér; a futtatás a `plan`-ből (a mostani konfigurációból) számol."""

    def test_a_db_ben_os_relativ_a_futtatas_a_planbol_ujraszamol(self):
        hivas = []

        def plan(cfg, p, stop):
            hivas.append(1)
            return [tasks.Step("x", [sys.executable, "-c", f"import sys; print('terv', {len(hivas)}, sys.argv[1])",
                                     str(cfg.root / "bin" / "mos")], str(cfg.root))], "", []
        tasks.register(tasks.TaskType("t_ut", "t_ut", plan))
        q = self.sor()
        f = q.submit("t_ut", {})
        self.assertEqual(self.var(q, f["id"]), "kesz")
        tarolt = q.get(f["id"])["lepesek"][0]
        self.assertEqual(tarolt["cwd"], "{os}")
        self.assertEqual(tarolt["argv"][-1], "{os}/bin/mos")
        self.assertNotIn(str(self.cfg.root), json.dumps(q.get(f["id"])["lepesek"], ensure_ascii=False).replace(sys.executable, ""))
        # a futás a lépést újraszámolta (2. terv), és az `{os}` a mostani gyökérre oldódott
        self.assertIn(f"terv 2 {self.cfg.root / 'bin' / 'mos'}", self.sorok(q, f["id"]))

    def test_a_regiszterbol_kikerult_tipus_tarolt_lepese_a_mostani_gyokerre_oldodik(self):
        q = self.sor()
        d = {"lepesek": [{"cim": "x", "argv": ["{os}/var/venv/bin/python", "-c", "x"], "cwd": "{os}", "jogok": "nincs"}],
             "parameterek": {}}
        l = q._lepesek_futtatasra(d, None, Path("/tmp/stop"))[0]
        self.assertEqual(l["argv"][0], f"{self.cfg.root}/var/venv/bin/python")
        self.assertEqual(l["cwd"], str(self.cfg.root))


class FuttatoTest(Alap):
    """A legacy `FuttatoTest` hét esete."""

    def test_letrehozas_nem_indit_semmit(self):
        q = self.sor()
        self.assertIsNone(q._thread)
        self.assertEqual(q.list(), [])

    def test_a_feladat_jelzi_hogy_automatikus_e(self):
        """E10: a felület a kézi feladat végéről rendszerértesítést kér, az automatikusról nem — ehhez a core adja a jelzést."""
        _tipus("t_kezi", ["print('x')"])
        tasks.register(tasks.TaskType("t_auto", "auto", lambda cfg, p, stop: ([tasks.Step("l", [sys.executable, "-c", "print(1)"], "/")], "", []),
                                      frozenset(), False, automatikus=True))
        q = self.sor(admit=lambda t: True)
        kezi = q.submit("t_kezi", {})
        auto = q.submit("t_auto", {})
        self.assertIs(q.get(kezi["id"])["automatikus"], False)
        self.assertIs(q.get(auto["id"])["automatikus"], True)
        self.assertIn("automatikus", q.list()[0])

    def test_lepesek_sorban_haladas_riport(self):
        _tipus("t_ket", ["print('[manifold-progress] 50.0%'); print('első')", "print('Riport: /x/KOR-1/riport.json')"])
        q = self.sor()
        f = q.submit("t_ket", {})
        self.assertEqual(self.var(q, f["id"]), "kesz")
        d = q.detail(f["id"])
        self.assertEqual(d["szazalek"], 100.0)
        self.assertEqual(d["riport"], "/x/KOR-1/riport.json")
        self.assertIn("első", d["sorok"])
        self.assertFalse(any("manifold-progress" in s for s in d["sorok"]))
        self.assertTrue(any(e["feladat"]["szazalek"] == 25.0 for e in self.esemenyek if e["tipus"] == "feladat"))
        q.shutdown(timeout=5)
        # a lezárt feladat a következő indításkor is látszik
        self.assertEqual(self.sor().list()[0]["allapot"], "kesz")

    def test_hibas_lepes_megallitja_a_tobbit(self):
        _tipus("t_hiba", ["import sys; sys.exit(3)", "print('nem fut le')"])
        q = self.sor()
        f = q.submit("t_hiba", {})
        self.assertEqual(self.var(q, f["id"]), "hiba")
        self.assertEqual(q.get(f["id"])["kilepes"], 3)
        self.assertNotIn("nem fut le", self.sorok(q, f["id"]))

    def test_kulturalt_leallitas_a_tetel_vegen(self):
        lanc = ("import os,time\nfor i in range(50):\n    if os.path.exists('STOP'): print('megállt', i); break\n"
                "    print('tétel', i, flush=True); time.sleep(0.1)\n")
        _tipus("t_lanc", [lanc, "print('második lépés')"], graceful=True)
        q = self.sor()
        f = q.submit("t_lanc", {})
        self.var_sorra(q, f["id"], "tétel 2")
        self.assertEqual(q.stop(f["id"])["allapot"], "megall_a_tetel_vegen")
        self.assertEqual(self.var(q, f["id"]), "megallitva")
        self.assertTrue(any(s.startswith("megállt") for s in self.sorok(q, f["id"])))
        self.assertNotIn("második lépés", self.sorok(q, f["id"]))

    def test_azonnali_leallitas(self):
        _tipus("t_alvo", ["import time; print('indul', flush=True); time.sleep(30)"])
        q = self.sor()
        f = q.submit("t_alvo", {})
        self.var_sorra(q, f["id"], "indul")
        q.stop(f["id"], immediate=True)
        self.assertEqual(self.var(q, f["id"]), "megallitva")

    def test_azonnali_leallitas_a_popen_es_a_run_proc_beallitasa_kozott_nem_vesz_el(self):
        """T134 (C29.8): a leállítás, amely a `Popen` után, de a `run.proc` beállítása előtt érkezik, eddig elveszett (a lépés a
        természetes végéig futott): a lassított `ps` (a `run.proc` a `_ps("lstart")` után állt be) ablakot nyit."""
        import threading
        from unittest import mock
        _tipus("t_alvo2", ["import time; print('indul', flush=True); time.sleep(30)"])
        popen_utan, tovabb = threading.Event(), threading.Event()
        eredeti = tasks._ps

        def lassu_ps(mezo, pid):
            if mezo == "lstart" and threading.current_thread().name.startswith("feladat-"):
                popen_utan.set()
                tovabb.wait(8)
            return eredeti(mezo, pid)
        with mock.patch.object(tasks, "_ps", lassu_ps):
            q = self.sor()
            f = q.submit("t_alvo2", {})["id"]
            self.assertTrue(popen_utan.wait(10))                    # a Popen megtörtént, a `run.proc` még (ma) nincs beállítva
            q.stop(f, immediate=True)                               # ma: nincs mit leállítani, a lépés fut tovább
            tovabb.set()
            t0 = time.time()
            self.assertEqual(self.var(q, f, mp=8), "megallitva")    # ma: ~30 s, „fut”
            self.assertLess(time.time() - t0, 6)
            self.assertLess(q.get(f)["kilepes"], 0)                 # jellel állt le (SIGTERM)

    def test_kulturalt_leallitas_nem_olni_a_lepest_a_popen_utan(self):
        """A kulturált leállítás (stop-fájl) a tétel végén áll meg; a T134 javítása a lépést nem lövi le idő előtt."""
        _tipus("t_kult", ["import time; print('indul', flush=True); time.sleep(2); print('tetel kesz', flush=True)"], graceful=True)
        q = self.sor()
        f = q.submit("t_kult", {})["id"]
        self.var_sorra(q, f, "indul")
        q.stop(f)
        self.assertEqual(self.var(q, f), "megallitva")
        self.assertIn("tetel kesz", self.sorok(q, f))

    def test_lepes_stdinje_devnull(self):
        _tipus("t_stdin", ["import sys; print('stdin:', repr(sys.stdin.read()))"])
        q = self.sor()
        f = q.submit("t_stdin", {})
        self.assertEqual(self.var(q, f["id"], mp=10), "kesz")
        self.assertIn("stdin: ''", self.sorok(q, f["id"]))

    def test_lezaras_csak_tetlenul_es_utana_nem_fogad(self):
        _tipus("t_rovid", [_tart(self.enged)])
        q = self.sor()
        ures = self.sor()
        self.assertTrue(ures.close_if_idle())                              # üres sor: azonnal
        f = q.submit("t_rovid", {})
        self.assertFalse(q.close_if_idle())                                # a feladat addig fut, amíg el nem engedjük
        self.enged.touch()
        self.assertEqual(self.var(q, f["id"]), "kesz")
        self.assertTrue(q.close_if_idle())
        with self.assertRaises(tasks.Closed):
            q.submit("t_rovid", {})


class SorTest(Alap):
    """A 2.0 bővítései."""

    def test_prioritas_es_fifo(self):
        _tipus("t_jel", ["import os; print(os.environ['MOS_FELADAT'])"])
        nyitva = {"v": False, "hivas": 0}

        def kapu():
            nyitva["hivas"] += 1
            return nyitva["v"]

        q = self.sor(gate=kapu, max_parallel=1)
        a = q.submit("t_jel", {}, 0)["id"]
        b = q.submit("t_jel", {}, 5)["id"]
        c = q.submit("t_jel", {}, 0)["id"]
        # T085: nem fix idő (sleep), hanem esemény: az ütemező mind a három submit UTÁN legalább kétszer lekérdezte a
        # kaput (a második kör biztosan a teljes sorral dolgozik), és a zárt kapu miatt egyik sem indult el
        n0 = nyitva["hivas"]
        t0 = time.time()
        while nyitva["hivas"] < n0 + 2 and time.time() - t0 < 15:
            time.sleep(0.02)
        self.assertGreaterEqual(nyitva["hivas"], n0 + 2)
        self.assertEqual(q.get(b)["allapot"], "sorban")                   # a kapu zárva: semmi nem indul
        nyitva["v"] = True
        for fid in (a, b, c):
            self.assertEqual(self.var(q, fid), "kesz")
        indult = sorted((q.get(x)["indult"], i) for i, x in enumerate((a, b, c)))
        sorrend = [e["feladat"]["id"] for e in self.esemenyek
                   if e["tipus"] == "feladat" and e["feladat"]["allapot"] == "fut" and e["feladat"]["lepes_i"] == 0
                   and e["feladat"]["szazalek"] == 0.0]
        self.assertEqual(list(dict.fromkeys(sorrend)), [b, a, c])
        self.assertTrue(indult)

    def test_egyszerre_egy_modell_a_konnyu_kozben_fut(self):
        _tipus("t_modell", [_tart(self.enged, "print('m', flush=True)")], resources=("modell",))
        _tipus("t_konnyu", ["print('k')"])
        q = self.sor(max_parallel=2)
        m1 = q.submit("t_modell", {})["id"]
        m2 = q.submit("t_modell", {})["id"]
        k = q.submit("t_konnyu", {})["id"]
        self.assertEqual(self.var(q, k), "kesz")
        self.assertEqual(q.get(m1)["allapot"], "fut")                     # az első modell addig fut, amíg el nem engedjük
        self.assertEqual(q.get(m2)["allapot"], "sorban")                  # a második modell vár
        self.enged.touch()
        self.assertEqual(self.var(q, m2), "kesz")
        self.assertGreaterEqual(q.get(m2)["indult"], q.get(m1)["vegzett"])
        self.assertTrue(q.get(m1)["modell"])

    def test_vault_iro_foglaltsag(self):
        _tipus("t_vault", [_tart(self.enged, "print('v', flush=True)")], resources=("vault",))
        q = self.sor()
        f = q.submit("t_vault", {})["id"]
        self.var_sorra(q, f, "v")
        self.assertTrue(q.busy_vault())                                   # a lépés addig fut, amíg el nem engedjük
        self.enged.touch()
        self.var(q, f)
        self.assertFalse(q.busy_vault())

    def test_ujrainditas_futo_megszakad_sorban_marad(self):
        _tipus("t_alvo", ["import time; print('indul', flush=True); time.sleep(30)"])
        q = self.sor(max_parallel=1)
        futo = q.submit("t_alvo", {})["id"]
        var = q.submit("t_alvo", {})["id"]
        self.var_sorra(q, futo, "indul")
        # „összeomlás”: új sor ugyanarra a DB-re, a régi folyamat nélkül (a lépés pidjét töröljük, különben az
        # indulási takarítás — C17 — a még élő próbafolyamatot le is állítaná; azt az árva-tesztek mérik)
        q._db.execute("UPDATE feladat SET lepes_pid=NULL, lepes_inditva=NULL WHERE id=?", (futo,))
        q2 = self.sor(start_delay=0.3)
        self.assertEqual(q2.get(futo)["allapot"], "megszakadt")
        self.assertEqual(q2.get(var)["allapot"], "sorban")
        self.assertIsNone(q2._thread)                                     # D8: a megnyitás nem indít munkát
        q.closed = True                                                   # a régi sor ütemezője leáll …
        os.killpg(q._running[futo].proc.pid, signal.SIGKILL)              # … és a folyamata „meghal”
        self.assertEqual(self.var(q2, var, allapotok=("fut",), mp=5), "fut")   # a szünet után indul
        q2.stop(var, immediate=True)
        self.var(q2, var)

    def test_sorban_allo_torolheto_es_ismeretlen_tipus(self):
        _tipus("t_x", ["print(1)"])
        q = self.sor(gate=lambda: False)
        f = q.submit("t_x", {})["id"]
        self.assertEqual(q.stop(f)["allapot"], "torolve")
        with self.assertRaises(tasks.Invalid):
            q.submit("nincs_ilyen", {})
        with self.assertRaises(tasks.Invalid):
            q.stop("F-nincs")

    def test_regi_pult_naplo_nincs_importalva(self):
        """A feladatsor csak a saját tartós állapotát tölti be: egy régi pult-napló (`{runs}/pult/feladatok.jsonl`) nem
        kerül be a listába, nincs `legacy` forrású feladat (a legacy-híd a termékből kikerült)."""
        pult = self.cfg.path("runs") / "pult"
        pult.mkdir(parents=True)
        sor = {"id": "F-20260924-083756-1", "tipus": "video_staging", "cim": "Régi feladat", "osszegzes": "x",
               "parameterek": {}, "figyelmeztetes": [], "lepesek": [], "allapot": "kesz", "letrehozva": "2026-09-24T08:37:56",
               "szazalek": 100.0, "lepes_i": 0, "vault_ir": True, "kulturalt_stop": True}
        (pult / "feladatok.jsonl").write_text(json.dumps(sor, ensure_ascii=False) + "\nnem json\n", encoding="utf-8")
        (pult / "F-20260924-083756-1.log").write_text("régi sor\n", encoding="utf-8")
        q = self.sor()
        self.assertEqual(q.list(), [])
        q.shutdown(timeout=5)
        self.assertEqual(self.sor().list(), [])                          # újraindítás után sem


_ARVA_KOD = """
import sys, time
from core import config, tasks
cfg = config.load()
def terv(cfg, p, stop):
    return [tasks.Step("alvó", [sys.executable, "-c", "import time; print('indul', flush=True); time.sleep(120)"], "/")], "", []
tasks.register(tasks.TaskType("t_arva", "t_arva", terv))
q = tasks.Queue(cfg, start_delay=0)
f = q.submit("t_arva", {})["id"]
t0 = time.time()
while "indul" not in q.detail(f)["sorok"] and time.time() - t0 < 20:
    time.sleep(0.05)
print(f, flush=True)
time.sleep(120)
"""


class ArvaTest(Alap):
    """Audit M2 (C17): a core halála után a lépés alfolyamata nem maradhat árván."""

    def _arva_core(self):
        import subprocess
        from tests.helpers import REPO, env as hermetikus
        env = hermetikus(MOS_ROOT=str(self.root), HOME=str(self.root.parent / "home"), PYTHONPATH=str(REPO))
        p = subprocess.Popen([sys.executable, "-B", "-c", _ARVA_KOD], env=env, cwd=str(REPO), stdout=subprocess.PIPE,
                             text=True)
        self.addCleanup(p.stdout.close)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        fid = p.stdout.readline().strip()
        self.assertTrue(fid.startswith("F-"), fid)
        import sqlite3
        db = sqlite3.connect(self.cfg.path("feladatok_db"))
        pid, inditva, argv0 = db.execute("SELECT lepes_pid, lepes_inditva, lepes_argv0 FROM feladat WHERE id=?",
                                         (fid,)).fetchone()
        db.close()
        self.addCleanup(lambda: self._el(pid) and os.killpg(pid, signal.SIGKILL))
        return p, fid, pid, inditva, argv0

    @staticmethod
    def _el(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return bool(tasks._ps("lstart", pid))     # a zombi/halott pid nem „él”

    def test_futo_lepes_pidje_a_db_ben(self):
        _tipus("t_pid", ["import time; print('indul', flush=True); time.sleep(30)"])
        q = self.sor()
        f = q.submit("t_pid", {})["id"]
        self.var_sorra(q, f, "indul")
        pid, inditva, argv0 = q._db.execute("SELECT lepes_pid, lepes_inditva, lepes_argv0 FROM feladat WHERE id=?",
                                            (f,)).fetchone()
        self.assertEqual(pid, q._running[f].proc.pid)
        self.assertTrue(inditva)
        self.assertEqual(argv0, sys.executable)
        self.assertNotIn("lepes_pid", q.get(f))                          # a belső mező nem publikus
        q.stop(f, immediate=True)
        self.var(q, f)
        self.assertIsNone(q._db.execute("SELECT lepes_pid FROM feladat WHERE id=?", (f,)).fetchone()[0])

    def test_core_megolese_utan_az_ujraindulas_leallitja_az_arva_lepest(self):
        p, fid, pid, _, _ = self._arva_core()
        self.assertTrue(self._el(pid))
        p.kill()
        p.wait()
        self.assertTrue(self._el(pid), "a lépés saját munkamenetben fut: a core halála után árván él")
        horog = []
        q = self.sor(leallitas_horog=horog.append)
        self.assertTrue(q.arva_var(15), "az árva lépés rendezése (háttérszál, A-javító) véget ér")
        self.assertFalse(self._el(pid), "az indulási takarítás leállítja")
        d = q.get(fid)
        self.assertEqual(d["allapot"], "megszakadt")
        self.assertIn("orphaned", d["hiba"])
        self.assertIn(str(pid), d["hiba"])
        self.assertEqual(horog, [fid])                                    # a worker értesül (C17)
        self.assertIn("orphaned", "\n".join(q.detail(fid)["sorok"]))

    def test_nem_egyezo_ujjlenyomatu_folyamathoz_nem_nyul(self):
        p, fid, pid, _, _ = self._arva_core()
        p.kill()
        p.wait()
        import sqlite3
        db = sqlite3.connect(self.cfg.path("feladatok_db"))
        db.execute("UPDATE feladat SET lepes_inditva='Mon Jan  1 00:00:00 2001' WHERE id=?", (fid,))
        db.commit()
        db.close()
        q = self.sor()
        self.assertTrue(q.arva_var(15))
        self.assertTrue(self._el(pid), "a pid-újrahasznosítás ellen: más indulási idő → nem a mi lépésünk")
        self.assertEqual(q.get(fid)["allapot"], "megszakadt")
        self.assertNotIn("orphaned", q.get(fid)["hiba"])

    def test_azonnali_leallitas_ertesiti_a_workert_a_kulturalt_nem(self):
        _tipus("t_hg", ["import time; print('indul', flush=True); time.sleep(30)"])
        _tipus("t_hk", ["import os,time; print('indul', flush=True)\nwhile not os.path.exists('STOP'): time.sleep(0.05)"],
               graceful=True)
        horog = []
        q = self.sor(leallitas_horog=horog.append, max_parallel=2)
        a = q.submit("t_hg", {})["id"]
        b = q.submit("t_hk", {})["id"]
        self.var_sorra(q, a, "indul")
        self.var_sorra(q, b, "indul")
        q.stop(b)                                                         # kulturált: a tétel végigfut
        self.assertEqual(horog, [])
        self.var(q, b)
        q.stop(a, immediate=True)
        self.assertEqual(horog, [a])
        self.var(q, a)

    def test_horog_hibaja_nem_akasztja_a_leallitast(self):
        _tipus("t_hh", ["import time; print('indul', flush=True); time.sleep(30)"])

        def rossz(fid):
            raise RuntimeError("a worker nem érhető el")
        q = self.sor(leallitas_horog=rossz)
        f = q.submit("t_hh", {})["id"]
        self.var_sorra(q, f, "indul")
        q.stop(f, immediate=True)
        self.assertEqual(self.var(q, f), "megallitva")

    def test_migracio_v1_bol_megorzi_a_sorokat(self):
        import sqlite3
        q = self.sor()
        _tipus("t_m", ["print(1)"])
        f = q.submit("t_m", {})["id"]
        self.var(q, f)
        q.shutdown(timeout=5)
        db = sqlite3.connect(self.cfg.path("feladatok_db"))
        for c in ("lepes_pid", "lepes_inditva", "lepes_argv0"):          # a v1 állapot: a három oszlop még nincs
            db.execute(f"ALTER TABLE feladat DROP COLUMN {c}")
        db.execute("PRAGMA user_version=1")
        db.commit()
        db.close()
        q2 = self.sor()
        self.assertEqual(q2.get(f)["allapot"], "kesz")
        self.assertEqual(q2._db.execute("PRAGMA user_version").fetchone()[0], 3)



def _jogos_tipus(tid, kod, jogok):
    """Egy egylépéses teszt-feladattípus megadott jogkészlettel (K149)."""
    def plan(cfg, p, stop):
        return [tasks.Step("lépés", [sys.executable, "-c", kod], "/", jogok=jogok)], "", []
    return tasks.register(tasks.TaskType(tid, tid, plan, frozenset()))


class JogkeszletTest(Alap):
    """K149 (Audit 3 A3-12): a lépés jogkészlete (`Step.jogok`, `core/lepes_kapu.py`) dönti el, kap-e lépés-tokent és a core címét."""

    def kod(self):
        """A lépés kiírja, mit kapott (a token értékét is, hogy a teszt a sorral összevethesse), és a kioldásig fut."""
        return _tart(self.enged, "print('TOKEN', os.environ.get('MOS_LEPES_TOKEN', '-'), 'CORE', os.environ.get('MOS_CORE_URL', '-'), "
                                 "flush=True)")

    def futtat(self, jogok):
        tid = f"t_jog_{jogok}"
        _jogos_tipus(tid, self.kod(), jogok)
        q = self.sor(env_extra=lambda t: {"MOS_CORE_URL": "http://127.0.0.1:1"})
        fid = q.submit(tid, {})["id"]
        t0 = time.time()
        while not any(s.startswith("TOKEN ") for s in self.sorok(q, fid)) and time.time() - t0 < 10:
            time.sleep(0.05)
        sor = next(s for s in self.sorok(q, fid) if s.startswith("TOKEN "))
        _, token, _, core = sor.split()
        return q, fid, token, core

    def test_az_alap_lepes_tokent_kap_amit_a_lepes_feladat_felismer(self):
        q, fid, token, core = self.futtat(tasks.lepes_kapu.JOGOK_GEPI)
        self.assertNotEqual(token, "-")
        self.assertEqual(core, "http://127.0.0.1:1")
        self.assertEqual(q.lepes_feladat(token), fid)
        self.enged.touch()
        self.assertEqual(self.var(q, fid), "kesz")
        self.assertIsNone(q.lepes_feladat(token), "a lépés végén a token lejár")

    def test_a_kulcs_nelkuli_step_az_alap(self):
        self.assertEqual(tasks.Step("x", ["true"], "/").jogok, tasks.lepes_kapu.JOGOK_GEPI)

    def test_a_nincs_lepes_futasa_alatt_nincs_bejegyzett_token_es_core_cim(self):
        q, fid, token, core = self.futtat(tasks.lepes_kapu.JOGOK_NINCS)
        self.assertEqual((token, core), ("-", "-"))
        self.assertEqual(q.get(fid)["allapot"], "fut")
        self.assertEqual(q._lepes_tokenek, {}, "a token nélküli lépésnek a core nem jegyez be tokent")
        self.enged.touch()
        self.assertEqual(self.var(q, fid), "kesz")

    def test_ismeretlen_jogkeszlet_zarva_hibazik(self):
        q, fid, token, core = self.futtat("admin")
        self.assertEqual((token, core), ("-", "-"))
        self.assertEqual(q._lepes_tokenek, {})
        self.enged.touch()
        self.assertEqual(self.var(q, fid), "kesz")

    def test_a_jogkeszlet_a_db_ben_marad_es_ujrainditas_utan_is_hat(self):
        _jogos_tipus("t_jog_tartos", self.kod(), tasks.lepes_kapu.JOGOK_NINCS)
        q = self.sor(gate=lambda: False)                  # a kapu zárva: a feladat a sorban marad
        fid = q.submit("t_jog_tartos", {})["id"]
        self.assertEqual(q.get(fid)["lepesek"][0]["jogok"], "nincs")
        q.close()
        q2 = self.sor(start_delay=0, env_extra=lambda t: {"MOS_CORE_URL": "http://127.0.0.1:1"})
        self.assertEqual(q2.get(fid)["lepesek"][0]["jogok"], "nincs")
        q2._ensure_thread()
        t0 = time.time()
        while not any(s.startswith("TOKEN ") for s in self.sorok(q2, fid)) and time.time() - t0 < 10:
            time.sleep(0.05)
        self.assertIn("TOKEN - CORE -", self.sorok(q2, fid))
        self.assertEqual(q2._lepes_tokenek, {})
        self.enged.touch()
        self.assertEqual(self.var(q2, fid), "kesz")

    def test_a_regi_kulcs_nelkuli_lepessor_az_alap_jogot_kapja(self):
        _jogos_tipus("t_jog_regi", self.kod(), tasks.lepes_kapu.JOGOK_GEPI)
        q = self.sor(gate=lambda: False)
        fid = q.submit("t_jog_regi", {})["id"]
        lepesek = q.get(fid)["lepesek"]
        del lepesek[0]["jogok"]                            # a K149 előtt mentett sor
        q._db.execute("UPDATE feladat SET lepesek=? WHERE id=?", (json.dumps(lepesek), fid))
        q.close()
        q2 = self.sor(start_delay=0)
        q2._ensure_thread()
        t0 = time.time()
        while not any(s.startswith("TOKEN ") for s in self.sorok(q2, fid)) and time.time() - t0 < 10:
            time.sleep(0.05)
        token = next(s for s in self.sorok(q2, fid) if s.startswith("TOKEN ")).split()[1]
        self.assertNotEqual(token, "-")
        self.assertEqual(q2.lepes_feladat(token), fid)
        self.enged.touch()
        self.assertEqual(self.var(q2, fid), "kesz")


if __name__ == "__main__":
    unittest.main()


class CxKeziAiTest(Alap):
    def test_tiltott_bekuldes_es_regi_sor_vegleges_lezarasa(self):
        _tipus('t_regi_auto', ['raise Exception("nem indulhat")'])
        q = self.sor(start_delay=999)
        d = q.submit('t_regi_auto')
        q.tiltott = lambda t: t.id == 't_regi_auto'
        with self.assertRaises(tasks.Invalid):
            q.submit('t_regi_auto')
        with q._lock:
            self.assertIsNone(q._pick())
        self.assertEqual(q.get(d['id'])['allapot'], 'torolve')
