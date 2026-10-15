"""A modell-worker HTTP-felülete (álmodellel, folyamaton belül) és életciklusa (valódi alfolyamat, modell nélkül)."""
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import unittest

from core.modell import kliens
from core.modell.kalibracio import Tabla
from core.modell.worker import Gazda, Szerver, _handler
from tests.helpers import REPO, alg_core, tmpdir
from tests.modell_segedek import AlAktivitas, al_betolto, beallitas


class WorkerHttpTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)
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

    def nyers(self, method, path, body=None, fejlec=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=fejlec or {})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def test_biztonsag(self):
        self.assertEqual(self.nyers("GET", "/health")[0], 403)
        self.assertEqual(self.nyers("GET", "/health", fejlec={"X-Manifold": "1", "Host": "gonosz.example"})[0], 403)
        kod, d = self.nyers("GET", "/health", fejlec={"X-Manifold": "1"})
        self.assertEqual(kod, 200)
        self.assertIsNone(d["modell"])

    def test_chat_proba_es_d9(self):
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.keres(self.u, "/v1/chat/completions", {"messages": [{"content": "x"}], "model": "qwen3_vl_4b"})
        self.assertEqual(cm.exception.kod, 400)                     # próba-jel nélkül nincs kifejezett modell
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.chat(self.u, [{"content": "x"}], feladat="szoveg")
        self.assertEqual(cm.exception.kod, 409)                     # nincs kalibrált modell
        r = kliens.chat(self.u, [{"content": "x"}], modell="qwen3_vl_4b")
        self.assertTrue(r["proba"])
        self.assertEqual(r["choices"][0]["message"]["content"], "qwen3_vl_4b: válasz")
        self.assertEqual(kliens.health(self.u)["modell"], "qwen3_vl_4b")
        self.tabla.rogzit("szoveg", "qwen35_2b", 0.8, "v1", kalibralt=True)
        r = kliens.chat(self.u, [{"content": "x"}], feladat="szoveg")
        self.assertFalse(r["proba"])
        self.assertEqual(r["modell"], "qwen35_2b")

    def test_masodik_velemeny_kizart_csalad(self):
        """C24b: a chat és a `/router/valaszt` a `kizart_csalad`-ot a routerhez viszi; ha nem marad jelölt: 409
        `nincs_masik_csalad`; hibás érték: 400."""
        self.tabla.rogzit("szoveg", "qwen35_2b", 0.8, "v1", kalibralt=True)
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.chat(self.u, [{"content": "x"}], feladat="szoveg", kizart_csalad="qwen")
        self.assertEqual(cm.exception.kod, 409)
        self.assertTrue(cm.exception.adat.get("nincs_masik_csalad"))
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.keres(self.u, "/router/valaszt", {"feladat": "szoveg", "kizart_csalad": "qwen"})
        self.assertEqual(cm.exception.kod, 409)
        self.tabla.rogzit("szoveg", "gemma4_e2b", 0.7, "v1", kalibralt=True)
        self.assertEqual(kliens.keres(self.u, "/router/valaszt", {"feladat": "szoveg", "kizart_csalad": "qwen"})["modell"],
                         "gemma4_e2b")
        self.assertEqual(kliens.chat(self.u, [{"content": "x"}], feladat="szoveg", kizart_csalad="qwen")["modell"], "gemma4_e2b")
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.chat(self.u, [{"content": "x"}], feladat="szoveg", kizart_csalad=["qwen"])
        self.assertEqual(cm.exception.kod, 400)

    def test_a_valasz_a_csucsmemoriat_es_a_betoltest_hordozza(self):
        """T045 (C29.8): a worker válasza a kérés mlx-csúcsmemóriáját, a betöltés tényét és idejét adja (a mérés a K28 előfeltétele)."""
        r1 = kliens.chat(self.u, [{"content": "x"}], modell="qwen3_vl_4b")
        m1 = r1["memoria"]
        self.assertEqual((m1["csucs_gb"], m1["betoltve"]), (3.5, True))              # ma: a válaszban nincs memoria
        self.assertGreaterEqual(m1["betoltes_mp"], 0.0)
        r2 = kliens.chat(self.u, [{"content": "x"}], modell="qwen3_vl_4b")           # ugyanaz a modell: nem töltődik újra
        m2 = r2["memoria"]
        self.assertEqual((m2["csucs_gb"], m2["betoltve"], m2["betoltes_mp"]), (3.5, False, 0.0))
        e = kliens.keres(self.u, "/v1/embeddings", {"input": ["a"], "model": "bge_m3", "proba": True, "mod": "interaktiv"})
        self.assertEqual(e["memoria"]["betoltve"], True)                              # másik modell: betöltés (és kiürítés)
        rr = kliens.keres(self.u, "/v1/rerank", {"query": "q", "documents": ["a"], "model": "bge_reranker_v2_m3", "proba": True, "mod": "interaktiv"})
        self.assertIn("csucs_gb", rr["memoria"])

    def test_nem_merheto_hatternel_a_csucs_null(self):
        from tests.modell_segedek import AlHatter
        eredeti = AlHatter.csucs_ertek
        AlHatter.csucs_ertek = None
        self.addCleanup(lambda: setattr(AlHatter, "csucs_ertek", eredeti))
        r = kliens.chat(self.u, [{"content": "x"}], modell="qwen3_vl_4b")
        self.assertIsNone(r["memoria"]["csucs_gb"])

    def test_m3_mod_kotelezo_ervenytelen_keret_400(self):
        """M3 (C19, T049): a `mod` kötelező; a NaN/inf/≤ 0 és az ismeretlen keret 400 (nem jut el az ütemezőig)."""
        uz = {"messages": [{"content": "x"}], "model": "qwen3_vl_4b", "proba": True}
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.keres(self.u, "/v1/chat/completions", uz)
        self.assertEqual((cm.exception.kod, "mod" in str(cm.exception)), (400, True))
        for rossz in ("nan", "inf", 0, -2, "valami", True):
            with self.subTest(keret=rossz), self.assertRaises(kliens.KliensHiba) as cm:
                kliens.keres(self.u, "/v1/chat/completions", {**uz, "mod": "interaktiv", "keret": rossz})
            self.assertEqual(cm.exception.kod, 400)
        # a kifejezett távol-keret interaktív kérésnél, tétlen (nem távoli) állapotban: nem emel → a 8,5 GB-os modell nem fér
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.chat(self.u, [{"content": "x"}], modell="gemma4_12b", keret="tavol")
        self.assertEqual(cm.exception.kod, 503)

    def test_m3_az_automatikus_feladat_kerese_auto(self):
        """M3 (C19): a core által automatikusnak jelzett feladat kérése akkor is `auto`, ha a lépés `interaktiv`-ot küld:
        aktív használatkor nem indul."""
        self.g.aktivitas.allit("aktiv")
        kliens.automatikus(self.u, "F-auto")
        eredmeny = []
        th = threading.Thread(target=lambda: eredmeny.append(kliens.chat(
            self.u, [{"content": "x"}], modell="qwen3_vl_4b", mod="interaktiv", feladat_id="F-auto")), daemon=True)
        th.start()
        th.join(0.5)
        self.assertEqual(eredmeny, [])                                     # szünetel (auto)
        self.assertEqual(self.g.utemezo.allapot()["fuggo"][0]["mod"], "auto")
        r = kliens.chat(self.u, [{"content": "x"}], modell="qwen3_vl_4b", mod="interaktiv", feladat_id="F-kezi")
        self.assertTrue(r["proba"])                                        # a nem jelzett feladat interaktív marad
        self.g.aktivitas.allit("tetlen")
        th.join(5)
        self.assertEqual(len(eredmeny), 1)
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.keres(self.u, "/v1/automatikus", {})
        self.assertEqual(cm.exception.kod, 400)

    def test_keret_503_beagyazas_rerank_router_unload(self):
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.chat(self.u, [{"content": "x"}], modell="gemma4_12b")
        self.assertEqual(cm.exception.kod, 503)
        self.assertEqual(kliens.beagyaz(self.u, ["a", "b"], model="bge_m3", proba=True), [[1.0, 0.0], [1.0, 0.0]])
        r = kliens.keres(self.u, "/v1/rerank", {"query": "q", "documents": ["a", "bbb"], "model": "bge_reranker_v2_m3", "mod": "interaktiv",
                                                "proba": True})
        self.assertEqual([x["relevance_score"] for x in r["results"]], [1.0, 3.0])
        self.tabla.rogzit("rerank", "bge_reranker_v2_m3", 0.5, "v1", kalibralt=True)
        self.assertEqual(kliens.keres(self.u, "/router/valaszt", {"feladat": "rerank"})["modell"], "bge_reranker_v2_m3")
        self.assertEqual(len(kliens.keres(self.u, "/router")["tabla"]), 1)
        kliens.keres(self.u, "/unload", {})
        self.assertIsNone(kliens.health(self.u)["modell"])
        self.assertEqual(self.g.betolto.zar.tartalom(), "")


