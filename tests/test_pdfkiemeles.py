"""C16: a PDF-kiemelés-fájl formátuma (elemző + író) és a `/api/pdf/kiemeles*` végpontok a valódi core-on,
álvaulton: új fájl a sémával, Source-lista, beszúrás és törlés a felhasználói szöveg megőrzésével, ütközés,
pillanatkép."""
import json
import os
import threading
import unittest
import urllib.parse

from core import pdfkiemeles as pk
from core import server, snapshot
from tests.helpers import API_TITOK, alg_core, ir, tmpdir
from tests.index_segedek import var_ra
from tests.test_core_api import _Kimenet

PDF = "Mx - Tankönyvek/10 - Matematika.pdf"
MD = "Mx - Tankönyvek/10 - Matematika – kiemelések.md"
CEL = "10 - Matematika.pdf"


class FormatumTest(unittest.TestCase):
    def test_escape_kozos_vektorok(self):
        """A felület `idezetSor`-jával közös vektorok (C32, T168): `tests/adat/idezet_escape.json`."""
        from tests.helpers import REPO
        vektorok = json.loads((REPO / "tests" / "adat" / "idezet_escape.json").read_text(encoding="utf-8"))
        for e in vektorok["esetek"]:
            with self.subTest(be=e["be"]):
                self.assertEqual(pk._escape(e["be"]), e["ki"])

    def test_ut_cimke_vaz(self):
        self.assertEqual(pk.fajl_ut(PDF), MD)
        self.assertEqual(pk.fajl_ut("Gyökér.PDF"), "Gyökér – kiemelések.md")
        with tmpdir() as t:
            cfg, _, _ = alg_core(t)
        self.assertEqual(pk.cimke(cfg, PDF), "Mathematics")                 # a `[pdf.tags]` térképből (config/os.toml)
        self.assertEqual(pk.cimke(cfg, "Xn - Forrás/a.pdf"), None)
        self.assertEqual(pk.cimke(cfg, "a.pdf"), None)
        self.assertIsNone(pk.cimke(None, PDF))                              # konfig nélkül nincs beépített térkép
        self.assertEqual(pk.h1(PDF), "Matematika – kiemelések")       # a sorszám-előtag nélkül (L46)
        self.assertTrue(pk.vaz(PDF, None).startswith("---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"))

    def test_beszuras_sorrend_es_elemzes(self):
        s = pk.vaz(PDF, "Mathematics")
        s = pk.beszur(s, "k-aaaaaa", 35, "Közép", [[0.1, 0.5, 0.3, 0.02]], CEL)
        s = pk.beszur(s, "k-bbbbbb", 35, "Fent", [[0.1, 0.2, 0.3, 0.02]], CEL)
        s = pk.beszur(s, "k-cccccc", 12, "Korábbi lap", [[0.1, 0.9, 0.3, 0.02]], CEL)
        s = pk.beszur(s, "k-dddddd", 40, "Későbbi lap", [[0.1, 0.9, 0.3, 0.02]], CEL)
        s = pk.beszur(s, "k-eeeeee", 35, "Lent", [[0.1, 0.9, 0.3, 0.02]], CEL)
        k = pk.elemez(s)
        self.assertEqual([(x["id"], x["oldal"], x["szoveg"]) for x in k], [
            ("k-cccccc", 12, "Korábbi lap"), ("k-bbbbbb", 35, "Fent"), ("k-aaaaaa", 35, "Közép"),
            ("k-eeeeee", 35, "Lent"), ("k-dddddd", 40, "Későbbi lap")])
        self.assertEqual(k[0]["teglalapok"], [[0.1, 0.9, 0.3, 0.02]])
        self.assertIn("## 12. oldal\n\n%%manifold-kiemeles k-cccccc 0.1,0.9,0.3,0.02%%\n> Korábbi lap\n"
                      "> — [[10 - Matematika.pdf#page=12]] ^k-cccccc\n\n## 35. oldal\n", s)
        self.assertNotIn("\n\n\n", s)

    def test_markdown_jelek_nem_torik_a_blokkot(self):
        for szov in ("# Cím", "> idézet", "- elem", "1. elem", "a [[link]] b", "50%% kész", "x ^abc", "```"):
            s = pk.beszur(pk.vaz(PDF, None), "k-abcdef", 3, szov, [[0, 0, 1, 1]], CEL)
            k = pk.elemez(s)
            self.assertEqual((len(k), k[0]["szoveg"]), (1, szov), szov)
            idezet = s.split("%%\n", 1)[1].split("\n")[0]
            self.assertNotIn("[[", idezet)
            self.assertNotIn("%%", idezet)

    def test_torles_es_ures_fejezet(self):
        s = pk.vaz(PDF, None)
        s = pk.beszur(s, "k-aaaaaa", 5, "A", [[0, 0.1, 1, 0.1]], CEL)
        s = pk.beszur(s, "k-bbbbbb", 5, "B", [[0, 0.5, 1, 0.1]], CEL)
        s = pk.beszur(s, "k-cccccc", 9, "C", [[0, 0.5, 1, 0.1]], CEL)
        t = pk.torol(s, "k-bbbbbb")
        self.assertEqual([x["id"] for x in pk.elemez(t)], ["k-aaaaaa", "k-cccccc"])
        t = pk.torol(t, "k-aaaaaa")
        self.assertNotIn("## 5. oldal", t)
        self.assertIn("## 9. oldal", t)
        t = pk.torol(t, "k-cccccc")
        self.assertEqual(t, pk.vaz(PDF, None))
        self.assertNotIn("\n\n\n", t)
        with self.assertRaises(pk.NotFound):
            pk.torol(t, "k-cccccc")

    def test_felhasznaloi_szoveg_erintetlen(self):
        s = pk.beszur(pk.vaz(PDF, None), "k-aaaaaa", 5, "A", [[0, 0.1, 1, 0.1]], CEL)
        s = s.replace("## 5. oldal\n", "## 5. oldal\n\nSaját  megjegyzés  **itt**.\n\n> sima idézet, nem kiemelés\n")
        s2 = pk.beszur(s, "k-bbbbbb", 5, "B", [[0, 0.9, 1, 0.1]], CEL)
        self.assertIn("Saját  megjegyzés  **itt**.\n\n> sima idézet, nem kiemelés\n", s2)
        self.assertEqual([x["id"] for x in pk.elemez(s2)], ["k-aaaaaa", "k-bbbbbb"])
        self.assertEqual(pk.torol(s2, "k-bbbbbb"), s)
        t = pk.torol(s, "k-aaaaaa")                    # a fejezetben saját szöveg maradt: a fejezet marad
        self.assertIn("## 5. oldal\n\nSaját", t)

    def test_crlf_megmarad(self):
        s = pk.vaz(PDF, None).replace("\n", "\r\n")
        s2 = pk.beszur(s, "k-aaaaaa", 5, "A", [[0, 0.1, 1, 0.1]], CEL)
        self.assertNotIn("\n", s2.replace("\r\n", ""))
        self.assertEqual(pk.torol(s2, "k-aaaaaa"), s)

    def test_szoveg_normalizalas(self):
        self.assertEqual(pk.normal_szoveg("A függ-\nvény   értéke­\nnő\x07"), "A függvény értéke nő")


class VegpontTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, PDF, b"%PDF-1.4\n%%EOF\n", "wb")
        ir(self.v, "Xn - Forrás/Más.pdf", b"%PDF-1.4\n", "wb")
        ir(self.v, "M01 - Halmazok/Jegyzet.md", "# Jegyzet\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
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

    def lista(self, pdf=PDF):
        return self.k("GET", "/api/pdf/kiemelesek?" + urllib.parse.urlencode({"ut": pdf}))

    def test_uj_fajl_hozzaadas_torles(self):
        kod, d = self.lista()
        self.assertEqual((kod, d["fajl"], d["kiemelesek"]), (200, None, []))
        kod, d = self.k("POST", "/api/pdf/kiemeles", {"ut": PDF, "oldal": 35, "szoveg": "A függ-\nvény  értéke",
                                                      "teglalapok": [[0.1, 0.2, 0.3, 0.02], [0.1, 0.23, 0.0, 0.02]]})
        self.assertEqual(kod, 200, d)
        self.assertEqual((d["fajl"], d["cel"], d["szoveg"], d["teglalapok"]),
                         (MD, CEL, "A függvény értéke", [[0.1, 0.2, 0.3, 0.02]]))
        szoveg = (self.v / MD).read_text(encoding="utf-8")
        self.assertTrue(szoveg.startswith('---\nTags:\n  - Mathematics\nSource:\n  - "[[10 - Matematika.pdf#page=35]]"\n'
                                          "Status:\nNN:\nCanvas:\n---\n\n# Matematika – kiemelések\n\n## 35. oldal\n"),
                        szoveg)
        elso = d["id"]
        kod, d = self.k("POST", "/api/pdf/kiemeles", {"ut": PDF, "oldal": 7, "szoveg": "Hetedik",
                                                      "teglalapok": [[0, 0, 1, 0.1]]})
        self.assertEqual(kod, 200, d)
        szoveg = (self.v / MD).read_text(encoding="utf-8")
        self.assertIn('Source:\n  - "[[10 - Matematika.pdf#page=7]]"\n  - "[[10 - Matematika.pdf#page=35]]"\nStatus:',
                      szoveg)
        kod, l = self.lista()
        self.assertEqual([(x["oldal"], x["szoveg"]) for x in l["kiemelesek"]], [(7, "Hetedik"), (35, "A függvény értéke")])
        # pillanatkép: a szerkesztő forrása, az útlistán csak a kiemelés-fájl
        c = self.repo.log(1)[0]
        self.assertEqual((c.trailers["Mos-Forras"], c.trailers["Mos-Tetel"]), ("pult-szerkeszto", MD))
        # törlés: a Source követi
        kod, d = self.k("POST", "/api/pdf/kiemeles/torol", {"ut": PDF, "id": elso, "alap": l["hash"]})
        self.assertEqual(kod, 200, d)
        szoveg = (self.v / MD).read_text(encoding="utf-8")
        self.assertIn('Source:\n  - "[[10 - Matematika.pdf#page=7]]"\nStatus:', szoveg)
        self.assertNotIn("## 35. oldal", szoveg)

    def test_utkozes_es_hibak(self):
        kod, d = self.k("POST", "/api/pdf/kiemeles", {"ut": PDF, "oldal": 1, "szoveg": "x", "teglalapok": [[0, 0, 1, 1]]})
        self.assertEqual(kod, 200, d)
        kod, d = self.k("POST", "/api/pdf/kiemeles", {"ut": PDF, "oldal": 2, "szoveg": "y", "teglalapok": [[0, 0, 1, 1]],
                                                      "alap": "0" * 40})
        self.assertEqual(kod, 409, d)
        for rossz in ({"ut": PDF, "oldal": 0, "szoveg": "x", "teglalapok": [[0, 0, 1, 1]]},
                      {"ut": PDF, "oldal": 1, "szoveg": "  ", "teglalapok": [[0, 0, 1, 1]]},
                      {"ut": PDF, "oldal": 1, "szoveg": "x", "teglalapok": []},
                      {"ut": PDF, "oldal": 1, "szoveg": "x", "teglalapok": [[0, 0, "a", 1]]},
                      {"ut": "M01 - Halmazok/Jegyzet.md", "oldal": 1, "szoveg": "x", "teglalapok": [[0, 0, 1, 1]]},
                      {"ut": "../kint.pdf", "oldal": 1, "szoveg": "x", "teglalapok": [[0, 0, 1, 1]]}):
            self.assertEqual(self.k("POST", "/api/pdf/kiemeles", rossz)[0], 400, rossz)
        self.assertEqual(self.k("POST", "/api/pdf/kiemeles", {"ut": "Nincs.pdf", "oldal": 1, "szoveg": "x",
                                                              "teglalapok": [[0, 0, 1, 1]]})[0], 404)
        self.assertEqual(self.k("POST", "/api/pdf/kiemeles/torol", {"ut": PDF, "id": "k-ffffff"})[0], 404)
        self.assertEqual(self.k("POST", "/api/pdf/kiemeles/torol", {"ut": PDF, "id": "rossz"})[0], 400)
        self.assertEqual(self.lista("Xn - Forrás/Más.pdf")[1]["fajl"], None)

    def test_ismeretlen_mappa_ures_tags_es_meglevo_szoveg(self):
        md = "Xn - Forrás/Más – kiemelések.md"
        ir(self.v, md, "---\nTags:\nSource:\n  - \"[[Valami.pdf#page=3]]\"\nStatus:\nNN:\nCanvas:\n---\n\n"
                       "# Más – kiemelések\n\nSaját bevezető.\n")
        self.assertTrue(var_ra(lambda: self.k("GET", "/api/vault/fajl?" + urllib.parse.urlencode({"ut": md}))[0] == 200, 5))
        kod, d = self.k("POST", "/api/pdf/kiemeles", {"ut": "Xn - Forrás/Más.pdf", "oldal": 4, "szoveg": "Négy",
                                                      "teglalapok": [[0, 0, 1, 1]]})
        self.assertEqual(kod, 200, d)
        szoveg = (self.v / md).read_text(encoding="utf-8")
        self.assertIn('Source:\n  - "[[Más.pdf#page=4]]"\n  - "[[Valami.pdf#page=3]]"\n', szoveg)
        self.assertIn("Saját bevezető.\n\n## 4. oldal\n", szoveg)
        # a kézi előzmény külön commitban (L13–L14)
        self.assertEqual(self.repo.log(2)[1].trailers.get("Mos-Forras"), "kezi")


if __name__ == "__main__":
    unittest.main()
