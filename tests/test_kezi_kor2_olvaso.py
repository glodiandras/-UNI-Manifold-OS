"""A Kézi kör 2 csak olvasó ellenőrzései (`tests/kezi/kor2_olvaso.py`): álkönyvtárban, pozitív és negatív eset; és hogy
a forrásmappákhoz egyik ellenőrzés sem ír (a bájtok és az mtime-ok azonosak)."""
import contextlib
import io
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import REPO, tmpdir

sys.path.insert(0, str(REPO / "tests" / "kezi"))
import kor2_olvaso as K  # noqa: E402

GITENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", GIT_CONFIG_NOSYSTEM="1",
              GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def csendben(f, *a, **kw):
    ki = io.StringIO()
    with contextlib.redirect_stdout(ki):
        r = f(*a, **kw)
    return r, ki.getvalue()


def pillanat(gyoker: Path) -> dict:
    return {str(p): (p.stat().st_mtime_ns, p.stat().st_size, p.read_bytes() if p.is_file() else b"")
            for p in sorted(gyoker.rglob("*"))}


def git(*args, cwd, env=None):
    subprocess.run(["git", *args], cwd=cwd, env=env or GITENV, check=True, capture_output=True)


def pos_db(ut: Path, verzio: int, parancs: int, rekord: int = 0):
    ut.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(ut)
    c.execute("CREATE TABLE has_parancs (id INTEGER)")
    c.execute("CREATE TABLE forras_rekord (id INTEGER, nev TEXT)")
    c.executemany("INSERT INTO has_parancs VALUES (?)", [(i,) for i in range(parancs)])
    c.executemany("INSERT INTO forras_rekord VALUES (?, ?)", [(i, "x") for i in range(rekord)])
    c.execute(f"PRAGMA user_version = {verzio}")
    c.commit()
    c.close()


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)

    def nem_ir(self, gyoker: Path, f, *a, **kw):
        elotte = pillanat(gyoker)
        r, ki = csendben(f, *a, **kw)
        self.assertEqual(pillanat(gyoker), elotte, "az ellenőrzés írt a forrásmappába")
        return r, ki


class K06(Alap):
    def test_nincs_sor_rendben_van_sor_elteres_hianyzo_jegyzet_elteres(self):
        v = self.d / "v"
        (v / "AI01").mkdir(parents=True)
        (v / ".obsidian").mkdir()
        (v / ".obsidian" / K.KALAUZ_JEGYZET).write_text("KILEPES_PROBA 9", encoding="utf-8")   # kihagyott mappa
        self.assertFalse(self.nem_ir(v, K.k06, v)[0])                      # még nincs jegyzet
        j = v / "AI01" / K.KALAUZ_JEGYZET
        j.write_text("tiszta\n", encoding="utf-8")
        self.assertTrue(self.nem_ir(v, K.k06, v)[0])
        j.write_text("tiszta\nKILEPES_PROBA 123\n", encoding="utf-8")
        r, ki = self.nem_ir(v, K.k06, v)
        self.assertFalse(r)
        self.assertIn("1 KILEPES_PROBA", ki)


class K41(Alap):
    def test_blobok_es_a_regi_index(self):
        hub = self.d / "hub"
        (hub / "models--a--b" / "blobs").mkdir(parents=True)
        regi = self.d / "manifold.sqlite"
        self.assertTrue(self.nem_ir(self.d, K.k41, hub, regi)[0])
        (hub / "models--a--b" / "blobs" / "abc.incomplete").write_bytes(b"x" * 10)
        r, ki = self.nem_ir(self.d, K.k41, hub, regi)
        self.assertFalse(r)
        self.assertIn("models--a--b: 1 blob", ki)
        (hub / "models--a--b" / "blobs" / "abc.incomplete").unlink()
        regi.write_bytes(b"x")
        self.assertFalse(self.nem_ir(self.d, K.k41, hub, regi)[0])


class K55(Alap):
    def test_futtathato_indito_vagy_venv_elteres(self):
        leg = self.d / "Legacy"
        (leg / "bin").mkdir(parents=True)
        mos, pult = leg / "bin" / "mos", leg / "Manifold-pult.command"
        for p in (mos, pult):
            p.write_text("#!/bin/sh\n")
            p.chmod(0o755)
        self.assertFalse(self.nem_ir(leg, K.k55, leg)[0])
        for p in (mos, pult):
            p.chmod(0o644)
        self.assertTrue(self.nem_ir(leg, K.k55, leg)[0])
        (leg / "var" / "venv").mkdir(parents=True)
        self.assertFalse(self.nem_ir(leg, K.k55, leg)[0])


