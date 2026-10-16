"""F9 backup / restore audit §4: recovery from a damaged index, end to end over the core's HTTP API.

The index (`{index}/vault.sqlite`) is a rebuildable cache (L60): a damaged or foreign file is set aside (`serult-<time>.sqlite`,
never deleted) and rebuilt from the vault; the notes and the snapshot history are untouched. Unit-level coverage:
`tests/test_index_c33.py`. Here: the whole core on (1) a non-SQLite file, (2) a real index with garbage over its middle pages,
(3) a missing index; plus the regression of the F9 race (a reader opening the file before its schema existed → 500)."""
from __future__ import annotations

import sqlite3
import time
import unittest
from pathlib import Path

from tests.biztonsag import Szerver, fa
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit


class _SerultAlap(Szerver):
    JEGYZETEK = {f"Notes/N{i:03}.md": f"# N{i}\n\nalpha {i} " + "padding text " * 200 + "\n" for i in range(60)}
    RONT = "nem_sqlite"

    def elokeszit(self):
        ix, _ = index_indit(self.cfg)
        self.db = Path(ix.db_ut)
        ix.leallit()
        if self.RONT == "nem_sqlite":
            self.db.write_bytes(b"this is not an SQLite database" * 300)
        elif self.RONT == "kozepe":
            b = bytearray(self.db.read_bytes())
            self.assertGreater(len(b), 64 * 1024)
            kezd = len(b) // 3
            b[kezd:kezd + 16384] = b"\xde\xad\xbe\xef" * 4096
            self.db.write_bytes(bytes(b))
        elif self.RONT == "hianyzik":
            self.db.unlink()
        for kiseret in ("-wal", "-shm"):
            Path(str(self.db) + kiseret).unlink(missing_ok=True)
        self.vault_elotte = fa(self.v)
        self.head_elotte = self.repo.git("rev-parse", "HEAD").stdout.strip()

    def kereses_mukodik(self, mp: float = 60):
        vege = time.monotonic() + mp
        while True:
            kod, d = self.k("GET", "/api/vault/kereses?q=alpha")
            if kod == 200 and len(d.get("talalatok", [])) >= 10:
                return d
            self.assertLess(time.monotonic(), vege, f"search did not recover: {kod} {d!r}"[:300])
            time.sleep(0.1)

    def kozos(self):
        self.kereses_mukodik()
        kod, d = self.k("GET", "/api/vault/index")
        self.assertEqual(kod, 200, d)
        self.assertEqual(d["jegyzetek"], len(self.JEGYZETEK))
        self.assertEqual(fa(self.v), self.vault_elotte, "the recovery changed the vault")
        self.assertEqual(self.repo.git("rev-parse", "HEAD").stdout.strip(), self.head_elotte)
        return d


class NemSqliteTest(_SerultAlap):
    RONT = "nem_sqlite"

    def test_felretesz_ujraepit_es_jelzi(self):
        d = self.kozos()
        self.assertTrue(str(d.get("felretett") or "").startswith("serult-"), d)
        self.assertTrue((self.db.parent / d["felretett"]).is_file(), "the damaged file is kept, not deleted")


class KozepeSerultTest(_SerultAlap):
    RONT = "kozepe"

    def test_a_kozepen_serult_index_is_helyreall(self):
        self.kozos()
        # the store is a valid, complete SQLite database again
        c = sqlite3.connect(str(self.db))
        try:
            self.assertEqual(c.execute("PRAGMA quick_check").fetchone()[0], "ok")
        finally:
            c.close()


class HianyzoTest(_SerultAlap):
    RONT = "hianyzik"

    def test_a_hianyzo_index_ujraepul(self):
        d = self.kozos()
        self.assertFalse(d.get("felretett"))


class SemaNelkuliOlvasoTest(unittest.TestCase):
    """Regression (F9): the writer creates `vault.sqlite` before its first migration commits; a reader that opened the file in
    that window ran its query on an empty schema (`no such table: fts`) and the core answered 500. It must be `NemKesz` (503)."""

    def test_sema_nelkuli_fajl_nem_kesz(self):
        from core.index.olvaso import NemKesz
        with tmpdir() as t:
            cfg, _, vault = alg_core(t)
            ir(vault, "A.md", "# A\n")
            ix, _ = index_indit(cfg)
            db = Path(ix.db_ut)
            ix.leallit()
            ix._pool_urit()
            for f in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
                f.unlink(missing_ok=True)
            sqlite3.connect(str(db)).close()                     # the file exists, the schema does not (user_version 0)
            with self.assertRaises(NemKesz):
                ix.kereses("a")
            c = sqlite3.connect(str(db))
            c.execute("PRAGMA user_version = 3")                 # a half-migrated (older) schema is not ready either
            c.close()
            with self.assertRaises(NemKesz):
                ix.kereses("a")
