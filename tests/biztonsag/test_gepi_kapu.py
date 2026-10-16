"""F9 security audit §4: can a machine step get around the machine-write gate (28(a), `core/lepes_kapu.py`)?

A step process holds a one-time step token (not the UI secret): it may call readers (GET/HEAD) and the `ENGEDELYEZETT` pure
calculators; every other writer is 403 (`tests/test_lepes_kapu.py` holds the decision table). The gate is only as strong as two
assumptions this test checks over real HTTP:

1. **No reader writes.** Every registered GET route (the fixed ones, with plausible query parameters) is called with a step
   token; afterwards the vault bytes, the snapshot history (HEAD) and the folder outside the vault are unchanged.
2. **The allowed calculators do not write**, even when called with write-like arguments, and the writers stay 403 under every
   spelling of their path (percent-encoding, trailing slash, double slash, method-override headers, HEAD/GET on a writer).
"""
from __future__ import annotations

import urllib.parse
from unittest import mock

from core import lepes_kapu, server, tasks
from tests.biztonsag import Szerver, fa

TOKEN = "f9-step-token-0123456789abcdef0123456789"


class GepiKapuTest(Szerver):

    def setUp(self):
        p = mock.patch.object(tasks.Queue, "lepes_feladat", lambda self, t: "F-20261016-000000-1" if t == TOKEN else None)
        p.start()
        self.addCleanup(p.stop)
        super().setUp()
        self.lepes = {"X-Manifold": TOKEN}

    def allapot(self):
        return fa(self.v), self.repo.git("rev-parse", "HEAD").stdout.strip()

    def test_a_lepes_token_ervenyes_es_nem_teljes_jogu(self):
        self.assertEqual(self.k("GET", "/api/vault/fajl?ut=Notes/A.md", fejlec=self.lepes)[0], 200)
        kod, d = self.k("PUT", "/api/vault/fajl", {"ut": "Notes/A.md", "tartalom": "x", "alap": "0" * 40}, fejlec=self.lepes)
        self.assertEqual((kod, d.get("kod")), (403, "http.lepes_tiltott"), d)

    def test_egyetlen_olvaso_sem_ir(self):
        elotte = self.allapot()
        q = urllib.parse.urlencode({"ut": "Notes/A.md", "q": "alpha", "n": "5", "kulcs": "tags", "id": "x", "sha": "0" * 40,
                                    "forras": "Notes/A.md", "cel": "A", "nap": "2026-10-16", "datum": "2026-10-16"})
        hivott = 0
        for m, u, _ in server.regiszter_epit().vegpontok():
            if m != "GET" or not isinstance(u, str) or u in ("/ws",) or any(c in u for c in "(*\\[{"):
                continue                                    # the WebSocket and the pattern routes (media has its own token)
            for ut in (u, f"{u}?{q}"):
                kod, d = self.k("GET", ut, fejlec=self.lepes)
                self.assertNotEqual(kod, 403, f"a reader refused the step token: {ut} {d!r}"[:300])
                hivott += 1
        self.assertGreater(hivott, 60)
        self.assertEqual(self.allapot(), elotte, "a GET route changed the vault or its snapshot history")
        self.kint_erintetlen()

    def test_a_tiszta_szamolok_nem_irnak(self):
        elotte = self.allapot()
        torzsek = {
            "/api/vault/tulajdonsagok/modosit": {"ut": "Notes/A.md", "fm": "title: x\n", "muvelet": "beallit", "kulcs": "status",
                                                 "ertek": "done", "megerosit": True, "forras": "felhasznalo"},
            "/api/vault/tulajdonsagok/elemez": {"ut": "Notes/A.md", "fm": "a: 1\n"},
            "/api/vault/tulajdonsagok/osszefesul": {"ut": "Notes/A.md", "fm": "a: 1\n", "sablon_fm": "b: 2\n"},
            "/api/vault/bazis/lekerdez": {"szoveg": "views:\n  - type: table\n    name: T\n", "ut": "Notes/x.base"},
            "/api/vault/bazis/modosit": {"szoveg": "", "muvelet": {"fajta": "nezet_uj"}, "ut": "Notes/x.base"},
            "/api/vault/atnevezes/terv": {"ut": "Notes/A.md", "uj": "Notes/Z.md"},
            "/api/vault/feloldas": {"forras": "Notes/B.md", "celok": ["A"]},
            "/api/sablon/kiertekel": {"sablon": "Notes/A.md", "ut": "Notes/A.md", "szoveg": "{{date}}"},
        }
        self.assertEqual({u for m, u in lepes_kapu.ENGEDELYEZETT if u != "/api/gepi-iras"}, set(torzsek),
                         "a new allowed calculator: add a write-like probe for it here")
        for u, t in torzsek.items():
            kod, d = self.k("POST", u, t, fejlec=self.lepes)
            self.assertNotEqual(kod, 403, (u, d))
        self.assertEqual(self.allapot(), elotte, "an allowed calculator wrote")

    def test_az_irok_minden_irasmoddal_tiltottak(self):
        elotte = self.allapot()
        irok = [(m, u) for m, u, _ in server.regiszter_epit().vegpontok()
                if m not in ("GET", "HEAD") and isinstance(u, str) and not any(c in u for c in "(*\\[{")
                and not lepes_kapu.engedelyezett(m, u)]
        self.assertGreater(len(irok), 30)
        for m, u in irok:
            for valtozat in (u, u + "/", u.replace("/api/", "/api//", 1), "/api/" + urllib.parse.quote(u[5:], safe="/").replace(
                    "a", "%61", 1), u + "?ut=Notes/A.md"):
                kod, d = self.k(m, valtozat, {"ut": "Notes/A.md", "tartalom": "x", "alap": "0" * 40}, fejlec=self.lepes)
                self.assertIn(kod, (403, 404, 405), f"{m} {valtozat}: {kod} {d!r}"[:300])
            for felul in ("X-HTTP-Method-Override", "X-Method-Override", "X-HTTP-Method"):
                kod, _ = self.k("POST", "/api/gepi-iras", {"ut": "Notes/A.md"}, fejlec={**self.lepes, felul: "PUT"})
                self.assertNotEqual(kod, 200)
        for m, u in (("GET", "/api/pillanat/vault/visszavonas"), ("HEAD", "/api/vault/atnevezes"), ("GET", "/api/vault/uj")):
            kod, _ = self.k(m, u, fejlec=self.lepes)
            self.assertIn(kod, (403, 404, 405), (m, u, kod))
        self.assertEqual(self.allapot(), elotte, "a writer ran under a step token")
        self.kint_erintetlen()
