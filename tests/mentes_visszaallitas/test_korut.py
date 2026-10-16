"""F9 backup / restore audit §1–2: every write path is a snapshot that the undo (`POST /api/pillanat/vault/visszavonas`, a NEW
reverse commit — `git revert` semantics, never `reset`) takes back byte-exactly, and the undo itself can be undone. The history is
never rewritten: every earlier commit stays an ancestor of HEAD. Conflicts (CAS) refuse with 409 and change nothing.

Write paths over real HTTP: note save, new note, rename (with link rewrite), move to another folder, the property-type registry
(`.obsidian/types.json`), the history restore. Function level (product layout): the Obsidian import and its reversal, the demo
reset (and the undo of the reset)."""
from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from tests.biztonsag import Szerver, fa


class KorutTest(Szerver):
    JEGYZETEK = {"Notes/A.md": "# A\n\nalpha body\n", "Notes/B.md": "# B\n\nsee [[A]] and [[Notes/A|alias]]\n",
                 "Notes/C.md": "line one\r\nline two\r\n"}

    def elokeszit(self):
        (self.v / "Archive").mkdir()
        (self.v / "Archive" / ".keep.md").write_text("", encoding="utf-8")   # hidden: never part of a probe
        self.repo.commit("archive folder", {"Mos-Forras": "kezi"})

    # ---------------------------------------------------------------- helpers

    def head(self) -> str:
        return self.repo.git("rev-parse", "HEAD").stdout.strip()

    def ose(self, regi: str, uj: str) -> bool:
        return self.repo.git("merge-base", "--is-ancestor", regi, uj, check=False).returncode == 0

    def tartalom(self):
        return {k: v for k, v in fa(self.v).items() if not k.startswith(".obsidian/") or k.endswith("types.json")}

    def visszavon(self, sha: str) -> str:
        kod, d = self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": sha})
        self.assertEqual(kod, 200, d)
        return d["sha"]

    def korut(self, elotte: dict, sha: str, utana: dict):
        """undo(sha) → `elotte`; undo(undo) → `utana`; HEAD only grows."""
        self.assertTrue(sha, "the write returned no snapshot")
        h0 = self.head()
        vissza = self.visszavon(sha)
        self.assertEqual(self.tartalom(), elotte, "the undo did not restore the bytes")
        self.assertTrue(self.ose(h0, self.head()) and self.ose(sha, self.head()), "history rewritten")
        self.visszavon(vissza)
        self.assertEqual(self.tartalom(), utana, "the undo of the undo did not bring the change back")
        self.kint_erintetlen()

    def ment(self, ut: str, szoveg: str) -> dict:
        kod, d = self.k("GET", "/api/vault/fajl?ut=" + urllib.parse.quote(ut))
        self.assertEqual(kod, 200, d)
        kod, m = self.k("PUT", "/api/vault/fajl", {"ut": ut, "tartalom": szoveg, "alap": d["hash"], "elso": True, "pillanat": True})
        self.assertEqual(kod, 200, m)
        return m

    def nevez(self, ut: str, uj: str) -> dict:
        kod, t = self.k("POST", "/api/vault/atnevezes/terv", {"ut": ut, "uj": uj})
        self.assertEqual(kod, 200, t)
        kod, d = self.k("POST", "/api/vault/atnevezes", {"ut": ut, "uj": uj, "terv_hash": t["terv_hash"]})
        self.assertEqual(kod, 200, d)
        return d

    # ---------------------------------------------------------------- write paths

    def test_jegyzet_mentese(self):
        elotte = self.tartalom()
        m = self.ment("Notes/A.md", "# A\n\nchanged body\n")
        utana = self.tartalom()
        self.assertNotEqual(utana, elotte)
        self.korut(elotte, m["pillanat"], utana)

    def test_crlf_jegyzet_mentese_bajtra(self):
        elotte = self.tartalom()
        m = self.ment("Notes/C.md", "line one\nline 2\n")
        self.assertEqual((self.v / "Notes/C.md").read_bytes(), b"line one\r\nline 2\r\n", "CRLF kept")
        self.korut(elotte, m["pillanat"], self.tartalom())

    def test_uj_jegyzet(self):
        elotte = self.tartalom()
        kod, d = self.k("POST", "/api/vault/uj", {"nev": "Fresh", "mappa": "Notes"})
        self.assertEqual(kod, 201, d)
        utana = self.tartalom()
        self.assertIn("Notes/Fresh.md", utana)
        self.korut(elotte, d["pillanat"], utana)

    def test_atnevezes_linkekkel(self):
        elotte = self.tartalom()
        d = self.nevez("Notes/A.md", "Notes/Alpha.md")
        utana = self.tartalom()
        self.assertIn("Notes/Alpha.md", utana)
        self.assertNotIn("Notes/A.md", utana)
        self.assertIn(b"Alpha", utana["Notes/B.md"], "the link in B was rewritten")
        self.korut(elotte, d["pillanat"], utana)

    def test_athelyezes_masik_mappaba(self):
        elotte = self.tartalom()
        d = self.nevez("Notes/A.md", "Archive/A.md")
        utana = self.tartalom()
        self.assertIn("Archive/A.md", utana)
        self.korut(elotte, d["pillanat"], utana)

    def test_tulajdonsag_tipus_regiszter(self):
        elotte = self.tartalom()
        for tipus, kulcs in (("number", "rating"), ("date", "due")):
            kod, t = self.k("GET", "/api/vault/tulajdonsagok/tipusok")
            self.assertEqual(kod, 200, t)
            kod, d = self.k("POST", "/api/vault/tulajdonsagok/tipus", {"kulcs": kulcs, "tipus": tipus, "rev": t["rev"]})
            self.assertEqual(kod, 200, d)
        utana = self.tartalom()
        self.assertIn(".obsidian/types.json", utana)
        # the second change on its own: undo → only `rating` left; undo of the undo → both
        kozben = dict(utana)
        self.visszavon(d["pillanat"])
        self.assertNotIn(b'"due"', self.tartalom()[".obsidian/types.json"])
        self.assertIn(b'"rating"', self.tartalom()[".obsidian/types.json"])
        self.assertEqual({k: v for k, v in self.tartalom().items() if k != ".obsidian/types.json"},
                         {k: v for k, v in elotte.items() if k != ".obsidian/types.json"})
        self.assertTrue(kozben)
        self.kint_erintetlen()

    def test_elozmeny_visszaallitas(self):
        regi = self.tartalom()
        m1 = self.ment("Notes/A.md", "# A\n\nversion two\n")
        self.assertTrue(m1["pillanat"])
        kod, d = self.k("GET", "/api/vault/elozmeny?ut=Notes/A.md")
        self.assertEqual(kod, 200, d)
        alap = d["bejegyzesek"][-1]["sha"]                    # the oldest entry: the baseline
        elotte = self.tartalom()
        kod, v = self.k("POST", "/api/vault/elozmeny/visszaallit", {"ut": "Notes/A.md", "sha": alap})
        self.assertEqual(kod, 200, v)
        self.assertEqual(self.tartalom()["Notes/A.md"], regi["Notes/A.md"])
        self.korut(elotte, v["sha"], self.tartalom())

    # ---------------------------------------------------------------- CAS

    def test_cas_utkozesek_nem_irnak(self):
        kod, d = self.k("GET", "/api/vault/fajl?ut=Notes/A.md")
        regi_hash = d["hash"]
        (self.v / "Notes/A.md").write_text("# A\n\nchanged by Obsidian\n", encoding="utf-8")       # an outside edit
        elotte, h = self.tartalom(), self.head()
        kod, e = self.k("PUT", "/api/vault/fajl", {"ut": "Notes/A.md", "tartalom": "mine\n", "alap": regi_hash, "pillanat": True})
        self.assertEqual((kod, e.get("kod")), (409, "vault.jegyzet_valtozott"), e)
        kod, e = self.k("PUT", "/api/vault/fajl", {"ut": "Notes/A.md", "tartalom": "mine\n", "pillanat": True})
        self.assertEqual(kod, 400, e)                                           # no base: never a blind overwrite
        kod, e = self.k("POST", "/api/vault/tulajdonsagok/tipus", {"kulcs": "x", "tipus": "number", "rev": "0" * 64})
        self.assertEqual(kod, 409, e)
        kod, t = self.k("POST", "/api/vault/atnevezes/terv", {"ut": "Notes/B.md", "uj": "Notes/B2.md"})
        (self.v / "Notes/New.md").write_text("[[B]]\n", encoding="utf-8")       # the vault changed after the plan
        import time
        vege = time.monotonic() + 30
        while self.k("GET", "/api/vault/jegyzet?ut=Notes/New.md")[0] != 200:    # … and the index has seen it
            self.assertLess(time.monotonic(), vege)
            time.sleep(0.05)
        kod, e = self.k("POST", "/api/vault/atnevezes", {"ut": "Notes/B.md", "uj": "Notes/B2.md", "terv_hash": t["terv_hash"]})
        self.assertEqual(kod, 409, e)
        (self.v / "Notes/New.md").unlink()
        self.assertEqual(self.tartalom(), elotte)
        self.assertEqual(self.head(), h, "a refused write made a commit")

    def test_atnevezes_a_terv_utani_kulso_valtozasnal_nem_hagy_felkesz_allapotot(self):
        """An outside note linking the source appears after the plan, before the index sees it: the rename either refuses (409)
        or runs, fails its own check and rolls back (`atnevezes.visszaallitva`). Either way no half-renamed vault remains."""
        kod, t = self.k("POST", "/api/vault/atnevezes/terv", {"ut": "Notes/B.md", "uj": "Notes/B2.md"})
        self.assertEqual(kod, 200, t)
        (self.v / "Notes/Late.md").write_text("[[B]]\n", encoding="utf-8")
        b_elotte = (self.v / "Notes/B.md").read_bytes()
        kod, e = self.k("POST", "/api/vault/atnevezes", {"ut": "Notes/B.md", "uj": "Notes/B2.md", "terv_hash": t["terv_hash"]})
        if kod == 200:                                         # the index was fast enough: then the new link was rewritten too
            self.assertEqual((self.v / "Notes/Late.md").read_text(encoding="utf-8"), "[[B2]]\n")
            return
        self.assertIn((kod, e.get("kod")), ((409, None), (409, "atnevezes.valtozott"), (409, "atnevezes.visszaallitva")), e)
        self.assertEqual((self.v / "Notes/B.md").read_bytes(), b_elotte)
        self.assertFalse((self.v / "Notes/B2.md").exists())
        self.assertEqual((self.v / "Notes/Late.md").read_text(encoding="utf-8"), "[[B]]\n")
        self.kint_erintetlen()

    def test_visszavonasi_utkozes_nem_ir(self):
        m1 = self.ment("Notes/A.md", "# A\n\nfirst edit\n")
        self.ment("Notes/A.md", "# A\n\nsecond edit on the same line\n")
        elotte, h = self.tartalom(), self.head()
        kod, e = self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": m1["pillanat"]})
        self.assertEqual((kod, e.get("kod")), (409, "pillanatkep.visszavonas_utkozes"), e)
        self.assertEqual(self.tartalom(), elotte)
        self.assertEqual(self.head(), h)
        for rossz in ({"sha": "HEAD"}, {"sha": "--all"}, {"sha": "0" * 40}, {"kor": "proba-x"}, {}):
            kod, e = self.k("POST", "/api/pillanat/vault/visszavonas", rossz)
            self.assertIn(kod, (400, 404, 409), (rossz, e))
        self.assertEqual(self.tartalom(), elotte)


