"""C36b: az AI-réteg végpontjai a valódi core-on, álvaulton és **álworkerrel** (`core/cpp_ai.py`): `/api/cpp/ai/allapot`, `POST
/api/cpp/ai`, `/api/cpp/ai/{id}`, `/api/cpp/ai/megszakit`, `/api/cpp/ai/tipp`, a `cpp_ai` WS-események és a `cpp_tipp`
tracker-esemény. Modell nem töltődik be: a worker egy tesztbeli HTTP-szerver (a `{run}/worker.pid`-en át találja meg a core), amely a
router döntését és a válasz-folyamot adja.

A hibaágak eszközlánc nélkül is futnak; a teljes út a valódi LLVM-mel és `sandbox-exec`-cel (különben `[indokolt]` kihagyás)."""
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

from core.modell import kalibracio
from tests.helpers import ir
from tests.test_core_api import ws_csatlakozik
from tests.test_cpp_api import CPP, JEGYZET, NOTE, OK_SKIP, OSSZEG, VAN, CppApiAlap

HIBAS = OSSZEG.replace("a + b", "a - b")
MAGYAR = ("A program kivonja a két számot ahelyett, hogy összeadná őket, ezért a teszt kimenete hibás lesz. A műveleti jelet "
          "kell megnézni a kiírásban.")


