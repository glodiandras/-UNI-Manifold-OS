"""F9 multi-user level (PLAN §8 „Multi-user”): two fake macOS users on one machine share ONE read-only application bundle, each
with their own HOME (so their own `{install}` = `~/Library/Application Support/Manifold`) and their own workspace.

- Both cores run at the same time: the install-level locks and pid files (`run/vaults/*.lock`, `run/cores/<id>.json`) live in each
  user's own install, so they never collide; neither user's install, HOME or workspace receives anything of the other's.
- State keyed by the workspace id (backups `{backup_gyoker}/<id>`, the registry) stays in the owner's install.
- A folder both users can reach (a shared vault): while user A's core holds it, user B's core refuses with 75 (the vault-level
  `core.lock` in `.manifold/var/run`), and B's registry is not touched. After A quits, B can open it: B's state for that id goes
  into B's install; A's install is byte-identical throughout B's session.
- The other user's API secret is 403 on each core.

Only fake HOMEs in temp dirs; no real user account is involved."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import unittest
import urllib.parse
from pathlib import Path

from core import config, server, workspace
from tests.biztonsag import fa
from tests.helpers import REPO, alg_bundle, tmpdir
from tests.multi_user import elso_sor, install, termek_env

TITOK = {"a": "user-a-secret-0123456789abcdef", "b": "user-b-secret-0123456789abcdef"}


def _leallit(p):
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


class KetFelhasznaloTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(os.path.realpath(self._t.name))
        self.root = alg_bundle(str(self.t))                       # ONE application, shared by both users
        self.home = {u: self.t / f"home-{u}" for u in "ab"}
        self.vault, self.id = {}, {}
        for u in "ab":
            self.home[u].mkdir()
            alap = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home[u]), "MOS_SETTINGS": ""}, munkater=False)
            v = self.home[u] / "Documents" / "Notes"
            v.mkdir(parents=True)
            (v / f"{u}.md").write_text(f"# note of user {u}\n\nsecret-of-{u}\n", encoding="utf-8")
            r = workspace.letrehoz(v, alap, nev=f"Notes {u}", nyelv="")
            self.vault[u], self.id[u] = v, r["id"]
        self.assertNotEqual(self.id["a"], self.id["b"])

    def core(self, u: str, vault: Path | None = None, *, titok: str | None = None):
        p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=termek_env(self.root, self.home[u], vault or self.vault[u], MOS_API_TITOK=titok or TITOK[u]))
        self.addCleanup(_leallit, p)
        return p

    def kezfogas(self, p) -> dict:
        sor = elso_sor(p)
        self.assertTrue(sor, "the core did not answer")
        return json.loads(sor)

    @staticmethod
    def k(port, ut, titok):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        try:
            c.request("GET", ut, headers={"Host": f"127.0.0.1:{port}", "X-Manifold": titok})
            r = c.getresponse()
            return r.status, r.read()
        finally:
            c.close()

    def idegen_nyom(self, u: str, masik: str, kiveve: str | None = None) -> list[str]:
        """Paths/contents in user `u`'s HOME that carry the other user's workspace id or home (`kiveve`: a shared folder)."""
        nyom = []
        for rp, b in fa(self.home[u]).items():
            if kiveve and rp.startswith(kiveve):
                continue
            szoveg = rp + (b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b or ""))
            if self.id[masik] in szoveg or str(self.home[masik]) in szoveg or f"secret-of-{masik}" in szoveg:
                nyom.append(rp)
        return nyom

    def test_egyszerre_futnak_kulon_zarakkal_es_allapottal(self):
        pa, pb = self.core("a"), self.core("b")
        ka, kb = self.kezfogas(pa), self.kezfogas(pb)
        self.assertEqual((ka["munkater_id"], kb["munkater_id"]), (self.id["a"], self.id["b"]))
        for u, p in (("a", pa), ("b", pb)):
            run = install(self.home[u]) / "run"
            self.assertEqual([f.name for f in (run / "cores").glob("*.json")], [f"{self.id[u]}.json"])
            orok = list((run / "vaults").glob("*.lock"))
            self.assertEqual(len(orok), 1)
            self.assertEqual(server.zar_foglalt(orok[0])["pid"], p.pid)
            self.assertEqual(server.zar_foglalt(self.vault[u] / ".manifold" / "var" / "run" / "core.lock")["pid"], p.pid)
        # the other user's secret opens nothing; the other user's vault path is refused
        self.assertEqual(self.k(ka["port"], "/api/allapot", TITOK["b"])[0], 403)
        self.assertEqual(self.k(kb["port"], "/api/allapot", TITOK["a"])[0], 403)
        kod, b = self.k(ka["port"], "/api/vault/fajl?ut=" + urllib.parse.quote(str(self.vault["b"] / "b.md")), TITOK["a"])
        self.assertIn(kod, (400, 403, 404))
        self.assertNotIn(b"secret-of-b", b)
        _leallit(pa)
        _leallit(pb)
        self.assertEqual((pa.returncode, pb.returncode), (0, 0))
        for u, masik in (("a", "b"), ("b", "a")):
            self.assertEqual(self.idegen_nyom(u, masik), [], f"user {u}'s HOME carries user {masik}'s state")
            mentesek = install(self.home[u]) / "backups"
            self.assertEqual({d.name for d in mentesek.iterdir()}, {self.id[u]}, "backups keyed by the owner's workspace id")
        self.assertFalse((self.root / "var").exists(), "nothing is written into the shared application bundle")

    def test_kozos_mappa_a_masik_felhasznalo_amig_fut_foglalt_utana_sajat_allapottal_nyithato(self):
        pa = self.core("a")
        ka = self.kezfogas(pa)
        self.assertEqual(ka["munkater_id"], self.id["a"])
        reg_b = install(self.home["b"]) / "workspaces.json"
        reg_b_elotte = reg_b.read_bytes()
        p = subprocess.run([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, input=b"", capture_output=True, timeout=120,
                           env=termek_env(self.root, self.home["b"], self.vault["a"], MOS_API_TITOK=TITOK["b"]))
        self.assertEqual(p.returncode, server.CORE_ZAR_KILEPES, p.stderr.decode(errors="replace")[-500:])
        self.assertEqual(json.loads(p.stdout.splitlines()[0])["pid"], pa.pid)
        self.assertEqual(reg_b.read_bytes(), reg_b_elotte, "a refused start registered the workspace for user B")
        _leallit(pa)

        a_install_elotte = fa(install(self.home["a"]))
        pb = self.core("b", self.vault["a"])
        kb = self.kezfogas(pb)
        self.assertEqual(kb["munkater_id"], self.id["a"], "the shared folder keeps its id")
        self.assertIn(self.id["a"], json.loads(reg_b.read_text(encoding="utf-8"))["munkaterek"])
        self.assertEqual(self.k(kb["port"], "/api/vault/fajl?ut=a.md", TITOK["b"])[0], 200)
        _leallit(pb)
        self.assertEqual(pb.returncode, 0)
        self.assertEqual(fa(install(self.home["a"])), a_install_elotte, "user B's session changed user A's install")
        self.assertTrue((install(self.home["b"]) / "backups" / self.id["a"]).is_dir(), "B's state for the id is in B's install")
        # the shared workspace itself records B's session in its own log (`.manifold/var/runs/core.log`); A's install does not
        self.assertEqual(self.idegen_nyom("a", "b", kiveve="Documents/Notes/"), [])
