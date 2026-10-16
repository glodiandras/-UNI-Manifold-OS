"""F8: the v2 import (Developer mode) — a Manifold-OS v2 folder's conventions into the open workspace's settings
(`core/importalas.py`). Synthetic v2 folder and workspace in temp dirs; the v2 folder must stay byte-identical."""
from __future__ import annotations

import json
import os
import tomllib
import types
import unittest
from pathlib import Path
from unittest import mock

from core import config, importalas as imp, termek_beallitasok, utvonalak, workspace
from core.utvonalak import HttpError
from tests.fresh_install import termek_alap, termek_cfg
from tests.helpers import alg_core, tmpdir
from tests.migracio import V2_SEMA, ujjlenyomat, v2_mappa


class V2Test(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, alap = termek_alap(self._t.name)
        self.vault = self.t / "Notes"
        self.vault.mkdir()
        (self.vault / "Note.md").write_text("# Note\n", encoding="utf-8")
        workspace.letrehoz(self.vault, alap)
        self.cfg = termek_cfg(self.root, self.home, self.vault)
        self.v2 = v2_mappa(self.t / "Manifold-OS v2")
        self.v2_lenyomat = ujjlenyomat(self.v2)
        self.ws = self.vault / ".manifold" / "workspace.toml"
        self.sema = self.vault / ".manifold" / "schema.json"

    def tearDown(self):
        self.assertEqual(ujjlenyomat(self.v2), self.v2_lenyomat, "the v2 import changed its source")

    def friss(self):
        return termek_cfg(self.root, self.home, self.vault)

    def test_elonezet_semmit_nem_ir(self):
        elotte = self.ws.read_bytes()
        r = imp.v2_elonezet(self.v2, self.cfg)
        self.assertEqual(r["eredmeny"], "mehet", r)
        self.assertEqual(self.ws.read_bytes(), elotte)
        self.assertFalse(self.sema.exists())
        self.assertFalse((self.cfg.path("state") / "import").exists())
        kulcsok = {k["kulcs"]: k["uj"] for k in r["kulcsok"]}
        self.assertEqual(kulcsok["naplo.ut"], "Log/YYYY/YYYY-MM-DD")
        self.assertEqual(kulcsok["kartya.mappa"], "Side - flashcards")
        self.assertEqual(kulcsok["pdf.tags.Q"], "Quantum")
        self.assertEqual(kulcsok["vault.kisero_elotag"], "Side - ")
        self.assertEqual(kulcsok["sema.mod"], "tanacsado", "the v2 file's own schema mode wins over the default `szigoru`")
        for tilos in ("utak.work", "fuzet.mappak", "modellek.pelda.nev", "sema.vault"):
            self.assertNotIn(tilos, kulcsok)
        self.assertGreater(r["nem_munkater_kulcs_db"], 0)
        self.assertEqual(r["sema"]["muvelet"], "ir")
        self.assertTrue(r["ujrainditas"])
        self.assertTrue(r["id"].startswith("v2-"))
        self.assertNotIn("_sema_bajt", r)

    def test_import_ujrainditas_utan_ervenyes_es_idempotens(self):
        t = imp.v2_elonezet(self.v2, self.cfg)
        r = imp.v2_importal(self.v2, self.cfg, terv_hash=t["terv_hash"])
        self.assertEqual((r["allapot"], r["ujrainditas"]), ("kesz", True))
        cfg = self.friss()
        self.assertEqual(cfg.section("naplo")["ut"], "Log/YYYY/YYYY-MM-DD")
        self.assertEqual(cfg.section("kartya")["mappa"], "Side - flashcards")
        self.assertEqual(cfg.section("pdf", "tags")["Q"], "Quantum")
        self.assertEqual(cfg.forras("naplo", "ut"), "munkater")
        self.assertEqual(json.loads(self.sema.read_text(encoding="utf-8")), V2_SEMA)
        self.assertTrue(self.ws.with_name("workspace.toml.elozo").is_file())
        self.assertEqual(workspace.azonosit(self.vault), self.cfg.workspace_id)
        # repeated: nothing to do, nothing written
        ws, sema = self.ws.read_bytes(), self.sema.read_bytes()
        r2 = imp.v2_importal(self.v2, self.cfg)
        self.assertEqual((r2["valtozas"], r2["ismetles"]), (0, True))
        self.assertEqual((self.ws.read_bytes(), self.sema.read_bytes()), (ws, sema))
        self.assertEqual(imp.v2_elonezet(self.v2, self.cfg)["valtozas_db"], 0)

    def test_utkozo_kulcs_es_sema_nem_irodik_felul(self):
        self.ws.write_text(self.ws.read_text(encoding="utf-8") + '\n[kartya]\nmappa = "Mine"\n', encoding="utf-8")
        self.sema.write_text(json.dumps({"mezosorrend": ["Tags"]}), encoding="utf-8")
        sema_elotte = self.sema.read_bytes()
        t = imp.v2_elonezet(self.v2, self.cfg)
        self.assertIn("utkozes_kihagyva", t["figyelmeztetes"])
        utk = {u["kulcs"] for u in t["utkozesek"]}
        self.assertEqual(utk, {"kartya.mappa", "schema.json"})
        imp.v2_importal(self.v2, self.cfg, terv_hash=t["terv_hash"])
        cfg = self.friss()
        self.assertEqual(cfg.section("kartya")["mappa"], "Mine")
        self.assertEqual(cfg.section("naplo")["ut"], "Log/YYYY/YYYY-MM-DD")
        self.assertEqual(self.sema.read_bytes(), sema_elotte)

    def test_valtozott_munkater_toml_utan_a_regi_terv_nem_fut(self):
        t = imp.v2_elonezet(self.v2, self.cfg)
        self.ws.write_text(self.ws.read_text(encoding="utf-8") + "\n# edited elsewhere\n", encoding="utf-8")
        elotte = self.ws.read_bytes()
        with self.assertRaises(HttpError) as e:
            imp.v2_importal(self.v2, self.cfg, terv_hash=t["terv_hash"])
        self.assertEqual(e.exception.kod, "import.terv_valtozott")
        self.assertEqual(self.ws.read_bytes(), elotte)

    def test_visszaforditas_bajtra_visszaallit(self):
        elotte = self.ws.read_bytes()
        r = imp.v2_importal(self.v2, self.cfg)
        v = imp.visszafordit(r["id"], self.cfg, cfg=self.cfg)
        self.assertEqual(v["allapot"], "visszaforditva")
        self.assertEqual(self.ws.read_bytes(), elotte)
        self.assertFalse(self.sema.exists())
        naplo = imp._v2_naplo(self.cfg, r["id"])
        self.assertEqual(json.loads((naplo.mappa / "visszavont-schema.json").read_text()), V2_SEMA, "kept, not deleted")
        self.assertTrue(imp.visszafordit(r["id"], self.cfg, cfg=self.cfg)["ismetles"])
        self.assertEqual(imp.allapot(r["id"], self.cfg, self.cfg)["allapot"], "visszaforditva")
        # importing again after the undo works and writes the same result
        r2 = imp.v2_importal(self.v2, self.cfg)
        self.assertEqual(r2["allapot"], "kesz")
        self.assertEqual(self.friss().section("kartya")["mappa"], "Side - flashcards")

    def test_kesobbi_kezi_valtozas_utan_nem_fordit_vissza(self):
        r = imp.v2_importal(self.v2, self.cfg)
        self.ws.write_text(self.ws.read_text(encoding="utf-8") + "\n# my own edit\n", encoding="utf-8")
        elotte = self.ws.read_bytes(), self.sema.read_bytes()
        with self.assertRaises(HttpError) as e:
            imp.visszafordit(r["id"], self.cfg, cfg=self.cfg)
        self.assertEqual(e.exception.kod, "import.visszafordit_utkozes")
        self.assertEqual((self.ws.read_bytes(), self.sema.read_bytes()), elotte)

    def test_nem_v2_mappa_es_hordozhato_elrendezes_tilos(self):
        r = imp.v2_elonezet(self.t / "Notes", self.cfg)
        self.assertEqual((r["eredmeny"], r["akadaly"]), ("tilos", ["v2_nincs_konfig"]))
        with self.assertRaises(HttpError) as e:
            imp.v2_importal(self.t / "Notes", self.cfg)
        self.assertEqual(e.exception.kod, "import.tilos")
        # portable layout: the settings would land in the code checkout's layer — refused, nothing written to the code tree
        cfg, root, _ = alg_core(str(self.t / "port"))
        elotte = ujjlenyomat(root / "config")
        r = imp.v2_elonezet(self.v2, cfg)
        self.assertIn("hordozhato_elrendezes", r["akadaly"])
        with self.assertRaises(HttpError):
            imp.v2_importal(self.v2, cfg)
        self.assertEqual(ujjlenyomat(root / "config"), elotte)

    def test_http_developer_modban(self):
        r = utvonalak.Regiszter()
        imp.utvonalak(r)
        app = types.SimpleNamespace(cfg=self.cfg, bus=types.SimpleNamespace(publish=lambda e: None))

        def hiv(ut, torzs):
            kezelo, m = r.keres("POST", ut)
            return kezelo(utvonalak.Kerees(app, None, ut, {}, m, torzs=torzs))

        with mock.patch.dict(os.environ):
            os.environ.pop("MOS_FEJLESZTOI_NEZET", None)
            with self.assertRaises(HttpError) as e:
                hiv("/api/import/v2/elonezet", {"forras": str(self.v2)})
            self.assertEqual((e.exception.code, e.exception.kod), (403, "import.fejleszto_mod"))
            b = termek_beallitasok.olvas(self.cfg)
            termek_beallitasok.ir(self.cfg, b["rev"], {"fejleszto": {"mod": True}})
            t = hiv("/api/import/v2/elonezet", {"forras": str(self.v2)})
            k = hiv("/api/import/v2", {"forras": str(self.v2), "terv_hash": t["terv_hash"]})
            self.assertEqual(k["allapot"], "kesz")
            v = hiv("/api/import/visszafordit", {"id": k["id"]})
            self.assertEqual(v["allapot"], "visszaforditva")


if __name__ == "__main__":
    unittest.main()