class AlWorker:
    """A worker álja: `/health`, `/router/valaszt` (kalibrált vagy 409), `/v1/chat/stream` (NDJSON-folyam)."""

    def __init__(self, valasz: str = "", kalibralt: bool = True, kesleltetes: float = 0.0):
        self.valasz, self.kalibralt, self.kesleltetes = valasz, kalibralt, kesleltetes
        self.keresek: list[dict] = []
        kulso = self

        class Kezelo(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _kuld(self, kod, d):
                t = json.dumps(d).encode()
                self.send_response(kod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(t)))
                self.end_headers()
                self.wfile.write(t)

            def do_GET(self):
                self._kuld(200, {"ok": True, "pid": os.getpid()})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.path == "/router/valaszt":
                    if not kulso.kalibralt:
                        return self._kuld(409, {"hiba": "a(z) kod feladatra nincs kalibrált modell", "nincs_kalibralt": True})
                    return self._kuld(200, {"modell": "qwen35_4b", "var_tavolra": False, "indok": "a legjobb kalibrált"})
                if self.path == "/v1/chat/stream":
                    kulso.keresek.append(body)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.end_headers()
                    try:
                        for szo in kulso.valasz.split(" "):
                            if kulso.kesleltetes:
                                time.sleep(kulso.kesleltetes)
                            self.wfile.write((json.dumps({"tipus": "token", "szoveg": szo + " "}) + "\n").encode())
                            self.wfile.flush()
                        self.wfile.write((json.dumps({"tipus": "vege", "modell": "qwen35_4b", "proba": False}) + "\n").encode())
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return None
                return self._kuld(404, {"hiba": "nincs"})

        self.szerver = ThreadingHTTPServer(("127.0.0.1", 0), Kezelo)
        self.szerver.daemon_threads = True
        threading.Thread(target=self.szerver.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return self.szerver.server_address[1]

    def leall(self):
        self.szerver.shutdown()
        self.szerver.server_close()


class AIApiAlap(CppApiAlap):
    KALIBRALT = True

    def elokeszit(self):
        super().elokeszit()
        ir(self.v, CPP, HIBAS)
        if self.KALIBRALT:
            t = kalibracio.megnyit(self.cfg)
            try:
                # Audit 4: a kalibrált sor csak az arany AKTUÁLIS verzióján számít (63(a); cpp_ai Verziok-szűrő): az álgyökér
                # `{modulok}/eval/kod/feladat.py`-ja adja a verziót (a test_gepi_iras `aranyverzio` mintája)
                mappa = self.cfg.path("modulok") / "eval" / "kod"
                mappa.mkdir(parents=True, exist_ok=True)
                (mappa / "feladat.py").write_text('ROUTER_FELADAT = "kod"\nVERZIO = "kod-v1"\n', encoding="utf-8")
                t.rogzit("kod", "qwen35_4b", 0.8, "kod-v1", True, "teszt", ervenyes=True)
            finally:
                t.close()

    def worker(self, **kw) -> AlWorker:
        w = AlWorker(**kw)
        self.addCleanup(w.leall)
        p = self.cfg.path("run") / "worker.pid"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{os.getpid()} {w.port}")
        return w

    def kesz_index(self):
        self.assertTrue(self.vegpont_var(lambda: self.k("GET", "/api/cpp/feladat?ut=" + quote(CPP))[1].get("jegyzet") == JEGYZET))

    def esemenyek(self, ws, aid, vege=("kesz", "hiba", "megszakitva"), mp=120):
        ki = []
        t0 = time.monotonic()
        while time.monotonic() - t0 < mp:
            e = json.loads(ws.recv(timeout=mp))
            if e.get("tipus") == "cpp_ai" and e["ai"] == aid:
                ki.append(e)
                if e["szakasz"] in vege:
                    break
        return ki

    def futtat(self, mod, **d):
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            kod, r = self.k("POST", "/api/cpp/ai", {"mod": mod, "ut": JEGYZET, **d})
            self.assertEqual(kod, 202, r)
            return r, self.esemenyek(ws, r["ai"])

    def tipp_sorok(self):
        c = self.pos()
        return [json.loads(s[0]) for s in c.execute("SELECT adat FROM tr_esemeny WHERE tipus = 'cpp_tipp' ORDER BY rowid")]


class NincsKalibraltTest(AIApiAlap):
    KALIBRALT = False

    def test_allapot_es_hibaagak(self):
        kod, a = self.k("GET", "/api/cpp/ai/allapot")
        self.assertEqual(kod, 200)
        self.assertFalse(a["kalibralt"])
        self.assertIn("nincs kalibrált modell", a["indok"])
        self.assertEqual(self.k("POST", "/api/cpp/ai", {"mod": "rossz", "ut": JEGYZET})[0], 400)
        kod, r = self.k("POST", "/api/cpp/ai", {"mod": "megoldas", "ut": JEGYZET})
        self.assertEqual((kod, r.get("kod")), (400, "megerosites_kell"))
        self.assertEqual(self.k("POST", "/api/cpp/ai/tipp", {"ai": "ai-000000000000", "szint": 1})[0], 404)
        self.assertEqual(self.k("POST", "/api/cpp/ai/tipp", {})[0], 400)
        self.assertEqual(self.k("POST", "/api/cpp/ai/megszakit", {"ai": "x"})[0], 404)
        self.assertEqual(self.k("GET", "/api/cpp/ai/ai-123")[0], 404)

    @unittest.skipUnless(VAN, OK_SKIP)
    def test_kalibralt_modell_nelkul_503(self):
        self.kesz_index()
        kod, r = self.k("POST", "/api/cpp/ai", {"mod": "hiba", "ut": JEGYZET})
        self.assertEqual(kod, 503)
        self.assertIn(r.get("kod"), ("nincs_kalibralt", "nincs_eszkoztar"))


@unittest.skipUnless(VAN, OK_SKIP)
class AIUtTest(AIApiAlap):
    ESZKOZTARRAL = True

    def setUp(self):
        super().setUp()
        self.kesz_index()

    def test_allapot_kalibralt(self):
        a = self.k("GET", "/api/cpp/ai/allapot")[1]
        self.assertEqual((a["kalibralt"], a["modell"]), (True, "qwen35_4b"))

    def test_mi_a_hiba_az_alworkerrel(self):
        w = self.worker(valasz=MAGYAR + "\nHIBA: 5 egyeb")
        r, es = self.futtat("hiba")
        szak = [e["szakasz"] for e in es]
        self.assertEqual(szak[0], "indul")
        self.assertIn("ellenorzes", szak)
        self.assertEqual(szak[-1], "kesz", es)
        er = next(e for e in es if e["szakasz"] == "eredmeny")
        self.assertEqual((er["sor"], er["fajta"]), (5, "egyeb"))
        k = w.keresek[0]
        self.assertEqual((k["feladat"], k["mod"], k["keret"], k["temperature"]), ("kod", "interaktiv", "munka", 0.0))
        self.assertNotIn("model", k)                                   # a router választ (D9), nem a kérés
        self.assertIn("5 |     std::cout << a - b", k["messages"][0]["content"])
        f = self.k("GET", f"/api/cpp/ai/{r['ai']}")[1]
        self.assertEqual((f["allapot"], f["modell"]), ("kesz", "qwen35_4b"))
        self.assertEqual(self.k("GET", "/api/vault/fajl?ut=" + quote(CPP))[1]["tartalom"], HIBAS)   # 53(d)

    def test_a_worker_routere_nem_ad_modellt(self):
        self.worker(kalibralt=False)
        _, es = self.futtat("hiba")
        self.assertEqual((es[-1]["szakasz"], es[-1]["kod"]), ("hiba", "nincs_kalibralt"))

    def test_tipp_felfedes_a_trackerbe_szintenkent_egyszer(self):
        self.worker(valasz="1. IRÁNY: nézd a kiírást.\n2. ALGORITMUS: összeadás kell.\n3. HELY: az 5. sorban.")
        r, es = self.futtat("tipp")
        er = next(e for e in es if e["szakasz"] == "eredmeny")
        self.assertEqual([s["cim"] for s in er["szintek"]], ["Irány", "Algoritmus", "Hely"])
        self.assertEqual(self.k("POST", "/api/cpp/ai/tipp", {"ai": r["ai"], "szint": 1})[1]["uj"], True)
        self.assertEqual(self.k("POST", "/api/cpp/ai/tipp", {"ai": r["ai"], "szint": 1})[1]["uj"], False)
        self.k("POST", "/api/cpp/ai/tipp", {"ai": r["ai"], "szint": 2})
        self.assertEqual(self.k("POST", "/api/cpp/ai/tipp", {"ai": r["ai"], "szint": 9})[0], 400)
        self.assertEqual(self.tipp_sorok(), [{"szint": 1}, {"szint": 2}])

    def test_teljes_megoldas_megerositessel_negyes_szint(self):
        self.worker(valasz="Összeadásra javítottam.\n```cpp\n" + OSSZEG + "```")
        _, es = self.futtat("megoldas", megerosit=True)
        er = next(e for e in es if e["szakasz"] == "eredmeny")
        self.assertTrue(er["ellenorzott"])
        self.assertEqual((er["atment_db"], er["ossz"]), (2, 2))
        self.assertEqual(self.tipp_sorok(), [{"szint": 4}])
        self.assertEqual(self.k("GET", "/api/vault/fajl?ut=" + quote(CPP))[1]["tartalom"], HIBAS)

    def test_egyszerre_egy_es_megszakitas(self):
        self.worker(valasz=" ".join(["szó"] * 400), kesleltetes=0.05)
        with ws_csatlakozik(self.port) as ws:
            json.loads(ws.recv(timeout=5))
            kod, r = self.k("POST", "/api/cpp/ai", {"mod": "teszt", "ut": JEGYZET})
            self.assertEqual(kod, 202)
            kod2, r2 = self.k("POST", "/api/cpp/ai", {"mod": "teszt", "ut": JEGYZET})
            self.assertEqual((kod2, r2.get("kod")), (409, "foglalt"))
            self.esemenyek(ws, r["ai"], vege=("generalas", "modell", "kesz", "hiba"), mp=60)
            self.assertTrue(self.k("POST", "/api/cpp/ai/megszakit", {"ai": r["ai"]})[1]["megszakitva"])
            es = self.esemenyek(ws, r["ai"], mp=30)
        self.assertEqual(es[-1]["szakasz"], "megszakitva")


if __name__ == "__main__":
    unittest.main()