class ImportVisszaforditasTest(__import__("unittest").TestCase):
    """The Obsidian import (a new workspace) → an edit inside it with its snapshot → undo of the edit → reversal of the import:
    the source stays byte- and metadata-identical, the reversal takes everything (the edit was undone), nothing is deleted."""

    def test_import_szerkesztes_visszavonas_visszaforditas(self):
        from core import importalas as imp
        from core import snapshot
        from core import vaultio
        from tests.fresh_install import termek_alap, termek_cfg
        from tests.helpers import tmpdir
        from tests.migracio import Kuka, obsidian_vault, ujjlenyomat
        with tmpdir() as t:
            t = Path(t)
            root, home, alap = termek_alap(str(t))
            forras = obsidian_vault(t / "Source vault")
            lenyomat = ujjlenyomat(forras)
            cel = t / "Imported"
            terv = imp.obsidian_elonezet(forras, cel, alap, None)
            r = imp.obsidian_importal(forras, cel, alap, terv_hash=terv["terv_hash"])
            self.assertEqual(r["allapot"], "kesz")
            cfg = termek_cfg(root, home, cel)
            repo = snapshot.repos(cfg)["vault"]
            self.assertTrue(repo.live())
            v = vaultio.Vault(cfg)
            d = v.read("Ideas.md")
            m = v.write({"ut": "Ideas.md", "tartalom": "edited inside Manifold\n", "alap": d["hash"], "elso": True, "pillanat": True})
            self.assertTrue(m["pillanat"])
            repo.undo_commit(m["pillanat"])
            self.assertEqual((cel / "Ideas.md").read_bytes(), (forras / "Ideas.md").read_bytes())
            kuka = Kuka(t / "Trash")
            vf = imp.visszafordit(r["id"], alap, kuka=kuka)
            self.assertEqual((vf["allapot"], vf["megtartva"]), ("visszaforditva", []), vf)
            self.assertFalse(cel.exists())
            self.assertTrue(any(p.name.endswith("-Imported") for p in kuka.mappa.iterdir()), "nothing deleted: in the Trash")
            self.assertEqual(ujjlenyomat(forras), lenyomat)


