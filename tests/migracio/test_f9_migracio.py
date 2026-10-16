"""F9 migration level (PLAN §8 „Migráció”): what an older Manifold leaves behind must open in this one.

1. **Index schema v1–v5 → v6** (`core/index/tar.migral`): a real index is rebuilt in the exact table shape of each older version
   (v1–v3 without the PDF/subtitle tables, v1–v5 without `fajl.ctime_ns`), reopened by the current writer: it migrates in place,
   keeps the file rows, re-parses what the step requires, and search, links and birth times work; the notes are not touched.
2. **Old settings and workspace files**: a minimal F3-era `workspace.toml` (only the id), one with unknown or legacy sections, an
   older registry (`workspaces.json` without `formatum`, unknown fields), an install `settings.toml` with retired keys — all
   load (the unknown keys are refused and listed, never fatal); a newer format still refuses (`workspace_ujabb`).
3. **Obsidian import → usable workspace**: after the import the core starts on it, finds an imported note by search, resolves its
   links, saves an edit with a snapshot, and undoes it — the source vault stays byte-identical.
Synthetic vaults in temp dirs only."""
from __future__ import annotations

import http.client
import json
import sqlite3
import subprocess
import sys
import time
import tomllib
import unittest
import urllib.parse
import uuid
from pathlib import Path

from core import config, termek_beallitasok, workspace
from core.index import tar
from tests.fresh_install import lenyomat, termek_alap, termek_cfg
from tests.helpers import REPO, alg_core, ir, tmpdir
from tests.index_segedek import index_indit
from tests.migracio import obsidian_vault, ujjlenyomat
from tests.multi_user import elso_sor, termek_env

JEGYZETEK = {
    "Dir/Source.md": "# Source\n\nmigrationtoken [[./Target]] [[Other/Note]] #tagged\n",
    "Dir/Target.md": "---\ntags: [x]\n---\n# Target\n",
    "Other/Note.md": "# Other\n\n- [ ] a task 📅 2026-10-20\n",
    "Board.canvas": json.dumps({"nodes": [{"id": "a", "type": "file", "file": "Dir/Target.md", "x": 0, "y": 0,
                                           "width": 10, "height": 10}], "edges": []}),
}


def _regi_alak(db: Path, verzio: int) -> None:
    """The table shape an index of `verzio` had (current rows kept), and its `user_version`."""
    c = sqlite3.connect(str(db), isolation_level=None)
    try:
        if verzio < 6:
            c.execute("ALTER TABLE fajl DROP COLUMN ctime_ns")
        if verzio < 4:
            for t in ("media_szoveg", "szakasz", "fts_szakasz"):
                c.execute(f"DROP TABLE IF EXISTS {t}")
        c.execute(f"PRAGMA user_version = {verzio}")
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        c.close()


