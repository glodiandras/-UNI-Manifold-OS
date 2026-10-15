"""A gráfnézet kiegészítő végpontjai (C13): jegyzetenkénti címke és tulajdonság, az Obsidian gráf-beállításai.
Álvaulton; a `/api/vault/graf` változatlan marad (csúcs- és élhalmaz = a core gráfja)."""
import json
import os
import threading
import unittest
import urllib.parse

from core import server
from core.index import graf_meta
from tests.helpers import API_TITOK, tmpdir
from tests.index_segedek import ALAP, alvault, index_indit, var_ra
from tests.test_core_api import _Kimenet

GRAPH_JSON = {
    "search": "tag:#x",
    "showTags": False,
    "showAttachments": True,
    "hideUnresolved": False,
    "showOrphans": False,
    "showArrow": True,
    "textFadeMultiplier": -0.5,
    "nodeSizeMultiplier": 2.25,
    "lineSizeMultiplier": 0.5,
    "centerStrength": 0.25,
    "repelStrength": 20,
    "linkStrength": 0.55,
    "linkDistance": 230,
    "colorGroups": [
        {"query": "tag:#Mathematics", "color": {"a": 1, "rgb": 5025616}},
        {"query": "file:.canvas", "color": {"a": 0.5, "rgb": 15728640}},
        {"query": "hibás rgb", "color": {"a": 1, "rgb": "piros"}},
        {"query": 7, "color": {"a": 1, "rgb": 1}},
        "nem objektum",
    ],
}


class GrafMetaTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)

    def indit(self, fajlok):
        cfg, v = alvault(self._t.name, fajlok)
        ix, _ = index_indit(cfg)
        self.addCleanup(ix.leallit)
        return ix, v

    def test_cimkek_es_tulajdonsagok_jegyzetenkent(self):
        ix, _ = self.indit({
            **ALAP,
            "T1.md": "---\nTags:\n  - Fizika/Mechanika\n  - Matek\nStatus: kész\nSzam: 3\nLista: [a, b]\n---\n"
                     "#Matek és #Optika\n",
            "T2.md": "szöveg\n",
        })
        m = graf_meta.graf_meta(ix)
        self.assertEqual(set(m), {"cimkek", "tulajdonsagok"})
        self.assertEqual(m["cimkek"]["T1.md"], ["Fizika/Mechanika", "Matek", "Optika"])      # egyszer, sorrendben
        self.assertEqual(m["cimkek"]["Cél.md"], ["Math/Algebra"])
        self.assertNotIn("T2.md", m["cimkek"])                                                # címke nélkül nincs kulcs
        self.assertNotIn("T2.md", m["tulajdonsagok"])
        t = m["tulajdonsagok"]["T1.md"]
        self.assertEqual(t["Status"], ["kész"])
        self.assertEqual(t["Szam"], ["3"])
        self.assertEqual(t["Lista"], ["a", "b"])

    def test_a_hosszu_ertek_vagott(self):
        ix, v = self.indit({"H.md": "---\nHosszu: " + "x" * 500 + "\n---\n", "Z.md": "---\nStatus: x\n---\n"})
        m = graf_meta.graf_meta(ix)
        self.assertEqual(len(m["tulajdonsagok"]["H.md"]["Hosszu"][0]), graf_meta.MAX_ERTEK_HOSSZ)
        self.assertIn("Z.md", m["tulajdonsagok"])

    def test_beallitasok_a_graph_jsonbol(self):
        cfg, v = alvault(self._t.name, {"A.md": "x\n"})
        (v / ".obsidian").mkdir(exist_ok=True)
        (v / ".obsidian" / "graph.json").write_text(json.dumps(GRAPH_JSON), encoding="utf-8")
        b = graf_meta.graf_beallitasok(v)
        self.assertTrue(b["van"])
        self.assertEqual(b["kereses"], "tag:#x")
        self.assertTrue(b["mutat_mellekletek"])
        self.assertFalse(b["mutat_arvak"])
        self.assertTrue(b["nyil"])
        self.assertEqual(b["erok"], {"kozep": 0.25, "taszitas": 20.0, "rugo": 0.55, "tavolsag": 230.0})
        self.assertEqual(b["meret_szorzo"], 2.25)
        self.assertEqual(b["szoveg_halvanyitas"], -0.5)
        self.assertEqual(b["szincsoportok"], [
            {"lekerdezes": "tag:#Mathematics", "szin": "#4caf50", "alfa": 1.0},         # 5025616 = 0x4CAF50
            {"lekerdezes": "file:.canvas", "szin": "#f00000", "alfa": 0.5},
        ])                                                                              # a hibás csoportok kimaradnak

    def test_hianyzo_es_hibas_graph_json(self):
        cfg, v = alvault(self._t.name, {"A.md": "x\n"})
        self.assertEqual(graf_meta.graf_beallitasok(v), {"van": False})                # nincs fájl
        (v / ".obsidian").mkdir(exist_ok=True)
        g = v / ".obsidian" / "graph.json"
        g.write_text("{nem json", encoding="utf-8")
        self.assertEqual(graf_meta.graf_beallitasok(v), {"van": False})
        g.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(graf_meta.graf_beallitasok(v), {"van": False})
        g.write_text("{}", encoding="utf-8")                                            # üres, de érvényes
        b = graf_meta.graf_beallitasok(v)
        self.assertTrue(b["van"])
        self.assertEqual(b["szincsoportok"], [])
        self.assertEqual(b["erok"], {})
        self.assertTrue(b["mutat_mellekletek"])

    def test_nem_ir_a_vaultba(self):
        cfg, v = alvault(self._t.name, {"A.md": "x\n"})
        (v / ".obsidian").mkdir(exist_ok=True)
        g = v / ".obsidian" / "graph.json"
        g.write_text(json.dumps(GRAPH_JSON), encoding="utf-8")
        elotte = (g.read_bytes(), g.stat().st_mtime_ns)
        graf_meta.graf_beallitasok(v)
        self.assertEqual((g.read_bytes(), g.stat().st_mtime_ns), elotte)


