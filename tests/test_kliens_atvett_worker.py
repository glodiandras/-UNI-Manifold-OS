"""F3 (F3-DESIGN §4, K11): az átvett (egy másik core-tól örökölt) worker eltűnése egy kérés közben → a kliens EGYSZER
újraindítja és a kérést EGYSZER megismétli. Nem ismétel: a saját worker halálánál, egy élő (csak lassú) workernél, a nem
modellmunka-kéréseknél, a `Folyamat` nélküli (lépés-) címeknél, és a második hibánál. Ál-worker: egy kis HTTP-szerver."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from core.modell import kliens
from tests.helpers import alg_core, tmpdir

AL_WORKER = r'''
import json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
mod, nev, szamlalo = sys.argv[1], sys.argv[2], sys.argv[3]
with open(szamlalo, "a", encoding="utf-8") as f:
    f.write(nev + "\n")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _valasz(self, d):
        b = json.dumps(d).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._valasz({"ok": True, "pid": os.getpid(), "fut": None, "fuggo": []})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if mod == "hal":
            os._exit(1)                      # a kérés közben eltűnik: válasz nélkül
        if mod == "lassu":
            time.sleep(3)
        self._valasz({"forras": nev, "choices": [{"message": {"content": nev}}]})

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print(json.dumps({"port": srv.server_address[1], "pid": os.getpid()}), flush=True)

def figyel():
    try:
        while sys.stdin.buffer.read(4096):
            pass
    except Exception:
        pass
    os._exit(0)

threading.Thread(target=figyel, daemon=True).start()
srv.serve_forever()
'''


class AtvettWorkerTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.al = Path(self._t.name) / "al_worker.py"
        self.al.write_text(AL_WORKER, encoding="utf-8")
        self.szamlalo = Path(self._t.name) / "indulasok.txt"

    def _indulasok(self) -> list[str]:
        return self.szamlalo.read_text(encoding="utf-8").split() if self.szamlalo.exists() else []

    def _atvett(self, mod: str) -> str:
        """Egy „másik core” workere: fut, és a gépszintű pidfájl nevezi meg."""
        p = subprocess.Popen([sys.executable, str(self.al), mod, "idegen", str(self.szamlalo)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        self.addCleanup(self._leallit, p)
        d = json.loads(p.stdout.readline())
        pidf = kliens.pidfajl(self.cfg)
        pidf.parent.mkdir(parents=True, exist_ok=True)
        pidf.write_text(f"{d['pid']} {d['port']} titok-123456789012345\n")
        return f"http://127.0.0.1:{d['port']}"

    @staticmethod
    def _leallit(p):
        if p.poll() is None:
            p.kill()
        p.wait()
        p.stdin.close()
        p.stdout.close()

    def _folyamat(self, mod: str) -> kliens.Folyamat:
        f = kliens.Folyamat(self.cfg, [sys.executable, str(self.al), mod, "uj", str(self.szamlalo)])
        self.addCleanup(f.leallit)
        return f

    def test_az_eltunt_atvett_worker_helyett_egyszer_ujraindit_es_ismetel(self):
        u = self._atvett("hal")
        f = self._folyamat("ok")
        self.assertEqual(f.biztosit(), u, "a pidfájl szerinti workert veszi át")
        self.assertIsNone(f.proc)
        r = kliens.chat(u, [{"role": "user", "content": "x"}], feladat="szoveg", timeout=20)
        self.assertEqual(r["forras"], "uj", "a megismételt kérés az újraindított workertől jött")
        self.assertIsNotNone(f.proc)
        self.assertNotEqual(f.url, u)
        self.assertEqual(self._indulasok(), ["idegen", "uj"], "pontosan egy újraindítás")
        self.assertEqual(kliens.keres(f.url, "/v1/embeddings", {"input": ["y"]}, timeout=20)["forras"], "uj")
        self.assertEqual(self._indulasok(), ["idegen", "uj"])

    def test_a_megismetelt_keres_masodik_hibaja_tovabbmegy(self):
        u = self._atvett("hal")
        f = self._folyamat("hal")
        f.biztosit()
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.keres(u, "/v1/embeddings", {"input": ["x"]}, timeout=20)
        self.assertTrue(cm.exception.adat.get("kapcsolat"))
        self.assertEqual(self._indulasok(), ["idegen", "uj"], "egyszer indult újra, többször nem")

    def test_a_sajat_worker_halala_nem_ismetel(self):
        f = self._folyamat("hal")
        u = f.biztosit()
        self.assertIsNotNone(f.proc)
        with self.assertRaises(kliens.KliensHiba):
            kliens.keres(u, "/v1/embeddings", {"input": ["x"]}, timeout=20)
        self.assertEqual(self._indulasok(), ["uj"])

    def test_az_elo_de_lassu_atvett_workert_nem_inditja_ujra(self):
        u = self._atvett("lassu")
        f = self._folyamat("ok")
        f.biztosit()
        with self.assertRaises(kliens.KliensHiba) as cm:
            kliens.keres(u, "/v1/embeddings", {"input": ["x"]}, timeout=0.5)
        self.assertTrue(cm.exception.adat.get("kapcsolat"))
        self.assertEqual(self._indulasok(), ["idegen"])
        self.assertIsNone(f.proc)
        self.assertEqual(f.url, u)

    def test_nem_modellmunka_keres_nem_indit_workert(self):
        u = self._atvett("hal")
        f = self._folyamat("ok")
        f.biztosit()
        with self.assertRaises(kliens.KliensHiba):
            kliens.megszakit(u, "F-20261008-101500-3")
        self.assertEqual(self._indulasok(), ["idegen"])

    def test_folyamat_nelkuli_cim_nem_ismetel(self):
        """A lépés a `MOS_WORKER_URL`-t kapja, `Folyamat` nélkül: workert nem indít (D4)."""
        u = self._atvett("hal")
        with self.assertRaises(kliens.KliensHiba):
            kliens.keres(u, "/v1/embeddings", {"input": ["x"]}, timeout=20)
        self.assertEqual(self._indulasok(), ["idegen"])


if __name__ == "__main__":
    unittest.main()