class IndexSemaMigracioTest(unittest.TestCase):
    def test_v1_tol_v5_ig_minden_regi_index_v6_ra_all(self):
        for verzio in range(1, 6):
            with self.subTest(verzio=verzio), tmpdir() as t:
                cfg, _, vault = alg_core(t)
                for ut, s in JEGYZETEK.items():
                    ir(vault, ut, s)
                elotte = lenyomat(vault, kihagy=())
                ix, _ = index_indit(cfg)
                db = Path(ix.db_ut)
                c = tar.nyit(db)
                sorok_elotte = {r[0] for r in c.execute("SELECT ut FROM fajl")}
                c.close()
                ix.leallit()
                _regi_alak(db, verzio)
                c = sqlite3.connect(str(db))
                self.assertNotIn("ctime_ns", [r[1] for r in c.execute("PRAGMA table_info(fajl)")])
                c.close()

                ix, _ = index_indit(cfg)
                try:
                    c = tar.nyit(db)
                    self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], tar.VERZIO)
                    self.assertIn("ctime_ns", [r[1] for r in c.execute("PRAGMA table_info(fajl)")])
                    self.assertTrue(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'fts_szakasz'").fetchone())
                    self.assertEqual({r[0] for r in c.execute("SELECT ut FROM fajl")}, sorok_elotte, "file rows kept")
                    self.assertEqual(c.execute("SELECT count(*) FROM fajl WHERE tipus = 'md' AND hash IS NULL").fetchone()[0], 0,
                                     "every note re-parsed after the migration")
                    c.close()
                    self.assertEqual([x["ut"] for x in ix.kereses("migrationtoken")["talalatok"]], ["Dir/Source.md"])
                    celok = sorted(str(r["cel"]) for r in ix.jegyzet("Dir/Source.md")["linkek"])
                    self.assertEqual(celok, ["Dir/Target.md", "Other/Note.md"])
                finally:
                    ix.leallit()
                self.assertEqual(lenyomat(vault, kihagy=()), elotte, "the migration touched the notes")

    def test_ujabb_index_sema_nem_nyilik_es_nem_romlik(self):
        with tmpdir() as t:
            cfg, _, vault = alg_core(t)
            ir(vault, "A.md", "# A\n")
            ix, _ = index_indit(cfg)
            db = Path(ix.db_ut)
            ix.leallit()
            c = sqlite3.connect(str(db))
            c.execute(f"PRAGMA user_version = {tar.VERZIO + 1}")
            c.commit()
            c.close()
            bajtok = db.read_bytes()
            with self.assertRaises(tar.SemaHiba):
                tar.nyit(db, iro=True)
            self.assertEqual(db.read_bytes(), bajtok, "a newer index is neither migrated down nor set aside")


class RegiFajlokTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)

    def munkater(self, nev: str, toml: str) -> Path:
        v = self.t / nev
        (v / ".obsidian").mkdir(parents=True)
        (v / ".manifold").mkdir()
        (v / ".manifold" / "workspace.toml").write_text(toml, encoding="utf-8")
        return v

    def test_minimalis_f3_korabeli_workspace_toml(self):
        id = uuid.uuid4().hex
        v = self.munkater("Old", f'[workspace]\nid = "{id}"\n')
        cfg = termek_cfg(self.root, self.home, v)
        self.assertEqual(cfg.workspace_id, id)
        b = termek_beallitasok.olvas(cfg)
        self.assertIn("ertek", b)
        self.assertTrue(b["setup_szukseges"], "an old workspace without a finished Setup offers it")
        self.assertEqual(workspace.felmer(v, self.alap).meglevo_id, id)

    def test_ismeretlen_es_regi_szakaszok_nem_vegzetesek(self):
        id = uuid.uuid4().hex
        v = self.munkater("Legacy", f'[workspace]\nid = "{id}"\nformatum = 1\nolvaso_min = 1\nnev = "Legacy"\nregi_kulcs = 3\n\n'
                                   '[regi_szakasz]\nx = 1\n\n[naplo]\nut = "Journal/YYYY-MM-DD"\n\n[utak]\nvault = "/etc"\n\n'
                                   '[felkeszultseg]\nkalibralt = true\n')
        cfg = termek_cfg(self.root, self.home, v)
        self.assertEqual(cfg.workspace_id, id)
        self.assertEqual(cfg.section("naplo")["ut"], "Journal/YYYY-MM-DD")
        elutasitott = {k for _, k, *_ in cfg.elutasitott}           # (layer, key, reason)
        for k in ("workspace.regi_kulcs", "regi_szakasz.x", "utak.vault", "felkeszultseg.kalibralt"):
            self.assertTrue(any(e.startswith(k) for e in elutasitott), (k, cfg.elutasitott))
        self.assertEqual(Path(cfg.path("vault")).resolve(), v.resolve(), "the workspace layer cannot move the vault")

    def test_regi_regiszter_es_telepitesi_reteg(self):
        install = Path(self.alap.path("install"))
        install.mkdir(parents=True, exist_ok=True)
        id = uuid.uuid4().hex
        v = self.munkater("Registered", f'[workspace]\nid = "{id}"\n')
        (install / "workspaces.json").write_text(json.dumps({"munkaterek": {id: {"ut": str(v), "nev": "Registered",
                                                                                  "regi_mezo": True}}}), encoding="utf-8")
        r = workspace.Regiszter(install).olvas()
        self.assertEqual(r["formatum"], 1)
        self.assertIn(id, r["munkaterek"])
        (install / "settings.toml").write_text('[telepites]\npresetek = []\n\n[regi]\nkulcs = "x"\n\n[mentes]\nido_perc = 45\n',
                                               encoding="utf-8")
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_VAULT": str(v)})
        self.assertEqual(cfg.section("mentes")["ido_perc"], 45)
        self.assertIn(("telepites", "regi.kulcs"), {(r, k) for r, k, *_ in cfg.elutasitott})

    def test_ujabb_formatum_tovabbra_is_tilos(self):
        v = self.munkater("Newer", f'[workspace]\nid = "{uuid.uuid4().hex}"\nformatum = 9\nolvaso_min = 9\n')
        cfg = termek_cfg(self.root, self.home, v)          # loading is fine; opening it (core start, `workspace.nyit`) is not
        with self.assertRaises(config.ConfigError) as e:
            workspace.nyit(cfg)
        self.assertEqual(e.exception.kod, "workspace_ujabb")
        self.assertIn("workspace_ujabb", workspace.felmer(v, self.alap).akadaly)


