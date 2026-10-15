"""A pillanatkép- és visszavonási réteg — ideiglenes álmunkafán, a valódi vault érintetlen (a legacy tesztjeinek portja)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from core import snapshot


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.wt = base / "Vault"
        self.wt.mkdir()
        (self.wt / ".obsidian").mkdir()
        (self.wt / "T01 - Téma").mkdir()
        self.note = self.wt / "T01 - Téma" / "01 - Jegyzet.md"
        self.note.write_text("---\nTags:\n  - History\n---\n\n# Jegyzet\n\nEredeti.\n", encoding="utf-8")
        (self.wt / "T01 - Téma" / "kep.JPG").write_bytes(b"\xff\xd8binary")
        (self.wt / "video.mp4").write_bytes(b"\x00" * 64)
        self.repo = snapshot.Repo("vault", self.wt, base / "var" / "vault.git",
                                  ["*.JPG", "*.jpg", "*.mp4", ".DS_Store"])
        self.repo.init()

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_git_inside_work_tree(self):
        self.assertFalse((self.wt / ".git").exists())
        self.assertTrue(self.repo.exists())

    def test_binaries_excluded(self):
        sha = self.repo.commit("alap")
        self.assertIsNotNone(sha)
        files = self.repo.git("ls-files").stdout.splitlines()
        self.assertIn("T01 - Téma/01 - Jegyzet.md", files)
        self.assertFalse(any(f.endswith((".JPG", ".mp4")) for f in files))

    def test_commit_idempotent(self):
        self.assertIsNotNone(self.repo.commit("alap"))
        self.assertIsNone(self.repo.commit("újra"))

    def test_undo_item_restores_bytes(self):
        self.repo.commit("alap")
        before = self.note.read_bytes()
        self.note.write_text(before.decode() + "\nGépi kiegészítés.\n", encoding="utf-8")
        sha = self.repo.commit("tétel", {snapshot.TRAILER_RUN: "k1", snapshot.TRAILER_ITEM: "t1"})
        self.repo.undo_commit(sha)
        self.assertEqual(self.note.read_bytes(), before)

    def test_undo_run_reverts_all_items_and_keeps_manual_edit(self):
        self.repo.commit("alap")
        before = self.note.read_bytes()
        other = self.wt / "T01 - Téma" / "02 - Új.md"
        self.note.write_text(before.decode() + "\nA\n", encoding="utf-8")
        self.repo.commit("t1", {snapshot.TRAILER_RUN: "k2"})
        other.write_text("# Új\n", encoding="utf-8")
        self.repo.commit("t2", {snapshot.TRAILER_RUN: "k2"})
        manual = self.wt / "kezi.md"
        manual.write_text("a gazda írta\n", encoding="utf-8")
        self.repo.undo_run("k2")
        self.assertEqual(self.note.read_bytes(), before)
        self.assertFalse(other.exists())
        self.assertEqual(manual.read_text(encoding="utf-8"), "a gazda írta\n")
        subjects = [c.subject for c in self.repo.log(5)]
        self.assertIn("kézi változások a visszavonás előtt", subjects)

    def test_machine_commit_separates_manual_edits(self):
        self.repo.commit("alap")
        manual = self.wt / "kezi.md"
        manual.write_text("a gazda írta\n", encoding="utf-8")
        self.note.write_text("gépi\n", encoding="utf-8")
        sha = self.repo.commit_machine("gép", {snapshot.TRAILER_RUN: "k5"}, ["T01 - Téma/01 - Jegyzet.md"])
        self.assertEqual(self.repo.changed_files(sha), ["T01 - Téma/01 - Jegyzet.md"])
        self.assertEqual(self.repo.log(2)[1].subject, "kézi változások (a gépi kör előtt különválasztva)")
        self.repo.undo_run("k5")
        self.assertEqual(manual.read_text(encoding="utf-8"), "a gazda írta\n")   # a gazdáé marad

    def test_exclusion_protects_owner_paths_in_mixed_commit(self):
        self.repo.commit("alap")
        (self.wt / "X01").mkdir()
        diary = self.wt / "X01" / "nap.md"
        diary.write_text("napló\n", encoding="utf-8")
        self.note.write_text("gépi\n", encoding="utf-8")
        sha = self.repo.commit("kevert", {snapshot.TRAILER_RUN: "k6"})   # a régi, add -A-s hiba
        self.repo.undo_run("k6", {sha: ["X01/*"]})
        self.assertTrue(diary.exists())
        self.assertIn("Eredeti.", self.note.read_text(encoding="utf-8"))

    def test_undo_restores_moved_files(self):
        self.repo.commit("alap")
        moved = self.wt / "T01 - Téma" / "al"
        moved.mkdir()
        os.rename(self.note, moved / "01 - Jegyzet.md")
        sha = self.repo.commit("áthelyezés")
        self.repo.undo_commit(sha)
        self.assertTrue(self.note.exists())
        self.assertFalse((moved / "01 - Jegyzet.md").exists())

    def test_undo_conflict_aborts_cleanly(self):
        self.repo.commit("alap")
        self.note.write_text("gépi 1\n", encoding="utf-8")
        sha = self.repo.commit("gép")
        self.note.write_text("gazda felülírta\n", encoding="utf-8")
        self.repo.commit("kézi")
        with self.assertRaises(snapshot.UndoConflict):
            self.repo.undo_commit(sha)
        self.assertEqual(self.note.read_text(encoding="utf-8"), "gazda felülírta\n")
        self.assertEqual(self.repo.dirty(), [])

    def test_log_trailers(self):
        self.repo.commit("alap")
        self.note.write_text("x\n", encoding="utf-8")
        self.repo.commit("tétel", {snapshot.TRAILER_RUN: "k9", snapshot.TRAILER_ITEM: "média-42"})
        c = self.repo.log(1)[0]
        self.assertEqual(c.run, "k9")
        self.assertEqual(c.item, "média-42")
        self.assertEqual(len(self.repo.log(run="k9")), 1)

    def test_undo_keeps_nfd_name_on_disk(self):
        """2.0: a visszavonás után a lemezen álló NFD-név megmarad (a `git apply` NFC-vel írná vissza)."""
        import unicodedata
        nfd = unicodedata.normalize("NFD", "Öröklés.md")
        f = self.wt / "T01 - Téma" / nfd
        f.write_bytes("# Öröklés\r\nElső.\r\n".encode())
        self.repo.commit("alap")
        before = f.read_bytes()
        f.write_bytes(before + "Gépi.\r\n".encode())
        sha = self.repo.commit("tétel", {snapshot.TRAILER_RUN: "k10"})
        self.repo.undo_commit(sha)
        names = os.listdir(self.wt / "T01 - Téma")
        self.assertIn(nfd, names)
        if nfd != unicodedata.normalize("NFC", nfd):
            self.assertNotIn(unicodedata.normalize("NFC", nfd), names)
        self.assertEqual((self.wt / "T01 - Téma" / nfd).read_bytes(), before)
        self.assertEqual(self.repo.dirty(), [])

    def test_undo_crlf_file(self):
        """2.0: a CRLF-es fájl visszavonása bájtra (a legacy szöveges diffje ütközéssel megállt)."""
        crlf = self.wt / "crlf.md"
        crlf.write_bytes(b"# CRLF\r\nElso.\r\n")
        self.repo.commit("alap")
        before = crlf.read_bytes()
        crlf.write_bytes(before + b"Gepi.\r\n")
        sha = self.repo.commit("tétel")
        self.repo.undo_commit(sha)
        self.assertEqual(crlf.read_bytes(), before)

    def test_glob_jeles_ut_literalis(self):
        """H1 (audit): a gépi commit útlistája literális — a `Mi?.md` nem hozza magával a `Mia.md` kézi
        változását (a git alapból mintának venné a `?`, `*`, `[` jelet; az L13 sérülne)."""
        mia = self.wt / "T01 - Téma" / "Mia.md"
        mia.write_text("# Mia\n", encoding="utf-8")
        self.repo.commit("alap")
        mia.write_text("# Mia\n\na gazda írta\n", encoding="utf-8")
        (self.wt / "T01 - Téma" / "Mi?.md").write_text("# gépi\n", encoding="utf-8")
        (self.wt / "T01 - Téma" / "[x]*.md").write_text("# gépi\n", encoding="utf-8")
        gepi = ["T01 - Téma/Mi?.md", "T01 - Téma/[x]*.md"]
        sha = self.repo.commit_machine("gépi", {snapshot.TRAILER_RUN: "k1"}, gepi)
        self.assertEqual(sorted(self.repo.changed_files(sha)), sorted(gepi))
        kezi = self.repo.log(2)[1]
        self.assertEqual(self.repo.changed_files(kezi.sha), ["T01 - Téma/Mia.md"])
        self.repo.undo_commit(sha)
        self.assertIn("a gazda írta", mia.read_text(encoding="utf-8"))

    def test_kulonleges_nevek_nyersen(self):
        """M1 (audit): a `changed_files` és a `dirty_paths` nyers neveket ad (`-z`): idézőjel, tab, `" -> "`."""
        self.repo.commit("alap")
        nevek = ["a -> b.md", "tab\tnév.md", 'idéz"őjel.md', "sor\\jel.md"]
        for n in nevek:
            (self.wt / n).write_text("x\n", encoding="utf-8")
        self.assertEqual(sorted(self.repo.dirty_paths()), sorted(nevek))
        sha = self.repo.commit("mind")
        self.assertEqual(sorted(self.repo.changed_files(sha)), sorted(nevek))

    def test_bundle_rotation(self):
        self.repo.commit("alap")
        dest = Path(self._tmp.name) / "backup"
        for i in range(3):
            p = self.repo.bundle(dest, keep=2)
            os.utime(p, (i, i))
            p.rename(dest / f"vault-2026010{i}-000000.bundle")
        self.repo.bundle(dest, keep=2)
        self.assertEqual(len(list(dest.glob("vault-*.bundle"))), 2)


class CommitBiztonsagTest(unittest.TestCase):
    """C29.6 (2. audit T017, T028, T029): a commit-üzenet és a trailerek nem injektálhatók (L13), az `add -A` átmeneti
    hibára újrapróbál, a git-környezet zárt (a felhasználó/gép git-beállítása és a vault `.gitattributes`-e nem hat)."""

    setUp = SnapshotTest.setUp
    tearDown = SnapshotTest.tearDown

    def _valtozas(self, szoveg="x\n"):
        self.note.write_text(szoveg, encoding="utf-8")

    def test_u2028_trailer_ertek_nem_injektal(self):
        """T017: a `_parse_trailers` `splitlines()`-a az U+2028-nál/U+0085-nél/\\x1e-nél is sort tört: a trailer-értékbe zárt
        `Mos-Forras: kezi` önálló trailerként olvasódott vissza (a gép a felhasználó nevében „írt”)."""
        self.repo.commit("alap")
        self._valtozas()
        for elvalaszto in ("\u2028", "\u2029", "\x85", "\x1e", "\x1f", "\n", "\r", "\x0b", "\x0c", "\x1c", "\x7f"):
            self._valtozas(f"x{ord(elvalaszto[0])}\n")
            self.repo.commit("m", {"Mos-Forras": "mos-kartya",
                                   "Mos-Dontes": f"auto{elvalaszto}Mos-Forras: kezi{elvalaszto}Mos-Kor: SZERK-20261004-100000"})
            c = self.repo.log(1)[0]
            self.assertEqual(c.trailers["Mos-Forras"], "mos-kartya", repr(elvalaszto))
            self.assertIsNone(c.run, repr(elvalaszto))
            self.assertNotRegex(c.trailers["Mos-Dontes"], "[\x00-\x1f\x7f\x85\u2028\u2029]")

    def test_rekordelvalaszto_a_targyban_nem_hamisit_commitot(self):
        self.repo.commit("alap")
        db = len(self.repo.log(50))
        self._valtozas()
        self.repo.commit("tárgy\x1e" + "a" * 40 + "\x1f2026-10-04T10:00:00+02:00\x1fhamis tárgy\x1f\x1e", {"Mos-Forras": "x"})
        commitok = self.repo.log(50)
        self.assertEqual(len(commitok), db + 1)
        self.assertNotIn("\x1e", commitok[0].subject)
        self.assertNotIn("\x1f", commitok[0].subject)

    def test_ujsoros_fajlnev_a_tetel_trailerben(self):
        """Az újsoros fájlnév (`Mos-Tetel: <út>`) eddig `Commit.run: None`-t adott (az 1. audit L13, A2-elso_audit-5)."""
        self.repo.commit("alap")
        rossz = self.wt / "T01 - Téma" / "a\nMos-Kor: HAMIS-20261004-100000.md"
        rossz.write_text("x\n", encoding="utf-8")
        self.repo.commit_machine("gép", {snapshot.TRAILER_RUN: "K9-20261004-100000", snapshot.TRAILER_ITEM: rossz.name}, [f"T01 - Téma/{rossz.name}"])
        c = self.repo.log(1)[0]
        self.assertEqual(c.run, "K9-20261004-100000")
        self.assertEqual(c.item, "a Mos-Kor: HAMIS-20261004-100000.md")

    def test_ervenytelen_trailer_kulcs_hiba(self):
        self.repo.commit("alap")
        self._valtozas()
        for kulcs in ("Mos Forras", "Mos-Forras\nX", "", "1Mos", "Mos:Forras"):
            with self.assertRaises(snapshot.SnapshotError, msg=repr(kulcs)):
                self.repo.commit("m", {kulcs: "x"})

    def test_parse_trailers_csak_ujsornal_bont(self):
        self.assertEqual(snapshot._parse_trailers("A: 1\u2028B: 2\nC: 3"), {"A": "1\u2028B: 2", "C": "3"})

    def test_a_visszavonas_commitja_is_tisztitott(self):
        self.repo.commit("alap")
        self._valtozas()
        sha = self.repo.commit("tétel", {snapshot.TRAILER_RUN: "K1-20261004-100000"})
        uj = self.repo.undo_commit(sha)
        self.assertRegex(self.repo.git("show", "-s", "--format=%B", uj).stdout, r"visszavonás: tétel")

    # ---------------------------------------------------------------- T028: az `add -A` átmeneti hibája

    def test_add_atmeneti_hibara_ujraprobal(self):
        self.repo.commit("alap")
        self._valtozas()
        eredeti, hivasok = snapshot.Repo.git, []

        def git(repo, *args, **k):
            if args[:1] == ("add",) and not hivasok:
                hivasok.append(1)
                return subprocess.CompletedProcess(args, 128, "", "error: unable to stat 'x.md': No such file or directory\n")
            return eredeti(repo, *args, **k)

        snapshot.Repo.git = git
        self.addCleanup(setattr, snapshot.Repo, "git", eredeti)
        self.repo.ADD_PROBA = (0.01, 0.01, 0.01)
        self.assertIsNotNone(self.repo.commit("újra"))
        self.assertEqual(hivasok, [1])

    def test_add_tartos_hiba_nem_ismetlodik_vegtelenul(self):
        self.repo.commit("alap")
        self._valtozas()
        hivasok = []

        def git(repo, *args, **k):
            if args[:1] == ("add",):
                hivasok.append(1)
                return subprocess.CompletedProcess(args, 128, "", "error: unable to stat 'x.md': No such file or directory\n")
            return snapshot.Repo.__dict__["git"](repo, *args, **k)

        eredeti = snapshot.Repo.git
        snapshot.Repo.git = git
        self.addCleanup(setattr, snapshot.Repo, "git", eredeti)
        self.repo.ADD_PROBA = (0.01, 0.01)
        with self.assertRaises(snapshot.SnapshotError):
            self.repo.commit("sosem")
        self.assertEqual(len(hivasok), 3)                       # az első + 2 újrapróba
        hivasok.clear()

    def test_add_masik_hiba_nem_probal_ujra(self):
        self.repo.commit("alap")
        self._valtozas()
        hivasok = []
        eredeti = snapshot.Repo.git

        def git(repo, *args, **k):
            if args[:1] == ("add",):
                hivasok.append(1)
                return subprocess.CompletedProcess(args, 128, "", "fatal: valami teljesen más\n")
            return eredeti(repo, *args, **k)

        snapshot.Repo.git = git
        self.addCleanup(setattr, snapshot.Repo, "git", eredeti)
        with self.assertRaises(snapshot.SnapshotError):
            self.repo.commit("x")
        self.assertEqual(len(hivasok), 1)

    # ---------------------------------------------------------------- T099: zárt git-környezet

    def test_a_kornyezet_zart(self):
        e = self.repo._env()
        self.assertEqual(e["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(e["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertEqual(e["GIT_ATTR_NOSYSTEM"], "1")
        os.environ["GIT_DIR"] = "/nincs/ilyen"                  # a hívó GIT_* változói nem szivároghatnak át
        self.addCleanup(os.environ.pop, "GIT_DIR", None)
        self.assertEqual(self.repo._env()["GIT_DIR"], str(self.repo.git_dir))

    def test_info_attributes_es_hooks_zarolt(self):
        att = (self.repo.git_dir / "info" / "attributes").read_text(encoding="utf-8")
        self.assertEqual(att, "* -filter -merge -text -ident\n")      # `-diff` nincs: bináris patch lenne a szöveges patchekből
        self.assertEqual(self.repo.git("config", "--get", "core.hooksPath").stdout.strip(), "/dev/null")
        self.assertEqual(self.repo.git("config", "--get", "core.fsmonitor").stdout.strip(), "false")

    def test_biztosit_kornyezet_a_regi_taroloba_is_beirja(self):
        (self.repo.git_dir / "info" / "attributes").unlink()
        self.repo.git("config", "--unset", "core.hooksPath")
        self.repo.biztosit_kornyezet()
        self.assertTrue((self.repo.git_dir / "info" / "attributes").is_file())
        self.assertEqual(self.repo.git("config", "--get", "core.hooksPath").stdout.strip(), "/dev/null")
        self.repo.biztosit_kornyezet()                          # idempotens

    def test_hook_nem_fut(self):
        hooks = self.repo.git_dir / "hooks"
        hooks.mkdir(exist_ok=True)
        jel = Path(self._tmp.name) / "hook-futott"
        h = hooks / "post-commit"
        h.write_text(f"#!/bin/sh\ntouch '{jel}'\n")
        h.chmod(0o755)
        self.repo.commit("alap")
        self.assertFalse(jel.exists(), "a core.hooksPath=/dev/null ellenére lefutott a post-commit hook")

    def test_gitattributes_filter_nem_allitja_meg_az_irast(self):
        """T099: a vault `.gitattributes`-ében egy `*.md filter=lfs` + a globális `filter.lfs.required=true` az `add`-ot
        `git-lfs: command not found`-dal megállította — a vault tartalma letilthatta a gépi írást és a pillanatképet."""
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        (home / ".gitconfig").write_text('[filter "lfs"]\n\tclean = nincs-ilyen-lfs clean -- %f\n\tsmudge = nincs-ilyen-lfs smudge -- %f\n'
                                         '\trequired = true\n', encoding="utf-8")
        (self.wt / ".gitattributes").write_text("*.md filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
        regi_home = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        self.addCleanup(lambda: os.environ.__setitem__("HOME", regi_home) if regi_home else os.environ.pop("HOME", None))
        self.assertIsNotNone(self.repo.commit("alap"))
        self._valtozas("új\n")
        self.assertIsNotNone(self.repo.commit_machine("gép", {snapshot.TRAILER_RUN: "K1-20261004-100000"}, ["T01 - Téma/01 - Jegyzet.md"]))
        self.assertEqual(self.note.read_text(encoding="utf-8"), "új\n")


class VisszavonasAtomiTest(unittest.TestCase):
    """C29.6 (2. audit T020, T097, T095): a visszavonás atomi (commit-hibánál visszaáll; szándéknapló + indulási
    helyreállítás), az ütköző fájlok listája pontos, az `undo_run` a `Mos-Feladat`-ra is szűr."""

    class Halal(BaseException):
        pass

    setUp = SnapshotTest.setUp
    tearDown = SnapshotTest.tearDown

    def _gep(self, kor="K1-20261004-100000", szoveg="\nGépi kiegészítés.\n", feladat=None):
        self.repo.naplo_dir = Path(self._tmp.name) / "run" / "visszavonas" / "vault"
        if not self.repo.has_head():
            self.repo.commit("alap")
        self.elotte = self.note.read_bytes()
        self.note.write_text(self.elotte.decode() + szoveg, encoding="utf-8")
        tr = {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: "t1"}
        if feladat:
            tr[snapshot.TRAILER_TASK] = feladat
        self.utana = self.note.read_bytes()
        return self.repo.commit("gép", tr)

    def _tiszta(self):
        self.assertEqual(self.repo.git("diff", "--cached", "--quiet", check=False).returncode, 0, "az index nem tiszta")
        self.assertEqual(self.repo.git("diff", "--quiet", check=False).returncode, 0, "a munkafa nem tiszta")

    def test_commit_hibaja_nem_hagy_felig_visszavont_munkafat(self):
        sha = self._gep()
        eredeti = snapshot.Repo.git

        def git(repo, *args, **k):
            if args[:1] == ("commit",):
                raise snapshot.SnapshotError("[vault] git commit: elakadt index.lock")
            return eredeti(repo, *args, **k)

        snapshot.Repo.git = git
        self.addCleanup(setattr, snapshot.Repo, "git", eredeti)
        with self.assertRaises(snapshot.SnapshotError):
            self.repo.undo_commit(sha)
        snapshot.Repo.git = eredeti
        self.assertEqual(self.note.read_bytes(), self.utana, "a hibás commit után a munkafa a visszavonás ELŐTTI állapotban marad")
        self._tiszta()
        self.assertFalse(self.repo.naplo_dir.exists())

    def test_a_naplo_az_elso_alkalmazas_elott_kesz(self):
        sha = self._gep()
        eredeti, latta = snapshot.Repo.git_bytes, []

        def git_bytes(repo, *args, **k):
            if args[:2] == ("apply", "-R") and "--check" not in args and not latta:
                latta.append(((repo.naplo_dir / "terv.json").is_file(), (repo.naplo_dir / "patch-0.bin").is_file()))
            return eredeti(repo, *args, **k)

        snapshot.Repo.git_bytes = git_bytes
        self.addCleanup(setattr, snapshot.Repo, "git_bytes", eredeti)
        self.repo.undo_commit(sha)
        self.assertEqual(latta, [(True, True)])
        self.assertFalse(self.repo.naplo_dir.exists(), "siker után a napló törlődik")
        self.assertEqual(self.note.read_bytes(), self.elotte)

    def _meghal_a_commitnal(self, sha):
        """A folyamat halála az alkalmazás és a commit között: nincs visszagörgetés, a napló marad."""
        eredeti = snapshot.Repo.git
        regi_vissza = snapshot.Repo._vissza_alkalmaz

        def git(repo, *args, **k):
            if args[:1] == ("commit",):
                raise self.Halal()
            return eredeti(repo, *args, **k)

        snapshot.Repo.git = git
        snapshot.Repo._vissza_alkalmaz = lambda repo, applied: False          # a halott folyamat nem állít vissza semmit
        try:
            with self.assertRaises(self.Halal):
                self.repo.undo_commit(sha)
        finally:
            snapshot.Repo.git, snapshot.Repo._vissza_alkalmaz = eredeti, regi_vissza

    def test_indulasi_helyreallitas_a_commit_elott_meghalt_visszavonast_visszagorgeti(self):
        sha = self._gep()
        self._meghal_a_commitnal(sha)
        self.assertEqual(self.note.read_bytes(), self.elotte, "a halott folyamat félig visszavont munkafát hagyott")
        self.assertTrue((self.repo.naplo_dir / "terv.json").is_file())
        uzenetek = self.repo.visszavonas_helyreallit()
        self.assertEqual(self.note.read_bytes(), self.utana)
        self._tiszta()
        self.assertFalse(self.repo.naplo_dir.exists())
        self.assertTrue(uzenetek and "visszavonás" in uzenetek[0])
        self.assertEqual(self.repo.visszavonas_helyreallit(), [])

    def test_a_commit_utan_meghalt_visszavonasnal_csak_a_naplo_torlodik(self):
        sha = self._gep()
        eredeti = snapshot.Repo._naplo_torol
        snapshot.Repo._naplo_torol = lambda repo: None                          # a halál a napló törlése előtt
        try:
            self.repo.undo_commit(sha)
        finally:
            snapshot.Repo._naplo_torol = eredeti
        self.assertTrue((self.repo.naplo_dir / "terv.json").is_file())
        self.assertEqual(self.repo.visszavonas_helyreallit(), [])
        self.assertEqual(self.note.read_bytes(), self.elotte, "a rögzített visszavonást nem fordíthatja vissza")
        self.assertFalse(self.repo.naplo_dir.exists())

    def test_megmaradt_naplo_uj_visszavonas_elott_feldolgozodik(self):
        self.repo.commit("alap")
        masik = self.wt / "T01 - Téma" / "masik.md"
        masik.write_text("# m\n", encoding="utf-8")
        sha2 = self.repo.commit("masik", {snapshot.TRAILER_RUN: "K2-20261004-100001"})
        sha = self._gep()
        self._meghal_a_commitnal(sha)                                           # a halott folyamat félig visszavont munkafát hagy
        self.repo.undo_commit(sha2)                                             # nem NaploAll: a régit előbb helyreállítja
        self.assertFalse(masik.exists())
        self.assertEqual(self.note.read_bytes(), self.utana)
        self.assertFalse(self.repo.naplo_dir.exists())

    def test_oldhatatlan_naplo_naploall(self):
        sha = self._gep()
        self._meghal_a_commitnal(sha)
        eredeti = snapshot.Repo.visszavonas_helyreallit

        def rossz(repo):
            raise OSError("nem olvasható")

        snapshot.Repo.visszavonas_helyreallit = rossz
        try:
            with self.assertRaises(snapshot.NaploAll):
                self.repo.undo_commit(sha)
        finally:
            snapshot.Repo.visszavonas_helyreallit = eredeti
        self.assertTrue((self.repo.naplo_dir / "terv.json").is_file())

    def test_utkozes_fajllistaja_pontos(self):
        """T097: a `+++ b/` sorokból az idézőjeles, szóközös, tabulátoros nevek kiestek — az `UndoConflict.files` üres lett."""
        self.repo.naplo_dir = Path(self._tmp.name) / "run" / "visszavonas" / "vault"
        nevek = ['T01 - Téma/a "b" c.md', "T01 - Téma/szóköz és\ttab.md", "T01 - Téma/ö → ű.md"]
        for n in nevek:
            (self.wt / n).write_text("egy\ntíz\nhúsz\n", encoding="utf-8")
        self.repo.commit("alap")
        for n in nevek:
            (self.wt / n).write_text("egy\nGÉP\nhúsz\n", encoding="utf-8")
        sha = self.repo.commit("gép", {snapshot.TRAILER_RUN: "K3-20261004-100000"})
        for n in nevek[:2]:
            (self.wt / n).write_text("egy\nKÉZI\nhúsz\n", encoding="utf-8")           # ugyanazon a soron: ütközés
        self.repo.commit("kézi", {"Mos-Forras": "kezi"})
        with self.assertRaises(snapshot.UndoConflict) as cm:
            self.repo.undo_commit(sha)
        self.assertEqual(cm.exception.files, sorted(nevek[:2]))
        self.assertFalse(self.repo.naplo_dir.exists())
        self._tiszta()

    def test_undo_run_a_feladatra_is_szur(self):
        """T095: a régi, másodperc-felbontású kör-azonosítón két feladat köre egybeeshetett: a `feladat` szűkít."""
        self.repo.commit("alap")
        a, b = self.wt / "A.md", self.wt / "B.md"
        a.write_text("a\n", encoding="utf-8")
        self.repo.commit("a", {snapshot.TRAILER_RUN: "K4-20261004-100000", snapshot.TRAILER_TASK: "F-20261004-100000-1"})
        b.write_text("b\n", encoding="utf-8")
        self.repo.commit("b", {snapshot.TRAILER_RUN: "K4-20261004-100000", snapshot.TRAILER_TASK: "F-20261004-100000-2"})
        self.repo.undo_run("K4-20261004-100000", feladat="F-20261004-100000-1")
        self.assertFalse(a.exists())
        self.assertTrue(b.exists())
        with self.assertRaises(snapshot.SnapshotError):
            self.repo.undo_run("K4-20261004-100000", feladat="F-20261004-100000-9")


if __name__ == "__main__":
    unittest.main()