class K56(Alap):
    def _tar(self, napok: list[str]) -> Path:
        mu = self.d / "mu"
        mu.mkdir()
        git("init", "-q", cwd=mu)
        for i, nap in enumerate(napok):
            (mu / "f.txt").write_text(str(i))
            git("add", "f.txt", cwd=mu)
            env = dict(GITENV, GIT_COMMITTER_DATE=f"{nap} 12:00:00 +0000", GIT_AUTHOR_DATE=f"{nap} 12:00:00 +0000")
            git("commit", "-q", "-m", "x\n\nMos-Forras: pult-szerkeszto", cwd=mu, env=env)
        return mu / ".git"

    def test_napi_commit_es_a_pos_db(self):
        het = [f"2026-10-0{n}" for n in range(1, 5)] + ["2026-09-30", "2026-09-29", "2026-09-28"]
        pos = self.d / "pos.sqlite"
        pos_db(pos, 2, 3)
        tar = self._tar(het)
        r, ki = self.nem_ir(self.d, K.k56, tar, pos, 7, "2026-10-04")
        self.assertTrue(r, ki)
        # hiányzó nap → eltérés
        self.assertFalse(csendben(K.k56, tar, pos, 8, "2026-10-04")[0])

    def test_regi_sema_vagy_ures_has_parancs_elteres(self):
        tar = self._tar(["2026-10-04"])
        pos = self.d / "pos.sqlite"
        pos_db(pos, 1, 3)
        self.assertFalse(csendben(K.k56, tar, pos, 1, "2026-10-04")[0])
        pos_db(self.d / "pos2.sqlite", 2, 0)
        self.assertFalse(csendben(K.k56, tar, self.d / "pos2.sqlite", 1, "2026-10-04")[0])


class K57(Alap):
    def test_elotte_utana(self):
        backup, vg, pos, fel = self.d / "b", self.d / "vg", self.d / "pos.sqlite", self.d / "fel.sqlite"
        backup.mkdir()
        (backup / "vault-1.bundle").write_bytes(b"1")
        vg.mkdir()
        (vg / "index").write_bytes(b"i")
        pos.write_bytes(b"p")
        fel.write_bytes(b"f")
        al = self.d / "ki" / "allapot.json"
        self.assertFalse(csendben(K.k57, "utana", al, backup, pos, vg, fel)[0])      # nincs előtte
        self.assertTrue(csendben(K.k57, "elotte", al, backup, pos, vg, fel)[0])
        self.assertTrue(csendben(K.k57, "utana", al, backup, pos, vg, fel)[0])
        (backup / "vault-2.bundle").write_bytes(b"2")                                  # új fájl a mentésben
        r, ki = csendben(K.k57, "utana", al, backup, pos, vg, fel)
        self.assertFalse(r)
        self.assertIn("vault-2.bundle", ki)
        (backup / "vault-2.bundle").unlink()
        os.utime(pos, ns=(1, 1))
        self.assertFalse(csendben(K.k57, "utana", al, backup, pos, vg, fel)[0])


class K63(Alap):
    def test_mentes_tartalma(self):
        mu = self.d / "mu"
        mu.mkdir()
        git("init", "-q", cwd=mu)
        (mu / "f").write_text("1")
        git("add", "f", cwd=mu)
        git("commit", "-q", "-m", "x", cwd=mu)
        backup, state = self.d / "bk", self.d / "state"
        backup.mkdir()
        state.mkdir()
        self.assertFalse(csendben(K.k63, backup, state, mu / ".git")[0])               # üres mentés
        for nev in ("vault-20261004-1.bundle", "mos-kodtar-20261004-1.bundle"):
            git("bundle", "create", str(backup / nev), "HEAD", cwd=mu)
        u = backup / "mos-allapot-20261004-1"
        (u / "szemelyes").mkdir(parents=True)
        (u / "state").mkdir()
        for r in ("router.sqlite", "feladatok.sqlite", "szemelyes/pos.sqlite", "state/a.json"):
            (u / r).write_bytes(b"x")
        r, ki = self.nem_ir(self.d, K.k63, backup, state, mu / ".git")
        self.assertTrue(r, ki)
        (state / "mentes-hiba.json").write_text("{}")
        self.assertFalse(csendben(K.k63, backup, state, mu / ".git")[0])
        (state / "mentes-hiba.json").unlink()
        (backup / "vault-20261004-1.bundle").write_bytes(b"torott")                    # a verify megbukik
        self.assertFalse(csendben(K.k63, backup, state, mu / ".git")[0])


class K71(Alap):
    def test_nevek_a_pos_fajlokban(self):
        pos = self.d / "pos.sqlite"
        pos_db(pos, 2, 1, rekord=5)
        r, ki = self.nem_ir(self.d, K.k71, pos, ["Titkos jegyzet"])
        self.assertTrue(r, ki)
        self.assertIn("forras_rekord: 5 sor", ki)
        (self.d / "pos.sqlite-wal").write_bytes("xx Titkos jegyzet xx".encode("utf-8"))
        r, ki = self.nem_ir(self.d, K.k71, pos, ["Titkos jegyzet"])
        self.assertFalse(r)
        self.assertIn("pos.sqlite-wal", ki)


if __name__ == "__main__":
    unittest.main()