class ImportUtanHasznalhatoTest(unittest.TestCase):
    TITOK = "f9-migration-secret-0123456789abcdef"

    def _k(self, port, metodus, ut, torzs=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        try:
            c.request(metodus, ut, body=None if torzs is None else json.dumps(torzs),
                      headers={"Host": f"127.0.0.1:{port}", "X-Manifold": self.TITOK, "Content-Type": "application/json"})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            c.close()

    def test_import_utan_a_core_kereshet_szerkeszthet_visszavonhat(self):
        from core import importalas as imp
        with tmpdir() as t:
            t = Path(t)
            root, home, alap = termek_alap(str(t))
            forras = obsidian_vault(t / "My Vault")
            lenyomat_elotte = ujjlenyomat(forras)
            cel = t / "Imported"
            terv = imp.obsidian_elonezet(forras, cel, alap, None)
            r = imp.obsidian_importal(forras, cel, alap, terv_hash=terv["terv_hash"])
            self.assertEqual(r["allapot"], "kesz")
            p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 env=termek_env(root, home, cel, MOS_API_TITOK=self.TITOK))
            try:
                sor = elso_sor(p)
                self.assertTrue(sor, "the core did not start on the imported workspace")
                k = json.loads(sor)
                self.assertEqual(k["munkater_id"], r["munkater_id"])
                port = k["port"]
                vege = time.monotonic() + 60
                while True:
                    kod, d = self._k(port, "GET", "/api/vault/kereses?q=plan")
                    if kod == 200 and any(x["ut"] == "Projects/Plan.md" for x in d.get("talalatok", [])):
                        break
                    self.assertLess(time.monotonic(), vege, d)
                    time.sleep(0.1)
                kod, j = self._k(port, "GET", "/api/vault/jegyzet?ut=Home.md")
                self.assertEqual(kod, 200, j)
                self.assertIn("Projects/Plan.md", [x["cel"] for x in j["linkek"]])
                kod, d = self._k(port, "GET", "/api/vault/fajl?ut=" + urllib.parse.quote("Ideas.md"))
                self.assertEqual(kod, 200, d)
                eredeti = (cel / "Ideas.md").read_bytes()
                kod, m = self._k(port, "PUT", "/api/vault/fajl", {"ut": "Ideas.md", "tartalom": "Edited after import\n",
                                                                   "alap": d["hash"], "elso": True, "pillanat": True})
                self.assertEqual((kod, m.get("git")), (200, True), m)
                self.assertEqual((cel / "Ideas.md").read_bytes(), b"Edited after import\r\n", "CRLF kept")
                kod, u = self._k(port, "POST", "/api/pillanat/vault/visszavonas", {"sha": m["pillanat"]})
                self.assertEqual(kod, 200, u)
                self.assertEqual((cel / "Ideas.md").read_bytes(), eredeti)
            finally:
                if p.poll() is None:
                    p.stdin.close()
                    try:
                        p.wait(60)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()
                p.stdout.close()
            self.assertEqual(ujjlenyomat(forras), lenyomat_elotte, "the source vault changed")
            w = tomllib.loads((cel / ".manifold" / "workspace.toml").read_text(encoding="utf-8"))
            self.assertEqual(w["workspace"]["id"], r["munkater_id"])
