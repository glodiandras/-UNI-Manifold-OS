"""F9 Definition of Done (PLAN §12) on a fresh install, in PRODUCT mode (Developer mode off), with no model installed.

One run on a read-only, product-shaped application, a fake HOME and a new, empty folder: create the workspace (3), write a note
(6), find it (7), the AI side without a model answers with product messages, not crashes (8), cards and quizzes work without a
model (9), a PDF's text becomes searchable (10), a math derivation is checked in the sandbox (11), and the developer-only routes
stay closed (15). Points 1, 2, 4, 12–14 are covered by the other tests of the `dod` level (`tests/szintek.py:DOD`); what stays
manual is listed there and in the F9 report."""
from __future__ import annotations

import base64
import http.client
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.parse
from pathlib import Path

from core import config, workspace
from tests.fresh_install.test_alap import _csak_olvashato, _irhato
from tests.helpers import REPO, alg_bundle, tmpdir
from tests.multi_user import elso_sor, termek_env

TITOK = "f9-dod-secret-0123456789abcdef0123"
MACOS_HOMOKOZO = sys.platform == "darwin" and os.access("/usr/bin/sandbox-exec", os.X_OK)


def _pdf(szoveg: str) -> bytes | None:
    try:
        import pymupdf
    except ImportError:
        return None
    d = pymupdf.open()
    lap = d.new_page()
    lap.insert_text((72, 72), szoveg)
    b = d.tobytes()
    d.close()
    return b


class DodTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.root = alg_bundle(str(self.t))
        self.home = self.t / "home"
        alap = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_SETTINGS": ""}, munkater=False)
        self.vault = self.t / "My notes"
        r = workspace.letrehoz(self.vault, alap, nev="My notes", nyelv="", uj_mappa=True)       # DoD 3
        self.id = r["id"]
        _csak_olvashato(self.root)
        self.addCleanup(_irhato, self.root)
        self.p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env=termek_env(self.root, self.home, self.vault, MOS_API_TITOK=TITOK, MOS_FEJLESZTO="0",
                                                 MOS_MODULOK=str(REPO / "modulok")))   # the fake bundle carries config only
        self.addCleanup(self._leallit)
        sor = elso_sor(self.p)
        self.assertTrue(sor, "the core did not start")
        k = json.loads(sor)
        self.assertEqual((k["elrendezes"], k["munkater_id"]), ("termek", self.id))
        self.port = k["port"]

    def _leallit(self):
        p = self.p
        if p.poll() is None:
            p.stdin.close()
            try:
                p.wait(60)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for f in (p.stdin, p.stdout):
            if f and not f.closed:
                f.close()

    def k(self, metodus, ut, torzs=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        try:
            c.request(metodus, ut, body=None if torzs is None else json.dumps(torzs),
                      headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": TITOK, "Content-Type": "application/json"})
            r = c.getresponse()
            b = r.read()
            try:
                return r.status, json.loads(b or b"null")
            except ValueError:
                return r.status, b
        finally:
            c.close()

    def var(self, fn, mp=60, uzenet=""):
        vege = time.monotonic() + mp
        while True:
            ertek = fn()
            if ertek:
                return ertek
            self.assertLess(time.monotonic(), vege, uzenet)
            time.sleep(0.1)

    def termek_hiba(self, kod, d, cimke):
        """A refusal a user can read: 4xx/503, a `kod`, an English sentence — never a 500 or a traceback."""
        self.assertNotEqual(kod, 500, (cimke, d))
        self.assertTrue(400 <= kod < 600, (cimke, kod, d))
        self.assertIsInstance(d, dict, (cimke, d))
        self.assertTrue(d.get("kod"), (cimke, d))
        self.assertNotIn("Traceback", json.dumps(d))

    def test_dod_pontok_modell_nelkul_termek_modban(self):
        # 6 · write a note (with a formula and a link)
        kod, uj = self.k("POST", "/api/vault/uj", {"nev": "First note", "mappa": "Notes", "mappa_keszit": True})
        self.assertEqual(kod, 201, uj)
        kod, d = self.k("GET", "/api/vault/fajl?ut=" + urllib.parse.quote(uj["ut"]))
        szoveg = "# First note\n\nDodsearchtoken links to [[Second]].\n\n$$x^2 + 1$$\n"
        kod, m = self.k("PUT", "/api/vault/fajl", {"ut": uj["ut"], "tartalom": szoveg, "alap": d["hash"], "elso": True, "pillanat": True})
        self.assertEqual((kod, m.get("git")), (200, True), m)
        # 7 · search
        self.var(lambda: any(x["ut"] == uj["ut"] for x in self.k("GET", "/api/vault/kereses?q=dodsearchtoken")[1].get("talalatok", [])),
                 uzenet="the new note is not found")
        # 10 · PDF: imported, served to the reader, highlighted into its companion note (the text index of PDFs waits for an
        # idle machine, D8 — `tests/test_kereses_media.py` covers it)
        pdf = _pdf("Pdfdodtoken appears on the first page")
        if pdf is not None:
            kod, r = self.k("POST", "/api/vault/import", {"nev": "Paper.pdf", "mappa": "Notes",
                                                           "adat": base64.b64encode(pdf).decode(), "vege": True})
            self.assertLess(kod, 300, r)
            pdf_ut = r.get("ut") or "Notes/Paper.pdf"
            token = self.k("GET", "/api/allapot")[1]["media_token"]
            kod, b = self.k("GET", f"/media/{token}/" + urllib.parse.quote(pdf_ut))
            self.assertEqual(kod, 200)
            self.assertTrue(isinstance(b, bytes) and b.startswith(b"%PDF"))
            kod, h = self.k("POST", "/api/pdf/kiemeles", {"ut": pdf_ut, "oldal": 1, "szoveg": "Pdfdodtoken appears",
                                                          "teglalapok": [[0.1, 0.1, 0.5, 0.05]]})
            self.assertEqual(kod, 200, h)
            self.assertIn("Pdfdodtoken appears", (self.vault / h["fajl"]).read_text(encoding="utf-8"))
        # 9 · cards and quizzes without a model
        for ut in ("/api/kartya/allapot", "/api/kartya/esedekes"):
            kod, d = self.k("GET", ut)
            self.assertEqual(kod, 200, (ut, d))
        kod, d = self.k("GET", "/api/kviz/kviz?ut=" + urllib.parse.quote(uj["ut"]))
        self.assertNotEqual(kod, 500, d)
        # 11 · a math derivation, checked in the sandbox (no model)
        kod, d = self.k("POST", "/api/matek/levezetes", {"sorok": [{"sor": 1, "szoveg": "2x + 3 = 7"},
                                                                   {"sor": 2, "szoveg": "2x = 4"}, {"sor": 3, "szoveg": "x = 2"}]})
        if MACOS_HOMOKOZO:
            self.assertEqual(kod, 200, d)
            self.assertNotIn(d.get("allapot"), ("hiba", None), d)
        else:
            self.termek_hiba(kod, d, "math without a sandbox")
        # 8 · AI without a model: the model list works, the features answer with product messages
        kod, d = self.k("GET", "/api/modellek")
        self.assertEqual(kod, 200, d)
        for metodus, ut, torzs in (("POST", "/api/kereses/kerdezz", {"kerdes": "What is in my notes?"}),
                                   ("POST", "/api/osszefoglalas/jegyzet", {"ut": uj["ut"]}),
                                   ("POST", "/api/kod/ai", {"ut": uj["ut"], "mod": "magyaraz"})):
            kod, d = self.k(metodus, ut, torzs)
            if kod >= 400:
                self.termek_hiba(kod, d, ut)
        # 15 · product mode: the developer-only routes stay closed
        kod, d = self.k("POST", "/api/import/v2/elonezet", {"forras": str(self.t)})
        self.assertEqual((kod, d.get("kod")), (403, "import.fejleszto_mod"), d)
        kod, b = self.k("GET", "/api/beallitasok")
        self.assertEqual(kod, 200, b)
        self.assertFalse(b["ertek"].get("fejleszto", {}).get("be", False) if isinstance(b["ertek"].get("fejleszto"), dict) else False)
