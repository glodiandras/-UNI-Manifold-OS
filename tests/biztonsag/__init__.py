"""F9 security audit (docs/plan/audit/07-f9-biztonsag.md): regression tests for every probe of the audit.

Shared frame: an in-process core (server thread, stdin pipe) on a synthetic vault (`alg_core`) with a LIVE snapshot repository,
plus a folder OUTSIDE the vault that holds a "secret" — every probe asserts that the secret is neither returned nor changed and
that nothing appears outside the vault. The real vault, the v2 checkout and the network are never touched."""
from __future__ import annotations

import http.client
import json
import os
import threading
import unittest
from pathlib import Path

from tests.helpers import API_TITOK, alg_core, ir, tmpdir

TITOK_SZOVEG = "OUTSIDE-SECRET-7d1e"


class _Kimenet:
    def __init__(self):
        self.sorok, self.jel = [], threading.Event()

    def write(self, s):
        self.sorok.append(s)
        self.jel.set()

    def flush(self):
        pass


def fa(gyoker: Path) -> dict[str, bytes | str | None]:
    """Every entry under `gyoker` (links not followed): {relative path: bytes | 'link:<target>' | None for folders}."""
    ki: dict[str, bytes | str | None] = {}
    for d, mappak, fajlok in os.walk(gyoker, followlinks=False):
        for m in mappak:
            p = os.path.join(d, m)
            ki[os.path.relpath(p, gyoker) + "/"] = ("link:" + os.readlink(p)) if os.path.islink(p) else None
        for f in fajlok:
            p = os.path.join(d, f)
            ki[os.path.relpath(p, gyoker)] = ("link:" + os.readlink(p)) if os.path.islink(p) else Path(p).read_bytes()
    return ki


class Szerver(unittest.TestCase):
    """The core on a thread over a synthetic vault with a live `vault.git`; `self.kint` is a folder outside the vault."""

    JEGYZETEK = {"Notes/A.md": "# A\n\nalpha body\n", "Notes/B.md": "# B\n\n[[A]]\n"}

    def elokeszit(self):
        """Runs before the core starts (subclasses add links, files…)."""

    def setUp(self):
        from core import server, snapshot, tasks
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.cfg, self.root, self.v = alg_core(str(self.t))
        self.kint = self.t / "kint"
        self.kint.mkdir()
        (self.kint / "titok.md").write_text(f"# secret\n{TITOK_SZOVEG}\n", encoding="utf-8")
        for rp, s in self.JEGYZETEK.items():
            ir(self.v, rp, s)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("baseline", {"Mos-Forras": "kezi"})
        self.elokeszit()
        self.kint_elotte = fa(self.kint)
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(10))
        self.kezfogas = json.loads(ki.sorok[0])
        self.port = self.kezfogas["port"]
        self.addCleanup(self._leall)
        self.index_kesz()

    def index_kesz(self, mp: float = 60):
        """Waits until the first index build is done (the rename plan and the search answer 503 before)."""
        import time
        vege = time.monotonic() + mp
        while True:
            kod, d = self.k("GET", "/api/vault/index")
            if kod == 200 and d.get("kesz"):
                return
            self.assertLess(time.monotonic(), vege, f"the index did not finish: {d}")
            time.sleep(0.05)

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(30)
        self.stdin_r.close()

    def k(self, metodus: str, ut: str, torzs=None, fejlec: dict | None = None, nyers: bytes | None = None):
        """→ (status, parsed JSON or raw bytes). `ut` is sent as is (no client-side normalisation)."""
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json", **(fejlec or {})}
        try:
            c.putrequest(metodus, ut, skip_host=True, skip_accept_encoding=True)
            test = nyers if nyers is not None else (json.dumps(torzs).encode() if torzs is not None else None)
            for kulcs, ertek in h.items():
                c.putheader(kulcs, ertek)
            if test is not None:
                c.putheader("Content-Length", str(len(test)))
            c.endheaders(test)
            r = c.getresponse()
            b = r.read()
        finally:
            c.close()
        if b and (r.getheader("Content-Type") or "").startswith("application/json"):
            return r.status, json.loads(b)
        return r.status, b

    def kint_erintetlen(self, uzenet=""):
        self.assertEqual(fa(self.kint), self.kint_elotte, f"something outside the vault changed {uzenet}")

    def nem_szivarog(self, valasz, uzenet=""):
        szoveg = valasz if isinstance(valasz, (bytes, bytearray)) else json.dumps(valasz, ensure_ascii=False).encode()
        self.assertNotIn(TITOK_SZOVEG.encode(), szoveg, f"the outside secret leaked {uzenet}")
