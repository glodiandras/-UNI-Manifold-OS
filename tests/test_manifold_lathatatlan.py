"""I6 (F3-DESIGN §3.6, K1): a `.manifold` láthatatlan.

Egy teljes próbaklón (a vault minden jegyzetével, képével, egy félbemaradt mentés `.manifold-tmp` fájljával) a
`.manifold/var/tmp/proba/` alatt: az index, a linkfeloldás, a figyelő (FSEvents és a lekérdező tartalék), a higiénia, a takarítás, a bináris
napló, a kártya-szinkron és a videó-egyezés nem látja; a `norm_path` a `.manifold/…` utat elutasítja; a pillanatkép (`git status`)
figyelmen kívül hagyja."""
from __future__ import annotations

import ctypes
import json
import re
import sqlite3
import time
import unittest
from pathlib import Path

from core import binaris_naplo, frame, snapshot, vaultio, workspace
from core.index import feloldas, figyelo, indexelo
from tests import csak_darwin
from tests.fresh_install import obsidian_vault, termek_alap, termek_cfg
from tests.helpers import tmpdir
from tests.index_segedek import index_indit, var_ra


class LathatatlanTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        root, home, alap = termek_alap(self._t.name)
        self.v = obsidian_vault(self.t / "Vault")
        (self.v / "T01 - Téma" / "Elmelet").mkdir(parents=True)
        (self.v / "T01 - Téma" / "Elmelet" / "Lecke.md").write_text("# Lecke\nszöveg\n", encoding="utf-8")
        workspace.letrehoz(self.v, alap)
        self.cfg = termek_cfg(root, home, self.v)
        # a „teljes” próbaklón: a vault minden fájlja a `.manifold/var/tmp/proba/<kör>/<vault>/` alatt, plusz saját fájlok
        self.klon = self.cfg.path("tmp") / "proba" / "K1" / self.v.name
        self.klon.mkdir(parents=True)
        for p in self.v.rglob("*"):
            rel = p.relative_to(self.v)
            if rel.parts[0] == ".manifold":
                continue
            cel = self.klon / rel
            if p.is_dir():
                cel.mkdir(parents=True, exist_ok=True)
            else:
                cel.parent.mkdir(parents=True, exist_ok=True)
                cel.write_bytes(p.read_bytes())
        (self.klon / "Csak a klonban.md").write_text("[[Kezdőlap]]\n", encoding="utf-8")
        (self.klon / "Jegyzetek" / "Első.md").write_text("átírt klón\n", encoding="utf-8")
        (self.klon / "csak-klon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.klon / "Jegyzetek" / ".Első.md.abcdef12.manifold-tmp").write_text("félbe")

    def nincs_manifold(self, utak):
        utak = list(utak)
        self.assertTrue(utak)
        self.assertEqual([u for u in utak if ".manifold" in str(u)], [])

    def test_bejaras_es_linkfeloldas(self):
        utak = [nfc for nfc, _ in feloldas.bejaras(self.v)]
        self.nincs_manifold(utak)
        self.assertNotIn("Csak a klonban.md", [u.rsplit("/", 1)[-1] for u in utak])
        f = feloldas.Feloldo(utak)
        self.assertEqual(f.resolve("Első", "Kezdőlap.md")[0], "Jegyzetek/Első.md")
        self.assertFalse(f.resolve("Első", "Kezdőlap.md")[2])               # nem többértelmű
        self.assertFalse(indexelo._ervenyes(".manifold/var/tmp/proba/K1/Vault/Kezdőlap.md"))
        self.assertFalse(indexelo._ervenyes(".manifold/workspace.toml"))

    def test_az_index_nem_latja(self):
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        c = sqlite3.connect(f"file:{ix.db_ut}?mode=ro", uri=True)
        self.addCleanup(c.close)
        fajlok = [r[0] for r in c.execute("SELECT ut FROM fajl WHERE torolve IS NULL")]
        self.nincs_manifold(fajlok)
        self.assertIn("Jegyzetek/Első.md", fajlok)
        self.nincs_manifold(r[0] for r in c.execute("SELECT ut FROM mappa WHERE torolve IS NULL"))
        celok = [r[0] for r in c.execute("SELECT cel FROM link WHERE cel IS NOT NULL")]
        self.nincs_manifold(celok)
        # egy `.manifold` alatti változás (teljes újrabejárás kérése is) nem kerül az indexbe
        (self.klon / "Uj a klonban.md").write_text("x")
        ix.jelez([".manifold/var/tmp"], True)                             # a figyelő teljes újrabejárás-kérése
        self.assertTrue(ix.frissit([".manifold/var/tmp/proba/K1/Vault/Uj a klonban.md"]))   # (sorrendben utána)
        self.nincs_manifold(r[0] for r in c.execute("SELECT ut FROM fajl WHERE torolve IS NULL"))

    def test_higienia_riport(self):
        from core.higienia import Higienia
        from core.tulajdonsagok import Tulajdonsagok
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        szoveg = json.dumps(Higienia(self.cfg, ix, Tulajdonsagok(self.cfg, ix)).riport(), ensure_ascii=False)
        self.assertNotIn(".manifold", szoveg)
        self.assertNotIn("Csak a klonban", szoveg)

    def test_lekerdezo_figyelo(self):
        lk = figyelo.Lekerdezo(self.v, lambda utak, teljes: None)
        self.nincs_manifold(lk._pillanat())

    def test_fsevents_szuro(self):
        kapott = []
        f = figyelo.FSEvents(self.v, lambda utak, teljes: kapott.append((list(utak), teljes)))
        utak = [f"{f.root}/.manifold/var/tmp/proba/K1/Vault/a.md", f"{f.root}/a.md", f"{f.root}/.manifold"]
        tomb = (ctypes.c_char_p * 3)(*[u.encode() for u in utak])
        jelek = (ctypes.c_uint32 * 3)(0, 0, figyelo._MUST_SCAN)
        f._esemeny(None, None, 3, tomb, jelek, None)
        self.assertEqual(kapott, [(["a.md"], False)])

    @csak_darwin("FSEvents")
    def test_fsevents_elo_folyam(self):
        kapott = []
        f = figyelo.FSEvents(self.v, lambda utak, teljes: kapott.extend(utak))
        f.indit()
        self.addCleanup(f.leallit)
        time.sleep(0.2)
        (self.klon / "friss.md").write_text("x")
        (self.v / ".manifold" / "var" / "state" / "x.json").write_text("{}")
        (self.v / "Uj.md").write_text("y")
        self.assertTrue(var_ra(lambda: "Uj.md" in kapott, 5))
        time.sleep(0.3)
        self.nincs_manifold(kapott)

    def test_takaritas_a_klon_ideiglenes_fajljat_nem_latja(self):
        sajat = self.v / "Jegyzetek" / ".Második.md.0123abcd.manifold-tmp"
        sajat.write_text("félbe")
        self.assertEqual(frame.tmp_maradekok(self.cfg), [sajat])

    def test_binaris_naplo(self):
        leltar = binaris_naplo.leltar(self.v)
        self.nincs_manifold(leltar)
        self.assertEqual(sorted(leltar), ["kép.png"])

    def test_kartya_szinkron_vault_utak(self):
        from modulok.kartya import lanc
        utak = lanc.vault_md_utak(self.cfg)
        self.nincs_manifold(utak)
        self.assertNotIn("Csak a klonban.md", utak)

    def test_video_egyezes(self):
        from modulok.ytdlp import egyezes
        minta = re.compile(r"^T\d\d - ")
        self.assertEqual(egyezes.temak(self.v, minta, ()), ["T01 - Téma"])
        idx = egyezes.NoteIndex(self.v, tema_minta=minta, kizart_mappak=(), elmelet_mappa="Elmelet")
        self.nincs_manifold(idx.notes)

    def test_norm_path_es_vault_api_elutasitja(self):
        for rp in (".manifold/workspace.toml", ".manifold/var/tmp/proba/K1/Vault/Kezdőlap.md", "a/.manifold/x.md"):
            with self.assertRaises(vaultio.Invalid):
                vaultio.norm_path(rp)
        with self.assertRaises(vaultio.Invalid):
            vaultio.Vault(self.cfg).read(".manifold/workspace.toml")

    def test_git_status_figyelmen_kivul_hagyja(self):
        repo = snapshot.repos(self.cfg)["vault"]
        self.assertEqual(repo.dirty(), [])
        self.assertIsNone(repo.commit("kézi", {"Mos-Forras": "kezi"}))
        (self.v / "Új.md").write_text("ú")
        self.assertEqual(repo.dirty_paths(), ["Új.md"])


if __name__ == "__main__":
    unittest.main()
