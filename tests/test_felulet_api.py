"""A felület core-oldala (C07): a tartós felület-állapot végpontja és az `app/dist` kiszolgálása — álgyökéren.

Amit őriz: az állapot a `{felulet}` fájlba kerül atomi cserével (sérült fájlból üres állapot lesz), a nem
objektum vagy túl nagy állapot 400, és a core a `dist` fájljait szolgálja ki, a pontfájlokat és a kilépő
utat nem.
"""
import http.client
import json
import os
import threading
import unittest

from core import felulet, server
from tests.helpers import API_TITOK, alg_core, tmpdir


class _Kimenet:
    def __init__(self):
        self.sorok, self.jel = [], threading.Event()

    def write(self, s):
        self.sorok.append(s)
        self.jel.set()

    def flush(self):
        pass


class FeluletApiTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        dist = self.cfg.path("app_dist")
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>Manifold</title><div id=app></div>", encoding="utf-8")
        (dist / "assets").mkdir()
        (dist / "assets" / "a.js").write_text("export {}", encoding="utf-8")
        (dist / ".rejtett").write_text("x", encoding="utf-8")
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def k(self, method, path, body=None, fejlec=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json", **(fejlec or {})}
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        t = r.read()
        tipus = r.getheader("Content-Type", "")
        return r.status, (json.loads(t) if t and tipus.startswith("application/json") else t), tipus

    def test_allapot_ures_majd_mentve(self):
        kod, d, _ = self.k("GET", "/api/felulet/allapot")
        self.assertEqual((kod, d), (200, {"allapot": {}}))
        allapot = {"verzio": 1, "tema": "sotet", "legutobbiFajlok": ["Matek/Mértani sorozat.md"]}
        self.assertEqual(self.k("PUT", "/api/felulet/allapot", {"allapot": allapot})[0], 200)
        self.assertEqual(self.k("GET", "/api/felulet/allapot")[1], {"allapot": allapot})
        f = self.cfg.path("felulet")
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), allapot)
        self.assertEqual([p.name for p in f.parent.iterdir() if p.name.endswith("manifold-tmp")], [])
        self.assertFalse(str(f).startswith(str(self.v)))            # a vaulton kívül

    def test_hibas_allapot(self):
        self.assertEqual(self.k("PUT", "/api/felulet/allapot", {"allapot": [1, 2]})[0], 400)
        self.assertEqual(self.k("PUT", "/api/felulet/allapot", {})[0], 400)
        nagy = {"x": "a" * (felulet.MAX_MERET + 1)}
        self.assertEqual(self.k("PUT", "/api/felulet/allapot", {"allapot": nagy})[0], 400)
        self.assertEqual(self.k("GET", "/api/felulet/allapot", fejlec={"X-Manifold": "0"})[0], 403)

    def test_serult_fajl_ures_allapot(self):
        f = self.cfg.path("felulet")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{félbe", encoding="utf-8")
        self.assertEqual(self.k("GET", "/api/felulet/allapot")[1], {"allapot": {}})

    def test_dist_kiszolgalasa(self):
        kod, t, tipus = self.k("GET", "/")
        self.assertEqual(kod, 200)
        self.assertIn(b'<div id=app>', t)
        self.assertTrue(tipus.startswith("text/html"))
        kod, _, tipus = self.k("GET", "/assets/a.js")
        self.assertEqual(kod, 200)
        self.assertIn("javascript", tipus)
        self.assertEqual(self.k("GET", "/.rejtett")[0], 404)
        self.assertEqual(self.k("GET", "/../config/os.toml")[0], 404)
        self.assertEqual(self.k("GET", "/assets/%2e%2e/%2e%2e/config/os.toml")[0], 404)


if __name__ == "__main__":
    unittest.main()
