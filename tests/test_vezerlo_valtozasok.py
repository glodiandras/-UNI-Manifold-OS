"""C20a / T144: a „Mit változtatott” a `Mos-Feladat` trailer szerint a TELJES történetben keres (nem az utolsó 500
commitban), a fájllisták egy git-folyamatból jönnek, a csonka lista jelezve van. Álgyökérben, a valódi var/-hoz nem nyúl."""
import unittest
from unittest import mock

from core import snapshot, vezerlo
from core.utvonalak import HttpError
from tests.helpers import alg_core, ir, tmpdir

FID = "F-20261004-100000-1"
KOR = "VIDEO-20261004-100000-aaaaaa"


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()

    def gepi(self, fid: str, kor: str, ut: str, szoveg: str = "x\n", tetel: str = "t1") -> str:
        ir(self.v, ut, szoveg)
        return self.repo.commit_machine(f"gépi: {ut}", {snapshot.TRAILER_TASK: fid, snapshot.TRAILER_RUN: kor,
                                                        snapshot.TRAILER_ITEM: tetel, "Mos-Forras": "mos-video"}, [ut])

    def sok_ures_commit(self, db: int, uzenet: str = "kézi", trailer: str = "") -> None:
        """`db` üres commit gyorsan (`git fast-import`), a gépi commitok UTÁN."""
        ag = self.repo.git("symbolic-ref", "HEAD").stdout.strip()
        fej = self.repo.git("rev-parse", "HEAD").stdout.strip()
        szoveg = uzenet + (("\n\n" + trailer) if trailer else "") + "\n"
        adat = szoveg.encode("utf-8")
        script = []
        for i in range(db):
            script.append(f"commit {ag}\ncommitter T <t@t> {1_800_000_000 + i} +0000\ndata {len(adat)}\n{szoveg}"
                          + (f"from {fej}\n" if i == 0 else "") + "\n")
        self.repo.git("fast-import", "--quiet", input="".join(script))


class ValtozasokTeszt(Alap):
    def test_a_regi_feladat_commitja_500_ujabb_commit_utan_is_megvan(self):
        """A régi kód az utolsó 500 commitban keresett: a régebbi feladatra hamisan „Nem írt a vaultba” lett a válasz."""
        sha = self.gepi(FID, KOR, "ATTCHMNTS - Videos/film.md")
        self.sok_ures_commit(700)
        self.assertGreater(int(self.repo.git("rev-list", "--count", "HEAD").stdout), 700)
        d = vezerlo.valtozasok(self.cfg, FID)
        self.assertEqual(len(d["korok"]), 1, d)
        (c,) = d["korok"][0]["commitok"]
        self.assertEqual(c["sha"], sha)
        self.assertEqual(c["fajlok"], [{"ut": "ATTCHMNTS - Videos/film.md", "allapot": "A", "plusz": 1, "minusz": 0}])
        self.assertFalse(d["levagva"])
        self.assertTrue(d["korok"][0]["visszavonhato"])

    def test_a_visszavonas_a_trailerbol_felismerheto_teljes_tortenetben(self):
        self.gepi(FID, KOR, "a.md")
        self.sok_ures_commit(600, "Visszavonás: " + KOR, f"Mos-Visszavon-Kor: {KOR}")
        d = vezerlo.valtozasok(self.cfg, FID)
        self.assertEqual([(k["kor"], k["visszavonva"], k["visszavonhato"]) for k in d["korok"]], [(KOR, True, False)])

    def test_tobb_kor_regebbi_elol_es_a_masik_feladat_nem_keveredik(self):
        self.gepi(FID, KOR, "a.md")
        self.gepi("F-20261004-100000-12", "VIDEO-20261004-100100-bbbbbb", "masik.md")
        self.gepi(FID, "VIDEO-20261004-100200-cccccc", "b.md", tetel="t2")
        d = vezerlo.valtozasok(self.cfg, FID)
        self.assertEqual([k["kor"] for k in d["korok"]], [KOR, "VIDEO-20261004-100200-cccccc"])
        self.assertEqual([c["tetel"] for k in d["korok"] for c in k["commitok"]], ["t1", "t2"])

    def test_a_fajllistak_egyetlen_git_folyamatbol_jonnek(self):
        for i in range(6):
            self.gepi(FID, f"VIDEO-20261004-10{i:02d}00-aaaaaa", f"f{i}.md")
        hivasok = []
        eredeti = snapshot.Repo.git

        def szamol(repo, *args, **kw):
            hivasok.append(args[0])
            return eredeti(repo, *args, **kw)
        with mock.patch.object(snapshot.Repo, "git", szamol):
            d = vezerlo.valtozasok(self.cfg, FID)
        self.assertEqual(sum(len(k["commitok"]) for k in d["korok"]), 6)
        self.assertLessEqual(hivasok.count("log"), 3, hivasok)
        self.assertNotIn("show", hivasok, "a régi kód commitonként két `git show`-t futtatott")

    def test_a_csonka_lista_jelezve_van(self):
        for i in range(5):
            self.gepi(FID, f"VIDEO-20261004-10{i:02d}00-aaaaaa", f"f{i}.md")
        with mock.patch.object(vezerlo, "MAX_COMMIT", 3):
            d = vezerlo.valtozasok(self.cfg, FID)
        self.assertTrue(d["levagva"])
        self.assertEqual(sum(len(k["commitok"]) for k in d["korok"]), 3)
        self.assertEqual([k["kor"] for k in d["korok"]],
                         [f"VIDEO-20261004-10{i:02d}00-aaaaaa" for i in (2, 3, 4)], "a legfrissebb három")

    def test_ismeretlen_feladat_ures_nem_csonka(self):
        d = vezerlo.valtozasok(self.cfg, "F-nincs")
        self.assertEqual((d["korok"], d["nincs_tar"], d["levagva"]), ([], False, False))

    def test_ervenytelen_azonosito_400(self):
        for fid in ("F-ü", "F x", "F-1\nMos-Kor: X"):
            with self.subTest(fid=fid), self.assertRaises(HttpError) as cm:
                vezerlo.valtozasok(self.cfg, fid)
            self.assertEqual(cm.exception.code, 400)

    def test_nincs_tar(self):
        import shutil
        shutil.rmtree(self.repo.git_dir)
        d = vezerlo.valtozasok(self.cfg, FID)
        self.assertEqual((d["korok"], d["nincs_tar"]), ([], True))