class GrafMetaApiTest(unittest.TestCase):
    """A két végpont a valódi core-szerveren, és a `/graf` változatlansága."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.v = alvault(self._t.name)
        (self.v / ".obsidian").mkdir(exist_ok=True)
        (self.v / ".obsidian" / "graph.json").write_text(json.dumps(GRAPH_JSON), encoding="utf-8")
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)
        self.assertTrue(var_ra(lambda: self.get("/api/vault/index")[1].get("kesz"), 30))

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def get(self, vegpont, **q):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", vegpont + ("?" + urllib.parse.urlencode(q) if q else ""),
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def test_vegpontok(self):
        kod, m = self.get("/api/vault/graf-meta")
        self.assertEqual(kod, 200)
        self.assertEqual(m["cimkek"]["Cél.md"], ["Math/Algebra"])
        kod, b = self.get("/api/vault/graf-beallitasok")
        self.assertEqual(kod, 200)
        self.assertTrue(b["van"])
        self.assertEqual(len(b["szincsoportok"]), 2)

    def test_limit_ellenorzes_mint_a_tobbi_vegponton(self):
        self.assertEqual(self.get("/api/vault/graf-meta", limit="0")[0], 400)

    def test_a_graf_valtozatlan_alaku(self):
        kod, g = self.get("/api/vault/graf")
        self.assertEqual(kod, 200)
        self.assertEqual(set(g), {"csucsok", "elek", "feloldatlan", "tobbertelmu", "canvas_hiba"})
        self.assertTrue(all(isinstance(c, str) for c in g["csucsok"]))
        self.assertNotIn(".obsidian/graph.json", g["csucsok"])


if __name__ == "__main__":
    unittest.main()
