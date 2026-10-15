"""C25b modellfele: a beágyazó a nyelvi modell mellett (a betöltő egyetlen döntése), a worker folyama és a kötés
(álmodellel, a valódi betöltő-, ütemező- és worker-kóddal)."""
import http.client
import json
import threading
import time
import unittest

from core.kereses_modell import ModellValtozott, WorkerBeagyazo, WorkerModell, WorkerReranker, router_modell
from core.modell.betolto import Betolto
from core.modell.kalibracio import Tabla
from core.modell.worker import Gazda, Szerver, _handler
from tests.helpers import alg_core, tmpdir
from tests.modell_segedek import AlHatter, AlAktivitas, al_betolto, beallitas


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)


class KotegTest(unittest.TestCase):
    def test_a_beagyazo_kotege_16(self):
        """K271 (2026-10-14): a kötegelt beágyazás 16-os (a 32-es köteg csúcsa 5,4 GB volt indexeléskor)."""
        from core.index.hibrid import frissites
        import inspect
        from core.kereses_modell import KOTEG
        self.assertEqual(KOTEG, 16)
        self.assertEqual(inspect.signature(frissites.frissit).parameters["koteg"].default, 16)
        self.assertEqual(inspect.signature(WorkerBeagyazo.__init__).parameters["koteg"].default, 16)


class EgyuttTest(Alap):
    def test_a_dontes_egyetlen_szabalya(self):
        bge, q4, g12, q2 = (self.b.modell(n) for n in ("bge_m3", "qwen35_4b", "gemma4_12b", "qwen35_2b"))
        e = Betolto.egyutt_maradhat
        self.assertFalse(e(bge, q4, 5.0))            # 3,3 + 4,1 > 5: munka közben nem fér együtt
        self.assertTrue(e(bge, q4, 9.0))             # távol-keretben igen
        self.assertTrue(e(q4, bge, 9.0))             # szimmetrikus
        self.assertFalse(e(bge, g12, 9.0))           # 3,3 + 8,5 > 9
        self.assertFalse(e(q4, q2, 9.0))             # két nyelvi modell soha
        self.assertFalse(e(bge, bge, 9.0))
        self.assertTrue(e(bge, q2, 6.0))             # 3,3 + 2,7 = 6,0 ≤ 6
        import dataclasses
        self.assertFalse(e(dataclasses.replace(bge, csucs_gb=None), q2, 99.0))   # mérés nélkül nem marad bent

    def test_tavol_keretben_bent_marad_munka_keretben_kiurul(self):
        t = al_betolto(self.b)
        bge, q4 = self.b.modell("bge_m3"), self.b.modell("qwen35_4b")
        t.beagyaz(bge, ["a"], 9.0)
        t.general(q4, [{"content": "x"}], 9.0)
        self.assertNotIn(("urit", "bge_m3"), AlHatter.naplo)
        self.assertEqual(t.allapot()["mellette"], ["bge_m3"])
        self.assertIn("+", t.zar.tartalom())
        n = t.betoltesek
        t.beagyaz(bge, ["b"], 9.0)                   # csere betöltés nélkül
        self.assertEqual(t.betoltesek, n)
        self.assertEqual(t.allapot()["modell"], "bge_m3")
        self.assertEqual(t.allapot()["mellette"], ["qwen35_4b"])
        t.beagyaz(bge, ["c"], 5.0)                   # a keret szűkült: a nyelvi modell kiürül
        self.assertIn(("urit", "qwen35_4b"), AlHatter.naplo)
        self.assertEqual(t.allapot()["mellette"], [])
        t.general(q4, [{"content": "x"}], 5.0)       # munka-keretben a beágyazó kiürül a nyelvi modell előtt
        self.assertEqual(AlHatter.naplo[-3:], [("urit", "bge_m3"), ("betolt", "qwen35_4b", t.cache_gb),
                                                ("general", "qwen35_4b", "x")])
        t.urit()
        self.assertIsNone(t.allapot()["modell"])
        self.assertEqual(t.zar.tartalom(), "")

    def test_a_memoriaor_mindkettot_uriti(self):
        szabad = [60]
        t = al_betolto(self.b, mem=lambda: szabad[0])
        t.beagyaz(self.b.modell("bge_m3"), ["a"], 9.0)
        t.general(self.b.modell("qwen35_4b"), [{"content": "x"}], 9.0)
        szabad[0] = 10
        threading.Timer(0.1, lambda: szabad.__setitem__(0, 90)).start()
        t.general(self.b.modell("qwen35_4b"), [{"content": "y"}], 9.0)
        self.assertIn(("urit", "bge_m3"), AlHatter.naplo)
        self.assertEqual(t.allapot()["mellette"], [])