class DemoAlaphelyzetTest(__import__("unittest").TestCase):
    """The demo reset keeps the user's edit one undo away: before-snapshot → reset → undo of the reset commit brings it back."""

    def test_reset_es_visszavonasa(self):
        from core import demo, snapshot
        from tests.fresh_install import termek_alap
        from tests.helpers import tmpdir
        with tmpdir() as t:
            _, _, alap = termek_alap(t)
            v, cfg, _ = demo.inditas(alap)
            repo = snapshot.repos(cfg)["vault"]
            jegyzet = next(p for p in sorted(v.rglob("*.md")) if ".manifold" not in p.parts and not p.name.startswith("."))
            eredeti = jegyzet.read_bytes()
            jegyzet.write_bytes(eredeti + b"\nmy own line\n")
            (v / "Mine.md").write_text("a note I added\n", encoding="utf-8")
            sajat = {jegyzet: jegyzet.read_bytes()}
            r = demo.alaphelyzet(cfg, megerosit=True)
            self.assertEqual(jegyzet.read_bytes(), eredeti)
            self.assertFalse((v / "Mine.md").exists())
            self.assertIn("Mine.md", r["felretett"], "an added note is set aside, not deleted")
            self.assertTrue((v / r["visszahelye"] / "Mine.md").is_file())
            elotte, utana = r["pillanatkep"]["elotte"], r["pillanatkep"]["utana"]
            self.assertTrue(elotte and utana)
            repo.undo_commit(utana)
            self.assertEqual(jegyzet.read_bytes(), sajat[jegyzet], "the undo of the reset brings the user's edit back")
            self.assertEqual(repo.git("merge-base", "--is-ancestor", utana, "HEAD", check=False).returncode, 0)
            self.assertTrue(os.path.isdir(v / ".manifold"))