class TrailerCommitokTeszt(Alap):
    def test_pontos_egyezes_nem_elotag(self):
        self.gepi("F-1", "K-1", "a.md")
        self.gepi("F-12", "K-12", "b.md")
        c, lev = self.repo.trailer_commitok("Mos-Feladat", "F-1")
        self.assertEqual([x.trailers["Mos-Kor"] for x in c], ["K-1"])
        self.assertFalse(lev)
        c, _ = self.repo.trailer_commitok("Mos-Kor")
        self.assertEqual(len(c), 2, "érték nélkül minden `Mos-Kor`-os commit")

    def test_veszelyes_ertek_elutasitva(self):
        for ertek in ("a.*", "x\n^Mos", "(a|b)", "a b"):
            with self.subTest(ertek=ertek), self.assertRaises(ValueError):
                self.repo.trailer_commitok("Mos-Feladat", ertek)
        with self.assertRaises(ValueError):
            self.repo.trailer_commitok("Mos Feladat", "F-1")

    def test_commitok_fajlok_eszrevetlen_nev_es_torles(self):
        self.gepi("F-1", "K-1", "szóköz és ékezet.md")
        sha = self.repo.git("rev-parse", "HEAD").stdout.strip()
        (self.v / "szóköz és ékezet.md").unlink()
        self.repo.commit_machine("törlés", {snapshot.TRAILER_TASK: "F-1", snapshot.TRAILER_RUN: "K-2"}, ["szóköz és ékezet.md"])
        sha2 = self.repo.git("rev-parse", "HEAD").stdout.strip()
        ki = self.repo.commitok_fajlok([sha2, sha])
        self.assertEqual(ki[sha], self.repo.commit_fajlok(sha))
        self.assertEqual(ki[sha2], self.repo.commit_fajlok(sha2))
        self.assertEqual(ki[sha2][0]["allapot"], "D")
        self.assertEqual(self.repo.commitok_fajlok([]), {})


if __name__ == "__main__":
    unittest.main()
