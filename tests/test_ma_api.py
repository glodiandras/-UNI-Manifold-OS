"""A C15 HTTP-végpontjai a valódi core-on, álvaulton: `/api/ma`, `/api/naplo/ma`, `/api/sablon/*`.
A hibakódok (400, 404) a szerver hibatérképén át, a WS-esemény a létrehozásról."""
import json
import os
import threading
import unittest
import urllib.parse

from core import server
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.index_segedek import var_ra
from tests.test_core_api import _Kimenet

UT = "X01 - Napló & To-Do/2026-10/Napló/2026-10-02.md"


class C15ApiTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "_Template/Cím.md", "# {{title}}\n{{date:YYYY. MMMM D.}} {{cursor}}")
        ir(self.v, "Feladat.md", "- [ ] ma 📅 2026-10-02\n")
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.port = json.loads(ki.sorok[0])["port"]
        self.addCleanup(self._leall)
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/vault/index")[1].get("kesz"), 30))

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def k(self, method, path, body=None):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def test_ma_vegpont(self):
        kod, d = self.k("GET", "/api/ma?" + urllib.parse.urlencode({"datum": "2026-10-02"}))
        self.assertEqual(kod, 200)
        self.assertEqual((d["datum"], d["felirat"]), ("2026-10-02", "2026. október 2., péntek"))
        self.assertEqual(d["napi"]["ut"], UT)
        self.assertFalse(d["napi"]["letezik"])
        self.assertEqual(d["feladatok"]["osszes_ma"], 1)
        self.assertIn("hiba", d["naptar"])                      # az álgyökérben nincs pos.sqlite
        self.assertEqual(d["kartyak"]["allapot"], "kesz")                  # C23b: a kártyák összesítője (adatbázis nélkül nullák)

    def test_ma_hibas_datum(self):
        self.assertEqual(self.k("GET", "/api/ma?datum=holnap")[0], 400)

    def test_naplo_letrehozas_es_ujranyitas(self):
        kod, d = self.k("POST", "/api/naplo/ma", {"datum": "2026-10-02"})
        self.assertEqual((kod, d["ut"], d["letrejott"]), (200, UT, True))
        self.assertTrue((self.v / UT).is_file())
        self.assertIsInstance(d["kurzor"], int)
        kod, d2 = self.k("POST", "/api/naplo/ma", {"datum": "2026-10-02"})
        self.assertEqual((kod, d2["letrejott"], d2["kurzor"]), (200, False, None))
        # a Ma oldal a létrehozás után látja a jegyzetet
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/ma?datum=2026-10-02")[1]["napi"]["letezik"], 5))

    def test_naplo_hibas_datum(self):
        self.assertEqual(self.k("POST", "/api/naplo/ma", {"datum": "2026-13-40"})[0], 400)
        self.assertFalse((self.v / "X01 - Napló & To-Do").exists())

    def test_sablon_lista_es_kiertekeles(self):
        kod, d = self.k("GET", "/api/sablon/lista")
        self.assertEqual((kod, d["mappa"], [s["nev"] for s in d["sablonok"]]), (200, "_Template", ["Cím"]))
        kod, d = self.k("POST", "/api/sablon/kiertekel", {"ut": "_Template/Cím.md", "cim": "Teszt"})
        self.assertEqual(kod, 200)
        self.assertTrue(d["szoveg"].startswith("# Teszt\n"))
        self.assertEqual(d["kurzor"], len(d["szoveg"]))
        self.assertFalse(d["frontmatter"])

    def test_sablon_hibak(self):
        self.assertEqual(self.k("POST", "/api/sablon/kiertekel", {"ut": "Feladat.md", "cim": "x"})[0], 400)    # nem sablon
        self.assertEqual(self.k("POST", "/api/sablon/kiertekel", {"ut": "_Template/Nincs.md", "cim": "x"})[0], 404)
        self.assertEqual(self.k("POST", "/api/sablon/kiertekel", {"ut": "_Template/Cím.md"})[0], 400)         # nincs cím

    def test_uj_jegyzet_sablonbol(self):
        """C32b: a `{{title}}` az új jegyzet neve, a váz a `Vault.create` útján íródik, névütközés 400, a kurzor a sablon jelénél áll."""
        kod, d = self.k("POST", "/api/sablon/uj", {"sablon": "_Template/Cím.md", "mappa": "", "nev": "Új téma.md"})
        self.assertEqual(kod, 200, d)
        self.assertEqual(d["ut"], "Új téma.md")
        szoveg = (self.v / "Új téma.md").read_text(encoding="utf-8")
        self.assertTrue(szoveg.startswith("# Új téma\n"), szoveg)
        self.assertEqual(d["kurzor"], len(szoveg.encode("utf-16-le")) // 2)
        self.assertEqual(self.k("POST", "/api/sablon/uj", {"sablon": "_Template/Cím.md", "mappa": "", "nev": "új téma"})[0], 400)
        self.assertEqual(self.k("POST", "/api/sablon/uj", {"sablon": "_Template/Cím.md", "mappa": "Nincs", "nev": "X"})[0], 404)
        self.assertEqual(self.k("POST", "/api/sablon/uj", {"sablon": "Feladat.md", "mappa": "", "nev": "Y"})[0], 400)
        self.assertEqual(self.k("POST", "/api/sablon/uj", {"sablon": "_Template/Cím.md", "mappa": ""})[0], 400)

    def test_uj_jegyzet_sablonbol_sema_sertes_megerositessel(self):
        """Javító 7 (64(b), 22(b)): a séma-sértő sablon-frontmatter 409 + lista, jegyzet nélkül; csak `megerosit: true`-val íródik."""
        sablon = "---\nTags:\n  - Mathematics\nicon: rocket\nSource:\nStatus:\nNN:\nCanvas:\n---\n\n# {{title}}\n"
        ir(self.v, "_Template/Ikonos.md", sablon)
        torzs = {"sablon": "_Template/Ikonos.md", "mappa": "", "nev": "Ikonos új"}
        kod, d = self.k("POST", "/api/sablon/uj", torzs)
        self.assertEqual(kod, 409, d)
        self.assertTrue(d["sema_sertes"] and d["megerositheto"])
        self.assertIn(("ismeretlen_kulcs", "icon"), [(p["kod"], p["kulcs"]) for p in d["problemak"]])
        self.assertTrue(all(p["szint"] == "sertes" for p in d["problemak"]))
        self.assertFalse((self.v / "Ikonos új.md").exists())
        # nem logikai megerősítés nem megerősítés (T128)
        self.assertEqual(self.k("POST", "/api/sablon/uj", {**torzs, "megerosit": "true"})[0], 400)
        self.assertEqual(self.k("POST", "/api/sablon/uj", {**torzs, "megerosit": False})[0], 409)
        self.assertFalse((self.v / "Ikonos új.md").exists())
        kod, d = self.k("POST", "/api/sablon/uj", {**torzs, "megerosit": True})
        self.assertEqual((kod, d["ut"]), (200, "Ikonos új.md"), d)
        szoveg = (self.v / "Ikonos új.md").read_text(encoding="utf-8")
        self.assertEqual(szoveg, sablon.replace("{{title}}", "Ikonos új"))          # a váz szó szerint íródik

    def test_uj_jegyzet_sablonbol_tiszta_frontmatter_megerosites_nelkul(self):
        sablon = "---\nTags:\n  - Mathematics\nSource:\nStatus:\nNN:\nCanvas:\n---\n\n# {{title}}\n"
        ir(self.v, "_Template/Tiszta.md", sablon)
        kod, d = self.k("POST", "/api/sablon/uj", {"sablon": "_Template/Tiszta.md", "mappa": "", "nev": "Tiszta új"})
        self.assertEqual((kod, d["ut"]), (200, "Tiszta új.md"), d)

    def test_uj_jegyzet_sablonbol_hiba_szintu_sertes_megerositessel_sem(self):
        ir(self.v, "_Template/Hibas.md", "---\nTags: [Mathematics\n---\n\n# {{title}}\n")
        for megerosit in (False, True):
            kod, d = self.k("POST", "/api/sablon/uj", {"sablon": "_Template/Hibas.md", "mappa": "", "nev": "Hibás új", "megerosit": megerosit})
            self.assertEqual(kod, 400, d)
            self.assertFalse(d["megerositheto"])
            self.assertIn("yaml_hiba", [p["kod"] for p in d["problemak"]])
            self.assertFalse((self.v / "Hibás új.md").exists())

    def test_osszefesules_vegpont(self):
        kod, d = self.k("POST", "/api/vault/tulajdonsagok/osszefesul", {
            "ut": "Jegyzet.md", "fm": "---\nTags:\n  - Mathematics\n---\n", "sablon_fm": "---\nTags:\n  - Physics\n---\n"})
        self.assertEqual(kod, 200, d)
        self.assertEqual(d["egyesitve"], ["Tags"])


if __name__ == "__main__":
    unittest.main()