class FolyamTest(Alap):
    def setUp(self):
        super().setUp()
        self.tabla = Tabla(self.b.router_db)
        self.g = Gazda(self.b, al_betolto(self.b), AlAktivitas(), self.tabla, tick_mp=0.02, naplo=lambda s: None)
        self.srv = Szerver(("127.0.0.1", 0), _handler(self.g))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.u = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.addCleanup(self._leall)

    def _leall(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.g.utemezo.leall()
        self.tabla.close()

    def test_tokenek_majd_vege_a_kalibralt_modellel(self):
        self.tabla.rogzit("szoveg", "qwen35_2b", 0.8, "v1", kalibralt=True)
        m = WorkerModell(lambda: self.u)
        self.assertEqual("".join(m("kérdés", 50)), "qwen35_2b: válasz")
        self.assertEqual(m.nev, "qwen35_2b")
        self.assertFalse(m.proba)
        self.assertEqual(m.utolso["tipus"], "vege")

    def test_nincs_kalibralt_modell_409(self):
        from core.modell.kliens import KliensHiba
        with self.assertRaises(KliensHiba) as cm:
            list(WorkerModell(lambda: self.u)("kérdés", 50))
        self.assertEqual(cm.exception.kod, 409)

    def test_a_bontott_kapcsolat_megallitja_a_generalast(self):
        self.tabla.rogzit("szoveg", "qwen35_2b", 0.8, "v1", kalibralt=True)
        fut = threading.Event()
        self.g.betolto.hatter_gyar = lambda m: AlHatter(hibak=[0], folyamatos=fut)
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request("POST", "/v1/chat/stream", body=json.dumps({"messages": [{"content": "x"}], "feladat": "szoveg",
                                                               "mod": "interaktiv"}),
                  headers={"X-Manifold": "1", "Content-Type": "application/json"})
        r = c.getresponse()
        self.assertEqual(r.status, 200)
        self.assertTrue(fut.wait(5))
        r.close()
        c.close()
        hatar = time.monotonic() + 8
        while ("megszakitva", "qwen35_2b") not in AlHatter.naplo and time.monotonic() < hatar:
            time.sleep(0.05)
        self.assertIn(("megszakitva", "qwen35_2b"), AlHatter.naplo)

    def test_a_vektorindex_lepese_a_workeren_at_epit_es_folytat(self):
        """A `vektorindex` feladat lépése (`python -m core.index.hibrid frissit`): a router beágyazójával, `auto` módban épít;
        a stop-fájlnál jegyzethatáron áll meg, a következő futás onnan folytatja."""
        import io
        import os
        from contextlib import redirect_stdout
        from pathlib import Path
        from unittest import mock
        from core import vektorindex_feladat
        from core.index.hibrid import __main__ as CLI
        from core.index.hibrid.vektortar import Vektortar
        from tests.hibrid_segedek import FAJLOK
        from tests.index_segedek import alvault, index_indit
        self.tabla.rogzit("beagyazas", "bge_m3", 0.86, "v1", kalibralt=True)
        cfg, _ = alvault(self._t.name + "/v", FAJLOK)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        stop = Path(self._t.name) / "stop"
        with mock.patch("core.config.load", lambda *a, **k: cfg), mock.patch.dict(os.environ, {"MOS_WORKER_URL": self.u}):
            with redirect_stdout(io.StringIO()) as ki:
                self.assertEqual(CLI.main(["frissit", "--max", "1", "--stop-fajl", str(stop)]), 0)
            self.assertEqual(json.loads(ki.getvalue())["beagyazott_jegyzet"], 1)
            stop.write_text("")
            with redirect_stdout(io.StringIO()) as ki:
                CLI.main(["frissit", "--stop-fajl", str(stop)])
            self.assertTrue(json.loads(ki.getvalue())["megszakitva"])
            stop.unlink()
            with redirect_stdout(io.StringIO()) as ki:
                CLI.main(["frissit", "--stop-fajl", str(stop)])
            self.assertEqual(json.loads(ki.getvalue())["beagyazott_jegyzet"], len(FAJLOK) - 1)
        t = Vektortar(Path(cfg.path("index")) / "vektor.sqlite", csak_olvas=True)
        self.addCleanup(t.close)
        self.assertEqual((t.allapot()["jegyzetek"], t.modell_kulcs()["nev"], t.modell_kulcs()["dim"]), (len(FAJLOK), "bge_m3", 2))
        self.assertTrue(any(("beagyaz", "bge_m3", 1) == x for x in AlHatter.naplo))      # a dimenzió-próba
        lepesek, _, _ = vektorindex_feladat._terv(cfg, {}, "/x/stop")
        self.assertEqual((lepesek[0].jogok, lepesek[0].argv[3:5]), ("nincs", ["core.index.hibrid", "frissit"]))

    def test_beagyazo_es_reranker_a_routerrel(self):
        self.tabla.rogzit("beagyazas", "bge_m3", 0.86, "v1", kalibralt=True)
        self.tabla.rogzit("rerank", "bge_reranker_v2_m3", 0.92, "v1", kalibralt=True)
        self.assertEqual(router_modell(self.u, "beagyazas"), "bge_m3")
        self.assertEqual(WorkerBeagyazo(lambda: self.u, "bge_m3").dim, 2)    # ismeretlen dimenzió: próba-beágyazás
        b = WorkerBeagyazo(lambda: self.u, "bge_m3")
        self.assertEqual(b(["a", "b"], "kerdes"), [[1.0, 0.0], [1.0, 0.0]])
        self.assertEqual((b.dim, b.elotag), (2, "nincs-v1"))
        with self.assertRaises(ValueError):
            b(["a"], "masfele")
        with self.assertRaises(ModellValtozott):     # a router közben átállt: nem keveredhet két modell vektora
            WorkerBeagyazo(lambda: self.u, "qwen3_embedding_06b")(["a"], "dokumentum")
        self.assertEqual(WorkerReranker(lambda: self.u)("q", ["aa", "a", "aaa"]), [2.0, 1.0, 3.0])


if __name__ == "__main__":
    unittest.main()