class WorkerMegszakitasTest(unittest.TestCase):
    """C17: a leállított feladat folyó generálása a workerben megszakad (`POST /v1/megszakit`)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)
        self.tabla = Tabla(self.b.router_db)
        self.elindult = threading.Event()
        self.g = Gazda(self.b, al_betolto(self.b, folyamatos=self.elindult), AlAktivitas(), self.tabla,
                       tick_mp=0.02, naplo=lambda s: None)
        self.srv = Szerver(("127.0.0.1", 0), _handler(self.g))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.u = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.addCleanup(self._leall)

    def _leall(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.g.utemezo.leall()
        self.tabla.close()

    def test_folyo_chat_409_megszakitva(self):
        eredmeny = []

        def kerd():
            try:
                eredmeny.append(kliens.chat(self.u, [{"content": "hosszú"}], modell="qwen3_vl_4b", feladat_id="F-7"))
            except kliens.KliensHiba as e:
                eredmeny.append(e)
        th = threading.Thread(target=kerd, daemon=True)
        th.start()
        self.assertTrue(self.elindult.wait(5))
        r = kliens.megszakit(self.u, "F-7")
        self.assertEqual(r, {"ok": True, "megszakitott": 1})
        th.join(5)
        self.assertEqual(len(eredmeny), 1)
        self.assertIsInstance(eredmeny[0], kliens.KliensHiba)
        self.assertEqual(eredmeny[0].kod, 409)
        self.assertTrue(eredmeny[0].adat["megszakitva"])
        # a leállított feladat későn érkező kérése sem indul; a worker él és kiszolgál mást
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.chat(self.u, [{"content": "késő"}], modell="qwen3_vl_4b", feladat_id="F-7")
        self.assertEqual(cm.exception.kod, 409)
        self.assertTrue(kliens.health(self.u)["ok"])

    def test_hibas_megszakitas_400_es_a_kliens_viszi_a_feladat_azonositot(self):
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.keres(self.u, "/v1/megszakit", {})
        self.assertEqual(cm.exception.kod, 400)
        body = kliens._feladat_id({"messages": []})
        self.assertNotIn("feladat_id", body)                         # MOS_FELADAT nélkül nincs mit vinni
        os.environ["MOS_FELADAT"] = "F-3"
        self.addCleanup(os.environ.pop, "MOS_FELADAT", None)
        self.assertEqual(kliens._feladat_id({"messages": []})["feladat_id"], "F-3")


class WorkerTitokTest(unittest.TestCase):
    """C33 (T182, T183): a titkos gazda a régi `1`-et elutasítja; a kliens a pidfájlból jegyzi a titkot; a kézfogás határidős."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.b = beallitas(self.cfg, helyreallas_mp=0.05)
        self.tabla = Tabla(self.b.router_db)
        self.g = Gazda(self.b, al_betolto(self.b), AlAktivitas(), self.tabla, tick_mp=0.02, naplo=lambda s: None,
                       titok="titok-123456789012345")
        self.srv = Szerver(("127.0.0.1", 0), _handler(self.g))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]
        self.u = f"http://127.0.0.1:{self.port}"
        self.addCleanup(self._leall)

    def _leall(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.g.utemezo.leall()
        self.tabla.close()

    def test_a_titok_nelkuli_keres_403_a_pidfajlbol_jegyzett_titokkal_200(self):
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.health(self.u)                                     # a kliens még nem ismeri: a régi `1`-et küldi
        self.assertEqual(cm.exception.kod, 403)
        pidf = self.cfg.path("run") / "worker.pid"
        pidf.parent.mkdir(parents=True, exist_ok=True)
        pidf.write_text(f"{os.getpid()} {self.port} titok-123456789012345\n")
        self.assertEqual(kliens.fut_url(self.cfg), self.u)
        self.assertTrue(kliens.health(self.u)["ok"])
        # előre „mérgezni” csak feladatsor-alakú azonosítót lehet, és csak a titokkal
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.megszakit(self.u, "barmi")
        self.assertEqual(cm.exception.kod, 400)
        self.assertEqual(kliens.megszakit(self.u, "F-20261008-101500-3"), {"ok": True, "megszakitott": 0})

    def test_a_kezfogas_hataridos_az_elakado_worker_leall(self):
        f = kliens.Folyamat(self.cfg, [sys.executable, "-c", "import time; time.sleep(60)"])
        t0 = time.monotonic()
        with self.assertRaises(kliens.KliensHiba) as cm:
            f.biztosit(timeout=1)
        self.assertEqual(cm.exception.kod, 503)
        self.assertIn("nem jelentkezett", str(cm.exception))
        self.assertLess(time.monotonic() - t0, 10)
        self.assertIsNone(f.proc)

    def test_az_atvett_idegen_worker_halala_utan_el_hamis(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (p.kill(), p.wait()))
        pidf = self.cfg.path("run") / "worker.pid"
        pidf.parent.mkdir(parents=True, exist_ok=True)
        pidf.write_text(f"{p.pid} {self.port} titok-123456789012345\n")
        f = kliens.Folyamat(self.cfg)
        self.assertEqual(f.biztosit(), self.u)                        # az idegen (a pidfájl szerinti) workert veszi át
        self.assertTrue(f.el())
        p.kill()
        p.wait()
        self.assertFalse(f.el())                                      # a pidfájl folyamata halott: nem él (a `_figyel` kilép)


class WorkerFolyamatTest(unittest.TestCase):
    """A valódi `python -m core.modell.worker`: kézfogás, pidfájl, egyetlen worker, stdin-EOF → kilépés."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)
        os.environ["MOS_ROOT"] = str(self.root)
        self.addCleanup(os.environ.pop, "MOS_ROOT", None)

    def test_eletciklus(self):
        f = kliens.Folyamat(self.cfg, [sys.executable, "-B", "-m", "core.modell.worker"])
        u = f.biztosit()
        self.addCleanup(f.leallit)
        h = kliens.health(u)
        self.assertTrue(h["ok"])
        self.assertIsNone(h["modell"])
        pidf = self.cfg.path("run") / "worker.pid"
        pid, port, titok = pidf.read_text().split()
        self.assertEqual(u, f"http://127.0.0.1:{port}")
        # C33 (T182): munkamenet-titok, 0600-as pidfájl; a régi `X-Manifold: 1` nem elég
        self.assertEqual(pidf.stat().st_mode & 0o777, 0o600)
        self.assertGreaterEqual(len(titok), 20)
        c = http.client.HTTPConnection("127.0.0.1", int(port), timeout=10)
        c.request("GET", "/health", headers={"X-Manifold": "1"})
        self.assertEqual(c.getresponse().status, 403)
        c.close()
        self.assertEqual(kliens.fut_url(self.cfg), u)
        # második worker nem indul (worker.lock)
        p = subprocess.run([sys.executable, "-B", "-m", "core.modell.worker"], input=b"", capture_output=True,
                           env={**os.environ}, cwd=str(REPO), timeout=30)
        self.assertEqual(p.returncode, 3)
        # a már futót egy új kliens-folyamat is megtalálja
        self.assertEqual(kliens.Folyamat(self.cfg).biztosit(), u)
        # M3 (C19): a keretes mérés saját workert kér — a futó idegent nem használja
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.Folyamat(self.cfg, env={"MANIFOLD_MODELL_KERET_GB": "9"}, sajat=True).biztosit()
        self.assertEqual(cm.exception.kod, 503)
        self.assertEqual(kliens.health(u)["keret_felulirva"], None)
        proc = f.proc
        f.leallit()
        self.assertEqual(proc.returncode, 0)
        self.assertFalse((self.cfg.path("run") / "worker.pid").exists())
        self.assertIsNone(kliens.fut_url(self.cfg))
        sajat = kliens.Folyamat(self.cfg, env={"MANIFOLD_MODELL_KERET_GB": "9"}, sajat=True)
        u2 = sajat.biztosit()
        self.addCleanup(sajat.leallit)
        self.assertEqual(kliens.health(u2)["keret_felulirva"], 9.0)          # a saját worker a felülírt kerettel fut


if __name__ == "__main__":
    unittest.main()
